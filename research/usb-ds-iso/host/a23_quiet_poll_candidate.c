#include "a23_quiet_poll_candidate.h"

static A23QuietCandidatePollStatus stop_quiet(
    A23QuietCandidateState *state, const A23QuietCandidateHooks *hooks,
    A23QuietCandidateReason reason)
{
    state->stopped = true;
    state->epochs_saved = false;
    state->settled = false;
    if (state->reason == A23QuietNoReason) {
        state->reason = reason;
        if (!state->journal_failed && !hooks->append(hooks->context, A23QuietStopEvent))
            state->journal_failed = true;
    }
    return state->journal_failed ? A23QuietJournalFailed : A23QuietStopped;
}

A23QuietCandidatePollStatus A23QuietCandidatePoll(
    A23QuietCandidateState *state, const A23CandidateClockStamp *now,
    const A23QuietCandidateHooks *hooks)
{
    if (!state) return A23QuietInvalidArgument;
    if (!now || !hooks || !hooks->guard || !hooks->append) {
        state->stopped = true;
        state->epochs_saved = false;
        state->settled = false;
        state->reason = A23QuietInvalidState;
        return A23QuietInvalidArgument;
    }
    if (state->journal_failed || state->stopped) {
        state->stopped = true;
        state->epochs_saved = false;
        state->settled = false;
        return state->journal_failed ? A23QuietJournalFailed : A23QuietStopped;
    }
    if (state->settled && (!state->started || !state->epochs_saved ||
                           !state->completion_attempted || !state->settled_at))
        return stop_quiet(state, hooks, A23QuietInvalidState);
    if (!state->started) return A23QuietIdle;
    if (!hooks->guard(hooks->context)) return stop_quiet(state, hooks, A23QuietGuardFailure);
    if (!state->epochs_saved) return A23QuietIdle;
    if (state->settled) return A23QuietSettled;
    if (state->completion_attempted) return stop_quiet(state, hooks, A23QuietInvalidState);

    A23CandidateClockResult duration;
    if (state->quiet_start.domain != A23CandidateInjectedDriver) {
        state->clock_status = A23CandidateClockMismatch;
        return stop_quiet(state, hooks, A23QuietClockFailure);
    }
    state->clock_status = state->quiet_start.ticks ?
        A23CandidateClockEvaluate(&state->quiet_start, now, UINT64_C(250000000), UINT64_MAX, &duration) :
        A23CandidateClockInvalidArgument;
    if (state->clock_status != A23CandidateClockOK)
        return stop_quiet(state, hooks, A23QuietClockFailure);
    if (!duration.minimum_met) return A23QuietWaiting;

    state->completion_attempted = true;
    if (!hooks->append(hooks->context, A23QuietCompleteEvent)) {
        state->journal_failed = true;
        state->stopped = true;
        state->epochs_saved = false;
        state->settled = false;
        state->reason = A23QuietJournalFailure;
        return A23QuietJournalFailed;
    }
    if (!hooks->guard(hooks->context)) return stop_quiet(state, hooks, A23QuietGuardFailure);
    state->settled = true;
    state->settled_at = now->ticks;
    return A23QuietSettled;
}

A23CandidateClockStatus A23QuietCandidateDeadline(
    const A23CandidateClockStamp *start, const A23CandidateClockStamp *end,
    uint64_t limit_ns, bool has_arrival, bool *expired)
{
    if (!expired) return A23CandidateClockInvalidArgument;
    *expired = true;
    if (!start || !end || !start->ticks) return A23CandidateClockInvalidArgument;
    A23CandidateClockResult duration;
    const A23CandidateClockStatus status = A23CandidateClockEvaluate(start, end, 0, limit_ns, &duration);
    if (status != A23CandidateClockOK) return status;
    *expired = has_arrival ? !duration.maximum_met : duration.rounded_up_ns >= limit_ns;
    return A23CandidateClockOK;
}
