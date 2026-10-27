"""Full isolated driver schedules for specified worker failures and collection."""
from pathlib import Path
from fractions import Fraction
import argparse,json,subprocess
import a23_driver_worker_failure_model as model
import a23_driver_worker_materials as diagnostics
import audit_a23_commit_concurrency_model as previous
import audit_a23_worker_failure_model as parent_audit
f,a=previous.f,previous.a
BASE=model.BASE
PARENT='A23-worker-failure-model-closeout-20261020'
PARENT_SUM='45830b2feab66328185313d54d67ed920669c8b92e808f82794b26b78c4877e1'
NEW=('tests/a23_driver_worker_failure_fixture.inc','tools/a23_driver_worker_failure_model.py','tools/a23_driver_worker_materials.py','tools/audit_a23_driver_worker_failure_model.py','tests/test_a23_driver_worker_failure_model.py')
NAMES=previous.NAMES+model.CASES
FALSE={**previous.FALSE,'driver_authenticates_worker_health':False,'worker_crash_or_cancel_verified':False,'automatic_odd_store_recovery_implemented':False}
DENY=previous.DENY
command,link_scope,bundle=previous.command,previous.link_scope,previous.bundle



# Only this larger offline review uses 8192 nodes. All other snapshot limits stay.
MAX_REVIEW_NODES=8192

def seal(root):
    files,_=a.snapshot(root,maximum=MAX_REVIEW_NODES)
    f.require('SHA256SUMS' not in files and 'COMMITTED' not in files,'already sealed')
    raw=a.sums(files);a.put(root,'SHA256SUMS',raw)
    for p in sorted((p for p in root.rglob('*') if p.is_dir()),key=lambda p:len(p.parts),reverse=True):a.f.sync(p)
    a.f.sync(root);a.put(root,'COMMITTED',(f.sha(raw)+'\n').encode());a.f.sync(root);a.f.sync(root.parent)


def sealed(root):
    files,dirs=a.snapshot(root,maximum=MAX_REVIEW_NODES);raw=files.pop('SHA256SUMS',None);commit=files.pop('COMMITTED',None)
    f.require(raw is not None and commit==(f.sha(raw)+'\n').encode() and raw==a.sums(files),'archive seal differs')
    return files,dirs,f.sha(raw)


def reference(root):
    files,_,digest=sealed(root);return dict(directory=str(root),manifest_sha256=digest,entries=len(files))


def sources():
    import audit_a23_pinned_view as old
    w=old.w;root=w.A/PARENT;w.card.seal_verify(root)
    f.require(f.sha(w.plain(root/'SHA256SUMS'))==PARENT_SUM,'parent pin differs')
    saved=w.load(root/'closeout.json');out=parent_audit.sources()
    f.require(out==saved['source_hashes'] and len(out)==483,'prior483 drift')
    for name in NEW:
        key=BASE+name;f.require(key not in out,'source overlap');out[key]=f.sha(w.plain(w.ROOT/name))
    return dict(sorted(out.items()))


def cache(directory):return {p.relative_to(directory).as_posix():a.read(p) for p in directory.rglob('*') if p.is_file()}


def analyze(root,result):
    f.require(result['case_count']==len(NAMES) and set(result['cases'])==set(NAMES),'worker driver cases differ')
    base={**result,'case_count':len(previous.NAMES),'cases':{n:result['cases'][n] for n in previous.NAMES}}
    semantic=previous.analyze(root,base)
    for name in model.CASES:semantic[name]=diagnostics.validate(name,result['cases'][name],cache(root/name))
    f.require(all(not semantic[n]['completion_admitted'] for n in model.CASES),'worker completion admitted')
    return semantic


