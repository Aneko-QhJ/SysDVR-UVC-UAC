#import "a23_waiting_receiver.h"

NSDictionary *A23WaitingReceiverDescription(void)
{
    return @{@"schema":@"A23-waiting-receiver-description-1",@"backend":@"a23-waiting-burst-1",
        @"entry_plan":A23WaitingBurstPlan(),@"wait_budget_ns":@120000000000ULL,@"poll_period_ns":@10000000,
        @"prepare_and_start_separate_turns":@YES,@"unresolved_process_policy":@"retain_no_kill_no_retry",
        @"hardware_verified":@NO,@"allow_next_burst":@NO};
}
@interface A23SelectionJournal : NSObject <A23SessionJournal>
@property A23WaitingJournal *sink;
@property uint64_t selectedID;
@end
@implementation A23SelectionJournal
- (BOOL)append:(NSDictionary *)row error:(NSError **)error
{
    if(![_sink append:row error:error])return NO;
    // Observe selection only AFTER the real durable append acknowledges it.
    if([row[@"event"] isEqual:@"adapter"] && [row[@"details"][@"event"] unsignedIntValue]==A23_E_SELECTED)
        _selectedID=[row[@"details"][@"interface_id"] unsignedLongLongValue];
    return YES;
}
@end
@implementation A23WaitingReceiverLoop {
    dispatch_queue_t _queue;id<A23RuntimeClock> _clock;A23WaitOps _ops;
    id<A23SessionProvider> _provider;id<A23WaitingPermit> _permit;
    A23SelectionJournal *_journal;A23WaitingBurstEntry *_entry;
    BOOL _begun,_prepared,_startAttempted,_exitRequested,_inTick;
}
- (instancetype)initWithHost:(NSString *)host queue:(dispatch_queue_t)queue clock:(id<A23RuntimeClock>)clock
    ops:(const A23WaitOps *)ops provider:(id<A23SessionProvider>)provider permit:(id<A23WaitingPermit>)permit
{
    if(!queue || !clock || !clock.numerator || !clock.denominator || !ops || !provider || !permit)return nil;
    dispatch_assert_queue(queue);
    if((self=[super init])){
        _queue=queue;_clock=clock;_ops=*ops;_provider=provider;_permit=permit;
        _journal=[A23SelectionJournal new];_journal.sink=[[A23WaitingJournal alloc] initWithPath:[host stringByAppendingPathComponent:@"wait.jsonl"]];
        if(!_journal.sink)return nil;
        _entry=[[A23WaitingBurstEntry alloc] initWithDirectory:host queue:queue clock:clock journal:_journal];if(!_entry)return nil;
        __weak A23WaitingReceiverLoop *weak=self;
        _entry.interruptionRequested=^BOOL{A23WaitingReceiverLoop *s=weak;return !s || s->_exitRequested || (s.interruptionRequested && s.interruptionRequested());};
    }return self;
}
- (BOOL)begin
{
    dispatch_assert_queue(_queue);if(_begun || _inTick)return NO;_begun=YES;
    uint64_t start=_clock.nowTicks;__uint128_t delta=((__uint128_t)120000000000ULL*_clock.denominator+_clock.numerator-1)/_clock.numerator;
    if(delta>UINT64_MAX-start){[_entry requestExit];return NO;}
    _inTick=YES;BOOL ok=[_entry beginWithOps:&_ops deadline:start+(uint64_t)delta];_inTick=NO;return ok;
}
- (void)tick
{
    dispatch_assert_queue(_queue);if(!_begun || _inTick || [_entry.result[@"finished"] boolValue])return;
    _inTick=YES;
    if(_exitRequested || (_interruptionRequested && _interruptionRequested()))[_entry requestExit];
    if([_entry.result[@"finished"] boolValue]){_inTick=NO;return;}
    if(_startAttempted)[_entry poll];
    else if(_prepared){_startAttempted=YES;[_entry startPrepared];}
    else if([_entry pollWaiting] && _journal.selectedID)_prepared=[_entry prepareWithProvider:_provider permit:_permit];
    _inTick=NO;
}
- (void)requestExit { dispatch_assert_queue(_queue);_exitRequested=YES;[_entry requestExit]; }
- (void)detachedRegistryID:(uint64_t)identity { dispatch_assert_queue(_queue);[_entry detachedRegistryID:identity]; }
- (uint64_t)selectedInterfaceID { dispatch_assert_queue(_queue);return _journal.selectedID; }
- (NSDictionary *)result { dispatch_assert_queue(_queue);return _entry.result; }
@end
