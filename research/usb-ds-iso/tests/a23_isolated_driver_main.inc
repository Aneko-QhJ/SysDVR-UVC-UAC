// Model-only faults at documented event boundaries; no production entry point.
@interface ReplayJournal : SDKModelJournal
@end
@implementation ReplayJournal
- (BOOL)append:(NSDictionary *)row error:(NSError **)error {
    BOOL ok=[super append:row error:error];
    if(ok && [row[@"event"] isEqual:@"epochs_saved"] && [self.fault isEqual:@"zero-start"])self.interface.clock.zeroNext=YES;
    if(ok && [row[@"event"] isEqual:@"observation_complete"] && [self.fault isEqual:@"postguard-failure"])[self.interface oldISO];
    return ok;
}
@end
static void modelJSON(NSString *directory,NSString *name,id value){
    NSData *raw=[NSJSONSerialization dataWithJSONObject:value options:NSJSONWritingSortedKeys error:NULL];
    assert(raw && [raw writeToFile:[directory stringByAppendingPathComponent:name] options:NSDataWritingWithoutOverwriting error:NULL]);
}
int main(int argc,const char *argv[]) {
    @autoreleasepool {
        if(argc!=2)return 2;
        NSString *root=@(argv[1]);assert(root.isAbsolutePath);
        NSArray *names=@[@"normal",@"fractional-short",@"fractional-short-equal",@"fractional-after",@"unlabeled",@"owner-role",@"zero-instance",@"zero-start",@"ratio-change",@"instance-change",@"domain-change",@"backwards",@"overflow",@"object-replaced",@"quiet-journal-failure",@"postguard-failure",@"late-after-settled",@"late-after-receipt",@"incomplete"];
        NSMutableDictionary *out=[NSMutableDictionary new];
        for(NSString *name in names){
            NSString *directory=[root stringByAppendingPathComponent:name];assert([[NSFileManager defaultManager] createDirectoryAtPath:directory withIntermediateDirectories:NO attributes:nil error:NULL]);
            PairOperations *op=pairOperations(name,NO);SDKModelInterface *r=[SDKModelInterface new];r.fault=name;r.clock=[TwoClock new];op.interface=r;
            TwoClock *clock=r.clock;PlainModelClock *plain=[PlainModelClock new];
            if([name hasPrefix:@"fractional-"]){clock.n=2;clock.d=3;}
            if([name isEqual:@"owner-role"])clock.role=2;
            if([name isEqual:@"zero-instance"])clock.instance=0;
            if([name isEqual:@"overflow"]){clock.n=UINT32_MAX;clock.step=0;}
            NSDictionary *initial=@{@"domain":@(clock.role),@"instance":@(clock.instance),@"numerator":@(clock.n),@"denominator":@(clock.d),@"injected":@YES};
            dispatch_queue_t q=dispatch_queue_create("a23.isolated.numeric.model",DISPATCH_QUEUE_SERIAL);
            __block A23TwoEpochSDKDriver *driver=nil;
            A23PairedSimulationProvider *provider=pairProvider(op,q,YES,^(uint32_t m){(void)m;[driver detachedRegistryID:102];});
            ReplayJournal *journal=[ReplayJournal new];journal.interface=r;journal.fault=name;
            journal.journal=[[A23SimulationJournal alloc] initWithPath:[directory stringByAppendingPathComponent:@"session.jsonl"] error:NULL];assert(journal.journal);
            __block id<A23PairedResources> lease;
            dispatch_sync(q,^{
                lease=[provider openCandidate:pairCandidate() error:NULL];assert(lease && op.liveReferences==1);
                for(NSData *data in lease.dataStores)assert(pairZero(data));
                id<A23RuntimeClock> supplied=[name isEqual:@"unlabeled"] ? (id<A23RuntimeClock>)plain : clock;
                driver=[[A23TwoEpochSDKDriver alloc] initWithResources:lease firstSequence:81 directory:directory queue:q clock:supplied journal:journal error:NULL];
                if(driver){assert([driver start]);assert(![driver start]);}
            });
            if(!driver){
                assert(([@[@"unlabeled",@"owner-role",@"zero-instance"] containsObject:name]));
                assert(!r.submissions && !r.triggers && !clock.reads && !plain.reads);
                dispatch_sync(q,^{out[name]=@{@"init_rejected":@YES,@"clock_reads":@0,@"lease":lease.result};});
                modelJSON(directory,@"model.json",out[name]);continue;
            }
            for(NSUInteger n=0;n<2;++n){[r deliver:n];dispatch_sync(q,^{[driver poll];});if(n==0)dispatch_sync(q,^{[driver poll];});}
            __block uint64_t start;dispatch_sync(q,^{start=[driver.result[@"quiet_start_ticks"] unsignedLongLongValue];});
            clock.step=0;uint64_t delta=clock.d==3 ? 375000000 : 250000000;
            if([name isEqual:@"fractional-short"] || [name isEqual:@"fractional-short-equal"])--delta;
            if([name isEqual:@"fractional-after"])++delta;
            if([name isEqual:@"incomplete"])--delta;
            uint64_t end=start+delta;
            if([name isEqual:@"ratio-change"])clock.n=2;
            if([name isEqual:@"instance-change"])clock.instance=2;
            if([name isEqual:@"domain-change"])clock.role=2;
            if([name isEqual:@"backwards"])end=start-1;
            if([name isEqual:@"overflow"])end=UINT64_MAX;
            [clock setTicks:end];
            if([name isEqual:@"object-replaced"]){
                TwoClock *other=[TwoClock new];other.step=0;[other setTicks:end];
                // Explicit model fault: replace private driver ivar, same labels.
                dispatch_sync(q,^{[driver setValue:other forKey:@"clock"];});
            }
            __block NSDictionary *firstPoll;dispatch_sync(q,^{[driver poll];firstPoll=driver.result;});
            if([name isEqual:@"fractional-short-equal"]){++end;[clock setTicks:end];dispatch_sync(q,^{[driver poll];});}
            if([name isEqual:@"late-after-settled"]){[r oldISO];dispatch_sync(q,^{[driver poll];});}
            dispatch_sync(q,^{[driver saveReceiptOnce];});
            if([name isEqual:@"late-after-receipt"]){[r oldISO];dispatch_sync(q,^{[driver poll];});}
            dispatch_sync(q,^{
                NSDictionary *result=driver.result,*receipt=driver.receiptStatus;
                assert(![driver saveReceiptOnce] && ![lease closeUnused] && !r.destroys && op.liveReferences==1 && r.submissions==2 && r.triggers==2 && !r.aborts);
                modelJSON(directory,@"result.json",result);modelJSON(directory,@"receipt-status.json",receipt);
                NSDictionary *profile=@{@"schema":@"A23-isolated-quiet-profile-1",@"initial":initial,@"end":@{@"domain":@(clock.role),@"instance":@(clock.instance),@"numerator":@(clock.n),@"denominator":@(clock.d)},@"quiet_start_ticks":@(start),@"test_end_ticks":@(end),@"object_replaced":@([name isEqual:@"object-replaced"]),@"profile_reads_atomic":@NO,@"actual_clock_authenticated":@NO};
                modelJSON(directory,@"clock-profile.json",profile);
                out[name]=@{@"result":result,@"receipt_status":receipt,@"first_poll":firstPoll,@"profile":profile,@"live_references":@(op.liveReferences),@"destroys":@(r.destroys)};
            });
        }
        NSDictionary *summary=@{@"case_count":@(names.count),@"cases":out,@"real_sdk_objects":@0,@"usb_requests":@0,@"sd_accesses":@0,@"actual_sdk_mapping_tested":@NO};
        NSData *raw=[NSJSONSerialization dataWithJSONObject:summary options:NSJSONWritingSortedKeys error:NULL];assert(raw);fwrite(raw.bytes,1,raw.length,stdout);puts("");
    }return 0;
}
