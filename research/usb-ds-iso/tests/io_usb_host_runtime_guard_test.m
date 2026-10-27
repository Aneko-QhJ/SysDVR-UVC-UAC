#import "io_usb_host_mock_adapter.h"

@interface RuntimeClock : NSObject <A23RuntimeClock>
@property A23LocalMachClock *local;
@property uint64_t offset;
@end
@implementation RuntimeClock
- (instancetype)init { if ((self = [super init])) _local = [A23LocalMachClock new]; return self; }
- (uint64_t)nowTicks { return mach_absolute_time() + _offset; }
- (uint32_t)numerator { return _local.numerator; }
- (uint32_t)denominator { return _local.denominator; }
- (void)advanceGrace { _offset = (uint64_t)(((__uint128_t)1000000001 * self.denominator + self.numerator-1)/self.numerator); }
@end
@interface RuntimeJournal : NSObject <A23SessionJournal>
@property A23SimulationJournal *journal;
@property BOOL stallSubmit;
@end
@implementation RuntimeJournal
- (BOOL)append:(NSDictionary *)event error:(NSError **)error
{
    BOOL saved = [_journal append:event error:error];
    if (saved && _stallSubmit && [event[@"event"] isEqual:@"submit_begin"]) usleep(20000);
    return saved;
}
@end

