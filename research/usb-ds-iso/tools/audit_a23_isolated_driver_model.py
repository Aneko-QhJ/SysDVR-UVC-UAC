"""Build and replay a numeric-clock driver with trimmed model-only providers."""
from pathlib import Path
from fractions import Fraction
import argparse,json,struct,subprocess
import a23_isolated_driver_model as model
previous=model.previous
f,a=previous.f,previous.a
BASE=model.BASE
PARENT='A23-quiet-driver-copy-closeout-20261020'
PARENT_SUM='611a83b03e206b9e8a8eb069fc03fa43a743f0c0e855d87872d69bee7fb18153'
NEW=('tools/a23_isolated_driver_model.py','tools/audit_a23_isolated_driver_model.py',
     'tests/a23_isolated_driver_clock.inc','tests/a23_isolated_driver_main.inc','tests/test_a23_isolated_driver_model.py')
NAMES=('normal','fractional-short','fractional-short-equal','fractional-after','unlabeled','owner-role','zero-instance',
       'zero-start','ratio-change','instance-change','domain-change','backwards','overflow','object-replaced',
       'quiet-journal-failure','postguard-failure','late-after-settled','late-after-receipt','incomplete')
FALSE={**previous.FALSE,'actual_sdk_mapping_tested':False,'full_production_sdk_chain_verified':False}
# Supersede the earlier compile-only observation only within this isolated scope.
FALSE.pop('full_sdk_driver_model_executed');FALSE.pop('objective_c_driver_runtime_verified')
DENY=(b'IOUSBHost.framework',b'IOKit.framework',b'mach_absolute_time',b'mach_timebase_info',
      b'IOServiceOpen',b'IOServiceMatching',b'IOObjectRetain',b'IOObjectRelease',b'A23ReadExecutionContext',
      b'OBJC_CLASS_$_IOUSB',b'OBJC_CLASS_$_A23PairedSDKOperations',b'OBJC_CLASS_$_A23DormantSDKOperations',
      b'OBJC_CLASS_$_A23ExistingPipeTransport',b'OBJC_CLASS_$_A23LocalMachClock')


def sources():
    import audit_a23_pinned_view as old
    w=old.w;root=w.A/PARENT;w.card.seal_verify(root)
    f.require(f.sha(w.plain(root/'SHA256SUMS'))==PARENT_SUM,'parent pin differs')
    saved=w.load(root/'closeout.json');out=previous.sources()
    f.require(out==saved['source_hashes'] and len(out)==452,'prior452 drift')
    for name in NEW:
        key=BASE+name;f.require(key not in out,'source overlap');out[key]=f.sha(w.plain(w.ROOT/name))
    return dict(sorted(out.items()))


def command(args):
    child=subprocess.run(args,capture_output=True,timeout=60)
    f.require(child.returncode==0 and child.stderr==b'','model command failed '+child.stderr.decode(errors='replace'))
    return child.stdout


def link_scope(binary,output):
    reports={}
    for label,flags in (('libraries',['-L']),('undefined-symbols',['-u']),('symbols',['-a'])):
        tool='/usr/bin/otool' if label=='libraries' else '/usr/bin/nm'
        raw=command([tool,*flags,str(binary)])
        f.require(all(token not in raw for token in DENY),'forbidden model link dependency')
        a.put(output,label+'.txt',raw);reports[label]=f.sha(raw)
    return reports


def bundle(path,expected):
    raw=a.read(path/'SHA256SUMS');f.require(a.read(path/'COMMITTED')==(f.sha(raw)+'\n').encode(),'model bundle commit differs')
    rows={}
    for line in raw.decode().splitlines():
        digest,name=line.split('  ',1)
        f.require(name in expected and name not in rows and f.hex64(digest),'model bundle member differs')
        rows[name]=digest;f.require(f.sha(a.read(path/name))==digest,'model bundle digest differs')
    f.require(set(rows)==set(expected) and {p.name for p in path.iterdir()}==set(expected)|{'SHA256SUMS','COMMITTED'},'model bundle inventory differs')


