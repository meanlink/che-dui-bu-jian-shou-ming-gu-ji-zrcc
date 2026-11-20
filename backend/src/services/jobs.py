import hashlib
import json
import time
from fastapi import HTTPException
from redis import Redis
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from src.config.settings import REDIS_URL
from src.models import Dataset, Job
from src.services.business import metadata, merge_observations, apply_supplements


def _fingerprint(parent_id, supplements):
    canonical = [{"asset": item["asset"].strip(), "lower_km": float(item["lower_km"]), "upper_km": float(item["upper_km"])} for item in supplements]
    canonical.sort(key=lambda item: (item["asset"], item["lower_km"], item["upper_km"]))
    blob = json.dumps({"parent": parent_id, "supplements": canonical}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()


def _flatten(batches):
    result = []
    for batch in batches or []:
        result.extend(batch if isinstance(batch, list) else [batch])
    return result


def create(db, data, user):
    if not db.get(Dataset, data.dataset_id): raise HTTPException(404,'数据批次不存在')
    allowed={p['key']:p for p in metadata().get('parameters',[])}
    if set(data.params)-set(allowed): raise HTTPException(422,'包含未知分析参数')
    params={k:p['default'] for k,p in allowed.items()}
    params.update(data.params)
    for key,p in allowed.items():
        v=params[key]
        if p['type']=='number':
            try:
                v=float(v)
                if not (p.get('min',-1e9)<=v<=p.get('max',1e9)): raise ValueError()
                params[key]=v
            except (ValueError,TypeError): raise HTTPException(422, f'{p["label"]} 超出范围或非数值')
        elif str(v) not in [str(o['value']) for o in p.get('options',[])]:
            raise HTTPException(422,f'{p["label"]} 不是有效选项')
    j=Job(name=data.name, dataset_id=data.dataset_id, params=params, created_by=user.id, created_at=time.time(), status='queued', revision=1, supplements=[], fingerprint='')
    db.add(j); db.flush()
    j.root_id=j.id
    return j


def _normalized_batch(batch):
    return sorted((item["asset"].strip(), float(item["lower_km"]), float(item["upper_km"])) for item in batch)


def _batch_already_applied(job, supplements):
    requested = _normalized_batch(supplements)
    return any(_normalized_batch(batch) == requested for batch in (job.supplements or []))


def locked(db, job_id):
    # populate_existing forces a fresh read under the row lock so a supplement and an approval
    # racing on the same version see each other's committed state.
    return db.scalar(select(Job).where(Job.id==job_id).with_for_update().execution_options(populate_existing=True))


def new_version(db, parent_id, data, user):
    """Create the next version from a supplement report. An identical retry returns the same version."""
    parent=locked(db,parent_id)
    if not parent: raise HTTPException(404,'分析任务不存在')
    if parent.status!='completed': raise HTTPException(409,'仅已完成的结果可以接受补报')
    supplements=[{'asset':item.asset.strip(),'lower_km':float(item.lower_km),'upper_km':float(item.upper_km)} for item in data.supplements]
    root_id=parent.root_id or parent.id
    fingerprint=_fingerprint(parent.id,supplements)
    existing=db.scalar(select(Job).where(Job.root_id==root_id,Job.fingerprint==fingerprint))
    if existing:
        return existing, False
    # A retry may arrive against the latest version that already applied this exact report.
    if _batch_already_applied(parent, supplements):
        return parent, False
    if parent.superseded_by is not None:
        raise HTTPException(409,'该估计已有补报新版本，请基于最新版本继续补报')
    dataset=db.get(Dataset,parent.dataset_id)
    if not dataset: raise HTTPException(409,'原数据批次不存在，无法补报')
    try:
        # Validate the whole chain against the raw batch so a supplement cannot silently revert an earlier narrowing.
        apply_supplements(merge_observations(dataset.records), [*_flatten(parent.supplements), supplements])
    except ValueError as error:
        raise HTTPException(422,str(error)) from None
    base_name=parent.name.split(' · 补报')[0]
    child=Job(name=f'{base_name} · 补报 v{parent.revision+1}', dataset_id=parent.dataset_id, params=parent.params, status='queued', result={}, error='', approved=False,
              created_by=user.id, created_at=time.time(), root_id=root_id, revision=parent.revision+1,
              supplements=[*parent.supplements, supplements], fingerprint=fingerprint)
    db.add(child)
    try:
        db.flush()
    except IntegrityError:
        # A concurrent identical retry won the unique (root_id, fingerprint) race; reuse its version.
        db.rollback()
        existing=db.scalar(select(Job).where(Job.root_id==root_id,Job.fingerprint==fingerprint))
        if existing: return existing, False
        raise HTTPException(409,'该估计已有并发补报生成的版本，请刷新后基于最新版本继续补报') from None
    parent.superseded_by=child.id
    return child, True


def chain(db, job):
    root=job.root_id or job.id
    return list(db.scalars(select(Job).where(Job.root_id==root).order_by(Job.revision,Job.id)))


def enqueue(job_id):
    try:
        r=Redis.from_url(REDIS_URL); r.rpush('analysis:queue',job_id); r.close()
    except Exception:
        pass # SQL queued status is the durable fallback
