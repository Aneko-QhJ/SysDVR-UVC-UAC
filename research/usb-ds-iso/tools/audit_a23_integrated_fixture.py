"""Offline synchronized fixture launcher, publication and cleanup combinations."""
from pathlib import Path
import argparse,copy,json,secrets,shutil,subprocess,tempfile,uuid
import a23_integrated_fixture_materials as model
import a23_integrated_fixture_launcher as launcher
import a23_fixture_publication as publication
import audit_a23_fixture_publication as previous
f,a=previous.f,previous.a
BASE=previous.BASE
PARENT='A23-fixture-publication-closeout-20261021'
PARENT_SUM='8c9bc439221fbac5a8525897622691b75931eceef8719b48539eeee275c5a6d1'
SOURCE_REVIEW_SUM='466e99d97542f40db2238e935da660d5c89e86b83a7ebcd0d1f4a9d3bf28b860'
NEW=('tools/a23_integrated_fixture_io.py','tools/a23_integrated_fixture_materials.py','tools/a23_integrated_fixture_launcher.py',
    'tests/a23_integrated_fixture_worker.py','tools/audit_a23_integrated_fixture.py','tests/test_a23_integrated_fixture.py')
FALSE={**previous.FALSE,**model.FALSE}
seal,sealed,reference,cache=previous.seal,previous.sealed,previous.reference,previous.cache
SPECS={'normal':{},**{'pre-'+x:dict(pre=x) for x in model.io.PRE_FAILURES},'spawn-error':dict(parent='spawn-error'),
    **{'cut-'+x:dict(cut=x) for x in model.io.CHILD_EVENTS},**{'fail-'+x:dict(fail=x) for x in model.io.CHILD_FAILURES},
    **{x:dict(mode=x) for x in model.MODES if x!='normal'},
    **{x:dict(parent=x) for x in ('read-error','stdout-close-error','selector-close-error','wait-error')},
    'partial-and-close':dict(cut='receipt.partial',parent='stdout-close-error'),
    'sync-and-close':dict(fail='receipt.directory_sync',parent='selector-close-error'),
    'exit-and-close':dict(mode='exit-seven',parent='stdout-close-error'),
    'timeout-and-wait':dict(mode='timeout-after-output',parent='wait-error')}
MUTANTS=('use-missing','use-bool','use-plan','attempt-missing','attempt-bool','trace-before-sync','trace-ready-missing',
    'trace-reordered','trace-extra','part-missing','part-diverges','receipt-job','receipt-authority','stdout-splice',
    'materials-missing','observation-plan','observation-attempt','observation-close','observation-unreaped','observation-pre-error')


def sources():
    import audit_a23_pinned_view as old
    w=old.w;root=w.A/PARENT;w.card.seal_verify(root);f.require(f.sha(w.plain(root/'SHA256SUMS'))==PARENT_SUM,'parent pin differs')
    saved=w.load(root/'closeout.json');out=previous.sources();f.require(out==saved['source_hashes'] and len(out)==517,'prior517 drift')
    for n in NEW:
        key=BASE+n;f.require(key not in out,'source overlap');out[key]=f.sha(w.plain(w.ROOT/n))
    return dict(sorted(out.items()))


def prepare(job,script,seed,spec):
    job.mkdir(mode=0o700)
    launch=model.encode(model.binding.manifest(str(uuid.uuid4()),secrets.token_hex(32),'normal',f.sha(a.read(script)),SOURCE_REVIEW_SUM,seed))
    libs={n:f.sha(a.read(script.parent/'lib'/n)) for n in model.LIBRARIES}
    raw=model.encode(model.plan(launch,libs,**spec));a.put(job,'launch.json',launch);a.put(job,'integrated-plan.json',raw)
    for n,v in seed.items():a.put(job,'inputs/'+n,v)
    return f.sha(raw)


def args_at(directory,pin):
    files={n:v for n,v in cache(directory).items() if n not in {'observation.json','stdout.bin','stderr.bin','harness.json','analysis.json','recovery.json'}}
    return [a.read(directory/'integrated-plan.json'),pin,files,a.read(directory/'stdout.bin'),a.read(directory/'stderr.bin'),f.load(directory/'observation.json')]


def semantic(r):
    # A reader failure may kill between stdout write and the final trace append.
    # Keep that raw observation, compare only schedule-independent dispositions.
    return {k:v for k,v in r.items() if k not in ('fixture_job_id','publication_trace_complete')}


