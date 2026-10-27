"""Bounded pipe-gated wrapper; parent-death aborts without journal PID signals."""
from pathlib import Path
import hashlib,json,os,runpy,select,sys
def encode(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(v):return hashlib.sha256(v).hexdigest()
class StopFixture(BaseException):
    def __init__(self,code,reason):self.code=code;self.reason=reason
def main():
    if len(sys.argv)!=6:return 2
    job=Path(sys.argv[1]);life,gate,status,parent=map(int,sys.argv[2:]);root=job.parent
    praw=(job/'crash-plan.json').read_bytes();plan=json.loads(praw);launch=json.loads((job/'launch.json').read_bytes())
    if not job.is_absolute() or job!=job.resolve() or not job.is_relative_to('/private/tmp'):return 2
    for n,h in plan['code_sha256'].items():
        if sha((root/n).read_bytes())!=h:return 2
    def send(kind,**extra):
        raw=encode(dict(schema='A23-parent-crash-worker-message-1',kind=kind,worker_pid=os.getpid(),parent_pid=parent,
            fixture_job_id=launch['fixture_job_id'],launch_nonce=launch['launch_nonce'],crash_plan_sha256=sha(praw),model_only=True,**extra))+b'\n'
        view=memoryview(raw)
        while view:count=os.write(status,view);view=view[count:]
    def resume():
        ready,_,_=select.select([gate],[],[],2)
        if not ready:raise StopFixture(88,'guardian_timeout')
        if os.read(gate,1)!=b'R':raise StopFixture(87,'guardian_closed')
        ready,_,_=select.select([life],[],[],0)
        if ready:
            if os.read(life,1)==b'':raise StopFixture(86,'parent_pipe_eof')
            raise StopFixture(89,'unexpected_lifeline_data')
    send('ready');reason='inner_exit';code=0
    try:
        resume();sys.path.insert(0,str(root/'lib'));import a23_integrated_fixture_io as io
        original=io.record
        def record(target,label,outcome):
            original(target,label,outcome)
            if plan['scenario']=='child-'+label and outcome=='completed':send('checkpoint',event=label);resume()
        io.record=record;sys.argv=[str(root/'a23_integrated_fixture_worker.py'),str(job)]
        try:runpy.run_path(sys.argv[0],run_name='__main__')
        except SystemExit as exc:code=exc.code if type(exc.code) is int else 2
    except StopFixture as exc:code,reason=exc.code,exc.reason
    send('end',exit_code=code,reason=reason)
    return code
if __name__=='__main__':raise SystemExit(main())
