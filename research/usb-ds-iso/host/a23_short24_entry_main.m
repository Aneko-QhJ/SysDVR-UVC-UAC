#import "a23_short24_runtime.h"
#import "a23_short24_launch_config.h" // Generated from verified local artifacts.
#include <CommonCrypto/CommonDigest.h>
#include <IOKit/IOKitLib.h>
#include <signal.h>
#include <stdatomic.h>
#include <stdlib.h>
#include <sys/statvfs.h>
#include <unistd.h>
static volatile sig_atomic_t stopWanted;
static void stopSignal(int s){(void)s;stopWanted=1;}
static NSString *sha(NSData *d){unsigned char h[32];CC_SHA256(d.bytes,(CC_LONG)d.length,h);NSMutableString *s=[NSMutableString string];
    for(unsigned i=0;i<32;i++)[s appendFormat:@"%02x",h[i]];return s;}
static int print(id v){NSData *d=[NSJSONSerialization dataWithJSONObject:v options:NSJSONWritingSortedKeys error:NULL];
    if(!d)return 2;fwrite(d.bytes,1,d.length,stdout);puts("");return 0;}
static BOOL flag(id v,BOOL expected){return [v isKindOfClass:NSNumber.class] && CFGetTypeID((__bridge CFTypeRef)v)==CFBooleanGetTypeID() && [v boolValue]==expected;}
static BOOL integer(id v,unsigned n){return [v isKindOfClass:NSNumber.class] && CFGetTypeID((__bridge CFTypeRef)v)!=CFBooleanGetTypeID() &&
    !CFNumberIsFloatType((__bridge CFNumberRef)v) && [v isEqual:@(n)];}
static NSString *canonical(NSString *p){char *s=realpath(p.fileSystemRepresentation,NULL);if(!s)return nil;NSString *r=@(s);free(s);return r;}
static NSDictionary *describe(void){return @{@"schema":@"A23-short24-entry-description-1",@"recipe":A23LaunchRecipe,
    @"package_manifest_sha256":A23LaunchPackageManifest,@"nsp_sha256":A23LaunchNSP,@"ips_sha256":A23LaunchIPS,
    @"baseline_manifest_sha256":A23LaunchBaseline,@"first_sequence":@513,@"last_sequence":@528,
    @"max_bursts":@1,@"wait_seconds":@120,@"capture_poll_budget_seconds":@5,
    @"first_frame_lead":@32,@"transaction_count":@128,@"packet_bytes":@24,
    @"holding_policy":@"remain_alive_after_native_open_no_release_no_retry",@"hardware_verified":@NO,
    @"current_authorization_issued":@NO,@"process_exit_after_capture_authorized":@NO};}
