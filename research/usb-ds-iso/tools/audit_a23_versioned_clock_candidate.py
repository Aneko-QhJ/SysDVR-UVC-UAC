"""Independent cooperative versioned profile/ticks candidate; no driver execution."""
from fractions import Fraction
from pathlib import Path
import argparse,json,subprocess
import audit_a23_driver_fault_model as previous
f,a=previous.f,previous.a
BASE=previous.BASE
PARENT='A23-driver-fault-model-closeout-20261020'
PARENT_SUM='e31444b8e8130a4395b5ffb5bc4c4d940d2253b867bf52164c5ece6cbdaa54d7'
NEW=('host/a23_versioned_clock_candidate.h','host/a23_versioned_clock_candidate.c','tests/a23_versioned_clock_fixture.c',
     'tools/audit_a23_versioned_clock_candidate.py','tests/test_a23_versioned_clock_candidate.py')
NAMES=('normal','fractional-short','fractional-equal','fractional-after','zero-tick','backwards','overflow',
       'invalid-domain','invalid-instance','invalid-numerator','invalid-denominator','invalid-incarnation',
       'during-numerator','during-denominator','during-domain','during-instance','start-aba','end-aba',
       'between-aba','between-noop','between-abort','between-numerator','busy-before','busy-during','nested-writer',
       'reader-failure','nil-reader','nil-store','poisoned','zero-generation','last-write','exhaustion','invalid-finish',
       'stale-ticket','wrong-ticket','other-store','other-incarnation','after-end-publish','bypass-aba','bypass-between',
       'thread-start-aba','thread-end-aba','thread-contender')
FALSE={**previous.FALSE,'versioned_driver_integrated':False,'writer_contract_enforced':False,
       'all_writers_participation_authenticated':False,'all_thread_interleavings_verified':False}
U64=2**64-1


def sources():
    import audit_a23_pinned_view as old
    w=old.w;root=w.A/PARENT;w.card.seal_verify(root)
    f.require(f.sha(w.plain(root/'SHA256SUMS'))==PARENT_SUM,'parent pin differs')
    saved=w.load(root/'closeout.json');out=previous.sources()
    f.require(out==saved['source_hashes'] and len(out)==462,'prior462 drift')
    for name in NEW:
        key=BASE+name;f.require(key not in out,'source overlap');out[key]=f.sha(w.plain(w.ROOT/name))
    return dict(sorted(out.items()))


