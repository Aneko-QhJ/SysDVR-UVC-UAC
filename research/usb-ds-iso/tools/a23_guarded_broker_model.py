"""Model-only prelaunch source guard and post-exit file collection adapter.

Python object separation is an API constraint, not an OS capability boundary.
The source check is a point-in-time check, not a filesystem lock.
"""
import copy
import a23_broker_model as old
import a23_failure_collector as collector
a=old.a;f=a.f
class GuardedBroker(old.BrokerModel):
    def __init__(self,*args,source_reader,expected_sources,**kwargs):
        super().__init__(*args,**kwargs);self.source_reader=source_reader;self.expected_sources=copy.deepcopy(expected_sources);self.admission_attempted=False
        d=f.load(self.receiver/'descriptor.json');f.require(f.encode(d['source_hashes'])==f.encode(self.expected_sources),'admission sources differ from frozen build');self.initial_receiver=a.build_scope(self.receiver);self.initial_supervisor=old.sv.build_info(self.supervisor_build)
    def start(self):
        f.require(not self.admission_attempted,'guarded launch already attempted');self.admission_attempted=True;a.put(self.root,'ADMISSION_ATTEMPT',b'one source admission attempt\n')
        try:
            f.require(a.build_scope(self.receiver)==self.initial_receiver and old.sv.build_info(self.supervisor_build)==self.initial_supervisor,'build changed before admission')
            observed=self.source_reader();same=f.encode(observed)==f.encode(self.expected_sources)
            receipt=dict(schema='A23-model-source-admission-1',source_sha256=f.sha(f.encode(self.expected_sources)),observed_sha256=f.sha(f.encode(observed)),source_count=len(self.expected_sources),source_match=same,receiver_build=self.initial_receiver[1],supervisor_build=self.initial_supervisor,point_in_time_only=True,production_execution_authorized=False)
            a.put(self.root,'admission.json',f.encode(receipt));f.require(same,'current sources differ before launch');super().start()
        except (ValueError,OSError,KeyError,TypeError):self.stop();raise
    def collect(self,output):
        f.require(not self.final_attempted,'guarded final collection already attempted');m=self.supervision
        if m.process is None or m.process.poll() is None or not m.settled_ns:return False
        if not m.closed:f.require(m.finish(),'supervision not final')
        self.final_attempted=True
        # Only paths and immutable observations cross the API; the collector
        # receives no Popen, stdin, issuer or source-reading callback.
        receipt=collector.ExitedModelFiles(self.root,self.receiver,self.supervisor_build,m.process.pid,self.delivery)
        return collector.collect(receipt,output)
