#import "a23_scope_verifier.h"
NS_ASSUME_NONNULL_BEGIN
@interface A23TwoEpochSDKDriver (A23LiveFailureEvidence)
- (NSArray<NSDictionary *> *)liveFailureSnapshots;
@end
@interface A23TwoEpochEntry (A23LiveFailureEvidence)
- (NSArray<NSDictionary *> *)liveFailureSnapshots;
@end
@protocol A23LiveEntryTarget <NSObject>
- (BOOL)begin;
- (void)tick;
- (BOOL)finalizeOnce;
@property(readonly) NSDictionary *result,*finalStatus;
@optional
- (NSArray<NSDictionary *> *)liveFailureSnapshots;
@end
// Same-queue controlled experiment loop. A stopped SDK lease is retained; this
// controller never kills, destroys, retries, or reads an in-flight data buffer.
@interface A23LiveTwoEpochRun : NSObject
- (instancetype)init NS_UNAVAILABLE;
+ (instancetype)new NS_UNAVAILABLE;
- (nullable instancetype)initWithTarget:(id<A23LiveEntryTarget>)target directory:(NSString *)directory
    stop:(void (^)(void))stop;
- (BOOL)begin;
- (void)tick;
- (void)requestExit;
// Explicit caller statement after a retained failure; never a drain assertion.
- (BOOL)finishAfterOperatorPowerOff;
@property(readonly) NSDictionary *status;
@end
NS_ASSUME_NONNULL_END
