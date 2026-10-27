"""Filesystem publication candidate for disposable fixtures; never a launcher."""
import os
from pathlib import Path

EVENTS=('begin','attempt.open','attempt.partial','attempt.complete','attempt.file_sync','attempt.close',
    'attempt.directory_sync','attempt.parent_directory_sync','payload.begin','materials.synced',
    'receipt.part_open','receipt.partial','receipt.complete','receipt.file_sync','receipt.close',
    'receipt.link','receipt.directory_sync','stdout.emit')
FAILURES=('attempt.open','attempt.file_sync','attempt.directory_sync','attempt.parent_directory_sync',
    'materials.synced','receipt.file_sync','receipt.link','receipt.directory_sync')


def write_all(fd,raw):
    view=memoryview(raw)
    while view:
        count=os.write(fd,view)
        if count<=0:raise OSError('fixture write made no progress')
        view=view[count:]


def sync_directory(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


def publish(job,attempt_raw,materials,receipt_raw,checkpoint):
    job=Path(job)
    if not job.is_absolute() or job!=job.resolve() or not job.is_relative_to('/private/tmp'):
        raise ValueError('canonical temporary fixture job required')
    def at(label,action):
        checkpoint(label,'before');value=action();checkpoint(label,'after');return value
    at('begin',lambda:None)
    fd=at('attempt.open',lambda:os.open(job/'launch-attempt.json',os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600))
    try:
        half=max(1,len(attempt_raw)//2)
        at('attempt.partial',lambda:write_all(fd,attempt_raw[:half]))
        at('attempt.complete',lambda:write_all(fd,attempt_raw[half:]))
        at('attempt.file_sync',lambda:os.fsync(fd))
    finally:os.close(fd)
    at('attempt.close',lambda:None)
    at('attempt.directory_sync',lambda:sync_directory(job))
    at('attempt.parent_directory_sync',lambda:sync_directory(job.parent))
    # This is a model barrier, not a production execution permit.
    at('payload.begin',lambda:None)
    result=job/'result'
    def save_materials():
        result.mkdir(mode=0o700)
        dirs={job,result}
        for name,raw in materials.items():
            if not isinstance(name,str) or name.startswith('/') or any(p in ('','.','..') for p in name.split('/')):
                raise ValueError('fixture material path differs')
            target=result/'materials'/name;target.parent.mkdir(parents=True,exist_ok=True)
            fd=os.open(target,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            try:write_all(fd,raw);os.fsync(fd)
            finally:os.close(fd)
            parent=target.parent
            while parent!=job:dirs.add(parent);parent=parent.parent
        for path in sorted(dirs,key=lambda p:len(p.parts),reverse=True):sync_directory(path)
    at('materials.synced',save_materials)
    part=result/'receipt.json.part'
    fd=at('receipt.part_open',lambda:os.open(part,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600))
    try:
        half=max(1,len(receipt_raw)//2)
        at('receipt.partial',lambda:write_all(fd,receipt_raw[:half]))
        at('receipt.complete',lambda:write_all(fd,receipt_raw[half:]))
        at('receipt.file_sync',lambda:os.fsync(fd))
    finally:os.close(fd)
    at('receipt.close',lambda:None)
    # Same-directory hard link publishes complete bytes without replacing any
    # existing receipt. Keep the staging name as forensic fixture evidence.
    at('receipt.link',lambda:os.link(part,result/'receipt.json'))
    at('receipt.directory_sync',lambda:sync_directory(result))


def recover(_job):
    """Recovery has no write/launch capability and never retries a prepared job."""
    raise ValueError('fixture recovery refuses restart; retain all evidence')
