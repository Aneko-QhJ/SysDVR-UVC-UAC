"""Bounded context-only model child supervision; no signal, acquisition or retry."""
from pathlib import Path
import os,selectors,subprocess,sys,time,uuid
import a23_supervisor_archive as v
a=v.a;f=v.f
ACTIVE={}
def identity():return {k:getattr(os,'get'+k)() for k in ('pid','ppid','uid','euid','gid','egid')}

class ModelSupervisor:
    def __init__(self,root,build,mode='normal',budget_ns=3000000000):
        self.root=a.canonical(root);self.build=a.canonical(build);f.require(self.root.is_relative_to('/private/tmp') and not self.root.exists(),'new temporary model root required');f.require(mode in v.MODES and type(budget_ns) is int and 10000000<=budget_ns<=5000000000,'bounded model mode/deadline required');self.reference=v.build_info(self.build);self.binary=self.build/'model-child';self.mode=mode;self.budget=budget_ns;self.process=None;self.started=False;self.failed=[];self.timed_out=False;self.truncated=False;self.hello=False;self.policy=False;self.closed=False;self.selector=selectors.DefaultSelector();self.buffers={'stdout':bytearray(),'stderr':bytearray()};self.eof={'stdout':False,'stderr':False};self.line_checked=False;self.hello_ns=0;self.settled_ns=0
        self.root.mkdir(mode=0o700);f.sync(self.root.parent);(self.root/'scratch').mkdir();self.environment={'LANG':'C','LC_ALL':'C','PATH':'/usr/bin:/bin:/usr/sbin:/sbin','TMPDIR':str(self.root/'scratch')};self.handoff=dict(schema='A23-supervisor-handoff-1',nonce=uuid.uuid4().hex+uuid.uuid4().hex,parent=identity(),build=self.reference,environment_sha256=f.sha(f.encode(self.environment)),model_only=True,inherited_environment=False)
        a.put(self.root,'OWNER',(self.handoff['nonce']+'\n').encode());a.put(self.root,'handoff.json',f.encode(self.handoff))
    def fail(self,reason):
        if reason not in self.failed:self.failed.append(reason)
    def guard(self):
        try:ok=a.read(self.root/'OWNER')==(self.handoff['nonce']+'\n').encode() and a.read(self.root/'handoff.json')==f.encode(self.handoff) and identity()==self.handoff['parent']
        except (ValueError,OSError):ok=False
        if not ok:self.fail('owner_handoff_or_parent_changed')
        return ok
    def start(self):
        f.require(not self.started,'model launch already attempted');self.started=True;a.put(self.root,'launch-attempt',b'one model launch attempt\n');f.require(self.guard(),'handoff invalid before launch');f.require(v.build_info(self.build)==self.reference,'model build changed before launch');self.begin_ns=time.monotonic_ns();self.deadline=self.begin_ns+self.budget
        # Fresh environment; no ambient PATH/Python/DYLD settings are inherited.
        self.process=subprocess.Popen([str(self.binary),'--model',self.mode,str(self.root/'handoff.json')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=self.environment,close_fds=True)
        ACTIVE[self.handoff['nonce']]=self
        for name in ('stdout','stderr'):
            stream=getattr(self.process,name);os.set_blocking(stream.fileno(),False);self.selector.register(stream,selectors.EVENT_READ,name)
    def poll(self,wait_seconds=0.01):
        f.require(self.started and self.process is not None and not self.closed and type(wait_seconds) in (int,float) and 0<=wait_seconds<=0.05,'bounded active poll required');self.guard()
        if self.settled_ns:return True
        now=time.monotonic_ns()
        if now>=self.deadline:self.timed_out=True;self.fail('deadline_expired')
        delay=min(wait_seconds,max(0,(self.deadline-now)/1e9))
        for key,_ in self.selector.select(delay):
            name=key.data;limit=4096 if name=='stdout' else 256;room=limit-len(self.buffers[name]);raw=os.read(key.fileobj.fileno(),min(1024,room+1))
            if not raw:self.eof[name]=True;self.selector.unregister(key.fileobj);continue
            self.buffers[name].extend(raw[:room])
            if len(raw)>room:self.truncated=True;self.fail(name+'_limit');self.selector.unregister(key.fileobj)
        out=bytes(self.buffers['stdout'])
        if b'\n' in out:
            first,rest=out.split(b'\n',1)
            if not self.line_checked:
                self.line_checked=True;self.hello_ns=time.monotonic_ns()
                if not self.failed:
                    try:self.policy=v.link(f.parse(first),self.handoff,self.process.pid,str(self.binary));self.hello=True
                    except (ValueError,KeyError,TypeError):self.fail('invalid_hello')
            if rest:self.fail('extra_stdout')
        code=self.process.poll()
        if code is not None and all(self.eof.values()) and not self.line_checked:self.fail('missing_or_partial_hello')
        if code is not None and code!=0:self.fail('child_exit_nonzero')
        self.guard();done=code is not None and (all(self.eof.values()) or self.truncated)
        if done:self.settled_ns=time.monotonic_ns()
        if self.settled_ns>=self.deadline:self.timed_out=True;self.fail('deadline_expired')
        return done
    def result(self):
        code=self.process.poll() if self.process is not None else None
        return dict(schema='A23-supervisor-result-1',launch_begin_ns=self.begin_ns,deadline_ns=self.deadline,hello_observed_ns=self.hello_ns,settled_ns=self.settled_ns,child_pid=self.process.pid if self.process else None,binary_path=str(self.binary),producer_exited=code is not None,returncode=code,timed_out=self.timed_out,truncated=self.truncated,hello_consistent=self.hello,child_execution_policy_pass=self.policy,supervision_complete=bool(code==0 and self.hello and not self.failed and all(self.eof.values())),stdout_eof=self.eof['stdout'],stderr_eof=self.eof['stderr'],failure_reasons=list(self.failed),**v.FALSE)
    def finish(self):
        f.require(not self.closed,'supervisor finalization already attempted')
        if self.process is None or self.process.poll() is None:return False
        if not self.settled_ns:return False
        self.guard()
        if v.build_info(self.build)!=self.reference:self.fail('model_build_changed')
        a.put(self.root,'handoff-original.json',f.encode(self.handoff));a.put(self.root,'OWNER-original',(self.handoff['nonce']+'\n').encode())
        for name in ('stdout','stderr'):a.put(self.root,name+'.bin',bytes(self.buffers[name]))
        a.put(self.root,'result.json',f.encode(self.result()));self.selector.close()
        for stream in (self.process.stdin,self.process.stdout,self.process.stderr):stream.close()
        self.closed=True;ACTIVE.pop(self.handoff['nonce'],None);a.seal(self.root);return True
