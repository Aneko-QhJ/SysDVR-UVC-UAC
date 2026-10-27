"""Integrate specified worker failures through fixture hooks; driver unchanged."""
import a23_commit_concurrency_model as old_model
f=old_model.f
BASE,DRIVER=old_model.BASE,old_model.DRIVER
protected,diff=old_model.protected,old_model.diff
CASES=('capture-worker-error','capture-worker-exit','capture-worker-unfinished-return','capture-worker-unfinished-exit',
       'capture-worker-invalid-finish','capture-worker-wrong-ticket','capture-worker-exhausted',
       'capture-return-worker-unfinished','capture-return-worker-exhausted','gate-worker-busy-error','gate-worker-object-replace',
       'after-release-worker-unfinished','after-receipt-worker-unfinished','after-release-worker-exhausted','after-receipt-worker-exhausted')
once=old_model.once


def render(source):
    out=old_model.render(source);key=BASE+'tests/model_main.m';text=out[key].decode()
    text=once(text,'@interface FaultClock : TwoClock',(source/BASE/'tests/a23_driver_worker_failure_fixture.inc').read_text()+'\n@interface FaultClock : TwoClock')
    text=once(text,'@property BOOL afterCaptureABA;','''@property BOOL afterCaptureABA;
@property A23VersionedClockStore *workerStore;
@property NSString *workerFailureCase;
@property NSDictionary *workerFailureTrace;''')
    text=once(text,'    A23VersionedClockStatus status=[super versionedCapture:out];','''    NSString *workerCase=_workerFailureCase;_workerFailureCase=nil;
    BOOL before=workerCase && ![workerCase hasPrefix:@"capture-return-"];
    NSMutableDictionary *workerTrace=before ? runDriverFailureWorker(_workerStore,workerCase) : nil;
    A23VersionedClockStatus status=[super versionedCapture:out];
    if(workerCase && !before)workerTrace=runDriverFailureWorker(_workerStore,workerCase);
    if(workerTrace){
        workerTrace[@"capture_status"]=@(status);
        BOOL zero=out && !out->stamp.ticks && !out->stamp.domain && !out->stamp.clock_instance && !out->stamp.numerator && !out->stamp.denominator && !out->store_identity && !out->incarnation && !out->generation;
        workerTrace[@"capture_output_zeroed"]=@(zero);_workerFailureTrace=workerTrace;
    }''')
    text=once(text,'@interface ConcurrentJournal : VersionJournal\n@property NSDictionary *trace;','@interface ConcurrentJournal : VersionJournal\n@property NSDictionary *trace;\n@property NSDictionary *workerTrace;')
    text=once(text,'    if([row[@"event"] isEqual:@"observation_complete"] && [self.fault hasPrefix:@"gate-"]){',
        '''    if([row[@"event"] isEqual:@"observation_complete"] && [self.fault hasPrefix:@"gate-worker-"]){
        FaultClock *clock=(FaultClock *)self.interface.clock;_workerTrace=runDriverFailureWorker(clock.workerStore,self.fault);
        if([self.fault isEqual:@"gate-worker-object-replace"]){FaultClock *other=[FaultClock new];other.step=0;[self.driver setValue:other forKey:@"clock"];}
    }
    if([row[@"event"] isEqual:@"observation_complete"] && [self.fault hasPrefix:@"gate-"] && ![self.fault hasPrefix:@"gate-worker-"]){''')
    names='        [names addObjectsFromArray:@['+','.join('@"'+n+'"' for n in CASES)+']];\n'
    text=once(text,'        NSMutableDictionary *out=[NSMutableDictionary new];',names+'        NSMutableDictionary *out=[NSMutableDictionary new];')
    text=once(text,'            FaultClock *clock=[FaultClock new];clock.step=0;','''            FaultClock *clock=[FaultClock new];clock.step=0;
            A23VersionedClockSample workerProfile;assert([clock versionedProfile:&workerProfile]==A23VersionedClockOK);clock.workerStore=(A23VersionedClockStore *)workerProfile.store_identity;''')
    text=once(text,'            __block BOOL shortObserved=NO,shortComplete=NO;','''            if(quietEligible && [name hasPrefix:@"capture-"] && [name containsString:@"worker-"])clock.workerFailureCase=name;
            __block BOOL shortObserved=NO,shortComplete=NO;''')
    text=once(text,'            if([name isEqual:@"after-release-aba"]){', '''            if([name hasPrefix:@"after-release-worker-"] || [name hasPrefix:@"after-receipt-worker-"]){
                if([name hasPrefix:@"after-receipt-"])dispatch_sync(q,^{[driver saveReceiptOnce];});
                clock.workerFailureTrace=runDriverFailureWorker(clock.workerStore,name);dispatch_sync(q,^{[driver poll];});
            }
            if([name isEqual:@"after-release-aba"]){''')
    text=once(text,'            if([name hasPrefix:@"after-receipt-"]){','            if([name hasPrefix:@"after-receipt-"] && ![name hasPrefix:@"after-receipt-worker-"]){')
    text=once(text,'                out[name]=row;', '''                NSDictionary *workerTrace=journal.workerTrace ?: clock.workerFailureTrace;
                if(workerTrace){faultJSON(directory,@"worker-failure.json",workerTrace);row[@"worker_failure"]=workerTrace;}
                out[name]=row;''')
    out[key]=text.encode();return out
