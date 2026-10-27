// Offline injected transport, Foundation memory, actual one-shot owner code.
// This fixture has no SDK interface/pipe creation or allocation path.
#import "../host/io_usb_host_transaction_owner.h"
#include <assert.h>
#include <string.h>

@interface RearmPipe : NSObject <A23TransactionTransport>
@property NSMutableArray *dataStores, *rowPointers, *callbacks;
@property NSUInteger submissions, aborts;
@end
@implementation RearmPipe
- (instancetype)init {
    if ((self=[super init])) {
        _dataStores=[NSMutableArray new]; _rowPointers=[NSMutableArray new]; _callbacks=[NSMutableArray new];
    }
    return self;
}
- (BOOL)enqueueIORequestWithData:(NSMutableData *)data transactionList:(IOUSBHostIsochronousTransaction *)rows
    transactionListCount:(NSUInteger)count firstFrameNumber:(uint64_t)frame options:(IOUSBHostIsochronousTransferOptions)options
    error:(NSError **)error completionHandler:(IOUSBHostIsochronousTransactionCompletionHandler)callback
{
    (void)error; assert(data.length==184320 && rows && count==960 && options==0);
    assert(_submissions<2 && frame==100+_submissions*32);
    [_dataStores addObject:data]; [_rowPointers addObject:[NSValue valueWithPointer:rows]];
    [_callbacks addObject:[callback copy]]; ++_submissions; return YES;
}
- (BOOL)abortWithOption:(IOUSBHostAbortOption)option error:(NSError **)error {
    (void)error; assert(option==IOUSBHostAbortOptionAsynchronous); ++_aborts; return YES;
}
- (void)emit:(NSUInteger)ordinal pointer:(IOUSBHostIsochronousTransaction *)rows status:(IOReturn)status {
    IOUSBHostIsochronousTransactionCompletionHandler callback=_callbacks[ordinal]; callback(status,rows);
}
@end

static NSDictionary *scenario(NSString *mode) {
    dispatch_queue_t q=dispatch_queue_create("a23.rearm.offline",DISPATCH_QUEUE_SERIAL);
    RearmPipe *pipe=[RearmPipe new];
    NSMutableArray<NSMutableData *> *stores=[NSMutableArray new];
    NSMutableArray<A23TransactionOwner *> *owners=[NSMutableArray new];
    __block BOOL stopped=NO; __block NSUInteger finished=0, observed=0;
    for (NSUInteger n=0;n<2;++n) {
        NSMutableData *data=[NSMutableData dataWithLength:184320], *rows=[NSMutableData dataWithLength:26880];
        [stores addObject:data]; [stores addObject:rows];
        A23TransactionOwner *owner=[[A23TransactionOwner alloc] initWithData:data transactions:rows queue:q];
        assert(owner); [owners addObject:owner];
        dispatch_sync(q, ^{
            assert([owner observeCompletions:^(NSDictionary *event) {
                ++observed;
                if ([event[@"count"] unsignedIntegerValue]!=1 || [event[@"pointer_mismatch"] boolValue] ||
                    [event[@"status_u32"] unsignedIntValue]!=0) stopped=YES;
            }]);
        });
    }
    // Check actual live address spans, not integer model identities.
    for (NSUInteger a=0;a<4;++a) for (NSUInteger b=a+1;b<4;++b) {
        uintptr_t x=(uintptr_t)stores[a].mutableBytes,y=(uintptr_t)stores[b].mutableBytes;
        assert(x+stores[a].length<=y || y+stores[b].length<=x);
    }
    for (NSUInteger n=0;n<2 && !stopped;++n) {
        dispatch_sync(q, ^{
            assert([owners[n] submitTo:pipe firstFrame:100+n*32 finished:^(NSDictionary *record) {
                assert([record[@"raw"] length]==184320 && [record[@"transactions"] length]==26880); ++finished;
            }]);
            assert(![owners[n] submitTo:pipe firstFrame:200 finished:^(NSDictionary *r) {(void)r;}]);
        });
        IOUSBHostIsochronousTransaction *rows=stores[n*2+1].mutableBytes;
        memset(stores[n*2].mutableBytes,n ? 0x97 : 0x81,184320);
        for (NSUInteger i=0;i<960;++i) { rows[i].status=0; rows[i].completeCount=i<16 ? 192 : 0; }
        if (n==1 && [mode isEqual:@"late-old"]) {
            // Old owner was acknowledged. Duplicate deliberately carries an
            // invalid pointer: duplicate path must never dereference it.
            [pipe emit:0 pointer:(void *)1 status:0]; dispatch_sync(q, ^{});
            assert(stopped && owners.count==2); break;
        }
        if (n==1 && [mode isEqual:@"timeout"]) {
            dispatch_sync(q, ^{ assert([owners[n] deadlineReached] && owners[n].storageRetained); stopped=YES; });
            assert(pipe.aborts==1); break;
        }
        IOUSBHostIsochronousTransaction *reply=(n==1 && [mode isEqual:@"cross-pointer"]) ? stores[1].mutableBytes : rows;
        [pipe emit:n pointer:reply status:(n==1 && [mode isEqual:@"status-error"]) ? kIOReturnError : 0];
        dispatch_sync(q, ^{
            if (n==0 && [mode isEqual:@"save-failure"]) { stopped=YES; assert(owners[n].storageRetained); return; }
            if (stopped) { assert(owners[n].storageRetained); return; }
            // This is an injected durable-save acknowledgement, NOT file I/O
            // or proof of control/ISO7/URB/sequence matching.
            assert([owners[n] acknowledgeEvidenceSaved] && !owners[n].storageRetained);
        });
    }
    dispatch_sync(q, ^{
        assert(stores.count==4 && ((uint8_t *)stores[0].bytes)[0]==0x81);
        assert([owners[0].evidence[@"raw"] isEqual:stores[0]]);
        if ([mode isEqual:@"normal"]) assert(!stopped && finished==2 && observed==2 && pipe.submissions==2);
        else assert(stopped);
        if ([mode isEqual:@"late-old"]) assert(owners[0].callbackCount==2 && owners[1].callbackCount==0 && finished==1);
        if ([mode isEqual:@"cross-pointer"]) assert(owners[1].state==A23TransactionRetained);
        if ([mode isEqual:@"save-failure"]) assert(pipe.submissions==1 && finished==1);
        if ([mode isEqual:@"status-error"]) assert(owners[1].state==A23TransactionCompleted);
    });
    return @{@"submissions":@(pipe.submissions),@"finished":@(finished),@"observations":@(observed),
        @"stopped":@(stopped),@"distinct_live_storage_spans":@4,@"session_keeps_all_stores":@YES};
}

int main(void) {
    @autoreleasepool {
        NSMutableDictionary *cases=[NSMutableDictionary new];
        for (NSString *mode in @[@"normal",@"late-old",@"cross-pointer",@"timeout",@"save-failure",@"status-error"])
            cases[mode]=scenario(mode);
        NSDictionary *result=@{@"cases":cases,@"case_count":@6,@"real_sdk_objects":@0,
            @"usb_requests":@0,@"sdk_allocations":@0,@"storage_is_foundation_memory":@YES,
            @"durable_save_injected":@YES,@"coordinator_is_fixture_only":@YES};
        NSData *json=[NSJSONSerialization dataWithJSONObject:result options:NSJSONWritingSortedKeys error:NULL];
        assert(json); fwrite(json.bytes,1,json.length,stdout); puts("");
    }
    return 0;
}
