#pragma once
/* Queue-confined passive-discovery policy. No IOKit, SDK, USB or ticket calls.
 * A future adapter must register notifications BEFORE draining the initial
 * iterator, retain selected objects, and prove callback quiescence on close. */
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
enum { A23_W_NEW,A23_W_REGISTERING,A23_W_DRAINING,A23_W_WAITING,
       A23_W_SELECTED,A23_W_HANDED,A23_W_STOPPED };
enum { A23_W_REASON_NONE,A23_W_REASON_CLOCK,A23_W_REASON_TIMEOUT,A23_W_REASON_ORDER,
       A23_W_REASON_REGISTER,A23_W_REASON_EXISTING,A23_W_REASON_AMBIGUOUS,
       A23_W_REASON_DETACHED,A23_W_REASON_INTERRUPTED,A23_W_REASON_EXTRA_ARRIVAL };
typedef struct {
    unsigned phase,reason;
    uint64_t last,deadline,selected_id;
    unsigned handoffs;
} A23PassiveWaitPolicy;
static inline bool a23_wait_stop(A23PassiveWaitPolicy *w,unsigned reason) {
    if(!w || w->phase==A23_W_STOPPED)return false;
    w->phase=A23_W_STOPPED;w->reason=reason;return false;
}
static inline bool a23_wait_clock(A23PassiveWaitPolicy *w,uint64_t now) {
    if(!w || w->phase==A23_W_STOPPED)return false;
    if(w->phase==A23_W_NEW)return a23_wait_stop(w,A23_W_REASON_ORDER);
    if(now<w->last)return a23_wait_stop(w,A23_W_REASON_CLOCK);
    w->last=now;
    /* Waiting deadline ends at handoff. SDK deadlines are a separate clock
     * policy; the passive wait must not silently abort a running transfer. */
    if(w->phase!=A23_W_HANDED && now>=w->deadline)return a23_wait_stop(w,A23_W_REASON_TIMEOUT);
    return true;
}
static inline bool a23_wait_begin(A23PassiveWaitPolicy *w,uint64_t now,uint64_t deadline) {
    if(!w || w->phase!=A23_W_NEW)return false;
    if(deadline<=now)return a23_wait_stop(w,A23_W_REASON_TIMEOUT);
    w->last=now;w->deadline=deadline;w->phase=A23_W_REGISTERING;return true;
}
static inline bool a23_wait_registered(A23PassiveWaitPolicy *w,uint64_t now,bool ok) {
    if(!a23_wait_clock(w,now))return false;
    if(w->phase!=A23_W_REGISTERING)return a23_wait_stop(w,A23_W_REASON_ORDER);
    if(!ok)return a23_wait_stop(w,A23_W_REASON_REGISTER);
    w->phase=A23_W_DRAINING;return true;
}
static inline bool a23_wait_initial_drained(A23PassiveWaitPolicy *w,uint64_t now,size_t existing) {
    if(!a23_wait_clock(w,now))return false;
    if(w->phase!=A23_W_DRAINING)return a23_wait_stop(w,A23_W_REASON_ORDER);
    if(existing)return a23_wait_stop(w,A23_W_REASON_EXISTING);
    w->phase=A23_W_WAITING;return true;
}
static inline bool a23_wait_arrival(A23PassiveWaitPolicy *w,uint64_t now,const uint64_t *ids,size_t n) {
    if(!a23_wait_clock(w,now))return false;
    if(w->phase==A23_W_SELECTED || w->phase==A23_W_HANDED)
        return a23_wait_stop(w,A23_W_REASON_EXTRA_ARRIVAL);
    if(w->phase!=A23_W_WAITING)return a23_wait_stop(w,A23_W_REASON_ORDER);
    if(n!=1 || !ids || !ids[0])return a23_wait_stop(w,A23_W_REASON_AMBIGUOUS);
    w->selected_id=ids[0];w->phase=A23_W_SELECTED;return true;
}
static inline bool a23_wait_handoff(A23PassiveWaitPolicy *w,uint64_t now,uint64_t *id) {
    if(!a23_wait_clock(w,now))return false;
    if(w->phase!=A23_W_SELECTED || !id || w->handoffs)return a23_wait_stop(w,A23_W_REASON_ORDER);
    *id=w->selected_id;w->handoffs=1;w->phase=A23_W_HANDED;return true;
}
