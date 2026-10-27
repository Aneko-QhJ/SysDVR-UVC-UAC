"""Offline one-shot fixture launch binding; check mode never launches a process."""
from pathlib import Path
import argparse,copy,json,secrets,shutil,subprocess,tempfile,uuid
import a23_fixture_job_binding as model
import a23_fixture_job_launcher as launcher
import audit_a23_supervisor_job_link as previous
f,a=previous.f,previous.a
BASE=previous.BASE
PARENT='A23-supervisor-job-link-closeout-20261020'
PARENT_SUM='2f6867c81d1c20a86801607873e1c9cb12ee0f0df93ede9b6f9f9c8cac3ed171'
SOURCE_REVIEW_SUM='7cfc2caf4011b67fc782785c7fa633e1e2ee5ea771d667f012fa5889e1b3a711'
NEW=('tools/a23_fixture_job_binding.py','tools/a23_fixture_job_launcher.py','tests/a23_job_launch_fixture.py',
     'tools/audit_a23_fixture_job_binding.py','tests/test_a23_fixture_job_binding.py')
FALSE={**previous.FALSE,**model.FALSE}
seal,sealed,reference,cache=previous.seal,previous.sealed,previous.reference,previous.cache
PREFLIGHT=('bad-pin','bad-fixture','bad-seed','preexisting-result')
MUTANTS=('receipt-job','receipt-nonce','receipt-launch','receipt-attempt','receipt-stdout','receipt-files','receipt-authority','receipt-extra',
    'attempt-number-bool','attempt-number-two','attempt-spent','attempt-job','observation-launch','observation-attempt','observation-mode',
    'observation-unreaped','observation-close','output-splice','complete-transplant','material-splice')


def sources():
    import audit_a23_pinned_view as old
    w=old.w;root=w.A/PARENT;w.card.seal_verify(root);f.require(f.sha(w.plain(root/'SHA256SUMS'))==PARENT_SUM,'parent pin differs')
    saved=w.load(root/'closeout.json');out=previous.sources();f.require(out==saved['source_hashes'] and len(out)==507,'prior507 drift')
    for name in NEW:
        key=BASE+name;f.require(key not in out,'source overlap');out[key]=f.sha(w.plain(w.ROOT/name))
    return dict(sorted(out.items()))


def prepare(stage,script,mode,seed):
    stage.mkdir(mode=0o700)
    raw=model.encode(model.manifest(str(uuid.uuid4()),secrets.token_hex(32),mode,f.sha(a.read(script)),SOURCE_REVIEW_SUM,seed))
    a.put(stage,'launch.json',raw)
    for n,v in seed.items():a.put(stage,'inputs/'+n,v)
    return f.sha(raw)


def args_at(directory,pin):
    return [a.read(directory/'launch.json'),pin,a.read(directory/'launch-attempt.json'),f.load(directory/'observation.json'),
        a.read(directory/'stdout.bin'),a.read(directory/'stderr.bin'),cache(directory/'result/materials') if (directory/'result/materials').exists() else {},
        a.read(directory/'result/receipt.json') if (directory/'result/receipt.json').exists() else b'']


def mutation(name,normal,other):
    args=copy.deepcopy(normal)
    def change(index,fn):v=model.parse(args[index]);fn(v);args[index]=model.encode(v)
    key={'receipt-job':'fixture_job_id','receipt-nonce':'launch_nonce','receipt-launch':'launch_sha256','receipt-attempt':'attempt_sha256','receipt-stdout':'stdout_sha256'}
    if name in key:change(7,lambda v:v.update({key[name]:'0'*64}))
    if name=='receipt-files':change(7,lambda v:v.update(material_files={}))
    if name=='receipt-authority':change(7,lambda v:v.update(production_execution_authorized=True))
    if name=='receipt-extra':change(7,lambda v:v.update(allow_retry=True))
    if name=='attempt-number-bool':change(2,lambda v:v.update(attempt_number=True))
    if name=='attempt-number-two':change(2,lambda v:v.update(attempt_number=2))
    if name=='attempt-spent':change(2,lambda v:v.update(spent_before_spawn=False))
    if name=='attempt-job':change(2,lambda v:v.update(fixture_job_id='00000000-0000-0000-0000-000000000001'))
    if name=='observation-launch':args[3]['launch_sha256']='0'*64
    if name=='observation-attempt':args[3]['attempt_sha256']='0'*64
    if name=='observation-mode':args[3]['fixture_mode']='abnormal-exit'
    if name=='observation-unreaped':args[3]['supervisor'].update(reaped=False,returncode=None)
    if name=='observation-close':args[3]['supervisor'].update(close_errors=['stdout'],close_completed=['selector','stderr'])
    if name=='output-splice':args[4]=other[4];args[3]['supervisor']['stdout_bytes']=len(args[4])
    if name=='complete-transplant':args[2:]=copy.deepcopy(other[2:])
    if name=='material-splice':args[6]['result.json']=b'{}'
    return args


