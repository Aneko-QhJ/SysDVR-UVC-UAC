#import "io_usb_host_transaction_owner.h"
#include <mach/mach_time.h>
#include <string.h>

_Static_assert(sizeof(IOUSBHostIsochronousTransaction) == 28, "Unexpected SDK layout");

@implementation A23ExistingPipeTransport {
    IOUSBHostPipe *_pipe;
}
- (instancetype)initWithPipe:(IOUSBHostPipe *)pipe
{
    if ((self = [super init])) _pipe = pipe;
    return self;
}
- (BOOL)enqueueIORequestWithData:(NSMutableData *)data
                 transactionList:(IOUSBHostIsochronousTransaction *)transactions
            transactionListCount:(NSUInteger)count
                firstFrameNumber:(uint64_t)firstFrame
                         options:(IOUSBHostIsochronousTransferOptions)options
                           error:(NSError **)error
               completionHandler:(IOUSBHostIsochronousTransactionCompletionHandler)completion
{
    return [_pipe enqueueIORequestWithData:data transactionList:transactions
                     transactionListCount:count firstFrameNumber:firstFrame
                                  options:options error:error completionHandler:completion];
}
- (BOOL)abortWithOption:(IOUSBHostAbortOption)option error:(NSError **)error
{
    return [_pipe abortWithOption:option error:error];
}
@end

