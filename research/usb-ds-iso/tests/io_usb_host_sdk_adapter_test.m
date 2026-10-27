#import "io_usb_host_mock_adapter.h"

@interface DetailedOpenFailure : AdapterOperations
@end
@implementation DetailedOpenFailure
- (id<A23AdapterInterface>)openService:(io_service_t)service queue:(dispatch_queue_t)queue
    interest:(A23AdapterInterest)interest error:(NSError **)error
{
    (void)service; (void)queue; (void)interest;
    self.opens++;
    if (error) *error = [NSError errorWithDomain:@"IOUSBHostErrorDomain" code:(int32_t)kIOReturnNotPermitted
        userInfo:@{NSLocalizedDescriptionKey:@"Unable to open io_service_t object and create user client.",
                   NSLocalizedFailureReasonErrorKey:@"IOServiceOpen failed."}];
    return nil;
}
@end

int main(int argc, const char *argv[])
{
    @autoreleasepool {
        assert(argc == 3); NSString *root = @(argv[1]), *inputs = @(argv[2]);
        assert([[NSFileManager defaultManager] createDirectoryAtPath:root withIntermediateDirectories:NO attributes:nil error:NULL]);
        dispatch_queue_t q = dispatch_queue_create("a23.offline.sdk",DISPATCH_QUEUE_SERIAL);
        NSArray *faults = @[@"clean",@"real-blocked",@"token-missing",@"token-bool",@"retain-failed",@"pre-identity",@"float-identity",
            @"open-failed",@"post-identity",@"descriptors-nil",@"active-alt",@"config-changed",@"device-changed",
            @"pipe-nil",@"endpoint-wrong",@"data-nil",@"transactions-nil",@"data-short",@"transactions-short"];
        for (NSString *fault in faults) {
            AdapterOperations *op = operations(fault); NSMutableDictionary *c = [candidate() mutableCopy];
            if ([fault isEqual:@"token-missing"]) [c removeObjectForKey:@"service_token"];
            if ([fault isEqual:@"token-bool"]) c[@"service_token"] = @YES;
            dispatch_sync(q, ^{
                NSError *error = nil;
                id<A23SessionResources> lease = [provider(op,q) openCandidate:c error:&error];
                if ([fault isEqual:@"clean"]) {
                    assert(lease && allZero(lease.dataStorage) && allZero(lease.transactionStorage));
                    assert(op.retains == 1 && op.releases == 0);
                    [lease closeWhenNoIO]; [lease closeWhenNoIO]; assert(op.interface.destroys == 1 && op.releases == 1);
                } else {
                    assert(!lease && op.interface.pipe.submissions == 0);
                    NSDictionary *stages = @{@"real-blocked":@"provider_mode",@"token-missing":@"service_token",@"token-bool":@"service_token",
                        @"retain-failed":@"retain_service",@"pre-identity":@"identity_before",@"float-identity":@"identity_before",
                        @"open-failed":@"sdk_init",@"post-identity":@"identity_after",@"descriptors-nil":@"descriptors",
                        @"active-alt":@"descriptors",@"config-changed":@"descriptors",@"device-changed":@"descriptors",
                        @"pipe-nil":@"copy_pipe_83",@"endpoint-wrong":@"endpoint_83",@"data-nil":@"allocate_raw_184320",
                        @"data-short":@"allocate_raw_184320",@"transactions-nil":@"allocate_transactions_26880",
                        @"transactions-short":@"allocate_transactions_26880"};
                    assert([error.userInfo[@"A23PreparationStage"] isEqual:stages[fault]]);
                    BOOL unopened = [@[@"real-blocked",@"token-missing",@"token-bool",@"retain-failed",@"pre-identity",@"float-identity",@"open-failed"] containsObject:fault];
                    assert(op.interface.destroys == (unopened ? 0 : 1));
                    if ([fault isEqual:@"real-blocked"]) assert(op.identities == 0 && op.opens == 0);
                    BOOL noReference = [@[@"real-blocked",@"token-missing",@"token-bool",@"retain-failed"] containsObject:fault];
                    assert(op.releases == (noReference ? 0 : 1));
                }
            });
        }
        dispatch_sync(q, ^{
            DetailedOpenFailure *op = [DetailedOpenFailure new]; op.simulation = YES; NSError *error = nil;
            assert(![provider(op,q) openCandidate:candidate() error:&error]);
            NSDictionary *details = A23PreparationErrorDetails(error);
            assert([details[@"domain"] isEqual:@"IOUSBHostErrorDomain"] && [details[@"code_u32"] unsignedIntValue]==(uint32_t)kIOReturnNotPermitted);
            assert([details[@"preparation_stage"] isEqual:@"sdk_init"] && [details[@"failure_reason"] isEqual:@"IOServiceOpen failed."]);
            assert(op.opens==1 && op.retains==1 && op.releases==1);
            NSString *longText = [@"🙂" stringByPaddingToLength:3000 withString:@"🙂" startingAtIndex:0];
            NSError *longError = [NSError errorWithDomain:@"mock" code:7 userInfo:@{NSLocalizedDescriptionKey:longText,NSLocalizedFailureReasonErrorKey:longText}];
            NSDictionary *bounded = A23PreparationErrorDetails(longError);
            assert([bounded[@"description"] dataUsingEncoding:NSUTF8StringEncoding].length<=384 &&
                   [bounded[@"failure_reason"] dataUsingEncoding:NSUTF8StringEncoding].length<=384);
            assert([NSJSONSerialization dataWithJSONObject:bounded options:0 error:NULL].length<4095);
        });
        NSData *before = [NSData dataWithContentsOfFile:[inputs stringByAppendingPathComponent:@"before.bin"]];
        NSData *after = [NSData dataWithContentsOfFile:[inputs stringByAppendingPathComponent:@"after.bin"]];
        assert(before.length == 168 && after.length == 168);
        NSArray *cases = @[@"clean",@"short-before",@"stale-before",@"short-after",@"error-after",@"overflow-after",
            @"native-error",@"late-after-close",@"missing-before",@"missing-after"];
        for (NSString *name in cases) {
            A23SimulationJournal *journal = [[A23SimulationJournal alloc] initWithPath:[root stringByAppendingPathComponent:[name stringByAppendingString:@".jsonl"]] error:NULL];
            assert(journal); A23SimulationSession *s = [[A23SimulationSession alloc] initWithQueue:q journal:journal requireStatusBinding:YES];
            AdapterOperations *op = operations(@"clean"); AdapterPipe *pipe = op.interface.pipe;
            dispatch_sync(q, ^{
                assert([s prepareCandidates:@[candidate()] provider:provider(op,q)]);
                assert(![s submitFirstFrame:100] && pipe.submissions == 0);
                if ([name isEqual:@"missing-before"]) { assert([s close]); return; }
                op.interface.reply = [name isEqual:@"short-before"] ? [before subdataWithRange:NSMakeRange(0,167)] :
                    [name isEqual:@"stale-before"] ? after : before;
                NSDictionary *reply = op.interface.readStatus;
                BOOL valid = [s recordStatusPhase:@"before" data:reply[@"data"] observation:reply[@"observation"]];
                assert((valid == ![@[@"short-before",@"stale-before"] containsObject:name]));
                if (!valid) { assert(![s submitFirstFrame:100] && pipe.submissions == 0 && [s close]); return; }
                assert(![s recordStatusPhase:@"before" data:reply[@"data"] observation:reply[@"observation"]]);
                assert([s submitFirstFrame:100]);
            });
            if (!pipe.submissions) continue;
            for (NSUInteger i = 0; i < 960; ++i) pipe.rows[i].status = kIOReturnUnderrun;
            for (NSUInteger n = 0; n < 16; ++n) {
                NSUInteger i = 522+n; uint16_t seq = (uint16_t)(1+n); uint8_t *p = (uint8_t *)pipe.data.mutableBytes+i*192;
                memcpy(p,"ISO1",4); p[4] = (uint8_t)seq; p[5] = (uint8_t)(seq>>8);
                for (NSUInteger j = 6; j < 192; ++j) p[j] = (uint8_t)(j^seq^(seq>>8));
                pipe.rows[i].status = 0; pipe.rows[i].completeCount = 192;
            }
            IOUSBHostIsochronousTransactionCompletionHandler callback = pipe.callback;
            IOUSBHostIsochronousTransaction *pointer = pipe.rows;
            if ([name isEqual:@"native-error"]) pipe.rows[522].status = kIOReturnError;
            callback([name isEqual:@"native-error"] ? kIOReturnError : 0,pointer); pipe.callback = nil;
            dispatch_sync(q, ^{
                assert((![s saveToParent:root name:name scenario:@{@"kind":@"single_burst",@"first_sequence":@1}]));
                if ([name isEqual:@"missing-after"]) { assert(![s close] && s.storageRetained && op.interface.destroys == 0); return; }
                op.interface.fault = name;
                op.interface.reply = [name isEqual:@"short-after"] ? [after subdataWithRange:NSMakeRange(0,167)] : after;
                NSDictionary *reply = op.interface.readStatus;
                BOOL valid = [s recordStatusPhase:@"after" data:reply[@"data"] observation:reply[@"observation"]];
                assert((valid == ![@[@"short-after",@"error-after",@"overflow-after"] containsObject:name]));
                assert(([s saveToParent:root name:name scenario:@{@"kind":@"single_burst",@"first_sequence":@1}]));
                pipe.data = nil;
                assert([s close] && !s.storageRetained && op.interface.destroys == 1);
            });
            if ([name isEqual:@"late-after-close"]) { callback(0,pointer); dispatch_sync(q, ^{ assert(s.stopped); }); }
        }
        NSString *noTD = [root stringByAppendingPathComponent:@"no-td"];
        assert([[NSFileManager defaultManager] createDirectoryAtPath:noTD withIntermediateDirectories:NO attributes:nil error:NULL]);
        assert(A23NoTDControlAllowed(0xc1,0x51,0,2,168));
        for (unsigned request = 0; request < 256; ++request)
            assert(A23NoTDControlAllowed(0xc1,(uint8_t)request,0,2,168) == (request == 0x51));
        assert(!A23NoTDControlAllowed(0x41,0x51,0,2,168) && !A23NoTDControlAllowed(0xc1,0x51,1,2,168) &&
               !A23NoTDControlAllowed(0xc1,0x51,0,3,168) && !A23NoTDControlAllowed(0xc1,0x51,0,2,167));
        NSArray *emptyCases = @[@"clean-underrun",@"mixed-status",@"all-zero",@"unknown-status",@"native-error",
            @"stray-raw",@"unexpected-data",@"invalid-row",@"late-after-close",@"timeout-accepted",@"timeout-rejected",
            @"detach-pending",@"missing-callback",@"missing-frame",@"bad-frame",@"wrong-frame",@"scenario-mismatch",@"missing-after"];
        for (NSString *name in emptyCases) {
            A23SimulationJournal *journal = [[A23SimulationJournal alloc] initWithPath:[noTD stringByAppendingPathComponent:[name stringByAppendingString:@".jsonl"]] error:NULL];
            assert(journal); A23SimulationSession *s = [[A23SimulationSession alloc] initNoTDWithQueue:q journal:journal];
            AdapterOperations *op = operations(@"clean"); AdapterPipe *pipe = op.interface.pipe;
            __block BOOL submitted = NO;
            dispatch_sync(q, ^{
                assert([s prepareCandidates:@[candidate()] provider:provider(op,q)]);
                assert(![s recordFrameSample:@{}] && ![s submitFirstFrame:100]);
                op.interface.reply = before; NSDictionary *reply = op.interface.readStatus;
                assert([s recordStatusPhase:@"before" data:reply[@"data"] observation:reply[@"observation"]]);
                assert(![s submitFirstFrame:100]);
                if ([name isEqual:@"missing-frame"]) { assert([s close] && pipe.submissions == 0); return; }
                uint64_t begin = mach_absolute_time(), end = mach_absolute_time();
                NSDictionary *sample = @{@"source":@"mock_frame_number",@"current_frame":([name isEqual:@"bad-frame"] ? @(UINT64_MAX) : @36),
                    @"begin_ticks":@(begin),@"end_ticks":@(end)};
                if ([name isEqual:@"bad-frame"]) {
                    assert(![s recordFrameSample:sample] && s.stopped && ![s submitFirstFrame:100]);
                    assert([s close] && pipe.submissions == 0); return;
                }
                assert([s recordFrameSample:sample] && s.plannedFirstFrame == 100);
                assert(![s recordFrameSample:sample]);
                if ([name isEqual:@"wrong-frame"]) {
                    assert(![s submitFirstFrame:101] && s.stopped && [s close] && pipe.submissions == 0); return;
                }
                submitted = [s submitFirstFrame:s.plannedFirstFrame]; assert(submitted && ![s submitFirstFrame:100]);
                assert(![s close] && op.retains == 1 && op.releases == 0);
                if ([name hasPrefix:@"timeout-"]) {
                    pipe.abortAllowed = [name isEqual:@"timeout-accepted"];
                    assert([s deadlineReached] == pipe.abortAllowed && ![s deadlineReached] && pipe.aborts == 1);
                    assert(s.storageRetained && s.resourcesRetained && ![s close]);
                }
                if ([name isEqual:@"detach-pending"]) {
                    assert([s detachedRegistryID:102] && ![s deadlineReached] && pipe.aborts == 0 && ![s close]);
                    assert(s.storageRetained && s.resourcesRetained);
                }
                if ([name isEqual:@"missing-callback"]) assert(![s close] && s.storageRetained && s.resourcesRetained);
            });
            if (!submitted || [name isEqual:@"missing-callback"]) continue;
            for (NSUInteger i = 0; i < 960; ++i) {
                pipe.rows[i].status = [name isEqual:@"all-zero"] ? 0 : [name isEqual:@"unknown-status"] ? 0xdeadbeef :
                    ([name isEqual:@"mixed-status"] && i < 271) ? 0xe000400e : kIOReturnUnderrun;
                pipe.rows[i].timeStamp = (IOUSBHostTime)i; // Original mock words; no bus-time inference.
            }
            if ([name isEqual:@"invalid-row"]) pipe.rows[0].status = kIOReturnInvalid;
            if ([name isEqual:@"stray-raw"]) ((uint8_t *)pipe.data.mutableBytes)[7] = 0xd1;
            if ([name isEqual:@"unexpected-data"]) pipe.rows[522].completeCount = 1;
            IOUSBHostIsochronousTransactionCompletionHandler callback = pipe.callback;
            IOUSBHostIsochronousTransaction *pointer = pipe.rows;
            callback([name isEqual:@"native-error"] ? kIOReturnError : 0,pointer); pipe.callback = nil;
            dispatch_sync(q, ^{
                if ([name isEqual:@"missing-after"]) { assert(![s close] && s.storageRetained && s.resourcesRetained); return; }
                NSMutableData *live = [before mutableCopy]; ((uint8_t *)live.mutableBytes)[56] = 0xd1;
                op.interface.reply = live; NSDictionary *reply = op.interface.readStatus;
                assert([s recordStatusPhase:@"after" data:reply[@"data"] observation:reply[@"observation"]]);
                if ([name isEqual:@"scenario-mismatch"]) {
                    assert((![s saveToParent:noTD name:name scenario:@{@"kind":@"single_burst",@"first_sequence":@1}]));
                    assert(s.stopped && s.storageRetained && ![s close]);
                }
                assert(([s saveToParent:noTD name:name scenario:@{@"kind":@"no_td"}]));
                pipe.data = nil;
                assert([s close] && !s.storageRetained && !s.resourcesRetained && op.interface.destroys == 1 && op.releases == 1);
                assert(pipe.aborts == ([name hasPrefix:@"timeout-"] ? 1 : 0));
            });
            if ([name isEqual:@"late-after-close"]) { callback(0,pointer); dispatch_sync(q, ^{ assert(s.stopped); }); }
        }
        puts("19 SDK adapter/reference, 10 STATUS/session, and 18 fixed no-TD observation scenarios passed. ASan/UBSan; real SDK/registry/USB calls: 0.");
        puts("Preparation stages, original SDK error identity/text, and bounded UTF-8 diagnostic fields verified.");
    }
    return 0;
}
