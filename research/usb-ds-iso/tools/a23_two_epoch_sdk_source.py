"""Pure reviewed derivation of a DISTINCT SDK driver from frozen offline core.

Never edits or runs the offline core. SDK bytes keep their original source tags;
SDK resource liveness, unused adoption, observation and receipt gates are added.
"""

HELPERS='''
static BOOL sdkHealthy(id<A23PairedResources> resources,BOOL unused) {
    if(![resources conformsToProtocol:@protocol(A23PairedResources)] || resources.offlineSimulation || !resources.sdkResources)return NO;
    NSDictionary *r=resources.result;
    if(![r isKindOfClass:NSDictionary.class] || ![r[@"schema"] isEqual:@"A23-paired-resource-result-1"] || ![r[@"execution_mode"] isEqual:@"sdk_capability"])return NO;
    for(NSString *k in @[@"ready",@"service_retained"]){id v=r[k];if(![v isKindOfClass:NSNumber.class] || CFGetTypeID((__bridge CFTypeRef)v)!=CFBooleanGetTypeID() || ![v boolValue])return NO;}
    for(NSString *k in @[@"closed_unused",@"poisoned",@"interest_seen",@"hardware_entry_enabled",@"hardware_verified",@"callback_drain_verified",@"continuation_save_verified"]){id v=r[k];if(![v isKindOfClass:NSNumber.class] || CFGetTypeID((__bridge CFTypeRef)v)!=CFBooleanGetTypeID() || [v boolValue])return NO;}
    if(!number(r[@"store_count"]) || [r[@"store_count"] unsignedIntegerValue]!=4)return NO;
    NSDictionary *limits=@{@"iso_attempts":@2,@"trigger_attempts":@2,@"status_reads":@4,@"frame_reads":@2,@"aborts":@1};
    for(NSString *k in limits)if(!number(r[k]) || [r[k] unsignedLongLongValue]>(unused ? 0 : [limits[k] unsignedLongLongValue]))return NO;
    if(unused){id touched=r[@"runtime_touched"];if(![touched isKindOfClass:NSNumber.class] || CFGetTypeID((__bridge CFTypeRef)touched)!=CFBooleanGetTypeID() || [touched boolValue])return NO;
        for(NSString *k in @[@"iso_callbacks",@"control_callbacks"]){NSArray *rows=r[k];if(![rows isKindOfClass:NSArray.class] || rows.count!=2)return NO;for(id v in rows)if(!number(v) || [v unsignedLongLongValue])return NO;}}
    return YES;
}
'''

OBSERVATION='''    if(_complete){
        if(!_settled){uint64_t now=_clock.nowTicks,ns=0;
            if(!_quietSince || now<_quietSince || !A23TicksToNanoseconds(now-_quietSince,_clock.numerator,_clock.denominator,&ns)){[self stop:@"observation_clock"];return;}
            if(ns>=250000000 && [self emit:@"observation_complete" details:@{@"quiet_start_ticks":@(_quietSince),@"quiet_end_ticks":@(now),@"minimum_ns":@250000000}] && [self guard]){_settled=YES;_settledAt=now;}
        }return;
    }'''

RECEIPT='''- (BOOL)saveReceiptOnce {
    dispatch_assert_queue(_queue);[self guard];
    if(!_started || _receiptAttempted || (!_settled && !_stopped))return NO;
    _receiptAttempted=YES;NSDictionary *snapshot=self.result;
    NSData *state=[NSJSONSerialization dataWithJSONObject:snapshot options:NSJSONWritingSortedKeys error:NULL];
    NSDictionary *receipt=@{@"schema":@"A23-two-epoch-sdk-receipt-1",@"execution_mode":@"sdk_observation",@"binding":_binding,
        @"snapshot":snapshot,@"snapshot_sha256":sha(state),@"hardware_verified":@NO,@"hardware_entry_enabled":@NO,@"physical_run_authenticated":@NO};
    NSData *raw=[NSJSONSerialization dataWithJSONObject:receipt options:NSJSONWritingSortedKeys error:NULL];
    if(!raw || !saveDirectory(_directory,@"sdk-receipt",@{@"receipt.json":raw,@"snapshot.json":state})){[self stop:@"receipt_save_failed"];return NO;}
    _receiptSnapshot=state;
    NSData *current=[NSJSONSerialization dataWithJSONObject:self.result options:NSJSONWritingSortedKeys error:NULL];
    if(![state isEqual:current]){_receiptStale=YES;[self stop:@"receipt_changed_during_save"];return NO;}
    _receiptSaved=YES;return YES;
}
- (NSDictionary *)receiptStatus {
    dispatch_assert_queue(_queue);NSDictionary *current=self.result;
    if(_receiptSnapshot){NSData *raw=[NSJSONSerialization dataWithJSONObject:current options:NSJSONWritingSortedKeys error:NULL];if(![raw isEqual:_receiptSnapshot])_receiptStale=YES;}
    return @{@"schema":@"A23-two-epoch-sdk-receipt-status-1",@"attempted":@(_receiptAttempted),@"saved":@((BOOL)(_receiptSaved && !_receiptStale)),@"stale":@(_receiptStale),@"hardware_verified":@NO};
}
'''