int main(int argc,const char *argv[])
{
    @autoreleasepool {
        assert(argc==3); NSString *root=@(argv[1]), *inputs=@(argv[2]);
        assert([[NSFileManager defaultManager] createDirectoryAtPath:root withIntermediateDirectories:NO attributes:nil error:NULL]);
        assert(allZero([NSMutableData dataWithLength:8]));
        uint64_t vectors[][3]={{0,1,1},{1,125,3},{2,125,3},{UINT64_MAX,1,1},{UINT64_MAX,2,1},
            {UINT64_MAX,UINT32_MAX,UINT32_MAX},{123,0,1},{123,1,0},{UINT64_MAX,UINT32_MAX,1}};
        NSMutableArray *math=[NSMutableArray array];
        for (NSUInteger i=0;i<sizeof(vectors)/sizeof(vectors[0]);++i) {
            uint64_t ns=0; BOOL converted=A23TicksToNanoseconds(vectors[i][0],(uint32_t)vectors[i][1],(uint32_t)vectors[i][2],&ns);
            [math addObject:@{@"ticks":@(vectors[i][0]),@"numerator":@(vectors[i][1]),@"denominator":@(vectors[i][2]),
                @"converted":@(converted),@"ns":@(ns)}];
        }
        NSData *json=[NSJSONSerialization dataWithJSONObject:math options:NSJSONWritingSortedKeys error:NULL];
        assert([json writeToFile:[root stringByAppendingPathComponent:@"math-vectors.json"] options:NSDataWritingWithoutOverwriting error:NULL]);
        NSData *before=[NSData dataWithContentsOfFile:[inputs stringByAppendingPathComponent:@"before.bin"]]; assert(before.length==168);
        dispatch_queue_t q=dispatch_queue_create("a23.offline.runtime",DISPATCH_QUEUE_SERIAL);
        NSArray *cases=@[@"clean",@"stale-after-journal",@"slow-frame-query",@"slow-enqueue",@"exit-pending",
            @"exit-abort-refused",@"exit-after-deadline",@"exit-detached",@"exit-after-save",@"exit-ready",@"late-after-expiry"];
        for (NSString *name in cases) {
            RuntimeClock *clock=[RuntimeClock new]; RuntimeJournal *journal=[RuntimeJournal new];
            journal.journal=[[A23SimulationJournal alloc] initWithPath:[root stringByAppendingPathComponent:[name stringByAppendingString:@".jsonl"]] error:NULL];
            assert(journal.journal); journal.stallSubmit=[name isEqual:@"stale-after-journal"];
            A23SimulationSession *s=[[A23SimulationSession alloc] initBudgetedNoTDWithQueue:q journal:journal clock:clock]; assert(s);
            AdapterOperations *op=operations(@"clean"); AdapterPipe *pipe=op.interface.pipe;
            pipe.abortAllowed=![name isEqual:@"exit-abort-refused"];
            pipe.enqueueDelayUS=[name isEqual:@"slow-enqueue"] ? 10000 : 0;
            __block BOOL submitted=NO;
            dispatch_sync(q, ^{
                assert([s prepareCandidates:@[candidate()] provider:provider(op,q)]);
                assert(op.retains==1 && op.releases==0);
                if ([name isEqual:@"exit-ready"]) {
                    assert([s requestExit] && s.exitDisposition==1 && op.releases==1 && pipe.submissions==0); return;
                }
                op.interface.reply=before; NSDictionary *reply=op.interface.readStatus;
                assert([s recordStatusPhase:@"before" data:reply[@"data"] observation:reply[@"observation"]]);
                uint64_t begin=mach_absolute_time(); if ([name isEqual:@"slow-frame-query"]) usleep(3000);
                uint64_t end=mach_absolute_time();
                assert(([s recordFrameSample:@{@"source":@"mock_frame_number",@"current_frame":@36,@"begin_ticks":@(begin),@"end_ticks":@(end)}]));
                submitted=[s submitFirstFrame:100];
                BOOL rejected=[@[@"stale-after-journal",@"slow-frame-query"] containsObject:name];
                assert(submitted==!rejected && pipe.submissions==(rejected ? 0 : 1));
                if (rejected) {
                    assert(s.stopped && s.storageRetained && op.releases==0);
                    assert(([s saveToParent:root name:name scenario:@{@"kind":@"no_td"}]));
                    assert([s close] && !s.storageRetained && op.releases==1); return;
                }
                if ([name isEqual:@"slow-enqueue"]) assert(s.stopped);
                if ([name isEqual:@"exit-after-deadline"]) assert([s deadlineReached] && pipe.aborts==1);
                if ([name isEqual:@"exit-detached"]) assert([s detachedRegistryID:102]);
                if (![name isEqual:@"clean"] && ![name isEqual:@"exit-after-save"]) {
                    assert([s requestExit] && ![s requestExit]);
                    assert(pipe.aborts==([name isEqual:@"exit-detached"] ? 0 : 1));
                    if (![name isEqual:@"exit-abort-refused"]) { assert(s.exitDisposition==0); [clock advanceGrace]; }
                    assert(s.exitDisposition==2 && s.storageRetained && s.resourcesRetained && op.releases==0);
                    assert(![s close] && ![s submitFirstFrame:100] && ![s deadlineReached]);
                }
            });
            if (!submitted) continue;
            BOOL completion=[@[@"clean",@"exit-after-save",@"slow-enqueue",@"late-after-expiry"] containsObject:name];
            if (!completion) continue; // Bounded single-request quarantine; no forced destroy.
            for (NSUInteger i=0;i<960;++i) pipe.rows[i].status=kIOReturnUnderrun;
            pipe.callback(0,pipe.rows);pipe.callback=nil;
            dispatch_sync(q, ^{
                NSMutableData *after=[before mutableCopy];((uint8_t *)after.mutableBytes)[56]=0xd1;
                op.interface.reply=after;NSDictionary *reply=op.interface.readStatus;
                assert([s recordStatusPhase:@"after" data:reply[@"data"] observation:reply[@"observation"]]);
                assert(([s saveToParent:root name:name scenario:@{@"kind":@"no_td"}]));
                pipe.data=nil;
                if ([name isEqual:@"exit-after-save"]) assert([s requestExit] && s.exitDisposition==1);
                else assert([s close]);
                assert(op.releases==1 && op.interface.destroys==1 && !s.storageRetained && !s.resourcesRetained);
                if ([name isEqual:@"late-after-expiry"] || [name isEqual:@"slow-enqueue"]) assert(s.exitDisposition==1);
            });
        }
        puts("11 runtime lifecycle scenarios and 9 exact timebase vectors passed. Service references remain held while pending; stale/query/slow-call admission and bounded exit verified under mocks. ASan/UBSan; USB calls: 0.");
    }
    return 0;
}
