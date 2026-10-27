#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <assert.h>
#include <stdio.h>
#include "iso_probe_protocol.h"
#include "serial_ring_guard.h"
static IsoProbeBurstContextDiagnostics sample(unsigned slot,unsigned cycle) {
    IsoProbeBurstContextDiagnostics d={0};
    d.magic=ISO_PROBE_BURST_INTERVAL_MAGIC;d.terminal=1;d.completed_bitmap=0xffff;d.actual_sum=3072;
    d.first_virtual_trb=0x100000+(uint64_t)slot*16;
    d.first_control=(1u<<20)|(5u<<10)|cycle;d.frame_select_mfi=16136;d.context_valid=1;
    d.context[0]=0x00010001;d.context[1]=0x0100002e;d.context[4]=0x01000c00;
    for(unsigned i=0;i<2;++i){d.td[i].event[0]=0x100000+((slot+1+2*i)%247)*16;
        d.td[i].event[2]=0x010000c0;d.td[i].event[3]=0x00078005;}
    return d;
}
int main(void) {
    unsigned transitions=0,rejections=0;
    for(unsigned start=0;start<247;++start)for(unsigned initial_cycle=0;initial_cycle<2;++initial_cycle){
        SerialRingState state={0};unsigned slot=start,cycle=initial_cycle;
        for(unsigned seq=1;seq<=16;++seq){IsoProbeBurstContextDiagnostics d=sample(slot,cycle);
            assert(serial_ring_guard(&state,&d,seq));++transitions;
            cycle^=slot+32>=247;slot=(slot+32)%247;}
        assert(state.wraps>=1);
    }
    for(unsigned mode=0;mode<10;++mode){
        SerialRingState state={0};IsoProbeBurstContextDiagnostics first=sample(224,1);assert(serial_ring_guard(&state,&first,1));
        SerialRingState before=state;IsoProbeBurstContextDiagnostics next=sample(9,0);
        unsigned seq=2;
        if(mode==0)next.td[0].event[0]+=16;
        if(mode==1)next.td[1].event[2]=0x010000bf;
        if(mode==2)next=sample(8,0);
        if(mode==3)next=sample(9,1);
        if(mode==4)seq=3;
        if(mode==5)next.context_valid=0;
        if(mode==6)next.context[1]^=1u<<16;
        if(mode==7)next.first_virtual_trb+=4096;
        if(mode==8)next.completed_bitmap=0x7fff;
        if(mode==9)next.frame_select_mfi=0;
        assert(!serial_ring_guard(&state,&next,seq));assert(memcmp(&before,&state,sizeof(state))==0);++rejections;
    }
    printf("%u valid transitions across all ring starts/two cycles; %u invalid cases reject without progression\n",transitions,rejections);
}
