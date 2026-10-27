"""Compile-only isolated driver patch and Foundation-only clock bridge replay."""
from fractions import Fraction
from pathlib import Path
import argparse,json,math,subprocess
import a23_quiet_driver_copy as patch

previous=patch.previous
view,ar,a,f=previous.view,previous.ar,previous.a,previous.f
U64,U32=previous.U64,previous.U32
PARENT='A23-quiet-poll-closeout-20261020'
PARENT_SUM='fd7ddc9457b2254147669528b19da8aa0aca23ae0e99d71a24664ea5bd476357'
NEW=('host/a23_quiet_driver_clock_candidate.h','tests/a23_quiet_driver_clock_fixture.m',
     'tools/a23_quiet_driver_copy.py','tools/audit_a23_quiet_driver_copy.py','tests/test_a23_quiet_driver_copy.py')
DRIVER='research/usb-ds-iso/host/a23_two_epoch_sdk_driver.m'
PROTOCOL='source/uvc/iso_probe_protocol.h'
FALSE={**previous.FALSE,'full_sdk_driver_model_executed':False,'production_driver_copy_deployed':False,
       'clock_profile_reads_atomic':False,'objective_c_driver_runtime_verified':False}
NAMES=('normal','fractional-short','fractional-equal','fractional-after','zero-tick','backwards','overflow',
       'zero-instance','zero-numerator','zero-denominator','owner-role','supervisor-role','unknown-role','missing-selector',
       'plain-clock','pretend-clock','nil-clock','numerator-between','denominator-between','instance-between','domain-between',
       'numerator-during','denominator-during','instance-during','domain-during','object-replaced','aba-during')


def sources():
    import audit_a23_pinned_view as old
    w=old.w;root=w.A/PARENT;w.card.seal_verify(root)
    f.require(f.sha(w.plain(root/'SHA256SUMS'))==PARENT_SUM,'parent pin differs')
    parent=w.load(root/'closeout.json');out=previous.sources()
    f.require(out==parent['source_hashes'] and len(out)==447,'prior447 drift')
    for name in NEW:
        key='research/usb-ds-iso/'+name;f.require(key not in out,'source overlap');out[key]=f.sha(w.plain(w.ROOT/name))
    return dict(sorted(out.items()))


def bridge_oracle(name):
    f.require(name in NAMES,'unknown bridge case')
    denied=name in ('zero-instance','zero-numerator','zero-denominator','owner-role','supervisor-role','unknown-role',
                    'missing-selector','plain-clock','pretend-clock','nil-clock')
    profile=begin=end=not denied;reads=0 if denied else 2
    status=1 if denied else 0;rounded=0;minimum=False;same_object=not denied
    n,d,b,e=1,1,100,250000100
    if name.startswith('fractional-'):
        n,d=2,3;e={'fractional-short':375000099,'fractional-equal':375000100,'fractional-after':375000101}[name]
    if name=='zero-tick':b,e=0,250000000
    if name=='backwards':e=99;status=5
    if name=='overflow':b,e,n=1,U64,U32;status=6
    if name in ('numerator-between','denominator-between','instance-between','object-replaced'):status=4
    if name=='object-replaced':same_object=False
    if name=='domain-between' or name.endswith('-during') and name!='aba-during':
        end=False;status=1;same_object=False
        if name=='domain-between':reads=1
    if status==0:
        duration=Fraction((e-b)*n,d);rounded=math.ceil(duration);minimum=duration>=250000000
    return dict(profile_ok=profile,begin_ok=begin,end_ok=end,status=status,rounded_up_ns=rounded,minimum_met=minimum,
                preflight_tick_reads=0,tick_reads=reads,begin_zeroed=not begin,end_zeroed=not end,
                same_object=same_object,aba_performed=name=='aba-during')


