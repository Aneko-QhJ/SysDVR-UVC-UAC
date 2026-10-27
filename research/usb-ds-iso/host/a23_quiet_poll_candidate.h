#ifndef A23_QUIET_POLL_CANDIDATE_H
#define A23_QUIET_POLL_CANDIDATE_H
#include "a23_clock_candidate.h"

/* Quiet-only offline adapter. Guards and append outcomes are supplied mocks.
 * Quiet completion accepts the injected-driver role only; no owner promotion.
 */
typedef enum { A23QuietCompleteEvent = 1, A23QuietStopEvent = 2 } A23QuietCandidateEvent;
typedef enum {
    A23QuietNoReason = 0, A23QuietClockFailure = 1, A23QuietGuardFailure = 2,
    A23QuietJournalFailure = 3, A23QuietInvalidState = 4
} A23QuietCandidateReason;
typedef enum {
    A23QuietIdle = 0, A23QuietWaiting = 1, A23QuietSettled = 2,
    A23QuietStopped = 3, A23QuietJournalFailed = 4, A23QuietInvalidArgument = 5
} A23QuietCandidatePollStatus;

typedef struct {
    bool started, epochs_saved, stopped, journal_failed, settled, completion_attempted;
    A23CandidateClockStamp quiet_start;
    uint64_t settled_at;
    A23QuietCandidateReason reason;
    A23CandidateClockStatus clock_status;
} A23QuietCandidateState;

typedef struct {
    void *context;
    bool (*guard)(void *context);
    bool (*append)(void *context, A23QuietCandidateEvent event);
} A23QuietCandidateHooks;

/* A terminal failure revokes settled but retains settled_at as diagnostic data.
 * No callback draining, aborts, epoch writes, receipt saving or SDK calls occur.
 */
A23QuietCandidatePollStatus A23QuietCandidatePoll(
    A23QuietCandidateState *state, const A23CandidateClockStamp *now,
    const A23QuietCandidateHooks *hooks);

/* Preserve the frozen driver policy: arrival expires at ceil(ns)>limit;
 * polling without arrival expires at ceil(ns)>=limit. Invalid clocks expire.
 * The caller selects arrival-vs-now; a tick-zero start remains unstarted.
 */
A23CandidateClockStatus A23QuietCandidateDeadline(
    const A23CandidateClockStamp *start, const A23CandidateClockStamp *end,
    uint64_t limit_ns, bool has_arrival, bool *expired);
#endif
