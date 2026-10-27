#pragma once
/* Isolated offline-build candidate. Not a production header or capture permit.
 * Native fixtures supply the same USB report ABI before including this header. */
#ifndef EP0_CANDIDATE_NATIVE
#include <switch.h>
#endif
#include "ep0_trace_owner.h"

bool Ep0CandidateStart(uint64_t writer,uint64_t frequency,uint64_t start,
                       const uint8_t boot[16],const uint8_t session[16],const uint8_t recipe[32]);
void Ep0CandidateRequestStop(void); /* explicit local caller; no USB command */
bool Ep0CandidateStopRequested(void);
bool Ep0CandidateEnter(void);
void Ep0CandidateLeave(void);
bool Ep0CandidateStop(uint64_t at);
bool Ep0CandidateFinish(uint64_t exporter,uint32_t actual_join_result);
const uint8_t *Ep0CandidateBytes(size_t *size);
const Ep0TraceOwner *Ep0CandidateObservation(void); /* after join, or native test */
void Ep0CandidateObservePost(unsigned channel,uint32_t rc,bool id_valid,uint32_t id);
void Ep0CandidateObserveReports(unsigned channel,Result rc,const UsbDsReportData *r);
void Ep0CandidateObserveIsoOwnership(uint32_t state,uint32_t id);
void trace_request(UsbDsInterface *iface);
void trace_poll(UsbDsInterface *iface,uint32_t result);
void trace_emit(uint16_t stage,UsbDsInterface *iface,uint32_t result,uint32_t arg0,uint32_t arg1,
                uint8_t flags,const void *setup,uint64_t begin,uint64_t end);
