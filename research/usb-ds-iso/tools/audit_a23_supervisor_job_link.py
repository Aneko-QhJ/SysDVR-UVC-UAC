"""Pure cached job/receipt correspondence and unapplied static read-only adapter."""
from pathlib import Path
import argparse,copy,json,subprocess
import a23_supervisor_job_link as model
import a23_supervisor_job_plan as plan
import audit_a23_supervisor_unified as previous
import audit_a23_cached_permit_context as historical
import audit_a23_cached_clock_domains as lineage
f,a=previous.f,previous.a
BASE=previous.BASE
PARENT='A23-supervisor-unified-closeout-20261020'
PARENT_SUM='d2bc4a251b1796bf7e2cc43bdd299fe1253df9515608a633f2f8dfe4c427fb9c'
SOURCE_REVIEW_SUM='f0322a1990f2d1db525984856db81c87c1ff2b93db1d0c80bf971541192b8f67'
JOB_REVIEW_SUM='5f843197e793bcbcf4ce1f0e3265d052d155eebbcdc2c15080841db9e4e3fda2'
NEW=('tools/a23_supervisor_job_link.py','tools/a23_supervisor_job_plan.py','tools/audit_a23_supervisor_job_link.py','tests/test_a23_supervisor_job_link.py')
VARIANTS=('job-scope','job-authorization-bool','job-authorization-hardware','job-consumed-remaining','job-consume-marker','job-native-stale','job-context-pid-bool','job-selection-identity',
    'link-job-id','link-consumed-hash','link-entry-binding','link-session','link-identity','link-descriptor','link-snapshot-hash','link-receipt-hash','link-case','link-observation-hash','link-relation-promoted','link-extra-authority')
FALSE={**previous.FALSE,**model.FALSE,'readonly_job_link_production_integrated':False,'same_job_execution_proven':False}
seal,sealed,reference,cache=previous.seal,previous.sealed,previous.reference,previous.cache


def sources():
    import audit_a23_pinned_view as old
    w=old.w;root=w.A/PARENT;w.card.seal_verify(root);f.require(f.sha(w.plain(root/'SHA256SUMS'))==PARENT_SUM,'parent pin differs')
    saved=w.load(root/'closeout.json');out=previous.sources();f.require(out==saved['source_hashes'] and len(out)==503,'prior503 drift')
    for n in NEW:
        key=BASE+n;f.require(key not in out,'source overlap');out[key]=f.sha(w.plain(w.ROOT/n))
    return dict(sorted(out.items()))


def extract_job(review):
    f.require(historical.a.sealed(review)[2]==JOB_REVIEW_SUM,'historical model review pin differs')
    builds,journal,roots=historical.factory.load_bundle(review/'bundle');raw={n:journal[0].read(n) for n in journal[0].files}
    receiver,_=historical.model.session.build.grouped.consume(*builds['receiver'])
    records=historical.model.shared_records(raw,receiver);native=historical.model.native_links(raw,records);historical.model.supervision_links(raw,records,native)
    prefix=historical.model.INPUTS+'namespace/';out={n:raw[prefix+n] for n in ('scope.json','history.json','namespace.json')}
    out['reservation.json']=raw[prefix+'block-00081.json']
    for n in model.JOB_FILES-{'scope.json','history.json','namespace.json','reservation.json','entry-binding.json','native-permit.json'}:out[n]=raw[records['job_prefix']+n]
    out['entry-binding.json']=model.encode(historical.f.parse(raw[historical.model.HOST+'entry-current.json'])['binding'])
    out['native-permit.json']=model.encode(native['report']['native']['permit']);model.job_view(out)
    return out


def material(inputs,name):
    p=inputs/'supervisor'/name
    return f.load(p/'observation.json'),a.read(p/'stdout.bin'),a.read(p/'stderr.bin'),cache(p/'materials')


