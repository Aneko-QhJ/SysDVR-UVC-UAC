#ifndef A23_SERVICE_OBSERVATION_H
#define A23_SERVICE_OBSERVATION_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

// Isolated local queue-service diagnostic. No receiver adopts this policy.
// These are explicit candidate limits, not USB timing or SDK drain guarantees.
#define A23_SERVICE_DURATION_NS UINT64_C(250000000)
#define A23_SERVICE_MAX_GAP_NS UINT64_C(32000000)
#define A23_SERVICE_MAX_SAMPLES 512u
typedef enum { A23ServiceIdle, A23ServiceRunning, A23ServicePassed,
    A23ServiceFailed } A23ServiceStage;
typedef enum { A23ServiceNoFailure, A23ServiceClock, A23ServiceGap,
    A23ServiceCapacity, A23ServiceFault, A23ServiceRestart } A23ServiceFailure;
typedef struct {
    uint64_t samples[A23_SERVICE_MAX_SAMPLES];
    uint64_t start_ns,last_ns,end_ns,max_gap_ns;
    size_t count;
    A23ServiceStage stage;
    A23ServiceFailure failure;
} A23ServiceObservation;
// Caller owns the state on one serial queue. Init is for a fresh session only;
// restarting/reinitializing an unsuccessful window is not an approved retry.
void a23_service_init(A23ServiceObservation *state);
bool a23_service_begin(A23ServiceObservation *state,uint64_t now_ns);
A23ServiceStage a23_service_tick(A23ServiceObservation *state,uint64_t now_ns);
void a23_service_fault(A23ServiceObservation *state);
#endif
