#include <assert.h>
#include <setjmp.h>
#include <stdio.h>
#include <string.h>
#include <stdint.h>
#define EP0_CANDIDATE_NATIVE
#define CUR_THREAD_HANDLE 0
static const char *scenario;static unsigned queries;static jmp_buf interrupted;
static uint32_t svcGetThreadId(uint64_t *id,unsigned handle) {
    (void)handle;queries++;*id=!strcmp(scenario,"zero-id") ? 0:11;
    if(!strcmp(scenario,"interrupted"))longjmp(interrupted,1);
    return !strcmp(scenario,"identity-error") ? 97:0;
}
#include "research/usb-ds-iso/device/ep0_startup_runtime.c"
int main(int argc,char **argv) {
    assert(argc==3);scenario=argv[1];uint8_t recipe[32]={3},bytes[EP0_INIT_MAX];memset(bytes,0xa5,sizeof(bytes));
    if(!strcmp(scenario,"unattempted")) {
        assert(!Ep0StartupSnapshot(bytes,sizeof(bytes)) && !queries && !Ep0StartupStatus());
        for(unsigned i=0;i<sizeof(bytes);i++)assert(bytes[i]==0xa5);
    } else {
        bool enabled=false;
        if(!setjmp(interrupted))enabled=Ep0StartupBegin(recipe);
        bool failed=!strcmp(scenario,"identity-error") || !strcmp(scenario,"zero-id") || !strcmp(scenario,"interrupted");
        assert(enabled!=failed && queries==1);assert(!Ep0StartupBegin(recipe) && queries==1);
        if(failed) {
            assert(Ep0StartupStatus()==(!strcmp(scenario,"interrupted") ? 1:3));
            assert(!Ep0StartupSnapshot(bytes,sizeof(bytes)) && !Ep0StartupSeal());
            Ep0StartupCall(EP0_I_FS_INIT);Ep0StartupResult(EP0_I_FS_INIT,0);Ep0StartupFatal(82);
            assert(!Ep0StartupSnapshot(bytes,sizeof(bytes)));for(unsigned i=0;i<sizeof(bytes);i++)assert(bytes[i]==0xa5);
        } else {
            int video=0,audio=0,unknown=0;Ep0StartupBindThreads(NULL,NULL);assert(!Ep0StartupCreateStep(NULL));
            Ep0StartupBindThreads(&video,&video);assert(!Ep0StartupCreateStep(&video));
            Ep0StartupBindThreads(&video,&audio);Ep0StartupBindThreads(&unknown,&audio);
            assert(Ep0StartupCreateStep(&video)==EP0_I_VIDEO_CREATE && Ep0StartupStartStep(&audio)==EP0_I_AUDIO_START);
            assert(!Ep0StartupCreateStep(&unknown));
            if(!strcmp(scenario,"overflow")) {
                for(unsigned i=0;i<32;i++) { Ep0StartupCall(EP0_I_FS_INIT);Ep0StartupResult(EP0_I_FS_INIT,0); }
                Ep0StartupCall(EP0_I_FS_INIT);
            } else {
                Ep0StartupCall(EP0_I_VIDEO_START);Ep0StartupResult(EP0_I_VIDEO_START,82);
                if(!strcmp(scenario,"fatal"))Ep0StartupFatal(82);
            }
            if(strcmp(scenario,"fatal"))assert(Ep0StartupSeal());
            size_t n=Ep0StartupSnapshot(bytes,sizeof(bytes));assert(n);uint8_t before[EP0_INIT_MAX];memcpy(before,bytes,n);
            Ep0StartupCall(EP0_I_FS_INIT);Ep0StartupResult(EP0_I_FS_INIT,97);Ep0StartupFatal(82);
            assert(!Ep0StartupSeal());assert(Ep0StartupSnapshot(bytes,sizeof(bytes))==n && !memcmp(before,bytes,n));
            FILE *f=fopen(argv[2],"wb");assert(f);assert(fwrite(bytes,1,n,f)==n);assert(!fclose(f));
        }
    }
    printf("{\"case\":\"%s\",\"passed\":true,\"identity_queries\":%u,\"status\":%u,\"identity_result\":%u,\"owner_reads\":0,\"payload_reads\":0,\"hardware_verified\":false}\n",scenario,queries,Ep0StartupStatus(),Ep0StartupIdentityResult());
}
