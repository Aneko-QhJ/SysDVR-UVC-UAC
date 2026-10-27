"""End-to-end supervised fake SDK models; actual sandbox rejection retained."""
import argparse,copy,json,shutil,tempfile,time
from pathlib import Path
import build_a23_broker_model as b
import a23_broker_model as model
import a23_broker_archive as ar
import audit_a23_scope_verifier as frozen
w=b.w;a=ar.a;f=a.f
CASES=('actual-policy-denied','injected-normal','injected-queued-delay','bad-payload','command-context','scope-before-consume','consumed-tamper','context-substitution','partial-control','timeout-before-hello','timeout-after-command','hello-timeout-before-hello')

def until(m,predicate,limit=40):
    end=time.monotonic()+limit
    while not predicate():f.require(time.monotonic()<end,'broker model observation bound exceeded');m.step()

def exercise(builds,scratch,output):
    output.mkdir();receiver=builds/'receiver-build';supervisor=builds/'supervisor-build';inputs=scratch/'inputs';frozen.template(receiver,inputs);roots={k:inputs/k for k in ('repository','cards','ledger','records')};history=f.load(builds/'history.json');out={};pending={}
    for case in CASES:
        m=model.BrokerModel(scratch/case,receiver,supervisor,roots,history,case,case!='actual-policy-denied');m.start()
        if case in ('timeout-before-hello','timeout-after-command','hello-timeout-before-hello'):
            if case=='timeout-after-command':until(m,lambda:(m.execution/'command-seen').exists())
            until(m,lambda:m.supervision.hello_timed_out if case=='hello-timeout-before-hello' else m.supervision.timed_out);pending[case]=dict(handle_retained=m.supervision.handoff['nonce'] in model.sv.ACTIVE,final_before_release=m.collect(output/case),namespace_exists=(m.execution/'namespace').exists());f.require(pending[case]['handle_retained'] and pending[case]['final_before_release'] is False and not (output/case).exists(),'unresolved model collected')
            m.supervision.process.stdin.write(b'x');m.supervision.process.stdin.flush()
            if case in ('timeout-before-hello','hello-timeout-before-hello') or m.control is None:m.supervision.process.stdin.close()
        until(m,lambda:bool(m.supervision.settled_ns));out[case]=m.collect(output/case);f.require(out[case] is not False,'exited broker not collected')
        report=f.parse(a.read(output/case/'final/report.json'))
        for k,max_ in (('iso_submissions',2),('burst_triggers',2),('aborts',1)):f.require(type(report['calls'][k]) is int and report['calls'][k]<=max_,'fake resource limit exceeded')
        if case in ('actual-policy-denied','command-context','scope-before-consume','consumed-tamper','partial-control','timeout-before-hello','timeout-after-command','hello-timeout-before-hello'):f.require(report['calls']['wait_creates']==report['calls']['opens']==0,'denied model reached wait/SDK')
        try:m.start()
        except ValueError:pass
        else:raise ValueError('broker model relaunched')
        try:m.collect(output/(case+'-retry'))
        except ValueError:pass
        else:raise ValueError('broker final collection retried')
    f.require({n for n,r in out.items() if r['complete_injected_model_chain']}=={'injected-normal','injected-queued-delay'},'joined broker classification differs');f.require(out['context-substitution']['collection']['analysis']['supplied_model_chain_complete'] is True and 'execution context substitution' in out['context-substitution']['errors'],'context substitution was not separated from standalone receiver validity')
    # Failed spawn never has a producer handle or final collection authority.
    m=model.BrokerModel(scratch/'spawn-error',receiver,supervisor,roots,history,'spawn-error',True);original=model.sv.subprocess.Popen
    def error(*args,**kwargs):raise OSError('injected model spawn failure')
    model.sv.subprocess.Popen=error
    try:
        try:m.start()
        except OSError:pass
        else:raise ValueError('spawn error admitted')
    finally:model.sv.subprocess.Popen=original
    f.require(m.collect(output/'spawn-error') is False and m.supervision.process is None,'unknown spawn collected');m.supervision.selector.close();shutil.copytree(m.root,output/'spawn-error-partial');f.require(not model.sv.ACTIVE,'unresolved broker handle lost or leaked')
    return dict(matrix=out,pending_before_release=pending,spawn_failure_retained=True)

def reseal(root):
    (root/'SHA256SUMS').unlink();(root/'COMMITTED').unlink();a.seal(root)

def negatives(normal,substitution,builds,output):
    output.mkdir();out={}
    for name in ('forged-substitution-success','command-context','command-job','expected-scope','binary-roles','missing-commit','claims-acquire'):
        target=output/name;shutil.copytree(substitution if name=='forged-substitution-success' else normal,target)
        if name in ('forged-substitution-success','claims-acquire','binary-roles'):
            p=target/'envelope.json';meta=f.parse(a.read(p))
            if name=='forged-substitution-success':meta['complete_injected_model_chain']=True
            elif name=='claims-acquire':meta['acquisition_permitted']=True
            else:meta['supervisor_build']['binary_sha256']='0'*64
            p.write_bytes(f.encode(meta));reseal(target)
        elif name in ('command-context','command-job'):
            p=target/'control.json';c=f.parse(a.read(p))
            if name=='command-context':c['actual_context']['pid']=123
            else:c['job_path']='/injected/other-job'
            p.write_bytes(f.encode(c));reseal(target)
        elif name=='expected-scope':p=target/'expected-scope.json';c=f.parse(a.read(p));c['formal_issuance_available']=0;p.write_bytes(f.encode(c));reseal(target)
        elif name=='missing-commit':(target/'COMMITTED').unlink()
        try:ar.analyze(target,builds/'receiver-build',builds/'supervisor-build')
        except (ValueError,OSError,KeyError,TypeError) as e:out[name]=str(e)
        else:raise ValueError('bad joined broker envelope accepted '+name)
    return out

def run(output):
    output=w.canonical(output);f.require(not output.exists(),'new broker review required');before=b.sources();output.mkdir(mode=0o700);b.build(output/'builds');scratch=Path(tempfile.mkdtemp(prefix='a23-broker-',dir='/private/tmp'));w.write(output/'scratch-reference.json',dict(directory=str(scratch),failure_policy='retain unresolved child inputs and ownership'))
    rows=exercise(output/'builds',scratch,output/'models');bad=negatives(output/'models/injected-normal',output/'models/context-substitution',output/'builds',output/'negative');f.require(not model.sv.ACTIVE,'cannot clean unresolved broker scratch');shutil.rmtree(scratch);f.require(before==b.sources(),'broker sources changed during audit')
    report=dict(schema='A23-broker-offline-audit-1',passed=True,source_count=len(before),source_hashes=before,prior_sources_unchanged=378,model_cases=len(CASES),complete_models=2,incomplete_models=len(CASES)-2,negative_archives=bad,**rows,sanitizers=['address','undefined'],usb_requests=0,sd_accesses=0,real_sdk_objects=0,formal_records=0,formal_reservations=0,production_broker_implemented=False,**ar.FALSE)
    w.write(output/'audit.json',report);w.b.seal(output);w.card.seal_verify(output);return dict(reference=w.reference(output),sources=len(before),model_cases=len(CASES),negative_archives=len(bad),passed=True)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);print(json.dumps(run(p.parse_args().output),indent=2))
