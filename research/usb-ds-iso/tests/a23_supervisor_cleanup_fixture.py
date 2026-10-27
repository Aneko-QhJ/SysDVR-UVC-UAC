"""Fixed offline pipe/exit schedules. Forked holders have a two-second TTL."""
import hashlib,json,os,sys,time
from pathlib import Path
CASES=('normal','leader-both-held','leader-stdout-held','leader-stderr-held','eof-worker-alive','stdout-eof-worker-alive','stderr-eof-worker-alive',
       'read-interrupted','read-error','selector-error','group-kill-error','group-kill-not-found','wait-error','wait-timeout','cleanup-multiple-errors')
def encode(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(v):return hashlib.sha256(v).hexdigest()
def main():
    if len(sys.argv)!=4 or sys.argv[1] not in CASES:return 2
    name=sys.argv[1];seed=Path(sys.argv[2]);target=Path(sys.argv[3])
    if not seed.is_absolute() or not target.is_absolute() or target.exists():return 2
    target.mkdir(mode=0o700);control=target.parent/'control';control.mkdir(mode=0o700)
    files={p.relative_to(seed).as_posix():p.read_bytes() for p in seed.rglob('*') if p.is_file()}
    for n,raw in files.items():
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
    inventory={n:dict(bytes=len(v),sha256=sha(v)) for n,v in sorted(files.items())}
    report=dict(schema='A23-supervised-worker-report-1',case=name,material_case='normal',inventory_sha256=sha(encode(inventory)),
                result_sha256=sha(files['result.json']),driver_complete=json.loads(files['result.json'])['complete'],provenance_authenticated=False)
    os.write(1,encode(report))
    if name.startswith('leader-'):(control/'leader-exiting').write_bytes(b'after holder ready\n');os._exit(0)
    if name in ('eof-worker-alive','wait-error','wait-timeout'):os.close(1);os.close(2)
    if name=='stdout-eof-worker-alive':os.close(1)
    if name=='stderr-eof-worker-alive':os.close(2)
    if name not in ('normal','read-interrupted'):time.sleep(2)
    return 0
if __name__=='__main__':raise SystemExit(main())