@implementation A23TransactionOwner {
    NSMutableData *_data;
    NSMutableData *_transactions;
    dispatch_queue_t _queue;
    id<A23TransactionTransport> _transport;
    void (^_finished)(NSDictionary *);
    A23TransactionOwnerState _state;
    BOOL _timedOut;
    NSUInteger _callbackCount;
    NSDictionary *_evidence;
    NSError *_abortError;
    uint64_t _firstFrame;
    uint64_t _submitBegin;
    uint64_t _submitReturn;
    A23TransactionOwner *_quarantine;
    void (^_observer)(NSDictionary *);
    uintptr_t _submittedAddress;
}
- (instancetype)initWithData:(NSMutableData *)data
                transactions:(NSMutableData *)transactions
                       queue:(dispatch_queue_t)queue
{
    if (data.length != 960 * 192 || transactions.length != 960 * 28 || !queue) return nil;
    if ((self = [super init])) {
        _data = data; _transactions = transactions; _queue = queue;
        _state = A23TransactionPrepared;
        IOUSBHostIsochronousTransaction *rows = transactions.mutableBytes;
        memset(rows, 0, transactions.length);
        for (NSUInteger i = 0; i < 960; ++i) {
            rows[i].status = kIOReturnInvalid;
            rows[i].requestCount = 192;
            rows[i].offset = (uint32_t)(i * 192);
            rows[i].options = IOUSBHostIsochronousTransactionOptionsNone;
        }
    }
    return self;
}
- (BOOL)observeCompletions:(void (^)(NSDictionary *))observer
{
    dispatch_assert_queue(_queue);
    if (_state != A23TransactionPrepared || _observer || !observer) return NO;
    _observer = [observer copy];
    return YES;
}
- (NSDictionary *)snapshot:(NSNumber *)overall submissionError:(NSError *)error
           pointerMismatch:(BOOL)mismatch arrival:(uint64_t)arrival
{
    // Copy every byte, including error frames and unfilled slots. No status
    // normalization, packing of only valid payloads, or transfer pass inference.
    NSMutableDictionary *record = [@{
        @"schema": @"A23-transaction-owner-1", @"backend": @"iousbhost-transaction-prototype-1",
        @"raw": [NSData dataWithBytes:_data.bytes length:_data.length],
        @"transactions": [NSData dataWithBytes:_transactions.bytes length:_transactions.length],
        @"transaction_count": @960, @"timed_out": @(_timedOut),
        @"first_frame": @(_firstFrame), @"request_bytes_per_transaction": @192,
        @"transfer_options": @0, @"submit_begin_ticks": @(_submitBegin),
        @"submit_return_ticks": @(_submitReturn),
        @"callback_pointer_mismatch": @(mismatch), @"callback_arrival_ticks": @(arrival),
    } mutableCopy];
    if (overall) record[@"overall_u32"] = overall;
    if (error) record[@"submission_error"] = @{@"domain": error.domain, @"code": @(error.code)};
    return [record copy];
}
- (BOOL)submitTo:(id<A23TransactionTransport>)transport firstFrame:(uint64_t)firstFrame
       finished:(void (^)(NSDictionary *))finished
{
    dispatch_assert_queue(_queue);
    if (_state != A23TransactionPrepared || !firstFrame || !transport || !finished) return NO;
    _state = A23TransactionPending; _transport = transport; _finished = [finished copy];
    _submittedAddress = (uintptr_t)_transactions.mutableBytes;
    _firstFrame = firstFrame; _submitBegin = mach_absolute_time();
    NSError *error = nil;
    BOOL accepted = [transport enqueueIORequestWithData:_data
        transactionList:_transactions.mutableBytes transactionListCount:960
        firstFrameNumber:firstFrame options:IOUSBHostIsochronousTransferOptionsNone error:&error
        completionHandler:^(IOReturn status, IOUSBHostIsochronousTransaction *rows) {
            uint64_t arrival = mach_absolute_time();
            // This block retains the owner and both backing stores until its
            // queued handler runs, even if the caller drops its own references.
            dispatch_async(self->_queue, ^{
                ++self->_callbackCount;
                A23TransactionOwnerState before = self->_state;
                BOOL consume = self->_callbackCount == 1 && before != A23TransactionRejected;
                BOOL mismatch = (uintptr_t)rows != self->_submittedAddress;
                if (consume) {
                    // Take the complete snapshot before a durable observer can
                    // block on disk. Duplicate callbacks never read storage.
                    self->_evidence = [self snapshot:@((uint32_t)status) submissionError:nil
                                          pointerMismatch:mismatch arrival:arrival];
                    self->_state = mismatch ? A23TransactionRetained : A23TransactionCompleted;
                    if (mismatch) self->_quarantine = self;
                }
                if (self->_observer) self->_observer(@{
                    @"count":@(self->_callbackCount), @"status_u32":@((uint32_t)status),
                    @"arrival_ticks":@(arrival),
                    @"pointer_mismatch":@(mismatch), @"owner_state_before":@(before)});
                if (!consume) return;
                // A foreign pointer is not proof that our DMA ownership ended.
                // Keep this one bounded request alive until the process exits;
                // no recovery/reset or unverified release is exposed here.
                void (^handler)(NSDictionary *) = self->_finished;
                self->_finished = nil;
                if (!mismatch) self->_transport = nil;
                handler(self->_evidence);
            });
        }];
    _submitReturn = mach_absolute_time();
    if (!accepted) {
        _state = A23TransactionRejected;
        _evidence = [self snapshot:nil submissionError:error pointerMismatch:NO arrival:0];
        void (^handler)(NSDictionary *) = _finished;
        _finished = nil; _transport = nil;
        handler(_evidence);
    }
    return accepted;
}
- (BOOL)deadlineReached
{
    dispatch_assert_queue(_queue);
    if (_state != A23TransactionPending) return NO;
    _timedOut = YES; _state = A23TransactionCancelPending;
    NSError *error = nil;
    BOOL accepted = [_transport abortWithOption:IOUSBHostAbortOptionAsynchronous error:&error];
    _abortError = error;
    if (!accepted) _state = A23TransactionRetained;
    // Abort return is not a callback drain and never releases backing storage.
    return accepted;
}
- (BOOL)acknowledgeEvidenceSaved
{
    dispatch_assert_queue(_queue);
    if (_state != A23TransactionCompleted && _state != A23TransactionRejected) return NO;
    _data = nil; _transactions = nil;
    return YES;
}
- (A23TransactionOwnerState)state { dispatch_assert_queue(_queue); return _state; }
- (BOOL)storageRetained { dispatch_assert_queue(_queue); return _data != nil && _transactions != nil; }
- (BOOL)timedOut { dispatch_assert_queue(_queue); return _timedOut; }
- (NSUInteger)callbackCount { dispatch_assert_queue(_queue); return _callbackCount; }
- (NSDictionary *)evidence { dispatch_assert_queue(_queue); return _evidence; }
- (NSError *)abortError { dispatch_assert_queue(_queue); return _abortError; }
@end
