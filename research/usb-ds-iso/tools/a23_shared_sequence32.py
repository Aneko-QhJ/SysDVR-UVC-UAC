"""Shared32 namespace engine. Dormant formal branch; tests use temporary namespaces."""
from contextlib import contextmanager
from pathlib import Path
import fcntl,os,uuid
import a23_sequence32_model as f
FORMAL_ROOT=Path(__file__).resolve().parents[1]/'private/sequence-reservations32'
SCOPE_HASHES={'baseline_manifest_sha256','baseline_inventory_sha256','workflow_source_sha256','build_manifest_sha256','receiver_sha256','device_binding_sha256','recipe_sha256','history_sha256'}
SCOPE_FLAGS={'formal_issuance_available','acquisition_mode_implemented','hardware_entry_enabled'}
JOB_FILES={'job.json','authorization.json','issue.json','issue-commit','consume-attempt','consumed.json','consume-commit','native-process-attempt','native-context.json','native-process-claim.json','native-selection-attempt','native-sdk-claim.json'}

def scope(v):
    f.require(type(v) is dict and set(v)==SCOPE_HASHES|SCOPE_FLAGS|{'schema','first_sequence','last_sequence'} and v['schema']=='A23-shared32-scope-1','shared scope inventory differs')
    for k in SCOPE_HASHES:f.require(f.hex64(v[k]),'shared scope digest differs')
    for k in SCOPE_FLAGS:f.require(type(v[k]) is bool,'shared scope flag differs')
    f.require(f.integer(v['first_sequence'],81,81) and f.integer(v['last_sequence'],112,112) and v['hardware_entry_enabled'] is False,'shared range/claim differs');return v

def job_id(v):f.require(type(v) is str and str(uuid.UUID(v))==v,'canonical job UUID required');return v

def records(root,job):
    root=Path(root);scope_value=scope(f.load(root/'scope.json'));ns=f.load(root/'namespace.json');historical=f.load(root/'history.json');f.history(historical)
    f.require(type(ns) is dict and set(ns)=={'schema','id','root','scope_sha256','history_sha256','simulation'} and ns['schema']=='A23-shared32-namespace-1' and type(ns['simulation']) is bool and type(ns['root']) is str and Path(ns['root']).is_absolute() and str(uuid.UUID(ns['id']))==ns['id'],'invalid shared namespace')
    f.require(ns['scope_sha256']==f.sha(f.read(root/'scope.json')) and ns['history_sha256']==scope_value['history_sha256']==f.sha(f.read(root/'history.json')),'shared namespace input drift')
    names={p.name for p in root.iterdir()};f.require({'namespace.json','scope.json','history.json','jobs'}<=names and names<={'namespace.json','scope.json','history.json','jobs','.lock','block-00081.json'},'unknown shared namespace artifact')
    for p in root.iterdir():f.require(not p.is_symlink() and (p.is_dir() if p.name=='jobs' else p.is_file()),'invalid shared namespace node')
    folder=root/'jobs'/job_id(job);logical=Path(ns['root'])/'jobs'/job
    j=f.load(folder/'job.json');expected=dict(schema='A23-shared32-job-1',job_id=job,job_path=str(logical),namespace_id=ns['id'],scope_sha256=ns['scope_sha256'])
    f.require(f.encode(j)==f.encode(expected),'job commitment differs')
    a=f.load(folder/'authorization.json');expected_a=dict(schema='A23-shared32-authorization-1',job_id=job,scope_sha256=ns['scope_sha256'],maximum_invocations=1,simulation=ns['simulation'],hardware_test_authorized=not ns['simulation'])
    f.require(f.encode(a)==f.encode(expected_a),'authorization binding differs')
    return ns,scope_value,historical,folder,j,a

def check_burn(root,job):
    ns,s,h,folder,j,a=records(root,job);r=f.load(Path(root)/'block-00081.json')
    expected=dict(schema='A23-shared32-reservation-1',namespace_id=ns['id'],job_id=job,job_path=j['job_path'],first=81,last=112,count=32,
        scope_sha256=ns['scope_sha256'],job_sha256=f.sha(f.read(folder/'job.json')),authorization_sha256=f.sha(f.read(folder/'authorization.json')),simulation=ns['simulation'])
    f.require(f.encode(r)==f.encode(expected) and not f.history(h)&set(range(81,113)),'shared reservation owner/range differs');return r

