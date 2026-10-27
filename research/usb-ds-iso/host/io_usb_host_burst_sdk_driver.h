#import "io_usb_host_burst_sdk_transport.h"
NS_ASSUME_NONNULL_BEGIN
FOUNDATION_EXPORT NSDictionary *A23DormantBurstSDKPlan(void);
// Dormant orchestration only: already prepared SDK lease, trusted output
// directory and serial queue supplied by caller. No service discovery, open,
// ticket or CLI. Poll regularly; unresolved requests remain alive for late I/O.
@interface A23DormantBurstSDKDriver : NSObject
- (instancetype)init NS_UNAVAILABLE;
+ (instancetype)new NS_UNAVAILABLE;
- (nullable instancetype)initWithResources:(id<A23PreparedBurstResources>)resources
    directory:(NSString *)directory queue:(dispatch_queue_t)queue clock:(id<A23RuntimeClock>)clock
    journal:(id<A23SessionJournal>)journal error:(NSError * _Nullable * _Nullable)error;
@property(copy, nullable) BOOL (^interruptionRequested)(void);
- (BOOL)start;
- (void)poll;
- (void)requestExit;
- (void)detachedRegistryID:(uint64_t)registryID;
@property(readonly) NSDictionary *result;
@end
NS_ASSUME_NONNULL_END
