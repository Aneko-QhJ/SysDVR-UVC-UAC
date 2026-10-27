#import "a23_shared_sequence_permit.h"
NS_ASSUME_NONNULL_BEGIN
FOUNDATION_EXPORT NSDictionary *A23VerifiedEntryDescription(void);
// File-only verifier, immutable embedded descriptor. Failure latches forever.
@interface A23ReadOnlyScopeVerifier : NSObject
- (instancetype)init NS_UNAVAILABLE;
+ (instancetype)new NS_UNAVAILABLE;
- (nullable instancetype)initWithBuild:(NSString *)build;
// Archive-only checks do not resolve any embedded live input root.
- (nullable instancetype)initWithArchive:(NSString *)build;
- (BOOL)verifyArchive;
- (BOOL)verifyCore;
- (BOOL)verifyScope:(NSDictionary *)scope job:(NSString *)job;
@property(readonly,nullable) NSDictionary *scope;
@property(readonly) NSDictionary *result;
@end
// Explicit test roots. Rejects roots outside /private/tmp; no implicit fallback.
@interface A23ModelScopeVerifier : A23ReadOnlyScopeVerifier
- (nullable instancetype)initWithBuild:(NSString *)build repository:(NSString *)repository
    cards:(NSString *)cards ledger:(NSString *)ledger records:(NSString *)records;
@end
// Holds the verifier and native permit. Complete file checks happen before
// begin/start, at idle epoch boundaries and final export; never while an ISO or
// control operation remains outstanding on the caller queue. No automatic exit.
@interface A23VerifiedEntryCoordinator : NSObject
- (instancetype)init NS_UNAVAILABLE;
+ (instancetype)new NS_UNAVAILABLE;
- (instancetype)initWithEntry:(A23TwoEpochEntry *)entry verifier:(A23ReadOnlyScopeVerifier *)verifier
    permit:(A23SharedSequencePermit *)permit scope:(NSDictionary *)scope job:(NSString *)job;
- (BOOL)begin;
- (void)tick;
- (BOOL)finalizeOnce;
@property(readonly) NSDictionary *result;
@property(readonly) NSDictionary *finalStatus;
@end
NS_ASSUME_NONNULL_END
