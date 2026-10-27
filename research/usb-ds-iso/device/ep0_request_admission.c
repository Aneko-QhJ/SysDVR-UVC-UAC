#include "ep0_request_admission.h"
static Ep0AdmissionObservation admission_state;
static bool admission_reject(unsigned reason,bool capacity) {
    if(capacity)ep0_trace_sat_inc(&admission_state.trace_refusals);
    Ep0CandidateGuardReject(reason);return false;
}
static bool admission_usable(void) {
    if(Ep0CandidateStopRequested()) {
        ep0_trace_sat_inc(&admission_state.stop_skips);return false;
    }
    const Ep0TraceOwner *o=Ep0CandidateObservation();
    if(!o->writer || o->stopped || o->joined || !o->processing || o->trace.lifecycle!=1)
        return admission_reject(EP0_BG_OWNER,false);
    if(o->fault)return admission_reject(EP0_BG_FAULT,false);
    if(o->trace.count>EP0_TRACE_CAPACITY || o->trace.dropped || o->trace.invalid)
        return admission_reject(EP0_BG_CAPACITY,true);
    return true;
}
bool Ep0CandidateAdmissionBegin(void) {
    if(!admission_usable())return false;
    if(admission_state.active)return admission_reject(EP0_BG_OWNER,false);
    /* One possible disconnect record outside ready-request handling. */
    if(Ep0CandidateObservation()->trace.count==EP0_TRACE_CAPACITY)return admission_reject(EP0_BG_CAPACITY,true);
    return true;
}
bool Ep0CandidateAdmissionReady(void) {
    if(!admission_usable())return false;
    const Ep0TraceOwner *o=Ep0CandidateObservation();
    if(admission_state.active)return admission_reject(EP0_BG_OWNER,false);
    if(o->trace.count>EP0_TRACE_CAPACITY-EP0_REQUEST_RECORD_RESERVE)return admission_reject(EP0_BG_CAPACITY,true);
    admission_state.before_count=o->trace.count;admission_state.before_dropped=o->trace.dropped;
    admission_state.before_invalid=o->trace.invalid;admission_state.active=true;
    ep0_trace_sat_inc(&admission_state.admitted);return true;
}
void Ep0CandidateAdmissionEnd(void) {
    const Ep0TraceOwner *o=Ep0CandidateObservation();
    if(!admission_state.active) { (void)admission_reject(EP0_BG_OWNER,false);return; }
    admission_state.active=false;
    if(o->trace.count<admission_state.before_count || o->trace.dropped!=admission_state.before_dropped ||
       o->trace.invalid!=admission_state.before_invalid ||
       o->trace.count-admission_state.before_count>EP0_REQUEST_RECORD_RESERVE) {
        ep0_trace_sat_inc(&admission_state.bound_violations);(void)admission_reject(EP0_BG_CAPACITY,true);return;
    }
    uint32_t n=o->trace.count-admission_state.before_count;
    if(n>admission_state.largest_request)admission_state.largest_request=n;
    if(o->fault && !Ep0CandidateStopRequested())Ep0CandidateGuardReject(EP0_BG_FAULT);
}
bool Ep0CandidateAdmissionBurst(const void *iso,size_t n,const void *ack) {
    /* No modifications/posts between these two checks. Both use the total
     * two-identity budget; they do not each consume/reserve two new slots. */
    if(!Ep0CandidateGuardAllow(iso,n,2) || !Ep0CandidateGuardAllow(ack,0,2))return false;
    if(ep0_bg_overlap((uintptr_t)iso,n,(uintptr_t)ack,0))return admission_reject(EP0_BG_OVERLAP,false);
    return true;
}
const Ep0AdmissionObservation *Ep0CandidateAdmissionObservation(void) { return &admission_state; }
