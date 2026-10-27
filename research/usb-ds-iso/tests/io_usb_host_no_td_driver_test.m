#import "io_usb_host_mock_adapter.h"
#import "../host/io_usb_host_no_td_driver.h"

@interface DriverClock : A23LocalMachClock
@property uint64_t offset;
@end
@implementation DriverClock
- (uint64_t)nowTicks { return mach_absolute_time()+_offset; }
- (void)advanceNS:(uint64_t)ns { _offset += (uint64_t)(((__uint128_t)ns*self.denominator+self.numerator-1)/self.numerator); }
@end
@interface FakeSDKInterface : NSObject <A23AdapterInterface>
@property AdapterInterface *delegate;
@property NSString *caseName;
@property NSUInteger statusCalls, frameCalls;
@property(copy) void (^afterStatus)(void), (^afterFrame)(void);
@end
@implementation FakeSDKInterface
- (NSDictionary *)descriptorBytes:(NSError **)error { return [_delegate descriptorBytes:error]; }
- (id<A23TransactionTransport>)copyTransport:(NSError **)error { return [_delegate copyTransport:error]; }
- (NSData *)currentEndpointBytes { return _delegate.currentEndpointBytes; }
- (NSMutableData *)allocate:(NSUInteger)length shared:(BOOL)shared error:(NSError **)error { return [_delegate allocate:length shared:shared error:error]; }
- (NSDictionary *)readStatus
{
    ++_statusCalls;
    if ([_caseName isEqual:@"short-before"] || ([_caseName isEqual:@"short-after"] && _statusCalls==2))
        _delegate.reply = [_delegate.reply subdataWithRange:NSMakeRange(0,167)];
    NSDictionary *original = _delegate.readStatus; NSMutableDictionary *obs = [original[@"observation"] mutableCopy];
    obs[@"source"] = @"sdk_control_reply"; if (_afterStatus) _afterStatus();
    return @{@"data":original[@"data"],@"observation":obs};
}
- (NSDictionary *)readFrameSample
{
    assert(++_frameCalls==1); uint64_t begin=mach_absolute_time();
    if ([_caseName isEqual:@"slow-query"]) usleep(3000);
    uint64_t end=mach_absolute_time();
    if ([_caseName isEqual:@"stale-frame"]) usleep(20000);
    if (_afterFrame) _afterFrame();
    return @{@"source":[_caseName isEqual:@"frame-source-mock"] ? @"mock_frame_number" : @"sdk_frame_number",
        @"current_frame":[_caseName isEqual:@"frame-zero"] ? @0 : @36,@"frame_time":@(begin),@"begin_ticks":@(begin),@"end_ticks":@(end)};
}
- (void)destroy { [_delegate destroy]; }
@end
@interface FakeSDKOperations : NSObject <A23AdapterOperations>
@property AdapterOperations *delegate;
@property FakeSDKInterface *interface;
@end
@implementation FakeSDKOperations
- (BOOL)simulation { return NO; } // Hardware-shaped fixture; all operations below are injected mocks.
- (BOOL)retainService:(io_service_t)service error:(NSError **)error { return [_delegate retainService:service error:error]; }
- (void)releaseService:(io_service_t)service { [_delegate releaseService:service]; }
- (NSDictionary *)identityForService:(io_service_t)service error:(NSError **)error { return [_delegate identityForService:service error:error]; }
- (id<A23AdapterInterface>)openService:(io_service_t)service queue:(dispatch_queue_t)queue interest:(A23AdapterInterest)interest error:(NSError **)error
{ return [_delegate openService:service queue:queue interest:interest error:error] ? _interface : nil; }
@end

