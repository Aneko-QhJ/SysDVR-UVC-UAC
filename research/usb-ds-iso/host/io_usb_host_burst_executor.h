#import "io_usb_host_runtime_guard.h"
#import "io_usb_host_evidence.h"
NS_ASSUME_NONNULL_BEGIN
// No SDK implementation exists for this interface. Only injected mocks may run.
@protocol A23BurstMockOperations <A23TransactionTransport>
@property(readonly) BOOL simulationOnly;
- (BOOL)enqueueBurst:(IOUSBDeviceRequest)request timeout:(NSTimeInterval)timeout
    completion:(IOUSBHostCompletionHandler)completion error:(NSError **)error;
- (NSData *)readAfterStatus;
- (void)closeMockResources;
@end
FOUNDATION_EXPORT NSDictionary *A23BurstExecutorSimulationPlan(void);
@interface A23BurstSimulationExecutor : NSObject
- (instancetype)initWithDirectory:(NSString *)directory queue:(dispatch_queue_t)queue
    clock:(id<A23RuntimeClock>)clock operations:(id<A23BurstMockOperations>)operations
    journal:(BOOL (^)(NSDictionary *event))journal;
- (BOOL)startBefore:(NSData *)before sample:(NSDictionary *)sample;
- (void)poll;
- (void)requestExit;
- (void)detached;
@property(readonly) NSDictionary *result;
@end
NS_ASSUME_NONNULL_END