def variant(inputs,label):
    name=label if label in previous.materials.CASES else 'normal';job=cache(inputs/'job');o,out,err,c=material(inputs,name)
    seed=cache(inputs/'seeds'/previous.materials.material_case(name));link=model.declaration(job,o,c if 'sdk-receipt/receipt.json' in c else seed)
    def change(n,fn):
        value=model.parse(job[n]);fn(value);job[n]=model.encode(value)
    if label=='job-scope':change('scope.json',lambda v:v.update(receiver_sha256='0'*64))
    if label=='job-authorization-bool':change('authorization.json',lambda v:v.update(maximum_invocations=True))
    if label=='job-authorization-hardware':change('authorization.json',lambda v:v.update(hardware_test_authorized=True))
    if label=='job-consumed-remaining':change('consumed.json',lambda v:v.update(remaining=1))
    if label=='job-consume-marker':job['consume-commit']=b'not committed\n'
    if label=='job-native-stale':change('native-permit.json',lambda v:v.update(stale=True))
    if label=='job-context-pid-bool':change('native-context.json',lambda v:v.update(pid=True))
    if label=='job-selection-identity':change('native-sdk-claim.json',lambda v:v['identity'].update(device_id=103))
    if label=='link-job-id':link['job_id']='00000000-0000-0000-0000-000000000001'
    if label=='link-consumed-hash':link['consumed_sha256']='0'*64
    if label=='link-entry-binding':link['entry_binding']['receiver_sha256']='0'*64
    if label=='link-session':link['sdk_binding']['session_id']='other-session'
    if label=='link-identity':link['sdk_binding']['identity']['interface_id']=103
    if label=='link-descriptor':link['sdk_binding']['descriptor_sha256']['active_interface']='0'*64
    if label=='link-snapshot-hash':link['sdk_snapshot_sha256']='0'*64
    if label=='link-receipt-hash':link['sdk_receipt_sha256']='0'*64
    if label=='link-case':link['supervisor_case']='read-interrupted'
    if label=='link-observation-hash':link['observation_sha256']='0'*64
    if label=='link-relation-promoted':link['relation_kind']='same_live_run'
    if label=='link-extra-authority':link['production_execution_authorized']=True
    expected=model.encode(model.anchor(name,job,o,out,err,c,JOB_REVIEW_SUM,SOURCE_REVIEW_SUM))
    return expected,job,o,out,err,c,model.encode(link)


def read_case(directory,pin):
    directory=a.canonical(directory);expected=a.read(directory/'expected.json');job=cache(directory/'job');o=f.load(directory/'observation.json')
    return model.assess(expected,pin,job,o,a.read(directory/'stdout.bin'),a.read(directory/'stderr.bin'),cache(directory/'materials'),a.read(directory/'link.json'))


def exercise(source,inputs,output):
    output.mkdir(mode=0o700);model.job_view(cache(inputs/'job'));static,wrapper,diff=plan.render(source)
    a.put(output,'integration-plan.json',f.encode(static));a.put(output,'generated/'+plan.TARGET,wrapper);a.put(output,'readonly-adapter.diff',diff)
    rows={}
    for label in (*previous.materials.CASES,*VARIANTS):
        expected,job,o,out,err,c,link=variant(inputs,label);pin=model.sha(expected);directory=output/'cases'/label
        for n,v in (('expected.json',expected),('link.json',link),('observation.json',f.encode(o)),('stdout.bin',out),('stderr.bin',err)):a.put(directory,n,v)
        for n,v in job.items():a.put(directory,'job/'+n,v)
        for n,v in c.items():a.put(directory,'materials/'+n,v)
        checked=read_case(directory,pin)
        if label in VARIANTS:f.require(bool(checked['errors']) and not checked['correspondence_valid'] and not checked['linked_model_completion'],'semantic link mutation accepted '+label)
        else:f.require(checked['linked_model_completion'] is (label in previous.GOOD),'cached completion link differs '+label)
        f.require(all(checked[k] is False for k in model.FALSE),'link grants authority')
        a.put(directory,'analysis.json',f.encode(checked));rows[label]=dict(result=checked,expected_sha256=pin,constructed_model=label in VARIANTS)
    return dict(passed=True,model_cases=57,semantic=rows,static_plan=static,readonly_adapter_sha256=f.sha(wrapper),readonly_diff_sha256=f.sha(diff),
        job_files=len(model.JOB_FILES),original_model_job_reused=True,new_job_created=False,python_fixture_direct_children=0,forked_pipe_holders=0,
        native_compiler_jobs=0,isolated_native_model_executions=0,real_sdk_objects=0,usb_requests=0,sd_accesses=0,production_receiver_executions=0,**FALSE)


