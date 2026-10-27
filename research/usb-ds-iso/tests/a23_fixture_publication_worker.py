"""Fixed publication crash fixture; only writes its disposable temporary job."""
from pathlib import Path
import hashlib,json,os,sys
def encode(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(v):return hashlib.sha256(v).hexdigest()
def inventory(c):return {n:dict(bytes=len(v),sha256=sha(v)) for n,v in sorted(c.items())}
def main():
    if len(sys.argv)!=2:return 2
    job=Path(sys.argv[1]);module=Path(__file__).parent/'lib/a23_fixture_publication.py'
    if not job.is_absolute() or job!=job.resolve() or not job.is_relative_to('/private/tmp'):return 2
    raw=(job/'launch.json').read_bytes();launch=json.loads(raw);praw=(job/'publication-plan.json').read_bytes();plan=json.loads(praw)
    if sha(raw)!=plan['launch_sha256'] or sha(Path(__file__).read_bytes())!=launch['fixture_sha256'] or sha(module.read_bytes())!=plan['publication_module_sha256']:return 2
    sys.path.insert(0,str(module.parent));import a23_fixture_publication as pub
    if plan['cut_after'] not in (None,*pub.EVENTS) or plan['fail_before'] not in (None,*pub.FAILURES):return 2
    files={p.relative_to(job/'inputs').as_posix():p.read_bytes() for p in (job/'inputs').rglob('*') if p.is_file()}
    if inventory(files)!=launch['seed_files']:return 2
    attempt=encode(dict(schema='A23-fixture-launch-attempt-1',fixture_job_id=launch['fixture_job_id'],launch_nonce=launch['launch_nonce'],
        launch_sha256=sha(raw),attempt_number=1,spent_before_spawn=True,model_only=True))
    report=dict(schema='A23-fixture-bound-report-1',fixture_job_id=launch['fixture_job_id'],launch_nonce=launch['launch_nonce'],
        launch_sha256=sha(raw),attempt_sha256=sha(attempt),material_files=inventory(files),
        cached_materials_origin='historical_model_cache',model_only=True,production_execution_authorized=False)
    stdout=encode(report);receipt=encode({**report,'schema':'A23-fixture-bound-receipt-1','stdout_sha256':sha(stdout)})
    def record(event,outcome):
        fd=os.open(job/'trace.jsonl',os.O_CREAT|os.O_APPEND|os.O_WRONLY,0o600)
        try:pub.write_all(fd,encode(dict(event=event,outcome=outcome))+b'\n')
        finally:os.close(fd)
    def checkpoint(label,phase):
        if phase=='before' and plan['fail_before']==label:
            record(label,'injected_error');raise OSError('fixed injected publication failure')
        if phase=='after':
            record(label,'completed')
            if plan['cut_after']==label:os._exit(73)
    try:
        pub.publish(job,attempt,files,receipt,checkpoint)
        checkpoint('stdout.emit','before');pub.write_all(1,stdout);checkpoint('stdout.emit','after')
    except OSError:return 74
    return 0
if __name__=='__main__':raise SystemExit(main())
