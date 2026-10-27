"""Replay specified commit/publisher/callback schedules and cached diagnostics."""
from pathlib import Path
from fractions import Fraction
import argparse,json,subprocess
import a23_commit_concurrency_model as model
import a23_concurrent_diagnostics as diagnostics
import audit_a23_versioned_driver_model as previous
f,a=previous.f,previous.a
BASE=model.BASE
PARENT='A23-versioned-driver-model-closeout-20261020'
PARENT_SUM='6a96bba3ac4dabd0955b0b4e0b3a0c0193f89b35ea923c5443a60dc3ab3fcb71'
NEW=('tests/a23_commit_concurrency_fixture.inc','tools/a23_commit_concurrency_model.py','tools/a23_concurrent_diagnostics.py','tools/audit_a23_commit_concurrency_model.py','tests/test_a23_commit_concurrency_model.py')
NAMES=previous.NAMES+model.CASES
FALSE={**previous.FALSE,'specified_schedules_cover_all_interleavings':False,'diagnostic_provenance_authenticated':False}
DENY=previous.DENY
command,link_scope,bundle=previous.command,previous.link_scope,previous.bundle


def sources():
    import audit_a23_pinned_view as old
    w=old.w;root=w.A/PARENT;w.card.seal_verify(root)
    f.require(f.sha(w.plain(root/'SHA256SUMS'))==PARENT_SUM,'parent pin differs')
    saved=w.load(root/'closeout.json');out=previous.sources()
    f.require(out==saved['source_hashes'] and len(out)==474,'prior474 drift')
    for name in NEW:
        key=BASE+name;f.require(key not in out,'source overlap');out[key]=f.sha(w.plain(w.ROOT/name))
    return dict(sorted(out.items()))


def cache(directory):return {p.relative_to(directory).as_posix():a.read(p) for p in directory.rglob('*') if p.is_file()}


def analyze(root,result):
    f.require(result['case_count']==len(NAMES) and set(result['cases'])==set(NAMES),'concurrency cases differ')
    f.require(set(model.CASES)==set(diagnostics.NEW) and set(previous.NAMES)==set(diagnostics.BASE_NAMES),'diagnostic case policy differs')
    base={**result,'case_count':len(previous.NAMES),'cases':{n:result['cases'][n] for n in previous.NAMES}}
    semantic=previous.analyze(root,base)
    for name in model.CASES:
        row=result['cases'][name];state=row['result'];receipt=row['receipt_status'];facts=row['facts'];events=[f.parse(line) for line in a.read(root/name/'session.jsonl').splitlines()];names=[e['event'] for e in events]
        good=name in ('gate-publish','gate-aba','gate-noop','gate-two-publishers')
        f.require(state['complete'] is good and state['stopped'] is (not good) and state['saved_epochs']==2 and state['iso_attempts']==state['trigger_attempts']==2 and state['aborts']==0,'concurrency terminal state differs '+name)
        f.require(names.count('saved')==2 and names.count('epochs_saved')==1 and names.count('observation_complete')==int(name not in ('capture-return-aba','gate-journal-failure')),'concurrent event milestones differ')
        if name=='capture-return-aba' or name.startswith('after-'):f.require('observation_version' in state['failure_reasons'],'concurrent version change did not stop driver')
        if name=='gate-journal-failure':f.require(state['journal_failed'] is True,'concurrent journal failure differs')
        if 'iso' in name or 'control' in name:f.require('invalid_callback_ingress' in state['failure_reasons'],'concurrent callback did not revoke settlement')
        historical=name.startswith('after-')
        f.require(state['observation_complete'] is good and (state['quiet_end_ticks']>0 if good or historical else state['quiet_end_ticks']==0),'concurrent settlement history differs')
        for flag in ('callback_drain_verified','device_trace_verified','hardware_verified','hardware_entry_enabled'):f.require(state[flag] is False,'concurrent model claims '+flag)
        semantic[name]=dict(complete=good,saved_epochs=2,aborts=0,failure_reasons=state['failure_reasons'],facts=facts,version=row['version'],receipt=receipt,events=names,concurrency=row['concurrency'])
    for name in NAMES:
        checked=diagnostics.validate(name,result['cases'][name],cache(root/name));semantic[name]['diagnostics']=checked
    f.require(sum(row.get('concurrency',{}).get('worker_count',0) for row in result['cases'].values())==14,'native worker count differs')
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
        result=f.parse(child.stdout);replays[mode]=analyze(fixtures,result)
        invalid=subprocess.run([str(binary)],capture_output=True,timeout=10)
        f.require(invalid.returncode==2 and invalid.stdout==invalid.stderr==b'','unexpected entry accepted')
        builds[mode]=dict(command=cmd,c_helper_command=ccmd,versioned_helper_command=vcmd,binary_sha256=f.sha(a.read(binary)),link_scope=reports)
    f.require(f.encode(replays['optimized'])==f.encode(replays['ubsan']),'optimized/UBSan model differs')
    return dict(passed=True,generated_sha256={k:f.sha(v) for k,v in generated.items()},builds=builds,model_cases=len(NAMES),
                semantic=replays['optimized'],specified_worker_threads_per_fixture=14,versioned_driver_model_integrated=True,isolated_full_driver_model_executed=True,
                driver_candidate_sha256=f.sha(generated[model.DRIVER]),driver_diff_sha256=f.sha(model.diff(original,generated[model.DRIVER])),
                protected_slice_sha256={k:f.sha(v) for k,v in model.protected(generated[model.DRIVER]).items()},model_process_executions=2,
                native_entry_rejections=2,native_compiler_jobs=6,real_sdk_objects=0,usb_requests=0,sd_accesses=0,**FALSE)


def verify(root,pin):
    root=a.canonical(root);_,_,digest=a.sealed(root);f.require(f.hex64(pin) and pin==digest,'external review pin differs')
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
        a.put(output,'failure.json',f.encode(dict(error=str(exc),source_hashes=frozen,scope='isolated-model-only')));a.seal(output);raise
    f.require(sources()==frozen,'source drift after model replay')
    a.put(output,'results.json',f.encode(result));a.put(output,'audit.json',f.encode(dict(passed=True,source_count=len(frozen),prior_sources_unchanged=474,source_hashes=frozen)))
    a.seal(output);return dict(passed=True,review_sha256=f.sha(a.read(output/'SHA256SUMS')),model_cases=len(NAMES))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--output',type=Path);g.add_argument('--check',type=Path);p.add_argument('--expected-sha256');args=p.parse_args()
    if args.check and not args.expected_sha256:p.error('--check requires --expected-sha256')
    try:r=run(args.output) if args.output else verify(args.check,args.expected_sha256)
    except (ValueError,OSError,KeyError,TypeError,subprocess.SubprocessError) as exc:print(json.dumps(dict(passed=False,error=str(exc))));raise SystemExit(2)
    print(json.dumps(r if args.output else dict(passed=True,model_cases=r['model_cases'],native_execution=False),indent=2))
