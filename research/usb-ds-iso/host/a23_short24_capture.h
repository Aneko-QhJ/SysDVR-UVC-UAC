#import <Foundation/Foundation.h>
#import <IOUSBHost/IOUSBHost.h>

NS_ASSUME_NONNULL_BEGIN
FOUNDATION_EXPORT uint64_t A23Short24NowNanoseconds(void);
@protocol A23Short24IO <NSObject>
@property(readonly) BOOL simulation;
@property(readonly) NSMutableData *dataStorage;
@property(readonly) NSMutableData *transactionStorage;
- (NSDictionary *)readStatus;
- (NSDictionary *)frameSample;
- (BOOL)enqueueISO:(uint64_t)frame completion:(IOUSBHostIsochronousTransactionCompletionHandler)completion
             error:(NSError * _Nullable * _Nullable)error;
- (BOOL)enqueueBurst:(uint16_t)first completion:(IOUSBHostCompletionHandler)completion
               error:(NSError * _Nullable * _Nullable)error;
- (BOOL)abortISO:(NSError * _Nullable * _Nullable)error;
@end

// No discovery/open/reset/close. Caller supplies already-open objects and owns
// their provider-interest registration. This adapter never proves deployment.
@interface A23Short24SDKIO : NSObject <A23Short24IO>
- (instancetype)init NS_UNAVAILABLE;
+ (instancetype)new NS_UNAVAILABLE;
- (nullable instancetype)initWithInterface:(IOUSBHostInterface *)interface pipe:(IOUSBHostPipe *)pipe
    queue:(dispatch_queue_t)queue speed:(NSUInteger)speed error:(NSError * _Nullable * _Nullable)error;
@end

// One ISO and one BURST. No backing release/reuse API. A started object holds
// itself and its I/O resources, including on rejection, timeout and success.
// Call poll on queue; forward every provider-interest event immediately.
// Caller grants exclusive use of both backing stores, including their lengths.
@interface A23Short24Capture : NSObject
- (instancetype)init NS_UNAVAILABLE;
+ (instancetype)new NS_UNAVAILABLE;
- (nullable instancetype)initWithIO:(id<A23Short24IO>)io queue:(dispatch_queue_t)queue
    clockNanoseconds:(uint64_t (^)(void))clock recipe:(NSString *)recipe firstSequence:(uint16_t)first;
// For SDKIO supply A23Short24NowNanoseconds; fixture clocks are injected only.
- (BOOL)start;
- (void)poll;
- (void)requestStop;
- (void)providerInterest:(uint32_t)message; // Any thread, latch before dispatch.
@property(readonly) NSDictionary *result;
// Immutable byte copies. Pending copies are explicitly partial observations.
// Caller persists these; this API never acknowledges DMA handoff or commit.
@property(readonly) NSDictionary *snapshot;
@end
NS_ASSUME_NONNULL_END
