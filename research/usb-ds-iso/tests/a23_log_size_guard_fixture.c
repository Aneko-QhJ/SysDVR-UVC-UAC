/* Exact isolated logger bodies, native vsnprintf, modeled files only. */
#include <assert.h>
#include <limits.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdarg.h>
#include <string.h>
typedef uint32_t Result; typedef int64_t s64; typedef uint64_t u64; typedef uint32_t u32;
typedef struct { unsigned unused; } FsFileSystem;
typedef struct { unsigned unused; } FsFile;
#define R_SUCCEEDED(rc) ((rc)==0)
#define FsOpenMode_Write 2
#define FsOpenMode_Append 4
#define FsWriteOption_Flush 1
static FsFileSystem g_sdCard;
static bool g_sdMounted=true;
static const char *scenario;
static unsigned opens,sizes,writes,closes,formats;
static int required_length;
static s64 write_offset;
static u64 requested;
static unsigned char file_bytes[4096],original[4096];
static size_t file_size=99;
static Result fsFsOpenFile(FsFileSystem *fs,const char *path,unsigned mode,FsFile *file) {
    (void)fs;(void)file;assert(!strcmp(path,"/logfile.txt") && mode==6);opens++;
    return !strcmp(scenario,"open-error")?71:0;
}
static Result fsFileGetSize(FsFile *file,s64 *n) {
    (void)file;sizes++;
    if(!strcmp(scenario,"size-error"))return 72;
    if(!strcmp(scenario,"size-poison")){*n=17;return 72;}
    if(!strcmp(scenario,"size-negative")){*n=-1;return 72;}
    if(!strcmp(scenario,"size-huge")){*n=INT64_MAX;return 72;}
    *n=(s64)file_size;return 0;
}
static Result fsFileWrite(FsFile *file,s64 offset,const void *data,u64 size,u32 flags) {
    (void)file;assert(flags==1 && size<=511);writes++;requested=size;write_offset=offset;
    if(!strcmp(scenario,"write-error"))return 73;
    if(offset<0 || (u64)offset>sizeof(file_bytes) || size>sizeof(file_bytes)-(size_t)offset)return 93;
    size_t count=!strcmp(scenario,"partial-write") && size>3?3:(size_t)size;
    memcpy(file_bytes+(size_t)offset,data,count);
    if((size_t)offset+count>file_size)file_size=(size_t)offset+count;
    return !strcmp(scenario,"partial-write")?73:0;
}
static void fsFileClose(FsFile *file){(void)file;closes++;}
static int observed_vsnprintf(char *buffer,size_t size,const char *format,va_list args) {
    formats++;assert(size==512);
    if(!strcmp(scenario,"format-error"))return required_length=-1;
    return required_length=vsnprintf(buffer,size,format,args);
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
    for(size_t i=0;i<file_size;i++)file_bytes[i]=(unsigned char)(i*17u+3u);
    memcpy(original,file_bytes,sizeof(original));
    if(!strcmp(scenario,"unmounted"))g_sdMounted=false;
    if(!strcmp(scenario,"catalog"))catalog_case(value);
    else {assert(value<=1024);char text[1025];memset(text,'Q',value);text[value]=0;LogFunctionImpl("%s",text);}
    assert(closes==(opens && strcmp(scenario,"open-error")?1u:0u));
    bool unchanged=!memcmp(original,file_bytes,sizeof(original)) && file_size==99;
    printf("{\"passed\":true,\"required_length\":%d,\"formats\":%u,\"opens\":%u,\"sizes\":%u,\"writes\":%u,\"closes\":%u,\"requested\":%llu,\"write_offset\":%lld,\"file_size\":%zu,\"existing_file_unchanged\":%s,\"usb_calls\":0,\"sd_calls\":0}\n",required_length,formats,opens,sizes,writes,closes,(unsigned long long)requested,(long long)write_offset,file_size,unchanged?"true":"false");
}
