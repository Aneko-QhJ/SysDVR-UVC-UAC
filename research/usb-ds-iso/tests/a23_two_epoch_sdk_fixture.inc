// Uses only frozen TwoResources + PairInterface prefixes. Real SDK operations
// are never instantiated. Source tags below explicitly carry injected_fixture.
#import "../host/a23_two_epoch_sdk_driver.h"

@interface SDKModelInterface : PairInterface
@end
@implementation SDKModelInterface
- (NSDictionary *)readStatus {
    NSDictionary *reply=[super readStatus];NSMutableDictionary *o=[reply[@"observation"] mutableCopy];
    if(![self.fault isEqual:@"mock-status"])o[@"source"]=@"sdk_control_reply";
    o[@"injected_fixture"]=@YES;return @{@"data":reply[@"data"],@"observation":o};
}
- (NSDictionary *)readFrameSample {
    NSMutableDictionary *sample=[[super readFrameSample] mutableCopy];
    if(![self.fault isEqual:@"mock-frame"])sample[@"source"]=@"sdk_frame_number";
    sample[@"frame_time"]=[self.fault isEqual:@"bad-frame-time"] ? @0 : @(self.clock.nowTicks);
    sample[@"injected_fixture"]=@YES;return sample;
}
@end
@interface SDKModelJournal : NSObject <A23SessionJournal>
@property A23SimulationJournal *journal;
@property SDKModelInterface *interface;
@property NSString *fault;
@end
@implementation SDKModelJournal
- (BOOL)append:(NSDictionary *)row error:(NSError **)error {
    NSString *event=row[@"event"];NSUInteger n=[row[@"details"][@"epoch"] unsignedIntegerValue];
    if(([self.fault isEqual:@"journal-save"] && [event isEqual:@"save_intent"]) ||
       ([self.fault isEqual:@"journal-after-commit"] && [event isEqual:@"saved"]) ||
       ([self.fault isEqual:@"quiet-journal-failure"] && [event isEqual:@"observation_complete"]))return NO;
    BOOL ok=[_journal append:row error:error];
    if(ok && [event isEqual:@"iso_intent"]){
        if([_fault isEqual:@"stale-frame"])[_interface.clock advanceNS:17000000];
        if(n==1 && [_fault isEqual:@"old-during-iso-intent"])[_interface oldISO];
    }
    if(ok && [event isEqual:@"trigger_intent"]){
        if([_fault isEqual:@"slow-trigger"])[_interface.clock advanceNS:9000000];
        if(n==1 && [_fault isEqual:@"old-control-trigger-intent"])[_interface oldControl];
    }
    if(ok && n==0 && [event isEqual:@"saved"] && [_fault isEqual:@"old-after-commit"])[_interface oldISO];
    return ok;
}
@end

