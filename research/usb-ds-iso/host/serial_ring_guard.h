#pragma once
/* Post-completion checks only; never writes the device ring or normalizes errors. */
typedef struct {
    bool initialized;
    uint64_t page;
    unsigned slot, cycle, sequence, wraps;
} SerialRingState;

static bool serial_ring_guard(SerialRingState *state,
                             const IsoProbeBurstContextDiagnostics *diag,
                             unsigned sequence) {
    uint64_t first=diag->first_virtual_trb, page=first & ~UINT64_C(4095);
    unsigned slot=(unsigned)(first & 4095)/16, cycle=diag->first_control & 1;
    if (!first || (first & 15) || slot>=247 || sequence<1 || sequence>16 ||
        diag->magic!=ISO_PROBE_BURST_INTERVAL_MAGIC || diag->terminal!=1 ||
        diag->completed_bitmap!=0xffff || diag->actual_sum!=3072 ||
        ((diag->first_control>>10)&63)!=5 || (diag->first_control>>31) ||
        diag->context_valid!=1 || diag->frame_select_mfi>=16384 ||
        ((diag->first_control>>20)&2047)!=(((diag->frame_select_mfi>>3)+32)&2047) ||
        (diag->context[0]&7)!=1 || ((diag->context[0]>>8)&3)!=0 ||
        ((diag->context[0]>>16)&255)!=1 || ((diag->context[1]>>3)&7)!=5 ||
        ((diag->context[1]>>8)&255)!=0 || (diag->context[1]>>16)!=256 ||
        (diag->context[4]>>16)!=256) return false;
    for (unsigned i=0;i<2;++i) {
        const IsoProbeAuditEvent *event=&diag->td[i];
        uint64_t tag=(uint64_t)event->event[0]|(uint64_t)event->event[1]<<32;
        uint32_t flags=event->event[3];
        if (((flags>>10)&63)!=32 || !(flags&4) || ((flags>>16)&31)!=7 ||
            (event->event[2]>>24)!=1 || (event->event[2]&0xffffff)!=192 ||
            tag!=page+(uint64_t)((slot+1+2*i)%247)*16) return false;
    }
    unsigned wraps=state->wraps;
    if (state->initialized) {
        unsigned crossing=state->slot+32>=247;
        if (sequence!=state->sequence+1 || page!=state->page ||
            slot!=(state->slot+32)%247 || cycle!=(state->cycle^crossing)) return false;
        wraps+=crossing;
    } else if (sequence!=1) return false;
    *state=(SerialRingState){true,page,slot,cycle,sequence,wraps};
    return true;
}