static NSDictionary *authorization(NSString *path,NSString *binary,BOOL allowModel){
    NSData *raw=[NSData dataWithContentsOfFile:path];if(!raw || raw.length>16384)return nil;
    id value=[NSJSONSerialization JSONObjectWithData:raw options:0 error:NULL];if(![value isKindOfClass:NSDictionary.class])return nil;
    NSDictionary *a=value;BOOL model=flag(a[@"model_only"],YES);
    if(!flag(a[@"model_only"],model) || (!allowModel && model))return nil;
    if(![a[@"schema"] isEqual:@"A23-short24-once-authorization-1"] || !integer(a[@"first_sequence"],513) ||
       !integer(a[@"last_sequence"],528) || !integer(a[@"max_bursts"],1))return nil;
    if(![a[@"nonce"] isKindOfClass:NSString.class])return nil;
    NSUUID *nonce=[[NSUUID alloc] initWithUUIDString:a[@"nonce"]];if(!nonce)return nil;
    NSData *binaryBytes=[NSData dataWithContentsOfFile:binary];if(!binaryBytes.length)return nil;
    NSDictionary *expected=@{@"recipe":A23LaunchRecipe,@"package_manifest_sha256":A23LaunchPackageManifest,
        @"nsp_sha256":A23LaunchNSP,@"ips_sha256":A23LaunchIPS,@"baseline_manifest_sha256":A23LaunchBaseline,
        @"receiver_sha256":sha(binaryBytes)};
    for(NSString *k in expected)if(![a[k] isEqual:expected[k]])return nil;
    for(NSString *k in @[@"human_authorized",@"deployment_readback_verified",@"power_off_sd_installed_usb_confirmed"])
        if(!flag(a[k],!model))return nil;
    return a;
}
static NSDictionary *identity(io_service_t service){
    uint64_t iface=0,device=0;io_registry_entry_t parent=IO_OBJECT_NULL;
    if(!IOObjectConformsTo(service,"IOUSBHostInterface") || IORegistryEntryGetRegistryEntryID(service,&iface)!=KERN_SUCCESS ||
       IORegistryEntryGetParentEntry(service,kIOServicePlane,&parent)!=KERN_SUCCESS)return nil;
    BOOL good=IOObjectConformsTo(parent,"IOUSBHostDevice") && IORegistryEntryGetRegistryEntryID(parent,&device)==KERN_SUCCESS;
    CFTypeRef prop=good?IORegistryEntryCreateCFProperty(parent,CFSTR(kUSBHostMatchingPropertySpeed),kCFAllocatorDefault,0):NULL;
    NSNumber *speed=prop && CFGetTypeID(prop)==CFNumberGetTypeID()?(__bridge NSNumber *)prop:nil;
    NSDictionary *r=good && iface && device && [speed isEqual:@3]?@{@"interface_id":@(iface),@"device_id":@(device),@"speed":speed}:nil;
    if(prop)CFRelease(prop);IOObjectRelease(parent);return r;
}
static NSArray *matching(void){
    // Called only after the durable range claim, never by file-only modes.
    NSMutableDictionary *props=CFBridgingRelease([IOUSBHostInterface createMatchingDictionaryWithVendorID:@0x1209 productID:@0xca57
        bcdDevice:nil interfaceNumber:@2 configurationValue:nil interfaceClass:@0xff interfaceSubclass:@0x49 interfaceProtocol:@1
        speed:@3 productIDArray:nil]);if(!props)return nil;
    [props removeObjectForKey:@"IOProviderClass"];CFMutableDictionaryRef match=IOServiceMatching("IOUSBHostInterface");if(!match)return nil;
    CFDictionarySetValue(match,CFSTR(kIOPropertyMatchKey),(__bridge CFDictionaryRef)props);
    io_iterator_t iterator=IO_OBJECT_NULL;if(IOServiceGetMatchingServices(kIOMainPortDefault,match,&iterator)!=KERN_SUCCESS)return nil;
    NSMutableArray *services=[NSMutableArray array];io_service_t service;
    while((service=IOIteratorNext(iterator))){if(services.count<2)[services addObject:@(service)];else IOObjectRelease(service);}
    IOObjectRelease(iterator);return services;
}
static void releaseServices(NSArray *services){for(NSNumber *n in services)IOObjectRelease(n.unsignedIntValue);}
@interface Short24Relay:NSObject
@property(atomic,strong) A23Short24Runtime *runtime;
@property(atomic) BOOL seen;
@end
@implementation Short24Relay @end

