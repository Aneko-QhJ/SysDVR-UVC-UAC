#pragma once
#import "io_usb_host_burst_entry.h"
#include "a23_passive_wait_adapter.h"
NS_ASSUME_NONNULL_BEGIN
FOUNDATION_EXPORT NSDictionary *A23WaitingBurstPlan(void);
// Exclusively created, bounded JSONL; fsync/readback of each row and parent.
@interface A23WaitingJournal : NSObject <A23SessionJournal>
- (instancetype)init NS_UNAVAILABLE;
+ (instancetype)new NS_UNAVAILABLE;
- (nullable instancetype)initWithPath:(NSString *)path;
@end
@protocol A23WaitingPermit <NSObject>
// Must burn one use durably BEFORE returning YES; never opens a device.
- (BOOL)claimForIdentity:(A23WaitIdentity)identity error:(NSError **)error;
@end
// File-only consumed-receipt checker. The caller must independently verify the
// build/source closure supplying these expected hashes. No ticket issuer/CLI.
// Same-queue use only; even a failed claim cannot be repeated on this object.
@interface A23WaitingReceiptPermit : NSObject <A23WaitingPermit>
- (instancetype)init NS_UNAVAILABLE;
+ (instancetype)new NS_UNAVAILABLE;
- (nullable instancetype)initWithDirectory:(NSString *)directory binary:(NSString *)binary
    buildManifest:(NSString *)manifest recipe:(NSString *)recipe;
@end
// Dormant integration component. No CLI, ticket renewal or native ops factory.
// All methods, ops, journals and callbacks confined to this caller queue.
// Keep the injected ops.context alive until waiter_closed; ops table is copied.
// SDK provider MUST independently retain the borrowed service and install its
// own termination observation before returning resources (existing SDK provider
// does so). Keep entry alive through finish; SDK driver retains unresolved I/O.
@interface A23WaitingBurstEntry : NSObject
- (instancetype)init NS_UNAVAILABLE;
+ (instancetype)new NS_UNAVAILABLE;
- (nullable instancetype)initWithDirectory:(NSString *)directory queue:(dispatch_queue_t)queue
    clock:(id<A23RuntimeClock>)clock journal:(id<A23SessionJournal>)journal;
@property(copy, nullable) BOOL (^interruptionRequested)(void);
- (BOOL)beginWithOps:(const A23WaitOps *)ops deadline:(uint64_t)deadline;
- (BOOL)pollWaiting;
// Select, claim permit, open/prepare, close adapter, construct dormant driver.
// Does NOT start STATUS, ISO or BURST. Injected ops.emit/now are replaced by
// this journal/clock; deadline is in this clock's ticks.
- (BOOL)prepareWithProvider:(id<A23SessionProvider>)provider permit:(id<A23WaitingPermit>)permit;
- (BOOL)startPrepared;
- (void)poll;
- (void)requestExit;
- (void)detachedRegistryID:(uint64_t)registryID;
@property(readonly) NSDictionary *result;
@end
NS_ASSUME_NONNULL_END
