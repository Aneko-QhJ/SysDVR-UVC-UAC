"""Compile file-only native permits and test cross-job shared32 ownership."""
import argparse,copy,json,shutil,subprocess,sys,tempfile,uuid
from pathlib import Path
import a23_shared_sequence32_scope as material
import a23_shared_sequence32 as s
from analyze_a23_shared_sequence32 import analyze
from a23_execution_context import model as context_model
w=material.w;f=s.f

def compile_command(source,binary):
    r=Path(source)/'research/usb-ds-iso'
    return ['clang','-fobjc-arc','-fblocks','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-omit-frame-pointer','-g',
        '-framework','Foundation','-framework','IOUSBHost','-framework','IOKit',str(r/'host/a23_execution_context.m'),
        str(r/'host/a23_shared_sequence_permit.m'),str(r/'tests/a23_shared_sequence_permit_fixture.m'),'-o',str(binary)]

def namespace(root,scope,h):
    store=s.SharedSequence32(root,simulation=True,fresh_scope=lambda:scope);store.initialize(h);return store

def job(store):
    ident=str(uuid.uuid4());ns=f.load(store.root/'namespace.json');a=dict(schema='A23-shared32-authorization-1',job_id=ident,scope_sha256=ns['scope_sha256'],maximum_invocations=1,simulation=True,hardware_test_authorized=False)
    store.prepare(ident,a);return ident

def native_command(binary,store,ident,scope,case):
    c=context_model(scope['receiver_sha256'],'/injected/shared32-entry')
    return [str(binary),str(store.root),ident,json.dumps(scope),json.dumps(store.binding(ident)),json.dumps(c),case]

def tree(root):return {p.relative_to(root).as_posix():f.sha(p.read_bytes()) for p in root.rglob('*') if p.is_file()}

