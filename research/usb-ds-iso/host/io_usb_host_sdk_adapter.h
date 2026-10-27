#import "io_usb_host_session.h"

NS_ASSUME_NONNULL_BEGIN
typedef void (^A23AdapterInterest)(uint32_t message);

@protocol A23AdapterInterface <NSObject>
- (nullable NSDictionary *)descriptorBytes:(NSError * _Nullable * _Nullable)error;
- (nullable id<A23TransactionTransport>)copyTransport:(NSError * _Nullable * _Nullable)error;
- (nullable NSData *)currentEndpointBytes;
- (nullable NSMutableData *)allocate:(NSUInteger)length shared:(BOOL)shared error:(NSError * _Nullable * _Nullable)error;
- (NSDictionary *)readStatus;
- (void)destroy;
@optional
- (NSDictionary *)readFrameSample;
@end
// Distinct fixed burst capability. The no-TD driver never calls this method.
@protocol A23AdapterBurstInterface <A23AdapterInterface>
- (BOOL)enqueueSequenceOneBurst:(IOUSBHostCompletionHandler)completion
    error:(NSError * _Nullable * _Nullable)error;
@end
@protocol A23PreparedBurstResources <A23SessionResources>
@property(readonly) BOOL sdkResources;
@property(readonly) BOOL supportsSingleBurst;
- (BOOL)enqueueSequenceOneBurst:(IOUSBHostCompletionHandler)completion
    error:(NSError * _Nullable * _Nullable)error;
@end
@protocol A23AdapterOperations <NSObject>
@property(readonly) BOOL simulation;
- (BOOL)retainService:(io_service_t)service error:(NSError * _Nullable * _Nullable)error;
- (void)releaseService:(io_service_t)service;
- (nullable NSDictionary *)identityForService:(io_service_t)service error:(NSError * _Nullable * _Nullable)error;
- (nullable id<A23AdapterInterface>)openService:(io_service_t)service queue:(dispatch_queue_t)queue
    interest:(A23AdapterInterest)interest error:(NSError * _Nullable * _Nullable)error;
@end

// Real IORegistry/SDK implementation. Compiled, never instantiated in tests.
// No enumeration, configuration change, reset or capture entry point. Fixed
// burst is available only through the distinct prepared-resource capability.
@interface A23DormantSDKOperations : NSObject <A23AdapterOperations>
@end

// Caller owns the borrowed token during openCandidate. Provider acquires its
// own reference before identity/open and retains it until interface destruction.
// Current provider accepts simulation operations only. It explicitly rejects
// dormant real SDK operations BEFORE any registry query/open. Future hardware
// execution requires a distinct prepared backend rather than changing a flag.
@interface A23AdapterSimulationProvider : NSObject <A23SessionProvider>
@property(readonly, nullable) id<A23SessionResources> openedResources;
- (instancetype)init NS_UNAVAILABLE;
+ (instancetype)new NS_UNAVAILABLE;
- (instancetype)initWithOperations:(id<A23AdapterOperations>)operations
    queue:(dispatch_queue_t)queue interest:(A23AdapterInterest)interest;
@end
// Explicit hardware provider. Uses cached SDK descriptors after open; rejects
// simulation operations. Registry iterator ownership stays with the caller.
@interface A23AdapterSDKProvider : A23AdapterSimulationProvider
@end
NS_ASSUME_NONNULL_END
