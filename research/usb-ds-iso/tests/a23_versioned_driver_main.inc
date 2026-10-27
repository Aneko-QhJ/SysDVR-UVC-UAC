// Derived from the pinned fault fixture; only isolated model code.
// Model-only callback/deadline/profile fault entry. No production launcher.
@interface FaultInterface : SDKModelInterface
- (void)prepare:(NSUInteger)n;
- (void)control:(NSUInteger)n status:(IOReturn)status bytes:(NSUInteger)bytes;
- (void)iso:(NSUInteger)n status:(IOReturn)status foreign:(BOOL)foreign;
@end
@implementation FaultInterface
- (void)prepare:(NSUInteger)n {
    id control=self.controlCallbacks[n],iso=self.isoCallbacks[n];
    self.controlCallbacks[n]=[^(IOReturn s,NSUInteger b){(void)s;(void)b;} copy];
    self.isoCallbacks[n]=[^(IOReturn s,IOUSBHostIsochronousTransaction *p){(void)s;(void)p;} copy];
    [super deliver:n]; // Fill complete model payload/STATUS without real ingress.
    self.controlCallbacks[n]=control;self.isoCallbacks[n]=iso;
}
- (void)control:(NSUInteger)n status:(IOReturn)status bytes:(NSUInteger)bytes {
    IOUSBHostCompletionHandler cb=self.controlCallbacks[n];cb(status,bytes);
}
- (void)iso:(NSUInteger)n status:(IOReturn)status foreign:(BOOL)foreign {
    IOUSBHostIsochronousTransactionCompletionHandler cb=self.isoCallbacks[n];
    cb(status,foreign ? (void *)1 : self.transactionStores[n].mutableBytes);
}
@end
@interface FaultJournal : SDKModelJournal
@property NSString *captureStage;
@end
@implementation FaultJournal
- (BOOL)append:(NSDictionary *)row error:(NSError **)error {
    BOOL ok=[super append:row error:error];
    if(ok && [_captureStage isEqual:@"start"] && [row[@"event"] isEqual:@"epochs_saved"]){
        FaultClock *clock=(FaultClock *)self.interface.clock;clock.onRead=clock.reads+1;
    }return ok;
}
@end
@interface VersionJournal : FaultJournal
@property uint64_t appendGeneration;
@property(weak) A23TwoEpochSDKDriver *driver;
@end
@implementation VersionJournal
- (BOOL)append:(NSDictionary *)row error:(NSError **)error {
    if([row[@"event"] isEqual:@"observation_complete"] && [self.fault isEqual:@"append-journal-failure"])return NO;
    BOOL ok=[super append:row error:error];
    FaultClock *clock=(FaultClock *)self.interface.clock;
    if(ok && [row[@"event"] isEqual:@"epochs_saved"] && [self.fault isEqual:@"zero-quiet-start"])clock.zeroNext=YES;
    if(ok && [row[@"event"] isEqual:@"observation_complete"]){
        _appendGeneration=clock.profileGeneration;
        if([self.fault isEqual:@"append-aba-attempt"]){clock.n=2;clock.n=1;}
        if([self.fault isEqual:@"append-visible-attempt"])clock.n=2;
        if([self.fault isEqual:@"append-callback"])[self.interface oldISO];
        if([self.fault isEqual:@"append-object-replaced"]){FaultClock *other=[FaultClock new];other.step=0;[_driver setValue:other forKey:@"clock"];}
    }return ok;
}
@end
static void bridgeChecks(void){
    A23VersionedDriverSample sample;
    assert(!A23VersionedDriverReadProfile([NSObject new],&sample) && !sample.object_identity && !sample.version.store_identity);
    assert(!A23VersionedDriverCapture(nil,&sample) && !sample.object_identity);
    assert(!A23VersionedDriverReadProfile(nil,NULL));
    A23CandidateClockResult result;
    assert(A23VersionedDriverEvaluate(NULL,NULL,0,&result)==A23CandidateClockInvalidArgument && !result.minimum_met);
    uint64_t generation=99;assert(!A23VersionedDriverEndCommit(nil,&generation) && !generation);
    A23CandidateClockStamp p={0,A23CandidateInjectedDriver,1,1,1};
    __weak A23VersionedDriverClockAdapter *weak;
    @autoreleasepool {
        A23VersionedDriverClockAdapter *owner=[[A23VersionedDriverClockAdapter alloc] initWithProfile:p incarnation:1];weak=owner;
        assert(A23VersionedDriverReadProfile(owner,&sample));
        assert(!A23VersionedDriverCapture(owner,&sample) && !sample.object_identity); // Base adapter has no raw reader.
        assert(!A23VersionedDriverEndCommit(owner,&generation));
    }
    assert(!weak);p.numerator=0;assert(![[A23VersionedDriverClockAdapter alloc] initWithProfile:p incarnation:1]);
}