def mutation(name,args):
    args=copy.deepcopy(args);files=args[2]
    def change(path,fn):v=model.parse(files[path]);fn(v);files[path]=model.encode(v)
    if name=='use-missing':files.pop('launcher-use.json')
    if name=='use-bool':change('launcher-use.json',lambda v:v.update(maximum_calls=True))
    if name=='use-plan':change('launcher-use.json',lambda v:v.update(plan_sha256='0'*64))
    if name=='attempt-missing':files.pop('launch-attempt.json')
    if name=='attempt-bool':change('launch-attempt.json',lambda v:v.update(attempt_number=True))
    if name.startswith('trace-'):
        rows=[model.parse(v) for v in files['trace.jsonl'].splitlines()]
        if name=='trace-before-sync':rows=[v for v in rows if v['event']!='attempt.parent_directory_sync']
        if name=='trace-ready-missing':rows=[v for v in rows if v['event']!='launch.ready']
        if name=='trace-reordered':rows[6],rows[8]=rows[8],rows[6]
        if name=='trace-extra':rows.append(dict(event='retry',outcome='completed'))
        files['trace.jsonl']=b'\n'.join(model.encode(v) for v in rows)+b'\n'
    if name=='part-missing':files.pop('result/receipt.json.part')
    if name=='part-diverges':files['result/receipt.json.part']=b'{}'
    if name in ('receipt-job','receipt-authority'):
        change('result/receipt.json',lambda v:v.update(fixture_job_id='00000000-0000-0000-0000-000000000001') if name=='receipt-job' else v.update(production_execution_authorized=True))
        files['result/receipt.json.part']=files['result/receipt.json']
    if name=='stdout-splice':args[3]=b'{}';args[5]['supervisor']['stdout_bytes']=2
    if name=='materials-missing':files.pop('result/materials/result.json')
    if name=='observation-plan':args[5]['plan_sha256']='0'*64
    if name=='observation-attempt':args[5]['attempt_sha256']='0'*64
    if name=='observation-close':args[5]['supervisor'].update(close_errors=['stdout'],close_completed=['selector','stderr'])
    if name=='observation-unreaped':args[5]['supervisor'].update(reaped=False,returncode=None)
    if name=='observation-pre-error':args[5]['prelaunch_error']='prelaunch_io_error'
    return args


def exercise(source,inputs,output):
    output.mkdir(mode=0o700);seed=cache(inputs/'seed');stage=Path(tempfile.mkdtemp(prefix='a23-integrated-',dir='/private/tmp'))
    script=stage/'a23_integrated_fixture_worker.py';a.put(stage,script.name,a.read(source/BASE/'tests'/script.name))
    for n in model.LIBRARIES:a.put(stage,'lib/'+n,a.read(source/BASE/'tools'/n))
    fp=f.sha(a.read(script));rows={};pins={};observations={};harness={};recovery={}
    for name,spec in SPECS.items():
        job=stage/name;pin=prepare(job,script,seed,spec);pins[name]=pin
        observed,out,err,owned=launcher.run(script,job,pin,fp);h=launcher.harness_finish(owned,observed)
        before=cache(job)
        try:launcher.run(script,job,pin,fp)
        except FileExistsError:pass
        else:raise ValueError('integrated fixture retry accepted')
        try:publication.recover(job)
        except ValueError:pass
        else:raise ValueError('integrated fixture recovery accepted')
        f.require(cache(job)==before,'integrated retry/recovery modified evidence')
        directory=output/'cases'/name;shutil.copytree(job,directory)
        for n,v in (('observation.json',f.encode(observed)),('stdout.bin',out),('stderr.bin',err),('harness.json',f.encode(h))):a.put(directory,n,v)
        checked=model.assess(*args_at(directory,pin));f.require(checked['integrated_model_complete'] is (name=='normal') and checked['publication_prefix_valid'],'integrated admission differs '+name)
        o=observed['supervisor'];spawned=not(name.startswith('pre-') or name=='spawn-error')
        f.require(o['spawned'] is spawned and h['direct_child_reaped'] is spawned,'integrated launch/reap differs')
        f.require(o['reaped'] is (spawned and spec.get('parent')!='wait-error') and h['rescue_used'] is (spawned and spec.get('parent')=='wait-error'),'integrated candidate/rescue reaping differs')
        f.require(all(checked[k] is False for k in model.FALSE),'integrated grants authority')
        rows[name]=semantic(checked);observations[name]=observed;harness[name]=h
        recovery[name]=dict(retry_refused=True,recovery_refused=True,evidence_unchanged=True)
        a.put(directory,'analysis.json',f.encode(checked));a.put(directory,'recovery.json',f.encode(recovery[name]))
    args=args_at(output/'cases/normal',pins['normal']);mutants={}
    for name in MUTANTS:
        r=model.assess(*mutation(name,args));f.require(not r['integrated_model_complete'] and bool(r['errors']),'integrated mutation accepted '+name);mutants[name]=semantic(r)
    return dict(passed=True,model_cases=51,launch_cases=31,semantic=rows,mutations=mutants,plan_pins=pins,
        observations=observations,harness=harness,recovery=recovery,fixture_sha256=fp,
        library_sha256={n:f.sha(a.read(script.parent/'lib'/n)) for n in model.LIBRARIES},staging_directory=str(stage),
        python_fixture_direct_children=sum(v['supervisor']['launches'] for v in observations.values()),
        candidate_direct_reaps=sum(v['supervisor']['reaped'] for v in observations.values()),
        harness_rescue_reaps=sum(v['rescue_used'] for v in harness.values()),
        parent_resource_rescues=sum(len(v['resource_rescues']) for v in harness.values()),fixture_jobs_created=31,
        native_compiler_jobs=0,real_sdk_objects=0,usb_requests=0,sd_accesses=0,formal_records=0,formal_reservations=0,
        authorization_consumptions=0,permit_claim_invocations=0,production_launcher_integrated=False,**FALSE)


