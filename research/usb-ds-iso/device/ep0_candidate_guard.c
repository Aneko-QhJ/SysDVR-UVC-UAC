#include "ep0_candidate_guard.h"
static Ep0BufferSpan spans[EP0_OWNER_SLOTS];
static Ep0GuardObservation observation;
static bool reject(unsigned reason) {
    ep0_trace_sat_inc(&observation.denials);observation.last_reason=reason;
    Ep0CandidateGuardFault();return false;
}
bool Ep0CandidateGuardAllow(const void *buffer,size_t n,unsigned reserve) {
    unsigned reason=ep0_bg_allow(Ep0CandidateObservation(),spans,(uintptr_t)buffer,n,reserve);
    return reason==EP0_BG_OK || reject(reason);
}
void Ep0CandidateGuardPost(unsigned channel,uint32_t result,bool id_valid,uint32_t id,const void *buffer,size_t n) {
    const Ep0TraceOwner *o=Ep0CandidateObservation();
    if(result || !id_valid || o->fault || !o->used || o->used>EP0_OWNER_SLOTS || !ep0_bg_range((uintptr_t)buffer,n)) {
        (void)reject(EP0_BG_UNTRACKED);return;
    }
    uint32_t index=o->used-1;const Ep0OwnedUrb *u=&o->urbs[index];
    if(spans[index].known || u->id!=id || u->channel!=channel || !u->active) {
        (void)reject(EP0_BG_UNTRACKED);return;
    }
    spans[index]=(Ep0BufferSpan){(uintptr_t)buffer,n,id,(uint8_t)channel,1};
}
const Ep0GuardObservation *Ep0CandidateGuardObservation(void) { return &observation; }
