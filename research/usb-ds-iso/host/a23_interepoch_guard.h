#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN
// Isolated fixed-three-epoch candidate. No hardware entry adopts this class.
// Every public call and every block except fullCheck runs on queue.
// Caller hands exclusive verifier ownership to fullCheck until finished runs.
@interface A23InterepochGuard : NSObject
- (instancetype)init NS_UNAVAILABLE;
+ (instancetype)new NS_UNAVAILABLE;
- (nullable instancetype)initWithQueue:(dispatch_queue_t)queue
    job:(NSString *)job scopeDigest:(NSString *)scopeDigest
    fullCheck:(BOOL (^)(void))fullCheck
    boundary:(NSDictionary *(^)(void))boundary
    recheck:(BOOL (^)(void))recheck
    poll:(void (^)(void))poll
    stop:(void (^)(void))stop
    finished:(void (^)(void))finished;
// Only saved->arm transitions 1 and 2, in order. One check may be outstanding.
// deadline is an absolute CLOCK_MONOTONIC_RAW value; expiry stops admission,
// retaining the worker. It does not cancel a blocking file call.
- (BOOL)requestEpoch:(NSUInteger)epoch deadlineNS:(uint64_t)deadline;
- (void)observeDeadline;
- (void)stopWithReason:(NSString *)reason;
// Returns controller-owned values only; never reads verifier/permit/SDK state.
@property(readonly) NSDictionary *result;
@end
NS_ASSUME_NONNULL_END
