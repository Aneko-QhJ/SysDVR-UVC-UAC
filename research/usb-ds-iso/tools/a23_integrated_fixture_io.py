"""Split the frozen fixture publication protocol across parent and child."""
import os
from pathlib import Path
from a23_fixture_publication import write_all,sync_directory,EVENTS
PRE_EVENTS=EVENTS[:8]
CHILD_EVENTS=EVENTS[8:]
PRE_FAILURES=('attempt.file_sync','attempt.directory_sync','attempt.parent_directory_sync')
CHILD_FAILURES=('materials.synced','receipt.file_sync','receipt.link','receipt.directory_sync')


def at(checkpoint,label,action):
    checkpoint(label,'before');value=action();checkpoint(label,'after');return value


def publish_attempt(job,raw,checkpoint):
    job=Path(job);at(checkpoint,'begin',lambda:None)
    fd=at(checkpoint,'attempt.open',lambda:os.open(job/'launch-attempt.json',os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600))
    try:
        half=max(1,len(raw)//2)
        at(checkpoint,'attempt.partial',lambda:write_all(fd,raw[:half]))
        at(checkpoint,'attempt.complete',lambda:write_all(fd,raw[half:]))
        at(checkpoint,'attempt.file_sync',lambda:os.fsync(fd))
    finally:os.close(fd)
    at(checkpoint,'attempt.close',lambda:None)
    at(checkpoint,'attempt.directory_sync',lambda:sync_directory(job))
    at(checkpoint,'attempt.parent_directory_sync',lambda:sync_directory(job.parent))


def publish_result(job,materials,receipt_raw,checkpoint):
    job=Path(job);at(checkpoint,'payload.begin',lambda:None);result=job/'result'
    def save():
        result.mkdir(mode=0o700);dirs={job,result}
        for name,raw in materials.items():
            if not isinstance(name,str) or name.startswith('/') or any(p in ('','.','..') for p in name.split('/')):
                raise ValueError('integrated fixture material path differs')
            target=result/'materials'/name;target.parent.mkdir(parents=True,exist_ok=True)
            fd=os.open(target,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            try:write_all(fd,raw);os.fsync(fd)
            finally:os.close(fd)
            parent=target.parent
            while parent!=job:dirs.add(parent);parent=parent.parent
        for path in sorted(dirs,key=lambda p:len(p.parts),reverse=True):sync_directory(path)
    at(checkpoint,'materials.synced',save)
    part=result/'receipt.json.part';fd=at(checkpoint,'receipt.part_open',lambda:os.open(part,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600))
    try:
        half=max(1,len(receipt_raw)//2)
        at(checkpoint,'receipt.partial',lambda:write_all(fd,receipt_raw[:half]))
        at(checkpoint,'receipt.complete',lambda:write_all(fd,receipt_raw[half:]))
        at(checkpoint,'receipt.file_sync',lambda:os.fsync(fd))
    finally:os.close(fd)
    at(checkpoint,'receipt.close',lambda:None)
    at(checkpoint,'receipt.link',lambda:os.link(part,result/'receipt.json'))
    at(checkpoint,'receipt.directory_sync',lambda:sync_directory(result))


def record(job,label,outcome):
    import json
    raw=json.dumps(dict(event=label,outcome=outcome),sort_keys=True,separators=(',',':')).encode()+b'\n'
    fd=os.open(Path(job)/'trace.jsonl',os.O_CREAT|os.O_APPEND|os.O_WRONLY,0o600)
    try:write_all(fd,raw)
    finally:os.close(fd)
