// Concatenated after reviewed resource/clock, paired fake and SDK fake prefixes.
// Only injected operations; real SDK operation classes are never instantiated.
@interface ThreeInterface : SDKModelInterface
@property NSMutableData *firstAfter;
@end
@implementation ThreeInterface
- (NSMutableData *)allocate:(NSUInteger)length shared:(BOOL)shared error:(NSError **)error {
    if(self.allocations==4 && [self.fault isEqual:@"alias-third-data"]){self.allocations++;return self.dataStores[0];}
    if(self.allocations==5 && [self.fault isEqual:@"alias-third-rows"]){self.allocations++;return self.transactionStores[1];}
    return [super allocate:length shared:shared error:error];
}
- (NSDictionary *)readStatus {
    NSUInteger ordinal=self.statusReads;
    if(ordinal==4 && [self.fault isEqual:@"third-before-first"])self.lastStatus=[self.firstAfter mutableCopy];
    // A query may independently change report_count within its accepted range.
    ((IsoProbeStatus *)self.lastStatus.mutableBytes)->report_count=ordinal ? ordinal%2 : 0;
    NSDictionary *reply=[super readStatus];if(ordinal==1)self.firstAfter=[reply[@"data"] mutableCopy];return reply;
}
- (void)deliver:(NSUInteger)n {
    [super deliver:n];IsoProbeStatus *s=self.lastStatus.mutableBytes;
    if([self.fault isEqual:[NSString stringWithFormat:@"fail-%lu",(unsigned long)n]])s->state=1;
    if(n==2 && ([self.fault isEqual:@"reuse-first"] || [self.fault isEqual:@"reuse-second"])){
        s->urb_id=[self.fault isEqual:@"reuse-first"] ? 501 : 502;s->report_id=s->urb_id;
    }
}
@end

int main(int argc,const char *argv[]) {
    @autoreleasepool {
        assert(argc==3);NSString *name=@(argv[1]),*directory=@(argv[2]);
        PairOperations *op=pairOperations(name,NO);ThreeInterface *r=[ThreeInterface new];r.fault=name;r.clock=[TwoClock new];op.interface=r;
        dispatch_queue_t q=dispatch_queue_create("a23.fixed-three.fixture",DISPATCH_QUEUE_SERIAL);
        __block A23ThreeEpochSDKDriver *driver=nil;__block id<A23TripleResources> lease;
        A23TripleSimulationProvider *provider=pairProvider(op,q,YES,^(uint32_t m){(void)m;[driver detachedRegistryID:102];});
        SDKModelJournal *journal=[SDKModelJournal new];journal.interface=r;journal.fault=name;
        journal.journal=[[A23SimulationJournal alloc] initWithPath:[directory stringByAppendingPathComponent:@"session.jsonl"] error:NULL];assert(journal.journal);
        dispatch_sync(q, ^{
            lease=[provider openCandidate:pairCandidate() error:NULL];
            if([name hasPrefix:@"alias-third-"]){assert(!lease && !r.submissions && !r.triggers);return;}
            assert(lease && lease.dataStores.count==3 && lease.transactionStores.count==3 && r.allocations==6);
            for(NSData *data in lease.dataStores)assert(pairZero(data));
            driver=[[A23ThreeEpochSDKDriver alloc] initWithResources:lease firstSequence:177 directory:directory queue:q clock:r.clock journal:journal error:NULL];assert(driver);
            if([name isEqual:@"third-save-collision"] || [name isEqual:@"third-status-collision"]){
                NSString *child=[name isEqual:@"third-save-collision"] ? @"epoch-2" : @"status-after-epoch-2";
                assert([[NSFileManager defaultManager] createDirectoryAtPath:[directory stringByAppendingPathComponent:child] withIntermediateDirectories:NO attributes:nil error:NULL]);
            }
            assert([driver start] && ![driver start]);
        });
        for(NSUInteger n=0;driver && n<3;++n){
            __block BOOL stopped;dispatch_sync(q,^{stopped=[driver.result[@"stopped"] boolValue];});if(stopped)break;
            if(n==2 && [name isEqual:@"third-timeout"]){
                [r.clock advanceNS:17000000];dispatch_sync(q,^{[driver poll];});break;
            }
            [r deliver:n];dispatch_sync(q,^{[driver poll];});
            if(n<2)dispatch_sync(q,^{
                if(n==1 && [name isEqual:@"late-first"])[r oldISO];
                if(n==1 && [name isEqual:@"late-second"]){IOUSBHostCompletionHandler cb=r.controlCallbacks[1];cb(0,0);}
                if(n==1 && [name isEqual:@"third-storage-change"])lease.dataStores[2].length--;
                if(n==1 && [name isEqual:@"detach-before-third"])[driver detachedRegistryID:102];
                [driver poll];
            });
        }
        __block NSDictionary *result,*receipt;
        dispatch_sync(q,^{
            if(driver){
                [r.clock advanceNS:250000001];[driver poll];
                if([name isEqual:@"fourth-status"])[lease readStatus];
                if([name isEqual:@"fourth-submit"])[lease.transport enqueueIORequestWithData:lease.dataStores[0] transactionList:lease.transactionStores[0].mutableBytes transactionListCount:960 firstFrameNumber:228 options:0 error:NULL completionHandler:^(IOReturn s,IOUSBHostIsochronousTransaction *p){(void)s;(void)p;}];
                if([name isEqual:@"old-after-third"])[r oldISO];
                [driver poll];[driver saveReceiptOnce];result=driver.result;receipt=driver.receiptStatus;
                BOOL normal=[name isEqual:@"normal"];
                assert([result[@"complete"] boolValue]==normal);
                if(normal)assert([receipt[@"saved"] boolValue] && [result[@"saved_epochs"] unsignedIntegerValue]==3);
                else assert([result[@"stopped"] boolValue]);
                assert(![lease closeUnused] && !r.destroys && op.liveReferences==1);
                for(NSString *n in @[@"result.json",@"receipt-status.json"]){
                    NSData *raw=[NSJSONSerialization dataWithJSONObject:[n isEqual:@"result.json"] ? result : receipt options:NSJSONWritingSortedKeys error:NULL];
                    assert([raw writeToFile:[directory stringByAppendingPathComponent:n] options:NSDataWritingWithoutOverwriting error:NULL]);
                }
            }
        });
        assert(r.submissions<=3 && r.triggers<=3 && r.aborts<=1);
        NSDictionary *row=@{@"case":name,@"init_rejected":@((BOOL)(driver==nil)),@"result":result?:@{},@"receipt":receipt?:@{},@"iso_submissions":@(r.submissions),@"burst_triggers":@(r.triggers),@"destroys":@(r.destroys),@"aborts":@(r.aborts),@"real_sdk_objects":@0,@"usb_requests":@0};
        NSData *raw=[NSJSONSerialization dataWithJSONObject:row options:NSJSONWritingSortedKeys error:NULL];fwrite(raw.bytes,1,raw.length,stdout);puts("");
    }return 0;
}
