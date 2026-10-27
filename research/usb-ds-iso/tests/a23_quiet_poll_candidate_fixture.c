#include "a23_quiet_poll_candidate.h"
#include <inttypes.h>
#include <stdio.h>
#include <string.h>

static bool parse(const char *line, uint64_t values[43], unsigned *count)
{
    const char *p = line;
    *count = 0;
    for (;;) {
        if (*count == 43) return false;
        uint64_t value = 0;
        unsigned digits = 0;
        while (*p >= '0' && *p <= '9') {
            const uint64_t digit = (uint64_t)(*p - '0');
            if (++digits > 20 || value > (UINT64_MAX - digit) / 10) return false;
            value = value * 10 + digit;
            ++p;
        }
        if (!digits) return false;
        values[(*count)++] = value;
        if (*p == '\n') return p[1] == '\0';
        if (*p++ != ' ') return false;
    }
}

static bool stamp(const uint64_t *v, A23CandidateClockStamp *out)
{
    if (v[1] > 2147483647 || v[3] > UINT32_MAX || v[4] > UINT32_MAX) return false;
    *out = (A23CandidateClockStamp){v[0], (A23CandidateClockDomain)v[1], v[2], (uint32_t)v[3], (uint32_t)v[4]};
    return true;
}

typedef struct {
    bool before, after, complete_ok, stop_ok;
    unsigned local_guards, guards, complete_attempts, complete_successes, stop_attempts, stop_successes;
    uint64_t trace;
} Mock;

static bool guard(void *context)
{
    Mock *mock = context;
    ++mock->guards;
    const bool ok = mock->local_guards++ ? mock->after : mock->before;
    mock->trace = mock->trace * 8 + (ok ? 1U : 2U);
    return ok;
}
static bool append(void *context, A23QuietCandidateEvent event)
{
    Mock *mock = context;
    if (event == A23QuietCompleteEvent) {
        ++mock->complete_attempts;
        if (mock->complete_ok) ++mock->complete_successes;
        mock->trace = mock->trace * 8 + (mock->complete_ok ? 3U : 4U);
        return mock->complete_ok;
    }
    ++mock->stop_attempts;
    if (mock->stop_ok) ++mock->stop_successes;
    mock->trace = mock->trace * 8 + (mock->stop_ok ? 5U : 6U);
    return mock->stop_ok;
}

static unsigned flags(const A23QuietCandidateState *s)
{
    return (s->started ? 1U : 0U) | (s->epochs_saved ? 2U : 0U) | (s->stopped ? 4U : 0U) |
           (s->journal_failed ? 8U : 0U) | (s->settled ? 16U : 0U) | (s->completion_attempted ? 32U : 0U);
}

static int pointers(void)
{
    A23QuietCandidateState s = {0};
    A23CandidateClockStamp t = {1, A23CandidateInjectedDriver, 1, 1, 1};
    Mock m = {0};
    A23QuietCandidateHooks h = {&m, guard, append};
    if (A23QuietCandidatePoll(NULL, &t, &h) != A23QuietInvalidArgument) return 1;
    s.started = s.epochs_saved = s.settled = true;
    if (A23QuietCandidatePoll(&s, NULL, &h) != A23QuietInvalidArgument || s.settled || s.epochs_saved || !s.stopped) return 1;
    if (A23QuietCandidatePoll(&s, &t, NULL) != A23QuietInvalidArgument) return 1;
    h.guard = NULL;
    if (A23QuietCandidatePoll(&s, &t, &h) != A23QuietInvalidArgument) return 1;
    h.guard = guard; h.append = NULL;
    if (A23QuietCandidatePoll(&s, &t, &h) != A23QuietInvalidArgument) return 1;
    bool expired = false;
    if (A23QuietCandidateDeadline(NULL, &t, 1, true, &expired) != A23CandidateClockInvalidArgument || !expired) return 1;
    expired = false;
    if (A23QuietCandidateDeadline(&t, NULL, 1, true, &expired) != A23CandidateClockInvalidArgument || !expired) return 1;
    return A23QuietCandidateDeadline(&t, &t, 1, true, NULL) == A23CandidateClockInvalidArgument ? 0 : 1;
}

int main(int argc, char **argv)
{
    if (argc == 2 && strcmp(argv[1], "--pointer-checks") == 0) return pointers();
    const bool deadlines = argc == 2 && strcmp(argv[1], "--deadlines") == 0;
    if (argc != 1 && !deadlines) return 2;
    char line[2048];
    while (fgets(line, (int)sizeof(line), stdin)) {
        uint64_t v[43]; unsigned count;
        if (!parse(line, v, &count)) return 2;
        if (deadlines) {
            A23CandidateClockStamp start, end;
            if (count != 12 || !stamp(v, &start) || !stamp(v + 5, &end) || v[11] > 1) return 2;
            bool expired = false;
            const A23CandidateClockStatus status = A23QuietCandidateDeadline(&start, &end, v[10], v[11] != 0, &expired);
            printf("{\"clock_status\":%u,\"expired\":%s}\n", (unsigned)status, expired ? "true" : "false");
            continue;
        }
        A23QuietCandidateState state = {0};
        if (count < 7 || v[0] > 63 || v[6] < 1 || v[6] > 4 || count != 7 + 9 * v[6] || !stamp(v + 1, &state.quiet_start)) return 2;
        state.started = (v[0] & 1) != 0; state.epochs_saved = (v[0] & 2) != 0;
        state.stopped = (v[0] & 4) != 0; state.journal_failed = (v[0] & 8) != 0;
        state.settled = (v[0] & 16) != 0; state.completion_attempted = (v[0] & 32) != 0;
        /* Validate the complete record before emitting any partial output. */
        for (unsigned i = 0; i < (unsigned)v[6]; ++i) {
            const uint64_t *step = v + 7 + i * 9;
            A23CandidateClockStamp now;
            if (!stamp(step, &now) || step[5] > 1 || step[6] > 1 || step[7] > 1 || step[8] > 1) return 2;
        }
        Mock mock = {0}; A23QuietCandidateHooks hooks = {&mock, guard, append};
        printf("{\"steps\":[");
        for (unsigned i = 0; i < (unsigned)v[6]; ++i) {
            const uint64_t *step = v + 7 + i * 9;
            A23CandidateClockStamp now; (void)stamp(step, &now);
            mock.local_guards = 0; mock.before = step[5] != 0; mock.after = step[6] != 0;
            mock.complete_ok = step[7] != 0; mock.stop_ok = step[8] != 0;
            const A23QuietCandidatePollStatus status = A23QuietCandidatePoll(&state, &now, &hooks);
            printf("%s{\"poll_status\":%u,\"flags\":%u,\"settled_at\":%" PRIu64 ",\"reason\":%u,\"clock_status\":%u,"
                   "\"guard_calls\":%u,\"complete_attempts\":%u,\"complete_successes\":%u,\"stop_attempts\":%u,\"stop_successes\":%u,\"trace\":%" PRIu64 "}",
                   i ? "," : "", (unsigned)status, flags(&state), state.settled_at, (unsigned)state.reason,
                   (unsigned)state.clock_status, mock.guards, mock.complete_attempts, mock.complete_successes, mock.stop_attempts, mock.stop_successes, mock.trace);
        }
        puts("]}");
    }
    return ferror(stdin) ? 2 : 0;
}
