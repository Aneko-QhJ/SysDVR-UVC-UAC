#import "io_usb_host_no_td_driver.h"
#include <mach/mach_time.h>

@implementation A23NoTDDriver {
    NSString *_directory;
    dispatch_queue_t _queue;
    id<A23RuntimeClock> _clock;
    A23SDKNoTDSession *_session;
    __weak id<A23SessionResources> _resources;
    uint64_t _submittedAt, _closedAt;
    BOOL _attempted, _finished, _unresolved, _exitRequested, _enqueueAccepted, _completionHandled, _failed;
    int _exitCode;
}
- (instancetype)initWithDirectory:(NSString *)directory queue:(dispatch_queue_t)queue clock:(id<A23RuntimeClock>)clock
{
    A23SimulationJournal *journal = [[A23SimulationJournal alloc] initWithPath:
        [directory stringByAppendingPathComponent:@"session.jsonl"] error:NULL];
    if (!journal || !clock || !queue) return nil;
    if ((self = [super init])) {
        _directory = [directory copy]; _queue = queue; _clock = clock; _exitCode = 1;
        _session = [[A23SDKNoTDSession alloc] initWithQueue:queue journal:journal clock:clock];
        if (!_session) return nil;
    }
    return self;
}
- (BOOL)startCandidates:(NSArray<NSDictionary *> *)candidates provider:(A23AdapterSDKProvider *)provider
{
    dispatch_assert_queue(_queue);
    if (_attempted || _exitRequested) return NO; _attempted = YES;
    if (_interruptionRequested && _interruptionRequested()) { candidates = @[]; _failed = YES; }
    if (![_session prepareCandidates:candidates provider:provider]) {
        _failed = YES; if (![_session close]) [self requestExit]; return NO;
    }
    _resources = provider.openedResources;
    if ([self stopForInterruption]) return NO;
    if (![_resources respondsToSelector:@selector(readStatus)] || ![_resources respondsToSelector:@selector(readFrameSample)]) {
        _failed = YES; [_session requestExit]; _exitRequested = YES; return NO;
    }
    NSDictionary *before = [_resources readStatus];
    if (![_session recordStatusPhase:@"before" data:before[@"data"] observation:before[@"observation"]]) {
        _failed = YES; if (![_session close]) [self requestExit]; return NO;
    }
    if ([self stopForInterruption]) return NO;
    if (![_session recordFrameSample:[_resources readFrameSample]]) {
        _failed = YES; if (![_session close]) [self requestExit]; return NO;
    }
    if ([self stopForInterruption]) return NO;
    _submittedAt = [_clock nowTicks];
    BOOL accepted = [_session submitFirstFrame:_session.plannedFirstFrame]; _enqueueAccepted = accepted;
    // Rejected admission has no callback/after STATUS. Its core failure evidence
    // is saved and acknowledged before releasing the allocated buffers.
    if (!accepted && _session.state == A23SessionCompleted) [self poll];
    else if (_session.stopped && _session.state == A23SessionPending) [self requestExit];
    return accepted;
}
- (BOOL)stopForInterruption
{
    if (_interruptionRequested && _interruptionRequested()) { _failed = YES; [self requestExit]; return YES; }
    return NO;
}
- (void)requestExit
{
    dispatch_assert_queue(_queue);
    if (_exitRequested || _finished) return; _exitRequested = YES;
    [_session requestExit];
}
- (void)detachedRegistryID:(uint64_t)registryID
{
    dispatch_assert_queue(_queue);
    if ([_session detachedRegistryID:registryID]) [self requestExit];
}
- (void)poll
{
    dispatch_assert_queue(_queue);
    if (_finished) return;
    // A failed journal before any resources existed has no DMA to retain.
    // Pending or unsaved requests keep at least one of these ownership flags.
    if (_session.journalFailed && !_session.resourcesRetained && !_session.storageRetained) {
        _finished = YES; _exitCode = 1; return;
    }
    [self stopForInterruption];
    if (_session.state == A23SessionCompleted && !_completionHandled) {
        _completionHandled = YES;
        if (_enqueueAccepted && !_session.journalFailed) {
            NSDictionary *after = [_resources readStatus];
            [_session recordStatusPhase:@"after" data:after[@"data"] observation:after[@"observation"]];
        }
        if ([_session saveToParent:_directory name:@"transfer" scenario:@{@"kind":@"no_td"}]) [_session close];
        else { [self requestExit]; _unresolved = YES; return; }
    }
    if (_session.state == A23SessionClosed) {
        uint64_t now = [_clock nowTicks], ns = 0;
        if (!_closedAt) _closedAt = now;
        if (now >= _closedAt && A23TicksToNanoseconds(now-_closedAt,_clock.numerator,_clock.denominator,&ns) && ns >= 250000000) {
            _exitCode = (_failed || _session.stopped) ? 1 : 0; _finished = YES; _unresolved = NO;
        }
        return;
    }
    if (!_exitRequested && _session.state == A23SessionPending) {
        uint64_t now = [_clock nowTicks], ns = 0;
        BOOL valid = now >= _submittedAt && A23TicksToNanoseconds(now-_submittedAt,_clock.numerator,_clock.denominator,&ns);
        if (!valid || ns >= 2000000000 || _session.stopped) [self requestExit];
    }
    if (!_exitRequested && _session.state == A23SessionRetained) [self requestExit];
    if (_exitRequested && _session.exitDisposition == 2) _unresolved = YES;
}
- (A23SDKNoTDSession *)session { return _session; }
- (BOOL)finished { return _finished; }
- (BOOL)unresolved { return _unresolved; }
- (int)exitCode { return _exitCode; }
@end
