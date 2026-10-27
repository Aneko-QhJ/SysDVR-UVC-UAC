"""Current132 receiver adapter, compiled for file checks and offline fixtures only."""
import argparse
import json
import re
import subprocess
from pathlib import Path
import audit_a23_terminal_observation as prior
import build_a23_live126_interepoch as base
import a23_checked_export as checked

w=base.w; sha=base.sha; encode=base.encode; require=base.require
PARENT=w.A/'A23-terminal-observation-closeout-20261026'
PARENT_SUM='e1bbc3840d8b32038de134fb0b928936c1fcdf58ebb1e561cf0a5949bfcceb0a'
LIVE=prior.BUILD
ANCHOR=w.ROOT/'private/card-cycles/20261025-live126-interepoch-first-read'
ANCHOR_SUM='c6aa7954e0c338ff4038e6bb75dbabaa20c643dc53c2fc738a50b8dba22e12be'
NEW=('tools/build_a23_live132_terminal.py','tools/audit_a23_live132_terminal.py','tools/a23_live132_terminal_consumer.py')
SCHEMA='A23-live132-terminal-offline48-scope-1'
DESCRIPTION=dict(base.DESCRIPTION,schema='A23-live132-terminal-offline-description-1',baseline_raw_files=132,
    first_sequence=465,last_sequence=512,full_guard_source_count=662,hardware_entry_enabled=False,
    formal_issuance_available=False,acquisition_mode_implemented=False,terminal_service_window_ns=250000000,
    terminal_max_gap_ns=32000000,terminal_worker_return_required=True)

def sources():
    require(base.core.verify_seal(PARENT)==PARENT_SUM,'terminal closeout drift')
    old=prior.sources();require(old==w.load(PARENT/'source-hashes.json') and len(old)==659,'old659 drift')
    return dict(sorted((old|{'research/usb-ds-iso/'+n:sha(w.plain(w.ROOT/n)) for n in NEW}).items()))

def inputs():
    hashes=sources();base.verify(LIVE,current=False);prior.protected()
    saved=w.card.verify_snapshot(ANCHOR);m=json.loads(saved['snapshot.json']);e=json.loads(saved['eject.json'])
    require(w.latest_snapshot()==ANCHOR and sha(w.plain(ANCHOR/'SHA256SUMS'))==ANCHOR_SUM,'current132 required')
    inventory={n[5:]:dict(bytes=len(v),sha256=sha(v)) for n,v in saved.items() if n.startswith('card/')}
    require(len(inventory)==132 and inventory==m['raw_files'] and m['read_only_mount_verified'] is True and
        m['simulation'] is False and m['deployment_files_match'] is True and
        m['identity']['VolumeUUID']==w.card.UUID and m['identity']['WritableVolume'] is False and
        e['ejected'] is True and e['mount_absent'] is True,'132 receipt differs')
    require(all(inventory.get(n)==v for n,v in m['expected_deployment_files'].items()),'deployment drift')
    record=w.A/'A23-live126-interepoch-once-20261025-r2.json';r=w.load(record)
    require(w.plain(record)==w.plain(PARENT/'once417-record-unchanged.json') and r['remaining']==0 and
        r['stage']=='captured_logs_recovered' and r['creator_wait_verified'] is True and
        r['device_log_pending'] is False and r['host_device_chain_consistent'] is True and
        r['device_lifecycle_normal_return'] is True and r['card_snapshot']==str(ANCHOR),'spent417 differs')
    history_files={p.relative_to(LIVE/'history').as_posix():w.plain(p) for p in (LIVE/'history').rglob('*') if p.is_file()}
    spent=w.ROOT/'private/sequence-reservations48-417'
    for p in spent.rglob('*'):
        if p.is_file():history_files['spent417/'+p.relative_to(spent).as_posix()]=w.plain(p)
    history_files['records/'+record.name]=w.plain(record)
    history=w.load(spent/'history.json')+[dict(first=n,last=n+15,reservation_sha256=sha(w.plain(spent/'block-00417.json')),record_sha256=sha(w.plain(record))) for n in (417,433,449)]
    require(base.history_values(history)==set(range(49,465)),'complete49..464 required')
    index={p.parent.name+'/snapshot.json':w.plain(p) for p in (w.ROOT/'private/card-cycles').glob('*/snapshot.json')}
    d=dict(w.load(LIVE/'descriptor.json'));d.pop('generated_hashes')
    d.update(description=DESCRIPTION,source_hashes=hashes,workflow_source_sha256=sha(encode(hashes)),
        baseline_directory=ANCHOR.name,baseline_files={n:sha(v) for n,v in saved.items()},baseline_manifest_sha256=ANCHOR_SUM,
        baseline_inventory_sha256=sha(encode(inventory)),history_files={n:sha(v) for n,v in history_files.items()},
        history_sha256=sha(encode(history)),recovery_index={n:sha(v) for n,v in index.items()},parent_manifest_sha256=PARENT_SUM)
    d['live_roots']=dict(d['live_roots'],spent417=str(spent))
    require(d['device_binding_sha256']==m['device_binding_sha256'] and d['recipe_sha256']==m['expected_recipe_sha256'],'device binding drift')
    return d,saved,history_files,index,history