def render(base):
    def replace(old,new):
        nonlocal base
        if old not in base:raise ValueError('derivation anchor missing: '+old[:100])
        base=base.replace(old,new)
    replace('#import "a23_two_epoch_receiver.h"','#import "a23_two_epoch_sdk_driver.h"')
    replace('A23TwoEpochReceiver','A23TwoEpochSDKDriver')
    replace('id<A23TwoEpochResources>','id<A23PairedResources>')
    replace('!resources.offlineSimulation','!sdkHealthy(resources,YES)')
    replace('Offline two-epoch capability and aligned unallocated model range required','Unused paired SDK capability and bounded aligned range required')
    replace('mock_control_reply','sdk_control_reply');replace('mock_frame_number','sdk_frame_number')
    replace('A23BudgetTransport','A23SDKBudgetTransport')
    replace('offline_simulation','sdk_observation')
    for old,new in [('A23-two-epoch-event-1','A23-two-epoch-sdk-event-1'),('A23-two-epoch-bundle-1','A23-two-epoch-sdk-bundle-1'),('A23-two-epoch-result-1','A23-two-epoch-sdk-result-1')]:replace(old,new)
    replace('static BOOL replyValid(',HELPERS+'\nstatic BOOL replyValid(')
    replace('static BOOL save(NSString *parent,NSUInteger epoch,NSDictionary<NSString *,NSData *> *files)',
            'static BOOL saveDirectory(NSString *parent,NSString *name,NSDictionary<NSString *,NSData *> *files)')
    replace('    NSString *name=[NSString stringWithFormat:@"epoch-%lu",(unsigned long)epoch];\n','')
    replace('save(_directory,_epoch,','saveDirectory(_directory,[NSString stringWithFormat:@"epoch-%lu",(unsigned long)_epoch],')
    replace('atomic_bool _triggerEntered[2],_invalidIngress;','atomic_bool _triggerEntered[2],_invalidIngress;\n    BOOL _settled,_receiptAttempted,_receiptSaved,_receiptStale;uint64_t _quietSince,_settledAt;NSData *_receiptSnapshot;')
    replace('_stopped=YES;_complete=NO;if','_stopped=YES;_complete=NO;_settled=NO;if')
    replace('_journalFailed=YES;_stopped=YES;_complete=NO;','_journalFailed=YES;_stopped=YES;_complete=NO;_settled=NO;')
    replace('- (BOOL)guard {','- (BOOL)guard {\n    if(!sdkHealthy(_resources,NO))[self stop:@"paired_resource_fault"];')
    replace('!number(sample[@"current_frame"])','!number(sample[@"frame_time"]) || ![sample[@"frame_time"] unsignedLongLongValue] ||\n        !number(sample[@"current_frame"])')
    replace('    if(_complete)return;',OBSERVATION)
    replace('if(_epoch==2){_complete=YES;[self emit:@"complete" details:@{@"saved_epochs":@2}];}',
            'if(_epoch==2){_complete=YES;if([self emit:@"epochs_saved" details:@{@"saved_epochs":@2}] && [self guard])_quietSince=_clock.nowTicks;}')
    replace('- (NSDictionary *)result {',RECEIPT+'\n- (NSDictionary *)result {')
    replace('@"complete":@(_complete),','@"complete":@((BOOL)(_complete && _settled && !_stopped)),@"epochs_saved_complete":@(_complete),\n        @"observation_complete":@(_settled),@"quiet_start_ticks":@(_quietSince),@"quiet_end_ticks":@(_settledAt),@"lease":_resources.result,')
    return '// SDK derivative of the frozen offline engine; a23_two_epoch_sdk_source.py verifies every derivation.\n'+base


