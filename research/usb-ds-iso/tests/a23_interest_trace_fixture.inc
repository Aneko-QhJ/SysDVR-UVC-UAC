#include <IOKit/IOMessage.h>
#include <IOKit/usb/IOUSBHostFamilyDefinitions.h>
#include "a23_interest_trace.h"
#include <pthread.h>
static void *traceWriter(void *p){a23_interest_record(p,UINT32_MAX,12345);return NULL;}
static NSDictionary *contracts(void){
    A23InterestTrace trace;a23_interest_init(&trace);A23InterestSnapshot empty=a23_interest_snapshot(&trace);assert(empty.complete && !empty.claimed);NSDictionary *gap=a23_interest_dictionary(&trace,true);assert(![gap[@"complete"] boolValue] && [gap[@"latch_without_slot"] boolValue]);
    unsigned token=a23_interest_begin(&trace,UINT32_MAX,0);A23InterestSnapshot pending=a23_interest_snapshot(&trace);assert(pending.claimed==1 && pending.pending==1 && !pending.complete && !pending.present[0]);NSDictionary *pendingBefore=a23_interest_dictionary(&trace,true);
    a23_interest_commit(&trace,token);A23InterestSnapshot ready=a23_interest_snapshot(&trace);assert(ready.complete && ready.message[0]==UINT32_MAX && ready.ticks[0]==0);
    A23InterestTrace concurrent;a23_interest_init(&concurrent);pthread_t threads[9];
    for(unsigned i=0;i<9;++i)assert(!pthread_create(&threads[i],NULL,traceWriter,&concurrent));
    for(unsigned i=0;i<9;++i)assert(!pthread_join(threads[i],NULL));
    A23InterestSnapshot full=a23_interest_snapshot(&concurrent);assert(full.overflow && full.claimed<=8 && full.committed==full.claimed && !full.complete);
    return @{@"latch_gap":gap,@"pending":pendingBefore,@"committed":a23_interest_dictionary(&trace,true),@"overflow":a23_interest_dictionary(&concurrent,true),@"native_threads_joined":@9};
}
int main(int argc,const char *argv[]){@autoreleasepool{
    assert(argc==3);NSString *name=@(argv[1]),*directory=@(argv[2]);
    if([name isEqual:@"contracts"]){NSData *raw=[NSJSONSerialization dataWithJSONObject:contracts() options:NSJSONWritingSortedKeys error:NULL];fwrite(raw.bytes,1,raw.length,stdout);puts("");return 0;}
    NSDictionary *messages=@{@"terminated":@(kIOMessageServiceIsTerminated),@"request-close":@(kUSBHostMessageDeviceIsRequestingClose),@"configuration":@(kUSBHostMessageConfigurationSet),@"unknown":@(UINT32_MAX),@"zero":@0,@"overflow":@0x12345678};
    PairOperations *op=pairOperations(name,NO);SDKModelInterface *r=[SDKModelInterface new];r.fault=name;r.clock=[TwoClock new];op.interface=r;
    dispatch_queue_t q=dispatch_queue_create("a23.interest.trace.fixture",DISPATCH_QUEUE_SERIAL);__block A23ThreeEpochSDKDriver *driver;__block id<A23TripleResources> lease;
    A23TripleSimulationProvider *provider=pairProvider(op,q,YES,^(uint32_t message){(void)message;});
    SDKModelJournal *journal=[SDKModelJournal new];journal.interface=r;journal.fault=name;journal.journal=[[A23SimulationJournal alloc] initWithPath:[directory stringByAppendingPathComponent:@"session.jsonl"] error:NULL];
    dispatch_sync(q,^{lease=[provider openCandidate:pairCandidate() error:NULL];assert(lease);for(NSData *d in lease.dataStores)assert(pairZero(d));driver=[[A23ThreeEpochSDKDriver alloc] initWithResources:lease firstSequence:177 directory:directory queue:q clock:r.clock journal:journal error:NULL];assert(driver && [driver start]);});
    for(unsigned n=0;n<3;++n){
        __block BOOL stopped;dispatch_sync(q,^{stopped=[driver.result[@"stopped"] boolValue];});if(stopped)break;
        [r deliver:n];dispatch_sync(q,^{[driver poll];});
        if(n<2)dispatch_sync(q,^{
            if(n==1 && messages[name]){
                unsigned count=[name isEqual:@"overflow"]?10:1;
                for(unsigned i=0;i<count;++i)r.interest([messages[name] unsignedIntValue]);
                // The poison latch must stop the third ISO even before queued pin delivery.
                assert([lease.result[@"interest_seen"] boolValue]);
            }
            [driver poll];
        });
    }
    __block NSDictionary *result,*row;
    dispatch_sync(q,^{[r.clock advanceNS:250000001];[driver poll];[driver saveReceiptOnce];result=driver.result;
        BOOL normal=[name isEqual:@"normal"];assert([result[@"complete"] boolValue]==normal && r.submissions==(normal?3:2) && !r.destroys);
        NSDictionary *trace=result[@"lease"][@"interest_trace"];
        assert([trace[@"claimed"] unsignedIntValue]==(normal?0:[name isEqual:@"overflow"]?8:1));
        if(!normal){assert([result[@"stopped"] boolValue]);assert([trace[@"rows"][0][@"message_u32"] unsignedIntValue]==[messages[name] unsignedIntValue]);}
        row=@{@"case":name,@"result":result,@"iso_submissions":@(r.submissions),@"burst_triggers":@(r.triggers),@"real_sdk_objects":@0,@"usb_requests":@0};
    });
    NSData *raw=[NSJSONSerialization dataWithJSONObject:row options:NSJSONWritingSortedKeys error:NULL];fwrite(raw.bytes,1,raw.length,stdout);puts("");return 0;
}}