int main(int argc,const char *argv[]) {
    @autoreleasepool {
        assert(argc==2);NSString *root=@(argv[1]);NSMutableDictionary *out=[NSMutableDictionary new];
        NSArray *cases=@[@"normal",@"queued-delay",@"mock-provider",@"reused-status",@"poisoned-before-init",@"mock-status",@"mock-frame",@"bad-frame-time",
            @"bad-payload",@"bad-status",@"same-urb",@"duplicate-iso",@"duplicate-control",@"foreign-pointer",@"control-error",@"control-bytes",@"early-iso",@"iso-reject",@"trigger-reject",@"slow-enqueue",@"slow-trigger",@"stale-frame",@"late-control",@"iso-timeout",@"control-timeout",
            @"save-collision",@"journal-save",@"journal-after-commit",@"old-during-iso-intent",@"old-control-trigger-intent",@"old-after-commit",@"old-ready",@"old-during-quiet",@"old-after-observation",@"old-after-receipt",@"quiet-incomplete",@"quiet-journal-failure",@"receipt-collision",@"extra-status-after-observation",@"third-iso-after-observation",@"runtime-interest",@"exit"];
        for(NSString *name in cases){
            NSString *directory=[root stringByAppendingPathComponent:name];assert([[NSFileManager defaultManager] createDirectoryAtPath:directory withIntermediateDirectories:NO attributes:nil error:NULL]);
            PairOperations *op=pairOperations(name,[name isEqual:@"mock-provider"]);
            SDKModelInterface *r=[SDKModelInterface new];r.fault=name;r.clock=[TwoClock new];op.interface=r;
            dispatch_queue_t q=dispatch_queue_create("a23.sdk.driver.model",DISPATCH_QUEUE_SERIAL);__block A23TwoEpochSDKDriver *driver=nil;
            A23PairedSimulationProvider *provider=pairProvider(op,q,![name isEqual:@"mock-provider"],^(uint32_t m){(void)m;[driver detachedRegistryID:102];});
            SDKModelJournal *journal=[SDKModelJournal new];journal.interface=r;journal.fault=name;
            journal.journal=[[A23SimulationJournal alloc] initWithPath:[directory stringByAppendingPathComponent:@"session.jsonl"] error:NULL];assert(journal.journal);
            __block id<A23PairedResources> lease;
            dispatch_sync(q, ^{
                lease=[provider openCandidate:pairCandidate() error:NULL];assert(lease && op.liveReferences==1);
                for(NSData *data in lease.dataStores)assert(pairZero(data));
                if([name isEqual:@"reused-status"]){[lease readStatus];((uint8_t *)lease.dataStores[0].mutableBytes)[0]=0xa5;}
                if([name isEqual:@"poisoned-before-init"])[lease readFrameSample];
                driver=[[A23TwoEpochSDKDriver alloc] initWithResources:lease firstSequence:81 directory:directory queue:q clock:r.clock journal:journal error:NULL];
                if(!driver){
                    assert(([@[@"mock-provider",@"reused-status",@"poisoned-before-init"] containsObject:name]));
                    assert(!r.submissions && !r.triggers);
                    if([name isEqual:@"reused-status"])assert(((uint8_t *)lease.dataStores[0].bytes)[0]==0xa5);
                    out[name]=@{@"init_rejected":@YES,@"lease":lease.result};return;
                }
                if([name isEqual:@"save-collision"] || [name isEqual:@"receipt-collision"]){
                    NSString *child=[name isEqual:@"save-collision"] ? @"epoch-0" : @"sdk-receipt";
                    assert([[NSFileManager defaultManager] createDirectoryAtPath:[directory stringByAppendingPathComponent:child] withIntermediateDirectories:NO attributes:nil error:NULL]);
                }
                [driver start];assert(![driver start] && ![lease closeUnused]);
            });
            if(!driver)continue;
            for(NSUInteger n=0;n<2;++n){
                __block BOOL stopped;dispatch_sync(q, ^{stopped=[driver.result[@"stopped"] boolValue];});if(stopped)break;
                if(n==0 && ([@[@"iso-timeout",@"control-timeout",@"runtime-interest",@"exit"] containsObject:name])){
                    if([name isEqual:@"iso-timeout"]){IOUSBHostCompletionHandler cb=r.controlCallbacks[0];cb(0,0);[r.clock advanceNS:2000000001];}
                    if([name isEqual:@"control-timeout"])[r.clock advanceNS:17000000];
                    if([name isEqual:@"runtime-interest"])r.interest(99);
                    dispatch_sync(q, ^{if([name isEqual:@"exit"])[driver requestStop];[driver poll];});break;
                }
                if([name isEqual:@"queued-delay"])dispatch_sync(q, ^{[r deliver:n];[r.clock advanceNS:25000000];});
                else [r deliver:n];
                dispatch_sync(q, ^{[driver poll];});
                if(n==0){if([name isEqual:@"old-ready"])[r oldISO];dispatch_sync(q, ^{[driver poll];});}
            }
            __block BOOL savedTwo;dispatch_sync(q, ^{savedTwo=[driver.result[@"saved_epochs"] unsignedIntegerValue]==2 && ![driver.result[@"stopped"] boolValue];});
            if(savedTwo){
                if([name isEqual:@"old-during-quiet"])[r oldISO];
                if(![name isEqual:@"quiet-incomplete"])[r.clock advanceNS:250000001];
                dispatch_sync(q, ^{[driver poll];});
                if([name isEqual:@"old-after-observation"])[r oldISO];
                dispatch_sync(q, ^{
                    if([name isEqual:@"extra-status-after-observation"])[lease readStatus];
                    if([name isEqual:@"third-iso-after-observation"])[lease.transport enqueueIORequestWithData:lease.dataStores[0] transactionList:lease.transactionStores[0].mutableBytes transactionListCount:960 firstFrameNumber:196 options:0 error:NULL completionHandler:^(IOReturn s,IOUSBHostIsochronousTransaction *p){(void)s;(void)p;}];
                    [driver poll];
                });
            }
            dispatch_sync(q, ^{[driver saveReceiptOnce];});
            if([name isEqual:@"old-after-receipt"]){[r oldISO];dispatch_sync(q, ^{[driver poll];});}
            dispatch_sync(q, ^{
                NSDictionary *result=driver.result,*status=driver.receiptStatus;
                BOOL normal=[name isEqual:@"normal"] || [name isEqual:@"queued-delay"];
                if(normal)assert([result[@"complete"] boolValue] && [status[@"saved"] boolValue] && ![status[@"stale"] boolValue]);
                else if([name isEqual:@"quiet-incomplete"])assert(![result[@"complete"] boolValue] && ![result[@"stopped"] boolValue] && ![status[@"attempted"] boolValue] && [result[@"saved_epochs"] unsignedIntegerValue]==2);
                else assert([result[@"stopped"] boolValue] && ![result[@"complete"] boolValue]);
                if([name isEqual:@"old-after-receipt"])assert([status[@"stale"] boolValue] && ![status[@"saved"] boolValue]);
                assert(![driver saveReceiptOnce] && ![lease closeUnused] && !r.destroys && op.liveReferences==1 && r.submissions<=2 && r.triggers<=2 && r.aborts<=1);
                for(NSString *file in @[@"result.json",@"receipt-status.json"]){NSDictionary *v=[file isEqual:@"result.json"] ? result : status;
                    NSData *raw=[NSJSONSerialization dataWithJSONObject:v options:NSJSONWritingSortedKeys error:NULL];assert([raw writeToFile:[directory stringByAppendingPathComponent:file] options:NSDataWritingWithoutOverwriting error:NULL]);}
                out[name]=@{@"result":result,@"receipt_status":status,@"live_references":@(op.liveReferences),@"destroys":@(r.destroys)};
            });
        }
        NSData *raw=[NSJSONSerialization dataWithJSONObject:@{@"case_count":@(cases.count),@"cases":out,@"real_sdk_objects":@0,@"usb_requests":@0,@"actual_sdk_mapping_tested":@NO} options:NSJSONWritingSortedKeys error:NULL];fwrite(raw.bytes,1,raw.length,stdout);puts("");
    }return 0;
}
