#import "a23_short24_capture.h"
NS_ASSUME_NONNULL_BEGIN
// Exclusive local writes, fsync and exact readback; no capture/owner acknowledgement.
FOUNDATION_EXPORT BOOL A23Short24WriteRecord(NSString *parent,NSString *name,NSDictionary *record,NSError **error);
FOUNDATION_EXPORT BOOL A23Short24WriteObservation(NSString *parent,NSString *name,NSDictionary *snapshot,NSError **error);
@interface A23Short24Runtime:NSObject
- (instancetype)init NS_UNAVAILABLE;
+ (instancetype)new NS_UNAVAILABLE;
- (nullable instancetype)initWithCapture:(A23Short24Capture *)capture queue:(dispatch_queue_t)queue
    directory:(NSString *)directory context:(NSDictionary *)context clockNanoseconds:(uint64_t (^)(void))clock;
- (BOOL)start;
- (void)poll;
- (void)requestStop;
- (void)providerInterest:(uint32_t)message; // May be called from SDK interest queue.
@property(readonly) NSDictionary *result;
@end
NS_ASSUME_NONNULL_END