ANALYSIS_HELPERS='''
def sdk_lease(lease):
    require(type(lease) is dict and lease.get('schema')=='A23-paired-resource-result-1' and lease.get('execution_mode')=='sdk_capability','SDK lease mode differs')
    for k in ('ready','runtime_touched','service_retained'):require(lease.get(k) is True,'SDK lifetime missing: '+k)
    for k in ('closed_unused','poisoned','interest_seen','continuation_save_verified','callback_drain_verified','hardware_entry_enabled','hardware_verified'):require(lease.get(k) is False,'SDK uncertainty/claim: '+k)
    for k,v in dict(iso_attempts=2,trigger_attempts=2,status_reads=4,frame_reads=2,aborts=0,store_count=4).items():require(integer(lease.get(k),v,v),'SDK count differs: '+k)
    for k in ('iso_callbacks','control_callbacks'):
        r=lease.get(k);require(type(r) is list and len(r)==2 and all(integer(v,1,1) for v in r),'SDK callback count differs')


def sdk_receipt(root,result):
    status=load(read(root/'receipt-status.json',16384))
    require(type(status) is dict and status.get('schema')=='A23-two-epoch-sdk-receipt-status-1' and status.get('attempted') is True and status.get('saved') is True and status.get('stale') is False and status.get('hardware_verified') is False,'SDK receipt not current/saved')
    folder=root/'sdk-receipt';require(folder.is_dir() and not folder.is_symlink() and {p.name for p in folder.iterdir()}=={'receipt.json','snapshot.json','SHA256SUMS','COMMITTED'},'SDK receipt inventory differs')
    files={n:read(folder/n,32768) for n in ('receipt.json','snapshot.json')};sums=''.join(sha(files[n])+'  '+n+'\\n' for n in sorted(files)).encode()
    require(read(folder/'SHA256SUMS')==sums and read(folder/'COMMITTED',65)==(sha(sums)+'\\n').encode(),'SDK receipt hash differs')
    r=load(files['receipt.json']);snapshot=load(files['snapshot.json'])
    canon=lambda v:json.dumps(v,sort_keys=True,separators=(',',':'))
    require(type(r) is dict and r.get('schema')=='A23-two-epoch-sdk-receipt-1' and r.get('execution_mode')=='sdk_observation' and r.get('hardware_verified') is False and r.get('hardware_entry_enabled') is False and r.get('physical_run_authenticated') is False and r.get('snapshot_sha256')==sha(files['snapshot.json']) and canon(snapshot)==canon(result)==canon(r.get('snapshot')),'SDK snapshot/receipt differs')
    sdk_lease(result.get('lease'));return r

'''


def render_analyzer(base):
    def replace(old,new):
        nonlocal base
        if old not in base:raise ValueError('SDK analysis anchor missing: '+old[:100])
        base=base.replace(old,new)
    replace('Standalone offline two-epoch archive verification; integrity is not provenance.',
            'Standalone supplied SDK two-epoch verification; source labels are not provenance.')
    for old,new in [('mock_control_reply','sdk_control_reply'),('mock_frame_number','sdk_frame_number'),('mock_runtime_budget','sdk_runtime_budget'),
        ('offline_simulation','sdk_observation'),('A23-two-epoch-result-1','A23-two-epoch-sdk-result-1'),('A23-two-epoch-event-1','A23-two-epoch-sdk-event-1'),
        ('A23-two-epoch-bundle-1','A23-two-epoch-sdk-bundle-1'),('A23-two-epoch-analysis-1','A23-two-epoch-sdk-analysis-1'),('offline_chain_complete','supplied_sdk_chain_complete')]:replace(old,new)
    replace('def analyze(root):',ANALYSIS_HELPERS+'\ndef analyze(root):')
    replace("first=result.get('first_sequence');", "receipt=sdk_receipt(root,result)\n    require(result.get('epochs_saved_complete') is True and result.get('observation_complete') is True,'SDK observation incomplete')\n    first=result.get('first_sequence');")
    replace('len(lines)==24','len(lines)==25')
    replace("row.get('event') in ('prepared','complete')", "row.get('event') in ('prepared','epochs_saved','observation_complete')")
    replace("rows[-1]['event']=='complete'", "rows[-1]['event']=='observation_complete'")
    replace("{('prepared',None),('complete',None)}", "{('prepared',None),('epochs_saved',None),('observation_complete',None)}")
    replace('out=[];old=None;old_id=None', '''require(receipt.get('binding')==binding,'SDK receipt binding differs')
    quiet=by['observation_complete',None]['details'];saved=by['epochs_saved',None]
    require(saved['index']==24 and integer(saved['details'].get('saved_epochs'),2,2) and integer(quiet.get('minimum_ns'),250000000,250000000) and integer(quiet.get('quiet_start_ticks'),saved['ticks']) and integer(quiet.get('quiet_end_ticks'),quiet['quiet_start_ticks']) and integer(result.get('quiet_start_ticks'),quiet['quiet_start_ticks'],quiet['quiet_start_ticks']) and integer(result.get('quiet_end_ticks'),quiet['quiet_end_ticks'],quiet['quiet_end_ticks']) and ns(quiet['quiet_end_ticks']-quiet['quiet_start_ticks'])>=250000000,'SDK quiet window differs')
    out=[];old=None;old_id=None;origins=[]''')
    replace("sample.get('source')=='sdk_frame_number' and integer", "sample.get('source')=='sdk_frame_number' and integer(sample.get('frame_time'),1) and integer")
    replace("observation(m.get('after_observation'),max(iso,control))", "observation(m.get('after_observation'),max(iso,control))\n        origins.extend([m['before_observation'].get('injected_fixture'),m['after_observation'].get('injected_fixture'),sample.get('injected_fixture')])")
    replace("return dict(schema='A23-two-epoch-sdk-analysis-1'", "require(all(v is True for v in origins) or all(v is None for v in origins),'SDK origin labels mixed')\n    return dict(input_origin='injected_sdk_model' if all(v is True for v in origins) else 'unverified_sdk_observation',resource_and_epoch_checks=True,observation_window_ns=ns(quiet['quiet_end_ticks']-quiet['quiet_start_ticks']),schema='A23-two-epoch-sdk-analysis-1'")
    return '# SDK-specific validator derived from frozen logic; no record relabeling.\n'+base
