"""Fixed fault-injection parent around the frozen offline launcher Popen."""
from pathlib import Path
import hashlib,json,os,sys
def encode(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(v):return hashlib.sha256(v).hexdigest()
def save(path,raw):
    with path.open('xb',buffering=0) as stream:stream.write(raw);os.fsync(stream.fileno())
def main():
    if len(sys.argv)!=4:return 2
    job=Path(sys.argv[1]);gate=int(sys.argv[2]);status=int(sys.argv[3]);root=job.parent
    if not job.is_absolute() or job!=job.resolve() or not job.is_relative_to('/private/tmp'):return 2
    praw=(job/'crash-plan.json').read_bytes();plan=json.loads(praw)
    for n,h in plan['code_sha256'].items():
        if sha((root/n).read_bytes())!=h:return 2
    sys.path.insert(0,str(root/'source/research/usb-ds-iso/tools'))
    import a23_integrated_fixture_launcher as launcher
    original=launcher.subprocess.Popen;lifelines=[];inner=root/'a23_integrated_fixture_worker.py'
    def popen(args,**kwargs):
        if args!=[sys.executable,'-I','-B',str(inner),str(job)]:raise ValueError('fixed parent command differs')
        if plan['scenario']=='before-popen':os._exit(79)
        life_r,life_w=os.pipe();lifelines.append(life_w)
        child=original([sys.executable,'-I','-B',str(root/'a23_parent_crash_worker.py'),str(job),str(life_r),str(gate),str(status),str(os.getpid())],
            pass_fds=(life_r,gate,status),**kwargs)
        if plan['scenario']=='after-popen-unrecorded':os._exit(79)
        os.close(life_r);os.close(gate);os.close(status)
        owner=dict(schema='A23-parent-crash-owner-1',parent_pid=os.getpid(),worker_pid=child.pid,
            crash_plan_sha256=sha(praw),launch_sha256=plan['launch_sha256'],model_only=True)
        raw=encode(owner)
        if plan['scenario']=='owner-partial':
            with (job/'owner.json').open('xb',buffering=0) as stream:stream.write(raw[:len(raw)//2])
            os._exit(79)
        save(job/'owner.json',raw)
        if plan['scenario']=='owner-synced':os._exit(79)
        return child
    launcher.subprocess.Popen=popen
    observed,out,err,owned=launcher.run(inner,job,plan['integrated_plan_sha256'],sha(inner.read_bytes()))
    harness=launcher.harness_finish(owned,observed)
    for n,raw in (('parent-observation.json',encode(observed)),('parent-harness.json',encode(harness)),('parent-stdout.bin',out),('parent-stderr.bin',err)):
        save(job/n,raw)
    if plan['scenario']=='after-parent-report':os._exit(79)
    for fd in lifelines:os.close(fd)
    return 0
if __name__=='__main__':raise SystemExit(main())
