#ifndef A23_CLOCK_CANDIDATE_H
#define A23_CLOCK_CANDIDATE_H

#include <stdbool.h>
#include <stdint.h>

/* Offline arithmetic candidate. Labels do not authenticate clock origins. */
typedef enum {
    A23CandidateInjectedDriver = 1,
    A23CandidateNativeOwner = 2,
    A23CandidateSupervisorNS = 3
} A23CandidateClockDomain;

typedef struct {
    uint64_t ticks;
    A23CandidateClockDomain domain;
    uint64_t clock_instance;
    uint32_t numerator;
    uint32_t denominator;
} A23CandidateClockStamp;

typedef enum {
    A23CandidateClockOK = 0,
    A23CandidateClockInvalidArgument = 1,
    A23CandidateClockUnknownDomain = 2,
    A23CandidateClockInvalidTimebase = 3,
    A23CandidateClockMismatch = 4,
    A23CandidateClockReversed = 5,
    A23CandidateClockOverflow = 6
} A23CandidateClockStatus;

typedef struct {
    uint64_t rounded_up_ns;
    bool minimum_met;
    bool maximum_met;
    bool within_interval;
} A23CandidateClockResult;

/* Inclusive [minimum_ns, maximum_ns]. On failure all output fields are zero.
 * A zero tick is arithmetic data; lifecycle/start sentinels belong to callers.
 * No domain mapping, clock query, callback handling or hardware API is used.
 */
A23CandidateClockStatus A23CandidateClockEvaluate(
    const A23CandidateClockStamp *begin, const A23CandidateClockStamp *end,
    uint64_t minimum_ns, uint64_t maximum_ns, A23CandidateClockResult *result);

#endif
