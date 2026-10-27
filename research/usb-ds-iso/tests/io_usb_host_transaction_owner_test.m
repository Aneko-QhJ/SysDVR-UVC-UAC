// Offline mock only. A23ExistingPipeTransport is linked for signature checking
// but never instantiated. No IOUSBHost service object or real pipe is created.
#import "../host/io_usb_host_transaction_owner.h"
#include <assert.h>
#include <string.h>

@interface MockPipe : NSObject <A23TransactionTransport>
@property BOOL reject;
@property BOOL rejectAbort;
@property BOOL inlineCallback;
@property NSUInteger submissions;
@property NSUInteger aborts;
@property IOUSBHostIsochronousTransaction *rows;
@property(copy) IOUSBHostIsochronousTransactionCompletionHandler callback;
@end
@implementation MockPipe
- (BOOL)enqueueIORequestWithData:(NSMutableData *)data transactionList:(IOUSBHostIsochronousTransaction *)rows
            transactionListCount:(NSUInteger)count firstFrameNumber:(uint64_t)firstFrame
                         options:(IOUSBHostIsochronousTransferOptions)options error:(NSError **)error
               completionHandler:(IOUSBHostIsochronousTransactionCompletionHandler)completion
{
    ++_submissions;
    assert(data.length == 184320 && count == 960 && firstFrame == 100 && options == 0);
    for (NSUInteger i = 0; i < count; ++i) assert(rows[i].offset == i * 192 && rows[i].requestCount == 192);
    if (_reject) { *error = [NSError errorWithDomain:@"mock" code:-17 userInfo:nil]; return NO; }
    _rows = rows; _callback = [completion copy];
    if (_inlineCallback) { completion(0, rows); _callback = nil; }
    return YES;
}
- (BOOL)abortWithOption:(IOUSBHostAbortOption)option error:(NSError **)error
{
    ++_aborts; assert(option == IOUSBHostAbortOptionAsynchronous);
    if (_rejectAbort) { *error = [NSError errorWithDomain:@"mock" code:-18 userInfo:nil]; return NO; }
    return YES;
}
@end

static A23TransactionOwner *owner(dispatch_queue_t queue)
{
    NSMutableData *data = [NSMutableData dataWithLength:184320];
    memset(data.mutableBytes, 0x5a, data.length);
    return [[A23TransactionOwner alloc] initWithData:data
        transactions:[NSMutableData dataWithLength:26880] queue:queue];
}

