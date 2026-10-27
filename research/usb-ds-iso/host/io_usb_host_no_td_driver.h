#import "io_usb_host_sdk_adapter.h"
NS_ASSUME_NONNULL_BEGIN
// Queue-confined orchestration, injectable for offline tests. Does not enumerate.
@interface A23NoTDDriver : NSObject
// Configure before start. A signal handler may set an atomic flag read here;
// checks between preflight calls prevent progressing after an interruption.
@property(copy, nullable) BOOL (^interruptionRequested)(void);
- (instancetype)initWithDirectory:(NSString *)directory queue:(dispatch_queue_t)queue
    clock:(id<A23RuntimeClock>)clock;
- (BOOL)startCandidates:(NSArray<NSDictionary *> *)candidates provider:(A23AdapterSDKProvider *)provider;
- (void)poll;
- (void)requestExit;
- (void)detachedRegistryID:(uint64_t)registryID;
@property(readonly) A23SDKNoTDSession *session;
@property(readonly) BOOL finished;
@property(readonly) BOOL unresolved;
@property(readonly) int exitCode;
@end
NS_ASSUME_NONNULL_END
