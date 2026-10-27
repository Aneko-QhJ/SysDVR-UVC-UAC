#import "a23_two_epoch_sdk_driver.h"
#import "a23_execution_context.h"
#include "a23_passive_wait_adapter.h"
NS_ASSUME_NONNULL_BEGIN
// Caller implements fresh build/source, issuance/consumption and latest-card
// checks. Each YES must first burn the corresponding use durably. No default
// production permit exists here. Injected fixtures never issue formal records.
@protocol A23TwoEpochEntryPermit <NSObject>
- (BOOL)claimProcess:(NSDictionary *)binding context:(NSDictionary *)context;
- (BOOL)claimSelection:(A23WaitIdentity)identity binding:(NSDictionary *)binding context:(NSDictionary *)context;
@end
FOUNDATION_EXPORT NSDictionary *A23TwoEpochEntryDescription(void);
FOUNDATION_EXPORT NSDictionary * _Nullable A23TwoEpochEntryCheckBuild(NSString *build,NSString *binary);
// Supplied clock/ops/permit/provider and context must outlive the loop. All API
// calls are on the serial queue. No discovery/open occurs until begin+tick.
@interface A23TwoEpochEntry : NSObject
- (instancetype)init NS_UNAVAILABLE;
+ (instancetype)new NS_UNAVAILABLE;
- (nullable instancetype)initWithDirectory:(NSString *)directory queue:(dispatch_queue_t)queue
    clock:(id<A23RuntimeClock>)clock ops:(const A23WaitOps *)ops
    provider:(A23PairedSimulationProvider *)provider permit:(id<A23TwoEpochEntryPermit>)permit
    context:(NSDictionary *)context binding:(NSDictionary *)binding;
- (BOOL)begin;
- (void)tick;
- (void)requestExit;
- (void)detachedRegistryID:(uint64_t)identity;
// Exclusive checkpoint, never automatic process exit or resource release.
- (BOOL)finalizeOnce;
@property(readonly) NSDictionary *result;
@property(readonly) NSDictionary *finalStatus;
@end
NS_ASSUME_NONNULL_END
