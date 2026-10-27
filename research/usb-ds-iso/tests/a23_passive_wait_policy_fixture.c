/* Actual policy header; all notifications/identities/clocks are injected. */
#include <assert.h>
#include <stdio.h>
#include "a23_passive_wait_policy.h"
static unsigned cases;
static A23PassiveWaitPolicy waiting(void) {
    A23PassiveWaitPolicy w={0};assert(a23_wait_begin(&w,100,200));
    assert(a23_wait_registered(&w,101,true));assert(a23_wait_initial_drained(&w,102,0));return w;
}
int main(void) {
    for(unsigned at=102;at<=202;at++)for(unsigned n=0;n<=3;n++) {
        A23PassiveWaitPolicy w=waiting();uint64_t ids[3]={42,43,44},out=777;
        bool selected=a23_wait_arrival(&w,at,ids,n);
        assert(selected==(n==1 && at<200));
        bool handed=a23_wait_handoff(&w,at,&out);assert(handed==selected);
        assert(out==(handed?42:777));assert(w.handoffs==(handed?1u:0u));
        assert(!a23_wait_handoff(&w,at,&out));assert(w.handoffs<=1);
        (void)a23_wait_arrival(&w,at,ids,1);assert(!a23_wait_handoff(&w,at,&out));cases++;
    }
    for(unsigned n=1;n<=32;n++) {
        A23PassiveWaitPolicy w={0};assert(a23_wait_begin(&w,100,200));
        assert(a23_wait_registered(&w,101,true));assert(!a23_wait_initial_drained(&w,102,n));
        assert(w.reason==A23_W_REASON_EXISTING);cases++;
    }
    for(unsigned reason=A23_W_REASON_DETACHED;reason<=A23_W_REASON_INTERRUPTED;reason++) {
        A23PassiveWaitPolicy w=waiting();uint64_t id=42,out=0;
        assert(a23_wait_arrival(&w,103,&id,1));(void)a23_wait_stop(&w,reason);
        assert(!a23_wait_handoff(&w,104,&out) && out==0);
        assert(!a23_wait_begin(&w,105,205));assert(!a23_wait_arrival(&w,106,&id,1));cases++;
    }
    A23PassiveWaitPolicy w=waiting();uint64_t id=0,out=0;
    assert(!a23_wait_arrival(&w,103,&id,1));cases++;
    w=waiting();assert(!a23_wait_arrival(&w,103,NULL,1));cases++;
    w=waiting();id=UINT64_MAX;assert(a23_wait_arrival(&w,103,&id,1));
    assert(!a23_wait_handoff(&w,200,&out) && out==0);cases++;
    w=waiting();assert(!a23_wait_clock(&w,101) && w.reason==A23_W_REASON_CLOCK);cases++;
    w=(A23PassiveWaitPolicy){0};assert(!a23_wait_begin(&w,100,100));cases++;
    w=(A23PassiveWaitPolicy){0};assert(a23_wait_begin(&w,100,200));
    assert(!a23_wait_registered(&w,101,false));cases++;
    w=(A23PassiveWaitPolicy){0};assert(a23_wait_begin(&w,100,200));
    assert(!a23_wait_initial_drained(&w,101,0));cases++;
    w=waiting();id=42;assert(a23_wait_arrival(&w,103,&id,1));
    assert(a23_wait_handoff(&w,104,&out));assert(a23_wait_clock(&w,1000000));cases++;
    w=(A23PassiveWaitPolicy){0};assert(!a23_wait_arrival(&w,100,&id,1));
    assert(!a23_wait_begin(&w,101,200));cases++;
    printf("{\"policy_cases\":%u,\"maximum_handoffs\":1,\"native_iokit_adapter_implemented\":false,"
        "\"usb_requests\":0,\"ticket_mutations\":0,\"injected_notifications\":true}\n",cases);
}
