#include <pthread.h>
#include <string.h>
@protocol ConcurrentCallbacks <NSObject>
- (void)oldISO;
- (void)oldControl;
@end
typedef struct {
    pthread_mutex_t lock;pthread_cond_t condition;
    unsigned ready,count;BOOL go;
} CommitThreadGate;
typedef struct {
    CommitThreadGate *gate;
    __unsafe_unretained TwoClock *clock;
    __unsafe_unretained id<ConcurrentCallbacks> callbacks;
    const char *name;
    uint64_t before,after;
    unsigned statuses[2],statusCount,actions[3],actionCount;
} CommitThreadWork;
static void action(CommitThreadWork *w,unsigned code){assert(w->actionCount<3);w->actions[w->actionCount++]=code;}
static void callback(CommitThreadWork *w){
    if(strstr(w->name,"iso")){action(w,1);[w->callbacks oldISO];}
    if(strstr(w->name,"control")){action(w,2);[w->callbacks oldControl];}
}
static void publish(CommitThreadWork *w,uint32_t numerator){
    action(w,3);w->clock.n=numerator;assert(w->statusCount<2);w->statuses[w->statusCount++]=(unsigned)w->clock.lastWriteStatus;
}
static void *commitWorker(void *argument){
    @autoreleasepool {
        CommitThreadWork *w=argument;CommitThreadGate *g=w->gate;
        assert(pthread_mutex_lock(&g->lock)==0);++g->ready;assert(pthread_cond_broadcast(&g->condition)==0);
        while(!g->go)assert(pthread_cond_wait(&g->condition,&g->lock)==0);
        assert(pthread_mutex_unlock(&g->lock)==0);
        w->before=w->clock.profileGeneration;
        if(strstr(w->name,"before-write"))callback(w);
        publish(w,strstr(w->name,"noop") ? 1 : 2);
        if(strstr(w->name,"aba"))publish(w,1);
        if(strstr(w->name,"write-before"))callback(w);
        w->after=w->clock.profileGeneration;
    }return NULL;
}
static NSDictionary *runCommitThreads(TwoClock *clock,id<ConcurrentCallbacks> callbacks,NSString *name){
    const char *mode=name.UTF8String;unsigned count=[name isEqual:@"gate-two-publishers"] ? 2 : 1;
    CommitThreadGate gate={.count=count};assert(pthread_mutex_init(&gate.lock,NULL)==0);assert(pthread_cond_init(&gate.condition,NULL)==0);
    CommitThreadWork work[2]={0};pthread_t threads[2];
    for(unsigned n=0;n<count;++n){work[n]=(CommitThreadWork){.gate=&gate,.clock=clock,.callbacks=callbacks,.name=mode};assert(pthread_create(&threads[n],NULL,commitWorker,&work[n])==0);}
    assert(pthread_mutex_lock(&gate.lock)==0);
    while(gate.ready<count)assert(pthread_cond_wait(&gate.condition,&gate.lock)==0);
    gate.go=YES;assert(pthread_cond_broadcast(&gate.condition)==0);assert(pthread_mutex_unlock(&gate.lock)==0);
    for(unsigned n=0;n<count;++n)assert(pthread_join(threads[n],NULL)==0);
    NSMutableArray *rows=[NSMutableArray new];
    for(unsigned n=0;n<count;++n){
        NSMutableArray *statuses=[NSMutableArray new],*actions=[NSMutableArray new];
        for(unsigned j=0;j<work[n].statusCount;++j)[statuses addObject:@(work[n].statuses[j])];
        for(unsigned j=0;j<work[n].actionCount;++j)[actions addObject:@[@"unused",@"iso",@"control",@"publish"][work[n].actions[j]]];
        [rows addObject:@{@"index":@(n),@"before_generation":@(work[n].before),@"after_generation":@(work[n].after),@"statuses":statuses,@"actions":actions}];
    }
    assert(pthread_cond_destroy(&gate.condition)==0);assert(pthread_mutex_destroy(&gate.lock)==0);
    NSString *stage=[name hasPrefix:@"gate-"] ? @"commit" : [name hasPrefix:@"after-receipt-"] ? @"after_receipt" : [name hasPrefix:@"after-release-"] ? @"after_release" : @"capture_return";
    return @{@"schema":@"A23-commit-concurrency-trace-1",@"case":name,@"stage":stage,@"worker_count":@(count),@"ready_count":@(gate.ready),@"workers":rows,@"injected_fixture":@YES,@"actual_clock_authenticated":@NO};
}
