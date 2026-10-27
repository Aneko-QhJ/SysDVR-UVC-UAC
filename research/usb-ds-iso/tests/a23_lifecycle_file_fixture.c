/* Native model of the ACTUAL SDK adapter source; never opens a real SD. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define EP0_LCP_NATIVE
#define CUR_THREAD_HANDLE 0
#define R_FAILED(x) ((x)!=0)
#define R_SUCCEEDED(x) ((x)==0)
typedef uint32_t Result,u32;typedef uint64_t u64;typedef int64_t s64;
typedef struct { unsigned unused; } FsFileSystem,FsFile;
enum { Module_Libnx=345,LibnxError_BadInput=1,LibnxError_IoError=2,
       FsOpenMode_Read=1,FsOpenMode_Write=2,FsWriteOption_None=0,FsReadOption_None=0 };
#define MAKERESULT(m,d) ((uint32_t)((m)|((d)<<9)))
#include "ep0_lifecycle_file.h"
static const char *scenario;
static uint8_t disk[EP0_LCP_MAX];
static bool opened,root_open;
static unsigned fs_open,fs_close,creates,opens,writes,flushes,sizes,reads,closes,commits;
static unsigned record_writes;
static uint64_t tick=1000,writer=22;
static bool is(const char *s) { return !strcmp(scenario,s); }
static Result svcGetThreadId(uint64_t *out,int handle) { (void)handle;if(is("identity-error"))return 80;*out=writer;return 0; }
static void randomGet(void *p,size_t n) { memset(p,is("zero-nonce")?0:7,n); }
static uint64_t armGetSystemTickFreq(void) { return 1000; }
static uint64_t svcGetSystemTick(void) { return tick++; }
static Result fsOpenSdCardFileSystem(FsFileSystem *f) { (void)f;fs_open++;if(is("sd-open-error"))return 91;root_open=true;return 0; }
static void fsFsClose(FsFileSystem *f) { (void)f;assert(root_open && !opened);root_open=false;fs_close++; }
static Result fsFsCreateFile(FsFileSystem *f,const char *path,s64 n,u32 opts) {
 (void)f;assert(root_open && !opened && n==EP0_LCP_MAX && !opts);creates++;
 assert(!strcmp(path,"/ep0-life-07070707070707070707070707070707.bin"));
 if(is("create-error") || is("collision"))return 92;memset(disk,0xa5,sizeof(disk));return 0;
}
static Result fsFsOpenFile(FsFileSystem *f,const char *path,u32 mode,FsFile *file) {
 (void)f;(void)path;(void)file;assert(root_open && !opened && mode==3);opens++;if(is("open-error"))return 93;opened=true;return 0;
}
static Result fsFileWrite(FsFile *f,s64 off,const void *data,u64 n,u32 opts) {
 (void)f;assert(opened && off>=0 && off+n<=sizeof(disk) && !opts);writes++;
 if(n==EP0_LCP_RECORD)record_writes++;
 memcpy(disk+off,data,(is("write-error") || (is("record-write-error") && record_writes==2))?n/2:n);
 if(is("corrupt-write"))disk[off+n-1]^=1;
 return is("write-error") || (is("record-write-error") && record_writes==2)?94:0;
}
static Result fsFileFlush(FsFile *f) { (void)f;assert(opened);flushes++;return is("flush-error")?95:0; }
static Result fsFileGetSize(FsFile *f,s64 *n) { (void)f;assert(opened);sizes++;if(is("size-error"))return 96;*n=sizeof(disk)-(is("short-size")?1:0);return 0; }
static Result fsFileRead(FsFile *f,s64 off,void *data,u64 n,u32 opts,u64 *got) {
 (void)f;assert(opened && off>=0 && off+n<=sizeof(disk) && !opts);reads++;
 if(is("read-error"))return 97;if(is("zero-read")) { *got=0;return 0; }if(is("oversize-read")) { *got=n+1;return 0; }
 *got=is("short-read") && n>7?7:n;memcpy(data,disk+off,*got);return 0;
}
static void fsFileClose(FsFile *f) { (void)f;assert(opened);opened=false;closes++; }
static Result fsFsCommit(FsFileSystem *f) { (void)f;assert(root_open && !opened);commits++;return is("commit-error") || (is("header-commit-error") && commits==2) || (is("record-commit-error") && commits==4)?98:0; }
#include "ep0_lifecycle_file.c"
static unsigned io_count(void) { return fs_open+fs_close+creates+opens+writes+flushes+sizes+reads+closes+commits; }
int main(int argc,char **argv) {
 assert(argc==3);scenario=argv[1];uint8_t recipe[32]={3};Result result=Ep0LifePrepare(recipe);
 unsigned before=io_count();assert(Ep0LifePrepare(recipe));assert(before==io_count());
 if(!result) {
  assert(!Ep0LifeContext((void*)1,(void*)1));assert(before==io_count());
  if(is("wrong-writer")) { writer=23;assert(!Ep0LifeNote(EP0_L_USB_INIT_CALL,0,0,0));assert(before==io_count());writer=22; }
  bool advanced=Ep0LifeNote(EP0_L_QUIET_ENTER,0,0,0);
  if(advanced) {
   before=io_count();assert(!Ep0LifeNote(EP0_L_SD_OPEN_CALL,0,0,0));assert(before==io_count());
   assert(Ep0LifeNote(EP0_L_MAIN_LOOP_LEFT,0,0,0));
   assert(Ep0LifeNote(EP0_L_VIDEO_JOIN_CALL,0,0,0));assert(Ep0LifeNote(EP0_L_VIDEO_JOIN_RESULT,0,0,0));
   assert(Ep0LifeNote(EP0_L_AUDIO_JOIN_CALL,0,0,0));assert(Ep0LifeNote(EP0_L_AUDIO_JOIN_RESULT,0,0,0));
   uint8_t boot[16]={1},session[16]={2};assert(Ep0LifeContext(boot,session));
  } else {
   before=io_count();assert(!Ep0LifeNote(EP0_L_MAIN_LOOP_LEFT,0,0,0));assert(before==io_count());
  }
 }
 bool header_valid=!memcmp(disk,"EP0LCP1",7) && ep0_lcp_crc(disk,124)==
  ((uint32_t)disk[124]|(uint32_t)disk[125]<<8|(uint32_t)disk[126]<<16|(uint32_t)disk[127]<<24);
 Ep0LifeFinish(EP0_L_RETAIN,0,0);Ep0LifeClose();assert(!opened && !root_open);assert(closes==opens-(is("open-error")?1:0));
 before=io_count();assert(!Ep0LifeNote(EP0_L_MAIN_RETURN,0,0,0));assert(before==io_count());
 FILE *out=fopen(argv[2],"wb");assert(out);assert(fwrite(disk,1,sizeof(disk),out)==sizeof(disk));assert(!fclose(out));
 printf("{\"prepare_result\":%u,\"phase\":%u,\"last_result\":%u,\"fs_open\":%u,\"fs_close\":%u,\"creates\":%u,\"writes\":%u,\"reads\":%u,\"commits\":%u,\"header_valid\":%s,\"simulation\":true}\n",
 result,Ep0LifeLastPhase(),Ep0LifeLastResult(),fs_open,fs_close,creates,writes,reads,commits,header_valid?"true":"false");
}
