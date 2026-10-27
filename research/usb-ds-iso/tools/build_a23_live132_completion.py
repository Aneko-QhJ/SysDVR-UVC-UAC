"""Offline receiver completion cut: one owner-queue continuation, immutable fact."""
import argparse
import json
import subprocess
from pathlib import Path
import build_a23_live132_terminal as base
import audit_a23_postexport_boundary as prior
import a23_checked_export as checked

w=base.w;sha=base.sha;encode=base.encode;require=base.require
PARENT=w.A/'A23-postexport-boundary-closeout-20261026'
PARENT_SUM='da064c6c8737917145d3f1cb398f5c8753eaa9e48cfd6744156c5309390e8d9e'
NEW=('tools/build_a23_live132_completion.py','tools/audit_a23_live132_completion.py','tools/a23_live132_completion_consumer.py')
SCHEMA='A23-live132-completion-offline48-scope-1'
DESCRIPTION=dict(base.DESCRIPTION,schema='A23-live132-completion-offline-description-1',full_guard_source_count=666,
    completion_owner_queue_handoffs=1,completion_fact_required=True,completion_pending_blocks_exit=True)

def sources():
    require(base.base.core.verify_seal(PARENT)==PARENT_SUM,'boundary closeout drift')
    old=prior.sources();require(len(old)==663 and old==w.load(PARENT/'source-hashes.json'),'old663 drift')
    return dict(sorted((old|{'research/usb-ds-iso/'+n:sha(w.plain(w.ROOT/n)) for n in NEW}).items()))

def inputs():
    d,saved,hist,index,history=base.inputs()
    d.update(description=DESCRIPTION,source_hashes=sources(),workflow_source_sha256=sha(encode(sources())),parent_manifest_sha256=PARENT_SUM)
    return d,saved,hist,index,history

