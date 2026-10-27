#import "a23_terminal_observation.h"
#include "a23_service_observation.h"
#include <time.h>

static uint64_t terminalNow(void) {
    struct timespec t;if(clock_gettime(CLOCK_MONOTONIC_RAW,&t))return 0;
    return (uint64_t)t.tv_sec*1000000000ULL+(uint64_t)t.tv_nsec;
}
static BOOL exactBool(id value,BOOL expected) {
    return [value isKindOfClass:NSNumber.class] &&
        CFGetTypeID((__bridge CFTypeRef)value)==CFBooleanGetTypeID() &&
        [value boolValue]==expected;
}
static BOOL terminalBoundary(NSDictionary *b) {
    if(![b isKindOfClass:NSDictionary.class])return NO;
    for(NSString *key in @[@"saved_epochs",@"iso_attempts"]){
        id n=b[key];if(![n isKindOfClass:NSNumber.class] ||
            CFGetTypeID((__bridge CFTypeRef)n)==CFBooleanGetTypeID() ||
            ![n isEqual:@3])return NO;
    }
    return exactBool(b[@"durable"],YES) && exactBool(b[@"pending"],NO) && exactBool(b[@"stopped"],NO);
}
@implementation A23TerminalObservation {
    dispatch_queue_t _queue,_worker;
    NSDictionary *_binding,*_boundary;
    BOOL (^_fullCheck)(void),(^_recheck)(void),(^_poll)(void),(^_finalCheck)(void);
    void (^_finished)(void);
    BOOL _requested,_busy,_ownsVerifier,_failed,_notified,_finalPassed;
    NSUInteger _checks,_returns,_rechecks,_polls,_finals;
    uint64_t _deadline,_workerBegin,_workerEnd;
    NSString *_phase,*_reason;
    NSMutableArray *_events;
    A23ServiceObservation _observation;
}
- (instancetype)initWithQueue:(dispatch_queue_t)queue binding:(NSDictionary *)binding
    fullCheck:(BOOL (^)(void))fullCheck recheck:(BOOL (^)(void))recheck
    poll:(BOOL (^)(void))poll finalCheck:(BOOL (^)(void))finalCheck finished:(void (^)(void))finished {
    if(!queue || !binding.count || !fullCheck || !recheck || !poll || !finalCheck || !finished)return nil;
    if((self=[super init])){
        _queue=queue;_worker=dispatch_queue_create("a23.terminal.full-check",DISPATCH_QUEUE_SERIAL);
        _binding=[binding copy];_fullCheck=[fullCheck copy];_recheck=[recheck copy];
        _poll=[poll copy];_finalCheck=[finalCheck copy];_finished=[finished copy];
        _ownsVerifier=YES;_phase=@"idle";_reason=@"";_events=[NSMutableArray new];
        a23_service_init(&_observation);
    }return self;
}
- (void)event:(NSString *)name time:(uint64_t)now {
    [_events addObject:@{@"event":name,@"ns":@(now)}];
}
- (void)fail:(NSString *)reason {
    if(!_failed){_failed=YES;_reason=[reason copy];_phase=@"failed";
        a23_service_fault(&_observation);[self event:@"failed" time:terminalNow()];}
}
- (void)notifyIfReady {
    if(!_busy && !_notified && (_failed || [_phase isEqual:@"passed"])){
        _notified=YES;_finished();
    }
}
- (void)requestStop {
    dispatch_assert_queue(_queue);[self event:@"stop_requested" time:terminalNow()];
    [self fail:@"exit_requested"];[self notifyIfReady];
}
- (void)service {
    if(_failed)return;
    _polls++;BOOL ok=NO;
    @try {ok=_poll();} @catch(NSException *e){(void)e;ok=NO;}
    uint64_t now=terminalNow();
    if(!ok || _failed){[self fail:@"poll_failed"];[self notifyIfReady];return;}
    [self event:@"poll_completed" time:now];
    if(_observation.stage==A23ServiceIdle){
        if(!a23_service_begin(&_observation,now))[self fail:@"observation_begin"];
        else {_phase=@"observing";[self event:@"window_started" time:now];}
    }else {
        A23ServiceStage stage=a23_service_tick(&_observation,now);
        if(stage==A23ServiceFailed)[self fail:@"service_window_failed"];
        else if(stage==A23ServicePassed){
            [self event:@"window_passed" time:now];_finals++;
            [self event:@"final_check_started" time:terminalNow()];BOOL accepted=NO;
            @try {accepted=_finalCheck();} @catch(NSException *e){(void)e;accepted=NO;}
            if(!accepted || _failed)[self fail:@"final_check_failed"];
            else {_finalPassed=YES;_phase=@"passed";[self event:@"final_check_passed" time:terminalNow()];}
        }
    }
    [self notifyIfReady];
}
- (BOOL)requestBoundary:(NSDictionary *)boundary deadlineNS:(uint64_t)deadline {
    dispatch_assert_queue(_queue);
    if(_requested || _failed){[self fail:@"restart"];[self notifyIfReady];return NO;}
    _requested=YES;_boundary=[boundary copy];uint64_t now=terminalNow();
    if(!now || deadline<=now || !terminalBoundary(boundary)){
        [self fail:@"boundary_or_deadline"];[self notifyIfReady];return NO;
    }
    _deadline=deadline;_busy=YES;_ownsVerifier=NO;_checks++;_phase=@"checking";
    [self event:@"worker_requested" time:now];
    __block BOOL passed=NO;__block uint64_t begin=0,end=0;
    dispatch_group_t group=dispatch_group_create();
    dispatch_group_async(group,_worker,^{@autoreleasepool{
        begin=terminalNow();@try {passed=self->_fullCheck();} @catch(NSException *e){(void)e;passed=NO;}
        end=terminalNow();
    }});
    dispatch_group_notify(group,_queue,^{
        self->_busy=NO;self->_ownsVerifier=YES;self->_returns++;
        self->_workerBegin=begin;self->_workerEnd=end;
        uint64_t returned=terminalNow();[self event:@"worker_returned" time:returned];
        if(!passed || !begin || end<begin)[self fail:@"full_check_failed"];
        if(!returned || returned>=self->_deadline)[self fail:@"guard_deadline"];
        if(!self->_failed){
            self->_rechecks++;[self event:@"recheck_started" time:terminalNow()];BOOL ok=NO;
            @try {ok=self->_recheck();} @catch(NSException *e){(void)e;ok=NO;}
            if(!ok)[self fail:@"job_or_sdk_changed"];
            uint64_t checked=terminalNow();
            if(!checked || checked>=self->_deadline)[self fail:@"guard_deadline"];
            if(!self->_failed){[self event:@"recheck_passed" time:terminalNow()];[self service];}
        }
        [self notifyIfReady];
    });return YES;
}
- (void)tick {
    dispatch_assert_queue(_queue);
    if(_busy){uint64_t now=terminalNow();if(!now || now>=_deadline)[self fail:@"guard_deadline"];return;}
    if([_phase isEqual:@"observing"])[self service];
}
- (BOOL)busy {dispatch_assert_queue(_queue);return _busy;}
- (BOOL)exitAllowed {
    dispatch_assert_queue(_queue);return !_busy && _ownsVerifier && (_failed || [_phase isEqual:@"passed"]);
}
- (NSDictionary *)result {
    dispatch_assert_queue(_queue);NSMutableArray *samples=[NSMutableArray new];
    for(size_t i=0;i<_observation.count;i++)[samples addObject:@(_observation.samples[i])];
    return @{@"schema":@"A23-terminal-observation-1",@"binding":_binding,@"boundary":_boundary?:@{},
        @"clock":@"CLOCK_MONOTONIC_RAW_ns",@"phase":_phase,@"reason":_reason,
        @"requested":@(_requested),@"busy":@(_busy),@"verifier_on_serial_queue":@(_ownsVerifier),
        @"exit_allowed":@(self.exitAllowed),@"accepted":@((BOOL)(!_failed && !_busy && _finalPassed && [_phase isEqual:@"passed"])),
        @"full_checks":@(_checks),@"worker_returns":@(_returns),@"rechecks":@(_rechecks),
        @"polls":@(_polls),@"final_checks":@(_finals),@"guard_deadline_ns":@(_deadline),
        @"worker_begin_ns":@(_workerBegin),@"worker_end_ns":@(_workerEnd),
        @"duration_ns":@(A23_SERVICE_DURATION_NS),@"gap_limit_ns":@(A23_SERVICE_MAX_GAP_NS),
        @"capacity":@(A23_SERVICE_MAX_SAMPLES),@"samples_ns":samples,@"sample_count":@(_observation.count),
        @"max_gap_ns":@(_observation.max_gap_ns),@"events":[_events copy],
        @"hardware_entry_enabled":@NO,@"callback_drain_verified":@NO,@"buffer_reuse_verified":@NO};
}
@end
