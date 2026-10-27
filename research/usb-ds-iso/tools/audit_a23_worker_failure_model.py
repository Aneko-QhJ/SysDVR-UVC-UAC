"""Standalone C worker failure schedules and strict cached-material admission."""
from pathlib import Path
import argparse,json,subprocess
import a23_worker_failure_materials as materials
import audit_a23_commit_concurrency_model as previous
f,a=previous.f,previous.a
BASE=previous.BASE
PARENT='A23-commit-concurrency-model-closeout-20261020'
PARENT_SUM='55a7337c3df822b7eda3f75b5b6c2df61b7dc87497b1e705fa02061d8ed285a7'
NEW=('tests/a23_worker_failure_fixture.c','tools/a23_worker_failure_materials.py','tools/audit_a23_worker_failure_model.py','tests/test_a23_worker_failure_model.py')
FALSE={**previous.FALSE,'worker_failures_integrated_into_full_driver':False,'worker_cancellation_verified':False,'automatic_odd_store_recovery_implemented':False}


def sources():
    import audit_a23_pinned_view as old
    w=old.w;root=w.A/PARENT;w.card.seal_verify(root)
    f.require(f.sha(w.plain(root/'SHA256SUMS'))==PARENT_SUM,'parent pin differs')
    saved=w.load(root/'closeout.json');out=previous.sources()
    f.require(out==saved['source_hashes'] and len(out)==479,'prior479 drift')
    for name in NEW:
        key=BASE+name;f.require(key not in out,'source overlap');out[key]=f.sha(w.plain(w.ROOT/name))
    return dict(sorted(out.items()))


def validate(result):
    expected=dict(schema='A23-worker-failure-native-1',cases=[materials.expected(n) for n in materials.NAMES],usb_requests=0,sd_accesses=0,real_sdk_objects=0,actual_clock_queries=0)
    f.require(f.encode(result)==f.encode(expected),'specified native worker outcome differs');return result


def collect(output,result,write=False):
    checked={}
    for row in result['cases']:
        name=row['case'];cache=materials.package(row)
        if write:
            for path,raw in cache.items():a.put(output,name+'/'+path,raw)
        else:
            cache=previous.cache(output/name)
        checked[name]=materials.admit(name,cache)
    return checked


def exercise(source,output):
    output.mkdir(mode=0o700);host=source/BASE/'host';fixture=source/BASE/'tests/a23_worker_failure_fixture.c'
    inputs=[host/'a23_clock_candidate.c',host/'a23_versioned_clock_candidate.c',fixture]
    for path in [*inputs,host/'a23_versioned_clock_candidate.h']:
        for token in (b'mach_absolute_time',b'mach_timebase_info',b'IOUSBHost',b'IOServiceOpen',b'A23ReadExecutionContext'):
            f.require(token not in a.read(path),'standalone worker crosses scope')
    build=output/'build';build.mkdir();builds={};results={};checks={}
    for mode in ('optimized','ubsan'):
        binary=build/('worker-failure-'+mode);flags=['-std=c11','-Wall','-Wextra','-Werror','-Wconversion','-Wsign-conversion','-O2']
        if mode=='ubsan':flags+=['-fsanitize=undefined','-fno-sanitize-recover=all']
        command=['/usr/bin/clang',*flags,'-I',str(host),*map(str,inputs),'-o',str(binary)]
        f.require(previous.command(command)==b'','worker compiler output differs')
        scope=output/('scope-'+mode);scope.mkdir();reports=previous.link_scope(binary,scope)
        child=subprocess.run([str(binary)],capture_output=True,timeout=30)
        a.put(output,'stdout-'+mode+'.json',child.stdout);a.put(output,'stderr-'+mode+'.txt',child.stderr)
        f.require(child.returncode==0 and child.stderr==b'','worker fixture failed '+str(child.returncode)+' '+child.stderr.decode(errors='replace'))
        results[mode]=validate(f.parse(child.stdout));checks[mode]=collect(output/('materials-'+mode),results[mode],write=True)
        rejected=subprocess.run([str(binary),'unknown-mode'],capture_output=True,timeout=10)
        f.require(rejected.returncode==2 and rejected.stdout==rejected.stderr==b'','unexpected worker entry accepted')
        builds[mode]=dict(command=command,binary_sha256=f.sha(a.read(binary)),link_scope=reports)
    f.require(f.encode(results['optimized'])==f.encode(results['ubsan']) and f.encode(checks['optimized'])==f.encode(checks['ubsan']),'optimized/UBSan worker differs')
    return dict(passed=True,model_cases=len(materials.NAMES),fixture=results['optimized'],admission=checks['optimized'],builds=builds,
                standalone_fixture_builds=2,native_compiler_jobs=2,fixture_process_executions=2,native_entry_rejections=2,
                specified_worker_threads_per_fixture=len(materials.NAMES),full_sdk_model_executions=0,production_receiver_executions=0,**FALSE)