COMPLETION=r'''
- (BOOL)configureCompletionQueue:(dispatch_queue_t)q {
    if(!q || _completionQueue || _begun)return NO;dispatch_assert_queue(q);_completionQueue=q;return YES;
}
- (NSDictionary *)frozenFiles:(NSDictionary *)values {
    NSMutableDictionary *f=[NSMutableDictionary new];
    for(NSString *n in values){NSData *raw=[values[n] isKindOfClass:NSData.class]?[values[n] copy]:encode(values[n]);if(!raw)return nil;f[n]=raw;}
    return [f copy];
}
- (void)completeOnOwnerQueue {
    dispatch_assert_queue(_completionQueue);_completionContinuations++;
    uint64_t entered=completionNow();checkpoint(@"completion_entered");uint64_t begin=completionNow();
    BOOL disks=payloadManifest([_directory stringByAppendingPathComponent:@"live-final"],_completionFiles)!=nil &&
        payloadManifest([_directory stringByAppendingPathComponent:@"live-acceptance"],_completionAcceptanceFiles)!=nil;
    BOOL healthy=[_target completionHealth];NSDictionary *latest=_target.result,*final=_target.finalStatus;
    BOOL equal=[encode(latest) isEqual:_completionEntry] && [encode(final) isEqual:_completionFinal];
    BOOL cancelled=_completionCancelled || _operatorOffAcknowledged || _exitRequests;
    uint64_t end=completionNow();
    BOOL clock=_completionRequested && entered>=_completionRequested && begin>=entered && end>=begin;
    BOOL accepted=disks && healthy && equal && !cancelled && clock && _completionContinuations==1 &&
        [latest[@"complete"] boolValue] && ![latest[@"stopped"] boolValue] &&
        [final[@"saved"] boolValue] && ![final[@"stale"] boolValue];
    // This is an explicitly historical sampling cut. Later arrivals and IO
    // after this sample are not certified by the fact we are about to write.
    NSDictionary *fact=@{@"schema":@"A23-owner-queue-completion-1",@"binding":_completionBinding,
        @"accepted":@((BOOL)accepted),@"clock":@"CLOCK_MONOTONIC_RAW_ns",
        @"queue_requested_ns":@(_completionRequested),@"continuation_entered_ns":@(entered),
        @"sample_begin_ns":@(begin),@"sample_end_ns":@(end),@"queue_handoffs":@1,
        @"continuations":@(_completionContinuations),@"disk_equal":@((BOOL)disks),
        @"sampled_healthy":@((BOOL)healthy),@"snapshots_equal":@((BOOL)equal),
        @"exit_requests":@(_exitRequests),@"operator_off_acknowledged":@(_operatorOffAcknowledged),
        @"current_entry_complete":@([latest[@"complete"] boolValue]),@"current_entry_stopped":@([latest[@"stopped"] boolValue]),
        @"sampled_entry_sha256":sha(encode(latest)),@"sampled_final_status_sha256":sha(encode(final)),
        @"historical_cut_only":@YES,@"queue_prefix_only":@YES,@"producer_history_authenticated":@NO,
        @"file_freshness_after_last_full_check_verified":@NO,@"future_events_excluded":@NO,
        @"callback_drain_verified":@NO,@"buffer_reuse_verified":@NO,@"hardware_entry_enabled":@NO};
    _completionRecordSaved=exportFiles(_directory,@"live-completion",@{@"completion.json":fact});
    _completionAccepted=accepted && _completionRecordSaved;
    if(!_completionAccepted){
        _completionFailure=_completionRecordSaved?@"completion_sample_rejected":@"completion_record_write";
        _stop();
        if(_operatorOffAcknowledged){_success=NO;_finished=YES;_unresolved=NO;}
        else [self fail:_target.result];
    }else {_success=YES;_finished=YES;}
    _completionPending=NO;
}
- (void)scheduleCompletion:(NSDictionary *)values acceptance:(NSDictionary *)acceptance
    entry:(NSDictionary *)entry final:(NSDictionary *)final manifest:(NSData *)manifest receipt:(NSDictionary *)receipt {
    if(!_completionQueue || _completionAttempted){_stop();[self fail:_target.result];return;}
    dispatch_assert_queue(_completionQueue);_completionAttempted=YES;
    _completionFiles=[self frozenFiles:values];_completionAcceptanceFiles=[self frozenFiles:acceptance];
    _completionEntry=encode(entry);_completionFinal=encode(final);
    NSData *acceptedManifest=payloadManifest([_directory stringByAppendingPathComponent:@"live-acceptance"],_completionAcceptanceFiles);
    if(!_completionFiles || !_completionAcceptanceFiles || !_completionEntry || !_completionFinal || !acceptedManifest){
        _completionFailure=@"completion_inputs";_stop();[self fail:_target.result];return;
    }
    _completionBinding=@{@"candidate_binding_sha256":sha(encode(candidateBinding())),@"entry_binding":entry[@"binding"],
        @"payload_manifest_sha256":sha(manifest),@"acceptance_manifest_sha256":sha(acceptedManifest),
        @"acceptance_receipt_sha256":sha(encode(receipt)),@"entry_snapshot_sha256":sha(_completionEntry),
        @"final_status_sha256":sha(_completionFinal)};
    _completionRequested=completionNow();_completionPending=YES;_completionEnqueues++;
    checkpoint(@"completion_pending");
    dispatch_async(_completionQueue,^{[self completeOnOwnerQueue];});
}
'''

def one(raw,old,new):
    require(raw.count(old)==1,'completion generation anchor '+old[:70]);return raw.replace(old,new)

