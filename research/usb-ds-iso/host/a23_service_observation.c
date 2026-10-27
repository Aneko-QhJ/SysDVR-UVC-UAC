#include "a23_service_observation.h"
#include <string.h>

static void fail(A23ServiceObservation *s,A23ServiceFailure reason) {
    if(s->stage!=A23ServiceFailed){s->stage=A23ServiceFailed;s->failure=reason;}
}
void a23_service_init(A23ServiceObservation *s) {memset(s,0,sizeof(*s));}
bool a23_service_begin(A23ServiceObservation *s,uint64_t now) {
    if(s->stage!=A23ServiceIdle){fail(s,A23ServiceRestart);return false;}
    if(!now || now>UINT64_MAX-A23_SERVICE_DURATION_NS){fail(s,A23ServiceClock);return false;}
    s->stage=A23ServiceRunning;s->start_ns=s->last_ns=now;
    s->samples[0]=now;s->count=1;return true;
}
A23ServiceStage a23_service_tick(A23ServiceObservation *s,uint64_t now) {
    if(s->stage!=A23ServiceRunning)return s->stage;
    if(!now || now<=s->last_ns){fail(s,A23ServiceClock);return s->stage;}
    if(s->count==A23_SERVICE_MAX_SAMPLES){fail(s,A23ServiceCapacity);return s->stage;}
    uint64_t gap=now-s->last_ns;
    s->samples[s->count++]=now;s->last_ns=now;
    if(gap>s->max_gap_ns)s->max_gap_ns=gap;
    // Check the entire last interval before elapsed-time acceptance, including
    // an interval that ends after the nominal observation deadline.
    if(gap>A23_SERVICE_MAX_GAP_NS){s->end_ns=now;fail(s,A23ServiceGap);}
    else if(now-s->start_ns>=A23_SERVICE_DURATION_NS){s->end_ns=now;s->stage=A23ServicePassed;}
    return s->stage;
}
void a23_service_fault(A23ServiceObservation *s) {fail(s,A23ServiceFault);}
