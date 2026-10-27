#include "ep0_candidate.h"
#include "ep0_candidate_capture.h"
#include <stdatomic.h>

static Ep0TraceOwner storage;
static uint32_t request_counter,request_ids[4];
static atomic_bool stop_requested;
static uint8_t exported[EP0_CAPTURE_MAX],recipe_digest[32];
static size_t exported_size;

bool Ep0CandidateStart(uint64_t writer,uint64_t frequency,uint64_t start,
                       const uint8_t boot[16],const uint8_t session[16],const uint8_t recipe[32]) {
    if(!recipe || !ep0_trace_nonzero(recipe,32) || !ep0_owner_init(&storage,writer,frequency,start,boot,session))return false;
    memcpy(recipe_digest,recipe,32);return true;
}
void Ep0CandidateRequestStop(void) { atomic_store_explicit(&stop_requested,true,memory_order_release); }
bool Ep0CandidateStopRequested(void) { return atomic_load_explicit(&stop_requested,memory_order_acquire); }
bool Ep0CandidateEnter(void) { return ep0_owner_enter(&storage,storage.writer); }
void Ep0CandidateLeave(void) { (void)ep0_owner_leave(&storage,storage.writer); }
bool Ep0CandidateStop(uint64_t at) {
    if(!Ep0CandidateStopRequested())return false;
    if(storage.trace.lifecycle==1 && !ep0_owner_freeze(&storage,storage.writer,at,EP0_TRACE_STOPPED))return false;
    return ep0_owner_stop(&storage,storage.writer);
}
bool Ep0CandidateFinish(uint64_t exporter,uint32_t actual_join_result) {
    if(!ep0_owner_handoff(&storage,exporter,actual_join_result))return false;
    exported_size=ep0_candidate_capture(&storage,exporter,recipe_digest,exported,sizeof(exported));
    return exported_size!=0;
}
const uint8_t *Ep0CandidateBytes(size_t *size) {
    if(size)*size=exported_size;
    return exported_size ? exported : NULL;
}
const Ep0TraceOwner *Ep0CandidateObservation(void) { return &storage; }
void Ep0CandidateObserveIsoOwnership(uint32_t state,uint32_t id) {
    if(!ep0_owner_writer(&storage,storage.writer))return;
    if(state!=1 && state!=4)return; /* Frozen A23 PENDING / RETAINED. */
    for(uint32_t i=0;i<storage.used;i++)
        if(storage.urbs[i].channel==8 && storage.urbs[i].id==id && storage.urbs[i].active)return;
    storage.fault=1; /* A pending ISO buffer was not observed by this session. */
}
void Ep0CandidateObservePost(unsigned channel,uint32_t rc,bool id_valid,uint32_t id) {
    (void)ep0_owner_post(&storage,storage.writer,channel,rc,id_valid,id);
}
void Ep0CandidateObserveReports(unsigned channel,Result rc,const UsbDsReportData *r) {
    if(!ep0_owner_writer(&storage,storage.writer))return;
    if(rc) { (void)ep0_owner_reports(&storage,storage.writer,channel,rc,NULL,0);return; }
    if(!r || r->report_count>8) {
        (void)ep0_owner_reports(&storage,storage.writer,channel,0,NULL,r ? r->report_count : 1);return;
    }
    Ep0OwnerReport entries[8];
    for(uint32_t i=0;i<r->report_count;i++)entries[i]=(Ep0OwnerReport){r->report[i].id,r->report[i].urb_status};
    (void)ep0_owner_reports(&storage,storage.writer,channel,0,entries,r->report_count);
}
void trace_request(UsbDsInterface *iface) {
    if(!ep0_owner_writer(&storage,storage.writer))return;
    if(!iface || iface->interface_index>=4 || request_counter==UINT32_MAX) {
        storage.fault=1;return;
    }
    request_ids[iface->interface_index]=++request_counter;
}
void trace_poll(UsbDsInterface *iface,uint32_t result) {
    if(!ep0_owner_writer(&storage,storage.writer))return;
    if(!iface || iface->interface_index>=4) { storage.fault=1;return; }
    (void)ep0_trace_poll(&storage.trace,iface->interface_index,result);
}
void trace_emit(uint16_t stage,UsbDsInterface *iface,uint32_t result,uint32_t arg0,uint32_t arg1,
                uint8_t flags,const void *setup,uint64_t begin,uint64_t end) {
    if(!ep0_owner_writer(&storage,storage.writer))return;
    unsigned index=iface ? iface->interface_index : 255;
    if(iface && index>=4) { storage.fault=1;return; }
    Ep0TraceRecord r={.begin=begin,.end=end,.result=result,.arg0=arg0,.arg1=arg1,
        .stage=stage,.interface_index=(uint8_t)index,.flags=flags,
        .request_id=iface ? request_ids[index] : 0};
    if(setup) { memcpy(r.setup,setup,8);r.flags|=EP0_TRACE_SETUP_VALID; }
    (void)ep0_trace_append(&storage.trace,&r);
}
