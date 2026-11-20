from fastapi import HTTPException
from sqlalchemy import select
from src.models import Dataset
from src.services.business import metadata, merge_observations
from src.utils.serialization import checksum
import math, time
def create(db, data):
    name=data.name.strip()
    if len(name)<2: raise HTTPException(422, '批次名称去除空格后至少需要两个字符')
    if db.scalar(select(Dataset).where(Dataset.name==name)):
        raise HTTPException(409, '该数据批次名已存在，请修改名称')
    for index,row in enumerate(data.records):
        if not isinstance(row,dict): raise HTTPException(422, f'第 {index+1} 行不是有效记录')
        for c in metadata()['columns']:
            value=row.get(c['key'])
            if value is None or value=='':
                if c.get('required',True): raise HTTPException(422, f'第 {index+1} 行缺少字段 {c["label"]}')
                continue
            if c['type']=='number':
                try:
                    if isinstance(value,bool) or not math.isfinite(float(value)): raise ValueError()
                    row[c['key']]=float(value)
                except (TypeError, ValueError, OverflowError): raise HTTPException(422, f'第 {index+1} 行 {c["label"]} 必须为有限数值')
    for index,row in enumerate(data.records):
        lower=row.get('km_lower')
        if lower in (None,''): continue
        try:
            if not 0<=float(lower)<=float(row['km']): raise ValueError()
        except (KeyError,TypeError,ValueError,OverflowError):
            raise HTTPException(422, f'第 {index+1} 行上次检查里程须为0与发现失效里程之间的数值') from None
    try:
        merge_observations(data.records)
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    d=Dataset(name=name, source=data.source, records=data.records, checksum=checksum(data.records), created_at=time.time())
    db.add(d); db.flush()
    return d
