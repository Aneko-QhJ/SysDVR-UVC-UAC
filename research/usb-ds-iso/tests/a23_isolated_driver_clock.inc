#import "../host/a23_quiet_driver_clock_candidate.h"
@interface TwoClock : NSObject <A23RuntimeClock,A23QuietDriverCandidateClock>
@property uint32_t n,d,role;
@property uint64_t instance,step,reads;
@property BOOL zeroNext;
- (void)advanceNS:(uint64_t)ns;
- (void)setTicks:(uint64_t)ticks;
@end
@implementation TwoClock { atomic_uint_fast64_t _ticks; }
- (instancetype)init {if((self=[super init])){_n=1;_d=1;_role=1;_instance=1;_step=100;atomic_init(&_ticks,100);}return self;}
- (uint64_t)nowTicks {++_reads;if(_zeroNext){_zeroNext=NO;return 0;}return atomic_fetch_add(&_ticks,_step);}
- (uint32_t)numerator {return _n;}
- (uint32_t)denominator {return _d;}
- (uint32_t)a23QuietDomain {return _role;}
- (uint64_t)a23QuietClockInstance {return _instance;}
- (uint32_t)a23QuietNumerator {return _n;}
- (uint32_t)a23QuietDenominator {return _d;}
- (void)advanceNS:(uint64_t)ns {assert(_n && _d);atomic_fetch_add(&_ticks,(uint64_t)(((__uint128_t)ns*_d+_n-1)/_n));}
- (void)setTicks:(uint64_t)ticks {atomic_store(&_ticks,ticks);}
@end
@interface PlainModelClock : NSObject <A23RuntimeClock>
@property NSUInteger reads;
@end
@implementation PlainModelClock
- (uint64_t)nowTicks {++_reads;return 100;}
- (uint32_t)numerator {return 1;}
- (uint32_t)denominator {return 1;}
@end
