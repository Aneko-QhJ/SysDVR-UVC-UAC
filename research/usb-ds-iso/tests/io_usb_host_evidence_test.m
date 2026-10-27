// Offline integration only. No service enumeration, matching call, open, or USB.
#import "../host/io_usb_host_evidence.h"
#include <assert.h>
#include <signal.h>
#include <string.h>
#include <sys/resource.h>

@interface EvidenceMock : NSObject <A23TransactionTransport>
@property BOOL reject;
@property IOUSBHostIsochronousTransaction *rows;
@property(copy) IOUSBHostIsochronousTransactionCompletionHandler callback;
@end
@implementation EvidenceMock
- (BOOL)enqueueIORequestWithData:(NSMutableData *)data transactionList:(IOUSBHostIsochronousTransaction *)rows
    transactionListCount:(NSUInteger)count firstFrameNumber:(uint64_t)firstFrame
    options:(IOUSBHostIsochronousTransferOptions)options error:(NSError **)error
    completionHandler:(IOUSBHostIsochronousTransactionCompletionHandler)completion
{
    assert(data.length == 184320 && count == 960 && firstFrame == 100 && options == 0);
    if (_reject) { *error = [NSError errorWithDomain:@"mock" code:-17 userInfo:nil]; return NO; }
    _rows = rows; _callback = completion; return YES;
}
- (BOOL)abortWithOption:(IOUSBHostAbortOption)option error:(NSError **)error
{
    assert(option == IOUSBHostAbortOptionAsynchronous);
    *error = [NSError errorWithDomain:@"mock" code:-18 userInfo:nil]; return NO;
}
@end

static void descriptors(void)
{
    uint8_t device[18] = {18,1,0,2,0,0,0,64,9,0x12,0x57,0xca,0,1,0,0,0,1};
    uint8_t config[] = {9,2,25,0,1,1,0,0x80,50, 9,4,2,0,1,0xff,0x49,1,0, 7,5,0x83,1,0,1,1};
    NSData *d = [NSData dataWithBytes:device length:sizeof(device)];
    NSData *c = [NSData dataWithBytes:config length:sizeof(config)];
    NSError *error = nil;
    assert([A23ValidateDescriptors(d,c,3,&error)[@"interval"] intValue] == 1);
    assert(A23ValidateDescriptors(d,c,4,&error) == nil); // No SS acceptance.
    assert(A23ValidateDescriptors([d subdataWithRange:NSMakeRange(0,17)],c,3,&error) == nil);
    for (NSUInteger field = 0; field < 7; ++field) {
        NSMutableData *bad = [c mutableCopy]; uint8_t *bytes = bad.mutableBytes;
        NSUInteger indices[] = {9, 11, 12, 16, 20, 23, 24};
        bytes[indices[field]] = field == 2 ? 1 : 0;
        assert(A23ValidateDescriptors(d,bad,3,&error) == nil);
    }
    NSMutableData *duplicate = [c mutableCopy];
    [duplicate appendData:[c subdataWithRange:NSMakeRange(9,16)]];
    ((uint8_t *)duplicate.mutableBytes)[2] = (uint8_t)duplicate.length;
    assert(A23ValidateDescriptors(d,duplicate,3,&error) == nil);
    NSMutableData *truncated = [c mutableCopy]; [truncated setLength:24];
    ((uint8_t *)truncated.mutableBytes)[2] = 24;
    assert(A23ValidateDescriptors(d,truncated,3,&error) == nil);
    // Unrelated UVC interface is allowed and never selected.
    NSMutableData *composite = [c mutableCopy]; uint8_t uvc[] = {9,4,0,0,0,14,1,0,0};
    [composite appendBytes:uvc length:sizeof(uvc)];
    ((uint8_t *)composite.mutableBytes)[2] = (uint8_t)composite.length;
    ((uint8_t *)composite.mutableBytes)[4] = 2;
    assert(A23ValidateDescriptors(d,composite,3,&error) != nil);
}

