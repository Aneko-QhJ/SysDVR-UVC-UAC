#pragma once
#include "ep0_candidate.h"
#include "ep0_buffer_guard.h"
#define EP0_GUARD_RESULT MAKERESULT(Module_Libnx,LibnxError_BadInput)
typedef struct { uint32_t denials,last_reason; } Ep0GuardObservation;
bool Ep0CandidateGuardAllow(const void *buffer,size_t n,unsigned reserve);
void Ep0CandidateGuardPost(unsigned channel,uint32_t result,bool id_valid,uint32_t id,const void *buffer,size_t n);
const Ep0GuardObservation *Ep0CandidateGuardObservation(void);
void Ep0CandidateGuardFault(void); /* defined ONLY in the generated runtime copy */