API='''
@interface A23ThreeEpochSDKDriver (A23TerminalService)
- (BOOL)terminalHealthPoll;
- (BOOL)finishTerminalObservation:(NSDictionary * _Nonnull)evidence;
@end
@interface A23TwoEpochEntry (A23TerminalService)
- (BOOL)terminalHealthPoll;
- (BOOL)finishTerminalObservation:(NSDictionary * _Nonnull)evidence;
- (BOOL)retainTerminalObservation:(NSDictionary * _Nonnull)evidence;
@end
'''
DRIVER=r'''
- (BOOL)terminalHealthPoll {
    dispatch_assert_queue(_queue);
    if(!_started || !_complete || _pending || _epoch!=3 || _saves!=3 || ![self guard])return NO;
    if(!_terminalHealthStarted){_terminalHealthStarted=YES;_quietSince=_clock.nowTicks;}
    return [self guard];
}
- (BOOL)finishTerminalObservation:(NSDictionary *)e {
    dispatch_assert_queue(_queue);
    if(_terminalAckAttempted || !_terminalHealthStarted || ![self terminalHealthPoll])return NO;
    _terminalAckAttempted=YES;
    if(![e[@"accepted"] isEqual:@YES] || ![e[@"phase"] isEqual:@"passed"] ||
       ![e[@"binding"][@"session_id"] isEqual:_session] ||
       [e[@"sample_count"] unsignedIntegerValue]<2 || [e[@"duration_ns"] unsignedLongLongValue]!=250000000 ||
       [e[@"max_gap_ns"] unsignedLongLongValue]>32000000){[self stop:@"terminal_evidence_invalid"];return NO;}
    _terminalProof=frozenJSON(e);uint64_t now=_clock.nowTicks;
    if(!_terminalProof || ![self emit:@"observation_complete" details:@{@"quiet_start_ticks":@(_quietSince),
        @"quiet_end_ticks":@(now),@"minimum_ns":@250000000}] || ![self guard])return NO;
    _settled=YES;_settledAt=now;return YES;
}
'''
ENTRY=r'''
- (BOOL)retainTerminalObservation:(NSDictionary *)e {
    dispatch_assert_queue(_queue);return file(_directory,@"terminal-observation.json",encode(e));
}
- (BOOL)terminalHealthPoll {
    dispatch_assert_queue(_queue);
    if(!_started || _stopped || _busy || !_driver || ![_driver terminalHealthPoll]){
        if(_started && !_stopped)[self stop:@"terminal_health_failed"];return NO;
    }return YES;
}
- (BOOL)finishTerminalObservation:(NSDictionary *)e {
    dispatch_assert_queue(_queue);
    if(_stopped || ![_driver finishTerminalObservation:e]){[self stop:@"terminal_completion_failed"];return NO;}return YES;
}
'''
COORD=r'''
- (NSDictionary *)terminalGuardResult {return _terminal.result?:@{};}
- (BOOL)terminalExitAllowed {return !_terminal || _terminal.exitAllowed;}
- (void)startTerminal:(NSDictionary *)d {
    if(_terminalStarted){[_entry requestExit];return;}_terminalStarted=YES;
    NSDictionary *binding=@{@"schema":@"A23-live132-terminal-binding-1",@"model_only":@YES,
        @"job":_job,@"scope_sha256":digest(encode(_scope)),@"session_id":d[@"session_id"],
        @"source_closure_sha256":_scope[@"workflow_source_sha256"],@"baseline_manifest_sha256":_scope[@"baseline_manifest_sha256"]};
    _terminal=[[A23TerminalObservation alloc] initWithQueue:_guardQueue binding:binding fullCheck:^BOOL{
        [self->_verifier setCheckPhase:@"terminal_worker"];
#ifdef A23_EXPORT_MODEL_FIXTURE
        A23Live132TerminalWorkerStarted();
#endif
        return [self->_verifier verifyCore];
    } recheck:^BOOL{return [self->_verifier verifyLiveJob:self->_scope job:self->_job] &&
        ![self->_permit.result[@"stale"] boolValue] && [self->_entry terminalHealthPoll];}
    poll:^BOOL{
#ifdef A23_EXPORT_MODEL_FIXTURE
        A23Live132TerminalPoll();
#endif
        return [self->_entry terminalHealthPoll];
    } finalCheck:^BOOL{return [self guard:@"terminal_final"] && [self->_entry terminalHealthPoll];}
    finished:^{
        if(![self->_entry retainTerminalObservation:self->_terminal.result] ||
           ![self->_terminal.result[@"accepted"] boolValue] ||
           ![self->_entry finishTerminalObservation:self->_terminal.result]){
            [self->_terminal requestStop];[self->_entry requestExit];
        }
    }];
    struct timespec t;if(clock_gettime(CLOCK_MONOTONIC_RAW,&t) || !_terminal){[_entry requestExit];return;}
    uint64_t now=(uint64_t)t.tv_sec*1000000000ULL+t.tv_nsec;
    if(![_terminal requestBoundary:@{@"saved_epochs":d[@"saved_epochs"],@"iso_attempts":d[@"iso_attempts"],
        @"durable":@YES,@"pending":@NO,@"stopped":@NO} deadlineNS:now+10000000000ULL])[_entry requestExit];
}
'''
TICK=r'''
- (void)tick {
    if([_between.result[@"busy"] boolValue]){[_between observeDeadline];return;}
    if([_between.result[@"stopped"] boolValue]){[_entry requestExit];return;}
    NSDictionary *r=_entry.result,*d=[r[@"driver"] isKindOfClass:NSDictionary.class]?r[@"driver"]:@{};
    if(_terminal){
        if([r[@"stopped"] boolValue] || [d[@"stopped"] boolValue])[_terminal requestStop];
        if(_terminal.busy){[_terminal tick];return;}
        if([_terminal.result[@"phase"] isEqual:@"observing"]){[_terminal tick];return;}
        if(![_terminal.result[@"accepted"] boolValue]){[_entry requestExit];return;}
        return;
    }
    NSUInteger saved=[d[@"saved_epochs"] unsignedIntegerValue];
    if(saved==3 && [d[@"iso_attempts"] unsignedIntegerValue]==3 && ![r[@"stopped"] boolValue] && ![d[@"stopped"] boolValue]){
        [self startTerminal:d];return;
    }
    if(_between && saved>0 && saved<3 && [d[@"iso_attempts"] unsignedIntegerValue]==saved &&
       ![r[@"stopped"] boolValue] && ![d[@"stopped"] boolValue]){
        struct timespec t;if(clock_gettime(CLOCK_MONOTONIC_RAW,&t)){[_entry requestExit];return;}
        uint64_t now=(uint64_t)t.tv_sec*1000000000ULL+t.tv_nsec;
        if(![_between requestEpoch:saved deadlineNS:now+10000000000ULL])[_entry requestExit];return;
    }
    if(![self inflight] && ![self guard:@"before_tick"])return;[_entry tick];
}
'''
MAIN=r'''#import "a23_scope_verifier.h"
#include <string.h>
int main(int argc,const char *argv[]){@autoreleasepool{
    if(argc==2 && !strcmp(argv[1],"--describe")){
        NSData *r=[NSJSONSerialization dataWithJSONObject:A23VerifiedEntryDescription() options:NSJSONWritingSortedKeys error:NULL];
        fwrite(r.bytes,1,r.length,stdout);puts("");return 0;
    }
    BOOL archive=argc==3 && !strcmp(argv[1],"--check-archive"),current=argc==3 && !strcmp(argv[1],"--check-build");
    if(!archive && !current){fputs("Offline file checks only; acquisition disabled.\n",stderr);return 2;}
    NSString *build=@(argv[2]);A23ReadOnlyScopeVerifier *v=archive?[[A23ReadOnlyScopeVerifier alloc] initWithArchive:build]:[[A23ReadOnlyScopeVerifier alloc] initWithBuild:build];
    if(!(archive?[v verifyArchive]:[v verifyCore]))return 2;
    NSData *r=[NSJSONSerialization dataWithJSONObject:@{@"scope":v.scope,@"verifier":v.result} options:NSJSONWritingSortedKeys error:NULL];
    fwrite(r.bytes,1,r.length,stdout);puts("");return 0;
}}
'''

