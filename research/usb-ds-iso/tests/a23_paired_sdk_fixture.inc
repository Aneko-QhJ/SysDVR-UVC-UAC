// Concatenated after the frozen TwoResources/TwoClock fixture prefix. Its old
// main is excluded; only this entry point executes. No real SDK client opens.
#import "../host/a23_paired_sdk_adapter.h"

// Fixed views force REAL live address overlap; Foundation no-copy factories
// may acquire independent storage on mutableBytes and cannot serve this fault.
@interface PairDataView : NSMutableData
- (instancetype)initWithBacking:(NSMutableData *)backing offset:(NSUInteger)offset length:(NSUInteger)length;
@end
@implementation PairDataView {
    NSMutableData *_backing;NSUInteger _offset,_length;
}
- (instancetype)initWithBacking:(NSMutableData *)backing offset:(NSUInteger)offset length:(NSUInteger)length {
    if((self=[super init])){assert(offset+length<=backing.length);_backing=backing;_offset=offset;_length=length;}return self;
}
- (NSUInteger)length {return _length;}
- (const void *)bytes {return (const uint8_t *)_backing.bytes+_offset;}
- (void *)mutableBytes {return (uint8_t *)_backing.mutableBytes+_offset;}
- (void)setLength:(NSUInteger)length {assert(length==_length);}
- (void)replaceBytesInRange:(NSRange)range withBytes:(const void *)bytes length:(NSUInteger)length {
    assert(range.length==length && NSMaxRange(range)<=_length);memcpy((uint8_t *)self.mutableBytes+range.location,bytes,length);
}
@end

@interface PairInterface : TwoResources <A23PairedInterface>
@property NSUInteger allocations,copies,destroys;
@property(copy) A23AdapterInterest interest;
@property NSMutableData *overlap;
@property(copy) void (^allocationHook)(NSUInteger);
@end
@implementation PairInterface
- (instancetype)init {
    if((self=[super init])){
        for(NSMutableData *d in self.dataStores)memset(d.mutableBytes,0x5a,d.length);
        for(NSMutableData *d in self.transactionStores)memset(d.mutableBytes,0x5a,d.length);
    }return self;
}
- (BOOL)respondsToSelector:(SEL)selector {
    if([self.fault isEqual:@"capability-missing"] && selector==@selector(enqueueScopedBurst:completion:error:))return NO;
    return [super respondsToSelector:selector];
}
- (NSDictionary *)descriptorBytes:(NSError **)error {
    (void)error;if([self.fault isEqual:@"descriptors-nil"])return nil;
    NSMutableDictionary *d=[self.descriptorBytes mutableCopy];
    if([self.fault isEqual:@"active-alt"]){NSMutableData *a=[d[@"active_interface"] mutableCopy];((uint8_t *)a.mutableBytes)[3]=1;d[@"active_interface"]=a;}
    return d;
}
- (id<A23TransactionTransport>)copyTransport:(NSError **)error {
    (void)error;assert(++_copies==1);return [self.fault isEqual:@"pipe-nil"] ? nil : self;
}
- (NSData *)currentEndpointBytes {
    uint8_t e[]={7,5,0x83,1,0,1,1};if([self.fault isEqual:@"endpoint-wrong"])e[6]=4;return [NSData dataWithBytes:e length:7];
}
- (NSMutableData *)allocate:(NSUInteger)length shared:(BOOL)shared error:(NSError **)error {
    (void)error;NSUInteger n=_allocations++;assert(n<4 && length==(n%2 ? 26880 : 184320) && shared==(BOOL)(n%2));
    if(_allocationHook)_allocationHook(n);
    if([self.fault isEqual:[NSString stringWithFormat:@"nil-%lu",(unsigned long)n]])return nil;
    NSMutableData *data=n%2 ? self.transactionStores[n/2] : self.dataStores[n/2];
    if([self.fault isEqual:[NSString stringWithFormat:@"short-%lu",(unsigned long)n]])data.length--;
    if([self.fault isEqual:@"alias-data1"] && n==2)data=self.dataStores[0];
    if([self.fault isEqual:@"overlap-tables"] && (n==1 || n==3)){
        if(!_overlap)_overlap=[NSMutableData dataWithLength:26884];
        data=[[PairDataView alloc] initWithBacking:_overlap offset:(n==3 ? 4 : 0) length:26880];
        assert(data.mutableBytes==(uint8_t *)_overlap.mutableBytes+(n==3 ? 4 : 0));
    }
    if([self.fault isEqual:@"packed-table"] && n==3){_overlap=[NSMutableData dataWithLength:26881];data=[[PairDataView alloc] initWithBacking:_overlap offset:1 length:26880];assert(data.mutableBytes==(uint8_t *)_overlap.mutableBytes+1);}
    return data;
}
- (BOOL)enqueueScopedBurst:(uint16_t)first completion:(IOUSBHostCompletionHandler)completion error:(NSError **)error {
    return [self enqueueBurst:first completion:completion error:error];
}
- (void)destroy {assert(!self.submissions && !self.triggers && ++_destroys==1);}
@end

