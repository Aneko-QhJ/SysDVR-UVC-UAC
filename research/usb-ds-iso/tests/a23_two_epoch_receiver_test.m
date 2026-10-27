#import "../host/a23_two_epoch_receiver.h"
#include "../../../source/uvc/iso_probe_protocol.h"
#include <assert.h>
#include <stdatomic.h>
#include <mach/mach_time.h>

@interface TwoClock : NSObject <A23RuntimeClock>
- (void)advanceNS:(uint64_t)ns;
@end
@implementation TwoClock { mach_timebase_info_data_t _info;atomic_uint_fast64_t _offset; }
- (instancetype)init {if((self=[super init])){mach_timebase_info(&_info);atomic_init(&_offset,0);}return self;}
- (uint64_t)nowTicks {return mach_absolute_time()+atomic_load(&_offset);}
- (uint32_t)numerator {return _info.numer;}
- (uint32_t)denominator {return _info.denom;}
- (void)advanceNS:(uint64_t)ns {atomic_fetch_add(&_offset,(uint64_t)(((__uint128_t)ns*_info.denom+_info.numer-1)/_info.numer));}
@end

@interface TwoResources : NSObject <A23TwoEpochResources,A23TransactionTransport>
@property NSString *fault;
@property TwoClock *clock;
@property NSArray<NSMutableData *> *dataStores,*transactionStores;
@property NSMutableArray *isoCallbacks,*controlCallbacks;
@property NSUInteger submissions,triggers,aborts,statusReads;
@property NSMutableData *lastStatus;
- (void)deliver:(NSUInteger)n;
- (void)oldISO;
- (void)oldControl;
@end
@implementation TwoResources
- (instancetype)init {
    if((self=[super init])){
        _dataStores=@[[NSMutableData dataWithLength:184320],[NSMutableData dataWithLength:184320]];
        _transactionStores=@[[NSMutableData dataWithLength:26880],[NSMutableData dataWithLength:26880]];
        _isoCallbacks=[NSMutableArray new];_controlCallbacks=[NSMutableArray new];
        IsoProbeStatus s={.magic=ISO_PROBE_STATUS_MAGIC,.version=1,.endpoint=0x83};_lastStatus=[[NSMutableData alloc] initWithBytes:&s length:sizeof(s)];
    }return self;
}
- (BOOL)offlineSimulation {return ![_fault isEqual:@"real-blocked"];}
- (id<A23TransactionTransport>)transport {return self;}
- (NSDictionary *)identity {return @{@"device_id":@101,@"interface_id":@102,@"parent_device_id":@101};}
- (NSDictionary *)descriptorBytes {
    uint8_t d[]={18,1,0,2,0,0,0,64,9,0x12,0x57,0xca,0,1,0,0,0,1};
    uint8_t c[]={9,2,25,0,1,1,0,0x80,50,9,4,2,0,1,0xff,0x49,1,0,7,5,0x83,1,0,1,1};
    uint8_t a[]={9,4,2,0,1,0xff,0x49,1,0};if([_fault isEqual:@"bad-descriptors"])c[24]=4;
    return @{@"device_descriptor":[NSData dataWithBytes:d length:18],@"configuration_descriptor":[NSData dataWithBytes:c length:25],@"active_interface":[NSData dataWithBytes:a length:9]};
}
- (NSDictionary *)readStatus {
    NSUInteger ordinal=_statusReads++;NSMutableData *raw=[_lastStatus mutableCopy];IsoProbeStatus *s=raw.mutableBytes;
    if([_fault isEqual:@"stale-before-second"] && ordinal==2)s->sequence=0;
    if([_fault isEqual:@"bad-before"] && ordinal==0)s->sequence=65;
    if([_fault isEqual:@"bad-status"] && ordinal==3)s->urb_status=4;
    if([_fault isEqual:@"same-urb"] && ordinal==3)s->urb_id=s->report_id=501;
    if([_fault isEqual:@"bad-iso7"] && ordinal==1)((IsoProbeBurstContextDiagnostics *)&s->diagnostics)->terminal=0;
    if([_fault isEqual:@"bad-status-sequence"] && ordinal==1)s->sequence=65;
    if(([_fault isEqual:@"short-before"] && ordinal==0) || ([_fault isEqual:@"short-after"] && ordinal==1))raw.length=167;
    uint64_t now=_clock.nowTicks;
    return @{@"data":raw,@"observation":@{@"source":@"mock_control_reply",@"accepted":@YES,@"bytes_transferred":@(raw.length),
        @"begin_ticks":@(now),@"end_ticks":@(now),@"control":@{@"request_type":@193,@"request":@81,@"value":@0,@"index":@2,@"length":@168,@"timeout_ms":@3000}}};
}
- (NSDictionary *)readFrameSample {
    uint64_t now=_clock.nowTicks;
    return @{@"source":@"mock_frame_number",@"current_frame":[_fault isEqual:@"frame-overflow"] ? @(UINT64_MAX) : @(100+_submissions*32),@"begin_ticks":@(now),@"end_ticks":@(now)};
}
- (BOOL)enqueueIORequestWithData:(NSMutableData *)data transactionList:(IOUSBHostIsochronousTransaction *)rows transactionListCount:(NSUInteger)count
    firstFrameNumber:(uint64_t)frame options:(IOUSBHostIsochronousTransferOptions)options error:(NSError **)error
    completionHandler:(IOUSBHostIsochronousTransactionCompletionHandler)callback {
    (void)error;assert(_submissions<2 && count==960 && options==0 && frame==132+_submissions*32);
    assert(data==_dataStores[_submissions] && rows==_transactionStores[_submissions].mutableBytes);
    ++_submissions;[_isoCallbacks addObject:[callback copy]];
    if([_fault isEqual:@"slow-enqueue"])[_clock advanceNS:9000000];
    if([_fault isEqual:@"early-iso"])callback(0,rows);
    return ![_fault isEqual:@"iso-reject"];
}
- (BOOL)enqueueBurst:(uint16_t)first completion:(IOUSBHostCompletionHandler)callback error:(NSError **)error {
    (void)error;assert(_triggers<2 && first==81+_triggers*16);++_triggers;[_controlCallbacks addObject:[callback copy]];
    return ![_fault isEqual:@"trigger-reject"];
}
- (BOOL)abortWithOption:(IOUSBHostAbortOption)option error:(NSError **)error {
    (void)error;assert(option==IOUSBHostAbortOptionAsynchronous && _aborts==0);++_aborts;return YES;
}
- (void)oldControl {IOUSBHostCompletionHandler cb=_controlCallbacks[0];cb(0,0);}
- (void)oldISO {IOUSBHostIsochronousTransactionCompletionHandler cb=_isoCallbacks[0];cb(0,(void *)1);}
- (void)deliver:(NSUInteger)n {
    assert(n<_submissions && n<_triggers);
    IOUSBHostIsochronousTransaction *rows=_transactionStores[n].mutableBytes;
    uint8_t *bytes=_dataStores[n].mutableBytes;
    for(unsigned i=0;i<960;++i){rows[i].status=0;rows[i].completeCount=(i>=n*120 && i<n*120+16) ? 192 : 0;}
    for(unsigned p=0;p<16;++p)for(unsigned j=0;j<192;++j)bytes[(n*120+p)*192+j]=isoProbeByte((uint16_t)(81+n*16+p),j);
    if([_fault isEqual:@"bad-payload"] && n==0)bytes[6]^=1;
    if([_fault isEqual:@"bad-transaction"] && n==0)rows[0].offset=192;
    if([_fault isEqual:@"late-control"] && n==0)[_clock advanceNS:17000000];
    IOUSBHostCompletionHandler control=_controlCallbacks[n];control([_fault isEqual:@"control-error"] ? kIOReturnError : 0,[_fault isEqual:@"control-bytes"] ? 1 : 0);
    if([_fault isEqual:@"duplicate-control"] && n==0)control(0,0);
    IOUSBHostIsochronousTransactionCompletionHandler iso=_isoCallbacks[n];
    iso([_fault isEqual:@"iso-error"] ? kIOReturnError : 0,[_fault isEqual:@"foreign-pointer"] ? (void *)1 : rows);
    if([_fault isEqual:@"duplicate-iso"] && n==0)iso(0,rows);
    IsoProbeStatus s={.magic=ISO_PROBE_STATUS_MAGIC,.version=1,.sequence=(uint32_t)(81+n*16),.state=ISO_PROBE_COMPLETE,
        .urb_id=(uint32_t)(501+n),.report_id=(uint32_t)(501+n),.requested=3072,.transferred=3072,.urb_status=3,.speed=3,.endpoint=0x83,.report_count=1};
    IsoProbeBurstContextDiagnostics d={.magic=ISO_PROBE_BURST_INTERVAL_MAGIC,.first_control=(32<<20)|(5<<10)|0x11,
        .terminal=1,.completed_bitmap=65535,.actual_sum=3072,.first_virtual_trb=0x2000000+n*512,.context_valid=1};
    memcpy(&s.diagnostics,&d,sizeof(d));_lastStatus=[[NSMutableData alloc] initWithBytes:&s length:sizeof(s)];
}
@end

