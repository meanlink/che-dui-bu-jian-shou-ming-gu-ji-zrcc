import time
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from src.config.database import get_db
from src.models import Job
from src.schemas.job import JobInput, SupplementInput
from src.middlewares.auth import current_user, can_write, admin_only
from src.services import jobs
from src.services.audit import record
from src.utils.serialization import job_dict
router=APIRouter(prefix='/jobs')
@router.get('')
def listing(db=Depends(get_db),u=Depends(current_user)):
    return [job_dict(j) for j in db.scalars(select(Job).order_by(Job.id.desc()).limit(100))]
@router.post('',status_code=201)
def create(data:JobInput,db=Depends(get_db),u=Depends(can_write)):
    j=jobs.create(db,data,u); record(db,u.email,'job.create',{'id':j.id,'params':j.params})
    db.commit(); jobs.enqueue(j.id); return job_dict(j)
@router.get('/{id}')
def detail(id:int,db=Depends(get_db),u=Depends(current_user)):
    j=db.get(Job,id)
    if not j: raise HTTPException(404,'分析任务不存在')
    return job_dict(j)
@router.get('/{id}/versions')
def versions(id:int,db=Depends(get_db),u=Depends(current_user)):
    j=db.get(Job,id)
    if not j: raise HTTPException(404,'分析任务不存在')
    return [job_dict(item) for item in jobs.chain(db,j)]
@router.post('/{id}/supplements',status_code=201)
def supplement(id:int,data:SupplementInput,response:Response,db=Depends(get_db),u=Depends(can_write)):
    child,created=jobs.new_version(db,id,data,u)
    if created:
        record(db,u.email,'job.supplement',{'parent':id,'id':child.id,'revision':child.revision,'supplements':child.supplements[-1:]})
    else:
        response.status_code=200
        record(db,u.email,'job.supplement.retry',{'parent':id,'id':child.id,'revision':child.revision})
    db.commit()
    if created: jobs.enqueue(child.id)
    return job_dict(child)
@router.post('/{id}/approve')
def approve(id:int,db=Depends(get_db),u=Depends(admin_only)):
    j=jobs.locked(db,id)
    if not j: raise HTTPException(404,'分析任务不存在')
    if j.status!='completed':raise HTTPException(409,'仅已完成结果可以批准')
    if j.superseded_by is not None:raise HTTPException(409,'该估计已有补报新版本，旧区间不可再批准；请复核最新版本')
    j.approved=True
    if j.approved_at is None:j.approved_at=time.time()
    record(db,u.email,'job.approve',{'id':id,'revision':j.revision,'interval_snapshot':j.result.get('observations')}); db.commit()
    return job_dict(j)