def generated(source,d):
    gen,_=base.generated(source,d);result={n:v.decode() for n,v in gen.items()}
    for name in result:result[name]=result[name].replace(base.SCHEMA,SCHEMA)
    s=result['live_export.m']
    s=one(s,'@implementation A23CheckedTwoEpochRun {','''
#include <time.h>
static uint64_t completionNow(void){struct timespec t;if(clock_gettime(CLOCK_MONOTONIC_RAW,&t))return 0;return (uint64_t)t.tv_sec*1000000000ULL+t.tv_nsec;}
@implementation A23CheckedTwoEpochRun {
    dispatch_queue_t _completionQueue;
    BOOL _completionAttempted,_completionPending,_completionCancelled,_completionRecordSaved,_completionAccepted;
    NSUInteger _completionEnqueues,_completionContinuations;
    uint64_t _completionRequested;
    NSDictionary *_completionFiles,*_completionAcceptanceFiles,*_completionBinding;
    NSData *_completionEntry,*_completionFinal;NSString *_completionFailure;
''')
    s=one(s,'- (BOOL)begin {if(_begun)return NO;','- (BOOL)begin {if(_begun || !_completionQueue)return NO;')
    s=one(s,'- (void)requestExit {if(_finished)return;++_exitRequests;_stop();}',
        '- (void)requestExit {if(_finished && !_completionPending)return;++_exitRequests;_completionCancelled=YES;_stop();if(_completionPending)[self fail:_target.result];}')
    s=one(s,'if(!_begun || _finished)return;[_target tick];','if(!_begun || _finished || _completionPending)return;[_target tick];')
    s=one(s,'_acceptanceSaved=exportFiles(_directory,@"live-acceptance",@{@"receipt.json":receipt,@"validation-after.json":post});',
        'NSDictionary *acceptance=@{@"receipt.json":receipt,@"validation-after.json":post};\n    _acceptanceSaved=exportFiles(_directory,@"live-acceptance",acceptance);')
    s=one(s,'_success=_finished=YES;', '[self scheduleCompletion:values acceptance:acceptance entry:r final:final manifest:manifest receipt:receipt];')
    s=one(s,'- (NSDictionary *)status {',COMPLETION+'\n- (NSDictionary *)status {')
    s=one(s,'@"schema":@"A23-checked-two-epoch-loop-1",','''@"completion_pending":@(_completionPending),@"completion_attempted":@(_completionAttempted),
        @"completion_dispatches":@(_completionEnqueues),@"completion_continuations":@(_completionContinuations),
        @"completion_record_saved":@(_completionRecordSaved),@"completion_accepted":@(_completionAccepted),
        @"completion_failure":_completionFailure?:@"",@"schema":@"A23-checked-two-epoch-loop-1",''')
    result['live_export.m']=s
    s=result['live_scope.m'];s=one(s,'- (BOOL)validateFinalExport {',r'''
- (BOOL)completionHealth {
    if([_between.result[@"busy"] boolValue] || _terminal.busy || ![_terminal.result[@"accepted"] boolValue])return NO;
    return [_entry terminalHealthPoll] && ![_permit.result[@"stale"] boolValue];
}
- (BOOL)validateFinalExport {''');result['live_scope.m']=s
    header=result['a23_checked_export.h']
    header=one(header,'- (BOOL)validateFinalExport;','- (BOOL)validateFinalExport;\n- (BOOL)completionHealth;')
    header+='\n@interface A23CheckedTwoEpochRun (A23CompletionQueue)\n- (BOOL)configureCompletionQueue:(dispatch_queue_t _Nonnull)queue;\n@end\n'
    result['a23_checked_export.h']=header
    result['interepoch_exit.h']+='''
static BOOL A23CompletionExitAllowed(NSDictionary *loop,NSDictionary *guard,NSDictionary *terminal) {
    return A23TerminalExitAllowed(loop,guard,terminal) && ![loop[@"completion_pending"] boolValue];
}
'''
    bound=dict(schema='A23-live132-completion-offline-candidate-1',source_closure_sha256=d['workflow_source_sha256'],
        descriptor_inputs_sha256=sha(encode(d)),parent_manifest_sha256=PARENT_SUM,
        generated_scope_sha256=sha(result['live_scope.m'].encode()),controller_sha256=sha(result['live_export.m'].encode()),
        entry_main_sha256=sha(result['live_main.m'].encode()),transaction_count=128,model_only=True,
        completion_fact_required=True,completion_owner_queue_handoffs=1)
    result['a23_checked_export_binding.h']=checked.binding_header(bound).decode()
    result['export_analysis.py']=result['export_analysis.py'].replace('A23-live132-terminal-offline-candidate-1',bound['schema'])
    return {n:v.encode() for n,v in result.items()},bound

