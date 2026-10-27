"""Exclusive durable65 burn with an immutable invocation commitment. No USB."""
import fcntl
import os
from pathlib import Path
import re
import uuid
from datetime import datetime,timezone
import context65_workflow as w

LEDGER=w.LEDGER

def entries(ledger):
    ledger=w.canonical(ledger)
    if not ledger.exists():return {}
    w.require(ledger.is_dir(),'ledger not directory');result={}
    for path in sorted(ledger.iterdir()):
        if path.name=='.lock':w.require(path.is_file() and not path.is_symlink(),'invalid lock');continue
        match=re.fullmatch(r'block-(\d{5})\.json',path.name);w.require(match is not None,'unknown ledger artifact')
        first=int(match[1]);value=w.load(path)
        base={'schema','first','last','record','scope','receiver','id','created_at','simulation'}
        schema=value.get('schema');extra={'preparation_id','commitment_sha256'} if schema=='A23-sequence-reservation-2' else set()
        w.require(schema in ('A23-sequence-reservation-1','A23-sequence-reservation-2') and set(value)==base|extra and
            type(value['first']) is int and value['first']==first and path.name==f'block-{first:05d}.json' and
            1<=first<=65505 and (first-1)%16==0 and type(value['last']) is int and value['last']==first+15 and
            type(value['simulation']) is bool and str(uuid.UUID(value['id']))==value['id'],'invalid reservation')
        for key in ('scope','receiver',*(['commitment_sha256'] if extra else [])):
            w.require(type(value[key]) is str and re.fullmatch('[0-9a-f]{64}',value[key]),'invalid reservation hash')
        if extra:w.require(str(uuid.UUID(value['preparation_id']))==value['preparation_id'],'invalid preparation id')
        w.canonical(value['record']);w.timestamp(value['created_at']);result[first]=dict(path=str(path),sha256=w.sha(w.plain(path)),value=value)
    return result

def location(path,ledger):
    path=w.canonical(path);ledger=w.canonical(ledger);model=Path('/private/tmp') in path.parents
    w.require((model and Path('/private/tmp') in ledger.parents) or (not model and path.parent==w.A and ledger==LEDGER),'record/ledger location mismatch')
    return path,ledger,model

def available(path,ledger):
    path,ledger,model=location(path,ledger)
    used={n for row in entries(ledger).values() for n in range(row['value']['first'],row['value']['last']+1)}
    w.require(not used.intersection(range(65,81)),'65..80 already burned; never reuse')
    return path,ledger,model

def burn(path,ledger,record):
    path,ledger,model=available(path,ledger);ledger.mkdir(mode=0o700,exist_ok=True);w.b.old.sync_dir(ledger.parent)
    fd=os.open(ledger/'.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);available(path,ledger)
        value=dict(schema='A23-sequence-reservation-2',first=65,last=80,record=str(path),scope=w.b.device.HISTORY_DIGEST,
            receiver=record['receiver_sha256'],preparation_id=record['preparation_id'],commitment_sha256=w.commitment(record),
            id=str(uuid.uuid4()),created_at=datetime.now(timezone.utc).isoformat(),simulation=model)
        target=ledger/'block-00065.json';w.write(target,value)
        receipt=dict(directory=str(ledger),path=str(target),sha256=w.sha(w.plain(target)),simulation=model)
        verify(receipt,path,record);return receipt
    finally:os.close(fd)

def verify(receipt,path,record):
    w.require(type(receipt) is dict and set(receipt)=={'directory','path','sha256','simulation'},'reservation receipt required')
    path,ledger,model=location(path,receipt['directory']);row=entries(ledger).get(65)
    w.require(row is not None and receipt['simulation'] is model and receipt['path']==row['path'] and receipt['sha256']==row['sha256'],'burn receipt differs')
    v=row['value'];w.require(v['schema']=='A23-sequence-reservation-2' and v['simulation'] is model and v['record']==str(path) and
        v['scope']==w.b.device.HISTORY_DIGEST and v['receiver']==record['receiver_sha256'] and
        v['preparation_id']==record['preparation_id'] and v['commitment_sha256']==w.commitment(record),'reservation invocation commitment differs')
    return True
