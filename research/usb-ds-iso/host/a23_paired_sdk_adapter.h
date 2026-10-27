#import "io_usb_host_sdk_adapter.h"
#import "a23_two_epoch_receiver.h"

NS_ASSUME_NONNULL_BEGIN
@protocol A23PairedInterface <A23AdapterInterface>
- (BOOL)enqueueScopedBurst:(uint16_t)first completion:(IOUSBHostCompletionHandler)completion
    error:(NSError * _Nullable * _Nullable)error;
@end

@protocol A23PairedResources <A23TwoEpochResources>
@property(readonly) BOOL sdkResources;
@property(readonly) NSDictionary *result;
// Only before runtime STATUS/frame/ISO/BURST, without interest or uncertainty.
// This is preparation cleanup, never an active-I/O cancellation/drain operation.
- (BOOL)closeUnused;
@end

// Compiled SDK implementation. Explicit caller-supplied service only; no
// enumeration/reset/configuration/CLI. Descriptor lookup may issue USB requests.
@interface A23PairedSDKOperations : A23DormantSDKOperations
@end

// One preparation attempt per provider. Two data+transaction allocations on a
// single copied pipe, stable identity before open/after open/after allocations.
// Simulation and SDK providers reject the wrong operations mode before retain.
@interface A23PairedSimulationProvider : NSObject
- (instancetype)init NS_UNAVAILABLE;
+ (instancetype)new NS_UNAVAILABLE;
- (instancetype)initWithOperations:(id<A23AdapterOperations>)operations
    queue:(dispatch_queue_t)queue interest:(A23AdapterInterest)interest firstSequence:(uint16_t)first;
- (nullable id<A23PairedResources>)openCandidate:(NSDictionary *)candidate
    error:(NSError * _Nullable * _Nullable)error;
@property(readonly) NSDictionary *result;
@property(readonly, nullable) id<A23PairedResources> retainedFailure;
@end
// Separate dormant SDK capability. Current offline receiver rejects its output;
// no execution driver or issuance/hardware authorization is provided here.
@interface A23PairedSDKProvider : A23PairedSimulationProvider
@end
NS_ASSUME_NONNULL_END