def build_plan(source):
    # These are source observations, not a capability or execution certificate.
    root=source/'research/usb-ds-iso';two=(root/'tests/a23_two_epoch_receiver_test.m').read_text()
    broker=(root/'tests/a23_broker_model_fixture.m').read_text()
    f.require('mach_timebase_info(&_info)' in two and 'mach_absolute_time()+atomic_load(&_offset)' in two and
              'ns*_info.denom+_info.numer-1' in two,'legacy clock source changed')
    f.require('A23ReadExecutionContext' in broker and 'A23ModelScopeVerifier' in broker,'broker source boundary changed')
    return dict(schema='A23-isolated-driver-replay-plan-1',compile_only_driver=True,foundation_clock_bridge_executable=True,
                full_sdk_fixture_executed=False,production_acquisition_enabled=False,
                legacy_two_clock_uses_actual_mach_clock=True,broker_reads_actual_context_and_scope=True,
                clock_policy='explicit_injected_role_and_instance_plus_object_identity',
                untouched_driver_slices=['deadline','emit-stop-guard','receipt-and-result'],
                future_cases=['normal-1-to-1','fractional-short-equal','unlabeled-rejected-before-start',
                              'profile-change-at-quiet-end','object-replacement','zero-quiet-start',
                              'completion-append-failure','postguard-failure','late-callback-revocation'],
                blockers=['replace legacy TwoClock with a numeric tick clock throughout every SDK-shaped mock',
                          'inspect native source list and exclude real SDK factories from the executable scope',
                          'decide how quiet-start profile evidence is exported without assuming legacy analyzers accept new fields',
                          'native owner timebase has no verified mapping to the injected driver domain'],**FALSE)


def compiler_job(command):
    child=subprocess.run(command,capture_output=True,timeout=60)
    f.require(child.returncode==0 and child.stdout==child.stderr==b'','compile failed '+child.stderr.decode(errors='replace'))
    return dict(command=command,returncode=0,compiler_stdout='',compiler_stderr='')


def exercise(source,output):
    output.mkdir(mode=0o700);original=a.read(source/DRIVER);candidate=patch.render(original)
    before=patch.protected_slices(original);after=patch.protected_slices(candidate)
    f.require(before==after,'unrelated driver slices changed')
    a.put(output,'candidate/source/'+DRIVER,candidate)
    a.put(output,'candidate/source/'+PROTOCOL,a.read(source/PROTOCOL))
    a.put(output,'driver-copy.diff',patch.diff(original,candidate));plan=build_plan(source);a.put(output,'replay-plan.json',f.encode(plan))
    host=source/'research/usb-ds-iso/host';build=output/'build';build.mkdir();jobs={}
    for role,path in (('baseline',source/DRIVER),('candidate',output/'candidate/source'/DRIVER)):
        obj=build/(role+'-driver.o')
        cmd=['/usr/bin/clang','-fobjc-arc','-fblocks','-Wall','-Wextra','-Werror','-O2','-I',str(host),'-c',str(path),'-o',str(obj)]
        jobs[role]=compiler_job(cmd);jobs[role]['object_sha256']=f.sha(a.read(obj))
    bridge_source=source/'research/usb-ds-iso/tests/a23_quiet_driver_clock_fixture.m'
    for path in (bridge_source,host/'a23_quiet_driver_clock_candidate.h'):
        text=a.read(path).decode()
        for token in ('mach_absolute_time','mach_timebase_info','IOUSBHost','IOServiceOpen','A23ReadExecutionContext',
                      'dataWithContentsOfFile','writeToFile','NSFileManager'):
            f.require(token not in text,'bridge scope contains '+token)
    bridge={};builds={}
    for mode in ('optimized','ubsan'):
        flags=['-Wall','-Wextra','-Werror','-Wconversion','-Wsign-conversion','-O2']
        if mode=='ubsan':flags+=['-fsanitize=undefined','-fno-sanitize-recover=all']
        obj=build/('clock-'+mode+'.o');binary=build/('clock-bridge-'+mode)
        ccmd=['/usr/bin/clang','-std=c11',*flags,'-I',str(host),'-c',str(host/'a23_clock_candidate.c'),'-o',str(obj)]
        cc=compiler_job(ccmd)
        cmd=['/usr/bin/clang','-fobjc-arc','-fblocks',*flags,'-I',str(host),str(bridge_source),str(obj),'-framework','Foundation','-o',str(binary)]
        bc=compiler_job(cmd);bc.update(c_helper_command=cc['command'],binary_sha256=f.sha(a.read(binary)))
        child=subprocess.run([str(binary)],capture_output=True,timeout=30)
        f.require(child.returncode==0 and child.stderr==b'','Foundation bridge fixture failed '+child.stderr.decode(errors='replace'))
        result=f.parse(child.stdout)
        f.require(result['pointer_checks_passed'] is True and set(result['cases'])==set(NAMES) and
                  all(result[k]==0 for k in ('actual_clock_queries','real_sdk_objects','usb_requests','sd_accesses')),'bridge result scope differs')
        for name in NAMES:f.require(f.encode(result['cases'][name])==f.encode(bridge_oracle(name)),'bridge oracle differs '+name+': '+str(result['cases'][name]))
        invalid=subprocess.run([str(binary),'unknown-mode'],capture_output=True,timeout=10)
        f.require(invalid.returncode==2 and invalid.stdout==invalid.stderr==b'','bridge unexpected mode accepted')
        bridge[mode]=result;builds[mode]=bc
    f.require(f.encode(bridge['optimized'])==f.encode(bridge['ubsan']),'bridge modes differ')
    return dict(passed=True,driver_original_sha256=f.sha(original),driver_candidate_sha256=f.sha(candidate),
                driver_diff_sha256=f.sha(patch.diff(original,candidate)),protected_slice_sha256={k:f.sha(v) for k,v in before.items()},
                compile_only_jobs=jobs,bridge_builds=builds,bridge=bridge['optimized'],replay_plan=plan,
                driver_translation_units_compiled=2,foundation_fixture_builds=2,native_compiler_jobs=6,
                foundation_fixture_executions=4,full_sdk_model_executions=0,production_receiver_executions=0,**FALSE)


