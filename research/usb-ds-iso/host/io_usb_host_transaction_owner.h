#import <Foundation/Foundation.h>
#import <IOUSBHost/IOUSBHost.h>

NS_ASSUME_NONNULL_BEGIN

// Injection boundary for offline tests. A future receiver supplies an already
// opened pipe; this component never enumerates or creates a USB service client.
@protocol A23TransactionTransport <NSObject>
- (BOOL)enqueueIORequestWithData:(NSMutableData *)data
                 transactionList:(IOUSBHostIsochronousTransaction *)transactions
            transactionListCount:(NSUInteger)count
                firstFrameNumber:(uint64_t)firstFrame
                         options:(IOUSBHostIsochronousTransferOptions)options
                           error:(NSError * _Nullable * _Nullable)error
               completionHandler:(IOUSBHostIsochronousTransactionCompletionHandler)completion;
- (BOOL)abortWithOption:(IOUSBHostAbortOption)option error:(NSError * _Nullable * _Nullable)error;
@end

@interface A23ExistingPipeTransport : NSObject <A23TransactionTransport>
- (instancetype)init NS_UNAVAILABLE;
+ (instancetype)new NS_UNAVAILABLE;
- (instancetype)initWithPipe:(IOUSBHostPipe *)pipe;
@end

typedef NS_ENUM(NSUInteger, A23TransactionOwnerState) {
    A23TransactionPrepared, A23TransactionPending, A23TransactionCancelPending,
    A23TransactionRetained, A23TransactionCompleted, A23TransactionRejected,
};

// One request only. Every method/property is accessed on the supplied serial
// queue. The SDK callback is marshalled there without waiting on that queue.
// Callers grant exclusive use of both buffers until evidence is acknowledged:
// no resizing, mutation, reuse, or external unmapping during that interval.
@interface A23TransactionOwner : NSObject
- (instancetype)init NS_UNAVAILABLE;
+ (instancetype)new NS_UNAVAILABLE;
- (nullable instancetype)initWithData:(NSMutableData *)data
                        transactions:(NSMutableData *)transactions
                               queue:(dispatch_queue_t)queue;
- (BOOL)submitTo:(id<A23TransactionTransport>)transport
     firstFrame:(uint64_t)firstFrame
       finished:(void (^)(NSDictionary *evidence))finished;
// Install once before submission. Observe all callbacks, including duplicates
// after storage release, without dereferencing their transaction pointer.
- (BOOL)observeCompletions:(void (^)(NSDictionary *event))observer;
- (BOOL)deadlineReached;
// Call only after writing and verifying evidence. Failure to save is not an ack.
- (BOOL)acknowledgeEvidenceSaved;
@property(readonly) A23TransactionOwnerState state;
@property(readonly) BOOL storageRetained;
@property(readonly) BOOL timedOut;
@property(readonly) NSUInteger callbackCount;
@property(readonly, nullable) NSDictionary *evidence;
@property(readonly, nullable) NSError *abortError;
@end

NS_ASSUME_NONNULL_END
