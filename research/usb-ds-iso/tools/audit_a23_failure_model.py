"""Native abrupt-exit fixtures and file-only failure archive fault injection."""
import argparse,copy,json,shutil,tempfile,time
from pathlib import Path
import build_a23_failure_model as b
import a23_guarded_broker_model as model
import a23_failure_archive as ar
import a23_failure_collector as collector
import audit_a23_scope_verifier as frozen
w=b.w;a=ar.a;f=a.f
CASES=('actual-policy-denied','injected-normal','context-substitution','consumed-tamper','partial-control','exit-before-hello','partial-hello','exit-after-command','partial-report','non-object-report','empty-report','timeout-before-hello')
def until(m,predicate,limit=40):
    end=time.monotonic()+limit
    while not predicate():f.require(time.monotonic()<end,'failure model observation exceeded');m.step()
def exercise(builds,scratch,output,source_reader,expected):
    output.mkdir();receiver=builds/'receiver-build';supervisor=builds/'supervisor-build';inputs=scratch/'inputs';frozen.template(receiver,inputs);roots={k:inputs/k for k in ('repository','cards','ledger','records')};history=f.load(builds/'history.json');rows={};pending={};rejected={}
    def instance(case,reader=source_reader,build=receiver):return model.GuardedBroker(scratch/case,build,supervisor,roots,history,case,case!='actual-policy-denied',source_reader=reader,expected_sources=expected)
    for case in CASES:
        m=instance(case);m.start()
        if case=='timeout-before-hello':
            until(m,lambda:m.supervision.timed_out);pending=dict(handle_retained=m.supervision.handoff['nonce'] in model.old.sv.ACTIVE,final_before_release=m.collect(output/'running-producer'),attempt_marker_before_release=(m.root/'FAILURE_COLLECTION_ATTEMPT').exists());f.require(pending['handle_retained'] and pending['final_before_release'] is False and not pending['attempt_marker_before_release'] and not (output/'running-producer').exists(),'running producer collected')
            m.supervision.process.stdin.write(b'x');m.supervision.process.stdin.flush();m.supervision.process.stdin.close()
        until(m,lambda:bool(m.supervision.settled_ns));rows[case]=m.collect(output/case);f.require(rows[case] is not False,'exited model not collected')
        raw=a.read(output/case/'final/report.json')
        if rows[case]['report_state']=='object':
            report=f.parse(raw);f.require(report['calls']['opens']<=1 and report['calls']['iso_submissions']<=2,'fake SDK limit differs')
        for action in (lambda:m.start(),lambda:m.collect(output/(case+'-retry')),lambda:collector.collect(collector.ExitedModelFiles(m.root,receiver,supervisor,m.supervision.process.pid,m.delivery),output/(case+'-direct-retry'))):
            try:action()
            except (ValueError,OSError):pass
            else:raise ValueError('model launch or collection replay accepted')
        f.require((m.root/'FAILURE_COLLECTION_ATTEMPT').exists(),'durable collection latch missing')
    f.require({n for n,r in rows.items() if r['complete_injected_model_chain']}=={'injected-normal'},'failure matrix classification differs')
    # A source change after construction refuses launch; do not mutate repository.
    changed=copy.deepcopy(expected);changed[next(iter(changed))]='0'*64;m=instance('source-drift',lambda:changed)
    try:m.start()
    except ValueError as e:rejected['source-drift']=str(e)
    else:raise ValueError('source drift launched')
    f.require(m.supervision.process is None and m.store is None and not (m.supervision.root/'launch-attempt').exists() and m.collect(output/'source-drift') is False,'source refusal created producer or consumption');m.supervision.selector.close();shutil.copytree(m.root,output/'source-drift-partial')
    # Corrupt a private copy after construction; neither binary nor build is run.
    bad=scratch/'changed-receiver';shutil.copytree(receiver,bad);m=instance('build-drift',build=bad);p=bad/'verified-entry';raw=a.read(p);p.write_bytes(raw[:-1]+bytes([raw[-1]^1]))
    try:m.start()
    except ValueError as e:rejected['build-drift']=str(e)
    else:raise ValueError('build drift launched')
    f.require(m.supervision.process is None and m.store is None and not (m.supervision.root/'launch-attempt').exists(),'build refusal launched');m.supervision.selector.close();shutil.copytree(m.root,output/'build-drift-partial')
    m=instance('spawn-error');original=model.old.sv.subprocess.Popen
    def error(*args,**kwargs):raise OSError('injected failure model spawn error')
    model.old.sv.subprocess.Popen=error
    try:
        try:m.start()
        except OSError:pass
        else:raise ValueError('spawn error accepted')
    finally:model.old.sv.subprocess.Popen=original
    f.require(m.collect(output/'spawn-error') is False and m.supervision.process is None,'unknown spawn collected');m.supervision.selector.close();shutil.copytree(m.root,output/'spawn-error-partial');f.require(not model.old.sv.ACTIVE,'unresolved failure model handle leaked')
    return dict(matrix=rows,pending_before_release=pending,prelaunch_rejected=rejected,spawn_failure_retained=True)
