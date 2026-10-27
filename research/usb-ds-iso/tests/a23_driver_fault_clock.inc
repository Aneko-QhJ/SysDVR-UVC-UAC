@interface FaultClock : TwoClock
@property NSString *mutation;
@property uint64_t onRead;
@property NSUInteger mutations;
@end
@implementation FaultClock
- (uint64_t)nowTicks {
    uint64_t ticks=[super nowTicks];
    if(_onRead && self.reads==_onRead){
        ++_mutations;
        if([_mutation isEqual:@"numerator"])self.n=2;
        if([_mutation isEqual:@"denominator"])self.d=2;
        if([_mutation isEqual:@"domain"])self.role=2;
        if([_mutation isEqual:@"instance"])self.instance=2;
        if([_mutation isEqual:@"aba"]){uint32_t saved=self.n;self.n=2;self.n=saved;}
    }return ticks;
}
@end
