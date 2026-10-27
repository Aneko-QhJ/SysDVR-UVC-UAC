"""Replay complete-driver callback/deadline faults and non-atomic profile reads."""
from pathlib import Path
from fractions import Fraction
import argparse,json,subprocess
import a23_driver_fault_model as model
import audit_a23_isolated_driver_model as previous
import analyze_a23_two_epoch_sdk as sdk
f,a=previous.f,previous.a
BASE=model.BASE
PARENT='A23-isolated-driver-model-closeout-20261020'
PARENT_SUM='df68ad2bf3d0a8d2a2d63eab3d6cbd383655c033c30e439d8c6b693f67e76fbb'
NEW=('tools/a23_driver_fault_model.py','tools/audit_a23_driver_fault_model.py','tests/a23_driver_fault_clock.inc',
     'tests/a23_driver_fault_main.inc','tests/test_a23_driver_fault_model.py')
DEADLINES=tuple('-'.join((target,mode,ratio,edge)) for target in ('control','iso') for mode in ('arrival','poll') for ratio in ('1to1','2to3') for edge in ('before','equal','after'))
PROFILES=tuple('profile-'+stage+'-'+field for stage in ('start','end') for field in ('numerator','denominator','domain','instance','aba'))
CALLBACKS=('duplicate-iso','duplicate-control','foreign-pointer','control-error','control-bytes','iso-error',
           'callback-queued-delay','old-control-between-epochs','early-iso','iso-reject','trigger-reject','iso-abort-late')
NAMES=DEADLINES+PROFILES+CALLBACKS
FALSE={**previous.FALSE,'profile_mutation_aba_rejected':False,'sidecar_provenance_authenticated':False}
DENY=previous.DENY
command,link_scope,bundle=previous.command,previous.link_scope,previous.bundle


def sources():
    import audit_a23_pinned_view as old
    w=old.w;root=w.A/PARENT;w.card.seal_verify(root)
    f.require(f.sha(w.plain(root/'SHA256SUMS'))==PARENT_SUM,'parent pin differs')
    saved=w.load(root/'closeout.json');out=previous.sources()
    f.require(out==saved['source_hashes'] and len(out)==457,'prior457 drift')
    for name in NEW:
        key=BASE+name;f.require(key not in out,'source overlap');out[key]=f.sha(w.plain(w.ROOT/name))
    return dict(sorted(out.items()))


def deadline_oracle(name):
    f.require(name in DEADLINES,'unknown deadline case')
    target,mode,ratio,edge=name.split('-');n,d=(1,1) if ratio=='1to1' else (2,3)
    limit=16000000 if target=='control' else 2000000000
    ticks=limit*d//n+{'before':-1,'equal':0,'after':1}[edge]
    exact=Fraction(ticks*n,d);ceil=(ticks*n+d-1)//d
    timeout=ceil>limit if mode=='arrival' else ceil>=limit
    return dict(numerator=n,denominator=d,limit_ns=limit,ticks=ticks,exact_ns=[exact.numerator,exact.denominator],
                rounded_up_ns=ceil,timeout=timeout,abort=int(timeout and mode=='poll' and target=='iso'))


def facts_valid(value,name):
    keys={'schema','case','start_accepted','initial_ticks','target_end_ticks','initial_numerator','initial_denominator',
          'end_numerator','end_denominator','end_domain','end_instance','mutations','quiet_start_ticks','quiet_test_end_ticks',
          'injected_fixture','profile_reads_atomic','actual_clock_authenticated','owners'}
    f.require(type(value) is dict and set(value)==keys and value['schema']=='A23-injected-driver-fault-facts-1' and value['case']==name,'fault sidecar schema differs')
    f.require(value['injected_fixture'] is True and value['profile_reads_atomic'] is False and value['actual_clock_authenticated'] is False and type(value['start_accepted']) is bool,'fault sidecar authority differs')
    for key in keys-{'schema','case','start_accepted','injected_fixture','profile_reads_atomic','actual_clock_authenticated','owners'}:
        f.require(type(value[key]) is int and 0<=value[key]<=2**64-1,'fault sidecar integer differs '+key)
    owners=value['owners'];f.require(type(owners) is list and len(owners)==2,'fault owner array differs')
    for owner in owners:
        f.require(type(owner) is dict and set(owner)=={'state','callbacks','retained','timed_out'} and type(owner['state']) is int and 0<=owner['state']<=5 and type(owner['callbacks']) is int and 0<=owner['callbacks']<=2 and type(owner['retained']) is bool and type(owner['timed_out']) is bool,'fault owner declaration differs')


