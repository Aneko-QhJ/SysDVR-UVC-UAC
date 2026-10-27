#import "a23_versioned_driver_bridge.h"

static bool rawReader(void *context,uint64_t *ticks)
{return [(__bridge A23VersionedDriverClockAdapter *)context readRawTicks:ticks];}
@implementation A23VersionedDriverClockAdapter {
    A23VersionedClockStore _store;
    uint64_t _commitTicket;
    A23VersionedClockSample _commitSample;
    _Atomic uint64_t _attempts,_successes,_busy;
    _Atomic unsigned _lastWrite;
}
- (instancetype)initWithProfile:(A23CandidateClockStamp)profile incarnation:(uint64_t)incarnation {
    if((self=[super init])){
        if(A23VersionedClockInit(&_store,incarnation,&profile)!=A23VersionedClockOK)return nil;
        atomic_init(&_attempts,0);atomic_init(&_successes,0);atomic_init(&_busy,0);atomic_init(&_lastWrite,0);
    }return self;
}
- (BOOL)readRawTicks:(uint64_t *)out {(void)out;return NO;}
- (A23VersionedClockStatus)versionedProfile:(A23VersionedClockSample *)out {return A23VersionedClockReadProfile(&_store,out);}
- (A23VersionedClockStatus)versionedCapture:(A23VersionedClockSample *)out {return A23VersionedClockCapture(&_store,rawReader,(__bridge void *)self,out);}
- (A23VersionedClockStatus)publishProfile:(A23CandidateClockStamp)profile {
    atomic_fetch_add(&_attempts,1);uint64_t ticket;
    A23VersionedClockStatus status=A23VersionedClockBegin(&_store,&ticket);
    if(status==A23VersionedClockOK)status=A23VersionedClockFinish(&_store,ticket,&profile);
    atomic_store(&_lastWrite,(unsigned)status);
    if(status==A23VersionedClockOK)atomic_fetch_add(&_successes,1);
    if(status==A23VersionedClockBusy)atomic_fetch_add(&_busy,1);
    return status;
}
- (BOOL)versionedBeginCommit:(const A23VersionedClockSample *)end {
    if(!end || _commitTicket || end->store_identity!=&_store || end->incarnation!=_store.incarnation ||
       !end->generation || (end->generation&1) || end->generation>UINT64_MAX-2)return NO;
    uint64_t ticket;
    if(A23VersionedClockBegin(&_store,&ticket)!=A23VersionedClockOK)return NO;
    if(ticket!=end->generation+1){A23VersionedClockAbort(&_store,ticket);return NO;}
    _commitSample=*end;_commitTicket=ticket;return YES;
}
- (BOOL)versionedEndCommit:(uint64_t *)generation {
    if(generation)*generation=0;
    if(!generation || !_commitTicket)return NO;
    uint64_t ticket=_commitTicket;_commitTicket=0;_commitSample=(A23VersionedClockSample){0};
    if(A23VersionedClockAbort(&_store,ticket)!=A23VersionedClockOK)return NO;
    *generation=ticket+1;return YES;
}
- (BOOL)versionedMatchesGeneration:(uint64_t)generation {
    if(!generation || (generation&1) || atomic_load(&_store.poisoned))return NO;
    if(_commitTicket){
        return generation==_commitSample.generation && _commitTicket==generation+1 &&
            atomic_load(&_store.generation)==_commitTicket && _store.incarnation==_commitSample.incarnation &&
            atomic_load(&_store.domain)==(uint32_t)_commitSample.stamp.domain && atomic_load(&_store.clock_instance)==_commitSample.stamp.clock_instance &&
            atomic_load(&_store.numerator)==_commitSample.stamp.numerator && atomic_load(&_store.denominator)==_commitSample.stamp.denominator;
    }
    A23VersionedClockSample now;
    return A23VersionedClockReadProfile(&_store,&now)==A23VersionedClockOK && now.generation==generation;
}
- (uint32_t)numerator {return atomic_load(&_store.numerator);}
- (uint32_t)denominator {return atomic_load(&_store.denominator);}
- (uint32_t)profileDomain {return atomic_load(&_store.domain);}
- (uint64_t)profileInstance {return atomic_load(&_store.clock_instance);}
- (uint64_t)profileGeneration {return atomic_load(&_store.generation);}
- (uint64_t)writeAttempts {return atomic_load(&_attempts);}
- (uint64_t)writeSuccesses {return atomic_load(&_successes);}
- (uint64_t)busyWrites {return atomic_load(&_busy);}
- (A23VersionedClockStatus)lastWriteStatus {return (A23VersionedClockStatus)atomic_load(&_lastWrite);}
@end

static BOOL contract(id object) {
    if(!object || ![object conformsToProtocol:@protocol(A23VersionedDriverClock)])return NO;
    for(NSString *name in @[@"versionedProfile:",@"versionedCapture:",@"versionedBeginCommit:",@"versionedEndCommit:",@"versionedMatchesGeneration:"])
        if(![object respondsToSelector:NSSelectorFromString(name)])return NO;
    return YES;
}
static BOOL sample(id object,BOOL ticks,A23VersionedDriverSample *out) {
    if(out)*out=(A23VersionedDriverSample){0};
    if(!out || !contract(object))return NO;
    A23VersionedClockSample value;A23VersionedClockStatus status=ticks ? [(id<A23VersionedDriverClock>)object versionedCapture:&value] : [(id<A23VersionedDriverClock>)object versionedProfile:&value];
    if(status!=A23VersionedClockOK || !value.store_identity || !value.incarnation || !value.generation || (value.generation&1) ||
        value.stamp.domain!=A23CandidateInjectedDriver || !value.stamp.clock_instance || !value.stamp.numerator || !value.stamp.denominator)return NO;
    *out=(A23VersionedDriverSample){value,(uintptr_t)(__bridge void *)object};return YES;
}
BOOL A23VersionedDriverReadProfile(id object,A23VersionedDriverSample *out){return sample(object,NO,out);}
BOOL A23VersionedDriverCapture(id object,A23VersionedDriverSample *out){return sample(object,YES,out);}
A23CandidateClockStatus A23VersionedDriverEvaluate(const A23VersionedDriverSample *begin,const A23VersionedDriverSample *end,uint64_t minimum,A23CandidateClockResult *out){
    if(out)*out=(A23CandidateClockResult){0};
    if(!begin || !end || !out)return A23CandidateClockInvalidArgument;
    if(!begin->object_identity || begin->object_identity!=end->object_identity)return A23CandidateClockMismatch;
    return A23VersionedClockEvaluate(&begin->version,&end->version,minimum,out);
}
BOOL A23VersionedDriverBeginCommit(id object,const A23VersionedDriverSample *end){return contract(object) && end && end->object_identity==(uintptr_t)(__bridge void *)object && [(id<A23VersionedDriverClock>)object versionedBeginCommit:&end->version];}
BOOL A23VersionedDriverEndCommit(id object,uint64_t *generation){if(generation)*generation=0;return contract(object) && generation && [(id<A23VersionedDriverClock>)object versionedEndCommit:generation];}
BOOL A23VersionedDriverMatches(id object,uint64_t generation){return contract(object) && [(id<A23VersionedDriverClock>)object versionedMatchesGeneration:generation];}
