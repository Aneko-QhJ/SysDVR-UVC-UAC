#import "io_usb_host_sdk_adapter.h"
NS_ASSUME_NONNULL_BEGIN

// Dormant capability adapter, not a capture entry point. Caller supplies an
// already prepared SDK lease from A23AdapterSDKProvider. No registry/open here.
// All public calls use queue; callbacks marshal there. Events need a durable
// sink. This class has no hardware journal/bundle exporter or ticket writer.
@interface A23DormantBurstSDKTransport : NSObject <A23TransactionTransport>
- (instancetype)init NS_UNAVAILABLE;
+ (instancetype)new NS_UNAVAILABLE;
- (nullable instancetype)initWithResources:(id<A23PreparedBurstResources>)resources
    queue:(dispatch_queue_t)queue clock:(id<A23RuntimeClock>)clock
    event:(BOOL (^)(NSDictionary *event))event error:(NSError * _Nullable * _Nullable)error;
@property(readonly) BOOL simulationOnly; // Always NO; mock executor must reject.
@property(readonly, nullable) A23TransactionOwner *owner;
// Native ingress of the first control callback, before queue dispatch. A
// software deadline must not mistake queue delay for SDK completion delay.
@property(readonly) uint64_t controlArrivalTicks;
@property(readonly) uint64_t isoArrivalTicks;
- (BOOL)recordBefore:(NSDictionary *)reply;
- (BOOL)recordFrame:(NSDictionary *)sample;
- (BOOL)submitISO;
- (BOOL)triggerOnce;
- (nullable NSDictionary *)readAfter;
- (BOOL)requestAbortOnce;
- (BOOL)detachedRegistryID:(uint64_t)registryID;
// Caller must have saved/read back the exact owner's evidence and acknowledged
// it. Transport never acknowledges, reuses, or unmaps the owner buffers itself.
- (BOOL)closeAfterOwnerAcknowledged;
@property(readonly) NSDictionary *result;
@end
NS_ASSUME_NONNULL_END
