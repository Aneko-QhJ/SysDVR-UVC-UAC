#import "../host/io_usb_host_session.h"
#include <assert.h>
#include <string.h>
#include <signal.h>
#include <sys/resource.h>
#include <sys/stat.h>

@interface SessionPipe : NSObject <A23TransactionTransport>
@property BOOL reject, abortAccepted;
@property NSUInteger submissions, aborts;
@property IOUSBHostIsochronousTransaction *rows;
@property(copy) IOUSBHostIsochronousTransactionCompletionHandler callback;
@end
@implementation SessionPipe
- (BOOL)enqueueIORequestWithData:(NSMutableData *)data transactionList:(IOUSBHostIsochronousTransaction *)rows
    transactionListCount:(NSUInteger)count firstFrameNumber:(uint64_t)firstFrame
    options:(IOUSBHostIsochronousTransferOptions)options error:(NSError **)error
    completionHandler:(IOUSBHostIsochronousTransactionCompletionHandler)completion
{
    assert(data.length == 184320 && count == 960 && firstFrame == 100 && options == 0); ++_submissions;
    if (_reject) { *error = [NSError errorWithDomain:@"session-mock" code:-17 userInfo:nil]; return NO; }
    _rows = rows; _callback = completion; return YES;
}
- (BOOL)abortWithOption:(IOUSBHostAbortOption)option error:(NSError **)error
{
    assert(option == IOUSBHostAbortOptionAsynchronous); ++_aborts;
    if (!_abortAccepted) *error = [NSError errorWithDomain:@"session-mock" code:-18 userInfo:nil];
    return _abortAccepted;
}
@end

@interface SessionLease : NSObject <A23SessionResources>
@property NSDictionary *identity;
@property NSMutableData *dataStorage, *transactionStorage;
@property id<A23TransactionTransport> transport;
@property NSUInteger closes;
@end
@implementation SessionLease
- (void)closeWhenNoIO
{
    assert(_closes == 0); ++_closes;
    _transport = nil; _dataStorage = nil; _transactionStorage = nil;
}
@end

@interface SessionProvider : NSObject <A23SessionProvider>
@property SessionLease *lease;
@property NSUInteger opens;
@property BOOL rejectOpen;
@property(copy) void (^duringOpen)(void);
@end
@implementation SessionProvider
- (id<A23SessionResources>)openCandidate:(NSDictionary *)candidate error:(NSError **)error
{
    assert([candidate[@"interface_id"] intValue] == 102); ++_opens;
    if (_duringOpen) _duringOpen();
    if (_rejectOpen) { if (error) *error = [NSError errorWithDomain:@"session-mock" code:-19 userInfo:nil]; return nil; }
    return _lease;
}
@end

static NSDictionary *candidate(void)
{
    uint8_t d[] = {18,1,0,2,0,0,0,64,9,0x12,0x57,0xca,0,1,0,0,0,1};
    uint8_t c[] = {9,2,25,0,1,1,0,0x80,50,9,4,2,0,1,0xff,0x49,1,0,7,5,0x83,1,0,1,1};
    return @{@"device_id":@101, @"interface_id":@102, @"parent_device_id":@101,
        @"connection_speed":@3, @"device_descriptor":[NSData dataWithBytes:d length:sizeof(d)],
        @"configuration_descriptor":[NSData dataWithBytes:c length:sizeof(c)]};
}

static SessionProvider *provider(SessionPipe *pipe)
{
    SessionLease *lease = [SessionLease new];
    lease.identity = @{@"device_id":@101, @"interface_id":@102, @"parent_device_id":@101};
    lease.dataStorage = [NSMutableData dataWithLength:184320];
    lease.transactionStorage = [NSMutableData dataWithLength:26880]; lease.transport = pipe;
    SessionProvider *result = [SessionProvider new]; result.lease = lease; return result;
}

