#import "a23_live_two_epoch.h"
#import "a23_guard_cadence_api.h"
NS_ASSUME_NONNULL_BEGIN
@protocol A23CheckedEntryTarget <A23LiveEntryTarget>
- (BOOL)validateFinalExport;
@property(readonly) NSDictionary *exportEvidence;
@end
@interface A23VerifiedEntryCoordinator (A23CheckedExportEvidence)
@property(readonly) NSDictionary *exportEvidence;
@end
// Independent model controller. Success requires a payload plus an acceptance
// receipt after explicit checks. Neither artifact proves future disk freshness.
@interface A23CheckedTwoEpochRun : NSObject
- (instancetype)init NS_UNAVAILABLE;
+ (instancetype)new NS_UNAVAILABLE;
- (nullable instancetype)initWithTarget:(id<A23CheckedEntryTarget>)target directory:(NSString *)directory
    stop:(void (^)(void))stop;
- (BOOL)begin;
- (void)tick;
- (void)requestExit;
- (BOOL)finishAfterOperatorPowerOff;
@property(readonly) NSDictionary *status;
@end
NS_ASSUME_NONNULL_END