int main(int argc, const char *argv[])
{
    @autoreleasepool {
        assert(argc == 2);
        NSString *parent = [NSString stringWithUTF8String:argv[1]];
        assert([[NSFileManager defaultManager] createDirectoryAtPath:parent
            withIntermediateDirectories:NO attributes:nil error:NULL]);
        descriptors();
        dispatch_queue_t queue = dispatch_queue_create("a23.offline.evidence", DISPATCH_QUEUE_SERIAL);
        NSArray *names = @[@"clean", @"native-error", @"timeout", @"rejected", @"duplicate", @"no-td"];
        for (NSUInteger mode = 0; mode < names.count; ++mode) {
            NSMutableData *raw = [NSMutableData dataWithLength:184320];
            A23TransactionOwner *owner = [[A23TransactionOwner alloc] initWithData:raw
                transactions:[NSMutableData dataWithLength:26880] queue:queue];
            EvidenceMock *mock = [EvidenceMock new]; mock.reject = mode == 3;
            dispatch_sync(queue, ^{
                assert([owner submitTo:mock firstFrame:100 finished:^(NSDictionary *e) { (void)e; }] == !mock.reject);
                if (!mock.reject) assert(!A23SaveSimulationEvidence(owner,parent,@"pending",@{},NULL));
                if (mode == 2) assert(![owner deadlineReached] && owner.storageRetained);
            });
            if (!mock.reject) {
                for (NSUInteger i = 0; i < 960; ++i) mock.rows[i].status = kIOReturnUnderrun;
                if (mode != 5) for (NSUInteger n = 0; n < 16; ++n) {
                    NSUInteger i = 522 + n; uint16_t seq = (uint16_t)(65530 + n);
                    uint8_t *packet = (uint8_t *)raw.mutableBytes + i * 192;
                    memcpy(packet,"ISO1",4); packet[4] = (uint8_t)seq; packet[5] = (uint8_t)(seq >> 8);
                    for (NSUInteger j = 6; j < 192; ++j) packet[j] = (uint8_t)(j ^ seq ^ (seq >> 8));
                    mock.rows[i].completeCount = 192; mock.rows[i].status = mode == 1 ? kIOReturnNotResponding : 0;
                    mock.rows[i].timeStamp = 1000 + n;
                }
                mock.callback(mode == 1 ? kIOReturnNoResources : 0, mock.rows);
                if (mode == 4) mock.callback(0,mock.rows);
                mock.callback = nil;
                dispatch_sync(queue, ^{});
            }
            dispatch_sync(queue, ^{
                NSError *error = nil;
                NSDictionary *scenario = mode == 5 ? @{@"kind":@"no_td"} :
                    @{@"kind":@"single_burst", @"first_sequence":@65530};
                assert(!A23SaveSimulationEvidence(owner,parent,@"../escape",scenario,&error));
                assert(!A23SaveSimulationEvidence(owner,parent,@"bad-json",@{@"data":[NSData data]},&error));
                assert(owner.storageRetained);
                if (mode == 0) {
                    // Fail midway through raw.bin, retaining buffers and no commit marker.
                    struct rlimit previous, limited;
                    assert(getrlimit(RLIMIT_FSIZE,&previous) == 0); limited = previous; limited.rlim_cur = 128;
                    void (*handler)(int) = signal(SIGXFSZ,SIG_IGN);
                    assert(setrlimit(RLIMIT_FSIZE,&limited) == 0);
                    BOOL saved = A23SaveSimulationEvidence(owner,parent,@"partial-write",scenario,&error);
                    assert(setrlimit(RLIMIT_FSIZE,&previous) == 0); signal(SIGXFSZ,handler);
                    assert(!saved && owner.storageRetained);
                    assert(![[NSFileManager defaultManager] fileExistsAtPath:
                        [[parent stringByAppendingPathComponent:@"partial-write"] stringByAppendingPathComponent:@"COMMITTED"]]);
                    // Existing directory/symlink refusal cannot release storage.
                    assert(!A23SaveSimulationEvidence(owner,parent,@"partial-write",scenario,&error));
                    NSString *link = [parent stringByAppendingPathComponent:@"symlink"];
                    assert([[NSFileManager defaultManager] createSymbolicLinkAtPath:link
                        withDestinationPath:@"partial-write" error:&error]);
                    assert(!A23SaveSimulationEvidence(owner,parent,@"symlink",scenario,&error) && owner.storageRetained);
                }
                assert(A23SaveSimulationEvidence(owner,parent,names[mode],scenario,&error));
                assert(!owner.storageRetained);
                assert(!A23SaveSimulationEvidence(owner,parent,names[mode],scenario,&error));
            });
        }
        puts("Offline descriptor and durable evidence integration checks passed; six simulated bundles; mid-write failure retained buffers. USB accessed: false.");
    }
    return 0;
}