def semantic(result):return {k:v for k,v in result.items() if k!='fixture_job_id'}


def exercise(source,inputs,output):
    output.mkdir(mode=0o700);seed=cache(inputs/'seed');stage=Path(tempfile.mkdtemp(prefix='a23-fixture-job-',dir='/private/tmp'))
    script=stage/'a23_job_launch_fixture.py';a.put(stage,script.name,a.read(source/BASE/'tests'/script.name));fixture_pin=f.sha(a.read(script))
    rows={};pins={};retries={};observations={};harness={}
    for name in model.MODES:
        job=stage/name;pin=prepare(job,script,name,seed);pins[name]=pin
        observed,out,err,owned=launcher.run(script,job,pin,fixture_pin)
        h=launcher.harness_finish(owned,observed);harness[name]=h;observations[name]=observed
        # Retained marker must stop another call before any process API.
        marker=a.read(job/'launch-attempt.json')
        try:launcher.run(script,job,pin,fixture_pin)
        except FileExistsError:retries[name]='refused_spent_fixture_attempt'
        else:raise ValueError('fixture retry allowed')
        f.require(a.read(job/'launch-attempt.json')==marker,'attempt marker changed')
        directory=output/'cases'/name;shutil.copytree(job,directory)
        for n,raw in (('observation.json',f.encode(observed)),('harness.json',f.encode(h)),('stdout.bin',out),('stderr.bin',err)):a.put(directory,n,raw)
        result=model.assess(*args_at(directory,pin));f.require(result['fixture_completion'] is (name=='normal'),'fixture admission differs '+name)
        f.require(h['direct_child_reaped'] is (name!='spawn-error') and not h['rescue_used'],'fixture cleanup needs rescue')
        f.require(all(result[k] is False for k in model.FALSE),'fixture grants authority')
        rows[name]=semantic(result);a.put(directory,'analysis.json',f.encode(result))
    preflight={}
    for name in PREFLIGHT:
        job=stage/name;pin=prepare(job,script,'normal',seed);fp=fixture_pin
        if name=='bad-pin':pin='0'*64
        if name=='bad-fixture':fp='0'*64
        if name=='bad-seed':(job/'inputs/result.json').write_bytes(b'{}')
        if name=='preexisting-result':(job/'result').mkdir()
        try:launcher.run(script,job,pin,fp)
        except ValueError as exc:message=str(exc)
        else:raise ValueError('preflight accepted '+name)
        marker=a.read(job/'launch-attempt.json')
        try:launcher.run(script,job,pin,fp)
        except FileExistsError:pass
        else:raise ValueError('preflight retry accepted')
        f.require(a.read(job/'launch-attempt.json')==marker,'preflight marker changed')
        shutil.copytree(job,output/'preflight'/name);preflight[name]=dict(rejected=True,attempt_retained=True,retry_refused=True,error=message)
    normal=args_at(output/'cases/normal',pins['normal']);other=args_at(output/'cases/abnormal-exit',pins['abnormal-exit']);mutants={}
    for name in MUTANTS:
        r=model.assess(*mutation(name,normal,other));f.require(not r['fixture_completion'] and bool(r['errors']),'mutation accepted '+name);mutants[name]=semantic(r)
    return dict(passed=True,model_cases=34,launch_cases=len(rows),preflight_cases=preflight,mutations=mutants,
        semantic=rows,launch_pins=pins,retries=retries,observations=observations,harness=harness,fixture_sha256=fixture_pin,
        staging_directory=str(stage),python_fixture_direct_children=9,candidate_direct_reaps=9,harness_rescue_reaps=0,
        forked_pipe_holders=0,native_compiler_jobs=0,real_sdk_objects=0,usb_requests=0,sd_accesses=0,
        formal_records=0,formal_reservations=0,authorization_consumptions=0,permit_claim_invocations=0,
        fixture_jobs_created=14,**FALSE)


