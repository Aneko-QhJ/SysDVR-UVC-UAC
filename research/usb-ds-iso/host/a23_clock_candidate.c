#include "a23_clock_candidate.h"

static bool known_domain(A23CandidateClockDomain domain)
{
    return domain == A23CandidateInjectedDriver || domain == A23CandidateNativeOwner ||
           domain == A23CandidateSupervisorNS;
}

A23CandidateClockStatus A23CandidateClockEvaluate(
    const A23CandidateClockStamp *begin, const A23CandidateClockStamp *end,
    uint64_t minimum_ns, uint64_t maximum_ns, A23CandidateClockResult *result)
{
    if (!result) return A23CandidateClockInvalidArgument;
    *result = (A23CandidateClockResult){0};
    if (!begin || !end || minimum_ns > maximum_ns)
        return A23CandidateClockInvalidArgument;
    if (!known_domain(begin->domain) || !known_domain(end->domain))
        return A23CandidateClockUnknownDomain;
    if (!begin->numerator || !begin->denominator || !end->numerator || !end->denominator)
        return A23CandidateClockInvalidTimebase;
    if ((begin->domain == A23CandidateSupervisorNS &&
         (begin->numerator != 1 || begin->denominator != 1)) ||
        (end->domain == A23CandidateSupervisorNS &&
         (end->numerator != 1 || end->denominator != 1)))
        return A23CandidateClockInvalidTimebase;
    if (!begin->clock_instance || !end->clock_instance ||
        begin->domain != end->domain || begin->clock_instance != end->clock_instance ||
        begin->numerator != end->numerator || begin->denominator != end->denominator)
        return A23CandidateClockMismatch;
    if (end->ticks < begin->ticks) return A23CandidateClockReversed;

    /* uint64 * uint32 is below 2^96; the ceiling addition also fits uint128. */
    const __uint128_t scaled = (__uint128_t)(end->ticks - begin->ticks) * begin->numerator;
    const __uint128_t rounded = (scaled + begin->denominator - 1) / begin->denominator;
    if (rounded > UINT64_MAX) return A23CandidateClockOverflow;

    result->rounded_up_ns = (uint64_t)rounded;
    result->minimum_met = scaled >= (__uint128_t)minimum_ns * begin->denominator;
    result->maximum_met = scaled <= (__uint128_t)maximum_ns * begin->denominator;
    result->within_interval = result->minimum_met && result->maximum_met;
    return A23CandidateClockOK;
}