def analyze(root,result):
    f.require(result['case_count']==len(NAMES) and set(result['cases'])==set(NAMES),'fault cases differ')
    f.require(all(type(result[k]) is int and result[k]==0 for k in ('real_sdk_objects','usb_requests','sd_accesses')) and result['actual_sdk_mapping_tested'] is False,'fault model claims authority')
    semantic={}
    for name in NAMES:
        row=result['cases'][name];directory=root/name;state=row['result'];receipt=row['receipt_status'];facts=row['facts'];facts_valid(facts,name)
        for file,value in (('result.json',state),('receipt-status.json',receipt),('fault-facts.json',facts)):
            f.require(f.encode(f.load(directory/file))==f.encode(value),'fault export differs '+file)
        events=[f.parse(line) for line in a.read(directory/'session.jsonl').splitlines()];names=[e['event'] for e in events]
        f.require([e['index'] for e in events]==list(range(1,len(events)+1)),'fault event indices differ')
        f.require(all(e['session_id']==state['session_id'] and e['hardware_verified'] is False and e['hardware_entry_enabled'] is False for e in events),'event binding or authority differs')
        n,d=facts['initial_numerator'],facts['initial_denominator'];f.require(facts['initial_ticks']==100 and events[0]['details']['timebase_numerator']==n and events[0]['details']['timebase_denominator']==d,'initial profile differs')
        expected_saved=0;expected_abort=0;good=False;edge=None
        if name in DEADLINES:
            edge=deadline_oracle(name);good=not edge['timeout'];expected_saved=2 if good else 0;expected_abort=edge['abort']
            f.require((n,d)==(edge['numerator'],edge['denominator']) and facts['target_end_ticks']==100+edge['ticks'],'deadline endpoint differs')
            f.require(row['edge_state']['stopped'] is edge['timeout'],'deadline edge state differs '+name)
            if edge['timeout']:f.require(name.split('-')[0]+'_deadline' in state['failure_reasons'],'wrong deadline reason')
            key='control_callback' if name.startswith('control-') else 'iso_callback'
            if '-arrival-' in name:
                callback=next(e for e in events if e['event']==key and e['details']['epoch']==0)
                if key=='control_callback':f.require(callback['details']['arrival_ticks']==facts['target_end_ticks'],'control ingress timestamp differs')
        elif name in PROFILES:
            good=name.endswith('-aba');expected_saved=2
            f.require(facts['mutations']==1,'profile mutation did not execute')
            if not good:f.require('observation_clock' in state['failure_reasons'],'profile mutation not rejected')
            if '-start-' in name and not good:f.require(facts['quiet_start_ticks']==0,'invalid start profile was committed')
            if '-end-' in name:f.require(facts['quiet_start_ticks']==100,'quiet start binding differs')
        elif name=='callback-queued-delay':
            good=True;expected_saved=2
            control=next(e for e in events if e['event']=='control_callback' and e['details']['epoch']==0)
            f.require(control['details']['arrival_ticks']==100 and control['ticks']==25000100,'queued delay did not preserve arrival')
        elif name=='old-control-between-epochs':expected_saved=1
        elif name in ('trigger-reject','iso-abort-late'):expected_abort=1
        if name=='iso-abort-late':
            f.require(row['edge_state']['stopped'] is True and row['after_late']['stopped'] is True and 'iso_deadline' in state['failure_reasons'],'late abort continuation differs')
        f.require(state['complete'] is good and state['stopped'] is (not good) and state['saved_epochs']==expected_saved and state['aborts']==expected_abort,'fault terminal state differs '+name)
        attempts=2 if expected_saved==2 else 1
        f.require(state['iso_attempts']==attempts and state['trigger_attempts']==(0 if name in ('early-iso','iso-reject') else attempts),'fault submission cap differs')
        f.require(names.count('saved')==expected_saved and names.count('epochs_saved')==int(expected_saved==2) and names.count('observation_complete')==int(good),'fault journal milestones differ')
        f.require(receipt['attempted'] is True and receipt['saved'] is True and receipt['stale'] is False,'fault receipt differs')
        for flag in ('callback_drain_verified','device_trace_verified','hardware_verified','hardware_entry_enabled'):f.require(state[flag] is False,'fault model claims '+flag)
        for epoch in range(expected_saved):
            path=directory/('epoch-'+str(epoch));bundle(path,('raw.bin','transactions.bin','before.bin','after.bin','metadata.json'))
            sdk.payload(a.read(path/'raw.bin'),a.read(path/'transactions.bin'),81+epoch*16)
            sdk.status(a.read(path/'before.bin'),None if epoch==0 else 81);sdk.status(a.read(path/'after.bin'),81+epoch*16)
            meta=f.load(path/'metadata.json');f.require(meta['binding']['session_id']==state['session_id'] and meta['epoch']==epoch,'epoch metadata binding differs')
            for key in ('before_observation','after_observation','sample'):f.require(meta[key]['injected_fixture'] is True,'fault SDK sample lost injection label')
        f.require(not any((directory/('epoch-'+str(epoch))).exists() for epoch in range(expected_saved,2)),'unexpected epoch saved')
        path=directory/'sdk-receipt';bundle(path,('receipt.json','snapshot.json'));saved=f.load(path/'receipt.json');snapshot=a.read(path/'snapshot.json')
        f.require(saved['snapshot_sha256']==f.sha(snapshot) and f.encode(f.parse(snapshot))==f.encode(saved['snapshot']) and f.encode(saved['snapshot'])==f.encode(state),'fault receipt snapshot differs')
        if good:
            duration=Fraction((state['quiet_end_ticks']-state['quiet_start_ticks'])*n,d)
            f.require(duration>=250000000 and facts['quiet_test_end_ticks']==state['quiet_end_ticks'],'fault quiet minimum differs')
            quiet=next(e for e in events if e['event']=='observation_complete')['details']
            f.require(quiet['quiet_start_ticks']==facts['quiet_start_ticks']==state['quiet_start_ticks'] and quiet['quiet_end_ticks']==state['quiet_end_ticks'],'quiet sidecar/event linkage differs')
        else:f.require(state['quiet_end_ticks']==0 and not state['observation_complete'],'fault committed settlement')
        owners=facts['owners']
        if expected_saved==2:f.require(all(o['callbacks']==1 and o['retained'] is False and o['state']==4 for o in owners),'saved owner state differs')
        if expected_abort:
            f.require(owners[0]['retained'] is True and owners[0]['timed_out'] is True,'abort released storage or lost timeout')
            f.require(owners[0]['callbacks']==(1 if name=='iso-abort-late' else 0) and owners[0]['state']==(4 if name=='iso-abort-late' else 2),'abort callback/owner state differs')
        semantic[name]=dict(complete=good,saved_epochs=expected_saved,aborts=expected_abort,failure_reasons=state['failure_reasons'],
                            facts=facts,events=names,receipt=receipt,deadline=edge)
    return semantic