static void faultJSON(NSString *directory,NSString *name,id value){
    NSData *raw=[NSJSONSerialization dataWithJSONObject:value options:NSJSONWritingSortedKeys error:NULL];
    assert(raw && [raw writeToFile:[directory stringByAppendingPathComponent:name] options:NSDataWritingWithoutOverwriting error:NULL]);
}
int main(int argc,const char *argv[]){
    @autoreleasepool {
        if(argc!=2)return 2;bridgeChecks();NSString *root=@(argv[1]);assert(root.isAbsolutePath);
        NSMutableArray *names=[NSMutableArray new];
        for(NSString *target in @[@"control",@"iso"])for(NSString *mode in @[@"arrival",@"poll"])for(NSString *ratio in @[@"1to1",@"2to3"])for(NSString *edge in @[@"before",@"equal",@"after"])
            [names addObject:[@[target,mode,ratio,edge] componentsJoinedByString:@"-"]];
        for(NSString *stage in @[@"start",@"end"])for(NSString *field in @[@"numerator",@"denominator",@"domain",@"instance",@"aba"])
            [names addObject:[NSString stringWithFormat:@"profile-%@-%@",stage,field]];
        [names addObjectsFromArray:@[@"duplicate-iso",@"duplicate-control",@"foreign-pointer",@"control-error",@"control-bytes",@"iso-error",@"callback-queued-delay",@"old-control-between-epochs",@"early-iso",@"iso-reject",@"trigger-reject",@"iso-abort-late"]];
        [names addObjectsFromArray:@[@"normal",@"between-captures-aba",@"after-capture-aba",@"append-aba-attempt",@"append-visible-attempt",@"append-callback",@"append-journal-failure",@"post-receipt-aba",@"object-replaced",@"zero-quiet-start",@"fractional-short-equal",@"profile-end-bypass",@"append-object-replaced"]];
        NSMutableDictionary *out=[NSMutableDictionary new];
        for(NSString *name in names){
            NSString *directory=[root stringByAppendingPathComponent:name];assert([[NSFileManager defaultManager] createDirectoryAtPath:directory withIntermediateDirectories:NO attributes:nil error:NULL]);
            NSArray *parts=[name componentsSeparatedByString:@"-"];BOOL deadline=parts.count==4 && ([(NSString *)parts[1] isEqual:@"arrival"] || [(NSString *)parts[1] isEqual:@"poll"]);
            BOOL profile=[name hasPrefix:@"profile-"];
            FaultClock *clock=[FaultClock new];clock.step=0;
            if((deadline && [parts[2] isEqual:@"2to3"]) || [name isEqual:@"fractional-short-equal"]){clock.n=2;clock.d=3;}
            if(profile)clock.mutation=parts[2];
            PairOperations *op=pairOperations(name,NO);FaultInterface *r=[FaultInterface new];r.clock=clock;r.fault=name;op.interface=r;
            dispatch_queue_t q=dispatch_queue_create("a23.isolated.fault.model",DISPATCH_QUEUE_SERIAL);__block A23TwoEpochSDKDriver *driver=nil;
            A23PairedSimulationProvider *provider=pairProvider(op,q,YES,^(uint32_t m){(void)m;[driver detachedRegistryID:102];});
            VersionJournal *journal=[VersionJournal new];journal.interface=r;journal.fault=name;
            if(profile)journal.captureStage=parts[1];
            journal.journal=[[A23SimulationJournal alloc] initWithPath:[directory stringByAppendingPathComponent:@"session.jsonl"] error:NULL];assert(journal.journal);
            uint64_t constructorGeneration=clock.profileGeneration;uint32_t initialN=clock.n,initialD=clock.d;
            __block id<A23PairedResources> lease;__block BOOL startAccepted;
            dispatch_sync(q,^{lease=[provider openCandidate:pairCandidate() error:NULL];assert(lease);for(NSData *data in lease.dataStores)assert(pairZero(data));driver=[[A23TwoEpochSDKDriver alloc] initWithResources:lease firstSequence:81 directory:directory queue:q clock:clock journal:journal error:NULL];assert(driver);journal.driver=driver;startAccepted=[driver start];assert(![driver start]);});
            uint64_t targetEnd=100;__block NSDictionary *edgeState=nil,*afterLate=nil;
            if(deadline || [name isEqual:@"iso-abort-late"]){
                BOOL iso=[parts[0] isEqual:@"iso"],poll=deadline ? [parts[1] isEqual:@"poll"] : YES;
                uint64_t limit=iso ? 2000000000 : 16000000;
                uint64_t ticks=(uint64_t)(((__uint128_t)limit*clock.d)/clock.n);
                if(deadline && [parts[3] isEqual:@"before"])--ticks;
                if(deadline && [parts[3] isEqual:@"after"])++ticks;
                [r prepare:0];
                if(iso)[r control:0 status:0 bytes:0];else [r iso:0 status:0 foreign:NO];
                dispatch_sync(q,^{});targetEnd=100+ticks;[clock setTicks:targetEnd];
                if(!poll){if(iso)[r iso:0 status:0 foreign:NO];else [r control:0 status:0 bytes:0];}
                dispatch_sync(q,^{[driver poll];edgeState=driver.result;});
                if(poll && ![edgeState[@"stopped"] boolValue]){
                    if(iso)[r iso:0 status:0 foreign:NO];else [r control:0 status:0 bytes:0];
                    dispatch_sync(q,^{[driver poll];});
                }
                if([name isEqual:@"iso-abort-late"]){
                    [clock setTicks:targetEnd+1];[r iso:0 status:0 foreign:NO];
                    dispatch_sync(q,^{[driver poll];afterLate=driver.result;});
                }
            }else if(startAccepted){
                if([name isEqual:@"callback-queued-delay"]){
                    dispatch_sync(q,^{[r deliver:0];[clock setTicks:25000100];});targetEnd=25000100;
                }else [r deliver:0];
                dispatch_sync(q,^{[driver poll];edgeState=driver.result;});
                if([name isEqual:@"old-control-between-epochs"]){[r oldControl];dispatch_sync(q,^{[driver poll];});}
            }else dispatch_sync(q,^{[driver poll];edgeState=driver.result;});
            __block BOOL continueEpoch;dispatch_sync(q,^{continueEpoch=![driver.result[@"stopped"] boolValue] && [driver.result[@"saved_epochs"] unsignedIntegerValue]==1;});
            if(continueEpoch){dispatch_sync(q,^{[driver poll];});[r deliver:1];dispatch_sync(q,^{[driver poll];});}
            __block uint64_t quietStart;__block BOOL quietEligible;
            dispatch_sync(q,^{NSDictionary *state=driver.result;quietStart=[state[@"quiet_start_ticks"] unsignedLongLongValue];quietEligible=![state[@"stopped"] boolValue] && [state[@"saved_epochs"] unsignedIntegerValue]==2;});
            if(quietEligible && [name isEqual:@"between-captures-aba"]){clock.n=2;clock.n=1;}
            if(quietEligible && [name isEqual:@"after-capture-aba"])clock.afterCaptureABA=YES;
            if(quietEligible && [name isEqual:@"object-replaced"]){
                FaultClock *other=[FaultClock new];other.step=0;
                dispatch_sync(q,^{[driver setValue:other forKey:@"clock"];});
            }
            __block BOOL shortObserved=NO,shortComplete=NO;
            uint64_t quietTestEnd=0;
            if(quietEligible){
                if(profile && [parts[1] isEqual:@"end"])clock.onRead=clock.reads+1;
                quietTestEnd=quietStart+(uint64_t)(((__uint128_t)250000000*clock.d+clock.n-1)/clock.n);
                if([name isEqual:@"fractional-short-equal"]){
                    [clock setTicks:quietTestEnd-1];dispatch_sync(q,^{[driver poll];shortObserved=YES;shortComplete=[driver.result[@"complete"] boolValue];});
                }
                [clock setTicks:quietTestEnd];
                dispatch_sync(q,^{[driver poll];});
            }
            if([name isEqual:@"post-receipt-aba"]){
                dispatch_sync(q,^{[driver poll];[driver saveReceiptOnce];});clock.n=2;clock.n=1;dispatch_sync(q,^{[driver poll];});
            }
            dispatch_sync(q,^{
                [driver poll];[driver saveReceiptOnce];NSDictionary *state=driver.result,*receipt=driver.receiptStatus;
                NSArray *owners=[driver valueForKey:@"owners"];NSMutableArray *ownerStates=[NSMutableArray new];
                for(A23TransactionOwner *owner in owners)[ownerStates addObject:@{@"state":@(owner.state),@"callbacks":@(owner.callbackCount),@"retained":@(owner.storageRetained),@"timed_out":@(owner.timedOut)}];
                assert(![driver saveReceiptOnce] && ![driver start] && ![lease closeUnused] && r.submissions<=2 && r.triggers<=2 && r.aborts<=1 && !r.destroys && op.liveReferences==1);
                NSDictionary *facts=@{@"schema":@"A23-injected-driver-fault-facts-1",@"case":name,@"start_accepted":@(startAccepted),@"initial_ticks":@100,@"target_end_ticks":@(targetEnd),@"initial_numerator":@(initialN),@"initial_denominator":@(initialD),@"end_numerator":@(clock.n),@"end_denominator":@(clock.d),@"end_domain":@(clock.role),@"end_instance":@(clock.instance),@"mutations":@(clock.mutations),@"quiet_start_ticks":@(quietStart),@"quiet_test_end_ticks":@(quietTestEnd),@"injected_fixture":@YES,@"profile_reads_atomic":@NO,@"actual_clock_authenticated":@NO,@"owners":ownerStates};
                NSDictionary *version=@{@"schema":@"A23-versioned-driver-profile-1",@"constructor_generation":@(constructorGeneration),
                    @"start_generation":[driver valueForKey:@"quietVersionStart"],@"end_generation":[driver valueForKey:@"quietVersionEnd"],
                    @"released_generation":[driver valueForKey:@"quietVersionReleased"],@"expected_generation":[driver valueForKey:@"quietVersionLive"],
                    @"current_generation":@(clock.profileGeneration),@"write_attempts":@(clock.writeAttempts),@"write_successes":@(clock.writeSuccesses),
                    @"busy_writes":@(clock.busyWrites),@"last_write_status":@(clock.lastWriteStatus),@"append_generation":@(journal.appendGeneration),
                    @"object_bound":@((BOOL)([driver valueForKey:@"versionedClockOwner"]==clock)),@"short_poll_observed":@(shortObserved),@"short_poll_complete":@(shortComplete),
                    @"contract_enforced":@NO,@"actual_clock_authenticated":@NO};
                faultJSON(directory,@"version-profile.json",version);
                faultJSON(directory,@"result.json",state);faultJSON(directory,@"receipt-status.json",receipt);faultJSON(directory,@"fault-facts.json",facts);
                NSMutableDictionary *row=[@{@"result":state,@"receipt_status":receipt,@"facts":facts,@"version":version} mutableCopy];if(edgeState)row[@"edge_state"]=edgeState;if(afterLate)row[@"after_late"]=afterLate;
                out[name]=row;
            });
        }
        NSData *raw=[NSJSONSerialization dataWithJSONObject:@{@"bridge_checks_passed":@YES,@"case_count":@(names.count),@"cases":out,@"real_sdk_objects":@0,@"usb_requests":@0,@"sd_accesses":@0,@"actual_sdk_mapping_tested":@NO} options:NSJSONWritingSortedKeys error:NULL];assert(raw);fwrite(raw.bytes,1,raw.length,stdout);puts("");
    }return 0;
}
