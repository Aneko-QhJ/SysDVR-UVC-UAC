"""Audit interrupted file publication in fixed offline fixture processes."""
from pathlib import Path
import argparse,copy,json,secrets,shutil,subprocess,sys,tempfile,uuid
import a23_fixture_publication as publication
import a23_fixture_recovery as model
import audit_a23_fixture_job_binding as previous
f,a=previous.f,previous.a
BASE=previous.BASE
PARENT='A23-fixture-job-binding-closeout-20261021'
PARENT_SUM='5edc9d426d30a6713faee71abaef9788acdd18b66349ac92a1e0e65e29a79582'
SOURCE_REVIEW_SUM='0d7c2b6bd3b8ce5a0547330dbfd12faa9b8b9d3df396d556f680ffb8a406c31d'
NEW=('tools/a23_fixture_publication.py','tools/a23_fixture_recovery.py','tests/a23_fixture_publication_worker.py',
    'tools/audit_a23_fixture_publication.py','tests/test_a23_fixture_publication.py')
FALSE={**previous.FALSE,**model.FALSE}
seal,sealed,reference,cache=previous.seal,previous.sealed,previous.reference,previous.cache
CASES=('normal',)+tuple('cut-'+x for x in publication.EVENTS)+tuple('fail-'+x for x in publication.FAILURES)
MUTANTS=('trace-missing','trace-reordered','trace-spliced','trace-extra','attempt-missing','attempt-bool',
    'attempt-partial','part-missing','part-diverges','receipt-missing','receipt-job','receipt-promoted',
    'output-missing','materials-missing','observation-unreaped','observation-bool')


def sources():
    import audit_a23_pinned_view as old
    w=old.w;root=w.A/PARENT;w.card.seal_verify(root);f.require(f.sha(w.plain(root/'SHA256SUMS'))==PARENT_SUM,'parent pin differs')
    saved=w.load(root/'closeout.json');out=previous.sources();f.require(out==saved['source_hashes'] and len(out)==512,'prior512 drift')
    for n in NEW:
        key=BASE+n;f.require(key not in out,'source overlap');out[key]=f.sha(w.plain(w.ROOT/n))
    return dict(sorted(out.items()))


def prepare(job,script,module,seed,name):
    job.mkdir(mode=0o700)
    launch=model.binding.encode(model.binding.manifest(str(uuid.uuid4()),secrets.token_hex(32),'normal',f.sha(a.read(script)),SOURCE_REVIEW_SUM,seed))
    cut=name.removeprefix('cut-') if name.startswith('cut-') else None
    fail=name.removeprefix('fail-') if name.startswith('fail-') else None
    p=model.encode(model.plan(launch,f.sha(a.read(module)),cut,fail))
    a.put(job,'launch.json',launch);a.put(job,'publication-plan.json',p)
    for n,v in seed.items():a.put(job,'inputs/'+n,v)
    return f.sha(p)


def args_at(directory,pin):
    files={n:v for n,v in cache(directory).items() if n not in {'observation.json','stdout.bin','stderr.bin','analysis.json','recovery.json'}}
    return [a.read(directory/'publication-plan.json'),pin,files,a.read(directory/'stdout.bin'),a.read(directory/'stderr.bin'),f.load(directory/'observation.json')]


def semantic(r):return {k:v for k,v in r.items() if k!='fixture_job_id'}


