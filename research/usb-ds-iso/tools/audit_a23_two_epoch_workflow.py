"""File-only saved69/atomic32 model audit; never writes the real ledger."""
import argparse,json,shutil,subprocess,sys,tempfile
from pathlib import Path
import a23_two_epoch_baseline69 as baseline
import a23_sequence32_model as m
from analyze_a23_sequence32 import analyze
from a23_execution_context import model as context_model
from prepare_a23_two_epoch import preview
w=baseline.w

def context(scope):return context_model(scope['model_materials']['receiver_sha256'],'/injected/two-epoch-entry')
def identity():return dict(device_id=101,interface_id=102,speed=3)
def digest_tree(root):return {p.relative_to(root).as_posix():m.sha(p.read_bytes()) for p in root.rglob('*') if p.is_file()}

def race(root,operation,scope):
    code='''import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import a23_sequence32_model as m
root=Path(sys.argv[2]);op=sys.argv[3];c=json.loads(sys.argv[4]);i=json.loads(sys.argv[5])
try:
 if op=='issue':m.issue(root)
 elif op=='consume':m.consume(root)
 elif op=='process':m.process_claim(root,c)
 else:m.selection_claim(root,i,c)
except (ValueError,OSError) as e:print(json.dumps(dict(won=False,reason=str(e))))
else:print(json.dumps(dict(won=True)))
'''
    args=[sys.executable,'-B','-c',code,str(Path(m.__file__).parent),str(root),operation,json.dumps(context(scope)),json.dumps(identity())]
    children=[subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for _ in range(2)];out=[]
    for child in children:
        stdout,stderr=child.communicate(timeout=15);m.require(child.returncode==0 and not stderr,'model race worker failed');out.append(json.loads(stdout))
    m.require(sum(r['won'] for r in out)==1,'race did not have exactly one winner');return out

def models(root,scope):
    root.mkdir();out={};names=('normal','reserve-only','issue-only','consume-only','bad-context','boolean-pid','changed-context','bad-identity','boolean-speed',
        'partial-reservation','empty-reservation','issue-write-failed','consume-write-failed','context-write-failed','process-write-failed','selection-write-failed',
        'consume-marker','process-marker','selection-marker','race-issue','race-consume','race-process','race-selection')
    for name in names:
        folder=root/name;m.create(folder,scope['model_materials'],scope['baseline']['history']);c=context(scope);i=identity();events=[];error=None
        original=m.exclusive
        failure={'partial-reservation':('reservation.json',b'{"schema":'),'empty-reservation':('reservation.json',b''),
            'issue-write-failed':('issue.json',b''),'consume-write-failed':('consumed.json',b'{'),
            'context-write-failed':('context.json',b'{'),'process-write-failed':('process-claim.json',b'{'),'selection-write-failed':('sdk-claim.json',b'{')}
        def injected(path,raw):
            if name in failure and Path(path).name==failure[name][0]:original(path,failure[name][1]);raise OSError('injected durable partial write')
            original(path,raw)
        try:
            m.exclusive=injected
            if name=='reserve-only':m.reserve(folder)
            else:
                if name=='race-issue':events=race(folder,'issue',scope)
                else:m.issue(folder)
                if name!='issue-only':
                    if name=='consume-marker':original(folder/'consume-attempt',b'one attempt\n')
                    if name=='race-consume':events=race(folder,'consume',scope)
                    else:m.consume(folder)
                    if name!='consume-only':
                        if name=='bad-context':c['sandbox_query_result']=1
                        if name=='boolean-pid':c['pid']=True
                        if name=='process-marker':original(folder/'process-attempt',b'one attempt\n')
                        if name=='race-process':events=race(folder,'process',scope)
                        else:m.process_claim(folder,c)
                        if name=='changed-context':c['pid']+=1
                        if name=='bad-identity':i['interface_id']=101
                        if name=='boolean-speed':i['speed']=True
                        if name=='selection-marker':original(folder/'selection-attempt',b'one attempt\n')
                        if name=='race-selection':events=race(folder,'selection',scope)
                        else:m.selection_claim(folder,i,c)
        except (ValueError,OSError) as e:error=str(e)
        finally:m.exclusive=original
        complete=False;reason=None
        try:result=analyze(folder,scope);complete=True
        except (ValueError,OSError,KeyError,TypeError) as e:reason=str(e);result=None
        expected=name in ('normal','race-issue','race-consume','race-process','race-selection');m.require(complete is expected,'model classification differs: '+name)
        before=digest_tree(folder)
        for operation in (m.reserve,m.issue):
            try:operation(folder)
            except (ValueError,OSError):pass
            else:raise ValueError('burn reused: '+name)
        m.require(digest_tree(folder)==before,'retry changed burned model: '+name)
        if complete:
            for operation in (m.consume,lambda r:m.process_claim(r,c),lambda r:m.selection_claim(r,i,c)):
                try:operation(folder)
                except (ValueError,OSError):pass
                else:raise ValueError('consumed phase reused')
            m.require(digest_tree(folder)==before,'claim replay changed files')
        out[name]=dict(complete=complete,result=result,rejection_reason=reason,injected_error=error,race=events,files=digest_tree(folder),entire32_burn_kept=(folder/'reservation.json').exists())
    return out