command=base.command
def build(output):
    output=w.canonical(output);require(not output.exists(),'fresh completion build required')
    d,saved,hist,index,_=inputs();gen,_=generated(w.b.REPO,d);d['generated_hashes']={n:sha(v) for n,v in gen.items()};output.mkdir(mode=0o700)
    for n,v in [('descriptor.json',encode(d)),('a23_verified_binding.h',base.base.HEADER(d)),('a23_checked_export_binding.h',gen['a23_checked_export_binding.h'])]:w.card.put(output,n,v)
    for n in d['source_hashes']:w.card.put(output,'source/'+n,w.plain(w.b.REPO/n))
    for group,items in [('baseline',saved),('history',hist),('recovery-index',index),('generated',gen)]:
        for n,v in items.items():w.card.put(output,group+'/'+n,v)
    cmd=command(output);p=subprocess.run(cmd,capture_output=True,timeout=60)
    w.card.put(output,'compile.log',p.stdout+p.stderr);w.write(output/'build-command.json',dict(command=cmd,returncode=p.returncode,creator_wait_verified=True));require(p.returncode==0,'completion compile failed')
    w.write(output/'binary.json',dict(schema='A23-verified-entry-binary-1',receiver_sha256=sha(w.plain(output/'verified-entry',64*1024*1024)),descriptor_sha256=sha(encode(d))))
    require(inputs()[0]=={k:v for k,v in d.items() if k!='generated_hashes'},'inputs drift');w.b.seal(output);return verify(output)

def verify(build,current=True):
    build=Path(build);files=w.card.seal_verify(build);d=w.load(build/'descriptor.json')
    require(d['description']==DESCRIPTION and len(d['source_hashes'])==666,'completion descriptor differs')
    if current:require(inputs()[0]=={k:v for k,v in d.items() if k!='generated_hashes'},'current completion inputs differ')
    gen,_=generated(build/'source',{k:v for k,v in d.items() if k!='generated_hashes'})
    require(d['generated_hashes']=={n:sha(v) for n,v in gen.items()},'generated completion drift')
    require(w.plain(build/'a23_verified_binding.h')==base.base.HEADER(d) and w.plain(build/'a23_checked_export_binding.h')==gen['a23_checked_export_binding.h'],'header drift')
    expected={'descriptor.json','a23_verified_binding.h','a23_checked_export_binding.h','verified-entry','binary.json','compile.log','build-command.json'}
    for group,items in [('source',d['source_hashes']),('baseline',d['baseline_files']),('history',d['history_files']),('recovery-index',d['recovery_index']),('generated',d['generated_hashes'])]:
        for n,h in items.items():expected.add(group+'/'+n);require(sha(w.plain(build/group/n,64*1024*1024))==h,'group drift')
    require(set(files)==expected,'completion inventory differs')
    require(w.load(build/'binary.json')==dict(schema='A23-verified-entry-binary-1',receiver_sha256=sha(w.plain(build/'verified-entry',64*1024*1024)),descriptor_sha256=sha(w.plain(build/'descriptor.json'))),'binary drift')
    return dict(directory=str(build),manifest_sha256=sha(w.plain(build/'SHA256SUMS')),entries=len(files))

def scope(build):
    verify(build);d=w.load(Path(build)/'descriptor.json');r=w.load(Path(build)/'binary.json')
    return dict(schema=SCHEMA,**{k:d[k] for k in ('baseline_manifest_sha256','baseline_inventory_sha256','workflow_source_sha256','device_binding_sha256','recipe_sha256','history_sha256')},
        build_manifest_sha256=sha(w.plain(Path(build)/'SHA256SUMS')),receiver_sha256=r['receiver_sha256'],first_sequence=465,last_sequence=512,
        formal_issuance_available=False,acquisition_mode_implemented=False,hardware_entry_enabled=False)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);print(json.dumps(build(p.parse_args().output)))
