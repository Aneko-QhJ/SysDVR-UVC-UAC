#import "a23_two_epoch_receiver.h"
#include "../../../source/uvc/iso_probe_protocol.h"
#include <CommonCrypto/CommonDigest.h>
#include <stdatomic.h>
#include <fcntl.h>
#include <errno.h>
#include <sys/stat.h>
#include <unistd.h>

static BOOL fail(NSError **error, NSString *why) {
    if(error)*error=[NSError errorWithDomain:@"A23TwoEpoch" code:1 userInfo:@{NSLocalizedDescriptionKey:why}];
    return NO;
}
static BOOL number(id v) {
    return [v isKindOfClass:NSNumber.class] && CFGetTypeID((__bridge CFTypeRef)v)!=CFBooleanGetTypeID() &&
        !CFNumberIsFloatType((__bridge CFNumberRef)v) && [v compare:@0]!=NSOrderedAscending;
}
static NSString *sha(NSData *data) {
    unsigned char h[32];CC_SHA256(data.bytes,(CC_LONG)data.length,h);
    NSMutableString *s=[NSMutableString new];for(unsigned i=0;i<32;++i)[s appendFormat:@"%02x",h[i]];return s;
}
static id frozenJSON(id v) {
    if(![NSJSONSerialization isValidJSONObject:v])return nil;
    NSData *raw=[NSJSONSerialization dataWithJSONObject:v options:NSJSONWritingSortedKeys error:NULL];
    return raw.length<=16384 ? [NSJSONSerialization JSONObjectWithData:raw options:0 error:NULL] : nil;
}
static BOOL replyValid(NSDictionary *reply, uint64_t lower, uint64_t now) {
    if(![reply isKindOfClass:NSDictionary.class])return NO;
    NSData *raw=reply[@"data"];NSDictionary *o=reply[@"observation"];
    if(![raw isKindOfClass:NSData.class] || raw.length!=168 || ![o isKindOfClass:NSDictionary.class])return NO;
    NSDictionary *c=o[@"control"],*expected=@{@"request_type":@193,@"request":@81,@"value":@0,@"index":@2,@"length":@168,@"timeout_ms":@3000};
    if(![c isKindOfClass:NSDictionary.class] || c.count!=expected.count)return NO;
    for(NSString *k in expected)if(!number(c[k]) || ![c[k] isEqual:expected[k]])return NO;
    id accepted=o[@"accepted"];
    return [o[@"source"] isEqual:@"mock_control_reply"] && [accepted isKindOfClass:NSNumber.class] &&
        CFGetTypeID((__bridge CFTypeRef)accepted)==CFBooleanGetTypeID() && [accepted boolValue] && !o[@"error"] &&
        number(o[@"bytes_transferred"]) && [o[@"bytes_transferred"] unsignedLongLongValue]==168 &&
        number(o[@"begin_ticks"]) && number(o[@"end_ticks"]) && [o[@"begin_ticks"] unsignedLongLongValue]>=lower &&
        [o[@"begin_ticks"] unsignedLongLongValue]<=[o[@"end_ticks"] unsignedLongLongValue] &&
        [o[@"end_ticks"] unsignedLongLongValue]<=now;
}
static BOOL writeFile(int dir,NSString *name,NSData *raw) {
    int fd=openat(dir,name.fileSystemRepresentation,O_CREAT|O_EXCL|O_NOFOLLOW|O_RDWR,0600);
    if(fd<0)return NO;BOOL ok=YES;NSUInteger at=0;
    while(at<raw.length){ssize_t n=write(fd,(const uint8_t *)raw.bytes+at,raw.length-at);
        if(n<0 && errno==EINTR)continue;if(n<=0){ok=NO;break;}at+=(NSUInteger)n;}
    if(ok)ok=fsync(fd)==0;
    NSMutableData *copy=[NSMutableData dataWithLength:raw.length];at=0;
    while(ok && at<raw.length){ssize_t n=pread(fd,(uint8_t *)copy.mutableBytes+at,raw.length-at,(off_t)at);
        if(n<0 && errno==EINTR)continue;if(n<=0){ok=NO;break;}at+=(NSUInteger)n;}
    uint8_t extra;if(ok)ok=pread(fd,&extra,1,(off_t)raw.length)==0 && [copy isEqual:raw];
    if(close(fd)!=0)ok=NO;return ok;
}
// Trusted existing output parent. Partial/colliding children are never retried
// or removed. The caller acknowledges the owner only after this returns YES.
static BOOL save(NSString *parent,NSUInteger epoch,NSDictionary<NSString *,NSData *> *files) {
    int p=open(parent.fileSystemRepresentation,O_RDONLY|O_DIRECTORY|O_NOFOLLOW);if(p<0)return NO;
    NSString *name=[NSString stringWithFormat:@"epoch-%lu",(unsigned long)epoch];
    if(mkdirat(p,name.fileSystemRepresentation,0700)!=0){close(p);return NO;}
    int d=openat(p,name.fileSystemRepresentation,O_RDONLY|O_DIRECTORY|O_NOFOLLOW);
    if(d<0){close(p);return NO;}BOOL ok=YES;NSMutableString *manifest=[NSMutableString new];
    for(NSString *name in [[files allKeys] sortedArrayUsingSelector:@selector(compare:)]){
        if(ok)ok=writeFile(d,name,files[name]);[manifest appendFormat:@"%@  %@\n",sha(files[name]),name];}
    NSData *sums=[manifest dataUsingEncoding:NSUTF8StringEncoding];
    if(ok)ok=writeFile(d,@"SHA256SUMS",sums) && fsync(d)==0;
    if(ok)ok=writeFile(d,@"COMMITTED",[[sha(sums) stringByAppendingString:@"\n"] dataUsingEncoding:NSUTF8StringEncoding]) && fsync(d)==0 && fsync(p)==0;
    if(close(d)!=0)ok=NO;if(close(p)!=0)ok=NO;return ok;
}

