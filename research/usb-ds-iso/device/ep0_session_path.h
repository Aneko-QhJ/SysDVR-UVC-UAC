#pragma once
/* Exact REL1 path, no format interpreter; output untouched on rejection. */
#include "ep0_startup_journal.h"
#define EP0_SESSION_PATH_BYTES 82u
static inline bool ep0_session_path(char *out,size_t cap,const uint8_t boot[16],const uint8_t session[16]) {
    if(!out || !boot || !session || cap<EP0_SESSION_PATH_BYTES ||
       !ep0_init_range((uintptr_t)out,EP0_SESSION_PATH_BYTES) ||
       !ep0_init_range((uintptr_t)boot,16) || !ep0_init_range((uintptr_t)session,16) ||
       ep0_init_overlap((uintptr_t)out,EP0_SESSION_PATH_BYTES,(uintptr_t)boot,16) ||
       ep0_init_overlap((uintptr_t)out,EP0_SESSION_PATH_BYTES,(uintptr_t)session,16) ||
       !ep0_trace_nonzero(boot,16) || !ep0_trace_nonzero(session,16))return false;
    static const char hex[]="0123456789abcdef";
    memcpy(out,"/ep0-",5);
    for(unsigned i=0;i<32;i++) {
        uint8_t x=i<16 ? boot[i]:session[i-16];out[5+2*i]=hex[x>>4];out[6+2*i]=hex[x&15];
    }
    memcpy(out+69,".session.bin",13);return true;
}
