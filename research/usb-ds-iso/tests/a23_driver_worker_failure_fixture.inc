/* Test-only store access. The adapter/driver retain its owner through join. */
typedef struct {
    A23VersionedClockStore *store;const char *name;
    uint64_t before,after,ticket;int beginStatus,finishStatus;
    BOOL tail,poisoned;
} DriverWorkerFailure;
static void *driverFailureWorker(void *argument){
    DriverWorkerFailure *w=argument;w->before=atomic_load(&w->store->generation);
    if(!strcmp(w->name,"capture-worker-exit"))pthread_exit((void *)(uintptr_t)9);
    if(!strcmp(w->name,"capture-worker-error")){w->tail=YES;return (void *)(uintptr_t)7;}
    if(strstr(w->name,"exhausted"))atomic_store(&w->store->generation,UINT64_MAX-1);
    w->beginStatus=(int)A23VersionedClockBegin(w->store,&w->ticket);
    if(w->beginStatus==A23VersionedClockOK){
        if(strstr(w->name,"unfinished-exit"))pthread_exit((void *)(uintptr_t)9);
        if(strstr(w->name,"unfinished")){w->tail=YES;return (void *)(uintptr_t)7;}
        A23CandidateClockStamp profile={0,A23CandidateInjectedDriver,1,1,1};
        if(strstr(w->name,"invalid-finish"))profile.numerator=0;
        w->finishStatus=(int)A23VersionedClockFinish(w->store,w->ticket+(strstr(w->name,"wrong-ticket") ? 2U : 0U),&profile);
    }
    w->tail=YES;return strstr(w->name,"busy-error") ? (void *)(uintptr_t)7 : NULL;
}
static NSMutableDictionary *runDriverFailureWorker(A23VersionedClockStore *store,NSString *name){
    DriverWorkerFailure work={.store=store,.name=name.UTF8String,.beginStatus=-1,.finishStatus=-1};
    pthread_t thread;assert(pthread_create(&thread,NULL,driverFailureWorker,&work)==0);
    void *exit=NULL;int joined=pthread_join(thread,&exit);assert(joined==0);
    work.after=atomic_load(&store->generation);work.poisoned=atomic_load(&store->poisoned);
    NSString *stage=[name hasPrefix:@"capture-return-"] ? @"capture_return" : [name hasPrefix:@"capture-"] ? @"capture" : [name hasPrefix:@"gate-"] ? @"commit" : [name hasPrefix:@"after-receipt-"] ? @"after_receipt" : @"after_release";
    return [@{@"schema":@"A23-driver-worker-failure-1",@"case":name,@"stage":stage,
        @"created":@YES,@"joined":@YES,@"join_status":@(joined),@"exit_code":@((uintptr_t)exit),@"tail_reached":@(work.tail),
        @"before_generation":@(work.before),@"after_generation":@(work.after),@"ticket":@(work.ticket),
        @"begin_status":@(work.beginStatus),@"finish_status":@(work.finishStatus),@"poisoned":@(work.poisoned),
        @"capture_status":@(-1),@"capture_output_zeroed":@NO,@"injected_fixture":@YES,@"provenance_authenticated":@NO} mutableCopy];
}
