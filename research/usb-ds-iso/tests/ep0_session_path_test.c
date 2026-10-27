#include <assert.h>
#include <stdio.h>
#include "research/usb-ds-iso/device/ep0_session_path.h"
static void untouched(const char *p,size_t n) { for(size_t i=0;i<n;i++)assert((uint8_t)p[i]==0xa5); }
int main(void) {
    uint8_t boot[16],session[16],zero[16]={0};char out[96],old[96];unsigned cases=0;
    for(unsigned n=0;n<256;n++) {
        for(unsigned i=0;i<16;i++) { boot[i]=(uint8_t)(n+i);session[i]=(uint8_t)(255-n-i); }
        memset(out,0xa5,sizeof(out));assert(ep0_session_path(out,82,boot,session));assert(strlen(out)==81);untouched(out+82,sizeof(out)-82);
        char nonce[65];for(unsigned i=0;i<32;i++)snprintf(nonce+2*i,3,"%02x",i<16 ? boot[i]:session[i-16]);
        snprintf(old,sizeof(old),"/ep0-%s.session.bin",nonce);assert(!memcmp(out,old,82));cases++;
    }
    memset(out,0xa5,sizeof(out));assert(!ep0_session_path(out,81,boot,session));untouched(out,sizeof(out));cases++;
    assert(!ep0_session_path(out,sizeof(out),zero,session));untouched(out,sizeof(out));cases++;
    assert(!ep0_session_path(out,sizeof(out),boot,zero));untouched(out,sizeof(out));cases++;
    assert(!ep0_session_path(out,sizeof(out),NULL,session));untouched(out,sizeof(out));cases++;
    assert(!ep0_session_path(out,sizeof(out),(void*)out,session));untouched(out,sizeof(out));cases++;
    assert(!ep0_session_path(out,sizeof(out),boot,(void*)(out+66)));untouched(out,sizeof(out));cases++;
    printf("{\"passed\":true,\"cases\":%u,\"path_bytes\":82,\"same_legacy_path\":true,\"output_unchanged_on_rejection\":true}\n",cases);
}
