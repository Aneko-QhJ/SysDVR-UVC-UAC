"""Add deterministic threaded model schedules without changing driver/bridge/C."""
import a23_versioned_driver_model as old_model
f=old_model.f
BASE,DRIVER=old_model.BASE,old_model.DRIVER
protected,diff=old_model.protected,old_model.diff
CASES=('gate-publish','gate-aba','gate-noop','gate-two-publishers','gate-iso-before-write','gate-write-before-iso',
       'gate-control-before-write','gate-write-before-control','gate-journal-failure','after-release-aba',
       'after-receipt-aba','after-receipt-noop','capture-return-aba')


def once(text,old,new):
    f.require(text.count(old)==1,'concurrency fixture anchor differs');return text.replace(old,new,1)


def render(source):
    out=old_model.render(source);key=BASE+'tests/model_main.m';text=out[key].decode()
    helper=(source/BASE/'tests/a23_commit_concurrency_fixture.inc').read_text()
    text=once(text,'@interface FaultClock : TwoClock',helper+'\n@interface FaultClock : TwoClock')
    text=once(text,'@property BOOL afterCaptureABA;','@property BOOL afterCaptureABA;\n@property NSString *concurrencyCase;\n@property NSDictionary *concurrencyTrace;')
    text=once(text,'    if(_afterCaptureABA && status==A23VersionedClockOK)',
        '    if(_concurrencyCase && status==A23VersionedClockOK){NSString *name=_concurrencyCase;_concurrencyCase=nil;++_mutations;_concurrencyTrace=runCommitThreads(self,nil,name);}\n    if(_afterCaptureABA && status==A23VersionedClockOK)')
    extra='''@interface ConcurrentJournal : VersionJournal
@property NSDictionary *trace;
@end
@implementation ConcurrentJournal
- (BOOL)append:(NSDictionary *)row error:(NSError **)error {
    if([row[@"event"] isEqual:@"observation_complete"] && [self.fault hasPrefix:@"gate-"]){
        _trace=runCommitThreads(self.interface.clock,(id<ConcurrentCallbacks>)self.interface,self.fault);
        if([self.fault isEqual:@"gate-journal-failure"])return NO;
    }return [super append:row error:error];
}
@end
'''
    text=once(text,'static void bridgeChecks(void)',extra+'\nstatic void bridgeChecks(void)')
    names='\n        [names addObjectsFromArray:@['+','.join('@"'+name+'"' for name in CASES)+']];'
    text=once(text,'        NSMutableDictionary *out=[NSMutableDictionary new];',names+'\n        NSMutableDictionary *out=[NSMutableDictionary new];')
    text=once(text,'VersionJournal *journal=[VersionJournal new];','ConcurrentJournal *journal=[ConcurrentJournal new];')
    text=once(text,'            __block BOOL shortObserved=NO,shortComplete=NO;',
        '            if(quietEligible && [name isEqual:@"capture-return-aba"])clock.concurrencyCase=name;\n            __block BOOL shortObserved=NO,shortComplete=NO;')
    text=once(text,'            if([name isEqual:@"post-receipt-aba"]){',
        '''            if([name isEqual:@"after-release-aba"]){journal.trace=runCommitThreads(clock,nil,name);dispatch_sync(q,^{[driver poll];});}
            if([name hasPrefix:@"after-receipt-"]){dispatch_sync(q,^{[driver poll];[driver saveReceiptOnce];});journal.trace=runCommitThreads(clock,nil,name);dispatch_sync(q,^{[driver poll];});}
            if([name isEqual:@"post-receipt-aba"]){''')
    text=once(text,'                out[name]=row;',
        '''                NSDictionary *trace=journal.trace ?: clock.concurrencyTrace;
                if(trace){faultJSON(directory,@"concurrency.json",trace);row[@"concurrency"]=trace;}
                out[name]=row;''')
    for token in ('mach_absolute_time','mach_timebase_info','initWithIOService:','A23ReadExecutionContext'):
        f.require(token not in text,'concurrency fixture crosses scope')
    out[key]=text.encode();return out
