"""Fixture-only exclusive local terminal commit protocol and fixed interruption hooks."""
from pathlib import Path
import errno,hashlib,json,os,runpy,sys

def encode(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(v):return hashlib.sha256(v).hexdigest()


class StatusTransportFailure(BaseException):
    def __init__(self,reason,error,committed,attempts):
        self.reason,self.error,self.committed,self.attempts=reason,error,committed,attempts


def write_status(fd,frame,write):
    if type(fd) is not int or fd<0 or type(frame) is not bytes or not 0<len(frame)<=8192:raise ValueError('bounded status frame required')
    position=attempts=0
    while position<len(frame):
        if attempts==16:raise StatusTransportFailure('attempt_limit',errno.EAGAIN,position,attempts)
        attempts+=1
        try:count=write(fd,memoryview(frame)[position:])
        except InterruptedError:continue
        except OSError as exc:raise StatusTransportFailure('epipe' if exc.errno==errno.EPIPE else 'io_error',exc.errno,position,attempts) from None
        if type(count) is not int or not 0<count<=len(frame)-position:raise StatusTransportFailure('invalid_progress',errno.EIO,position,attempts)
        position+=count
    return position


def main():
    if len(sys.argv)<4 or sys.argv[1] not in ('requester','worker'):return 2
    role=sys.argv[1];job=Path(sys.argv[2]);root=job.parent
    if not job.is_absolute() or job!=job.resolve() or not job.is_relative_to('/private/tmp'):return 2
    raw=(job/'failure-plan.json').read_bytes();v=json.loads(raw);owned=json.loads((job/'owned-plan.json').read_bytes());launch=json.loads((job/'launch.json').read_bytes())
    if sha(Path(__file__).read_bytes())!=v['instrumentation_sha256']['a23_guardian_failure_actor.py']:return 2
    name='a23_guardian_owned_parent.py' if role=='requester' else 'a23_parent_crash_worker.py'
    if sha((root/name).read_bytes())!=owned['code_sha256'][name]:return 2
    local_raw=(job/'terminal-plan.json').read_bytes();local=json.loads(local_raw);local_pin=os.environ['A23_TERMINAL_PLAN_PIN'];trace_fd=int(os.environ['A23_TERMINAL_TRACE_FD'])
    if sha(local_raw)!=local_pin or sha(Path(__file__).read_bytes())!=local['actor_source_sha256']:return 2
    if sha((root/'lib/a23_terminal_commit_io.py').read_bytes())!=local['publication_io_sha256']:return 2
    sys.path.insert(0,str(root/'lib'));import a23_terminal_commit_io as publication
    status=int(sys.argv[4] if role=='requester' else sys.argv[5]);original_write=os.write;failed=None;transport=None
    def write(fd,data):
        nonlocal failed,transport
        if fd!=status:return original_write(fd,data)
        frame=bytes(data)
        try:return write_status(fd,frame,original_write)
        except StatusTransportFailure as exc:
            failed=frame;transport=dict(reason=exc.reason,errno=exc.error,bytes_committed=exc.committed,write_attempts=exc.attempts)
            raise
    code=0;exception=None;sys.argv=[str(root/name),str(job),*sys.argv[3:]];os.write=write
    try:runpy.run_path(sys.argv[0],run_name='__main__')
    except StatusTransportFailure:code=91;exception='StatusTransportFailure'
    except SystemExit as exc:code=exc.code if type(exc.code) is int else 0 if exc.code is None else 1
    except BaseException as exc:code=1;exception=type(exc).__name__
    finally:os.write=original_write
    records={}
    def put(name,data):records[name]=data
    if failed is not None:
        frame=json.loads(failed);put(role+'-failed-status.bin',failed)
        put(role+'-transport.json',encode(dict(schema='A23-status-transport-failure-1',role=role,actor_pid=os.getpid(),
            failure_plan_sha256=sha(raw),fixture_job_id=launch['fixture_job_id'],launch_nonce=launch['launch_nonce'],
            failed_frame_sha256=sha(failed),failed_frame_size=len(failed),message_kind=frame['kind'],delivery_confirmed=False,
            creator_wait_observed=False,model_only=True,**transport)))
    put(role+'-exit.json',encode(dict(schema='A23-guardian-failure-actor-exit-1',role=role,actor_pid=os.getpid(),failure_plan_sha256=sha(raw),
        fixture_job_id=launch['fixture_job_id'],launch_nonce=launch['launch_nonce'],reported_exit_code=code,exception_type=exception,model_only=True)))
    metadata=dict(role=role,actor_pid=os.getpid(),fixture_job_id=launch['fixture_job_id'],launch_nonce=launch['launch_nonce'],
        terminal_plan_sha256=local_pin,failure_plan_sha256=sha(raw))
    def event(kind,phase,data,written):
        if role!=local['role']:return
        cut=local['artifact']==kind and local['phase']==phase
        row=dict(schema='A23-terminal-commit-event-1',kind=kind,phase=phase,content_sha256=sha(data),content_size=len(data),
            bytes_written=written,exit_requested=73 if cut else None,model_only=True,**metadata)
        if phase=='before':row['content_hex']=data.hex()
        view=memoryview(encode(row)+b'\n')
        while view:
            count=original_write(trace_fd,view)
            if not count:raise OSError('commit event stalled')
            view=view[count:]
        if cut:os._exit(73)
    publication.publish(job,role,records,metadata,event)
    return code
if __name__=='__main__':raise SystemExit(main())
