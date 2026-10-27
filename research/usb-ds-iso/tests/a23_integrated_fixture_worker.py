"""Fixed child: consume parent attempt, publish only fixture model results."""
from pathlib import Path
import hashlib,json,os,sys,time
def encode(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(v):return hashlib.sha256(v).hexdigest()
def inventory(c):return {n:dict(bytes=len(v),sha256=sha(v)) for n,v in sorted(c.items())}
def main():
    if len(sys.argv)!=2:return 2
    job=Path(sys.argv[1]);lib=Path(__file__).parent/'lib'
    if not job.is_absolute() or job!=job.resolve() or not job.is_relative_to('/private/tmp'):return 2
    raw=(job/'launch.json').read_bytes();v=json.loads(raw);praw=(job/'integrated-plan.json').read_bytes();plan=json.loads(praw)
    if sha(raw)!=plan['launch_sha256'] or sha(Path(__file__).read_bytes())!=v['fixture_sha256']:return 2
    if set(plan['library_sha256'])!={'a23_integrated_fixture_io.py','a23_fixture_publication.py'}:return 2
    if any(sha((lib/n).read_bytes())!=h for n,h in plan['library_sha256'].items()):return 2
    sys.path.insert(0,str(lib));import a23_integrated_fixture_io as io
    if plan['child_cut_after'] not in (None,*io.CHILD_EVENTS) or plan['child_fail_before'] not in (None,*io.CHILD_FAILURES):return 2
    attempt=(job/'launch-attempt.json').read_bytes();use=json.loads((job/'launcher-use.json').read_bytes())
    if attempt!=encode(dict(schema='A23-fixture-launch-attempt-1',fixture_job_id=v['fixture_job_id'],launch_nonce=v['launch_nonce'],
        launch_sha256=sha(raw),attempt_number=1,spent_before_spawn=True,model_only=True)):return 2
    if use!=dict(schema='A23-integrated-fixture-launcher-use-1',launch_sha256=sha(raw),plan_sha256=sha(praw),maximum_calls=1,model_only=True):return 2
    prefix=[dict(event=n,outcome='completed') for n in (*io.PRE_EVENTS,'launch.ready')]
    if [json.loads(line) for line in (job/'trace.jsonl').read_bytes().splitlines()]!=prefix:return 2
    files={p.relative_to(job/'inputs').as_posix():p.read_bytes() for p in (job/'inputs').rglob('*') if p.is_file()}
    if inventory(files)!=v['seed_files']:return 2
    report=dict(schema='A23-fixture-bound-report-1',fixture_job_id=v['fixture_job_id'],launch_nonce=v['launch_nonce'],launch_sha256=sha(raw),
        attempt_sha256=sha(attempt),material_files=inventory(files),cached_materials_origin='historical_model_cache',model_only=True,production_execution_authorized=False)
    stdout=encode(report);receipt=encode({**report,'schema':'A23-fixture-bound-receipt-1','stdout_sha256':sha(stdout)})
    def checkpoint(label,phase):
        if phase=='before' and plan['child_fail_before']==label:
            io.record(job,label,'injected_error');raise OSError('fixed integrated child publication error')
        if phase=='after':
            io.record(job,label,'completed')
            if plan['child_cut_after']==label:os._exit(73)
    try:
        io.publish_result(job,files,receipt,checkpoint)
        checkpoint('stdout.emit','before')
        if plan['worker_mode']=='stderr-output':io.write_all(2,b'fixed integrated diagnostic\n')
        if plan['worker_mode']!='no-stdout':io.write_all(1,stdout)
        checkpoint('stdout.emit','after')
        if plan['worker_mode']=='timeout-after-output':time.sleep(2)
    except OSError:return 74
    return 7 if plan['worker_mode']=='exit-seven' else 0
if __name__=='__main__':raise SystemExit(main())
