/* Supplied bytes only. No file service, USB, worker joins or provenance. */
#include "ep0_lifecycle_capsule.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
static uint8_t disk[EP0_LCP_MAX];
static uint32_t save(void *unused,size_t offset,const void *data,size_t n) {
    (void)unused;assert(offset+n<=sizeof(disk));memcpy(disk+offset,data,n);return 0;
}
int main(int argc,char **argv) {
    assert(argc==3);uint8_t recipe[32]={3},nonce[16]={3},context[32]={1};context[16]=2;
    Ep0LifecycleCapsule c={0};assert(ep0_lcp_init(&c,NULL,save,22,1000,1,nonce,recipe));
    unsigned stages[]={EP0_L_PREPARED,EP0_L_USB_INIT_CALL,EP0_L_USB_INIT_RESULT,EP0_L_QUIET_ENTER,
        EP0_L_MAIN_LOOP_LEFT,EP0_L_CLEANUP_RESULT,EP0_L_VIDEO_JOIN_CALL,EP0_L_VIDEO_JOIN_RESULT,
        EP0_L_AUDIO_JOIN_CALL,EP0_L_AUDIO_JOIN_RESULT,EP0_L_EXPORTER_RESULT,EP0_L_CONTEXT,EP0_L_RETAIN};
    unsigned count=(unsigned)strtoul(argv[1],NULL,10);assert(count<=sizeof(stages)/sizeof(stages[0]));
    for(unsigned i=0;i<count;i++)assert(ep0_lcp_note(&c,22,stages[i],1000+i,0,0,0,stages[i]==EP0_L_CONTEXT?context:NULL));
    FILE *f=fopen(argv[2],"wbx");assert(f);assert(fwrite(disk,1,sizeof(disk),f)==sizeof(disk));assert(!fclose(f));
    return 0;
}
