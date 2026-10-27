// Compile-only SDK feasibility probe. No main, device enumeration, or capture entry.
// This is not a receiver; callers would need to establish ownership and preserve
// backing storage until completion before using the API in a real experiment.
#import <IOUSBHost/IOUSBHost.h>
#include <stddef.h>

_Static_assert(sizeof(IOUSBHostIsochronousTransaction) == 28, "Unexpected transaction size");
_Static_assert(offsetof(IOUSBHostIsochronousTransaction, status) == 0, "Unexpected status offset");
_Static_assert(offsetof(IOUSBHostIsochronousTransaction, requestCount) == 4, "Unexpected request offset");
_Static_assert(offsetof(IOUSBHostIsochronousTransaction, offset) == 8, "Unexpected data offset");
_Static_assert(offsetof(IOUSBHostIsochronousTransaction, completeCount) == 12, "Unexpected actual offset");
_Static_assert(offsetof(IOUSBHostIsochronousTransaction, timeStamp) == 16, "Unexpected time offset");
_Static_assert(offsetof(IOUSBHostIsochronousTransaction, options) == 24, "Unexpected options offset");

BOOL a23_sdk_transaction_signature_probe(
    IOUSBHostPipe *pipe, NSMutableData *data,
    IOUSBHostIsochronousTransaction *transactions, NSUInteger count,
    uint64_t firstFrame, NSError **error,
    IOUSBHostIsochronousTransactionCompletionHandler completion)
{
    return [pipe enqueueIORequestWithData:data
                         transactionList:transactions
                    transactionListCount:count
                        firstFrameNumber:firstFrame
                                 options:IOUSBHostIsochronousTransferOptionsNone
                                   error:error
                       completionHandler:completion];
}
