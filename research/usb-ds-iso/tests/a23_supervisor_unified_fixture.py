"""Unified fixed offline fixture; no driver, SDK or arbitrary command launch."""
import hashlib,json,os,signal,sys,time
from pathlib import Path
COLLECTION=('normal','no-stdout','malformed-stdout','partial-stdout','empty-materials','missing-material','abnormal-exit','signal-exit','timeout-before-output','timeout-after-output','oversize-stdout','oversize-stderr','stderr-output','wrong-case','wrong-digest','driver-failure','worker-failure')
CLEANUP=('leader-both-held','leader-stdout-held','leader-stderr-held','eof-worker-alive','stdout-eof-worker-alive','stderr-eof-worker-alive','read-interrupted','read-error','selector-error','group-kill-error','group-kill-not-found','wait-error','wait-timeout','cleanup-multiple-errors')
CLOSE=('stdout-close-error','stderr-close-error','both-close-error','selector-close-error','close-and-wait-error')
def encode(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(v):return hashlib.sha256(v).hexdigest()
def main():
    if len(sys.argv)!=4 or sys.argv[1] not in COLLECTION+CLEANUP+CLOSE:return 2
    name=sys.argv[1];seed=Path(sys.argv[2]);target=Path(sys.argv[3])
    if not seed.is_absolute() or not target.is_absolute() or target.exists():return 2
    target.mkdir(mode=0o700);control=target.parent/'control';control.mkdir(mode=0o700)
    if name=='timeout-before-output':time.sleep(2);return 3
    files={p.relative_to(seed).as_posix():p.read_bytes() for p in seed.rglob('*') if p.is_file()}
    for n,raw in files.items():
        if name=='empty-materials' or name=='missing-material' and n=='version-profile.json':continue
        p=target/n;p.parent.mkdir(parents=True,exist_ok=True)
        with p.open('xb') as stream:stream.write(raw)
    if name.startswith('leader-'):
        ready_r,ready_w=os.pipe();holder=os.fork()
        if holder==0:
            os.close(ready_r)
            if name=='leader-stdout-held':os.close(2)
            if name=='leader-stderr-held':os.close(1)
            os.write(ready_w,b'R');os.close(ready_w);time.sleep(2);os._exit(0)
        os.close(ready_w);assert os.read(ready_r,1)==b'R';os.close(ready_r)
        (control/'holder.json').write_bytes(encode(dict(holder_pid=holder,group=os.getpgrp(),ttl_seconds=2)))
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
    if name.startswith('leader-'):(control/'leader-exiting').write_bytes(b'after holder ready\n');os._exit(0)
    if name in ('eof-worker-alive','wait-error','wait-timeout','close-and-wait-error'):os.close(1);os.close(2)
    if name=='stdout-eof-worker-alive':os.close(1)
    if name=='stderr-eof-worker-alive':os.close(2)
    if name in CLEANUP and name!='read-interrupted' or name in ('timeout-after-output','oversize-stdout','oversize-stderr','close-and-wait-error'):time.sleep(2)
    if name=='abnormal-exit':return 7
    if name=='signal-exit':os.kill(os.getpid(),signal.SIGTERM)
    return 0
if __name__=='__main__':raise SystemExit(main())
