/* Real logger function, real host vsnprintf, modeled FS. No USB/SD. */
#include <assert.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint32_t Result;typedef int64_t s64;typedef uint64_t u64;typedef uint32_t u32;
typedef struct { unsigned unused; } FsFileSystem;typedef struct { unsigned unused; } FsFile;
#define R_SUCCEEDED(rc) ((rc)==0)
#define FsOpenMode_Write 2
#define FsOpenMode_Append 4
#define FsWriteOption_Flush 1
static FsFileSystem g_sdCard;static bool g_sdMounted=true;
static const char *scenario;
static unsigned opens,sizes,writes,closes,formats;
static int required_length;static u64 requested;static s64 write_offset;
static bool span_exceeds_buffer,text_truncated,contains_nul;
static unsigned checksum;static size_t copied;
static Result fsFsOpenFile(FsFileSystem *fs,const char *path,unsigned mode,FsFile *file) {
    (void)fs;(void)file;assert(!strcmp(path,"/logfile.txt"));assert(mode==6);opens++;return !strcmp(scenario,"open-error")?71:0;
}
static Result fsFileGetSize(FsFile *file,s64 *n) { (void)file;sizes++;if(!strcmp(scenario,"size-error"))return 72;*n=99;return 0; }
static Result fsFileWrite(FsFile *file,s64 offset,const void *buffer,u64 size,u32 flags) {
    (void)file;assert(flags==1);writes++;requested=size;write_offset=offset;
    span_exceeds_buffer=size>512;text_truncated=required_length>=512;
    /* Observe the oversized argument without making the service stub read
       outside the real 512-byte stack object. Actual DMA/FS reads untested. */
    copied=size<512?(size_t)size:512;const unsigned char *p=buffer;
    for(size_t i=0;i<copied;i++) { contains_nul|=!p[i];checksum=(checksum*33u)^p[i]; }
    return !strcmp(scenario,"write-error")?73:0;
}
static void fsFileClose(FsFile *file) { (void)file;closes++; }
static int observed_vsnprintf(char *p,size_t n,const char *fmt,va_list args) {
    formats++;assert(n==512);if(!strcmp(scenario,"format-error"))return required_length=-1;
    return required_length=vsnprintf(p,n,fmt,args);
}
#define vsnprintf observed_vsnprintf
/* INSERT_LOGGER */
#undef vsnprintf
static void catalog_case(unsigned index) {
    switch(index) {
/* INSERT_CATALOG */
    default:assert(false);
    }
}
int main(int argc,char **argv) {
    assert(argc==3);scenario=argv[1];unsigned value=(unsigned)strtoul(argv[2],NULL,10);
    if(!strcmp(scenario,"unmounted"))g_sdMounted=false;
    if(!strcmp(scenario,"catalog"))catalog_case(value);
    else { char text[1025];assert(value<=1024);memset(text,'Q',value);text[value]=0;LogFunctionImpl("%s",text); }
    assert(closes==(opens && strcmp(scenario,"open-error") ? 1u:0u));
    printf("{\"passed\":true,\"required_length\":%d,\"formats\":%u,\"opens\":%u,\"sizes\":%u,\"writes\":%u,\"closes\":%u,\"requested\":%llu,\"write_offset\":%lld,\"copied\":%zu,\"checksum\":%u,\"span_exceeds_buffer\":%s,\"text_truncated\":%s,\"contains_nul\":%s,\"usb_calls\":0,\"sd_calls\":0}\n",required_length,formats,opens,sizes,writes,closes,(unsigned long long)requested,(long long)write_offset,copied,checksum,span_exceeds_buffer?"true":"false",text_truncated?"true":"false",contains_nul?"true":"false");
}