def generated(source,d):
    old,_=base.generated(source,d)
    result={n:v.decode() for n,v in old.items()}
    # Preserve old spent417 history names; only the prospective model namespace
    # and aligned range move. No directory at this embedded path is created.
    for name,s in list(result.items()):
        s=s.replace(base.SCOPE_SCHEMA,SCHEMA)
        s=s.replace('block-00417','block-00465')
        s=re.sub(r'\b(417|464|465)\b',lambda m:{'417':'465','464':'512','465':'513'}[m[0]],s)
        result[name]=s
    s=result['live_scope.m']
    s=s.replace('@"spent321",@"spent369"]','@"spent321",@"spent369",@"spent417"]').replace('_roots.count==12','_roots.count==13')
    s=s.replace('([name hasPrefix:@"spent369/"]?_roots[@"spent369"]:_roots[@"records"])','([name hasPrefix:@"spent369/"]?_roots[@"spent369"]:([name hasPrefix:@"spent417/"]?_roots[@"spent417"]:_roots[@"records"]))')
    s=s.replace('@"spent369":at(records.stringByDeletingLastPathComponent,@"spent369")}','@"spent369":at(records.stringByDeletingLastPathComponent,@"spent369"),@"spent417":at(records.stringByDeletingLastPathComponent,@"spent417")}')
    s=s.replace('@"formal_issuance_available":@YES,@"acquisition_mode_implemented":@YES,@"hardware_entry_enabled":@YES','@"formal_issuance_available":@NO,@"acquisition_mode_implemented":@NO,@"hardware_entry_enabled":@NO')
    s='#import "a23_terminal_observation.h"\n#ifdef A23_EXPORT_MODEL_FIXTURE\nextern void A23Live132TerminalWorkerStarted(void);\nextern void A23Live132TerminalPoll(void);\n#endif\n'+s
    s=s.replace('A23InterepochGuard *_between;}','A23InterepochGuard *_between;A23TerminalObservation *_terminal;dispatch_queue_t _guardQueue;BOOL _terminalStarted;}')
    s=s.replace('- (void)configureGuardQueue:(dispatch_queue_t)q {','- (void)configureGuardQueue:(dispatch_queue_t)q {\n    _guardQueue=q;')
    begin=s.index('- (void)tick {',s.index('@implementation A23VerifiedEntryCoordinator'));end=s.index('- (BOOL)finalizeOnce',begin)
    s=s[:begin]+TICK+'\n'+s[end:]
    s=s.replace('- (NSArray<NSDictionary *> *)liveFailureSnapshots',COORD+'\n- (NSArray<NSDictionary *> *)liveFailureSnapshots')
    s=s.replace('if([_between.result[@"busy"] boolValue])return NO;','if([_between.result[@"busy"] boolValue] || _terminal.busy)return NO;')
    s=s.replace('if([_between.result[@"busy"] boolValue])return @','if([_between.result[@"busy"] boolValue] || _terminal.busy)return @')
    s=s.replace('@"verification_pending":@YES,@"interepoch_guard":_between.result}', '@"verification_pending":@YES,@"interepoch_guard":_between.result,@"terminal_guard":_terminal.result?:@{}}')
    s=s.replace('@"interepoch_guard":_between.result?:@{}};','@"interepoch_guard":_between.result?:@{},@"terminal_guard":_terminal.result?:@{}};')
    result['live_scope.m']=s
    driver=result['live_driver.m'];begin=driver.index('    if(_complete){',driver.index('- (void)poll {'));end=driver.index('    if(!_pending)',begin)
    driver=driver[:begin]+'    if(_complete)return; // Terminal adapter owns observation completion.\n'+driver[end:]
    driver=driver.replace('A23ThreeEpochSDKDriver *_hold;','A23ThreeEpochSDKDriver *_hold;BOOL _terminalHealthStarted,_terminalAckAttempted;NSDictionary *_terminalProof;')
    driver=driver.replace('- (void)requestStop {',DRIVER+'\n- (void)requestStop {')
    driver=driver.replace('@"observation_complete":@(_settled),','@"terminal_service_window":_terminalProof?:@{},@"observation_complete":@(_settled),')
    result['live_driver.m']=driver
    result['live_entry.m']=result['live_entry.m'].replace('- (void)requestExit {',ENTRY+'\n- (void)requestExit {')
    result['a23_three_epoch_sdk_driver.h']+='\n'+API.split('@interface A23TwoEpochEntry')[0]
    result['a23_two_epoch_entry.h']+='\n@interface A23TwoEpochEntry'+API.split('@interface A23TwoEpochEntry')[1]
    result['a23_guard_cadence_api.h']+='\n@interface A23VerifiedEntryCoordinator (A23TerminalQueue)\n- (NSDictionary * _Nonnull)terminalGuardResult;\n- (BOOL)terminalExitAllowed;\n@end\n'
    permit=result['live_permit.m'].replace('else if(![_root isEqual:@"'+str(w.ROOT/'private/sequence-reservations48-513')+'"])return nil;','else return nil;')
    # The namespace path replacement above is followed by numeric rebasing.
    permit=re.sub(r'else if\(!\[_root isEqual:@"[^"]+"\]\)return nil;', 'else return nil;',permit)
    permit=permit.replace('flag(_scope[@"hardware_entry_enabled"],YES)','flag(_scope[@"hardware_entry_enabled"],NO)').replace('flag(_scope[key],YES)','flag(_scope[key],NO)')
    result['live_permit.m']=permit
    result['fixed48.py']=result['fixed48.py'].replace("v['hardware_entry_enabled'] is True","v['hardware_entry_enabled'] is False")
    # Hardware workflow is deliberately absent; the command-line binary has
    # only file check modes and the native formal permit always rejects.
    result['workflow.py']='raise RuntimeError("offline terminal adapter: no acquisition workflow")\n'
    result['live_main.m']=MAIN
    result['interepoch_exit.h']+='''
static BOOL A23TerminalExitAllowed(NSDictionary *loop,NSDictionary *guard,NSDictionary *terminal) {
    return A23InterepochExitAllowed(loop,guard) && (!terminal.count ||
        (![terminal[@"busy"] boolValue] && [terminal[@"verifier_on_serial_queue"] boolValue] &&
         ([terminal[@"phase"] isEqual:@"passed"] || [terminal[@"phase"] isEqual:@"failed"])));
}
'''
    result['live_export.m']=result['live_export.m'].replace('exportFiles(_directory,@"live-failure",[self files:r])',
        'exportFiles(_directory,@"live-failure",[self failureFiles:r])')
    result['live_export.m']=result['live_export.m'].replace('- (void)fail:(NSDictionary *)r {', '''
- (NSDictionary *)failureFiles:(NSDictionary *)r {
    NSMutableDictionary *files=[[self files:r] mutableCopy];files[@"terminal-boundary.json"]=_target.exportEvidence;return files;
}
- (void)fail:(NSDictionary *)r {''')
    result['sdk_analysis.py']=result['sdk_analysis.py'].replace("read(root/'result.json',16384)","read(root/'result.json',262144)").replace('read(folder/n,32768)','read(folder/n,524288)')
    bound=dict(schema='A23-live132-terminal-offline-candidate-1',source_closure_sha256=d['workflow_source_sha256'],
        descriptor_inputs_sha256=sha(encode(d)),parent_manifest_sha256=PARENT_SUM,generated_scope_sha256=sha(s.encode()),
        controller_sha256=sha(result['live_export.m'].encode()),entry_main_sha256=sha(MAIN.encode()),
        terminal_adapter_sha256=sha(driver.encode()),transaction_count=128,model_only=True)
    result['a23_checked_export_binding.h']=checked.binding_header(bound).decode()
    result['export_analysis.py']=result['export_analysis.py'].replace('A23-live126-interepoch-candidate-1',bound['schema']).replace("bound['model_only'] is False","bound['model_only'] is True")
    return {n:v.encode() for n,v in result.items()},bound