def verify(root,pin):
    root=a.canonical(root);_,_,digest=a.sealed(root);f.require(f.hex64(pin) and pin==digest,'external review pin differs')
    report=f.load(root/'results.json');source=root/'source';work=root/'work'
    original=a.read(source/DRIVER);candidate=a.read(work/'candidate/source'/DRIVER)
    f.require(patch.render(original)==candidate and report['driver_candidate_sha256']==f.sha(candidate) and
              report['driver_original_sha256']==f.sha(original) and a.read(work/'driver-copy.diff')==patch.diff(original,candidate),'driver copy derivation differs')
    f.require(patch.protected_slices(original)==patch.protected_slices(candidate),'protected methods changed')
    f.require(f.encode(report['replay_plan'])==f.encode(build_plan(source)),'replay plan differs')
    for name in NAMES:f.require(f.encode(report['bridge']['cases'][name])==f.encode(bridge_oracle(name)),'saved bridge differs '+name)
    for mode,row in report['bridge_builds'].items():f.require(f.sha(a.read(work/'build'/('clock-bridge-'+mode)))==row['binary_sha256'],'bridge binary differs')
    for role,row in report['compile_only_jobs'].items():f.require(f.sha(a.read(work/'build'/(role+'-driver.o')))==row['object_sha256'],'driver object differs')
    f.require(all(report[k] is False for k in FALSE),'driver copy claims authority');return report


def run(output):
    import audit_a23_pinned_view as old
    w=old.w;output=a.canonical(output);f.require(not output.exists(),'new driver-copy review required')
    frozen=sources();output.mkdir(mode=0o700)
    for name,digest in frozen.items():
        value=w.plain(w.b.REPO/name);f.require(f.sha(value)==digest,'source drift');a.put(output,'source/'+name,value)
    result=exercise(output/'source',output/'work');a.put(output,'results.json',f.encode(result))
    f.require(sources()==frozen,'source drift after driver-copy audit')
    a.put(output,'audit.json',f.encode(dict(passed=True,source_count=452,prior_sources_unchanged=447,source_hashes=frozen,
          bridge_cases=len(NAMES),driver_translation_units_compiled=2,foundation_fixture_builds=2,native_compiler_jobs=6,
          foundation_fixture_executions=4,full_sdk_model_executions=0,real_sdk_objects=0,usb_requests=0,sd_accesses=0,
          formal_records=0,formal_reservations=0,**FALSE)))
    a.seal(output);return dict(passed=True,review_sha256=f.sha(a.read(output/'SHA256SUMS')),bridge_cases=len(NAMES))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--output',type=Path);group.add_argument('--check',type=Path);parser.add_argument('--expected-sha256');args=parser.parse_args()
    if args.check and not args.expected_sha256:parser.error('--check requires --expected-sha256')
    try:result=run(args.output) if args.output else verify(args.check,args.expected_sha256)
    except (ValueError,OSError,KeyError,TypeError,subprocess.SubprocessError) as exc:print(json.dumps(dict(passed=False,error=str(exc))));raise SystemExit(2)
    if args.output:print(json.dumps(result,indent=2))
    else:print(json.dumps(dict(passed=True,bridge_cases=len(NAMES),native_execution=False)))