def verify(root,pin):
    root=a.canonical(root);_,_,digest=sealed(root);f.require(f.hex64(pin) and pin==digest,'external review pin differs')
    audit=f.load(root/'audit.json');r=f.load(root/'results.json')
    f.require(audit['source_count']==523 and audit['prior_sources_unchanged']==517 and len(audit['source_hashes'])==523,'integrated source inventory differs')
    for n,h in audit['source_hashes'].items():f.require(f.sha(a.read(root/'source'/n))==h,'frozen integrated source differs')
    f.require(r['fixture_sha256']==f.sha(a.read(root/'source'/BASE/'tests/a23_integrated_fixture_worker.py')),'integrated worker differs')
    for n,h in r['library_sha256'].items():f.require(h==f.sha(a.read(root/'source'/BASE/'tools'/n)),'integrated worker library differs')
    f.require(set(r['semantic'])==set(SPECS) and set(r['mutations'])==set(MUTANTS),'integrated case inventory differs')
    for name in SPECS:
        directory=root/'work/cases'/name;checked=model.assess(*args_at(directory,r['plan_pins'][name]))
        f.require(semantic(checked)==r['semantic'][name] and f.encode(checked)==a.read(directory/'analysis.json'),'saved integrated verdict differs')
        f.require(f.load(directory/'observation.json')==r['observations'][name] and f.load(directory/'harness.json')==r['harness'][name] and f.load(directory/'recovery.json')==r['recovery'][name],'saved integrated observations differ')
    args=args_at(root/'work/cases/normal',r['plan_pins']['normal'])
    for name in MUTANTS:f.require(semantic(model.assess(*mutation(name,args)))==r['mutations'][name],'saved integrated mutation differs')
    f.require(all(r[k] is False for k in FALSE),'integrated claims authority');return r


def run(output):
    import audit_a23_pinned_view as old
    w=old.w;output=a.canonical(output);f.require(not output.exists(),'new integrated review required');frozen=sources();output.mkdir(mode=0o700)
    for n,h in frozen.items():
        raw=w.plain(w.b.REPO/n);f.require(f.sha(raw)==h,'integrated source drift');a.put(output,'source/'+n,raw)
    parent=f.load(w.A/PARENT/'closeout.json');review=Path(parent['references']['review']['directory']);previous.verify(review,SOURCE_REVIEW_SUM)
    for n,v in cache(review/'inputs/seed').items():a.put(output,'inputs/seed/'+n,v)
    a.put(output,'inputs/provenance.json',f.encode(dict(source_review=parent['references']['review'],cached_sdk_materials=True,new_sdk_execution=False)))
    try:r=exercise(output/'source',output/'inputs',output/'work')
    except Exception as exc:a.put(output,'failure.json',f.encode(dict(error=str(exc),source_hashes=frozen,scope='fixed-integrated-fixture-only')));seal(output);raise
    f.require(sources()==frozen,'integrated source drift after exercise')
    a.put(output,'results.json',f.encode(r));a.put(output,'audit.json',f.encode(dict(passed=True,source_count=523,prior_sources_unchanged=517,source_hashes=frozen)))
    seal(output);return dict(passed=True,review_sha256=f.sha(a.read(output/'SHA256SUMS')),model_cases=51)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--output',type=Path);g.add_argument('--check',type=Path);p.add_argument('--expected-sha256');args=p.parse_args()
    if args.check and not args.expected_sha256:p.error('--check requires --expected-sha256')
    try:r=run(args.output) if args.output else verify(args.check,args.expected_sha256)
    except (ValueError,OSError,KeyError,TypeError,subprocess.SubprocessError) as exc:print(json.dumps(dict(passed=False,error=str(exc))));raise SystemExit(2)
    print(json.dumps(r if args.output else dict(passed=True,model_cases=r['model_cases'],process_execution=False),indent=2))
