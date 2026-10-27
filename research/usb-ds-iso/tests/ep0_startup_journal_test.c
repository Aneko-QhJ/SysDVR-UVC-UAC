#include <assert.h>
#include <pthread.h>
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include "research/usb-ds-iso/device/ep0_startup_journal.h"
static uint8_t recipe[32]={3};
static void save(const char *prefix,const char *name,const Ep0StartupJournal *j) {
    uint8_t bytes[EP0_INIT_MAX];size_t n=ep0_startup_snapshot(j,bytes,sizeof(bytes));assert(n);
    char path[1024];assert(strlen(prefix)+strlen(name)+6<sizeof(path));snprintf(path,sizeof(path),"%s-%s.bin",prefix,name);
    FILE *f=fopen(path,"wb");assert(f);assert(fwrite(bytes,1,n,f)==n);assert(!fclose(f));
}
static void untouched(const uint8_t *b,size_t n) { for(size_t i=0;i<n;i++)assert(b[i]==0xa5); }
static uint32_t read32(const uint8_t *p) { return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24; }
static Ep0StartupJournal journals[32];
static atomic_bool ready,observed,done;
static unsigned concurrent_reads,live_reads;
static void *writer(void *p) {
    (void)p;
    for(unsigned j=0;j<32;j++) {
        assert(ep0_startup_init(&journals[j],11,recipe));
        for(unsigned i=0;i<64;i++) {
            assert(ep0_startup_record(&journals[j],11,EP0_I_FS_INIT,(i&1) ? EP0_I_RESULT:EP0_I_CALL,0));
            if(j==0 && i==0) {
                atomic_store_explicit(&ready,true,memory_order_release);
                while(!atomic_load_explicit(&observed,memory_order_acquire))sched_yield();
            }
            if((i&7)==0)sched_yield();
        }
        assert(ep0_startup_seal(&journals[j],11));
    }
    atomic_store_explicit(&done,true,memory_order_release);return NULL;
}
static void check_prefix(unsigned j) {
    uint8_t b[EP0_INIT_MAX];size_t n=ep0_startup_snapshot(&journals[j],b,sizeof(b));if(!n)return;
    unsigned count=read32(b+24),flags=read32(b+20);assert(count<=64 && n==96+16*count);
    assert(!(flags&6));
    if(!(flags&1))live_reads++;
    for(unsigned i=0;i<count;i++) {
        const uint8_t *r=b+96+i*16;assert(r[0]==EP0_I_FS_INIT && r[1]==0);
        assert(r[2]==((i&1) ? EP0_I_RESULT:EP0_I_CALL) && !r[3]);
        assert(read32(r+4)==0 && read32(r+8)==i+1 && read32(r+12)==0);
    }
    assert(ep0_trace_crc32(b+96,16*count)==read32(b+72));
    concurrent_reads++;
}
static void *reader(void *p) {
    (void)p;while(!atomic_load_explicit(&ready,memory_order_acquire))sched_yield();
    check_prefix(0);assert(live_reads);
    atomic_store_explicit(&observed,true,memory_order_release);
    do { for(unsigned j=0;j<32;j++)check_prefix(j); }
    while(!atomic_load_explicit(&done,memory_order_acquire));return NULL;
}
int main(int argc,char **argv) {
    assert(argc==2);unsigned cases=0;uint8_t bytes[EP0_INIT_MAX],zero[32]={0};
    Ep0StartupJournal unstarted={0};memset(bytes,0xa5,sizeof(bytes));assert(!ep0_startup_snapshot(&unstarted,bytes,sizeof(bytes)));untouched(bytes,sizeof(bytes));cases++;
    assert(!ep0_startup_init(&unstarted,0,recipe));assert(!ep0_startup_init(&unstarted,11,zero));assert(!atomic_load(&unstarted.published));cases++;
    Ep0StartupJournal j={0};assert(ep0_startup_init(&j,11,recipe));assert(!ep0_startup_init(&j,11,recipe));
    assert(ep0_startup_record(&j,11,EP0_I_VIDEO_CREATE,EP0_I_CALL,0));assert(ep0_startup_record(&j,11,EP0_I_VIDEO_CREATE,EP0_I_RESULT,0));
    assert(ep0_startup_record(&j,11,EP0_I_VIDEO_START,EP0_I_CALL,0));assert(ep0_startup_record(&j,11,EP0_I_VIDEO_START,EP0_I_RESULT,82));
    assert(ep0_startup_record(&j,11,EP0_I_FATAL,EP0_I_FATAL_RESULT,82));assert(ep0_startup_seal(&j,11));save(argv[1],"failure",&j);cases++;
    size_t n=ep0_startup_snapshot(&j,bytes,sizeof(bytes));uint8_t before[EP0_INIT_MAX];memcpy(before,bytes,n);
    assert(!ep0_startup_record(&j,9,EP0_I_FS_INIT,EP0_I_CALL,0));assert(!ep0_startup_seal(&j,11));assert(!ep0_startup_init(&j,11,recipe));
    assert(ep0_startup_snapshot(&j,bytes,sizeof(bytes))==n && !memcmp(bytes,before,n));cases++;
    memset(bytes,0xa5,sizeof(bytes));assert(!ep0_startup_snapshot(&j,bytes,n-1));untouched(bytes,sizeof(bytes));cases++;
    Ep0StartupJournal alias_before=j;assert(!ep0_startup_snapshot(&j,(uint8_t*)&j,sizeof(j)));assert(!memcmp(&j,&alias_before,sizeof(j)));cases++;
    Ep0StartupJournal bad={0};assert(ep0_startup_init(&bad,11,recipe));assert(!ep0_startup_record(&bad,9,EP0_I_FS_INIT,EP0_I_CALL,0));assert(!ep0_startup_record(&bad,11,EP0_I_FS_INIT,EP0_I_CALL,0));save(argv[1],"wrong-writer",&bad);cases++;
    Ep0StartupJournal invalid={0};assert(ep0_startup_init(&invalid,11,recipe));assert(!ep0_startup_record(&invalid,11,EP0_I_FS_EXIT,EP0_I_RESULT,0));save(argv[1],"invalid",&invalid);cases++;
    Ep0StartupJournal busy={0};assert(ep0_startup_init(&busy,11,recipe));assert(ep0_startup_record(&busy,11,EP0_I_FS_INIT,EP0_I_CALL,0));
    atomic_fetch_or(&busy.published,EP0_IN_BUSY);busy.records[1]=(Ep0InitRecord){0xffff,0xffff,0xffffffff};
    assert(!ep0_startup_seal(&busy,11));save(argv[1],"busy-prefix",&busy);cases++;
    assert(!ep0_startup_record(&busy,11,EP0_I_FS_INIT,EP0_I_RESULT,0));assert((atomic_load(&busy.published)&EP0_IN_COUNT)==1);cases++;
    Ep0StartupJournal full={0};assert(ep0_startup_init(&full,11,recipe));
    for(unsigned i=0;i<64;i++)assert(ep0_startup_record(&full,11,EP0_I_FS_INIT,(i&1) ? EP0_I_RESULT:EP0_I_CALL,0));
    assert(!ep0_startup_record(&full,11,EP0_I_FS_INIT,EP0_I_CALL,0));assert(ep0_startup_seal(&full,11));save(argv[1],"full",&full);assert(ep0_startup_snapshot(&full,bytes,sizeof(bytes))==EP0_INIT_MAX);cases++;
    Ep0StartupJournal voids={0};assert(ep0_startup_init(&voids,11,recipe));assert(ep0_startup_record(&voids,11,EP0_I_SD_CLOSE,EP0_I_CALL,0));assert(ep0_startup_record(&voids,11,EP0_I_SD_CLOSE,EP0_I_VOID_RETURN,0));assert(ep0_startup_seal(&voids,11));save(argv[1],"void",&voids);cases++;
    Ep0StartupJournal mismatch={0};assert(ep0_startup_init(&mismatch,11,recipe));
    assert(!ep0_startup_record(&mismatch,11,EP0_I_VIDEO_START,EP0_I_RESULT,0));save(argv[1],"mismatch",&mismatch);cases++;
    Ep0StartupJournal terminal={0};assert(ep0_startup_init(&terminal,11,recipe));assert(ep0_startup_record(&terminal,11,EP0_I_FATAL,EP0_I_FATAL_RESULT,82));
    assert(!ep0_startup_record(&terminal,11,EP0_I_FS_INIT,EP0_I_CALL,0));assert(ep0_startup_seal(&terminal,11));save(argv[1],"terminal",&terminal);cases++;
    pthread_t a,b;assert(!pthread_create(&a,NULL,writer,NULL));assert(!pthread_create(&b,NULL,reader,NULL));assert(!pthread_join(a,NULL));assert(!pthread_join(b,NULL));
    assert(concurrent_reads && live_reads);save(argv[1],"concurrent-final",&journals[31]);cases++;
    printf("{\"passed\":true,\"cases\":%u,\"cpu_threads\":2,\"journals\":32,\"published_records\":2048,\"concurrent_reads\":%u,\"live_prefix_reads\":%u,\"maximum\":%u,\"single_writer_contract\":true,\"switch_threads_executed\":false}\n",cases,concurrent_reads,live_reads,EP0_INIT_MAX);
}
