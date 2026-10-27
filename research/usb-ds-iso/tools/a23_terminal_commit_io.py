"""Exclusive local publication with a final manifest; no process supervision."""
import hashlib,json,os

def encode(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(v):return hashlib.sha256(v).hexdigest()


def write_all(fd,data):
    view=memoryview(data)
    while view:
        count=os.write(fd,view)
        if type(count) is not int or not 0<count<=len(view):raise OSError('publication write stalled')
        view=view[count:]


def sync_directory(job):
    fd=os.open(job,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


def use_record(metadata):return dict(schema='A23-terminal-commit-use-1',maximum_publications=1,model_only=True,**metadata)
def commit_record(metadata,records):
    return dict(schema='A23-terminal-commit-record-1',records={name:dict(sha256=sha(raw),size=len(raw)) for name,raw in records.items()},
        process_wait_verified=False,model_only=True,**metadata)


def publish(job,role,records,metadata,event):
    names=[role+'-'+suffix for suffix in ('failed-status.bin','transport.json','exit.json')]
    if role not in ('requester','worker') or list(records) not in ([names[-1]],names) or any(type(raw) is not bytes or not 0<len(raw)<=8192 for raw in records.values()):raise ValueError('fixed bounded local records required')
    name=role+'-terminal-use.json';data=encode(use_record(metadata));event('use','before',data,0)
    with (job/name).open('xb',buffering=0) as stream:
        event('use','created',data,0);half=len(data)//2;write_all(stream.fileno(),data[:half]);event('use','half',data,half)
        write_all(stream.fileno(),data[half:]);os.fsync(stream.fileno());event('use','file_sync',data,len(data))
    sync_directory(job);event('use','dir_sync',data,len(data))
    def put(kind,name,data):
        event(kind,'before',data,0);part=job/(name+'.part')
        with part.open('xb',buffering=0) as stream:
            event(kind,'created',data,0);half=len(data)//2;write_all(stream.fileno(),data[:half]);event(kind,'half',data,half)
            write_all(stream.fileno(),data[half:]);os.fsync(stream.fileno());event(kind,'file_sync',data,len(data))
        os.link(part,job/name);event(kind,'link',data,len(data));sync_directory(job);event(kind,'dir_sync',data,len(data))
    kinds={'failed-status.bin':'frame','transport.json':'transport','exit.json':'exit'}
    for name,data in records.items():put(kinds[name.removeprefix(role+'-')],name,data)
    data=encode(commit_record(metadata,records));put('commit',role+'-terminal-commit.json',data)
    event('complete','complete',data,len(data))


def recover(job,role):raise ValueError('local terminal recovery or restart is forbidden')