def reseal(root):
    (root/'SHA256SUMS').unlink();(root/'COMMITTED').unlink();a.seal(root)
def negatives(models,builds,output):
    output.mkdir();out={}
    for name in ('forged-missing-success','report-state','source-digest','typed-admission','producer-pid','stream-substitution','missing-commit'):
        target=output/name;shutil.copytree(models/('exit-after-command' if name=='forged-missing-success' else 'injected-normal'),target)
        if name in ('forged-missing-success','report-state','producer-pid'):
            p=target/'envelope.json';v=f.parse(a.read(p));v['complete_injected_model_chain']=True if name=='forged-missing-success' else v['complete_injected_model_chain']
            if name=='report-state':v['report_state']='missing'
            if name=='producer-pid':v['child_pid']=123
            p.write_bytes(f.encode(v));reseal(target)
        elif name in ('source-digest','typed-admission'):
            p=target/'admission.json';v=f.parse(a.read(p));v['observed_sha256']='0'*64 if name=='source-digest' else v['observed_sha256']
            if name=='typed-admission':v['production_execution_authorized']=0
            p.write_bytes(f.encode(v));reseal(target)
        elif name=='stream-substitution':(target/'final/process.stdout').write_bytes(b'{}\n');reseal(target/'final');reseal(target)
        else:(target/'COMMITTED').unlink()
        try:ar.analyze(target,builds/'receiver-build',builds/'supervisor-build')
        except (ValueError,OSError,KeyError,TypeError) as e:out[name]=str(e)
        else:raise ValueError('forged failure archive accepted '+name)
    return out
def run(output):
    output=w.canonical(output);f.require(not output.exists(),'new failure review required');source=b.sources();output.mkdir(mode=0o700);b.build(output/'builds');scratch=Path(tempfile.mkdtemp(prefix='a23-failure-',dir='/private/tmp'));w.write(output/'scratch-reference.json',dict(directory=str(scratch),failure_policy='retain unresolved ownership and uncommitted attempt'))
    rows=exercise(output/'builds',scratch,output/'models',b.sources,source);bad=negatives(output/'models',output/'builds',output/'negative');f.require(not model.old.sv.ACTIVE and b.sources()==source,'unresolved producer or source drift');shutil.rmtree(scratch)
    report=dict(schema='A23-model-failure-audit-1',passed=True,source_count=len(source),source_hashes=source,prior_sources_unchanged=385,model_cases=len(CASES),negative_archives=bad,**rows,sanitizers=['address','undefined'],usb_requests=0,sd_accesses=0,real_sdk_objects=0,formal_records=0,formal_reservations=0,production_broker_implemented=False,os_capability_isolation_implemented=False,**ar.old.FALSE)
    w.write(output/'audit.json',report);w.b.seal(output);w.card.seal_verify(output);return dict(reference=w.reference(output),sources=len(source),model_cases=len(CASES),negative_archives=len(bad),passed=True)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);print(json.dumps(run(p.parse_args().output),indent=2))