@interface TwoJournal : NSObject <A23SessionJournal>
@property A23SimulationJournal *journal;
@property TwoResources *resources;
@property NSString *fault;
@end
@implementation TwoJournal
- (BOOL)append:(NSDictionary *)row error:(NSError **)error {
    NSString *event=row[@"event"];NSUInteger n=[row[@"details"][@"epoch"] unsignedIntegerValue];
    if([_fault isEqual:@"journal-failure"] && [event isEqual:@"save_intent"])return NO;
    if([_fault isEqual:@"journal-after-commit"] && [event isEqual:@"saved"])return NO;
    BOOL ok=[_journal append:row error:error];
    if(ok && n==0 && [event isEqual:@"saved"] && [_fault isEqual:@"old-after-commit"])[_resources oldISO];
    if(ok && [event isEqual:@"iso_intent"]){
        if([_fault isEqual:@"stale-frame"])[_resources.clock advanceNS:17000000];
        if(n==1 && [_fault isEqual:@"old-during-iso-intent"])[_resources oldISO];
    }
    if(ok && n==1 && [event isEqual:@"trigger_intent"] && [_fault isEqual:@"old-control-trigger-intent"])[_resources oldControl];
    if(ok && [event isEqual:@"trigger_intent"] && [_fault isEqual:@"slow-trigger"])[_resources.clock advanceNS:9000000];
    if(ok && [event isEqual:@"save_intent"] && n==1 && [_fault isEqual:@"old-during-save"])[_resources oldISO];
    return ok;
}
@end

