#import "a23_paired_sdk_adapter.h"

NS_ASSUME_NONNULL_BEGIN
// Dormant SDK orchestration: caller supplies an unused prepared SDK lease and
// polls on its serial queue. No service open/enumeration, CLI, ticket, reset or
// authorization. SDK-shaped injected operations are used by offline tests.
// Keeps all stores and shared resources for process lifetime after start.
@interface A23TwoEpochSDKDriver : NSObject <A23TransactionTransport>
- (instancetype)init NS_UNAVAILABLE;
+ (instancetype)new NS_UNAVAILABLE;
- (nullable instancetype)initWithResources:(id<A23PairedResources>)resources
    firstSequence:(uint16_t)first directory:(NSString *)directory queue:(dispatch_queue_t)queue
    clock:(id<A23RuntimeClock>)clock journal:(id<A23SessionJournal>)journal
    error:(NSError * _Nullable * _Nullable)error;
- (BOOL)start;
- (void)poll;
- (void)requestStop;
- (void)detachedRegistryID:(uint64_t)registryID;
// Once after successful observation, or after a stop for failure evidence.
// Exclusive commit; no retry/overwrite. A late callback may stale a committed
// receipt. Caller must inspect current result AND receiptStatus before ending.
- (BOOL)saveReceiptOnce;
@property(readonly) NSDictionary *result;
@property(readonly) NSDictionary *receiptStatus;
@end
NS_ASSUME_NONNULL_END
