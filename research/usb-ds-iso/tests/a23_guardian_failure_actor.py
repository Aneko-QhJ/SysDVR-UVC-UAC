"""Observe frozen actor failure locally without retaining guardian pipe readers."""
from pathlib import Path
import hashlib,json,os,runpy,sys
def encode(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(v):return hashlib.sha256(v).hexdigest()
def main():
    if len(sys.argv)<4 or sys.argv[1] not in ('requester','worker'):return 2
    role=sys.argv[1];job=Path(sys.argv[2]);root=job.parent
    if not job.is_absolute() or job!=job.resolve() or not job.is_relative_to('/private/tmp'):return 2
    raw=(job/'failure-plan.json').read_bytes();v=json.loads(raw);owned=json.loads((job/'owned-plan.json').read_bytes());launch=json.loads((job/'launch.json').read_bytes())
    if sha(Path(__file__).read_bytes())!=v['instrumentation_sha256']['a23_guardian_failure_actor.py']:return 2
    name='a23_guardian_owned_parent.py' if role=='requester' else 'a23_parent_crash_worker.py'
    if sha((root/name).read_bytes())!=owned['code_sha256'][name]:return 2
    code=0;exception=None;sys.argv=[str(root/name),str(job),*sys.argv[3:]]
    try:runpy.run_path(sys.argv[0],run_name='__main__')
    except SystemExit as exc:code=exc.code if type(exc.code) is int else 0 if exc.code is None else 1
    except BaseException as exc:code=1;exception=type(exc).__name__
    result=dict(schema='A23-guardian-failure-actor-exit-1',role=role,actor_pid=os.getpid(),failure_plan_sha256=sha(raw),
        fixture_job_id=launch['fixture_job_id'],launch_nonce=launch['launch_nonce'],reported_exit_code=code,exception_type=exception,model_only=True)
    with (job/(role+'-exit.json')).open('xb',buffering=0) as stream:stream.write(encode(result));os.fsync(stream.fileno())
    return code
if __name__=='__main__':raise SystemExit(main())
