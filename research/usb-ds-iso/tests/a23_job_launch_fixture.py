"""Fixed stdlib child: fresh fixture receipt over explicitly historical SDK bytes."""
import hashlib,json,os,sys,time
from pathlib import Path
def encode(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(v):return hashlib.sha256(v).hexdigest()
def inventory(c):return {n:dict(bytes=len(v),sha256=sha(v)) for n,v in sorted(c.items())}
def main():
    if len(sys.argv)!=2:return 2
    job=Path(sys.argv[1])
    if not job.is_absolute() or job!=job.resolve() or not job.is_relative_to('/private/tmp'):return 2
    raw=(job/'launch.json').read_bytes();v=json.loads(raw);attempt=(job/'launch-attempt.json').read_bytes()
    if v['fixture_sha256']!=sha(Path(__file__).read_bytes()):return 2
    files={p.relative_to(job/'inputs').as_posix():p.read_bytes() for p in (job/'inputs').rglob('*') if p.is_file()}
    if inventory(files)!=v['seed_files']:return 2
    a=json.loads(attempt)
    if a!=dict(schema='A23-fixture-launch-attempt-1',fixture_job_id=v['fixture_job_id'],launch_nonce=v['launch_nonce'],
        launch_sha256=sha(raw),attempt_number=1,spent_before_spawn=True,model_only=True):return 2
    target=job/'result';target.mkdir(mode=0o700)
    for n,b in files.items():
        p=target/'materials'/n;p.parent.mkdir(parents=True,exist_ok=True)
        with p.open('xb') as stream:stream.write(b)
    r=dict(schema='A23-fixture-bound-report-1',fixture_job_id=v['fixture_job_id'],launch_nonce=v['launch_nonce'],
        launch_sha256=sha(raw),attempt_sha256=sha(attempt),material_files=inventory(files),
        cached_materials_origin='historical_model_cache',model_only=True,production_execution_authorized=False)
    mode=v['fixture_mode']
    if mode=='wrong-nonce':r['launch_nonce']='0'*64
    if mode=='wrong-job':r['fixture_job_id']='00000000-0000-0000-0000-000000000001'
    stdout=encode(r);receipt={**r,'schema':'A23-fixture-bound-receipt-1','stdout_sha256':sha(stdout)}
    if mode!='missing-receipt':
        with (target/'receipt.json').open('xb') as stream:stream.write(b'{' if mode=='partial-receipt' else encode(receipt))
    if mode=='tampered-material':(target/'materials/result.json').write_bytes(b'{}')
    if mode=='stderr-output':os.write(2,b'fixed fixture diagnostic\n')
    os.write(1,stdout)
    if mode=='timeout-after-output':time.sleep(2)
    return 7 if mode=='abnormal-exit' else 0
if __name__=='__main__':raise SystemExit(main())
