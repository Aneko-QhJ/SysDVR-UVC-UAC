#import "a23_quiet_driver_clock_candidate.h"
#include <stdio.h>

@interface BridgeClock : NSObject <A23QuietDriverCandidateClock>
@property uint64_t value, instance, reads;
@property uint32_t role, n, d;
@property NSString *mutation;
@property BOOL denySelector, abaPerformed;
@end
@implementation BridgeClock
- (instancetype)init {if((self=[super init])){_value=100;_instance=1;_role=1;_n=1;_d=1;}return self;}
- (uint32_t)a23QuietDomain {return _role;}
- (uint64_t)a23QuietClockInstance {return _instance;}
- (uint32_t)numerator {return _n;}
- (uint32_t)denominator {return _d;}
- (BOOL)respondsToSelector:(SEL)selector {
    if(_denySelector && selector==@selector(denominator))return NO;
    return [super respondsToSelector:selector];
}
- (uint64_t)nowTicks {
    ++_reads;
    if(_reads==2){
        if([_mutation isEqual:@"numerator-during"])_n=2;
        if([_mutation isEqual:@"denominator-during"])_d=2;
        if([_mutation isEqual:@"instance-during"])_instance=2;
        if([_mutation isEqual:@"domain-during"])_role=2;
        if([_mutation isEqual:@"aba-during"]){uint32_t saved=_n;_n=2;_abaPerformed=YES;_n=saved;}
    }
    return _value;
}
@end

@interface PlainClock : NSObject
@property uint64_t reads;
@end
@implementation PlainClock
- (uint64_t)nowTicks {++_reads;return 100;}
- (uint32_t)numerator {return 1;}
- (uint32_t)denominator {return 1;}
@end
@interface PretendClock : NSObject
@end
@implementation PretendClock
- (BOOL)conformsToProtocol:(Protocol *)protocol {
    return protocol==@protocol(A23QuietDriverCandidateClock) || [super conformsToProtocol:protocol];
}
@end

static BOOL empty(A23QuietDriverClockSample v)
{
    return !v.stamp.ticks && !v.stamp.domain && !v.stamp.clock_instance && !v.stamp.numerator &&
           !v.stamp.denominator && !v.object_identity;
}

static NSDictionary *one(NSString *name)
{
    BridgeClock *clock=[BridgeClock new];clock.value=100;
    uint64_t end=250000100;
    if([name hasPrefix:@"fractional-"]){clock.n=2;clock.d=3;
        end=[name isEqual:@"fractional-short"]?375000099:[name isEqual:@"fractional-equal"]?375000100:375000101;}
    if([name isEqual:@"zero-tick"]){clock.value=0;end=250000000;}
    if([name isEqual:@"backwards"])end=99;
    if([name isEqual:@"overflow"]){clock.value=1;clock.n=UINT32_MAX;end=UINT64_MAX;}
    if([name isEqual:@"zero-instance"])clock.instance=0;
    if([name isEqual:@"zero-numerator"])clock.n=0;
    if([name isEqual:@"zero-denominator"])clock.d=0;
    if([name isEqual:@"owner-role"])clock.role=2;
    if([name isEqual:@"supervisor-role"])clock.role=3;
    if([name isEqual:@"unknown-role"])clock.role=99;
    if([name isEqual:@"missing-selector"])clock.denySelector=YES;
    clock.mutation=name;
    PlainClock *plain=[PlainClock new];
    id object=clock;
    if([name isEqual:@"plain-clock"])object=plain;
    if([name isEqual:@"pretend-clock"])object=[PretendClock new];
    if([name isEqual:@"nil-clock"])object=nil;
    A23QuietDriverClockSample profile={0},begin={{7,A23CandidateNativeOwner,7,7,7},7},finish={{7,A23CandidateNativeOwner,7,7,7},7};
    BOOL profileOK=A23QuietDriverReadProfile(object,&profile);
    uint64_t preflightReads=clock.reads+plain.reads;
    BOOL beginOK=A23QuietDriverCapture(object,&begin);
    clock.value=end;
    if([name isEqual:@"numerator-between"])clock.n=2;
    if([name isEqual:@"denominator-between"])clock.d=2;
    if([name isEqual:@"instance-between"])clock.instance=2;
    if([name isEqual:@"domain-between"])clock.role=2;
    BridgeClock *replacement=nil;
    if([name isEqual:@"object-replaced"]){replacement=[BridgeClock new];replacement.value=end;object=replacement;}
    BOOL endOK=A23QuietDriverCapture(object,&finish);
    A23CandidateClockResult result={0};
    A23CandidateClockStatus status=beginOK && endOK ? A23QuietDriverEvaluate(&begin,&finish,250000000,&result):A23CandidateClockInvalidArgument;
    return @{@"profile_ok":@(profileOK),@"begin_ok":@(beginOK),@"end_ok":@(endOK),@"status":@(status),
        @"rounded_up_ns":@(result.rounded_up_ns),@"minimum_met":@(result.minimum_met),
        @"preflight_tick_reads":@(preflightReads),@"tick_reads":@(clock.reads+plain.reads+replacement.reads),
        @"begin_zeroed":@(empty(begin)),@"end_zeroed":@(empty(finish)),
        @"same_object":@((BOOL)(begin.object_identity && begin.object_identity==finish.object_identity)),
        @"aba_performed":@(clock.abaPerformed)};
}

int main(int argc,const char *argv[])
{
    (void)argv;if(argc!=1)return 2;
    @autoreleasepool {
        NSArray *names=@[@"normal",@"fractional-short",@"fractional-equal",@"fractional-after",@"zero-tick",@"backwards",@"overflow",
            @"zero-instance",@"zero-numerator",@"zero-denominator",@"owner-role",@"supervisor-role",@"unknown-role",@"missing-selector",
            @"plain-clock",@"pretend-clock",@"nil-clock",@"numerator-between",@"denominator-between",@"instance-between",@"domain-between",
            @"numerator-during",@"denominator-during",@"instance-during",@"domain-during",@"object-replaced",@"aba-during"];
        NSMutableDictionary *rows=[NSMutableDictionary new];for(NSString *name in names)rows[name]=one(name);
        BridgeClock *clock=[BridgeClock new];A23QuietDriverClockSample s={0};A23CandidateClockResult result={7,true,true,true};
        BOOL pointerOK=!A23QuietDriverReadProfile(clock,NULL) && !A23QuietDriverCapture(clock,NULL) &&
            A23QuietDriverEvaluate(NULL,&s,1,&result)==A23CandidateClockInvalidArgument && !result.rounded_up_ns && !result.minimum_met &&
            A23QuietDriverEvaluate(&s,NULL,1,&result)==A23CandidateClockInvalidArgument &&
            A23QuietDriverEvaluate(&s,&s,1,NULL)==A23CandidateClockInvalidArgument;
        NSDictionary *out=@{@"cases":rows,@"pointer_checks_passed":@(pointerOK),@"actual_clock_queries":@0,@"real_sdk_objects":@0,@"usb_requests":@0,@"sd_accesses":@0};
        NSData *raw=[NSJSONSerialization dataWithJSONObject:out options:NSJSONWritingSortedKeys error:NULL];
        if(!raw)return 3;fwrite(raw.bytes,1,raw.length,stdout);puts("");
    }return 0;
}
