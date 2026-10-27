// Isolated, model-only revision. No receiver or hardware entry adopts this API.
#import "a23_scope_verifier.h"
NS_ASSUME_NONNULL_BEGIN
@interface A23ReadOnlyScopeVerifier (A23GuardCadence)
// Checks the changing job/claim files. Requires a prior successful full check;
// this method alone does not certify current source/baseline/archive bytes.
- (BOOL)verifyLiveJob:(NSDictionary *)scope job:(NSString *)job;
- (void)setCheckPhase:(NSString *)phase;
- (NSDictionary *)cadenceMetrics;
@end
@interface A23VerifiedEntryCoordinator (A23GuardCadence)
// Explicit full check before and after an export. Snapshot getters do no IO
// and cannot attest to freshness after the last explicit boundary.
- (BOOL)validateFinalExport;
@end
NS_ASSUME_NONNULL_END