def mutation(name,args):
    args=copy.deepcopy(args);files=args[2]
    if name=='trace-missing':files.pop('trace.jsonl')
    if name in ('trace-reordered','trace-spliced','trace-extra'):
        rows=[model.parse(x) for x in files['trace.jsonl'].splitlines()]
        if name=='trace-reordered':rows[4],rows[6]=rows[6],rows[4]
        if name=='trace-spliced':rows.pop(7)
        if name=='trace-extra':rows.append(dict(event='retry',outcome='completed'))
        files['trace.jsonl']=b'\n'.join(model.encode(v) for v in rows)+b'\n'
    if name=='attempt-missing':files.pop('launch-attempt.json')
    if name=='attempt-bool':v=model.parse(files['launch-attempt.json']);v['attempt_number']=True;files['launch-attempt.json']=model.encode(v)
    if name=='attempt-partial':files['launch-attempt.json']=b'{'
    if name=='part-missing':files.pop('result/receipt.json.part')
    if name=='part-diverges':files['result/receipt.json.part']=b'{}'
    if name=='receipt-missing':files.pop('result/receipt.json')
    if name in ('receipt-job','receipt-promoted'):
        v=model.parse(files['result/receipt.json'])
        if name=='receipt-job':v['fixture_job_id']='00000000-0000-0000-0000-000000000001'
        else:v['production_execution_authorized']=True
        files['result/receipt.json']=model.encode(v);files['result/receipt.json.part']=model.encode(v)
    if name=='output-missing':args[3]=b'';args[5]['stdout_bytes']=0
    if name=='materials-missing':files.pop('result/materials/result.json')
    if name=='observation-unreaped':args[5]['reaped']=False
    if name=='observation-bool':args[5]['returncode']=False
    return args


def exercise(source,inputs,output):
    output.mkdir(mode=0o700);seed=cache(inputs/'seed');stage=Path(tempfile.mkdtemp(prefix='a23-publication-',dir='/private/tmp'))
    script=stage/'a23_fixture_publication_worker.py';module=stage/'lib/a23_fixture_publication.py'
    a.put(stage,script.name,a.read(source/BASE/'tests'/script.name));a.put(stage,'lib/'+module.name,a.read(source/BASE/'tools'/module.name))
    rows={};pins={};recovery={}
    for name in CASES:
        job=stage/name;pin=prepare(job,script,module,seed,name);pins[name]=pin
        # Audit harness only: fixed source emits one bounded report, has no forks,
        # and exits at fixed checkpoints. This is not a production supervisor.
        child=subprocess.run([sys.executable,'-I','-B',str(script),str(job)],stdin=subprocess.DEVNULL,
            capture_output=True,timeout=3,env={'PATH':'/usr/bin:/bin','LC_ALL':'C'})
        expected=0 if name=='normal' else 73 if name.startswith('cut-') else 74
        f.require(child.returncode==expected and not child.stderr and len(child.stdout)<=65536,'publication fixture failed '+name)
        observed=model.observation(child.returncode,child.stdout,child.stderr)
        before=cache(job)
        try:publication.recover(job)
        except ValueError:pass
        else:raise ValueError('fixture recovery allowed restart')
        f.require(cache(job)==before,'recovery changed interrupted evidence')
        retry_blocked=None
        if 'launch-attempt.json' in before:
            # Exercise exclusive creation against empty/partial/complete retained
            # markers. No second payload or worker is ever started.
            try:publication.publish(job,b'not a new attempt',{},b'',lambda *_:None)
            except FileExistsError:retry_blocked=True
            else:raise ValueError('retained marker overwrite allowed')
            f.require(cache(job)==before,'retry changed interrupted evidence')
        directory=output/'cases'/name;shutil.copytree(job,directory)
        for n,v in (('observation.json',f.encode(observed)),('stdout.bin',child.stdout),('stderr.bin',child.stderr)):a.put(directory,n,v)
        result=model.assess(*args_at(directory,pin))
        f.require(result['publication_model_complete'] is (name=='normal') and result['trace_prefix_valid'],'publication admission differs '+name)
        f.require(all(result[k] is False for k in model.FALSE),'publication grants authority')
        rows[name]=semantic(result);recovery[name]=dict(restart_refused=True,evidence_unchanged=True,exclusive_reuse_refused=retry_blocked)
        a.put(directory,'analysis.json',f.encode(result));a.put(directory,'recovery.json',f.encode(recovery[name]))
    args=args_at(output/'cases/normal',pins['normal']);mutants={}
    for name in MUTANTS:
        r=model.assess(*mutation(name,args));f.require(not r['publication_model_complete'] and bool(r['errors']),'publication mutation accepted '+name);mutants[name]=semantic(r)
    return dict(passed=True,model_cases=43,publication_cases=27,semantic=rows,mutations=mutants,recovery=recovery,plan_pins=pins,
        fixture_sha256=f.sha(a.read(script)),module_sha256=f.sha(a.read(module)),staging_directory=str(stage),
        python_fixture_direct_children=27,harness_direct_reaps=27,candidate_direct_reaps=0,harness_rescue_reaps=0,fixture_jobs_created=27,
        native_compiler_jobs=0,real_sdk_objects=0,usb_requests=0,sd_accesses=0,formal_records=0,formal_reservations=0,
        authorization_consumptions=0,permit_claim_invocations=0,**FALSE)