def command(build,fixture=None):
    cmd=base.command(build,fixture);root=Path(build)/'source/research/usb-ds-iso/host'
    at=cmd.index('-o');cmd[at:at]=[str(root/'a23_terminal_observation.m'),str(root/'a23_service_observation.c')]
    return cmd

def build(output):
    output=w.canonical(output);require(not output.exists(),'fresh offline132 build required')
    d,saved,hist,index,_=inputs();gen,_=generated(w.b.REPO,d);d['generated_hashes']={n:sha(v) for n,v in gen.items()};output.mkdir(mode=0o700)
    for n,v in [('descriptor.json',encode(d)),('a23_verified_binding.h',base.HEADER(d)),('a23_checked_export_binding.h',gen['a23_checked_export_binding.h'])]:w.card.put(output,n,v)
    for n in d['source_hashes']:w.card.put(output,'source/'+n,w.plain(w.b.REPO/n))
    for group,items in [('baseline',saved),('history',hist),('recovery-index',index),('generated',gen)]:
        for n,v in items.items():w.card.put(output,group+'/'+n,v)
    cmd=command(output);p=subprocess.run(cmd,capture_output=True,timeout=60)
    w.card.put(output,'compile.log',p.stdout+p.stderr);w.write(output/'build-command.json',dict(command=cmd,returncode=p.returncode,creator_wait_verified=True))
    require(p.returncode==0,'offline132 compile failed')
    w.write(output/'binary.json',dict(schema='A23-verified-entry-binary-1',receiver_sha256=sha(w.plain(output/'verified-entry',64*1024*1024)),descriptor_sha256=sha(encode(d))))
    require(inputs()[0]=={k:v for k,v in d.items() if k!='generated_hashes'},'132 inputs drift');w.b.seal(output);return verify(output)

