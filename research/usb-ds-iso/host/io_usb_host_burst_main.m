#import "io_usb_host_burst_entry.h"
#include <IOKit/IOMessage.h>
#include <signal.h>
static volatile sig_atomic_t exitWanted;
static void requestExit(int number) { (void)number;exitWanted=1; }
int main(int argc,const char *argv[])
{
    @autoreleasepool {
        if(argc==2 && !strcmp(argv[1],"--describe")){
            NSData *raw=[NSJSONSerialization dataWithJSONObject:A23DormantBurstSDKPlan()
                options:NSJSONWritingSortedKeys|NSJSONWritingWithoutEscapingSlashes error:NULL];
            puts([[NSString alloc] initWithData:raw encoding:NSUTF8StringEncoding].UTF8String);return 0;
        }
        if(argc!=3 || strcmp(argv[1],"--acquire-once")){
            fputs("Use --describe. Single burst requires a separately issued consumed receipt; no USB accessed.\n",stderr);return 2;
        }
        NSError *error=nil;NSString *directory=@(argv[2]);
        if(!A23ClaimBurstReceipt(directory,@(argv[0]),&error)){fprintf(stderr,"%s\n",error.localizedDescription.UTF8String);return 2;}
        if(@available(macOS 26.4,*)){}else{fputs("Mapped SDK API requires macOS 26.4+.\n",stderr);return 2;}
        signal(SIGINT,requestExit);signal(SIGTERM,requestExit);
        dispatch_queue_t queue=dispatch_queue_create("a23.io-usb-host.single-burst",DISPATCH_QUEUE_SERIAL);
        NSString *host=[directory stringByAppendingPathComponent:@"host"];
        if(![[NSFileManager defaultManager] createDirectoryAtPath:host withIntermediateDirectories:NO attributes:nil error:NULL])return 2;
        A23BurstEntry *entry=[[A23BurstEntry alloc] initWithDirectory:host queue:queue clock:[A23LocalMachClock new]];
        if(!entry)return 2;entry.interruptionRequested=^BOOL{return exitWanted!=0;};
        dispatch_source_t timer=dispatch_source_create(DISPATCH_SOURCE_TYPE_TIMER,0,0,queue);__block BOOL retainedReported=NO;
        dispatch_source_set_timer(timer,dispatch_time(DISPATCH_TIME_NOW,10000000),10000000,1000000);
        dispatch_source_set_event_handler(timer,^{
            [entry poll];NSDictionary *result=entry.result;
            if([result[@"unresolved"] boolValue] && !retainedReported){
                retainedReported=YES;A23SaveBurstEntryResult(directory,@"entry-retained.json",result);
                fputs("Burst unresolved: keep receiver and SDK buffers alive; no retry or forced exit.\n",stderr);fflush(stderr);
            }
            if([result[@"finished"] boolValue]){
                BOOL saved=A23SaveBurstEntryResult(directory,@"entry-result.json",result);exit(saved ? [result[@"exit_code"] intValue] : 1);
            }
        });
        dispatch_async(queue,^{
            A23DormantSDKOperations *operations=[A23DormantSDKOperations new];
            CFMutableDictionaryRef matching=exitWanted ? NULL : A23CreateMatchingDictionary();io_iterator_t iterator=IO_OBJECT_NULL;
            kern_return_t code=matching ? IOServiceGetMatchingServices(kIOMainPortDefault,matching,&iterator) : kIOReturnError;
            NSMutableArray *services=[NSMutableArray array];io_service_t service;
            if(code==KERN_SUCCESS)while((service=IOIteratorNext(iterator)))[services addObject:@(service)];
            if(iterator)IOObjectRelease(iterator);
            NSMutableArray *candidates=[NSMutableArray array];NSError *identityError=nil;
            if(services.count==1 && !exitWanted){
                NSDictionary *identity=[operations identityForService:[services[0] unsignedIntValue] error:&identityError];
                if(identity){NSMutableDictionary *candidate=[identity mutableCopy];candidate[@"service_token"]=services[0];[candidates addObject:candidate];}
            }else if(services.count>1)for(NSUInteger i=0;i<services.count;++i)[candidates addObject:@{}];
            NSDictionary *selection=@{@"schema":@"A23-burst-sdk-selection-1",@"matched_service_count":@(services.count),
                @"registry_result_u32":@((uint32_t)code),@"identity_error":identityError ? A23PreparationErrorDetails(identityError) : (id)NSNull.null,
                @"hardware_verified":@NO};
            if(!A23SaveBurstEntryResult(directory,@"selection.json",selection)){[entry requestExit];[candidates removeAllObjects];}
            uint64_t interfaceID=[candidates.firstObject[@"interface_id"] unsignedLongLongValue];
            A23AdapterSDKProvider *provider=[[A23AdapterSDKProvider alloc] initWithOperations:operations queue:queue interest:^(uint32_t message){
                if(message==kIOMessageServiceIsTerminated)[entry detachedRegistryID:interfaceID];
                else if(message==kIOMessageServiceIsRequestingClose)[entry requestExit];
            }];
            [entry startCandidates:candidates provider:provider];
            for(NSNumber *token in services)IOObjectRelease(token.unsignedIntValue);
        });
        dispatch_resume(timer);dispatch_main();
    }
}
