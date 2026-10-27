#import "io_usb_host_mock_adapter.h"
#import "../host/io_usb_host_burst_sdk_transport.h"
#import "../host/io_usb_host_burst_executor.h"
#import "../../../source/uvc/iso_probe_protocol.h"
#include <stdio.h>

@interface SDKFixtureClock : A23LocalMachClock
@property uint64_t offset;
- (void)advance:(uint64_t)ns;
@end
@implementation SDKFixtureClock
- (uint64_t)nowTicks { return mach_absolute_time()+_offset; }
- (void)advance:(uint64_t)ns { _offset+=(uint64_t)(((__uint128_t)ns*self.denominator+self.numerator-1)/self.numerator); }
@end
@interface SDKFixtureInterface : AdapterInterface <A23AdapterBurstInterface>
@property(copy) IOUSBHostCompletionHandler completion;
@property NSUInteger triggers,reads;
@end
@implementation SDKFixtureInterface
- (NSDictionary *)readStatus
{
    ++_reads;NSDictionary *r=[super readStatus];NSMutableDictionary *o=[r[@"observation"] mutableCopy];
    IsoProbeStatus s={0};if([r[@"data"] length]==168)memcpy(&s,[r[@"data"] bytes],sizeof(s));
    if(!s.sequence && [@[@"error-after",@"overflow-after"] containsObject:self.fault]){
        o[@"accepted"]=@YES;[o removeObjectForKey:@"error"];o[@"bytes_transferred"]=@([r[@"data"] length]);
    }
    o[@"source"]=[self.fault isEqual:@"mock-before"] ? @"mock_control_reply" : @"sdk_control_reply";
    if([self.fault isEqual:@"integer-accepted"])o[@"accepted"]=@1;
    if([self.fault isEqual:@"boolean-count"])o[@"bytes_transferred"]=@YES;
    if([self.fault isEqual:@"error-before"])o[@"error"]=@{@"domain":@"fixture",@"code":@-9};
    if([self.fault isEqual:@"overflow-before"])o[@"bytes_transferred"]=@169;
    if([self.fault isEqual:@"old-before-time"]){o[@"begin_ticks"]=@1;o[@"end_ticks"]=@1;}
    if([self.fault isEqual:@"future-before-time"]){o[@"begin_ticks"]=@(UINT64_MAX);o[@"end_ticks"]=@(UINT64_MAX);}
    return @{@"data":r[@"data"],@"observation":o};
}
- (NSDictionary *)readFrameSample
{
    uint64_t begin=mach_absolute_time(),end=mach_absolute_time();
    return @{@"source":@"sdk_frame_number",@"current_frame":@36,@"frame_time":@0,@"begin_ticks":@(begin),@"end_ticks":@(end)};
}
- (BOOL)enqueueSequenceOneBurst:(IOUSBHostCompletionHandler)completion error:(NSError **)error
{
    assert(++_triggers==1);_completion=completion;
    if([self.fault isEqual:@"trigger-rejected"]){if(error)*error=[NSError errorWithDomain:@"fixture-control" code:(int32_t)kIOReturnNotPermitted userInfo:nil];return NO;}
    if([self.fault isEqual:@"inline-control"])completion(0,0);
    if([self.fault isEqual:@"accepted-control-error"] && error)*error=[NSError errorWithDomain:@"fixture-control" code:19 userInfo:nil];
    return YES;
}
@end
// SDK-role injection only. Never inherits or invokes A23DormantSDKOperations.
@interface SDKFixtureOperations : NSObject <A23AdapterOperations>
@property NSUInteger retains,releases,identities,opens;
@property SDKFixtureInterface *interface;
@end
@implementation SDKFixtureOperations
- (BOOL)simulation { return NO; }
- (BOOL)retainService:(io_service_t)service error:(NSError **)error
{ (void)error;assert(service==7 && ++_retains==1);return YES; }
- (void)releaseService:(io_service_t)service
{ assert(service==7 && ++_releases==1 && _interface.destroys==1); }
- (NSDictionary *)identityForService:(io_service_t)service error:(NSError **)error
{
    (void)error;assert(service==7 && _retains==1 && !_releases);++_identities;
    return @{@"device_id":@101,@"interface_id":@102,@"parent_device_id":@101,@"connection_speed":@3};
}
- (id<A23AdapterInterface>)openService:(io_service_t)service queue:(dispatch_queue_t)queue interest:(A23AdapterInterest)interest error:(NSError **)error
{ (void)queue;(void)interest;(void)error;assert(service==7 && ++_opens==1);return _interface; }
@end
static NSData *status(BOOL active,BOOL shortReply)
{
    IsoProbeStatus s={0};s.magic=ISO_PROBE_STATUS_MAGIC;s.version=1;s.endpoint=0x83;
    if(active){s.sequence=1;s.state=2;s.urb_id=s.report_id=42;s.requested=s.transferred=3072;s.urb_status=s.speed=3;s.report_count=1;}
    return [NSData dataWithBytes:&s length:shortReply ? 167 : 168];
}
static void finishISO(AdapterPipe *pipe,BOOL foreign)
{
    for(unsigned i=0;i<960;++i){pipe.rows[i].status=0;pipe.rows[i].timeStamp=mach_absolute_time();}
    for(unsigned p=0;p<16;++p){unsigned i=512+p;pipe.rows[i].completeCount=192;uint8_t *b=(uint8_t *)pipe.data.mutableBytes+i*192;
        for(unsigned j=0;j<192;++j)b[j]=isoProbeByte((uint16_t)(p+1),j);}
    pipe.callback(0,foreign ? (IOUSBHostIsochronousTransaction *)(uintptr_t)1 : pipe.rows);
}
int main(int argc,const char *argv[])
{
    @autoreleasepool {
        assert(argc==2);NSString *root=@(argv[1]);assert([[NSFileManager defaultManager] createDirectoryAtPath:root withIntermediateDirectories:NO attributes:nil error:NULL]);
        NSArray *names=@[@"iso-first",@"control-first",@"inline-control",@"trigger-rejected",@"accepted-control-error",@"control-error",@"control-bytes",@"control-pending",
            @"foreign-pointer",@"iso-pending",@"abort-refused",@"detach-pending",@"save-failed",@"short-after",@"error-after",@"overflow-after",
            @"short-before",@"stale-before",@"mock-before",@"error-before",@"overflow-before",@"integer-accepted",@"boolean-count",
            @"gap-after-intent",@"arrival-during-intent",@"journal-trigger-failed",@"stale-frame",@"mock-frame",@"duplicate-control",@"duplicate-iso",
            @"old-before-time",@"future-before-time",@"old-frame-time"];
        dispatch_queue_t queue=dispatch_queue_create("a23.sdk.burst.injected",DISPATCH_QUEUE_SERIAL);
        for(NSString *name in names){
            NSString *directory=[root stringByAppendingPathComponent:name];assert([[NSFileManager defaultManager] createDirectoryAtPath:directory withIntermediateDirectories:NO attributes:nil error:NULL]);
            assert([@"SDKFixtureOperations/Interface injection; no SDK objects, registry calls or USB.\n" writeToFile:[directory stringByAppendingPathComponent:@"MOCK_ONLY.txt"] atomically:NO encoding:NSUTF8StringEncoding error:NULL]);
            SDKFixtureOperations *ops=[SDKFixtureOperations new];ops.interface=[SDKFixtureInterface new];ops.interface.pipe=[AdapterPipe new];ops.interface.fault=name;
            ops.interface.reply=status([name isEqual:@"stale-before"],[name isEqual:@"short-before"]);SDKFixtureClock *clock=[SDKFixtureClock new];
            A23SimulationJournal *journal=[[A23SimulationJournal alloc] initWithPath:[directory stringByAppendingPathComponent:@"adapter.jsonl"] error:NULL];assert(journal);
            __block A23DormantBurstSDKTransport *transport=nil;
            __block id<A23SessionResources> resources=nil;
            dispatch_sync(queue,^{
                A23AdapterSDKProvider *provider=[[A23AdapterSDKProvider alloc] initWithOperations:ops queue:queue interest:^(uint32_t message){(void)message;assert(!"No real interest expected");}];
                resources=[provider openCandidate:candidate() error:NULL];assert(resources && ops.retains==1 && ops.identities==2 && ops.opens==1);
                assert(allZero(resources.dataStorage) && allZero(resources.transactionStorage));
                transport=[[A23DormantBurstSDKTransport alloc] initWithResources:(id<A23PreparedBurstResources>)resources queue:queue clock:clock event:^BOOL(NSDictionary *row){
                    assert([journal append:row error:NULL]);
                    if([row[@"event"] isEqual:@"trigger_intent"]){
                        if([name isEqual:@"gap-after-intent"])[clock advance:9000000];
                        if([name isEqual:@"arrival-during-intent"])finishISO(ops.interface.pipe,NO);
                        if([name isEqual:@"journal-trigger-failed"])return NO;
                    }return YES;
                } error:NULL];assert(transport && !transport.simulationOnly);
                NSError *invalid=nil;
                assert(![transport enqueueIORequestWithData:resources.dataStorage transactionList:resources.transactionStorage.mutableBytes
                    transactionListCount:959 firstFrameNumber:100 options:0 error:&invalid completionHandler:^(IOReturn rc,IOUSBHostIsochronousTransaction *p){(void)rc;(void)p;assert(!"Must not forward");}]);
                assert(invalid && !ops.interface.pipe.submissions);
                assert(![[A23BurstSimulationExecutor alloc] initWithDirectory:directory queue:queue clock:clock operations:(id<A23BurstMockOperations>)transport journal:^BOOL(NSDictionary *e){(void)e;return YES;}]);
                assert(![transport submitISO] && ![transport triggerOnce] && ![transport readAfter]);
                NSDictionary *beforeReply=resources.readStatus;BOOL before=[transport recordBefore:beforeReply];
                BOOL invalidBefore=[@[@"short-before",@"stale-before",@"mock-before",@"error-before",@"overflow-before",@"integer-accepted",@"boolean-count",@"old-before-time",@"future-before-time"] containsObject:name];
                assert(before==!invalidBefore);if(!before){assert([transport closeAfterOwnerAcknowledged]);return;}
                assert(![transport recordBefore:beforeReply]); // Do not issue a second before request.
                NSMutableDictionary *frame=[resources.readFrameSample mutableCopy];
                if([name isEqual:@"mock-frame"])frame[@"source"]=@"mock_frame_number";
                if([name isEqual:@"old-frame-time"]){frame[@"begin_ticks"]=@1;frame[@"end_ticks"]=@1;}
                BOOL bound=[transport recordFrame:frame];
                if(!bound){assert(([@[@"mock-frame",@"old-frame-time"] containsObject:name] && [transport closeAfterOwnerAcknowledged]));return;}
                if([name isEqual:@"stale-frame"])[clock advance:17000000];
                BOOL accepted=[transport submitISO];assert(accepted==![name isEqual:@"stale-frame"]);
                assert(![transport submitISO] && ![transport closeAfterOwnerAcknowledged]);
                if(accepted)[transport triggerOnce];
                if(ops.interface.triggers){NSError *again=nil;assert(![(id<A23PreparedBurstResources>)resources enqueueSequenceOneBurst:^(IOReturn rc,NSUInteger bytes){(void)rc;(void)bytes;assert(!"Consumed lease cannot trigger");} error:&again] && again && ops.interface.triggers==1);}
                assert(![transport triggerOnce] && ![transport readAfter]);
                if([name isEqual:@"detach-pending"]){assert(![transport detachedRegistryID:999]);assert([transport detachedRegistryID:102]);assert(![transport requestAbortOnce]);}
            });
            AdapterPipe *pipe=ops.interface.pipe;IOUSBHostCompletionHandler control=ops.interface.completion;
            BOOL missing=[@[@"iso-pending",@"abort-refused",@"detach-pending"] containsObject:name];
            if([name isEqual:@"control-first"] || missing){control(0,0);dispatch_sync(queue,^{assert(![transport readAfter] && ![transport closeAfterOwnerAcknowledged]);});}
            if(pipe.submissions && !missing && ![name isEqual:@"arrival-during-intent"]){finishISO(pipe,[name isEqual:@"foreign-pointer"]);dispatch_sync(queue,^{});}
            dispatch_sync(queue,^{if([name isEqual:@"control-pending"]){assert(![transport readAfter]);assert(ops.interface.reads==1 && ![transport closeAfterOwnerAcknowledged]);}});
            if(control && ![@[@"control-first",@"inline-control",@"trigger-rejected",@"iso-pending",@"abort-refused",@"detach-pending"] containsObject:name]){
                control([name isEqual:@"control-error"] ? kIOReturnTimeout : 0,[name isEqual:@"control-bytes"] ? 1 : 0);dispatch_sync(queue,^{});
            }
            if([name isEqual:@"duplicate-control"]){control(0,0);dispatch_sync(queue,^{});}
            if([name isEqual:@"duplicate-iso"]){pipe.callback(0,pipe.rows);dispatch_sync(queue,^{});}
            dispatch_sync(queue,^{
                if(missing){pipe.abortAllowed=![name isEqual:@"abort-refused"];if(![name isEqual:@"detach-pending"]){BOOL ok=[transport requestAbortOnce];assert(ok==pipe.abortAllowed);}
                    assert(![transport requestAbortOnce] && ![transport closeAfterOwnerAcknowledged] && transport.owner.storageRetained);
                }else if(transport.owner.state==A23TransactionCompleted || transport.owner.state==A23TransactionRejected){
                    ops.interface.reply=status(YES,[name isEqual:@"short-after"]);
                    NSDictionary *after=[transport readAfter];
                    if([name isEqual:@"duplicate-iso"])assert(!after);
                    else if(transport.owner.state==A23TransactionCompleted && ![name isEqual:@"journal-trigger-failed"])assert(after);
                    assert(![transport readAfter] && ![transport closeAfterOwnerAcknowledged]);
                    if([name isEqual:@"save-failed"])assert([[NSFileManager defaultManager] createDirectoryAtPath:[directory stringByAppendingPathComponent:@"transfer"] withIntermediateDirectories:NO attributes:nil error:NULL]);
                    BOOL saved=A23SaveSimulationEvidence(transport.owner,directory,@"transfer",@{@"kind":@"single_burst",@"first_sequence":@1},NULL);
                    assert(saved==![name isEqual:@"save-failed"]);
                    if(saved && ![name isEqual:@"duplicate-iso"] && ![name isEqual:@"journal-trigger-failed"])assert([transport closeAfterOwnerAcknowledged]);
                    else assert(![transport closeAfterOwnerAcknowledged]);
                }
                if([name isEqual:@"foreign-pointer"])assert(transport.owner.state==A23TransactionRetained && ![transport closeAfterOwnerAcknowledged]);
                NSDictionary *result=transport.result;
                assert(pipe.submissions<=1 && ops.interface.triggers<=1 && pipe.aborts<=1);
                if([@[@"iso-first",@"control-first",@"inline-control"] containsObject:name])assert([result[@"closed"] boolValue] && ![result[@"failure_reasons"] count]);
                NSData *json=[NSJSONSerialization dataWithJSONObject:result options:NSJSONWritingPrettyPrinted error:NULL];assert([json writeToFile:[directory stringByAppendingPathComponent:@"result.json"] atomically:NO]);
                NSDictionary *calls=@{@"execution_mode":@"simulation",@"injected_only":@YES,@"real_sdk_calls":@0,@"registry_calls":@0,@"usb_requests":@0,
                    @"retains":@(ops.retains),@"identities":@(ops.identities),@"opens":@(ops.opens),@"releases":@(ops.releases),@"destroys":@(ops.interface.destroys),
                    @"iso_submissions":@(pipe.submissions),@"burst_enqueues":@(ops.interface.triggers),@"host_aborts":@(pipe.aborts),@"status_reads":@(ops.interface.reads)};
                NSData *callsJSON=[NSJSONSerialization dataWithJSONObject:calls options:NSJSONWritingPrettyPrinted error:NULL];assert([callsJSON writeToFile:[directory stringByAppendingPathComponent:@"fixture-calls.json"] atomically:NO]);
            });
        }
        // A simulation provider lease has no SDK role/capability. Rejection
        // precedes all status/frame/ISO/control requests.
        dispatch_sync(queue,^{
            AdapterOperations *op=operations(@"clean");id<A23SessionResources> r=[provider(op,queue) openCandidate:candidate() error:NULL];
            assert(r && ![[A23DormantBurstSDKTransport alloc] initWithResources:(id<A23PreparedBurstResources>)r queue:queue clock:[SDKFixtureClock new] event:^BOOL(NSDictionary *e){(void)e;return YES;} error:NULL]);
            assert(!op.interface.pipe.submissions);[r closeWhenNoIO];
        });
        puts("33 injected SDK burst capability/lifecycle cases passed; real SDK/registry/USB calls 0");
    }return 0;
}