def negatives(normal,root,scope):
    root.mkdir();out={}
    for name in ('split16','bool-count','old-baseline','source-scope','history-scope','remaining','wrong-pid','wrong-identity','context-digest','hardware-claim','duplicate-json','unknown-file','missing-attempt','partial-issue','wrong-lock'):
        folder=root/name;shutil.copytree(normal,folder)
        target='reservation.json';r=m.load(folder/target)
        if name=='split16':r['last']=96;r['count']=16
        elif name=='bool-count':r['count']=True
        elif name in ('old-baseline','source-scope','hardware-claim'):
            target='materials.json';r=m.load(folder/target)
            if name=='old-baseline':r['baseline_manifest_sha256']=scope['baseline']['prior_snapshot']['manifest_sha256']
            elif name=='source-scope':r['workflow_source_sha256']='0'*64
            else:r['hardware_entry_enabled']=True
        elif name=='history-scope':target='history.json';r=m.load(folder/target);r[0]['record_sha256']='0'*64
        elif name=='remaining':target='consumed.json';r=m.load(folder/target);r['remaining']=1
        elif name in ('wrong-pid','wrong-identity'):target='sdk-claim.json';r=m.load(folder/target);r['pid']=124 if name=='wrong-pid' else r['pid'];r['identity']['interface_id']=101 if name=='wrong-identity' else 102
        elif name=='context-digest':target='process-claim.json';r=m.load(folder/target);r['context_sha256']='0'*64
        if name in ('split16','bool-count','old-baseline','source-scope','history-scope','remaining','wrong-pid','wrong-identity','context-digest','hardware-claim'):
            (folder/target).write_bytes(m.encode(r))
            if target in ('materials.json','history.json'):
                cap=m.load(folder/'capsule.json');cap['materials_sha256' if target=='materials.json' else 'history_sha256']=m.sha(m.read(folder/target));(folder/'capsule.json').write_bytes(m.encode(cap))
        elif name=='duplicate-json':p=folder/'sdk-claim.json';raw=p.read_bytes();p.write_bytes(b'{"pid":123,'+raw[1:])
        elif name=='unknown-file':(folder/'unexpected').write_bytes(b'x')
        elif name=='missing-attempt':(folder/'selection-attempt').unlink()
        elif name=='partial-issue':(folder/'issue.json').write_bytes(b'{')
        elif name=='wrong-lock':(folder/'.lock').write_bytes(b'changed')
        elif name=='symlink':(folder/'context.json').unlink();(folder/'context.json').symlink_to(normal/'context.json')
        try:analyze(folder,scope)
        except (ValueError,OSError,KeyError,TypeError) as e:out[name]=dict(rejected=True,reason=str(e))
        else:raise ValueError('bad model archive accepted: '+name)
    return out

def run(output):
    output=w.canonical(output);m.require(not output.exists(),'new review required');hashes=baseline.sources();scope=preview();output.mkdir(mode=0o700)
    before={p.name:m.sha(w.plain(p)) for p in w.LEDGER.iterdir() if p.is_file()};w.write(output/'preview.json',scope)
    for n,h in hashes.items():
        raw=w.plain(w.b.REPO/n,2*1024*1024);m.require(m.sha(raw)==h,'source drift');w.card.put(output,'source/'+n,raw)
    saved=w.card.verify_snapshot(baseline.ANCHOR)
    for name,raw in saved.items():w.card.put(output,'saved69/'+name,raw)
    with tempfile.TemporaryDirectory(prefix='a23-sequence32-',dir='/private/tmp') as tmp:
        scratch=Path(tmp);matrix=models(scratch/'models',scope);negative=negatives(scratch/'models/normal',scratch/'negative',scope)
        shutil.copytree(scratch/'models',output/'models');shutil.copytree(scratch/'negative',output/'negative')
        clone=scratch/'clone';shutil.copytree(scratch/'models/issue-only',clone);old=digest_tree(clone)
        try:m.consume(clone)
        except ValueError:pass
        else:raise ValueError('copied model writable')
        m.require(digest_tree(clone)==old,'copy claim changed files')
    m.require(before=={p.name:m.sha(w.plain(p)) for p in w.LEDGER.iterdir() if p.is_file()},'real ledger changed')
    m.require(hashes==baseline.sources(),'source drift after models')
    audit=dict(schema='A23-sequence32-offline-audit-1',passed=True,source_hashes=hashes,source_count=len(hashes),prior_sources_unchanged=345,
        models=matrix,model_cases=len(matrix),accepted=sorted(n for n,r in matrix.items() if r['complete']),negative_archives=negative,
        cloned_writer_rejected=True,real_ledger_before=before,real_ledger_after=before,actual_baseline69_validated=True,
        actual_history=[(r['first'],r['last']) for r in scope['baseline']['history']],usb_requests=0,sd_accesses=0,real_sdk_objects=0,
        formal_records=0,formal_reservations=0,remaining=0,hardware_verified=False,firmware_built=False,receiver_launched=False,
        formal_issuance_available=False,production_permit_implemented=False,acquisition_mode_implemented=False)
    w.write(output/'audit.json',audit);w.b.seal(output);return dict(reference=w.reference(output),sources=len(hashes),model_cases=len(matrix),negative_archives=len(negative),passed=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);print(json.dumps(run(p.parse_args().output),indent=2))