@implementation A23TwoEpochReceiver {
    id<A23TwoEpochResources> _resources;id<A23RuntimeClock> _clock;id<A23SessionJournal> _journal;
    dispatch_queue_t _queue;NSString *_directory,*_session;id<A23TransactionTransport> _sharedTransport;
    NSDictionary *_binding;NSArray<NSMutableData *> *_data,*_rows;NSMutableArray<A23TransactionOwner *> *_owners;NSMutableArray *_budgets,*_before,*_after,*_beforeObservation;
    NSMutableArray *_reasons;NSDictionary *_sample;
    uintptr_t _dataAddress[2],_rowAddress[2];uint16_t _first;
    NSUInteger _epoch,_index,_isoAttempts,_triggers,_saves,_aborts;
    BOOL _started,_pending,_stopped,_journalFailed,_complete,_detached,_saveAttempted[2],_abortAttempted,_controlObserved[2];
    uint64_t _preparedAt,_lastSaveTicks,_submittedAt[2],_triggerAt[2];
    atomic_uint _isoCount[2],_controlCount[2];atomic_uint_fast64_t _isoAt[2],_controlAt[2];
    atomic_bool _triggerEntered[2],_invalidIngress;
    A23TwoEpochReceiver *_hold;
}
- (instancetype)initWithResources:(id<A23TwoEpochResources>)resources firstSequence:(uint16_t)first
    directory:(NSString *)directory queue:(dispatch_queue_t)queue clock:(id<A23RuntimeClock>)clock
    journal:(id<A23SessionJournal>)journal error:(NSError **)error {
    if(!resources || !resources.offlineSimulation || !queue || !clock || !journal || !clock.numerator || !clock.denominator ||
        first<81 || first>65504 || first%16!=1 || !directory.isAbsolutePath || [directory rangeOfString:@"\0"].location!=NSNotFound){
        fail(error,@"Offline two-epoch capability and aligned unallocated model range required");return nil;}
    dispatch_assert_queue(queue);
    NSArray<NSMutableData *> *data=[resources.dataStores copy],*rows=[resources.transactionStores copy];
    NSDictionary *identity=frozenJSON(resources.identity),*desc=resources.descriptorBytes;
    BOOL valid=[data isKindOfClass:NSArray.class] && [rows isKindOfClass:NSArray.class] && data.count==2 && rows.count==2 &&
        resources.transport && [identity isKindOfClass:NSDictionary.class] && identity.count==3 && [desc isKindOfClass:NSDictionary.class];
    for(NSString *k in @[@"device_id",@"interface_id",@"parent_device_id"])valid=valid && number(identity[k]) && [identity[k] unsignedLongLongValue]>0;
    valid=valid && [identity[@"device_id"] isEqual:identity[@"parent_device_id"]] && ![identity[@"device_id"] isEqual:identity[@"interface_id"]];
    if(!valid){fail(error,@"Invalid capability containers");return nil;}
    NSMutableDictionary *hashes=[NSMutableDictionary new];
    for(NSString *k in @[@"device_descriptor",@"configuration_descriptor",@"active_interface"]){
        NSData *raw=desc[k];if(![raw isKindOfClass:NSData.class] || raw.length>1024){valid=NO;break;}hashes[k]=sha(raw);}
    if(valid){NSData *active=desc[@"active_interface"];const uint8_t *a=active.bytes;
        valid=A23ValidateDescriptors(desc[@"device_descriptor"],desc[@"configuration_descriptor"],3,error)!=nil &&
            active.length==9 && a[0]==9 && a[1]==4 && a[2]==2 && a[3]==0 && a[4]==1 && a[5]==0xff && a[6]==0x49 && a[7]==1;}
    if(valid){NSArray *all=@[data[0],rows[0],data[1],rows[1]];
        for(NSUInteger i=0;i<4;++i){NSMutableData *x=all[i];valid=valid && [x isKindOfClass:NSMutableData.class] && x.length==(i%2 ? 26880 : 184320);
            if(!valid)break;uintptr_t a=(uintptr_t)x.mutableBytes;valid=a && a<=UINTPTR_MAX-x.length;
            for(NSUInteger j=0;valid && j<i;++j){NSMutableData *y=all[j];uintptr_t b=(uintptr_t)y.mutableBytes;valid=a+x.length<=b || b+y.length<=a;}}}
    if(!valid){fail(error,@"Identity/descriptors or four disjoint fixed-size stores rejected");return nil;}
    if((self=[super init])){
        _resources=resources;_sharedTransport=resources.transport;_clock=clock;_journal=journal;_queue=queue;_directory=[directory copy];_first=first;
        _data=data;_rows=rows;_session=NSUUID.UUID.UUIDString;_preparedAt=clock.nowTicks;
        _binding=@{@"session_id":_session,@"identity":identity,@"descriptor_sha256":hashes,@"first_sequence":@(first),@"execution_mode":@"offline_simulation"};
        _owners=[NSMutableArray new];_budgets=[NSMutableArray arrayWithArray:@[NSNull.null,NSNull.null]];
        _before=[_budgets mutableCopy];_after=[_budgets mutableCopy];_beforeObservation=[_budgets mutableCopy];_reasons=[NSMutableArray new];
        atomic_init(&_invalidIngress,false);
        for(NSUInteger n=0;n<2;++n){
            atomic_init(&_isoCount[n],0);atomic_init(&_controlCount[n],0);atomic_init(&_isoAt[n],0);atomic_init(&_controlAt[n],0);atomic_init(&_triggerEntered[n],false);
            _dataAddress[n]=(uintptr_t)data[n].mutableBytes;_rowAddress[n]=(uintptr_t)rows[n].mutableBytes;
            memset(data[n].mutableBytes,0,data[n].length);
            A23TransactionOwner *owner=[[A23TransactionOwner alloc] initWithData:data[n] transactions:rows[n] queue:queue];
            if(!owner)return nil;[_owners addObject:owner];
            __weak A23TwoEpochReceiver *weak=self;
            [owner observeCompletions:^(NSDictionary *event){
                A23TwoEpochReceiver *s=weak;if(!s)return;
                [s emit:@"iso_callback" details:@{@"epoch":@(n),@"owner":event}];[s guard];
            }];
        }
        if(![self emit:@"prepared" details:@{@"binding":_binding,@"max_epochs":@2,@"lead_frames":@32,
            @"timebase_numerator":@(clock.numerator),@"timebase_denominator":@(clock.denominator)}])return nil;
    }return self;
}
- (BOOL)emit:(NSString *)name details:(NSDictionary *)details {
    if(_journalFailed)return NO;
    NSDictionary *row=@{@"schema":@"A23-two-epoch-event-1",@"session_id":_session,@"index":@(++_index),@"ticks":@(_clock.nowTicks),
        @"event":name,@"details":details,@"execution_mode":@"offline_simulation",@"hardware_verified":@NO,@"hardware_entry_enabled":@NO};
    if(![_journal append:row error:NULL]){_journalFailed=YES;_stopped=YES;_complete=NO;[_reasons addObject:@"journal_failed"];return NO;}return YES;
}
- (void)stop:(NSString *)reason {
    _stopped=YES;_complete=NO;if(![_reasons containsObject:reason]){[_reasons addObject:reason];[self emit:@"stop" details:@{@"reason":reason}];}
}
- (BOOL)guard {
    if(atomic_load(&_invalidIngress))[self stop:@"invalid_callback_ingress"];
    for(NSUInteger n=0;n<2;++n)if(_data[n].length!=184320 || _rows[n].length!=26880 ||
        (uintptr_t)_data[n].mutableBytes!=_dataAddress[n] || (uintptr_t)_rows[n].mutableBytes!=_rowAddress[n]){
        [self stop:@"storage_changed"];break;}
    return !_stopped && !_journalFailed && !_detached;
}
- (BOOL)start {
    dispatch_assert_queue(_queue);if(_started)return NO;_started=YES;_hold=self;
    if(![self guard])return NO;return [self arm];
}
- (BOOL)arm {
    if(![self guard] || _epoch>=2 || _pending || _isoAttempts!=_epoch || _saves!=_epoch)return NO;
    if(![self emit:@"before_intent" details:@{@"epoch":@(_epoch)}] || ![self guard])return NO;
    NSDictionary *reply=[_resources readStatus];uint64_t lower=_epoch ? _lastSaveTicks : _preparedAt;
    if(!replyValid(reply,lower,_clock.nowTicks)){[self stop:@"invalid_before_reply"];return NO;}
    NSData *raw=[reply[@"data"] copy];IsoProbeStatus s;memcpy(&s,raw.bytes,sizeof(s));
    BOOL valid=s.magic==ISO_PROBE_STATUS_MAGIC && s.version==1 && s.endpoint==0x83;
    if(!_epoch)valid=valid && !s.sequence && !s.state && !s.post_result && !s.urb_id && !s.report_id && !s.requested && !s.transferred &&
        !s.urb_status && !s.report_count && !s.report_result && (s.speed==0 || s.speed==3);
    else valid=valid && [raw isEqual:_after[0]];
    if(!valid){[self stop:@"before_state_mismatch"];return NO;}
    NSDictionary *beforeObservation=frozenJSON(reply[@"observation"]);
    if(!beforeObservation){[self stop:@"invalid_before_observation_json"];return NO;}
    _before[_epoch]=raw;_beforeObservation[_epoch]=beforeObservation;
    if(![self emit:@"before" details:@{@"epoch":@(_epoch),@"sha256":sha(raw)}] || ![self guard])return NO;
    NSDictionary *sample=frozenJSON([_resources readFrameSample]);uint64_t now=_clock.nowTicks;
    if(![sample isKindOfClass:NSDictionary.class] || ![sample[@"source"] isEqual:@"mock_frame_number"] ||
        !number(sample[@"current_frame"]) || ![sample[@"current_frame"] unsignedLongLongValue] || [sample[@"current_frame"] unsignedLongLongValue]>UINT64_MAX-32 ||
        !number(sample[@"begin_ticks"]) || !number(sample[@"end_ticks"]) || [sample[@"begin_ticks"] unsignedLongLongValue]<[reply[@"observation"][@"end_ticks"] unsignedLongLongValue] ||
        [sample[@"end_ticks"] unsignedLongLongValue]<[sample[@"begin_ticks"] unsignedLongLongValue] || [sample[@"end_ticks"] unsignedLongLongValue]>now){
        [self stop:@"invalid_frame_sample"];return NO;}
    _sample=sample;
    if(![self emit:@"iso_intent" details:@{@"epoch":@(_epoch),@"sample":sample}] || ![self guard])return NO;
    _pending=YES;_submittedAt[_epoch]=_clock.nowTicks;++_isoAttempts;
    A23BudgetTransport *budget=[[A23BudgetTransport alloc] initWithTransport:_sharedTransport clock:_clock sample:sample];_budgets[_epoch]=budget;
    A23TransactionOwner *owner=_owners[_epoch];
    BOOL accepted=[owner submitTo:self firstFrame:[sample[@"current_frame"] unsignedLongLongValue]+32 finished:^(NSDictionary *e){(void)e;}];
    [self emit:@"iso_return" details:@{@"epoch":@(_epoch),@"accepted":@(accepted),@"budget":budget.result ?: @{}}];
    if(!accepted || ![budget.result[@"budget_pass"] boolValue]){[self stop:@"iso_not_admitted"];return NO;}
    if(![self guard] || atomic_load(&_isoCount[_epoch])){[self stop:@"iso_arrived_before_trigger"];return NO;}
    if(![self emit:@"trigger_intent" details:@{@"epoch":@(_epoch),@"first_sequence":@(_first+_epoch*16)}] || ![self guard])return NO;
    uint64_t gap=0,age=0;now=_clock.nowTicks;uint64_t returned=[budget.result[@"return_ticks"] unsignedLongLongValue],begin=[sample[@"begin_ticks"] unsignedLongLongValue];
    if(now<returned || now<begin || !A23TicksToNanoseconds(now-returned,_clock.numerator,_clock.denominator,&gap) ||
        !A23TicksToNanoseconds(now-begin,_clock.numerator,_clock.denominator,&age) || gap>8000000 || age>32000000){[self stop:@"trigger_budget"];return NO;}
    NSUInteger n=_epoch;_triggerAt[n]=now;++_triggers;atomic_store(&_triggerEntered[n],true);NSError *error=nil;
    BOOL triggered=[_resources enqueueBurst:(uint16_t)(_first+n*16) completion:^(IOReturn status,NSUInteger bytes){
        uint64_t arrival=self->_clock.nowTicks;unsigned count=atomic_fetch_add(&self->_controlCount[n],1)+1;
        if(count==1)atomic_store(&self->_controlAt[n],arrival);
        if(count!=1 || status || bytes)atomic_store(&self->_invalidIngress,true);
        dispatch_async(self->_queue, ^{self->_controlObserved[n]=YES;[self emit:@"control_callback" details:@{@"epoch":@(n),@"count":@(count),@"status":@((uint32_t)status),@"bytes":@(bytes),@"arrival_ticks":@(arrival)}];[self guard];});
    } error:&error];
    [self emit:@"trigger_return" details:@{@"epoch":@(n),@"accepted":@(triggered),@"gap_ns":@(gap),@"age_ns":@(age)}];
    if(!triggered || error)[self stop:@"trigger_rejected"];return triggered && [self guard];
}
- (BOOL)enqueueIORequestWithData:(NSMutableData *)data transactionList:(IOUSBHostIsochronousTransaction *)rows transactionListCount:(NSUInteger)count
    firstFrameNumber:(uint64_t)frame options:(IOUSBHostIsochronousTransferOptions)options error:(NSError **)error
    completionHandler:(IOUSBHostIsochronousTransactionCompletionHandler)completion {
    dispatch_assert_queue(_queue);NSUInteger n=_epoch;
    if(n>=2 || ![self guard] || !_pending || data!=_data[n] || (uintptr_t)rows!=_rowAddress[n] || count!=960 || options ||
        frame!=[_sample[@"current_frame"] unsignedLongLongValue]+32 || !completion)return fail(error,@"Fixed two-epoch ISO tuple rejected");
    for(unsigned i=0;i<960;++i)if(rows[i].status!=kIOReturnInvalid || rows[i].requestCount!=192 || rows[i].offset!=i*192 || rows[i].completeCount || rows[i].timeStamp || rows[i].options)return fail(error,@"Initializer rejected");
    return [_budgets[n] enqueueIORequestWithData:data transactionList:rows transactionListCount:count firstFrameNumber:frame options:options error:error
        completionHandler:^(IOReturn status,IOUSBHostIsochronousTransaction *pointer){
            unsigned calls=atomic_fetch_add(&self->_isoCount[n],1)+1;
            if(calls==1)atomic_store(&self->_isoAt[n],self->_clock.nowTicks);
            if(calls!=1 || status || (uintptr_t)pointer!=self->_rowAddress[n] || !atomic_load(&self->_triggerEntered[n]))atomic_store(&self->_invalidIngress,true);
            completion(status,pointer);
        }];
}
- (BOOL)abortWithOption:(IOUSBHostAbortOption)option error:(NSError **)error {
    dispatch_assert_queue(_queue);if(!_abortAttempted || _aborts || _epoch>=2 || option!=IOUSBHostAbortOptionAsynchronous)return NO;
    ++_aborts;return [_budgets[_epoch] abortWithOption:option error:error];
}
- (BOOL)elapsed:(uint64_t)start arrival:(uint64_t)arrival limit:(uint64_t)limit {
    uint64_t end=arrival ?: _clock.nowTicks,ns=0;
    return !start || end<start || !A23TicksToNanoseconds(end-start,_clock.numerator,_clock.denominator,&ns) || (arrival ? ns>limit : ns>=limit);
}
- (BOOL)verifySnapshot:(NSDictionary *)e {
    if(![self guard] || ![e isKindOfClass:NSDictionary.class] || !number(e[@"overall_u32"]) || [e[@"overall_u32"] unsignedIntValue] ||
        [e[@"callback_pointer_mismatch"] boolValue] || [e[@"timed_out"] boolValue])return NO;
    NSData *raw=e[@"raw"],*tx=e[@"transactions"];
    if(raw.length!=184320 || tx.length!=26880)return NO;
    const uint8_t *p=raw.bytes;const IOUSBHostIsochronousTransaction *rows=tx.bytes;unsigned packet=0;
    for(unsigned i=0;i<960;++i){
        if(rows[i].status || rows[i].requestCount!=192 || rows[i].offset!=i*192 || rows[i].options || (rows[i].completeCount && rows[i].completeCount!=192))return NO;
        if(rows[i].completeCount){if(packet>=16)return NO;uint16_t seq=(uint16_t)(_first+_epoch*16+packet);
            for(unsigned j=0;j<192;++j)if(p[i*192+j]!=isoProbeByte(seq,j))return NO;++packet;}
    }return packet==16;
}
- (void)poll {
    dispatch_assert_queue(_queue);if(!_started)return;[self guard];
    if(_epoch<2 && _pending){
        if([self elapsed:_submittedAt[_epoch] arrival:atomic_load(&_isoAt[_epoch]) limit:2000000000])[self stop:@"iso_deadline"];
        if(_triggerAt[_epoch] && [self elapsed:_triggerAt[_epoch] arrival:atomic_load(&_controlAt[_epoch]) limit:16000000])[self stop:@"control_deadline"];
    }
    if(_stopped){
        if(_epoch<2 && _pending && !_detached && !_journalFailed && !_abortAttempted && !atomic_load(&_isoCount[_epoch]) && [_owners[_epoch] state]==A23TransactionPending){
            if([self emit:@"abort_intent" details:@{@"epoch":@(_epoch)}]){_abortAttempted=YES;[_owners[_epoch] deadlineReached];}}
        return;
    }
    if(_complete)return;
    if(!_pending){[self arm];return;}
    A23TransactionOwner *owner=_owners[_epoch];
    if(owner.state!=A23TransactionCompleted || owner.callbackCount!=1 || !_controlObserved[_epoch] || atomic_load(&_controlCount[_epoch])!=1)return;
    if(![self verifySnapshot:owner.evidence]){[self stop:@"invalid_payload_or_transactions"];return;}
    if(![self emit:@"after_intent" details:@{@"epoch":@(_epoch)}] || ![self guard])return;
    NSDictionary *reply=[_resources readStatus];uint64_t lower=MAX(atomic_load(&_isoAt[_epoch]),atomic_load(&_controlAt[_epoch]));
    if(!replyValid(reply,lower,_clock.nowTicks)){[self stop:@"invalid_after_reply"];return;}
    NSData *raw=[reply[@"data"] copy];IsoProbeStatus s;IsoProbeBurstContextDiagnostics d;
    memcpy(&s,raw.bytes,sizeof(s));memcpy(&d,&s.diagnostics,sizeof(d));
    BOOL valid=s.magic==ISO_PROBE_STATUS_MAGIC && s.version==1 && s.sequence==_first+_epoch*16 && s.state==ISO_PROBE_COMPLETE &&
        !s.post_result && s.urb_id && s.urb_id==s.report_id && s.requested==3072 && s.transferred==3072 && s.urb_status==3 &&
        s.speed==3 && s.endpoint==0x83 && s.report_count==1 && !s.report_result && d.magic==ISO_PROBE_BURST_INTERVAL_MAGIC &&
        d.terminal==1 && d.completed_bitmap==65535 && d.actual_sum==3072 && d.context_valid==1 && d.frame_select_mfi<16384 &&
        ((d.first_control>>10)&63)==5 && !(d.first_control>>31) && ((d.first_control>>20)&2047)==(((d.frame_select_mfi>>3)+32)&2047);
    if(_epoch){IsoProbeStatus old;memcpy(&old,[_after[0] bytes],sizeof(old));valid=valid && old.urb_id!=s.urb_id;}
    if(!valid){[self stop:@"status_urb_or_iso7_mismatch"];return;}
    _after[_epoch]=raw;NSDictionary *afterObservation=frozenJSON(reply[@"observation"]);
    if(!afterObservation){[self stop:@"invalid_after_observation_json"];return;}
    if(![self emit:@"save_intent" details:@{@"epoch":@(_epoch)}] || ![self guard] || _saveAttempted[_epoch])return;
    _saveAttempted[_epoch]=YES;
    NSDictionary *metadata=@{@"schema":@"A23-two-epoch-bundle-1",@"binding":_binding,@"epoch":@(_epoch),@"first_sequence":@(_first+_epoch*16),
        @"execution_mode":@"offline_simulation",@"hardware_verified":@NO,@"hardware_entry_enabled":@NO,@"device_trace_verified":@NO,
        @"before_observation":_beforeObservation[_epoch],@"after_observation":afterObservation,
        @"sample":_sample,@"first_frame":owner.evidence[@"first_frame"],@"budget":[_budgets[_epoch] result],@"overall_u32":owner.evidence[@"overall_u32"],
        @"callback_count":@(owner.callbackCount),@"submit_ticks":@(_submittedAt[_epoch]),@"trigger_ticks":@(_triggerAt[_epoch]),@"control_count":@(atomic_load(&_controlCount[_epoch])),@"iso_arrival_ticks":@(atomic_load(&_isoAt[_epoch])),@"control_arrival_ticks":@(atomic_load(&_controlAt[_epoch]))};
    NSData *json=[NSJSONSerialization dataWithJSONObject:metadata options:NSJSONWritingSortedKeys error:NULL];
    if(!json || !save(_directory,_epoch,@{@"raw.bin":owner.evidence[@"raw"],@"transactions.bin":owner.evidence[@"transactions"],@"before.bin":_before[_epoch],@"after.bin":raw,@"metadata.json":json})){
        [self stop:@"save_failed"];return;}
    if(![self guard] || ![self emit:@"saved" details:@{@"epoch":@(_epoch),@"metadata_sha256":sha(json)}] || ![self guard])return;
    if(![owner acknowledgeEvidenceSaved]){[self stop:@"owner_ack_failed"];return;}
    ++_saves;_lastSaveTicks=_clock.nowTicks;_pending=NO;++_epoch;
    if(_epoch==2){_complete=YES;[self emit:@"complete" details:@{@"saved_epochs":@2}];}
    // Do not arm here. A later serial-queue poll observes pending old callbacks.
}
- (void)requestStop {dispatch_assert_queue(_queue);[self stop:@"exit_requested"];[self poll];}
- (void)detachedRegistryID:(uint64_t)registryID {
    dispatch_assert_queue(_queue);NSDictionary *identity=_binding[@"identity"];
    if(registryID==[identity[@"device_id"] unsignedLongLongValue] || registryID==[identity[@"interface_id"] unsignedLongLongValue]){_detached=YES;[self stop:@"detached"];}
}
- (NSDictionary *)result {
    dispatch_assert_queue(_queue);[self guard];
    return @{@"schema":@"A23-two-epoch-result-1",@"session_id":_session,@"first_sequence":@(_first),@"execution_mode":@"offline_simulation",
        @"iso_attempts":@(_isoAttempts),@"trigger_attempts":@(_triggers),@"saved_epochs":@(_saves),@"aborts":@(_aborts),
        @"complete":@(_complete),@"stopped":@(_stopped),@"failure_reasons":[_reasons copy],@"journal_failed":@(_journalFailed),
        @"all_stores_retained":@YES,@"shared_resources_retained":@YES,@"callback_drain_verified":@NO,@"device_trace_verified":@NO,
        @"hardware_verified":@NO,@"hardware_entry_enabled":@NO};
}
@end
