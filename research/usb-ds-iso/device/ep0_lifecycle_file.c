#ifndef EP0_LCP_NATIVE
#include <switch.h>
#endif
#include "ep0_lifecycle_file.h"

static Ep0LifecycleCapsule life_capsule;
static FsFileSystem life_fs;
static bool life_fs_open,life_prepare_attempted,life_prepared;
static uint32_t life_phase,life_result;
static uint8_t life_check[EP0_LCP_HEADER];
static const uint8_t life_zero[EP0_LCP_HEADER];
static char life_path[64];
static uint32_t life_bad_input(void) { return MAKERESULT(Module_Libnx,LibnxError_BadInput); }
static uint32_t life_bad_io(void) { return MAKERESULT(Module_Libnx,LibnxError_IoError); }
static uint32_t life_transfer(size_t offset,const void *data,size_t n,bool zero) {
    if(!life_fs_open || (!zero && !data) || n>EP0_LCP_MAX || offset+n>EP0_LCP_MAX)return life_bad_input();
    FsFile file={0};
    life_phase=EP0_LF_FILE_OPEN;
    Result rc=fsFsOpenFile(&life_fs,life_path,FsOpenMode_Read|FsOpenMode_Write,&file);
    if(R_FAILED(rc))return life_result=rc;
    life_phase=EP0_LF_WRITE;
    for(size_t at=0;at<n;) {
        size_t chunk=n-at<sizeof(life_zero)?n-at:sizeof(life_zero);
        rc=fsFileWrite(&file,(s64)(offset+at),zero?life_zero:(const uint8_t*)data+at,chunk,FsWriteOption_None);
        if(R_FAILED(rc))goto close;
        at+=chunk;
    }
    life_phase=EP0_LF_FLUSH;rc=fsFileFlush(&file);if(R_FAILED(rc))goto close;
    life_phase=EP0_LF_SIZE;
    s64 size=0;rc=fsFileGetSize(&file,&size);if(R_FAILED(rc))goto close;
    if(size!=EP0_LCP_MAX) { rc=life_bad_io();goto close; }
    size_t at=0;
    while(at<n) {
        size_t chunk=n-at<sizeof(life_check)?n-at:sizeof(life_check);
        life_phase=EP0_LF_READ;
        u64 got=0;rc=fsFileRead(&file,(s64)(offset+at),life_check,chunk,FsReadOption_None,&got);
        if(R_FAILED(rc))goto close;
        if(!got || got>chunk) { rc=life_bad_io();goto close; }
        life_phase=EP0_LF_COMPARE;
        if(memcmp(life_check,zero?life_zero:(const uint8_t*)data+at,(size_t)got)) { rc=life_bad_io();goto close; }
        at+=(size_t)got;
    }
close:
    fsFileClose(&file);
    if(R_SUCCEEDED(rc)) {
        life_phase=EP0_LF_COMMIT;rc=fsFsCommit(&life_fs);
        if(R_SUCCEEDED(rc))life_phase=EP0_LF_READY;
    }
    life_result=rc;return rc;
}
static uint32_t life_write_once(void *unused,size_t offset,const void *data,size_t n) {
    (void)unused;
    if(n>EP0_LCP_HEADER)return life_bad_input();
    return life_transfer(offset,data,n,false);
}
uint32_t Ep0LifeLastPhase(void) { return life_phase; }
uint32_t Ep0LifeLastResult(void) { return life_result; }
void Ep0LifeClose(void) {
    /* Close ONLY the extra main-owned journal, never Core/USB/DMA resources. */
    if(life_fs_open) { fsFsClose(&life_fs);life_fs_open=false; }
    life_prepared=false;
}
void Ep0LifeFinish(unsigned stage,uint32_t result,uint32_t reason) {
    (void)Ep0LifeNote(stage,result,reason,0);Ep0LifeClose();
}
uint32_t Ep0LifePrepare(const uint8_t recipe[32]) {
    if(life_prepare_attempted)return life_bad_input();
    life_prepare_attempted=true;uint64_t writer=0;
    life_phase=EP0_LF_IDENTITY;
    Result rc=svcGetThreadId(&writer,CUR_THREAD_HANDLE);
    if(R_FAILED(rc) || !writer) { life_result=rc?rc:life_bad_input();return life_result; }
    life_phase=EP0_LF_NONCE;
    uint8_t nonce[16];randomGet(nonce,sizeof(nonce));
    if(!ep0_lcp_nonzero(nonce,sizeof(nonce)) || !ep0_lcp_nonzero(recipe,32))return life_result=life_bad_input();
    static const char hex[]="0123456789abcdef";
    memcpy(life_path,"/ep0-life-",10);
    for(unsigned i=0;i<16;i++) { life_path[10+2*i]=hex[nonce[i]>>4];life_path[11+2*i]=hex[nonce[i]&15]; }
    memcpy(life_path+42,".bin",5);
    life_phase=EP0_LF_SD_OPEN;rc=fsOpenSdCardFileSystem(&life_fs);
    if(R_FAILED(rc))return life_result=rc;
    life_fs_open=true;life_phase=EP0_LF_CREATE;
    rc=fsFsCreateFile(&life_fs,life_path,EP0_LCP_MAX,0); /* No delete/truncate or retry. */
    if(R_FAILED(rc)) { life_result=rc;Ep0LifeClose();return rc; }
    rc=life_transfer(0,NULL,EP0_LCP_MAX,true); /* Do not assume newly allocated bytes are zero. */
    if(R_FAILED(rc)) { Ep0LifeClose();return rc; }
    if(!ep0_lcp_init(&life_capsule,NULL,life_write_once,writer,armGetSystemTickFreq(),svcGetSystemTick(),nonce,recipe)) {
        rc=life_capsule.last_result?life_capsule.last_result:life_bad_input();Ep0LifeClose();return life_result=rc;
    }
    life_prepared=true;
    if(!Ep0LifeNote(EP0_L_PREPARED,0,0,0)) {
        rc=life_result?life_result:life_bad_input();Ep0LifeClose();return life_result=rc;
    }
    return 0;
}
bool Ep0LifeNote(unsigned stage,uint32_t result,uint32_t arg0,uint32_t arg1) {
    if(!life_prepared || life_capsule.disabled || life_capsule.closed)return false;
    uint64_t writer=0;if(R_FAILED(svcGetThreadId(&writer,CUR_THREAD_HANDLE)))return false;
    return ep0_lcp_note(&life_capsule,writer,stage,svcGetSystemTick(),result,arg0,arg1,NULL);
}
bool Ep0LifeContext(const uint8_t boot[16],const uint8_t session[16]) {
    /* Reject before reading optional owner metadata, including poison pointers. */
    if(!life_prepared || life_capsule.disabled || life_capsule.closed || life_capsule.join_mask!=3 || !boot || !session)return false;
    uint64_t writer=0;if(R_FAILED(svcGetThreadId(&writer,CUR_THREAD_HANDLE)) || writer!=life_capsule.writer)return false;
    uint8_t context[32];memcpy(context,boot,16);memcpy(context+16,session,16);
    return ep0_lcp_note(&life_capsule,writer,EP0_L_CONTEXT,svcGetSystemTick(),0,0,0,context);
}