def verify(root,pin):
    root=a.canonical(root);_,_,digest=a.sealed(root);f.require(f.hex64(pin) and pin==digest,'external review pin differs')
    report=f.load(root/'results.json');audit=f.load(root/'audit.json')
    f.require(audit['source_count']==483 and audit['prior_sources_unchanged']==479 and len(audit['source_hashes'])==483,'worker source inventory differs')
    for name,h in audit['source_hashes'].items():f.require(f.sha(a.read(root/'source'/name))==h,'worker frozen source differs')
    validate(report['fixture']);f.require(set(report['builds'])=={'optimized','ubsan'} and report['model_cases']==13,'worker build inventory differs')
    for mode,row in report['builds'].items():
        f.require(f.sha(a.read(root/'work/build'/('worker-failure-'+mode)))==row['binary_sha256'],'worker binary differs')
        f.require(a.read(root/'work'/('stderr-'+mode+'.txt'))==b'' and f.encode(validate(f.load(root/'work'/('stdout-'+mode+'.json'))))==f.encode(report['fixture']),'saved worker fixture differs')
        f.require(f.encode(collect(root/'work'/('materials-'+mode),report['fixture']))==f.encode(report['admission']),'saved worker admission differs')
        for label,h in row['link_scope'].items():
            raw=a.read(root/'work'/('scope-'+mode)/(label+'.txt'));f.require(f.sha(raw)==h and all(t not in raw for t in previous.DENY),'saved worker scope differs')
    f.require(all(report[k] is False for k in FALSE),'worker model claims authority');return report


def run(output):
    import audit_a23_pinned_view as old
    w=old.w;output=a.canonical(output);f.require(not output.exists(),'new worker review required');frozen=sources();output.mkdir(mode=0o700)
    for name,h in frozen.items():
        raw=w.plain(w.b.REPO/name);f.require(f.sha(raw)==h,'worker source drift');a.put(output,'source/'+name,raw)
    try:result=exercise(output/'source',output/'work')
    except Exception as exc:
        a.put(output,'failure.json',f.encode(dict(error=str(exc),source_hashes=frozen,scope='standalone-worker-only')));a.seal(output);raise
    f.require(sources()==frozen,'worker source drift after exercise')
    a.put(output,'results.json',f.encode(result));a.put(output,'audit.json',f.encode(dict(passed=True,source_count=len(frozen),prior_sources_unchanged=479,source_hashes=frozen)))
    a.seal(output);return dict(passed=True,review_sha256=f.sha(a.read(output/'SHA256SUMS')),model_cases=len(materials.NAMES))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--output',type=Path);g.add_argument('--check',type=Path);p.add_argument('--expected-sha256');args=p.parse_args()
    if args.check and not args.expected_sha256:p.error('--check requires --expected-sha256')
    try:r=run(args.output) if args.output else verify(args.check,args.expected_sha256)
    except (ValueError,OSError,KeyError,TypeError,subprocess.SubprocessError) as exc:print(json.dumps(dict(passed=False,error=str(exc))));raise SystemExit(2)
    print(json.dumps(r if args.output else dict(passed=True,model_cases=r['model_cases'],native_execution=False),indent=2))
