#import "io_usb_host_transaction_owner.h"

NS_ASSUME_NONNULL_BEGIN
@protocol A23RuntimeClock <NSObject>
- (uint64_t)nowTicks;
@property(readonly) uint32_t numerator;
@property(readonly) uint32_t denominator;
@end
// Local clock only; no controller query or hardware API.
@interface A23LocalMachClock : NSObject <A23RuntimeClock>
@end
FOUNDATION_EXPORT BOOL A23TicksToNanoseconds(uint64_t ticks, uint32_t numerator, uint32_t denominator, uint64_t *result);
FOUNDATION_EXPORT NSDictionary *A23RuntimeBudget(void);

// Final admission check runs inside enqueue, after the session's durable log.
// No disk work between admission and forwarding. Each instance forwards at most
// one request. The result is read after return, on the same serial queue.
@interface A23BudgetTransport : NSObject <A23TransactionTransport>
- (instancetype)init NS_UNAVAILABLE;
+ (instancetype)new NS_UNAVAILABLE;
- (instancetype)initWithTransport:(id<A23TransactionTransport>)transport clock:(id<A23RuntimeClock>)clock sample:(NSDictionary *)sample;
@property(readonly, nullable) NSDictionary *result;
@end
// Same guard, explicit SDK-origin observations. No service access in this class.
@interface A23SDKBudgetTransport : A23BudgetTransport
@end
NS_ASSUME_NONNULL_END
