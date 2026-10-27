#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN
// Offline terminal adapter. No receiver or hardware launcher adopts this class.
// All calls/callbacks use queue except fullCheck, which exclusively owns the
// verifier until the work block returns. poll must finish a lightweight health
// check before returning YES; a timer firing alone is not a service sample.
@interface A23TerminalObservation : NSObject
- (instancetype)init NS_UNAVAILABLE;
+ (instancetype)new NS_UNAVAILABLE;
- (nullable instancetype)initWithQueue:(dispatch_queue_t)queue
    binding:(NSDictionary *)binding fullCheck:(BOOL (^)(void))fullCheck
    recheck:(BOOL (^)(void))recheck poll:(BOOL (^)(void))poll
    finalCheck:(BOOL (^)(void))finalCheck finished:(void (^)(void))finished;
// Exactly one request on this instance, including failed admission. Boundary:
// saved_epochs=iso_attempts=3, durable=true, pending=stopped=false.
- (BOOL)requestBoundary:(NSDictionary *)boundary deadlineNS:(uint64_t)deadline;
- (void)tick;
- (void)requestStop;
@property(readonly) BOOL busy;
@property(readonly) BOOL exitAllowed;
// Snapshot never reads the verifier or live job. While busy it cannot pass.
@property(readonly) NSDictionary *result;
@end
NS_ASSUME_NONNULL_END