int main(int argc,const char *argv[])
{
    @autoreleasepool {
        assert(argc==3); NSString *root=@(argv[1]);
        assert([[NSFileManager defaultManager] createDirectoryAtPath:root withIntermediateDirectories:NO attributes:nil error:NULL]);
        NSData *before=[NSData dataWithContentsOfFile:[@(argv[2]) stringByAppendingPathComponent:@"before.bin"]]; assert(before.length==168);
        assert(allZero([NSMutableData dataWithLength:8]));
        NSArray *names=@[@"clean",@"stale-frame",@"slow-query",@"slow-enqueue",@"short-before",@"short-after",
            @"pending-timeout",@"abort-refused",@"detach-pending",@"foreign-pointer",@"save-failed",@"ambiguous",
            @"mode-rejected",@"frame-zero",@"frame-source-mock",@"post-close-late",@"interrupt-after-status",@"interrupt-after-frame"];
        dispatch_queue_t q=dispatch_queue_create("a23.offline.sdk-driver",DISPATCH_QUEUE_SERIAL);
        for (NSString *name in names) {
            NSString *dir=[root stringByAppendingPathComponent:name];
            assert([[NSFileManager defaultManager] createDirectoryAtPath:dir withIntermediateDirectories:NO attributes:nil error:NULL]);
            assert([@"Injected FakeSDKOperations only. No SDK/registry/USB calls.\n" writeToFile:[dir stringByAppendingPathComponent:@"MOCK_ONLY.txt"] atomically:NO encoding:NSUTF8StringEncoding error:NULL]);
            DriverClock *clock=[DriverClock new]; AdapterOperations *op=operations(@"clean");
            AdapterPipe *pipe=op.interface.pipe; pipe.abortAllowed=![name isEqual:@"abort-refused"];
            pipe.enqueueDelayUS=[name isEqual:@"slow-enqueue"] ? 10000 : 0;
            FakeSDKInterface *interface=[FakeSDKInterface new]; interface.delegate=op.interface; interface.caseName=name; op.interface.reply=before;
            FakeSDKOperations *fake=[FakeSDKOperations new]; fake.delegate=op; fake.interface=interface;
            A23AdapterSDKProvider *provider=[[A23AdapterSDKProvider alloc] initWithOperations:[name isEqual:@"mode-rejected"] ? (id)op : fake queue:q interest:^(uint32_t m){(void)m;}];
            A23NoTDDriver *driver=[[A23NoTDDriver alloc] initWithDirectory:dir queue:q clock:clock]; assert(driver);
            __block BOOL interrupted = NO;
            driver.interruptionRequested = ^BOOL { return interrupted; };
            if ([name isEqual:@"interrupt-after-status"]) interface.afterStatus = ^{ interrupted = YES; };
            if ([name isEqual:@"interrupt-after-frame"]) interface.afterFrame = ^{ interrupted = YES; };
            __block BOOL accepted=NO;
            dispatch_sync(q,^{
                NSArray *candidates=[name isEqual:@"ambiguous"] ? @[candidate(),candidate()] : @[candidate()];
                accepted=[driver startCandidates:candidates provider:provider];
                assert(![driver startCandidates:candidates provider:provider]);
                if ([name isEqual:@"mode-rejected"] || [name isEqual:@"ambiguous"]) assert(op.retains==0 && pipe.submissions==0);
                if ([name isEqual:@"stale-frame"] || [name isEqual:@"slow-query"]) {
                    assert(!accepted && pipe.submissions==0 && interface.statusCalls==1 && op.releases==1);
                }
                if ([name isEqual:@"frame-zero"] || [name isEqual:@"frame-source-mock"] || [name isEqual:@"short-before"])
                    assert(!accepted && pipe.submissions==0 && interface.statusCalls==1 && op.releases==1);
                if ([name hasPrefix:@"interrupt-"]) assert(!accepted && pipe.submissions==0 && pipe.aborts==0 && op.releases==1);
                if ([name isEqual:@"save-failed"])
                    assert([[NSFileManager defaultManager] createDirectoryAtPath:[dir stringByAppendingPathComponent:@"transfer"] withIntermediateDirectories:NO attributes:nil error:NULL]);
                if ([name isEqual:@"abort-refused"]) [driver requestExit];
                if ([name isEqual:@"detach-pending"]) [driver detachedRegistryID:102];
            });
            if ([name isEqual:@"pending-timeout"]) { usleep(2010000); dispatch_sync(q,^{ [driver poll]; assert(pipe.aborts==1); }); }
            BOOL callback=accepted && [@[@"clean",@"short-after",@"slow-enqueue",@"foreign-pointer",@"save-failed",@"post-close-late"] containsObject:name];
            IOUSBHostIsochronousTransactionCompletionHandler completion=pipe.callback; IOUSBHostIsochronousTransaction *address=pipe.rows;
            if (callback) {
                for (NSUInteger i=0;i<960;++i) pipe.rows[i].status=kIOReturnUnderrun;
                completion(0,[name isEqual:@"foreign-pointer"] ? (IOUSBHostIsochronousTransaction *)(uintptr_t)1 : address);
                dispatch_sync(q,^{ [driver poll]; });
            }
            if ([name isEqual:@"post-close-late"]) { completion(0,address); dispatch_sync(q,^{ [driver poll]; }); }
            dispatch_sync(q,^{
                if (driver.session.state==A23SessionClosed) {
                    [driver poll]; [clock advanceNS:250000001]; [driver poll];
                    assert(driver.finished && !driver.session.resourcesRetained && !driver.session.storageRetained);
                    assert(driver.exitCode==([name isEqual:@"clean"] ? 0 : 1));
                } else {
                    [clock advanceNS:1000000001]; [driver poll];
                    assert(!driver.finished && driver.unresolved && driver.session.resourcesRetained && driver.session.storageRetained);
                    assert(op.releases==0 && op.interface.destroys==0);
                    assert(pipe.aborts==([@[@"detach-pending",@"foreign-pointer",@"save-failed"] containsObject:name] ? 0 : 1));
                }
                NSUInteger statuses=interface.statusCalls;
                for (NSUInteger i=0;i<5;++i) { [driver poll]; [driver requestExit]; }
                assert(interface.statusCalls==statuses && pipe.aborts<=1 && pipe.submissions<=1);
            });
        }
        puts("18 injected SDK-shaped driver scenarios passed under ASan/UBSan. Real registry/SDK/USB calls: 0; no retry, no rejection-after-STATUS, no forced pending exit; interruption checked before enqueue.");
    }
    return 0;
}