def verify(root,pin):
    root=a.canonical(root);_,_,digest=sealed(root);f.require(f.hex64(pin) and pin==digest,'external review pin differs')
    audit=f.load(root/'audit.json');r=f.load(root/'results.json')
    f.require(audit['source_count']==512 and audit['prior_sources_unchanged']==507 and len(audit['source_hashes'])==512,'fixture source inventory differs')
    for n,h in audit['source_hashes'].items():f.require(f.sha(a.read(root/'source'/n))==h,'frozen fixture source differs')
    f.require(r['fixture_sha256']==f.sha(a.read(root/'source'/BASE/'tests/a23_job_launch_fixture.py')),'fixture pin differs')
    f.require(set(r['semantic'])==set(model.MODES) and set(r['mutations'])==set(MUTANTS) and set(r['preflight_cases'])==set(PREFLIGHT),'fixture cases differ')
    for name in model.MODES:
        directory=root/'work/cases'/name;args=args_at(directory,r['launch_pins'][name]);checked=model.assess(*args)
        f.require(semantic(checked)==r['semantic'][name] and f.encode(checked)==a.read(directory/'analysis.json'),'fixture saved verdict differs')
        f.require(args[3]==r['observations'][name] and f.load(directory/'harness.json')==r['harness'][name],'fixture observation differs')
        f.require(r['retries'][name]=='refused_spent_fixture_attempt','retry receipt differs')
    for name in PREFLIGHT:
        directory=root/'work/preflight'/name
        f.require(f.load(directory/'launch-attempt.json')==model.attempt(a.read(directory/'launch.json')),'preflight attempt differs')
    normal=args_at(root/'work/cases/normal',r['launch_pins']['normal']);other=args_at(root/'work/cases/abnormal-exit',r['launch_pins']['abnormal-exit'])
    for name in MUTANTS:f.require(semantic(model.assess(*mutation(name,normal,other)))==r['mutations'][name],'fixture mutation verdict differs')
    f.require(all(r[k] is False for k in FALSE),'fixture report grants authority');return r


def run(output):
    import audit_a23_pinned_view as old
    w=old.w;output=a.canonical(output);f.require(not output.exists(),'new fixture review required');frozen=sources();output.mkdir(mode=0o700)
    for n,h in frozen.items():
        raw=w.plain(w.b.REPO/n);f.require(f.sha(raw)==h,'fixture source drift');a.put(output,'source/'+n,raw)
    parent=f.load(w.A/PARENT/'closeout.json');review=Path(parent['references']['review']['directory']);previous.verify(review,SOURCE_REVIEW_SUM)
    for n,v in cache(review/'inputs/seeds/normal').items():a.put(output,'inputs/seed/'+n,v)
    a.put(output,'inputs/provenance.json',f.encode(dict(source_review=parent['references']['review'],cached_sdk_materials=True,new_sdk_execution=False)))
    try:r=exercise(output/'source',output/'inputs',output/'work')
    except Exception as exc:a.put(output,'failure.json',f.encode(dict(error=str(exc),source_hashes=frozen,scope='fixed-python-fixture-only')));seal(output);raise
    f.require(sources()==frozen,'fixture sources drift after exercise')
    a.put(output,'results.json',f.encode(r));a.put(output,'audit.json',f.encode(dict(passed=True,source_count=512,prior_sources_unchanged=507,source_hashes=frozen)))
    seal(output);return dict(passed=True,review_sha256=f.sha(a.read(output/'SHA256SUMS')),model_cases=34)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--output',type=Path);g.add_argument('--check',type=Path);p.add_argument('--expected-sha256');args=p.parse_args()
    if args.check and not args.expected_sha256:p.error('--check requires --expected-sha256')
    try:r=run(args.output) if args.output else verify(args.check,args.expected_sha256)
    except (ValueError,OSError,KeyError,TypeError,subprocess.SubprocessError) as exc:print(json.dumps(dict(passed=False,error=str(exc))));raise SystemExit(2)
    print(json.dumps(r if args.output else dict(passed=True,model_cases=r['model_cases'],process_execution=False),indent=2))