def verify(root,pin):
    root=a.canonical(root);_,_,digest=sealed(root);f.require(f.hex64(pin) and pin==digest,'external review pin differs')
    audit=f.load(root/'audit.json');report=f.load(root/'results.json');f.require(audit['source_count']==507 and audit['prior_sources_unchanged']==503 and len(audit['source_hashes'])==507,'job link source inventory differs')
    for n,h in audit['source_hashes'].items():f.require(f.sha(a.read(root/'source'/n))==h,'frozen job link source differs')
    static,wrapper,diff=plan.render(root/'source');f.require(f.encode(static)==f.encode(report['static_plan']) and f.encode(static)==a.read(root/'work/integration-plan.json'),'static integration evidence differs')
    f.require(wrapper==a.read(root/'work/generated'/plan.TARGET) and diff==a.read(root/'work/readonly-adapter.diff') and report['readonly_adapter_sha256']==f.sha(wrapper) and report['readonly_diff_sha256']==f.sha(diff),'static adapter derivation differs')
    f.require(report['model_cases']==57 and set(report['semantic'])==set(previous.materials.CASES)|set(VARIANTS),'job link case inventory differs')
    for label,row in report['semantic'].items():
        checked=read_case(root/'work/cases'/label,row['expected_sha256']);f.require(f.encode(checked)==f.encode(row['result']) and f.encode(checked)==a.read(root/'work/cases'/label/'analysis.json'),'saved job link verdict differs')
    f.require(all(report[k] is False for k in FALSE),'job link claims authority');return report


def run(output):
    import audit_a23_pinned_view as old
    w=old.w;output=a.canonical(output);f.require(not output.exists(),'new job link review required');frozen=sources();output.mkdir(mode=0o700)
    for n,h in frozen.items():
        raw=w.plain(w.b.REPO/n);f.require(f.sha(raw)==h,'job link source drift');a.put(output,'source/'+n,raw)
    parent=f.load(w.A/PARENT/'closeout.json');review=Path(parent['references']['review']['directory']);previous.verify(review,SOURCE_REVIEW_SUM)
    context=w.A/lineage.PARENT;w.card.seal_verify(context);f.require(f.sha(w.plain(context/'SHA256SUMS'))==lineage.PARENT_SUM,'historical context closeout pin differs')
    ref=f.load(context/'closeout.json')['references']['review'];f.require(ref['manifest_sha256']==JOB_REVIEW_SUM,'historical context reference differs')
    job=extract_job(Path(ref['directory']))
    for n,v in job.items():a.put(output,'inputs/job/'+n,v)
    for name in previous.materials.CASES:
        source=review/'work'/name
        for n in ('observation.json','stdout.bin','stderr.bin'):a.put(output,'inputs/supervisor/'+name+'/'+n,a.read(source/n))
        for n,v in cache(source/'materials').items():a.put(output,'inputs/supervisor/'+name+'/materials/'+n,v)
    for n,v in cache(review/'inputs').items():a.put(output,'inputs/seeds/'+n,v)
    a.put(output,'inputs/provenance.json',f.encode(dict(job_review=ref,supervisor_review=parent['references']['review'],full_cached_job_checks_passed=True,declared_cross_model=True,same_job_execution_proven=False)))
    try:result=exercise(output/'source',output/'inputs',output/'work')
    except Exception as exc:a.put(output,'failure.json',f.encode(dict(error=str(exc),source_hashes=frozen,scope='read-only-cached-job-correspondence')));seal(output);raise
    f.require(sources()==frozen,'job link source drift after exercise')
    a.put(output,'results.json',f.encode(result));a.put(output,'audit.json',f.encode(dict(passed=True,source_count=507,prior_sources_unchanged=503,source_hashes=frozen)))
    seal(output);return dict(passed=True,review_sha256=f.sha(a.read(output/'SHA256SUMS')),model_cases=57)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--output',type=Path);g.add_argument('--check',type=Path);p.add_argument('--expected-sha256');args=p.parse_args()
    if args.check and not args.expected_sha256:p.error('--check requires --expected-sha256')
    try:r=run(args.output) if args.output else verify(args.check,args.expected_sha256)
    except (ValueError,OSError,KeyError,TypeError,subprocess.SubprocessError) as exc:print(json.dumps(dict(passed=False,error=str(exc))));raise SystemExit(2)
    print(json.dumps(r if args.output else dict(passed=True,model_cases=r['model_cases'],process_execution=False),indent=2))
