#include "a23_clock_candidate.h"
#include <inttypes.h>
#include <stdio.h>
#include <string.h>

/* Bounded decimal protocol: twelve uint64 columns per line, single spaces.
 * No fixture argument can name a path or cause a clock/hardware query.
 */
static bool parse_line(const char *line, uint64_t values[12])
{
    const char *p = line;
    for (unsigned i = 0; i < 12; ++i) {
        uint64_t value = 0;
        unsigned digits = 0;
        while (*p >= '0' && *p <= '9') {
            const uint64_t digit = (uint64_t)(*p - '0');
            if (++digits > 20 || value > (UINT64_MAX - digit) / 10) return false;
            value = value * 10 + digit;
            ++p;
        }
        if (!digits || (i < 11 ? *p != ' ' : *p != '\n')) return false;
        ++p;
        values[i] = value;
    }
    return *p == '\0';
}

static int pointer_checks(void)
{
    A23CandidateClockStamp stamp = {1, A23CandidateInjectedDriver, 1, 1, 1};
    A23CandidateClockResult result = {7, true, true, true};
    if (A23CandidateClockEvaluate(NULL, &stamp, 0, 1, &result) != A23CandidateClockInvalidArgument ||
        result.rounded_up_ns || result.minimum_met || result.maximum_met || result.within_interval) return 1;
    result = (A23CandidateClockResult){7, true, true, true};
    if (A23CandidateClockEvaluate(&stamp, NULL, 0, 1, &result) != A23CandidateClockInvalidArgument ||
        result.rounded_up_ns || result.minimum_met || result.maximum_met || result.within_interval) return 1;
    return A23CandidateClockEvaluate(&stamp, &stamp, 0, 1, NULL) == A23CandidateClockInvalidArgument ? 0 : 1;
}

int main(int argc, char **argv)
{
    if (argc == 2 && strcmp(argv[1], "--pointer-checks") == 0) return pointer_checks();
    if (argc != 1) return 2;
    char line[512];
    while (fgets(line, (int)sizeof(line), stdin)) {
        uint64_t v[12];
        if (!parse_line(line, v) || v[1] > 2147483647 || v[6] > 2147483647 ||
            v[3] > UINT32_MAX || v[4] > UINT32_MAX || v[8] > UINT32_MAX || v[9] > UINT32_MAX) return 2;
        const A23CandidateClockStamp begin = {v[0], (A23CandidateClockDomain)v[1], v[2], (uint32_t)v[3], (uint32_t)v[4]};
        const A23CandidateClockStamp end = {v[5], (A23CandidateClockDomain)v[6], v[7], (uint32_t)v[8], (uint32_t)v[9]};
        A23CandidateClockResult result = {7, true, true, true};
        const A23CandidateClockStatus status = A23CandidateClockEvaluate(&begin, &end, v[10], v[11], &result);
        printf("{\"status\":%u,\"rounded_up_ns\":%" PRIu64 ",\"minimum_met\":%s,\"maximum_met\":%s,\"within_interval\":%s}\n",
               (unsigned)status, result.rounded_up_ns, result.minimum_met ? "true" : "false",
               result.maximum_met ? "true" : "false", result.within_interval ? "true" : "false");
    }
    return ferror(stdin) ? 2 : 0;
}