def verify(root,pin):
    root=a.canonical(root);_,_,digest=sealed(root);f.require(f.hex64(pin) and pin==digest,'external review pin differs')
    audit=f.load(root/'audit.json');r=f.load(root/'results.json')
    f.require(audit['source_count']==517 and audit['prior_sources_unchanged']==512 and len(audit['source_hashes'])==517,'publication source inventory differs')
    for n,h in audit['source_hashes'].items():f.require(f.sha(a.read(root/'source'/n))==h,'frozen publication source differs')
    for key,path in (('fixture_sha256','tests/a23_fixture_publication_worker.py'),('module_sha256','tools/a23_fixture_publication.py')):f.require(r[key]==f.sha(a.read(root/'source'/BASE/path)),'publication code pin differs')
    f.require(set(r['semantic'])==set(CASES) and set(r['mutations'])==set(MUTANTS),'publication cases differ')
    for name in CASES:
        directory=root/'work/cases'/name;args=args_at(directory,r['plan_pins'][name]);checked=model.assess(*args)
        f.require(semantic(checked)==r['semantic'][name] and f.encode(checked)==a.read(directory/'analysis.json'),'saved publication verdict differs')
        f.require(f.load(directory/'recovery.json')==r['recovery'][name],'saved recovery differs')
    args=args_at(root/'work/cases/normal',r['plan_pins']['normal'])
    for name in MUTANTS:f.require(semantic(model.assess(*mutation(name,args)))==r['mutations'][name],'publication mutation verdict differs')
    f.require(all(r[k] is False for k in FALSE),'publication report grants authority');return r


def run(output):
    import audit_a23_pinned_view as old
    w=old.w;output=a.canonical(output);f.require(not output.exists(),'new publication review required');frozen=sources();output.mkdir(mode=0o700)
    for n,h in frozen.items():
        raw=w.plain(w.b.REPO/n);f.require(f.sha(raw)==h,'publication source drift');a.put(output,'source/'+n,raw)
    parent=f.load(w.A/PARENT/'closeout.json');review=Path(parent['references']['review']['directory']);previous.verify(review,SOURCE_REVIEW_SUM)
    for n,v in cache(review/'inputs/seed').items():a.put(output,'inputs/seed/'+n,v)
    a.put(output,'inputs/provenance.json',f.encode(dict(source_review=parent['references']['review'],cached_sdk_materials=True,new_sdk_execution=False)))
    try:r=exercise(output/'source',output/'inputs',output/'work')
    except Exception as exc:a.put(output,'failure.json',f.encode(dict(error=str(exc),source_hashes=frozen,scope='fixed-publication-fixture-only')));seal(output);raise
    f.require(sources()==frozen,'publication source drift after exercise')
    a.put(output,'results.json',f.encode(r));a.put(output,'audit.json',f.encode(dict(passed=True,source_count=517,prior_sources_unchanged=512,source_hashes=frozen)))
    seal(output);return dict(passed=True,review_sha256=f.sha(a.read(output/'SHA256SUMS')),model_cases=43)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--output',type=Path);g.add_argument('--check',type=Path);p.add_argument('--expected-sha256');args=p.parse_args()
    if args.check and not args.expected_sha256:p.error('--check requires --expected-sha256')
    try:r=run(args.output) if args.output else verify(args.check,args.expected_sha256)
    except (ValueError,OSError,KeyError,TypeError,subprocess.SubprocessError) as exc:print(json.dumps(dict(passed=False,error=str(exc))));raise SystemExit(2)
    print(json.dumps(r if args.output else dict(passed=True,model_cases=r['model_cases'],process_execution=False),indent=2))
