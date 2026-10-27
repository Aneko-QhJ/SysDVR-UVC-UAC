"""Fixed guardian instrumentation with a separate, write-only publication event FD."""
from pathlib import Path
import hashlib,json,os,select,sys
def encode(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(v):return hashlib.sha256(v).hexdigest()
def main():
    if len(sys.argv)!=7:return 2
    job=Path(sys.argv[1]);pin=sys.argv[2];command,status,trace_fd=map(int,sys.argv[3:6]);local_pin=sys.argv[6];root=job.parent
    if sha((job/'terminal-plan.json').read_bytes())!=local_pin:return 2
    raw=(job/'failure-plan.json').read_bytes();v=json.loads(raw)
    if sha(raw)!=pin:return 2
    for name,digest in v['instrumentation_sha256'].items():
        if sha((root/name).read_bytes())!=digest:return 2
    sys.path.insert(0,str(root/'source/research/usb-ds-iso/tools'))
    import audit_a23_guardian_owned as frozen
    original_popen=frozen.subprocess.Popen;original_write=os.write;original_fsync=os.fsync;records=[];handles=[];cut=v['scenario']
    def pause(event):
        snapshot=dict(schema='A23-guardian-failure-checkpoint-1',event=event,guardian_pid=os.getpid(),failure_plan_sha256=pin,
            actors=[dict(r) for r in records],model_only=True)
        data=encode(snapshot)+b'\n';view=memoryview(data)
        while view:count=original_write(status,view);view=view[count:]
        ready,_,_=select.select([command],[],[],3)
        if not ready or os.read(command,1)!=b'R':os._exit(90)
    class Handle:
        def __init__(self,process,record):self.process=process;self.record=record
        def __getattr__(self,name):return getattr(self.process,name)
        def kill(self):
            if cut.startswith('child-') and self.record['role']=='requester':pause(cut)
            return self.process.kill()
        def communicate(self,*args,**kwargs):
            result=self.process.communicate(*args,**kwargs);self.record.update(waited=True,returncode=self.process.returncode)
            label='after-worker-wait' if self.record['role']=='worker' else 'after-requester-wait'
            if cut==label:pause(label)
            return result
    def popen(args,**kwargs):
        name=Path(args[3]).name;role='requester' if name=='a23_guardian_owned_parent.py' else 'worker' if name=='a23_parent_crash_worker.py' else None
        if role is None:raise ValueError('fixed guardian actor differs')
        if cut=='before-requester' and role=='requester':pause(cut)
        kwargs['pass_fds']=(*kwargs['pass_fds'],trace_fd);kwargs['env']={**kwargs['env'],'A23_TERMINAL_TRACE_FD':str(trace_fd),'A23_TERMINAL_PLAN_PIN':local_pin}
        process=original_popen([sys.executable,'-I','-B',str(root/'a23_guardian_failure_actor.py'),role,*args[4:]],**kwargs)
        record=dict(role=role,pid=process.pid,waited=False,returncode=None);records.append(record);handle=Handle(process,record);handles.append(handle)
        pause('watch-'+role)
        label='after-requester' if role=='requester' else 'after-worker-unrecorded'
        if cut==label:pause(label)
        return handle
    def owner_fd(fd):
        try:
            a=os.fstat(fd);b=(job/'guardian-owner.json').stat();return (a.st_dev,a.st_ino)==(b.st_dev,b.st_ino)
        except (OSError,ValueError):return False
    original_all=frozen.io.write_all
    def write_all(fd,data):
        if cut=='owner-partial' and owner_fd(fd):original_all(fd,data[:len(data)//2]);pause(cut)
        return original_all(fd,data)
    def fsync(fd):
        result=original_fsync(fd)
        if cut=='owner-synced' and owner_fd(fd):pause(cut)
        return result
    def write(fd,data):
        if cut=='before-worker-release' and data==b'R':pause(cut)
        return original_write(fd,data)
    frozen.subprocess.Popen=popen;frozen.io.write_all=write_all;os.fsync=fsync;os.write=write
    observation,pm,wm=frozen.run_case(root,job)
    for name,value in (('inner-observation.json',observation),('inner-requester-messages.json',pm),('inner-worker-messages.json',wm)):
        with (job/name).open('xb') as stream:stream.write(encode(value))
    pause('finished')
    return 0
if __name__=='__main__':raise SystemExit(main())
