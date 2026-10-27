#import "a23_two_epoch_entry.h"
NS_ASSUME_NONNULL_BEGIN
typedef BOOL (^A23SharedScopeVerifier)(NSDictionary *scope);
// File-only bridge. Caller freshly verifies current/frozen build, latest saved
// card, history and consumed authorization in verifier; no default verifier or
// acquisition CLI. Same-queue calls only. Both classes keep one-shot instance
// and durable file gates; distinct processes compete with exclusive markers.
@interface A23SharedSequencePermit : NSObject <A23TwoEpochEntryPermit>
- (instancetype)init NS_UNAVAILABLE;
+ (instancetype)new NS_UNAVAILABLE;
- (nullable instancetype)initWithJob:(NSString *)job expectedScope:(NSDictionary *)scope
    verifier:(A23SharedScopeVerifier)verifier;
@property(readonly) NSDictionary *result;
@end
// Explicit injected-model class; production class rejects model receipts before
// creating an attempt marker. This class never authenticates a live process.
@interface A23SharedSequenceModelPermit : A23SharedSequencePermit
@end
NS_ASSUME_NONNULL_END