def verify(build,current=True):
    build=Path(build);files=w.card.seal_verify(build);d=w.load(build/'descriptor.json')
    require(d['description']==DESCRIPTION and len(d['source_hashes'])==662,'descriptor differs')
    if current:require(inputs()[0]=={k:v for k,v in d.items() if k!='generated_hashes'},'current132 differs')
    gen,_=generated(build/'source',{k:v for k,v in d.items() if k!='generated_hashes'})
    require(d['generated_hashes']=={n:sha(v) for n,v in gen.items()},'generated drift')
    require(w.plain(build/'a23_verified_binding.h')==base.HEADER(d) and w.plain(build/'a23_checked_export_binding.h')==gen['a23_checked_export_binding.h'],'binding drift')
    expected={'descriptor.json','a23_verified_binding.h','a23_checked_export_binding.h','verified-entry','binary.json','compile.log','build-command.json'}
    for group,items in [('source',d['source_hashes']),('baseline',d['baseline_files']),('history',d['history_files']),('recovery-index',d['recovery_index']),('generated',d['generated_hashes'])]:
        for n,h in items.items():expected.add(group+'/'+n);require(sha(w.plain(build/group/n,64*1024*1024))==h,'input drift')
    require(set(files)==expected,'inventory differs')
    require(w.load(build/'binary.json')==dict(schema='A23-verified-entry-binary-1',receiver_sha256=sha(w.plain(build/'verified-entry',64*1024*1024)),descriptor_sha256=sha(w.plain(build/'descriptor.json'))),'binary drift')
    return dict(directory=str(build),manifest_sha256=sha(w.plain(build/'SHA256SUMS')),entries=len(files))

def scope(build):
    verify(build);d=w.load(Path(build)/'descriptor.json');record=w.load(Path(build)/'binary.json')
    return dict(schema=SCHEMA,**{k:d[k] for k in ('baseline_manifest_sha256','baseline_inventory_sha256','workflow_source_sha256','device_binding_sha256','recipe_sha256','history_sha256')},
        build_manifest_sha256=sha(w.plain(Path(build)/'SHA256SUMS')),receiver_sha256=record['receiver_sha256'],first_sequence=465,last_sequence=512,
        formal_issuance_available=False,acquisition_mode_implemented=False,hardware_entry_enabled=False)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);print(json.dumps(build(p.parse_args().output)))