def exercise(source,output):
    output.mkdir(mode=0o700);generated=model.render(source)
    for name,raw in generated.items():a.put(output,'generated/'+name,raw)
    root=output/'generated'/BASE;host=root/'host';build=output/'build';build.mkdir();builds={};replays={}
    native=sorted(str(p) for p in host.glob('*.m'))+[str(root/'tests/model_main.m')]
    f.require(len(native)==7,'model translation-unit scope differs')
    for mode in ('optimized','ubsan'):
        flags=['-Wall','-Wextra','-Werror','-O2']
        if mode=='ubsan':flags+=['-fsanitize=undefined','-fno-sanitize-recover=all']
        obj=build/('clock-'+mode+'.o');binary=build/('isolated-driver-'+mode)
        ccmd=['/usr/bin/clang','-std=c11',*flags,'-I',str(host),'-c',str(host/'a23_clock_candidate.c'),'-o',str(obj)]
        f.require(command(ccmd)==b'','compiler output differs')
        cmd=['/usr/bin/clang','-fobjc-arc','-fblocks',*flags,'-I',str(host),*native,str(obj),'-framework','Foundation','-o',str(binary)]
        f.require(command(cmd)==b'','compiler output differs')
        scope=output/('scope-'+mode);scope.mkdir();reports=link_scope(binary,scope)
        fixtures=output/('models-'+mode);fixtures.mkdir()
        child=subprocess.run([str(binary),str(fixtures)],capture_output=True,timeout=60)
        a.put(output,'stdout-'+mode+'.json',child.stdout);a.put(output,'stderr-'+mode+'.txt',child.stderr)
        f.require(child.returncode==0 and child.stderr==b'','isolated model failed '+str(child.returncode)+' '+child.stderr.decode(errors='replace'))
        result=f.parse(child.stdout);replays[mode]=analyze(fixtures,result)
        invalid=subprocess.run([str(binary)],capture_output=True,timeout=10)
        f.require(invalid.returncode==2 and invalid.stdout==invalid.stderr==b'','unexpected entry accepted')
        builds[mode]=dict(command=cmd,c_helper_command=ccmd,binary_sha256=f.sha(a.read(binary)),link_scope=reports)
    f.require(f.encode(replays['optimized'])==f.encode(replays['ubsan']),'optimized/UBSan model differs')
    return dict(passed=True,generated_sha256={k:f.sha(v) for k,v in generated.items()},builds=builds,model_cases=len(NAMES),
                semantic=replays['optimized'],isolated_full_driver_model_executed=True,model_process_executions=2,
                native_entry_rejections=2,native_compiler_jobs=4,real_sdk_objects=0,usb_requests=0,sd_accesses=0,**FALSE)


