"""Pinned transformations for an isolated, injected-clock-only driver copy."""
import difflib
import audit_a23_quiet_poll_candidate as previous
f=previous.f
ORIGINAL_SHA='4f7f46345f1dbadf12b02bcf8c2322caacde33a63addd219976c9b942bfe8797'


def replace_once(text,old,new):
    f.require(text.count(old)==1,'driver patch anchor missing or repeated')
    return text.replace(old,new,1)


def render(raw):
    f.require(type(raw) is bytes and f.sha(raw)==ORIGINAL_SHA,'frozen driver pin differs')
    text=raw.decode()
    text=replace_once(text,'#import "a23_two_epoch_sdk_driver.h"',
                      '#import "a23_two_epoch_sdk_driver.h"\n#import "a23_quiet_driver_clock_candidate.h"')
    text=replace_once(text,'BOOL _settled,_receiptAttempted,_receiptSaved,_receiptStale;uint64_t _quietSince,_settledAt;NSData *_receiptSnapshot;',
                      'BOOL _settled,_receiptAttempted,_receiptSaved,_receiptStale;uint64_t _quietSince,_settledAt;NSData *_receiptSnapshot;\n    A23QuietDriverClockSample _quietClockStart;')
    text=replace_once(text,'    dispatch_assert_queue(queue);\n    NSArray<NSMutableData *> *data=',
                      '    A23QuietDriverClockSample quietProfile;\n    if(!A23QuietDriverReadProfile(clock,&quietProfile)){fail(error,@"Explicit injected quiet clock profile required");return nil;}\n    dispatch_assert_queue(queue);\n    NSArray<NSMutableData *> *data=')
    old='''        if(!_settled){uint64_t now=_clock.nowTicks,ns=0;
            if(!_quietSince || now<_quietSince || !A23TicksToNanoseconds(now-_quietSince,_clock.numerator,_clock.denominator,&ns)){[self stop:@"observation_clock"];return;}
            if(ns>=250000000 && [self emit:@"observation_complete" details:@{@"quiet_start_ticks":@(_quietSince),@"quiet_end_ticks":@(now),@"minimum_ns":@250000000}] && [self guard]){_settled=YES;_settledAt=now;}
        }return;'''
    new='''        if(!_settled){A23QuietDriverClockSample now;A23CandidateClockResult duration;
            if(!_quietSince || _quietClockStart.stamp.ticks!=_quietSince || !A23QuietDriverCapture(_clock,&now) ||
                A23QuietDriverEvaluate(&_quietClockStart,&now,250000000,&duration)!=A23CandidateClockOK){[self stop:@"observation_clock"];return;}
            if(duration.minimum_met && [self emit:@"observation_complete" details:@{@"quiet_start_ticks":@(_quietSince),@"quiet_end_ticks":@(now.stamp.ticks),@"minimum_ns":@250000000}] && [self guard]){_settled=YES;_settledAt=now.stamp.ticks;}
        }return;'''
    text=replace_once(text,old,new)
    text=replace_once(text,'    if(_epoch==2){_complete=YES;if([self emit:@"epochs_saved" details:@{@"saved_epochs":@2}] && [self guard])_quietSince=_clock.nowTicks;}',
                     '''    if(_epoch==2){_complete=YES;if([self emit:@"epochs_saved" details:@{@"saved_epochs":@2}] && [self guard]){
        A23QuietDriverClockSample start;
        if(!A23QuietDriverCapture(_clock,&start) || !start.stamp.ticks){[self stop:@"observation_clock"];return;}
        _quietClockStart=start;_quietSince=start.stamp.ticks;
    }}''')
    return text.encode()


def protected_slices(raw):
    text=raw.decode();out={}
    for name,begin,end in (
        ('deadline','- (BOOL)elapsed:','- (BOOL)verifySnapshot:'),
        ('emit-stop-guard','- (BOOL)emit:','- (BOOL)start {'),
        ('receipt-and-result','- (void)requestStop','\n@end')):
        f.require(text.count(begin)==1,'protected slice anchor differs')
        start=text.index(begin);finish=text.index(end,start)
        out[name]=text[start:finish].encode()
    return out


def diff(raw,candidate):
    return ''.join(difflib.unified_diff(raw.decode().splitlines(True),candidate.decode().splitlines(True),
                   fromfile='frozen/host/a23_two_epoch_sdk_driver.m',tofile='candidate/host/a23_two_epoch_sdk_driver.m')).encode()