int main(int argc, const char *argv[])
{
    @autoreleasepool {
        assert(argc == 2); NSString *parent = [NSString stringWithUTF8String:argv[1]];
        assert([[NSFileManager defaultManager] createDirectoryAtPath:parent withIntermediateDirectories:NO attributes:nil error:NULL]);
        dispatch_queue_t queue = dispatch_queue_create("a23.offline.session",DISPATCH_QUEUE_SERIAL);
        NSArray *names = @[@"clean",@"late-after-close",@"detach-pending",@"detach-missing-callback",
            @"foreign-pointer",@"timeout-accepted",@"timeout-rejected",@"submit-rejected",
            @"open-rejected",@"identity-changed",@"candidate-ambiguous",@"parent-mismatch",
            @"detach-ready",@"detach-during-open",@"save-failed",@"journal-failed"];
        for (NSUInteger mode = 0; mode < names.count; ++mode) {
            NSString *name = names[mode];
            A23SimulationJournal *journal = [[A23SimulationJournal alloc] initWithPath:
                [parent stringByAppendingPathComponent:[name stringByAppendingString:@".jsonl"]] error:NULL];
            assert(journal);
            __block A23SimulationSession *session = [[A23SimulationSession alloc] initWithQueue:queue journal:journal];
            SessionPipe *pipe = [SessionPipe new]; pipe.abortAccepted = mode == 5; pipe.reject = mode == 7;
            SessionProvider *p = provider(pipe); p.rejectOpen = mode == 8;
            if (mode == 9) p.lease.identity = @{@"device_id":@101,@"interface_id":@103,@"parent_device_id":@101};
            if (mode == 13) {
                __weak A23SimulationSession *weakSession = session;
                p.duringOpen = ^{ assert([weakSession detachedRegistryID:101]); };
            }
            NSArray *candidates = mode == 10 ? @[candidate(),candidate()] : @[candidate()];
            if (mode == 11) { NSMutableDictionary *bad = [candidate() mutableCopy]; bad[@"parent_device_id"] = @999; candidates = @[bad]; }
            __block BOOL prepared = NO;
            dispatch_sync(queue, ^{
                prepared = [session prepareCandidates:candidates provider:p];
                if (mode >= 8 && mode <= 11) assert(!prepared);
                else if (mode == 13) assert(!prepared && p.lease.closes == 1);
                else assert(prepared);
                if (mode == 10 || mode == 11) assert(p.opens == 0);
            });
            if (!prepared) continue;
            if (mode == 12) {
                dispatch_sync(queue, ^{
                    assert([session detachedRegistryID:101] && session.stopped);
                    assert(session.state == A23SessionClosed && p.lease.closes == 1 && !session.storageRetained);
                    assert(![session submitFirstFrame:100] && pipe.submissions == 0);
                }); continue;
            }
            if (mode == 15) {
                // A partial journal append before enqueue must prevent submission.
                struct rlimit old, limited; assert(getrlimit(RLIMIT_FSIZE,&old) == 0); limited = old;
                struct stat info; assert(stat([[parent stringByAppendingPathComponent:[name stringByAppendingString:@".jsonl"]] fileSystemRepresentation],&info) == 0);
                limited.rlim_cur = (rlim_t)info.st_size + 32;
                void (*handler)(int) = signal(SIGXFSZ,SIG_IGN); assert(setrlimit(RLIMIT_FSIZE,&limited) == 0);
                dispatch_sync(queue, ^{ assert(![session submitFirstFrame:100]); assert(session.journalFailed && session.stopped); });
                assert(setrlimit(RLIMIT_FSIZE,&old) == 0); signal(SIGXFSZ,handler);
                assert(pipe.submissions == 0); continue;
            }
            dispatch_sync(queue, ^{
                assert([session submitFirstFrame:100] == (mode != 7));
                assert(![session submitFirstFrame:100] && pipe.submissions == 1);
                assert(![session close]); // No evidence saved, including rejected enqueue.
                if (mode == 2 || mode == 3) {
                    assert(![session detachedRegistryID:999] && !session.stopped);
                    assert([session detachedRegistryID:102] && session.resourcesRetained && session.storageRetained);
                    assert(![session deadlineReached] && pipe.aborts == 0 && ![session close]);
                }
                if (mode == 5 || mode == 6) {
                    assert([session deadlineReached] == (mode == 5));
                    assert(![session deadlineReached] && pipe.aborts == 1 && session.storageRetained);
                    assert(![session close]);
                }
            });
            if (mode == 3) {
                __weak A23SimulationSession *weakSession = session;
                session = nil; assert(weakSession != nil);
                dispatch_sync(queue, ^{ assert(weakSession.resourcesRetained && weakSession.storageRetained && p.lease.closes == 0); });
                continue; // Intentionally quarantined until process exits.
            }
            IOUSBHostIsochronousTransactionCompletionHandler callback = pipe.callback;
            IOUSBHostIsochronousTransaction *pointer = pipe.rows;
            if (mode != 7) {
                for (NSUInteger i = 0; i < 960; ++i) pipe.rows[i].status = kIOReturnUnderrun;
                for (NSUInteger n = 0; n < 16; ++n) {
                    NSUInteger i = 522 + n; uint16_t seq = (uint16_t)(1 + n);
                    uint8_t *packet = (uint8_t *)p.lease.dataStorage.mutableBytes + i*192;
                    memcpy(packet,"ISO1",4); packet[4] = (uint8_t)seq; packet[5] = (uint8_t)(seq >> 8);
                    for (NSUInteger j = 6; j < 192; ++j) packet[j] = (uint8_t)(j ^ seq ^ (seq >> 8));
                    pipe.rows[i].status = 0; pipe.rows[i].completeCount = 192;
                }
                callback(0,mode == 4 ? (IOUSBHostIsochronousTransaction *)(uintptr_t)1 : pointer);
                pipe.callback = nil;
                dispatch_sync(queue, ^{});
            }
            if (mode == 4) {
                dispatch_sync(queue, ^{ assert(session.state == A23SessionRetained && session.storageRetained);
                    assert((![session saveToParent:parent name:name scenario:@{@"kind":@"single_burst",@"first_sequence":@1}]));
                    assert(![session close] && p.lease.closes == 0); }); continue;
            }
            dispatch_sync(queue, ^{
                NSDictionary *scenario = @{@"kind":@"single_burst",@"first_sequence":@1};
                if (mode == 14) {
                    assert([[NSFileManager defaultManager] createDirectoryAtPath:[parent stringByAppendingPathComponent:name]
                        withIntermediateDirectories:NO attributes:nil error:NULL]);
                    assert(![session saveToParent:parent name:name scenario:scenario]);
                    assert(session.stopped && session.storageRetained && ![session close] && p.lease.closes == 0); return;
                }
                assert([session saveToParent:parent name:name scenario:scenario]);
                assert(!session.storageRetained && [session close] && p.lease.closes == 1 && !session.resourcesRetained);
                assert(![session close] && ![session submitFirstFrame:100]);
            });
            if (mode == 1) {
                __weak A23SimulationSession *weakSession = session; session = nil;
                assert(weakSession != nil);
                callback(0,pointer); // Released array: compare pointer only, never dereference.
                dispatch_sync(queue, ^{ assert(weakSession.stopped && !weakSession.resourcesRetained); });
            }
        }
        puts("16 offline lifecycle scenarios passed: identity/selection, single enqueue, detach, missing/foreign/late callbacks, timeout, rejection, save and journal failure. ASan/UBSan; USB accessed: false.");
    }
    return 0;
}