int main(void)
{
    @autoreleasepool {
        dispatch_queue_t queue = dispatch_queue_create("a23.offline.owner", DISPATCH_QUEUE_SERIAL);
        for (NSUInteger rejectAbort = 0; rejectAbort < 2; ++rejectAbort) {
            A23TransactionOwner *request = owner(queue); MockPipe *pipe = [MockPipe new];
            pipe.rejectAbort = rejectAbort;
            __block NSUInteger finished = 0;
            dispatch_sync(queue, ^{
                assert([request submitTo:pipe firstFrame:100 finished:^(NSDictionary *e) {
                    ++finished; assert([e[@"overall_u32"] unsignedIntValue] == 0xe00002be);
                    assert([e[@"timed_out"] boolValue]);
                    assert([e[@"first_frame"] unsignedLongLongValue] == 100);
                    assert([e[@"submit_return_ticks"] unsignedLongLongValue] >=
                           [e[@"submit_begin_ticks"] unsignedLongLongValue]);
                    const IOUSBHostIsochronousTransaction *rows = [e[@"transactions"] bytes];
                    assert((uint32_t)rows[522].status == 0xe00002ed && rows[522].completeCount == 192);
                    assert(((const uint8_t *)[e[@"raw"] bytes])[522 * 192] == 0x5a);
                }]);
                assert(![request acknowledgeEvidenceSaved]);
                assert([request deadlineReached] == !rejectAbort);
                assert(![request deadlineReached] && pipe.aborts == 1 && request.storageRetained);
                assert(![request acknowledgeEvidenceSaved]);
                assert(request.state == (rejectAbort ? A23TransactionRetained : A23TransactionCancelPending));
            });
            pipe.rows[522].status = (IOReturn)0xe00002ed; pipe.rows[522].completeCount = 192;
            IOUSBHostIsochronousTransactionCompletionHandler callback = pipe.callback;
            pipe.callback = nil; callback((IOReturn)0xe00002be, pipe.rows);
            dispatch_sync(queue, ^{
                assert(finished == 1 && request.state == A23TransactionCompleted && request.storageRetained);
                assert([request acknowledgeEvidenceSaved] && !request.storageRetained);
                assert(![request submitTo:pipe firstFrame:100 finished:^(NSDictionary *e) { (void)e; assert(0); }]);
            });
            callback(0, (IOUSBHostIsochronousTransaction *)(uintptr_t)1); // No stale-storage access.
            dispatch_sync(queue, ^{ assert(request.callbackCount == 2 && finished == 1);
                assert([request.evidence[@"overall_u32"] unsignedIntValue] == 0xe00002be); });
        }
        {
            A23TransactionOwner *request = owner(queue); MockPipe *pipe = [MockPipe new]; pipe.reject = YES;
            dispatch_sync(queue, ^{
                assert(![request submitTo:pipe firstFrame:100 finished:^(NSDictionary *e) {
                    assert(e[@"overall_u32"] == nil && [e[@"submission_error"][@"code"] intValue] == -17);
                }]);
                assert(request.state == A23TransactionRejected && ![request deadlineReached] && pipe.aborts == 0);
                assert(request.storageRetained && [request acknowledgeEvidenceSaved]);
            });
        }
        {
            A23TransactionOwner *request = owner(queue); MockPipe *pipe = [MockPipe new]; pipe.inlineCallback = YES;
            __block BOOL finished = NO;
            dispatch_sync(queue, ^{ assert([request submitTo:pipe firstFrame:100 finished:^(NSDictionary *e) {
                finished = YES; assert(![e[@"callback_pointer_mismatch"] boolValue]); }]); });
            dispatch_sync(queue, ^{ assert(finished && request.state == A23TransactionCompleted); });
        }
        {
            MockPipe *pipe = [MockPipe new]; __weak A23TransactionOwner *weakRequest;
            @autoreleasepool {
                A23TransactionOwner *request = owner(queue); weakRequest = request;
                dispatch_sync(queue, ^{ assert([request submitTo:pipe firstFrame:100 finished:^(NSDictionary *e) {
                    assert([e[@"raw"] length] == 184320); }]); });
                request = nil;
            }
            assert(weakRequest != nil); // Framework-style block ownership preserves backing storage.
            @autoreleasepool {
                IOUSBHostIsochronousTransactionCompletionHandler callback = pipe.callback;
                pipe.callback = nil; callback(0, pipe.rows); callback = nil;
                dispatch_sync(queue, ^{});
            }
            assert(weakRequest == nil);
        }
        {
            A23TransactionOwner *request = owner(queue); MockPipe *pipe = [MockPipe new];
            dispatch_sync(queue, ^{ assert([request submitTo:pipe firstFrame:100 finished:^(NSDictionary *e) {
                assert([e[@"callback_pointer_mismatch"] boolValue] && [e[@"transactions"] length] == 26880); }]); });
            pipe.callback(0, (IOUSBHostIsochronousTransaction *)(uintptr_t)1); pipe.callback = nil;
            dispatch_sync(queue, ^{
                assert(request.callbackCount == 1 && request.state == A23TransactionRetained);
                assert(request.storageRetained && ![request acknowledgeEvidenceSaved]);
            });
        }
        assert([[A23TransactionOwner alloc] initWithData:[NSMutableData dataWithLength:1]
            transactions:[NSMutableData dataWithLength:26880] queue:queue] == nil);
        puts("Offline owner checks passed: error/raw preservation, cancellation and retained ownership, rejection, duplicate callback, inline callback, ARC lifetime, pointer mismatch, invalid storage. USB accessed: false.");
    }
    return 0;
}
