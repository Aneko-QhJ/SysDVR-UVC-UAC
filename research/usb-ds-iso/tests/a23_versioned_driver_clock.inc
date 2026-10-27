#import "../host/a23_quiet_driver_clock_candidate.h"
#import "../host/a23_versioned_driver_bridge.h"
@interface TwoClock : A23VersionedDriverClockAdapter <A23RuntimeClock,A23QuietDriverCandidateClock>
+ (instancetype)new;
- (instancetype)init;
@property uint32_t n,d,role;
@property uint64_t instance,step,reads;
@property BOOL zeroNext;
- (void)advanceNS:(uint64_t)ns;
- (void)setTicks:(uint64_t)ticks;
@end
@implementation TwoClock { _Atomic uint64_t _ticks,_steps,_reads;_Atomic bool _zero; }
+ (instancetype)new {return [[self alloc] init];}
- (instancetype)init {
    if((self=[super initWithProfile:(A23CandidateClockStamp){0,A23CandidateInjectedDriver,1,1,1} incarnation:1])){
        atomic_init(&_ticks,100);atomic_init(&_steps,100);atomic_init(&_reads,0);atomic_init(&_zero,false);
    }return self;
}
- (void)change:(uint32_t)field value:(uint64_t)value {
    A23CandidateClockStamp profile={0,(A23CandidateClockDomain)self.profileDomain,self.profileInstance,self.numerator,self.denominator};
    if(field==0)profile.numerator=(uint32_t)value;if(field==1)profile.denominator=(uint32_t)value;
    if(field==2)profile.domain=(A23CandidateClockDomain)value;if(field==3)profile.clock_instance=value;
    [self publishProfile:profile];
}
- (uint32_t)n {return self.numerator;}
- (void)setN:(uint32_t)value {[self change:0 value:value];}
- (uint32_t)d {return self.denominator;}
- (void)setD:(uint32_t)value {[self change:1 value:value];}
- (uint32_t)role {return self.profileDomain;}
- (void)setRole:(uint32_t)value {[self change:2 value:value];}
- (uint64_t)instance {return self.profileInstance;}
- (void)setInstance:(uint64_t)value {[self change:3 value:value];}
- (uint64_t)step {return atomic_load(&_steps);}
- (void)setStep:(uint64_t)value {atomic_store(&_steps,value);}
- (uint64_t)reads {return atomic_load(&_reads);}
- (void)setReads:(uint64_t)value {atomic_store(&_reads,value);}
- (BOOL)zeroNext {return atomic_load(&_zero);}
- (void)setZeroNext:(BOOL)value {atomic_store(&_zero,value);}
- (uint64_t)nowTicks {atomic_fetch_add(&_reads,1);if(atomic_exchange(&_zero,false))return 0;return atomic_fetch_add(&_ticks,atomic_load(&_steps));}
- (BOOL)readRawTicks:(uint64_t *)out {if(!out)return NO;*out=self.nowTicks;return YES;}
- (uint32_t)a23QuietDomain {return self.role;}
- (uint64_t)a23QuietClockInstance {return self.instance;}
- (uint32_t)a23QuietNumerator {return self.n;}
- (uint32_t)a23QuietDenominator {return self.d;}
- (void)advanceNS:(uint64_t)ns {assert(self.n && self.d);atomic_fetch_add(&_ticks,(uint64_t)(((__uint128_t)ns*self.d+self.n-1)/self.n));}
- (void)setTicks:(uint64_t)ticks {atomic_store(&_ticks,ticks);}
@end
