#ifndef A23_VERSIONED_CLOCK_CANDIDATE_H
#define A23_VERSIONED_CLOCK_CANDIDATE_H
#include <stdatomic.h>
#include "a23_clock_candidate.h"

/* Offline candidate contract:
 * - Init exactly once before publication; retain the store through evaluation.
 * - Every profile write, even ABA/no-op/aborted writes, uses Begin/Finish/Abort.
 * - incarnation identifies this store lifetime; it is an injected declaration.
 * - No resetting generation, bypassing these APIs, or concurrent reinitializing.
 * All shared fields are atomic, using sequential consistency. No retry/spin.
 * This is neither clock provenance nor an enforced boundary against bad writers.
 */
typedef struct {
    _Atomic uint64_t generation;
    _Atomic uint32_t domain,numerator,denominator;
    _Atomic uint64_t clock_instance;
    _Atomic bool poisoned;
    uint64_t incarnation;
} A23VersionedClockStore;
typedef struct {
    A23CandidateClockStamp stamp;
    const A23VersionedClockStore *store_identity;
    uint64_t incarnation,generation;
} A23VersionedClockSample;
typedef enum {
    A23VersionedClockOK=0,A23VersionedClockArgument=1,A23VersionedClockProfile=2,
    A23VersionedClockBusy=3,A23VersionedClockChanged=4,A23VersionedClockPoisoned=5,
    A23VersionedClockExhausted=6,A23VersionedClockReaderFailed=7
} A23VersionedClockStatus;
typedef bool (*A23VersionedClockReader)(void *context,uint64_t *ticks);

A23VersionedClockStatus A23VersionedClockInit(A23VersionedClockStore *,uint64_t incarnation,const A23CandidateClockStamp *profile);
A23VersionedClockStatus A23VersionedClockBegin(A23VersionedClockStore *,uint64_t *ticket);
A23VersionedClockStatus A23VersionedClockFinish(A23VersionedClockStore *,uint64_t ticket,const A23CandidateClockStamp *profile);
A23VersionedClockStatus A23VersionedClockAbort(A23VersionedClockStore *,uint64_t ticket);
A23VersionedClockStatus A23VersionedClockPublish(A23VersionedClockStore *,const A23CandidateClockStamp *profile);
/* Preflight reads no ticks. Capture calls the reader at most once. Failure clears
 * output; a tick0 sample remains arithmetic data, not a driver lifecycle start.
 */
A23VersionedClockStatus A23VersionedClockReadProfile(const A23VersionedClockStore *,A23VersionedClockSample *);
A23VersionedClockStatus A23VersionedClockCapture(const A23VersionedClockStore *,A23VersionedClockReader,void *context,A23VersionedClockSample *);
A23CandidateClockStatus A23VersionedClockEvaluate(const A23VersionedClockSample *,const A23VersionedClockSample *,uint64_t minimum_ns,A23CandidateClockResult *);
#endif
