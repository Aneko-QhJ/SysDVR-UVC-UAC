#pragma once
#import "a23_waiting_burst_entry.h"
NS_ASSUME_NONNULL_BEGIN
FOUNDATION_EXPORT NSDictionary *A23WaitingReceiverDescription(void);
// File-only guard, includes current and frozen source hashes embedded at build.
FOUNDATION_EXPORT NSDictionary * _Nullable A23CheckWaitingBuild(NSString *build,NSString *binary,NSError **error);
FOUNDATION_EXPORT NSDictionary * _Nullable A23CheckWaitingConsumed(NSString *run,NSString *build,NSString *binary,NSError **error);
// Caller invokes only after build+consumed receipt verification. One use even
// when this durable create fails. No device, signal or process operations here.
FOUNDATION_EXPORT BOOL A23ClaimWaitingProcess(NSString *run,NSDictionary *checked);
// Rechecks build/current sources + receipt at selected handoff, verifies the
// earlier process claim, then delegates the existing single-use SDK claim.
FOUNDATION_EXPORT id<A23WaitingPermit> A23MakeWaitingBoundPermit(NSString *run,NSString *build,NSString *binary,NSDictionary *checked);
// Caller queue only. Preparation and start occupy distinct tick invocations;
// the real main uses separate dispatch timer turns. No automatic retry/exit.
@interface A23WaitingReceiverLoop : NSObject
- (instancetype)init NS_UNAVAILABLE;
+ (instancetype)new NS_UNAVAILABLE;
- (nullable instancetype)initWithHost:(NSString *)host queue:(dispatch_queue_t)queue
    clock:(id<A23RuntimeClock>)clock ops:(const A23WaitOps *)ops
    provider:(id<A23SessionProvider>)provider permit:(id<A23WaitingPermit>)permit;
@property(copy,nullable) BOOL (^interruptionRequested)(void);
- (BOOL)begin;
- (void)tick;
- (void)requestExit;
- (void)detachedRegistryID:(uint64_t)identity;
@property(readonly) uint64_t selectedInterfaceID;
@property(readonly) NSDictionary *result;
@end
NS_ASSUME_NONNULL_END