int main(int argc,const char *argv[]) {
    @autoreleasepool {
        assert(argc==2);NSString *root=@(argv[1]);NSMutableDictionary *results=[NSMutableDictionary new];
        NSArray *cases=@[@"normal",@"real-blocked",@"alias-store",@"short-store",@"bad-descriptors",@"bad-first",
            @"bad-before",@"short-before",@"short-after",@"bad-status",@"bad-iso7",@"bad-status-sequence",@"same-urb",@"stale-before-second",
            @"bad-payload",@"bad-transaction",@"foreign-pointer",@"iso-error",@"control-error",@"duplicate-iso",@"duplicate-control",
            @"late-old-ready",@"late-old-second",@"old-after-complete",@"old-during-iso-intent",@"old-during-save",@"storage-change",
            @"save-collision",@"save-second-collision",@"journal-failure",@"journal-after-commit",@"old-after-commit",@"stale-frame",@"frame-overflow",@"slow-enqueue",@"slow-trigger",
            @"control-bytes",@"old-control-ready",@"old-control-trigger-intent",@"early-iso",@"iso-reject",@"trigger-reject",@"iso-timeout",@"control-timeout",@"late-control",@"detach",@"exit"];
        for(NSString *mode in cases){
            NSString *directory=[root stringByAppendingPathComponent:mode];assert([[NSFileManager defaultManager] createDirectoryAtPath:directory withIntermediateDirectories:NO attributes:nil error:NULL]);
            TwoResources *r=[TwoResources new];r.fault=mode;r.clock=[TwoClock new];
            if([mode isEqual:@"alias-store"])r.dataStores=@[r.dataStores[0],r.dataStores[0]];
            if([mode isEqual:@"short-store"])r.transactionStores[1].length=26879;
            TwoJournal *journal=[TwoJournal new];journal.resources=r;journal.fault=mode;
            journal.journal=[[A23SimulationJournal alloc] initWithPath:[directory stringByAppendingPathComponent:@"session.jsonl"] error:NULL];assert(journal.journal);
            dispatch_queue_t q=dispatch_queue_create("a23.two.epoch.test",DISPATCH_QUEUE_SERIAL);
            __block A23TwoEpochReceiver *receiver=nil;
            dispatch_sync(q, ^{receiver=[[A23TwoEpochReceiver alloc] initWithResources:r firstSequence:[mode isEqual:@"bad-first"] ? 82 : 81 directory:directory queue:q clock:r.clock journal:journal error:NULL];});
            if(!receiver){assert(([@[@"real-blocked",@"alias-store",@"short-store",@"bad-descriptors",@"bad-first"] containsObject:mode]));assert(!r.submissions && !r.triggers);results[mode]=@{@"init_rejected":@YES};continue;}
            if([mode isEqual:@"save-collision"] || [mode isEqual:@"save-second-collision"]){NSString *name=[mode isEqual:@"save-collision"] ? @"epoch-0" : @"epoch-1";assert([[NSFileManager defaultManager] createDirectoryAtPath:[directory stringByAppendingPathComponent:name] withIntermediateDirectories:NO attributes:nil error:NULL]);}
            dispatch_sync(q, ^{[receiver start];assert(![receiver start]);});
            for(NSUInteger n=0;n<2;++n){
                __block NSDictionary *state;dispatch_sync(q, ^{state=receiver.result;});if([state[@"stopped"] boolValue])break;
                if(n==0 && [@[@"iso-timeout",@"control-timeout",@"detach",@"exit"] containsObject:mode]){
                    if([mode isEqual:@"iso-timeout"]){IOUSBHostCompletionHandler cb=r.controlCallbacks[0];cb(0,0);[r.clock advanceNS:2000000001];}
                    if([mode isEqual:@"control-timeout"])[r.clock advanceNS:17000000];
                    dispatch_sync(q, ^{if([mode isEqual:@"detach"])[receiver detachedRegistryID:102];if([mode isEqual:@"exit"])[receiver requestStop];[receiver poll];});break;
                }
                if(n==1 && [mode isEqual:@"late-old-second"]){[r oldISO];dispatch_sync(q, ^{[receiver poll];});break;}
                [r deliver:n];dispatch_sync(q, ^{[receiver poll];});
                if(n==0){
                    if([mode isEqual:@"late-old-ready"])[r oldISO];
                    if([mode isEqual:@"old-control-ready"])[r oldControl];
                    if([mode isEqual:@"storage-change"])r.dataStores[0].length=184321;
                    dispatch_sync(q, ^{[receiver poll];});
                }
            }
            if([mode isEqual:@"old-after-complete"]){[r oldISO];dispatch_sync(q, ^{[receiver poll];});}
            dispatch_sync(q, ^{
                [receiver poll];NSDictionary *result=receiver.result;
                if([mode isEqual:@"normal"])assert([result[@"complete"] boolValue] && ![result[@"stopped"] boolValue] && [result[@"saved_epochs"] unsignedIntegerValue]==2);
                else assert([result[@"stopped"] boolValue] && ![result[@"complete"] boolValue]);
                assert(r.submissions<=2 && r.triggers<=2 && r.aborts<=1 && [result[@"all_stores_retained"] boolValue]);
                if([@[@"late-old-ready",@"old-during-iso-intent",@"storage-change",@"stale-before-second",@"save-collision",@"journal-failure"] containsObject:mode])assert(r.submissions==1);
                NSData *json=[NSJSONSerialization dataWithJSONObject:result options:NSJSONWritingSortedKeys error:NULL];assert([json writeToFile:[directory stringByAppendingPathComponent:@"result.json"] options:NSDataWritingWithoutOverwriting error:NULL]);results[mode]=result;
            });
        }
        NSData *json=[NSJSONSerialization dataWithJSONObject:@{@"case_count":@(cases.count),@"cases":results,@"real_sdk_objects":@0,@"usb_requests":@0} options:NSJSONWritingSortedKeys error:NULL];fwrite(json.bytes,1,json.length,stdout);puts("");
    }return 0;
}
