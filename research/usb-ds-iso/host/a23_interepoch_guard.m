#import "a23_interepoch_guard.h"
#include <time.h>

static uint64_t guardNow(void) {
    struct timespec t;
    if(clock_gettime(CLOCK_MONOTONIC_RAW,&t))return 0;
    return (uint64_t)t.tv_sec*1000000000ULL+(uint64_t)t.tv_nsec;
}
static BOOL boundaryMatches(NSDictionary *v,NSUInteger epoch) {
    if(![v isKindOfClass:NSDictionary.class])return NO;
    for(NSString *key in @[@"saved_epochs",@"iso_attempts"])
        if(![v[key] isKindOfClass:NSNumber.class] || ![v[key] isEqual:@(epoch)])return NO;
    return [v[@"durable"] isEqual:@YES] && [v[@"pending"] isEqual:@NO] &&
        [v[@"stopped"] isEqual:@NO];
}

@implementation A23InterepochGuard {
    dispatch_queue_t _queue,_worker;
    NSString *_job,*_scopeDigest;
    BOOL (^_fullCheck)(void);NSDictionary *(^_boundary)(void);
    BOOL (^_recheck)(void);void (^_poll)(void),(^_stop)(void),(^_finished)(void);
    BOOL _busy,_ownsVerifier,_stopped,_delivering;
    NSUInteger _nextEpoch,_generation,_checks,_returns,_rechecks,_polls,_discarded;
    uint64_t _deadline;
    NSDictionary *_request,*_lastReceipt;
    NSMutableArray *_reasons;
}
- (instancetype)initWithQueue:(dispatch_queue_t)queue job:(NSString *)job
    scopeDigest:(NSString *)scopeDigest fullCheck:(BOOL (^)(void))fullCheck
    boundary:(NSDictionary *(^)(void))boundary recheck:(BOOL (^)(void))recheck
    poll:(void (^)(void))poll stop:(void (^)(void))stop finished:(void (^)(void))finished {
    if(!queue || !job.length || scopeDigest.length!=64 || !fullCheck || !boundary ||
       !recheck || !poll || !stop || !finished)return nil;
    if((self=[super init])){
        _queue=queue;_worker=dispatch_queue_create("a23.interepoch.full-guard",DISPATCH_QUEUE_SERIAL);
        _job=[job copy];_scopeDigest=[scopeDigest copy];_fullCheck=[fullCheck copy];
        _boundary=[boundary copy];_recheck=[recheck copy];_poll=[poll copy];
        _stop=[stop copy];_finished=[finished copy];_nextEpoch=1;_generation=1;
        _ownsVerifier=YES;_reasons=[NSMutableArray new];
    }return self;
}
- (void)stopWithReason:(NSString *)reason {
    dispatch_assert_queue(_queue);
    if(!_stopped){_stopped=YES;_generation++;_stop();}
    if(![_reasons containsObject:reason])[_reasons addObject:[reason copy]];
}
- (void)observeDeadline {
    dispatch_assert_queue(_queue);if(!_busy)return;
    uint64_t now=guardNow();if(!now || now>=_deadline)[self stopWithReason:@"guard_deadline"];
}
// Private: accepts only after the dispatch group reports work-block return.
- (void)returnedReceipt:(NSDictionary *)receipt {
    dispatch_assert_queue(_queue);
    if(!_busy || !_ownsVerifier){_discarded++;return;}
    BOOL identity=[receipt isKindOfClass:NSDictionary.class] &&
        [receipt[@"request"] isEqual:_request] &&
        [receipt[@"phase"] isEqual:@"between_epochs"];
    _lastReceipt=[receipt copy];
    [self observeDeadline];
    NSUInteger epoch=[_request[@"epoch"] unsignedIntegerValue];
    NSUInteger generation=[_request[@"generation"] unsignedIntegerValue];
    if(!identity)[self stopWithReason:@"receipt_identity"];
    else if(![receipt[@"passed"] isEqual:@YES])[self stopWithReason:@"full_check_failed"];
    if(!_stopped && (generation!=_generation || !boundaryMatches(_boundary(),epoch)))
        [self stopWithReason:@"boundary_changed"];
    if(!_stopped){
        _rechecks++;
        if(!_recheck())[self stopWithReason:@"job_or_permit_changed"];
    }
    // recheck may itself observe a stop or a boundary change. Never trust the
    // pre-recheck state; do not let a successful check clear a later failure.
    [self observeDeadline];
    if(!_stopped && (generation!=_generation || !boundaryMatches(_boundary(),epoch)))
        [self stopWithReason:@"final_boundary_changed"];
    _busy=NO;_delivering=YES;
    if(!_stopped){_nextEpoch++;_polls++;_poll();}
    _delivering=NO;
    _finished();
}
- (BOOL)requestEpoch:(NSUInteger)epoch deadlineNS:(uint64_t)deadline {
    dispatch_assert_queue(_queue);
    if(_busy || _delivering || !_ownsVerifier || _stopped || epoch!=_nextEpoch || epoch>2)return NO;
    uint64_t now=guardNow();
    if(!now || deadline<=now || !boundaryMatches(_boundary(),epoch))return NO;
    _busy=YES;_ownsVerifier=NO;_checks++;_deadline=deadline;
    _request=@{@"job":_job,@"scope_sha256":_scopeDigest,@"epoch":@(epoch),
        @"generation":@(_generation),@"request_id":@(_checks)};
    NSDictionary *request=_request;__block NSDictionary *receipt;
    dispatch_group_t group=dispatch_group_create();
    dispatch_group_async(group,_worker,^{@autoreleasepool{
        BOOL ok=NO;uint64_t begin=guardNow();
        @try {ok=self->_fullCheck();} @catch(NSException *e){(void)e;ok=NO;}
        uint64_t end=guardNow();
        receipt=@{@"request":request,@"phase":@"between_epochs",
            @"passed":@((BOOL)(ok && begin && end>=begin)),
            @"begin_ns":@(begin),@"end_ns":@(end)};
    }});
    dispatch_group_notify(group,_queue,^{
        // The work block, including its autorelease pool, has returned. This
        // handoff covers this verifier only; it says nothing about SDK drain.
        self->_ownsVerifier=YES;self->_returns++;
        [self returnedReceipt:receipt];
    });
    return YES;
}
- (NSDictionary *)result {
    dispatch_assert_queue(_queue);
    return @{@"schema":@"A23-interepoch-guard-1",@"busy":@(_busy),
        @"verifier_on_serial_queue":@(_ownsVerifier),@"stopped":@(_stopped),
        @"next_epoch":@(_nextEpoch),@"generation":@(_generation),
        @"full_checks":@(_checks),@"worker_returns":@(_returns),
        @"job_rechecks":@(_rechecks),@"resumed_polls":@(_polls),
        @"discarded_receipts":@(_discarded),@"reasons":[_reasons copy],
        @"last_receipt":_lastReceipt?:@{},@"hardware_entry_enabled":@NO,
        @"callback_drain_verified":@NO,@"buffer_reuse_verified":@NO};
}
@end