def check_issue(root,job,*,committed=True):
    ns,s,h,folder,j,a=records(root,job);check_burn(root,job);v=f.load(folder/'issue.json')
    expected=dict(schema='A23-shared32-issue-1',namespace_id=ns['id'],job_id=job,job_path=j['job_path'],scope_sha256=ns['scope_sha256'],reservation_sha256=f.sha(f.read(Path(root)/'block-00081.json')),authorization_sha256=f.sha(f.read(folder/'authorization.json')),remaining=1,simulation=ns['simulation'])
    f.require(f.encode(v)==f.encode(expected),'shared issue differs')
    if committed:f.require(f.read(folder/'issue-commit')==b'issue durable\n','issue not durably committed')
    return v

def check_consumed(root,job,*,committed=True):
    ns,s,h,folder,j,a=records(root,job);check_issue(root,job);v=f.load(folder/'consumed.json')
    expected=dict(schema='A23-shared32-consumed-1',namespace_id=ns['id'],job_id=job,job_path=j['job_path'],scope_sha256=ns['scope_sha256'],reservation_sha256=f.sha(f.read(Path(root)/'block-00081.json')),issue_sha256=f.sha(f.read(folder/'issue.json')),authorization_sha256=f.sha(f.read(folder/'authorization.json')),remaining=0,receiver_launched=False,simulation=ns['simulation'])
    f.require(f.encode(v)==f.encode(expected) and f.read(folder/'consume-attempt')==b'one attempt\n','shared consumption differs')
    if committed:f.require(f.read(folder/'consume-commit')==b'consumption durable\n','consumption not durably committed')
    return v

