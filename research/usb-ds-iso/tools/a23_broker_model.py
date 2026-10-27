"""One model child: observed hello -> guarded model consumption -> final files."""
from pathlib import Path
import copy,os,shutil,uuid
import a23_broker_supervision as sv
import a23_broker_archive as ar
import a23_shared_sequence32 as sequence
import collect_a23_two_epoch_final as collector
a=ar.a;f=a.f

class BrokerModel:
    def __init__(self,root,receiver,supervisor,roots,history,case,inject_policy):
        self.root=a.canonical(root);f.require(self.root.is_relative_to('/private/tmp') and not self.root.exists(),'new temporary broker model required');self.receiver=a.canonical(receiver);self.supervisor_build=a.canonical(supervisor);self.scope,_=a.build_scope(self.receiver);f.require(self.scope['receiver_sha256']==sv.v.build_info(self.supervisor_build)['binary_sha256'],'model binary roles differ');self.history=copy.deepcopy(history);self.case=case;self.root.mkdir(mode=0o700);self.execution=self.root/'execution';self.execution.mkdir();(self.execution/'host').mkdir();self.started=False;self.decided=False;self.final_attempted=False;self.delivery='none';self.issue_error=None;self.store=None;self.job=str(uuid.uuid4());self.control=None
        self.plan=dict(schema='A23-broker-model-plan-1',case=case,inject_policy=inject_policy,receiver_build=str(self.receiver),roots={k:str(v) for k,v in roots.items()},job_id=self.job);f.require(type(inject_policy) is bool,'explicit model injection flag required')
        for n,v in (('plan.json',self.plan),('scope.json',self.scope),('expected-scope.json',self.scope)):a.put(self.root,n,f.encode(v))
        a.put(self.execution,'case-info.json',f.encode(dict(job_id=self.job)));a.put(self.execution,'config.json',f.encode(dict(binding={})))
        budget=200000000 if case=='timeout-before-hello' else 1200000000 if case=='timeout-after-command' else 30000000000
        self.supervision=sv.ModelSupervisor(self.root/'supervision',self.supervisor_build,'normal',budget_ns=budget)
    def start(self):
        f.require(not self.started,'broker model launch already attempted');self.started=True;self.supervision.start()
    def stop(self):
        if not (self.root/'STOP').exists():a.put(self.root,'STOP',b'model admission stopped; retain ownership\n')
    def step(self):
        m=self.supervision;done=m.poll(0.01)
        if m.failed:self.stop()
        if m.hello and not m.failed and not self.decided:
            self.decided=True;hello=f.parse(bytes(m.buffers['stdout']).split(b'\n',1)[0]);action='deny_model';binding={};job_path=None
            if m.policy or self.plan['inject_policy']:
                try:
                    self.store=sequence.SharedSequence32(self.execution/'namespace',simulation=True,fresh_scope=lambda:f.load(self.root/'scope.json'));self.store.initialize(self.history);ns=f.load(self.store.root/'namespace.json');self.store.prepare(self.job,dict(schema='A23-shared32-authorization-1',job_id=self.job,scope_sha256=ns['scope_sha256'],maximum_invocations=1,simulation=True,hardware_test_authorized=False))
                    if self.case=='scope-before-consume':bad=copy.deepcopy(self.scope);bad['workflow_source_sha256']='0'*64;(self.root/'scope.json').write_bytes(f.encode(bad))
                    self.store.issue(self.job);self.store.consume(self.job);binding=self.store.binding(self.job);job_path=str(self.store.root/'jobs'/self.job);action='execute_model'
                    if self.case=='consumed-tamper':(Path(job_path)/'consumed.json').write_bytes(b'{')
                except (ValueError,OSError) as e:self.issue_error=str(e);self.stop()
            # Recheck ownership/deadlines after filesystem work, before sending
            # any command. A spent model receipt is retained on late failure.
            m.poll(0)
            if m.failed:self.stop();return done
            temporary=self.execution/'config.bound.tmp';f.exclusive(temporary,f.encode(dict(binding=binding)));os.replace(temporary,self.execution/'config.json');f.sync(self.execution)
            self.control=dict(schema='A23-broker-model-command-1',action=action,nonce=m.handoff['nonce'],actual_context=hello['context'],job_path=job_path)
            if self.case=='command-context':self.control['actual_context']=dict(hello['context'],pid=123)
            raw=f.encode(self.control);f.require(len(raw)<=4096,'bounded model command required');a.put(self.root,'control.json',raw);os.set_blocking(m.process.stdin.fileno(),False)
            sent=raw[:len(raw)//2] if self.case=='partial-control' else raw
            try:n=os.write(m.process.stdin.fileno(),sent)
            except (OSError,BlockingIOError):n=0;self.stop()
            self.delivery='whole_written' if n==len(raw) else 'partial_or_failed'
            if self.case=='partial-control':m.process.stdin.close()
        return done
    def collect(self,output):
        f.require(not self.final_attempted,'broker final collection already attempted');m=self.supervision
        if m.process is None or m.process.poll() is None or not m.settled_ns:return False
        if not m.closed:f.require(m.finish(),'model supervision not final')
        self.final_attempted=True;output=a.canonical(output);f.require(not output.exists() and not output.is_relative_to(self.root) and not self.root.is_relative_to(output),'new nonoverlapping model envelope required');output.mkdir(mode=0o700);a.put(output,'FINAL_ATTEMPT',b'one model envelope attempt\n');shutil.copytree(m.root,output/'supervision')
        report=a.read(self.execution/'report.json');collector.freeze(self.execution,self.receiver,output/'final',static_model=True,report=report,stdout=bytes(m.buffers['stdout']),stderr=bytes(m.buffers['stderr']))
        for n in ('plan.json','scope.json','expected-scope.json','control.json','STOP'):
            if (self.root/n).exists():a.put(output,n,a.read(self.root/n))
        _,ref=a.build_scope(self.receiver);meta=dict(schema='A23-broker-model-envelope-1',receiver_build=ref,supervisor_build=sv.v.build_info(self.supervisor_build),producer_exited=True,child_pid=m.process.pid,control_delivery=self.delivery,complete_injected_model_chain=False,**ar.FALSE)
        # Private draft has no COMMITTED marker. Publish the derived verdict
        # once, then seal once; committed evidence is never rewritten.
        a.put(output,'envelope.json',f.encode(meta));files,dirs=a.snapshot(output);result=ar.evaluate(output,self.receiver,self.supervisor_build,files,dirs,check_saved=False);meta['complete_injected_model_chain']=result['complete_injected_model_chain']
        temporary=output/'envelope.final.tmp';f.exclusive(temporary,f.encode(meta));os.replace(temporary,output/'envelope.json');f.sync(output);a.seal(output);return ar.analyze(output,self.receiver,self.supervisor_build)
