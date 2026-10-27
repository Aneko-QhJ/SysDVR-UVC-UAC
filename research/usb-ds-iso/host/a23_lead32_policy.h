#pragma once
/* Isolated host-window hypothesis. Nominal frame arithmetic, never a wire deadline. */
#include <stdbool.h>
#include <stdint.h>
#define A23_L32_LEAD 32u
#define A23_L32_QUERY_NS UINT64_C(2000000)
#define A23_L32_AGE_NS UINT64_C(4000000)
#define A23_L32_CALL_NS UINT64_C(2000000)
#define A23_L32_GAP_NS UINT64_C(2000000)
#define A23_L32_TRIGGER_AGE_NS UINT64_C(8000000)
#define A23_L32_CONTROL_NS UINT64_C(16000000)
#define A23_L32_TRIGGER_END_NS UINT64_C(24000000)
#define A23_L32_RESERVE_NS UINT64_C(8000000)
_Static_assert(A23_L32_AGE_NS+A23_L32_CALL_NS+A23_L32_GAP_NS==A23_L32_TRIGGER_AGE_NS,"pretrigger budget");
_Static_assert(A23_L32_TRIGGER_AGE_NS+A23_L32_CONTROL_NS==A23_L32_TRIGGER_END_NS,"control budget");
_Static_assert(A23_L32_TRIGGER_END_NS+A23_L32_RESERVE_NS==A23_L32_LEAD*UINT64_C(1000000),"nominal reserve");
static inline bool A23Lead32Admission(uint64_t query,uint64_t age)
{return query<=A23_L32_QUERY_NS && age<=A23_L32_AGE_NS;}
static inline bool A23Lead32Call(uint64_t elapsed) {return elapsed<=A23_L32_CALL_NS;}
static inline bool A23Lead32Trigger(uint64_t gap,uint64_t age)
{return gap<=A23_L32_GAP_NS && age<=A23_L32_TRIGGER_AGE_NS;}
