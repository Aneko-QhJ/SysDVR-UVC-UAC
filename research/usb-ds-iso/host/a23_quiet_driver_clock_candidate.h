#ifndef A23_QUIET_DRIVER_CLOCK_CANDIDATE_H
#define A23_QUIET_DRIVER_CLOCK_CANDIDATE_H
#import <Foundation/Foundation.h>
#include "a23_clock_candidate.h"

/* Explicit offline-mock contract. A23LocalMachClock does not implement it. */
@protocol A23QuietDriverCandidateClock <NSObject>
@property(readonly) uint32_t a23QuietDomain;
@property(readonly) uint64_t a23QuietClockInstance;
@property(readonly) uint32_t numerator;
@property(readonly) uint32_t denominator;
- (uint64_t)nowTicks;
@end

typedef struct {
    A23CandidateClockStamp stamp;
    uintptr_t object_identity;
} A23QuietDriverClockSample;

static inline BOOL A23QuietDriverReadProfile(id object, A23QuietDriverClockSample *out)
{
    if (!out) return NO;
    *out = (A23QuietDriverClockSample){0};
    if (!object || ![object conformsToProtocol:@protocol(A23QuietDriverCandidateClock)]) return NO;
    for (NSString *name in @[@"a23QuietDomain", @"a23QuietClockInstance", @"numerator", @"denominator", @"nowTicks"])
        if (![object respondsToSelector:NSSelectorFromString(name)]) return NO;
    id<A23QuietDriverCandidateClock> clock = object;
    const uint32_t domain = clock.a23QuietDomain;
    const uint64_t instance = clock.a23QuietClockInstance;
    const uint32_t numerator = clock.numerator, denominator = clock.denominator;
    if (domain != A23CandidateInjectedDriver || !instance || !numerator || !denominator) return NO;
    out->stamp = (A23CandidateClockStamp){0, A23CandidateInjectedDriver, instance, numerator, denominator};
    out->object_identity = (uintptr_t)(__bridge void *)object;
    return YES;
}

static inline BOOL A23QuietDriverCapture(id object, A23QuietDriverClockSample *out)
{
    if (!out) return NO;
    *out = (A23QuietDriverClockSample){0};
    A23QuietDriverClockSample before, after;
    if (!A23QuietDriverReadProfile(object, &before)) return NO;
    const uint64_t ticks = [(id<A23QuietDriverCandidateClock>)object nowTicks];
    if (!A23QuietDriverReadProfile(object, &after) || before.object_identity != after.object_identity ||
        before.stamp.clock_instance != after.stamp.clock_instance || before.stamp.numerator != after.stamp.numerator ||
        before.stamp.denominator != after.stamp.denominator || before.stamp.domain != after.stamp.domain) return NO;
    before.stamp.ticks = ticks;
    *out = before;
    return YES;
}

static inline A23CandidateClockStatus A23QuietDriverEvaluate(
    const A23QuietDriverClockSample *begin, const A23QuietDriverClockSample *end,
    uint64_t minimum_ns, A23CandidateClockResult *out)
{
    if (!out) return A23CandidateClockInvalidArgument;
    *out = (A23CandidateClockResult){0};
    if (!begin || !end) return A23CandidateClockInvalidArgument;
    if (!begin->object_identity || begin->object_identity != end->object_identity)
        return A23CandidateClockMismatch;
    return A23CandidateClockEvaluate(&begin->stamp, &end->stamp, minimum_ns, UINT64_MAX, out);
}
#endif