def verify(root,pin):
    root=a.canonical(root);_,_,digest=a.sealed(root);f.require(f.hex64(pin) and pin==digest,'external review pin differs')
    report=f.load(root/'results.json');audit=f.load(root/'audit.json')
    for name,h in audit['source_hashes'].items():f.require(f.sha(a.read(root/'source'/name))==h,'frozen model source differs')
    generated=model.render(root/'source')
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
    a.put(output,'results.json',f.encode(result));a.put(output,'audit.json',f.encode(dict(passed=True,source_count=len(frozen),prior_sources_unchanged=457,source_hashes=frozen)))
    a.seal(output);return dict(passed=True,review_sha256=f.sha(a.read(output/'SHA256SUMS')),model_cases=len(NAMES))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--output',type=Path);g.add_argument('--check',type=Path);p.add_argument('--expected-sha256');args=p.parse_args()
    if args.check and not args.expected_sha256:p.error('--check requires --expected-sha256')
    try:r=run(args.output) if args.output else verify(args.check,args.expected_sha256)
    except (ValueError,OSError,KeyError,TypeError,subprocess.SubprocessError) as exc:print(json.dumps(dict(passed=False,error=str(exc))));raise SystemExit(2)
    print(json.dumps(r if args.output else dict(passed=True,model_cases=r['model_cases'],native_execution=False),indent=2))
