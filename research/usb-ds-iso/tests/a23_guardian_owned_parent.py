"""Fixed requester: accepts a bound handoff once, never creates/waits a worker."""
from pathlib import Path
import hashlib,json,os,select,sys
def encode(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(v):return hashlib.sha256(v).hexdigest()
def main():
    if len(sys.argv)!=5:return 2
    job=Path(sys.argv[1]);command,status,life=map(int,sys.argv[2:]);root=job.parent
    if not job.is_absolute() or job!=job.resolve() or not job.is_relative_to('/private/tmp'):return 2
    praw=(job/'owned-plan.json').read_bytes();plan=json.loads(praw);launch=json.loads((job/'launch.json').read_bytes())
    for n,h in plan['code_sha256'].items():
        if sha((root/n).read_bytes())!=h:return 2
    def send(kind,**extra):
        raw=encode(dict(schema='A23-guardian-requester-message-1',kind=kind,requester_pid=os.getpid(),guardian_pid=os.getppid(),
            fixture_job_id=launch['fixture_job_id'],launch_nonce=launch['launch_nonce'],owned_plan_sha256=sha(praw),model_only=True,**extra))+b'\n'
        view=memoryview(raw)
        while view:count=os.write(status,view);view=view[count:]
    buffer=bytearray()
    def receive():
        while b'\n' not in buffer:
            ready,_,_=select.select([command],[],[],2)
            if not ready:raise ValueError('requester control timeout')
            raw=os.read(command,4096)
            if not raw:raise ValueError('guardian control closed')
            buffer.extend(raw)
            if len(buffer)>8192:raise ValueError('requester control limit')
        raw,_,tail=buffer.partition(b'\n');buffer[:]=tail;return json.loads(raw)
    if plan['scenario']=='before-request':os._exit(79)
    send('request')
    if plan['scenario']=='after-request':os._exit(79)
    try:
        handoff=receive();expected=dict(schema='A23-guardian-owned-handoff-1',fixture_job_id=launch['fixture_job_id'],launch_nonce=launch['launch_nonce'],
            owned_plan_sha256=sha(praw),launch_sha256=sha((job/'launch.json').read_bytes()),integrated_plan_sha256=plan['integrated_plan_sha256'],
            requester_pid=os.getpid(),guardian_pid=os.getppid(),worker_pid=handoff.get('worker_pid'),maximum_accepts=1,model_only=True,production_execution_authorized=False)
        if type(handoff.get('worker_pid')) is not int or handoff['worker_pid']<=0 or encode(handoff)!=encode(expected):
            send('rejected',reason='handoff_binding');return 82
        raw=encode(handoff)
        with (job/'parent-accept.json').open('xb',buffering=0) as stream:stream.write(raw);os.fsync(stream.fileno())
        send('accepted',handoff_sha256=sha(raw))
        if plan['scenario']=='after-handoff':os._exit(79)
        result=receive()
        if result.get('schema')=='A23-guardian-owned-handoff-1':send('rejected',reason='handoff_repeat');return 82
        expected=dict(schema='A23-guardian-owned-result-1',handoff_sha256=sha(raw),worker_pid=handoff['worker_pid'],
            returncode=result.get('returncode'),worker_waited=True,model_only=True,production_execution_authorized=False)
        if type(result.get('returncode')) is not int or encode(result)!=encode(expected):send('rejected',reason='result_binding');return 82
        with (job/'parent-result.json').open('xb',buffering=0) as stream:stream.write(encode(result));os.fsync(stream.fileno())
        send('reported',result_sha256=sha(encode(result)))
        if plan['scenario']=='after-parent-report':os._exit(79)
        os.close(life);return 0
    except (ValueError,KeyError,TypeError):send('rejected',reason='control_failure');return 83
if __name__=='__main__':raise SystemExit(main())