int main(int argc,const char **argv){@autoreleasepool{
    if(argc==2 && !strcmp(argv[1],"--describe"))return print(describe());
    BOOL check=argc==3 && !strcmp(argv[1],"--check-authorization");
    BOOL run=argc==4 && !strcmp(argv[1],"--acquire-once");
    if(!check && !run){fputs("Use --describe or --check-authorization; acquisition requires new human authorization.\n",stderr);return 2;}
    NSString *binary=canonical(@(argv[0]));if(!binary)return 2;
    NSDictionary *a=authorization(@(argv[2]),binary,check);if(!a){fputs("Authorization absent, model-only or mismatched; no device accessed.\n",stderr);return 2;}
    if(check)return print(@{@"schema":@"A23-short24-authorization-check-1",@"model_only":a[@"model_only"],@"claimed":@NO,@"device_accessed":@NO});
    // File/readiness checks and single-use range consumption precede ALL SDK,
    // registry, port or service access. Never creates an authorization itself.
    NSString *runPath=@(argv[3]);NSString *parent=canonical(runPath.stringByDeletingLastPathComponent);
    if(![parent isEqual:[A23LaunchPrivate stringByAppendingPathComponent:@"runs"]] ||
       ![runPath isEqual:[parent stringByAppendingPathComponent:runPath.lastPathComponent]] ||
       [runPath.lastPathComponent isEqual:@"."] || [runPath.lastPathComponent isEqual:@".."] ||
       [[NSFileManager defaultManager] fileExistsAtPath:runPath])return 2;
    struct statvfs fs;if(statvfs(parent.fileSystemRepresentation,&fs) || (__uint128_t)fs.f_bavail*fs.f_frsize<4*1024*1024)return 2;
    NSString *scope=[A23LaunchPrivate stringByAppendingPathComponent:@"short24-once"];
    NSError *error=nil;BOOL dir=[[NSFileManager defaultManager] createDirectoryAtPath:scope withIntermediateDirectories:NO attributes:nil error:&error];
    BOOL isDir=NO;if(!dir && !([[NSFileManager defaultManager] fileExistsAtPath:scope isDirectory:&isDir] && isDir))return 2;
    error=nil;if(!A23Short24WriteRecord(scope,@"513-528.CONSUMED",@{@"schema":@"A23-short24-range-consumed-1",@"authorization":a,
        @"run_directory":runPath,@"pid":@(getpid()),@"remaining":@0},&error)){fputs("Range claim exists or failed; no device accessed.\n",stderr);return 2;}
    if(![[NSFileManager defaultManager] createDirectoryAtPath:runPath withIntermediateDirectories:NO attributes:nil error:NULL])return 2;
    signal(SIGINT,stopSignal);signal(SIGTERM,stopSignal);
    NSArray *initial=matching();if(!initial || initial.count){releaseServices(initial);A23Short24WriteRecord(runPath,@"preflight-failure.json",@{@"reason":@"device must be absent before WAITING",@"native_open_attempted":@NO},NULL);return 1;}
    puts("WAITING short24: boot only after this line; one burst; native-open process remains resident.");fflush(stdout);
    dispatch_queue_t queue=dispatch_queue_create("short24.entry",DISPATCH_QUEUE_SERIAL);Short24Relay *relay=[Short24Relay new];
    __block IOUSBHostInterface *interface=nil;__block IOUSBHostPipe *pipe=nil;__block A23Short24SDKIO *io=nil;
    __block A23Short24Capture *capture=nil;__block A23Short24Runtime *runtime=nil;
    __block BOOL nativeTouched=NO,reported=NO,stopSent=NO;__block io_service_t selected=IO_OBJECT_NULL;
    __block NSDictionary *selectedIdentity=nil;uint64_t begin=A23Short24NowNanoseconds();
    dispatch_source_t timer=dispatch_source_create(DISPATCH_SOURCE_TYPE_TIMER,0,0,queue);
    dispatch_source_set_timer(timer,dispatch_time(DISPATCH_TIME_NOW,10000000),10000000,1000000);
    dispatch_source_set_event_handler(timer,^{
        if(!nativeTouched){
            if(stopWanted || A23Short24NowNanoseconds()-begin>120000000000ULL){
                A23Short24WriteRecord(runPath,@"wait-result.json",@{@"reason":@"wait ended before native open",@"native_open_attempted":@NO},NULL);exit(1);
            }
            NSArray *services=matching();if(!services || services.count>1){releaseServices(services);
                A23Short24WriteRecord(runPath,@"wait-result.json",@{@"reason":@"ambiguous or failed registry match",@"native_open_attempted":@NO},NULL);exit(1);}
            if(!services.count)return;
            selected=[services[0] unsignedIntValue];selectedIdentity=identity(selected);
            if(!selectedIdentity){IOObjectRelease(selected);selected=0;A23Short24WriteRecord(runPath,@"wait-result.json",@{@"reason":@"identity invalid before native open"},NULL);exit(1);}
            nativeTouched=YES;NSError *openError=nil;
            interface=[[IOUSBHostInterface alloc] initWithIOService:selected options:IOUSBHostObjectInitOptionsNone queue:queue error:&openError
                interestHandler:^(IOUSBHostObject *o,uint32_t message,void *arg){(void)o;(void)arg;relay.seen=YES;[relay.runtime providerInterest:message];}];
            if(interface && [identity(selected) isEqual:selectedIdentity])pipe=[interface copyPipeWithAddress:0x83 error:&openError];
            if(pipe)io=[[A23Short24SDKIO alloc] initWithInterface:interface pipe:pipe queue:queue speed:3 error:&openError];
            if(io)capture=[[A23Short24Capture alloc] initWithIO:io queue:queue clockNanoseconds:^uint64_t{return A23Short24NowNanoseconds();}
                recipe:A23LaunchRecipe firstSequence:513];
            NSDictionary *context=@{@"schema":@"A23-short24-entry-context-1",@"authorization":a,@"identity":selectedIdentity,
                @"receiver_sha256":sha([NSData dataWithContentsOfFile:binary]),@"model_only":@NO};
            if(capture)runtime=[[A23Short24Runtime alloc] initWithCapture:capture queue:queue directory:runPath context:context
                clockNanoseconds:^uint64_t{return A23Short24NowNanoseconds();}];
            relay.runtime=runtime;
            if(runtime && !relay.seen)[runtime start];
            else A23Short24WriteRecord(runPath,@"native-preparation-failure.json",@{@"reason":relay.seen?@"interest before start":@"SDK preparation failed",
                @"error_domain":openError.domain ?: @"none",@"error_code":@(openError.code),@"retained":@YES,@"process_exit_authorized":@NO},NULL);
        }
        if(stopWanted && !stopSent){stopSent=YES;[runtime requestStop];}
        [runtime poll];NSDictionary *state=runtime.result;
        if(!reported && (!runtime || [state[@"observation_attempted"] boolValue] || ![state[@"started"] boolValue])){
            reported=YES;A23Short24WriteRecord(runPath,@"runtime-held.json",state ?: @{@"retained_after_native_preparation":@YES,@"process_exit_authorized":@NO},NULL);
            puts("HELD short24: evidence save attempted; resources retained. No retry or automatic exit.");fflush(stdout);
        }
        // No destroy, release, exit or second submission after native touch.
        (void)interface;(void)pipe;(void)io;(void)capture;(void)selected;
    });
    dispatch_resume(timer);dispatch_main();
}}