def exercise(source,output):
    output.mkdir(mode=0o700);generated=model.render(source)
    original=a.read(source/model.DRIVER);a.put(output,'driver-versioned.diff',model.diff(original,generated[model.DRIVER]))
    for name,raw in generated.items():a.put(output,'generated/'+name,raw)
    root=output/'generated'/BASE;host=root/'host';build=output/'build';build.mkdir();builds={};replays={}
    native=sorted(str(p) for p in host.glob('*.m'))+[str(root/'tests/model_main.m')]
    f.require(len(native)==8,'model translation-unit scope differs')
    for mode in ('optimized','ubsan'):
        flags=['-Wall','-Wextra','-Werror','-O2']
        if mode=='ubsan':flags+=['-fsanitize=undefined','-fno-sanitize-recover=all']
        obj=build/('clock-'+mode+'.o');binary=build/('isolated-driver-'+mode)
        ccmd=['/usr/bin/clang','-std=c11',*flags,'-I',str(host),'-c',str(host/'a23_clock_candidate.c'),'-o',str(obj)]
        f.require(command(ccmd)==b'','compiler output differs')
        versionobj=build/('versioned-'+mode+'.o')
        vcmd=['/usr/bin/clang','-std=c11',*flags,'-I',str(host),'-c',str(host/'a23_versioned_clock_candidate.c'),'-o',str(versionobj)]
        f.require(command(vcmd)==b'','versioned compiler output differs')
        cmd=['/usr/bin/clang','-fobjc-arc','-fblocks',*flags,'-I',str(host),*native,str(obj),str(versionobj),'-framework','Foundation','-o',str(binary)]
        f.require(command(cmd)==b'','compiler output differs')
        scope=output/('scope-'+mode);scope.mkdir();reports=link_scope(binary,scope)
        fixtures=output/('models-'+mode);fixtures.mkdir()
        child=subprocess.run([str(binary),str(fixtures)],capture_output=True,timeout=60)
        a.put(output,'stdout-'+mode+'.json',child.stdout);a.put(output,'stderr-'+mode+'.txt',child.stderr)
        f.require(child.returncode==0 and child.stderr==b'','isolated model failed '+str(child.returncode)+' '+child.stderr.decode(errors='replace'))
        result=f.parse(child.stdout)
        for name in model.CASES:a.put(fixtures/name,'worker-materials.json',diagnostics.contract(name,cache(fixtures/name)))
        replays[mode]=analyze(fixtures,result)
        invalid=subprocess.run([str(binary)],capture_output=True,timeout=10)
        f.require(invalid.returncode==2 and invalid.stdout==invalid.stderr==b'','unexpected entry accepted')
        builds[mode]=dict(command=cmd,c_helper_command=ccmd,versioned_helper_command=vcmd,binary_sha256=f.sha(a.read(binary)),link_scope=reports)
    f.require(f.encode(replays['optimized'])==f.encode(replays['ubsan']),'optimized/UBSan model differs')
    return dict(passed=True,generated_sha256={k:f.sha(v) for k,v in generated.items()},builds=builds,model_cases=len(NAMES),
                semantic=replays['optimized'],specified_worker_threads_per_fixture=29,versioned_driver_model_integrated=True,isolated_full_driver_model_executed=True,
                driver_candidate_sha256=f.sha(generated[model.DRIVER]),driver_diff_sha256=f.sha(model.diff(original,generated[model.DRIVER])),
                protected_slice_sha256={k:f.sha(v) for k,v in model.protected(generated[model.DRIVER]).items()},model_process_executions=2,
                native_entry_rejections=2,native_compiler_jobs=6,real_sdk_objects=0,usb_requests=0,sd_accesses=0,**FALSE)


def verify(root,pin):
    root=a.canonical(root);_,_,digest=sealed(root);f.require(f.hex64(pin) and pin==digest,'external review pin differs')
    report=f.load(root/'results.json');audit=f.load(root/'audit.json')
    for name,h in audit['source_hashes'].items():f.require(f.sha(a.read(root/'source'/name))==h,'frozen model source differs')
    generated=model.render(root/'source')
    f.require(a.read(root/'work/driver-versioned.diff')==model.diff(a.read(root/'source'/model.DRIVER),generated[model.DRIVER]),'saved driver diff differs')
    f.require(report['generated_sha256']=={k:f.sha(v) for k,v in generated.items()},'model derivation differs')
    for name,raw in generated.items():f.require(a.read(root/'work/generated'/name)==raw,'generated file differs')
    for mode,row in report['builds'].items():
        f.require(f.sha(a.read(root/'work/build'/('isolated-driver-'+mode)))==row['binary_sha256'],'model binary differs')
        for label,h in row['link_scope'].items():
            raw=a.read(root/'work'/('scope-'+mode)/(label+'.txt'))
            f.require(f.sha(raw)==h and all(token not in raw for token in DENY),'saved model link scope differs')
        result=f.load(root/'work'/('stdout-'+mode+'.json'))
        semantic=analyze(root/'work'/('models-'+mode),result)
        f.require(f.encode(semantic)==f.encode(report['semantic']),'saved model semantics differ')
    f.require(all(report[k] is False for k in FALSE),'model claims authority');return report


def run(output):
    import audit_a23_pinned_view as old
    w=old.w;output=a.canonical(output);f.require(not output.exists(),'new model review required');frozen=sources();output.mkdir(mode=0o700)
    for name,h in frozen.items():
        raw=w.plain(w.b.REPO/name);f.require(f.sha(raw)==h,'source drift');a.put(output,'source/'+name,raw)
    try:result=exercise(output/'source',output/'work')
    except Exception as exc:
        a.put(output,'failure.json',f.encode(dict(error=str(exc),source_hashes=frozen,scope='isolated-model-only')));seal(output);raise
    f.require(sources()==frozen,'source drift after model replay')
    a.put(output,'results.json',f.encode(result));a.put(output,'audit.json',f.encode(dict(passed=True,source_count=len(frozen),prior_sources_unchanged=483,source_hashes=frozen)))
    seal(output);return dict(passed=True,review_sha256=f.sha(a.read(output/'SHA256SUMS')),model_cases=len(NAMES))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--output',type=Path);g.add_argument('--check',type=Path);p.add_argument('--expected-sha256');args=p.parse_args()
    if args.check and not args.expected_sha256:p.error('--check requires --expected-sha256')
    try:r=run(args.output) if args.output else verify(args.check,args.expected_sha256)
    except (ValueError,OSError,KeyError,TypeError,subprocess.SubprocessError) as exc:print(json.dumps(dict(passed=False,error=str(exc))));raise SystemExit(2)
    print(json.dumps(r if args.output else dict(passed=True,model_cases=r['model_cases'],native_execution=False),indent=2))