@interface PairOperations : NSObject <A23AdapterOperations>
@property BOOL simulation;
@property NSString *fault;
@property PairInterface *interface;
@property NSUInteger retainCalls,releaseCalls,liveReferences,identities,opens;
@end
@implementation PairOperations
- (BOOL)retainService:(io_service_t)service error:(NSError **)error {
    assert(service==7 && ++_retainCalls==1);
    if([_fault isEqual:@"retain-failed"])return NO;
    ++_liveReferences;
    if([_fault isEqual:@"retain-with-error"] && error)*error=[NSError errorWithDomain:@"injected" code:7 userInfo:nil];
    return YES;
}
- (void)releaseService:(io_service_t)service {assert(service==7 && _liveReferences==1 && ++_releaseCalls==1);--_liveReferences;}
- (NSDictionary *)identityForService:(io_service_t)service error:(NSError **)error {
    (void)error;assert(service==7 && _liveReferences==1);++_identities;
    NSMutableDictionary *d=[@{@"device_id":@101,@"interface_id":@102,@"parent_device_id":@101,@"connection_speed":@3} mutableCopy];
    if(([_fault isEqual:@"identity-before"] && _identities==1) || ([_fault isEqual:@"identity-after-open"] && _identities==2) ||
        ([_fault isEqual:@"identity-after-maps"] && _identities==3))d[@"interface_id"]=@103;
    if([_fault isEqual:@"interest-final"] && _identities==3)_interface.interest(99);
    return d;
}
- (id<A23AdapterInterface>)openService:(io_service_t)service queue:(dispatch_queue_t)queue interest:(A23AdapterInterest)interest error:(NSError **)error {
    (void)queue;(void)error;assert(service==7 && _liveReferences==1 && ++_opens==1);
    if([_fault isEqual:@"open-failed"])return nil;
    _interface.interest=interest;if([_fault isEqual:@"interest-open"])interest(99);return _interface;
}
@end
static NSDictionary *pairCandidate(void) {
    return @{@"service_token":@7,@"device_id":@101,@"interface_id":@102,@"parent_device_id":@101,@"connection_speed":@3};
}
static PairOperations *pairOperations(NSString *fault,BOOL simulation) {
    PairOperations *op=[PairOperations new];op.simulation=simulation;op.fault=fault;op.interface=[PairInterface new];op.interface.fault=fault;op.interface.clock=[TwoClock new];
    __weak PairOperations *weak=op;
    op.interface.allocationHook=^(NSUInteger n){
        if(n==2 && [fault isEqual:@"interest-allocate"])weak.interface.interest(99);
        if(n==1 && [fault isEqual:@"mode-change-allocate"])weak.simulation=NO;
    };return op;
}
static BOOL pairZero(NSData *data) {const uint8_t *p=data.bytes;for(NSUInteger n=0;n<data.length;++n)if(p[n])return NO;return YES;}
static A23PairedSimulationProvider *pairProvider(PairOperations *op,dispatch_queue_t q,BOOL sdk,A23AdapterInterest interest) {
    Class cls=sdk ? A23PairedSDKProvider.class : A23PairedSimulationProvider.class;
    return [[cls alloc] initWithOperations:op queue:q interest:interest firstSequence:81];
}

