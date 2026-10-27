#import "io_usb_host_burst_sdk_driver.h"
NS_ASSUME_NONNULL_BEGIN
FOUNDATION_EXPORT NSDictionary *A23BurstDiagnosticScope(void);
// File checks/claim only; never creates SDK operations or accesses registry.
FOUNDATION_EXPORT BOOL A23ClaimBurstReceipt(NSString *directory, NSString *binary, NSError **error);
FOUNDATION_EXPORT BOOL A23SaveBurstEntryResult(NSString *directory, NSString *name, NSDictionary *result);
// Queue-confined preflight around the existing SDK coordinator. No discovery.
@interface A23BurstEntry : NSObject
- (instancetype)init NS_UNAVAILABLE;
+ (instancetype)new NS_UNAVAILABLE;
- (instancetype)initWithDirectory:(NSString *)directory queue:(dispatch_queue_t)queue clock:(id<A23RuntimeClock>)clock;
@property(copy, nullable) BOOL (^interruptionRequested)(void);
- (BOOL)startCandidates:(NSArray<NSDictionary *> *)candidates provider:(id<A23SessionProvider>)provider;
- (void)poll;
- (void)requestExit;
- (void)detachedRegistryID:(uint64_t)registryID;
@property(readonly) NSDictionary *result;
@end
NS_ASSUME_NONNULL_END