def cross_job_tests(root,scope,h,binary):
    root.mkdir();out={}
    # Two different jobs, two OS processes, one namespace and one global burn.
    store=namespace(root/'race',scope,h);a=job(store);b=job(store)
    code='''import sys,json
from pathlib import Path
sys.path.insert(0,sys.argv[1]);import a23_shared_sequence32 as s
root=Path(sys.argv[2]);scope=json.loads(sys.argv[4]);store=s.SharedSequence32(root,simulation=True,fresh_scope=lambda:scope)
try:store.issue(sys.argv[3])
except (ValueError,OSError) as e:print(json.dumps(dict(won=False,reason=str(e))))
else:print(json.dumps(dict(won=True)))
'''
    processes=[subprocess.Popen([sys.executable,'-B','-c',code,str(Path(s.__file__).parent),str(store.root),ident,json.dumps(scope)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for ident in (a,b)];results=[]
    for p in processes:
        stdout,stderr=p.communicate(timeout=15);f.require(p.returncode==0 and not stderr,'cross-job process failed');results.append(json.loads(stdout))
    f.require(sum(r['won'] for r in results)==1,'two jobs did not have one winner');burn=f.load(store.root/'block-00081.json');winner=burn['job_id'];loser=b if winner==a else a
    before=tree(store.root)
    try:store.issue(loser)
    except (ValueError,OSError):pass
    else:raise ValueError('losing job took over shared range')
    f.require(before==tree(store.root),'loser changed shared namespace');store.consume(winner)
    cmd=native_command(binary,store,winner,scope,'normal');procs=[subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for _ in range(2)];native=[]
    for p in procs:
        stdout,stderr=p.communicate(timeout=15);f.require(p.returncode==0 and not stderr,'native race failed');native.append(json.loads(stdout))
    f.require(sum(r['selection_returned'] for r in native)==1 and sum(r['process_returned'] for r in native)==1,'native process race had wrong winners')
    out['cross-job-and-native-race']=dict(job_results=results,native_results=native,winner=winner,loser=loser,shared_burn_files=1)
    for kind in ('empty-burn','issue-failure','scope-after-burn','scope-before-issue','history-drift','overlap','stolen-owner','clone','issue-not-committed','consume-not-committed'):
        current=copy.deepcopy(scope);hist=copy.deepcopy(h)
        if kind=='overlap':hist.append(dict(first=97,last=112,reservation_sha256='1'*64,record_sha256='2'*64));current['history_sha256']=f.sha(f.encode(hist))
        st=namespace(root/kind,current,hist);one=job(st);two=job(st);original=f.exclusive
        def fail(path,raw):
            if (kind=='empty-burn' and Path(path).name=='block-00081.json') or (kind=='issue-failure' and Path(path).name=='issue.json'):
                original(path,b'');raise OSError('injected durable empty write')
            original(path,raw)
            if (kind=='scope-after-burn' and Path(path).name=='block-00081.json') or (kind=='issue-not-committed' and Path(path).name=='issue.json') or (kind=='consume-not-committed' and Path(path).name=='consumed.json'):current['workflow_source_sha256']='0'*64
        error=None
        try:
            if kind=='scope-before-issue':current['workflow_source_sha256']='0'*64
            if kind=='history-drift':(st.root/'history.json').write_bytes(f.encode([]))
            f.exclusive=fail;st.issue(one)
            if kind=='consume-not-committed':st.consume(one)
        except (ValueError,OSError) as e:error=str(e)
        finally:f.exclusive=original
        if kind in ('stolen-owner','clone'):
            f.require(error is None,'expected first issue');
            if kind=='stolen-owner':
                shutil.copyfile(st.root/'jobs'/one/'issue.json',st.root/'jobs'/two/'issue.json')
                try:st.consume(two)
                except (ValueError,OSError):error='foreign burn owner rejected'
                else:raise ValueError('foreign job consumed owner receipt')
            else:
                target=root/'cloned-copy';shutil.copytree(st.root,target);cloned=s.SharedSequence32(target,simulation=True,fresh_scope=lambda:current)
                try:cloned.consume(one)
                except (ValueError,OSError):error='cloned namespace rejected'
                else:raise ValueError('cloned namespace consumed')
        f.require(error is not None,'fault did not block: '+kind)
        if kind in ('scope-after-burn','issue-not-committed','consume-not-committed'):current.clear();current.update(copy.deepcopy(scope))
        if kind in ('issue-not-committed','consume-not-committed'):
            try:st.consume(one)
            except (ValueError,OSError):pass
            else:raise ValueError('uncommitted phase resumed')
        before=tree(st.root)
        try:st.issue(two)
        except (ValueError,OSError):pass
        else:raise ValueError('second job admitted after failure: '+kind)
        f.require(before==tree(st.root),'failure retry mutated namespace')
        out[kind]=dict(rejected=True,error=error,burn_retained=(st.root/'block-00081.json').exists())
    return out

def native_cases(root,scope,h,binary):
    root.mkdir();matrix={};accepted={};rejected={}
    cases=('normal','cross-instance-replay','bad-binding','sandbox-context','bool-pid','changed-context','bad-identity','scope-before-process','scope-before-selection','scope-after-selection','fail-after-process-save','fail-after-selection-save','process-file-tamper','context-file-tamper','selection-file-tamper','core-after-selection','production-rejects-model','process-collision','selection-collision','mode-flipped','missing-issue-commit','missing-consume-commit','scope-restored-after-read')
    for name in cases:
        store=namespace(root/name,scope,h);ident=job(store);store.issue(ident);store.consume(ident);cmd=native_command(binary,store,ident,scope,name);folder=store.root/'jobs'/ident
        if name=='missing-issue-commit':(folder/'issue-commit').unlink()
        if name=='missing-consume-commit':(folder/'consume-commit').unlink()
        if name=='process-collision':f.exclusive(folder/'native-process-attempt',b'one attempt\n')
        if name=='selection-collision':f.exclusive(folder/'native-selection-attempt',b'one attempt\n')
        if name=='mode-flipped':ns=f.load(store.root/'namespace.json');ns['simulation']=False;(store.root/'namespace.json').write_bytes(f.encode(ns))
        r=subprocess.run(cmd,capture_output=True,text=True);f.require(r.returncode==0 and not r.stderr,'native fixture failed: '+name+' '+r.stderr);row=json.loads(r.stdout)
        matrix[name]=dict(job_id=ident,native=row)
        try:accepted[name]=analyze(store.root,ident,scope,row)
        except (ValueError,OSError,KeyError,TypeError) as e:rejected[name]=str(e)
    f.require(set(accepted)=={'normal','cross-instance-replay'} and len(rejected)==21,'native classification differs');return matrix,accepted,rejected

def negatives(normal,ident,native,scope,root):
    root.mkdir();out={}
    for name in ('bool-count','split16','owner-job','remaining','context-digest','selection-pid','stale-native','mixed-mode','baseline-scope','duplicate-json','unknown-job-file','partial-burn'):
        dest=root/name;shutil.copytree(normal,dest);folder=dest/'jobs'/ident;n=copy.deepcopy(native)
        if name in ('bool-count','split16','owner-job'):
            row=f.load(dest/'block-00081.json')
            if name=='bool-count':row['count']=True
            elif name=='split16':row['count']=16;row['last']=96
            else:row['job_id']=str(uuid.uuid4())
            (dest/'block-00081.json').write_bytes(f.encode(row))
        elif name=='remaining':row=f.load(folder/'consumed.json');row['remaining']=1;(folder/'consumed.json').write_bytes(f.encode(row))
        elif name=='context-digest':row=f.load(folder/'native-process-claim.json');row['context_sha256']='0'*64;(folder/'native-process-claim.json').write_bytes(f.encode(row))
        elif name=='selection-pid':row=f.load(folder/'native-sdk-claim.json');row['pid']=124;(folder/'native-sdk-claim.json').write_bytes(f.encode(row))
        elif name=='stale-native':n['permit']['stale']=True
        elif name=='mixed-mode':row=f.load(dest/'namespace.json');row['simulation']=False;(dest/'namespace.json').write_bytes(f.encode(row))
        elif name=='baseline-scope':
            row=f.load(dest/'scope.json');row['baseline_manifest_sha256']='0'*64;(dest/'scope.json').write_bytes(f.encode(row));digest=f.sha(f.read(dest/'scope.json'))
            ns=f.load(dest/'namespace.json');ns['scope_sha256']=digest;(dest/'namespace.json').write_bytes(f.encode(ns))
            for file in ('job.json','authorization.json'):
                row=f.load(folder/file);row['scope_sha256']=digest;(folder/file).write_bytes(f.encode(row))
            row=f.load(dest/'block-00081.json');row.update(scope_sha256=digest,job_sha256=f.sha(f.read(folder/'job.json')),authorization_sha256=f.sha(f.read(folder/'authorization.json')));(dest/'block-00081.json').write_bytes(f.encode(row))
            row=f.load(folder/'issue.json');row.update(scope_sha256=digest,reservation_sha256=f.sha(f.read(dest/'block-00081.json')),authorization_sha256=f.sha(f.read(folder/'authorization.json')));(folder/'issue.json').write_bytes(f.encode(row))
            row=f.load(folder/'consumed.json');row.update(scope_sha256=digest,reservation_sha256=f.sha(f.read(dest/'block-00081.json')),issue_sha256=f.sha(f.read(folder/'issue.json')),authorization_sha256=f.sha(f.read(folder/'authorization.json')));(folder/'consumed.json').write_bytes(f.encode(row))
            row=f.load(folder/'native-process-claim.json');row.update(scope_sha256=digest,consumed_sha256=f.sha(f.read(folder/'consumed.json')));(folder/'native-process-claim.json').write_bytes(f.encode(row))
            row=f.load(folder/'native-sdk-claim.json');row['process_sha256']=f.sha(f.read(folder/'native-process-claim.json'));(folder/'native-sdk-claim.json').write_bytes(f.encode(row))
        elif name=='duplicate-json':p=folder/'native-sdk-claim.json';raw=p.read_bytes();p.write_bytes(b'{"pid":123,'+raw[1:])
        elif name=='unknown-job-file':(folder/'unexpected').write_bytes(b'x')
        elif name=='partial-burn':(dest/'block-00081.json').write_bytes(b'{')
        try:analyze(dest,ident,scope,n)
        except (ValueError,OSError,KeyError,TypeError) as e:out[name]=dict(rejected=True,reason=str(e),native=n)
        else:raise ValueError('bad shared chain accepted: '+name)
    return out

def run(output):
    output=w.canonical(output);f.require(not output.exists(),'new review required');source=material.sources();inputs=material.materials();scope=inputs['scope'];h=inputs['history'];output.mkdir(mode=0o700)
    for name,digest in source.items():
        raw=w.plain(w.b.REPO/name,2*1024*1024);f.require(f.sha(raw)==digest,'source drift');w.card.put(output,'source/'+name,raw)
    w.write(output/'materials.json',inputs);cmd=compile_command(output/'source',output/'native-permit-test');r=subprocess.run(cmd,capture_output=True,text=True)
    w.card.put(output,'compile.log',(r.stdout+r.stderr).encode());f.require(r.returncode==0,'native permit compile failed')
    with tempfile.TemporaryDirectory(prefix='a23-shared32-',dir='/private/tmp') as tmp:
        tmp=Path(tmp);cross=cross_job_tests(tmp/'shared',scope,h,output/'native-permit-test');matrix,accepted,rejected=native_cases(tmp/'native',scope,h,output/'native-permit-test')
        normal=tmp/'native/normal';ident=matrix['normal']['job_id'];bad=negatives(normal,ident,matrix['normal']['native'],scope,tmp/'negative')
        shutil.copytree(tmp/'shared',output/'shared');shutil.copytree(tmp/'native',output/'native');shutil.copytree(tmp/'negative',output/'negative')
    f.require(material.sources()==source,'source drift after shared audit')
    audit=dict(schema='A23-shared32-offline-audit-1',passed=True,source_count=len(source),source_hashes=source,prior_sources_unchanged=351,
        shared_cases=cross,native_cases=23,matrix=matrix,accepted=accepted,rejected=rejected,negative_archives=bad,compiler_command=cmd,
        sanitizers=['address','undefined'],usb_requests=0,sd_accesses=0,real_sdk_objects=0,formal_records=0,formal_reservations=0,remaining=0,
        hardware_verified=False,receiver_launched=False,production_engine_implemented=True,production_native_permit_implemented=True,
        production_fresh_scope_binding_wired=False,formal_issuance_available=False,acquisition_mode_implemented=False,firmware_built=False)
    w.write(output/'audit.json',audit);w.b.seal(output);return dict(reference=w.reference(output),sources=len(source),native_cases=23,shared_cases=len(cross),negative_archives=len(bad),passed=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);print(json.dumps(run(p.parse_args().output),indent=2))
