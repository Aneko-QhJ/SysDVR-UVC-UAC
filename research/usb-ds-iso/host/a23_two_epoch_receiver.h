#import "io_usb_host_session.h"

NS_ASSUME_NONNULL_BEGIN
// Separate two-epoch capability. This revision accepts offline simulation only;
// there is no SDK provider, enumeration, launch CLI or hardware authorization.
// Stores are exclusive, fixed-size, independently allocated and never resized.
// The shared transport and all four stores remain retained for process lifetime
// after the first attempt, including success. No close/destroy/drain API exists.
@protocol A23TwoEpochResources <NSObject>
@property(readonly) BOOL offlineSimulation;
@property(readonly) NSDictionary *identity, *descriptorBytes;
@property(readonly) NSArray<NSMutableData *> *dataStores, *transactionStores;
@property(readonly) id<A23TransactionTransport> transport;
- (NSDictionary *)readStatus;
- (NSDictionary *)readFrameSample;
- (BOOL)enqueueBurst:(uint16_t)firstSequence completion:(IOUSBHostCompletionHandler)completion
    error:(NSError * _Nullable * _Nullable)error;
@end

@interface A23TwoEpochReceiver : NSObject <A23TransactionTransport>
- (instancetype)init NS_UNAVAILABLE;
+ (instancetype)new NS_UNAVAILABLE;
- (nullable instancetype)initWithResources:(id<A23TwoEpochResources>)resources
    firstSequence:(uint16_t)first directory:(NSString *)directory queue:(dispatch_queue_t)queue
    clock:(id<A23RuntimeClock>)clock journal:(id<A23SessionJournal>)journal
    error:(NSError * _Nullable * _Nullable)error;
// Once only. poll advances at most one phase; a completed first epoch is saved
// before a later poll may arm the second. All methods use the serial queue.
// The clock must also be thread-safe for recording native callback ingress.
- (BOOL)start;
- (void)poll;
- (void)requestStop;
- (void)detachedRegistryID:(uint64_t)registryID;
@property(readonly) NSDictionary *result;
@end
NS_ASSUME_NONNULL_END