class SharedSequence32:
    def __init__(self,root,*,simulation,fresh_scope):
        self.root=Path(root);self.simulation=simulation;self.fresh_scope=fresh_scope
        f.require(type(simulation) is bool and callable(fresh_scope),'explicit shared mode/verifier required')
        f.require(self.root.is_absolute() and self.root==self.root.resolve(),'canonical shared root required')
        f.require((simulation and Path('/private/tmp') in self.root.parents) or (not simulation and self.root==FORMAL_ROOT),'shared namespace/mode mismatch')
    def fresh(self):
        v=scope(self.fresh_scope())
        if not self.simulation:f.require(v['formal_issuance_available'] is True and v['acquisition_mode_implemented'] is True,'formal shared issuer is not ready')
        if self.root.exists():f.require(f.encode(v)==f.read(self.root/'scope.json'),'fresh scope changed')
        return v
    def initialize(self,historical):
        s=self.fresh();f.history(historical);f.require(f.sha(f.encode(historical))==s['history_sha256'],'history scope differs')
        f.require(not self.root.exists() and self.root.parent.is_dir(),'new shared namespace required');self.root.mkdir(mode=0o700);f.sync(self.root.parent)
        f.put(self.root/'scope.json',s);f.put(self.root/'history.json',historical);(self.root/'jobs').mkdir(mode=0o700);f.sync(self.root)
        f.put(self.root/'namespace.json',dict(schema='A23-shared32-namespace-1',id=str(uuid.uuid4()),root=str(self.root),scope_sha256=f.sha(f.read(self.root/'scope.json')),history_sha256=s['history_sha256'],simulation=self.simulation))
        return self.root
    def validate(self):
        self.fresh();ns=f.load(self.root/'namespace.json')
        names={p.name for p in self.root.iterdir()};f.require({'namespace.json','scope.json','history.json','jobs'}<=names and names<={'namespace.json','scope.json','history.json','jobs','.lock','block-00081.json'},'unknown shared namespace artifact')
        for p in self.root.iterdir():f.require(not p.is_symlink() and (p.is_dir() if p.name=='jobs' else p.is_file()),'invalid shared namespace node')
        f.require(ns['schema']=='A23-shared32-namespace-1' and ns['scope_sha256']==f.sha(f.read(self.root/'scope.json')) and ns['history_sha256']==f.sha(f.read(self.root/'history.json')),'shared namespace input drift')
        f.require(ns['root']==str(self.root) and ns['simulation'] is self.simulation,'copied/mixed shared namespace')
        for p in (self.root/'jobs').iterdir():
            f.require(not p.is_symlink() and p.is_dir(),'invalid job directory');job_id(p.name);records(self.root,p.name)
            f.require(all(not q.is_symlink() and q.is_file() and q.name in JOB_FILES for q in p.iterdir()),'unknown job artifact')
        return ns
    @contextmanager
    def lock(self):
        self.validate();fd=os.open(self.root/'.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
        try:
            os.fsync(fd);f.sync(self.root);fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);self.validate();yield
        finally:os.close(fd)
    def prepare(self,job,authorization):
        job_id(job)
        with self.lock():
            ns=self.validate();a=dict(schema='A23-shared32-authorization-1',job_id=job,scope_sha256=ns['scope_sha256'],maximum_invocations=1,simulation=self.simulation,hardware_test_authorized=not self.simulation)
            f.require(f.encode(authorization)==f.encode(a),'explicit bound authorization required')
            folder=self.root/'jobs'/job;folder.mkdir(mode=0o700);f.sync(folder.parent)
            f.put(folder/'job.json',dict(schema='A23-shared32-job-1',job_id=job,job_path=str(folder),namespace_id=ns['id'],scope_sha256=ns['scope_sha256']));f.put(folder/'authorization.json',a);records(self.root,job)
            return folder
    def issue(self,job):
        with self.lock():
            ns,s,h,folder,j,a=records(self.root,job);f.require(not f.history(h)&set(range(81,113)),'shared historical overlap')
            f.require(not (self.root/'block-00081.json').exists(),'shared32 already burned; no job may take over')
            r=dict(schema='A23-shared32-reservation-1',namespace_id=ns['id'],job_id=job,job_path=j['job_path'],first=81,last=112,count=32,scope_sha256=ns['scope_sha256'],job_sha256=f.sha(f.read(folder/'job.json')),authorization_sha256=f.sha(f.read(folder/'authorization.json')),simulation=self.simulation)
            f.put(self.root/'block-00081.json',r);self.fresh();check_burn(self.root,job)
            v=dict(schema='A23-shared32-issue-1',namespace_id=ns['id'],job_id=job,job_path=j['job_path'],scope_sha256=ns['scope_sha256'],reservation_sha256=f.sha(f.read(self.root/'block-00081.json')),authorization_sha256=f.sha(f.read(folder/'authorization.json')),remaining=1,simulation=self.simulation)
            f.put(folder/'issue.json',v);self.fresh();check_issue(self.root,job,committed=False);f.exclusive(folder/'issue-commit',b'issue durable\n');return v
    def consume(self,job):
        with self.lock():
            ns,s,h,folder,j,a=records(self.root,job);check_issue(self.root,job);f.exclusive(folder/'consume-attempt',b'one attempt\n')
            v=dict(schema='A23-shared32-consumed-1',namespace_id=ns['id'],job_id=job,job_path=j['job_path'],scope_sha256=ns['scope_sha256'],reservation_sha256=f.sha(f.read(self.root/'block-00081.json')),issue_sha256=f.sha(f.read(folder/'issue.json')),authorization_sha256=f.sha(f.read(folder/'authorization.json')),remaining=0,receiver_launched=False,simulation=self.simulation)
            f.put(folder/'consumed.json',v);self.fresh();check_consumed(self.root,job,committed=False);f.exclusive(folder/'consume-commit',b'consumption durable\n');return v
    def binding(self,job):
        self.validate();check_consumed(self.root,job);ns,s,h,folder,j,a=records(self.root,job)
        return dict(schema='A23-two-epoch-entry-binding-1',build_manifest_sha256=s['build_manifest_sha256'],receiver_sha256=s['receiver_sha256'],authorization_receipt_sha256=f.sha(f.read(folder/'consumed.json')),first_sequence=81,last_sequence=112)
