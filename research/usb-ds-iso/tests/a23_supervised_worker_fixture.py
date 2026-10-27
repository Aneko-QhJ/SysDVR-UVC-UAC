"""Fixed offline process fixture. Only copies supplied model byte materials."""
import hashlib,json,os,signal,sys,time
from pathlib import Path
CASES=('normal','no-stdout','malformed-stdout','partial-stdout','empty-materials','missing-material','abnormal-exit','signal-exit','timeout-before-output','timeout-after-output','oversize-stdout','oversize-stderr','stderr-output','wrong-case','wrong-digest','driver-failure','worker-failure')

def encode(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(v):return hashlib.sha256(v).hexdigest()

def main():
    if len(sys.argv)!=4 or sys.argv[1] not in CASES:return 2
    name=sys.argv[1];seed=Path(sys.argv[2]);target=Path(sys.argv[3])
    if not seed.is_absolute() or not target.is_absolute() or target.exists():return 2
    target.mkdir(mode=0o700)
    if name=='timeout-before-output':time.sleep(60);return 3
    files={p.relative_to(seed).as_posix():p.read_bytes() for p in seed.rglob('*') if p.is_file()}
    for path,raw in files.items():
        if name=='empty-materials' or name=='missing-material' and path=='version-profile.json':continue
        p=target/path;p.parent.mkdir(parents=True,exist_ok=True)
        with p.open('xb') as stream:stream.write(raw)
    source='capture-worker-unfinished-return' if name=='driver-failure' else 'capture-worker-error' if name=='worker-failure' else 'normal'
    inventory={n:dict(bytes=len(v),sha256=sha(v)) for n,v in sorted(files.items())}
    report=dict(schema='A23-supervised-worker-report-1',case=name,material_case=source,inventory_sha256=sha(encode(inventory)),result_sha256=sha(files['result.json']),driver_complete=json.loads(files['result.json'])['complete'],provenance_authenticated=False)
    if name=='wrong-case':report['case']='normal'
    if name=='wrong-digest':report['inventory_sha256']='0'*64
    raw=encode(report)
    if name=='malformed-stdout':raw=b'{'
    if name=='partial-stdout':raw=raw[:-1]
    if name=='no-stdout':raw=b''
    if name=='oversize-stdout':raw=b'x'*65537
    if name=='oversize-stderr':raw=b'';os.write(2,b'x'*8193)
    if name=='stderr-output':os.write(2,b'injected diagnostic\n')
    if raw:os.write(1,raw)
    if name in ('timeout-after-output','oversize-stdout','oversize-stderr'):time.sleep(60)
    if name=='abnormal-exit':return 7
    if name=='signal-exit':os.kill(os.getpid(),signal.SIGTERM)
    return 0

if __name__=='__main__':raise SystemExit(main())
