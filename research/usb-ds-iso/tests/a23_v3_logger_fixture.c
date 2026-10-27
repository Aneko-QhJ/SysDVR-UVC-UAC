/* Exact sealed logger body is inserted by the audit. All FS calls are mocks.
 * Command serialization deliberately does not serialize a whole log message.
 * Offset, append and busy-open policies are alternatives, not Horizon facts. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdarg.h>
#include <string.h>
#include <pthread.h>
typedef uint32_t Result;
typedef int64_t s64;
typedef struct { int unused; } FsFileSystem;
typedef struct { int owner; } FsFile;
enum { FsOpenMode_Write=2, FsOpenMode_Append=4, FsWriteOption_Flush=1 };
#define R_SUCCEEDED(x) ((x)==0)
static FsFileSystem g_sdCard;
static bool g_sdMounted=true;
static pthread_mutex_t mu=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t cv=PTHREAD_COND_INITIALIZER;
static _Thread_local int who;
static char bytes[8192], trace[512];
static size_t used, trace_used, lengths[2];
static s64 offsets[2];
static int opens, sizes, writes, closes, format_calls, mode, fault;
static bool threaded, first_size, second_seen, first_written;
static int mock_vsnprintf(char *p,size_t n,const char *fmt,va_list a) {
    pthread_mutex_lock(&mu);format_calls++;pthread_mutex_unlock(&mu);
    if (fault==1) return -1;
    return vsnprintf(p,n,fmt,a);
}
static void note(char op,int id) {
    assert(trace_used+3<sizeof(trace));trace[trace_used++]=op;
    trace[trace_used++]=(char)('0'+id);trace[trace_used++]=' ';trace[trace_used]=0;
}
static Result fsFsOpenFile(FsFileSystem *s,const char *path,int flags,FsFile *f) {
    assert(s==&g_sdCard && !strcmp(path,"/logfile.txt") && flags==6);
    pthread_mutex_lock(&mu);opens++;note('O',who);
    bool fail=fault==2 || (threaded && mode==3 && who==1);
    if (threaded && who==1 && fail) {second_seen=true;pthread_cond_broadcast(&cv);}
    if (!fail) f->owner=who;
    pthread_mutex_unlock(&mu);return fail ? 1u:0u;
}
static Result fsFileGetSize(FsFile *f,s64 *p) {
    pthread_mutex_lock(&mu);sizes++;note('G',f->owner);*p=(s64)used;
    if (threaded) {
        if (who==0) {first_size=true;pthread_cond_broadcast(&cv);}
        else {second_seen=true;pthread_cond_broadcast(&cv);}
        /* Pause after this command has read the size. The other command may
         * execute while the first caller has not yet made its write. */
        while (who==0 && !second_seen) pthread_cond_wait(&cv,&mu);
        while (who==1 && !first_written) pthread_cond_wait(&cv,&mu);
    }
    pthread_mutex_unlock(&mu);return fault==3 ? 1u:0u;
}
static Result fsFileWrite(FsFile *f,s64 offset,const void *p,size_t n,int options) {
    assert(offset>=0 && n<=511 && options==FsWriteOption_Flush);
    pthread_mutex_lock(&mu);writes++;note('W',f->owner);
    offsets[f->owner]=offset;lengths[f->owner]=n;
    if (fault!=4) {
        size_t at=mode==2 ? used:(size_t)offset;assert(at+n<=sizeof(bytes));
        memcpy(bytes+at,p,n);if (at+n>used) used=at+n;
    }
    if (threaded && who==0) {first_written=true;pthread_cond_broadcast(&cv);}
    pthread_mutex_unlock(&mu);return fault==4 ? 1u:0u;
}
static void fsFileClose(FsFile *f) {
    pthread_mutex_lock(&mu);closes++;note('C',f->owner);pthread_mutex_unlock(&mu);
}
#define vsnprintf mock_vsnprintf
/* INSERT_LOGGER */
#undef vsnprintf
static void *worker(void *arg) {
    who=(int)(intptr_t)arg;LogFunctionImpl("%s",who ? "BBBB":"AAAA");return NULL;
}
int main(int argc,char **argv) {
    assert(argc==2);const char *name=argv[1];
    if (!strcmp(name,"offset") || !strcmp(name,"append") || !strcmp(name,"busy")) {
        threaded=true;mode=!strcmp(name,"append") ? 2:!strcmp(name,"busy") ? 3:1;
        pthread_t a,b;assert(!pthread_create(&a,NULL,worker,(void *)(intptr_t)0));
        pthread_mutex_lock(&mu);while (!first_size) pthread_cond_wait(&cv,&mu);pthread_mutex_unlock(&mu);
        assert(!pthread_create(&b,NULL,worker,(void *)(intptr_t)1));
        assert(!pthread_join(a,NULL));assert(!pthread_join(b,NULL));
        if (mode==1) {assert(used==4 && !memcmp(bytes,"BBBB",4));assert(offsets[0]==0 && offsets[1]==0);}
        if (mode==2) {assert(used==8 && !memcmp(bytes,"AAAABBBB",8));assert(offsets[0]==0 && offsets[1]==0);}
        if (mode==3) {assert(used==4 && !memcmp(bytes,"AAAA",4));assert(sizes==1 && writes==1 && closes==1);}
        assert(opens==2 && format_calls==2);
    } else {
        if (!strcmp(name,"unmounted")) g_sdMounted=false;
        if (!strcmp(name,"format-failure")) fault=1;
        if (!strcmp(name,"open-failure")) fault=2;
        if (!strcmp(name,"size-failure")) fault=3;
        if (!strcmp(name,"write-failure")) fault=4;
        if (!strcmp(name,"empty")) LogFunctionImpl("");
        else if (!strcmp(name,"binary")) LogFunctionImpl("%cX",0);
        else if (!strncmp(name,"length-",7)) {
            int n=atoi(name+7);assert(n>0 && n<4096);char s[4096];memset(s,'Z',(size_t)n);s[n]=0;
            LogFunctionImpl("%s",s);assert(used==(size_t)(n>511 ? 511:n));
            assert(lengths[0]==used && bytes[used-1]=='Z');
        } else LogFunctionImpl("hello %d",7);
        if (!g_sdMounted) assert(!format_calls && !opens);
        else if (fault==1 || !strcmp(name,"empty")) assert(format_calls==1 && !opens);
        else if (fault==2) assert(opens==1 && !sizes && !writes && !closes);
        else if (fault==3) assert(opens==1 && sizes==1 && !writes && closes==1);
        else {assert(opens==1 && sizes==1 && writes==1 && closes==1);if (fault==4) assert(!used);}
        if (!strcmp(name,"binary")) assert(used==2 && bytes[0]==0 && bytes[1]=='X');
    }
    printf("{\"case\":\"%s\",\"format_calls\":%d,\"opens\":%d,\"sizes\":%d,\"writes\":%d,\"closes\":%d,\"file_bytes\":%zu,\"offsets\":[%lld,%lld],\"trace\":\"%s\",\"mock_fs_only\":true,\"real_concurrency_verified\":false}\n",
        name,format_calls,opens,sizes,writes,closes,used,(long long)offsets[0],(long long)offsets[1],trace);
    return 0;
}