def oracle(name):
    f.require(name in NAMES,'unknown versioned case')
    row=dict(init=0,preflight=0,begin=0,end=0,evaluate=0,rounded_ns=250000000,minimum_met=True,
             reads=2,mutations=0,threads=0,writer_status=0,generation=2,poisoned=False,
             begin_generation=2,end_generation=2,begin_zeroed=False,end_zeroed=False)
    if name.startswith('fractional-'):
        ticks={'fractional-short':374999999,'fractional-equal':375000000,'fractional-after':375000001}[name]
        ns=Fraction(ticks*2,3);row.update(rounded_ns=(ns.numerator+ns.denominator-1)//ns.denominator,minimum_met=ns>=250000000)
    if name=='backwards':row['evaluate']=5
    if name=='overflow':row['evaluate']=6
    if name.startswith('invalid-') and name!='invalid-finish':
        row.update(init=2,preflight=5,begin=5,end=5,evaluate=1,reads=0,generation=0,poisoned=True)
    if name in ('during-numerator','during-denominator','during-instance'):
        row.update(end=4,evaluate=1,mutations=1,generation=4)
    if name=='during-domain':row.update(end=5,evaluate=1,mutations=1,generation=4,writer_status=2,poisoned=True)
    if name in ('start-aba','thread-start-aba'):row.update(begin=4,evaluate=1,mutations=2,generation=6,end_generation=6)
    if name in ('end-aba','thread-end-aba'):row.update(end=4,evaluate=1,mutations=2,generation=6)
    if name.startswith('thread-'):row['threads']=1
    if name in ('between-aba','between-noop','between-abort','between-numerator','stale-ticket','wrong-ticket'):
        gen=6 if name=='between-aba' else 4
        row.update(evaluate=4,mutations=2 if name=='between-aba' else 1,generation=gen,end_generation=gen)
        if name in ('stale-ticket','wrong-ticket'):row['writer_status']=4
    if name=='busy-before':row.update(begin=3,evaluate=1,reads=1,mutations=1,generation=4,end_generation=4)
    if name in ('busy-during','nested-writer','thread-contender'):
        row.update(end=4,evaluate=1,mutations=1,generation=4)
        if name!='busy-during':row['writer_status']=3
    if name=='reader-failure':row.update(end=7,evaluate=1)
    if name in ('nil-reader','nil-store'):row.update(end=1,evaluate=1,reads=1)
    if name in ('poisoned','zero-generation','exhaustion','invalid-finish'):
        row.update(end=5,evaluate=1,reads=1)
        if name!='zero-generation':row['poisoned']=True
        if name=='zero-generation':row['generation']=0
        if name=='exhaustion':row.update(generation=U64-1,writer_status=6)
        if name=='invalid-finish':row.update(generation=4,writer_status=2,mutations=1)
    if name=='last-write':row.update(generation=U64-1,end_generation=U64-1,mutations=1,evaluate=4)
    if name in ('other-store','other-incarnation'):row['evaluate']=4
    if name=='after-end-publish':row.update(generation=4,mutations=1)
    if name in ('bypass-aba','bypass-between'):row['mutations']=2
    if row['begin']!=0:row.update(begin_zeroed=True,begin_generation=0)
    if row['end']!=0:row.update(end_zeroed=True,end_generation=0)
    if row['evaluate']!=0:row.update(rounded_ns=0,minimum_met=False)
    return row


def validate(result):
    f.require(result['pointer_checks_passed'] is True and set(result['cases'])==set(NAMES) and result['threads_created']==3,'versioned fixture inventory differs')
    f.require(all(type(result[k]) is int and result[k]==0 for k in ('explicit_actual_clock_queries','real_sdk_objects','usb_requests','sd_accesses')),'versioned fixture scope differs')
    for name in NAMES:
        f.require(f.encode(result['cases'][name])==f.encode(oracle(name)),'versioned oracle differs '+name+': '+str(result['cases'][name]))
    return result


def exercise(source,output):
    output.mkdir(mode=0o700);host=source/BASE/'host';fixture=source/BASE/'tests/a23_versioned_clock_fixture.c'
    inputs=[host/'a23_clock_candidate.c',host/'a23_versioned_clock_candidate.c',fixture]
    for path in [*inputs,host/'a23_versioned_clock_candidate.h']:
        raw=a.read(path)
        for token in (b'mach_absolute_time',b'mach_timebase_info',b'IOUSBHost',b'IOServiceOpen',b'A23ReadExecutionContext'):
            f.require(token not in raw,'versioned fixture crosses scope')
    build=output/'build';build.mkdir();builds={};results={}
    for mode in ('optimized','ubsan'):
        binary=build/('versioned-clock-'+mode)
        flags=['-std=c11','-Wall','-Wextra','-Werror','-Wconversion','-Wsign-conversion','-O2']
        if mode=='ubsan':flags+=['-fsanitize=undefined','-fno-sanitize-recover=all']
        command=['/usr/bin/clang',*flags,'-I',str(host),*map(str,inputs),'-o',str(binary)]
        f.require(previous.command(command)==b'','versioned compiler stdout differs')
        scope=output/('scope-'+mode);scope.mkdir();reports=previous.link_scope(binary,scope)
        child=subprocess.run([str(binary)],capture_output=True,timeout=30)
        a.put(output,'stdout-'+mode+'.json',child.stdout);a.put(output,'stderr-'+mode+'.txt',child.stderr)
        f.require(child.returncode==0 and child.stderr==b'','versioned fixture failed '+str(child.returncode)+' '+child.stderr.decode(errors='replace'))
        results[mode]=validate(f.parse(child.stdout))
        rejected=subprocess.run([str(binary),'unknown-mode'],capture_output=True,timeout=10)
        f.require(rejected.returncode==2 and rejected.stdout==rejected.stderr==b'','versioned invalid entry accepted')
        builds[mode]=dict(command=command,binary_sha256=f.sha(a.read(binary)),link_scope=reports)
    f.require(f.encode(results['optimized'])==f.encode(results['ubsan']),'versioned optimized/UBSan differs')
    return dict(passed=True,model_cases=len(NAMES),fixture=results['optimized'],builds=builds,standalone_fixture_builds=2,
                native_compiler_jobs=2,fixture_process_executions=2,native_entry_rejections=2,
                participating_writer_aba_rejected=True,independent_versioned_candidate_implemented=True,
                full_sdk_model_executions=0,production_receiver_executions=0,**FALSE)


def verify(root,pin):
    root=a.canonical(root);_,_,digest=a.sealed(root);f.require(f.hex64(pin) and pin==digest,'external review pin differs')
    report=f.load(root/'results.json');audit=f.load(root/'audit.json')
    for name,h in audit['source_hashes'].items():f.require(f.sha(a.read(root/'source'/name))==h,'versioned frozen source differs')
    validate(report['fixture'])
    for mode,row in report['builds'].items():
        f.require(f.sha(a.read(root/'work/build'/('versioned-clock-'+mode)))==row['binary_sha256'],'versioned binary differs')
        f.require(a.read(root/'work'/('stderr-'+mode+'.txt'))==b'' and f.encode(validate(f.load(root/'work'/('stdout-'+mode+'.json'))))==f.encode(report['fixture']),'saved versioned fixture differs')
        for label,h in row['link_scope'].items():
            raw=a.read(root/'work'/('scope-'+mode)/(label+'.txt'));f.require(f.sha(raw)==h and all(t not in raw for t in previous.DENY),'saved versioned link scope differs')
    f.require(all(report[k] is False for k in FALSE),'versioned candidate claims authority');return report


def run(output):
    import audit_a23_pinned_view as old
    w=old.w;output=a.canonical(output);f.require(not output.exists(),'new versioned review required');frozen=sources();output.mkdir(mode=0o700)
    for name,h in frozen.items():
        raw=w.plain(w.b.REPO/name);f.require(f.sha(raw)==h,'versioned source drift');a.put(output,'source/'+name,raw)
    try:result=exercise(output/'source',output/'work')
    except Exception as exc:
        a.put(output,'failure.json',f.encode(dict(error=str(exc),source_hashes=frozen,scope='standalone-versioned-candidate')));a.seal(output);raise
    f.require(sources()==frozen,'versioned source drift after exercise')
    a.put(output,'results.json',f.encode(result));a.put(output,'audit.json',f.encode(dict(passed=True,source_count=len(frozen),prior_sources_unchanged=462,source_hashes=frozen)))
    a.seal(output);return dict(passed=True,review_sha256=f.sha(a.read(output/'SHA256SUMS')),model_cases=len(NAMES))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--output',type=Path);g.add_argument('--check',type=Path);p.add_argument('--expected-sha256');args=p.parse_args()
    if args.check and not args.expected_sha256:p.error('--check requires --expected-sha256')
    try:r=run(args.output) if args.output else verify(args.check,args.expected_sha256)
    except (ValueError,OSError,KeyError,TypeError,subprocess.SubprocessError) as exc:print(json.dumps(dict(passed=False,error=str(exc))));raise SystemExit(2)
    print(json.dumps(r if args.output else dict(passed=True,model_cases=r['model_cases'],native_execution=False),indent=2))