int main(int argc,const char *argv[]) {
    @autoreleasepool {
        assert(argc==2);NSString *root=@(argv[1]);NSMutableDictionary *preparation=[NSMutableDictionary new],*runtime=[NSMutableDictionary new];
        NSArray *faults=@[@"clean",@"sdk-fake-clean",@"simulation-mode-blocked",@"sdk-mode-blocked",@"token-missing",@"token-bool",@"token-float",@"token-negative",@"token-zero",@"token-large",@"parent-mismatch",@"speed-wrong",@"identity-float",
            @"retain-failed",@"retain-with-error",@"identity-before",@"open-failed",@"capability-missing",@"identity-after-open",@"descriptors-nil",@"active-alt",@"bad-descriptors",@"pipe-nil",@"endpoint-wrong",
            @"nil-0",@"nil-1",@"nil-2",@"nil-3",@"short-0",@"short-1",@"short-2",@"short-3",@"alias-data1",@"overlap-tables",@"packed-table",@"identity-after-maps",@"interest-open",@"interest-allocate",@"interest-final",@"mode-change-allocate"];
        for(NSString *fault in faults){
            dispatch_queue_t q=dispatch_queue_create("a23.pair.prepare",DISPATCH_QUEUE_SERIAL);
            BOOL sdk=[fault hasPrefix:@"sdk-"];
            BOOL simulation=![fault isEqual:@"sdk-fake-clean"] && ![fault isEqual:@"simulation-mode-blocked"];
            PairOperations *op=pairOperations(fault,simulation);A23PairedSimulationProvider *provider=pairProvider(op,q,sdk,^(uint32_t m){(void)m;});
            NSMutableDictionary *candidate=[pairCandidate() mutableCopy];
            if([fault isEqual:@"token-missing"])[candidate removeObjectForKey:@"service_token"];
            NSDictionary *tokens=@{@"token-bool":@YES,@"token-float":@7.0,@"token-negative":@(-7),@"token-zero":@0,@"token-large":@(UINT64_C(0x100000000))};
            if(tokens[fault])candidate[@"service_token"]=tokens[fault];
            if([fault isEqual:@"parent-mismatch"])candidate[@"parent_device_id"]=@103;
            if([fault isEqual:@"speed-wrong"])candidate[@"connection_speed"]=@2;
            if([fault isEqual:@"identity-float"])candidate[@"device_id"]=@101.0;
            dispatch_sync(q, ^{
                id<A23PairedResources> lease=[provider openCandidate:candidate error:NULL];
                BOOL clean=[fault isEqual:@"clean"] || [fault isEqual:@"sdk-fake-clean"] || [fault isEqual:@"packed-table"];
                if(clean){
                    assert(lease && lease.offlineSimulation==simulation && lease.sdkResources==!simulation && op.identities==3 && op.opens==1 && op.interface.copies==1 && op.interface.allocations==4);
                    for(NSData *d in lease.dataStores)assert(pairZero(d));for(NSData *d in lease.transactionStores)assert(pairZero(d));
                    assert([lease closeUnused] && [lease closeUnused] && op.interface.destroys==1 && op.releaseCalls==1 && !op.liveReferences);
                }else{
                    if(lease)fprintf(stderr,"unexpected prepared: %s\n",fault.UTF8String);
                    assert(!lease);
                    BOOL quarantine=[fault hasPrefix:@"interest-"] || [fault isEqual:@"mode-change-allocate"];
                    if(quarantine){assert(provider.retainedFailure && ![provider.retainedFailure closeUnused] && op.liveReferences==1 && !op.releaseCalls && !op.interface.destroys);}
                    else assert(!op.liveReferences && op.interface.destroys==(op.opens && ![fault isEqual:@"open-failed"] ? 1 : 0));
                    if([fault hasSuffix:@"mode-blocked"])assert(!op.retainCalls && !op.identities && !op.opens);
                }
                NSUInteger before=op.opens;assert(![provider openCandidate:pairCandidate() error:NULL] && op.opens==before);
                NSMutableDictionary *row=[provider.result mutableCopy];row[@"retains"]=@(op.retainCalls);row[@"releases"]=@(op.releaseCalls);row[@"live_references"]=@(op.liveReferences);
                row[@"opens"]=@(op.opens);row[@"copies"]=@(op.interface.copies);row[@"allocations"]=@(op.interface.allocations);row[@"destroys"]=@(op.interface.destroys);
                if(provider.retainedFailure)row[@"retained_failure"]=provider.retainedFailure.result;preparation[fault]=row;
            });
        }
        NSArray *cases=@[@"normal",@"sdk-core-rejected",@"bad-payload",@"bad-status",@"same-urb",@"duplicate-iso",@"duplicate-control",@"foreign-pointer",@"control-error",@"early-iso",@"iso-reject",@"trigger-reject",@"save-collision",@"old-iso-ready",@"old-control-ready",@"third-iso",@"extra-status",@"wrong-sequence",@"wrong-pointer",@"runtime-interest",@"deadline",@"resize-ready",@"mode-change-ready"];
        for(NSString *name in cases){
            NSString *directory=[root stringByAppendingPathComponent:name];assert([[NSFileManager defaultManager] createDirectoryAtPath:directory withIntermediateDirectories:NO attributes:nil error:NULL]);
            PairOperations *op=pairOperations(name,![name isEqual:@"sdk-core-rejected"]);PairInterface *r=op.interface;
            dispatch_queue_t q=dispatch_queue_create("a23.pair.runtime",DISPATCH_QUEUE_SERIAL);__block A23TwoEpochReceiver *receiver=nil;
            A23PairedSimulationProvider *provider=pairProvider(op,q,[name isEqual:@"sdk-core-rejected"],^(uint32_t m){(void)m;[receiver detachedRegistryID:102];});
            A23SimulationJournal *journal=[[A23SimulationJournal alloc] initWithPath:[directory stringByAppendingPathComponent:@"session.jsonl"] error:NULL];
            __block id<A23PairedResources> lease=nil;
            dispatch_sync(q, ^{
                lease=[provider openCandidate:pairCandidate() error:NULL];assert(lease && op.liveReferences==1);
                receiver=[[A23TwoEpochReceiver alloc] initWithResources:lease firstSequence:81 directory:directory queue:q clock:r.clock journal:journal error:NULL];
                if([name isEqual:@"sdk-core-rejected"]){assert(!receiver && !r.submissions);assert([lease closeUnused]);runtime[name]=@{@"core_rejected_sdk_mode":@YES};return;}
                assert(receiver);
                if([name isEqual:@"wrong-pointer"]){[lease readStatus];[lease readFrameSample];assert(![lease.transport enqueueIORequestWithData:lease.dataStores[0] transactionList:(void *)1 transactionListCount:960 firstFrameNumber:132 options:0 error:NULL completionHandler:^(IOReturn s,IOUSBHostIsochronousTransaction *p){(void)s;(void)p;}]);}
                else{if([name isEqual:@"save-collision"])assert([[NSFileManager defaultManager] createDirectoryAtPath:[directory stringByAppendingPathComponent:@"epoch-0"] withIntermediateDirectories:NO attributes:nil error:NULL]);[receiver start];}
                assert(![lease closeUnused] && op.liveReferences==1 && !r.destroys);
            });
            if(!receiver)continue;
            for(NSUInteger n=0;n<2;++n){
                __block BOOL stopped;dispatch_sync(q, ^{stopped=[receiver.result[@"stopped"] boolValue] || [lease.result[@"poisoned"] boolValue];});if(stopped)break;
                if(n==0 && [name isEqual:@"runtime-interest"]){r.interest(99);dispatch_sync(q, ^{[receiver poll];});break;}
                if(n==0 && [name isEqual:@"deadline"]){[r.clock advanceNS:17000000];dispatch_sync(q, ^{[receiver poll];[receiver poll];});break;}
                if(n==0 && [name isEqual:@"wrong-sequence"]){dispatch_sync(q, ^{assert(![lease enqueueBurst:97 completion:^(IOReturn s,NSUInteger b){(void)s;(void)b;} error:NULL]);[receiver requestStop];});break;}
                [r deliver:n];dispatch_sync(q, ^{[receiver poll];});
                if(n==0){
                    if([name isEqual:@"old-iso-ready"])[r oldISO];if([name isEqual:@"old-control-ready"])[r oldControl];
                    if([name isEqual:@"resize-ready"])r.dataStores[0].length=184321;
                    if([name isEqual:@"mode-change-ready"])op.simulation=NO;
                    dispatch_sync(q, ^{[receiver poll];});
                }
            }
            dispatch_sync(q, ^{
                if([name isEqual:@"third-iso"])assert(![lease.transport enqueueIORequestWithData:lease.dataStores[0] transactionList:lease.transactionStores[0].mutableBytes transactionListCount:960 firstFrameNumber:196 options:0 error:NULL completionHandler:^(IOReturn s,IOUSBHostIsochronousTransaction *p){(void)s;(void)p;}]);
                if([name isEqual:@"extra-status"])assert(![lease readStatus].count);
                [receiver poll];NSDictionary *result=receiver.result;
                if([name isEqual:@"normal"])assert([result[@"complete"] boolValue] && [result[@"saved_epochs"] unsignedIntegerValue]==2 && ![lease.result[@"poisoned"] boolValue]);
                else assert([result[@"stopped"] boolValue] || [lease.result[@"poisoned"] boolValue]);
                assert(![lease closeUnused] && op.liveReferences==1 && !r.destroys && r.submissions<=2 && r.triggers<=2 && r.aborts<=1);
                NSDictionary *row=@{@"schema":@"A23-paired-offline-chain-1",@"execution_mode":@"offline_simulation",@"receiver":result,@"lease":lease.result,@"mapped_calls":@(r.allocations),@"pipe_copies":@(r.copies),@"service_retained":@(op.liveReferences),@"destroys":@(r.destroys)};
                NSData *raw=[NSJSONSerialization dataWithJSONObject:result options:NSJSONWritingSortedKeys error:NULL];assert([raw writeToFile:[directory stringByAppendingPathComponent:@"result.json"] options:NSDataWritingWithoutOverwriting error:NULL]);NSData *pairRaw=[NSJSONSerialization dataWithJSONObject:row options:NSJSONWritingSortedKeys error:NULL];assert([pairRaw writeToFile:[directory stringByAppendingPathComponent:@"paired-result.json"] options:NSDataWritingWithoutOverwriting error:NULL]);runtime[name]=row;
            });
        }
        NSData *raw=[NSJSONSerialization dataWithJSONObject:@{@"preparation":preparation,@"runtime":runtime,@"preparation_cases":@(faults.count),@"runtime_cases":@(cases.count),@"real_sdk_objects":@0,@"usb_requests":@0,@"actual_sdk_mapping_tested":@NO} options:NSJSONWritingSortedKeys error:NULL];fwrite(raw.bytes,1,raw.length,stdout);puts("");
    }return 0;
}