def analyze(root,result):
    f.require(result['case_count']==len(NAMES) and set(result['cases'])==set(NAMES),'model cases differ')
    f.require(all(result[k]==0 for k in ('real_sdk_objects','usb_requests','sd_accesses')) and result['actual_sdk_mapping_tested'] is False,'model claims physical authority')
    semantic={}
    for name in NAMES:
        row=result['cases'][name];directory=root/name
        events=[f.parse(line) for line in a.read(directory/'session.jsonl').splitlines()]
        names=[event['event'] for event in events]
        f.require([e['index'] for e in events]==list(range(1,len(events)+1)),'event order differs')
        if name in ('unlabeled','owner-role','zero-instance'):
            f.require(row['init_rejected'] is True and row['clock_reads']==0 and not events,'invalid profile touched driver runtime')
            f.require(row['lease']['iso_attempts']==row['lease']['trigger_attempts']==0,'preflight enqueued I/O')
            semantic[name]=dict(init_rejected=True,clock_reads=0,events=[]);continue
        state=row['result'];receipt=row['receipt_status'];profile=row['profile']
        f.require(f.load(directory/'result.json')==state and f.load(directory/'receipt-status.json')==receipt and
                  f.load(directory/'clock-profile.json')==profile,'model exports differ')
        f.require(row['live_references']==1 and row['destroys']==0 and state['saved_epochs']==2 and
                  state['iso_attempts']==state['trigger_attempts']==2 and state['aborts']==0,'bounded owner state differs')
        for flag in ('callback_drain_verified','device_trace_verified','hardware_verified','hardware_entry_enabled'):
            f.require(state[flag] is False,'driver result claims '+flag)
        f.require(names.count('epochs_saved')==1 and names.count('saved')==2,'epoch journals differ')
        for n in range(2):
            path=directory/('epoch-'+str(n));bundle(path,('raw.bin','transactions.bin','before.bin','after.bin','metadata.json'))
            raw=a.read(path/'raw.bin');tx=a.read(path/'transactions.bin');metadata=f.load(path/'metadata.json')
            f.require(len(raw)==184320 and len(tx)==26880 and len(a.read(path/'before.bin'))==len(a.read(path/'after.bin'))==168,'model raw lengths differ')
            packets=0
            for i in range(960):
                status,request,offset,actual,stamp,options=struct.unpack_from('<IIIIQI',tx,i*28)
                f.require(status==stamp==options==0 and request==192 and offset==i*192 and actual in (0,192),'model transaction differs')
                if actual:
                    sequence=81+n*16+packets
                    expected=b'ISO1'+struct.pack('<H',sequence)+bytes((j^sequence^(sequence>>8))&255 for j in range(6,192))
                    f.require(raw[offset:offset+192]==expected,'model payload sequence/body differs')
                    packets+=1
            f.require(packets==16 and metadata['epoch']==n and metadata['first_sequence']==81+n*16,'model packet count differs')
            for key in ('before_observation','after_observation','sample'):
                f.require(metadata[key]['injected_fixture'] is True,'SDK-shaped observation is not labeled injected')
        good=name in ('normal','fractional-short-equal','fractional-after')
        waiting=name in ('fractional-short','incomplete')
        f.require(state['complete'] is good and state['stopped'] is (not good and not waiting),'quiet terminal state differs '+name)
        f.require(names.count('observation_complete')==(0 if waiting or name in ('zero-start','ratio-change','instance-change','domain-change','backwards','overflow','object-replaced','quiet-journal-failure') else 1),'completion event differs '+name)
        if waiting:
            f.require(not receipt['attempted'] and state['quiet_end_ticks']==0,'premature receipt or settlement')
        elif name=='late-after-receipt':
            f.require(receipt['attempted'] and receipt['stale'] and not receipt['saved'],'late callback did not revoke receipt')
        else:f.require(receipt['attempted'] and receipt['saved'] and not receipt['stale'],'terminal receipt differs '+name)
        if name in ('ratio-change','instance-change','domain-change','backwards','overflow','object-replaced','zero-start'):
            f.require('observation_clock' in state['failure_reasons'],'clock fault did not stop driver')
        if name=='quiet-journal-failure':f.require(state['journal_failed'] and 'journal_failed' in state['failure_reasons'],'append fault did not stop driver')
        if name=='postguard-failure':f.require(not state['observation_complete'] and state['quiet_end_ticks']==0,'postguard committed settlement')
        if name=='fractional-short-equal':
            f.require(not row['first_poll']['complete'] and not row['first_poll']['stopped'] and row['first_poll']['quiet_end_ticks']==0,'fractional shortfall rounded into settlement')
        duration=Fraction((profile['test_end_ticks']-profile['quiet_start_ticks'])*profile['initial']['numerator'],profile['initial']['denominator'])
        if good:f.require(duration>=250000000 and state['quiet_end_ticks']==profile['test_end_ticks'],'exact minimum differs')
        if waiting:f.require(duration<250000000,'waiting model reached exact minimum')
        if receipt['attempted']:
            path=directory/'sdk-receipt';bundle(path,('receipt.json','snapshot.json'))
            saved=f.load(path/'receipt.json');snapshot=a.read(path/'snapshot.json')
            f.require(saved['snapshot_sha256']==f.sha(snapshot) and f.parse(snapshot)==saved['snapshot'],'receipt snapshot differs')
        semantic[name]=dict(complete=state['complete'],stopped=state['stopped'],observation_complete=state['observation_complete'],
                            quiet_start_ticks=state['quiet_start_ticks'],quiet_end_ticks=state['quiet_end_ticks'],
                            failure_reasons=state['failure_reasons'],receipt=receipt,events=names,profile=profile,
                            exact_duration=[duration.numerator,duration.denominator])
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
    a.put(output,'results.json',f.encode(result));a.put(output,'audit.json',f.encode(dict(passed=True,source_count=len(frozen),prior_sources_unchanged=452,source_hashes=frozen)))
    a.seal(output);return dict(passed=True,review_sha256=f.sha(a.read(output/'SHA256SUMS')),model_cases=len(NAMES))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--output',type=Path);g.add_argument('--check',type=Path);p.add_argument('--expected-sha256');args=p.parse_args()
    if args.check and not args.expected_sha256:p.error('--check requires --expected-sha256')
    try:r=run(args.output) if args.output else verify(args.check,args.expected_sha256)
    except (ValueError,OSError,KeyError,TypeError,subprocess.SubprocessError) as exc:print(json.dumps(dict(passed=False,error=str(exc))));raise SystemExit(2)
    print(json.dumps(r if args.output else dict(passed=True,model_cases=r['model_cases'],native_execution=False),indent=2))
