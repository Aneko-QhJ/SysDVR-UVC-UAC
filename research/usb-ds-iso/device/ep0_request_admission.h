#pragma once
/* Isolated offline candidate. A ready setup consumes at most 17 trace records
 * under the bound A23 source. Quiet polls consume no record. No new USB calls. */
#include "ep0_candidate_guard.h"
#define EP0_REQUEST_RECORD_RESERVE 17u
typedef struct {
    uint32_t admitted,trace_refusals,stop_skips,bound_violations,largest_request;
    uint32_t before_count,before_dropped,before_invalid;
    bool active;
} Ep0AdmissionObservation;
bool Ep0CandidateAdmissionBegin(void);
bool Ep0CandidateAdmissionReady(void);
void Ep0CandidateAdmissionEnd(void);
bool Ep0CandidateAdmissionBurst(const void *iso,size_t n,const void *ack);
const Ep0AdmissionObservation *Ep0CandidateAdmissionObservation(void);
void Ep0CandidateGuardReject(unsigned reason); /* generated old adapter copy only */
