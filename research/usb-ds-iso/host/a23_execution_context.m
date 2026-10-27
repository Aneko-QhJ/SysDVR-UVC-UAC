#import "a23_execution_context.h"
#include <CommonCrypto/CommonDigest.h>
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <mach-o/dyld.h>
#include <mach/mach_time.h>
#include <sys/stat.h>
#include <sys/sysctl.h>
#include <unistd.h>

NSDictionary *A23ExecutionContextPolicy(void)
{
    return @{@"schema":@"A23-execution-context-policy-1",@"sample_before":@"process_claim_and_native_wait",
        @"required_os_build":@"26A434",@"required_framework_uuid":@"B0D41EEF-C9BF-39DD-A1C4-226DCB94E78B",
        @"sandbox_query":@"sandbox_check(self,NULL,0)",@"required_sandbox_result":@0,
        @"usb_open_permission_proven":@NO,@"automatic_privilege_change":@NO};
}
static NSString *systemString(const char *name)
{
    char bytes[256]={0};size_t size=sizeof(bytes);
    if(sysctlbyname(name,bytes,&size,NULL,0) || !size || size>sizeof(bytes) || bytes[size-1])return @"";
    return @(bytes);
}
static NSString *binarySHA(NSString *path)
{
    char *resolved=realpath(path.fileSystemRepresentation,NULL);
    BOOL canonical=resolved && [path isEqual:@(resolved)];free(resolved);if(!canonical)return @"";
    int fd=open(path.fileSystemRepresentation,O_RDONLY|O_NOFOLLOW|O_NONBLOCK);if(fd<0)return @"";
    struct stat st;BOOL ok=!fstat(fd,&st) && S_ISREG(st.st_mode) && st.st_size>0 && st.st_size<=64*1024*1024;
    CC_SHA256_CTX state;CC_SHA256_Init(&state);unsigned char buffer[65536];off_t count=0;
    while(ok){ssize_t n=read(fd,buffer,sizeof(buffer));if(n<0 && errno==EINTR)continue;
        if(n<0){ok=NO;break;}if(!n)break;count+=n;if(count>st.st_size){ok=NO;break;}CC_SHA256_Update(&state,buffer,(CC_LONG)n);}
    close(fd);if(!ok || count!=st.st_size)return @"";
    unsigned char digest[CC_SHA256_DIGEST_LENGTH];CC_SHA256_Final(digest,&state);
    NSMutableString *result=[NSMutableString string];for(unsigned i=0;i<sizeof(digest);i++)[result appendFormat:@"%02x",digest[i]];return result;
}
static NSString *frameworkUUID(void)
{
    const char *path="/System/Library/Frameworks/IOUSBHost.framework/Versions/A/IOUSBHost";
    for(uint32_t i=0;i<_dyld_image_count();i++)if(!strcmp(_dyld_get_image_name(i),path)){
        const struct mach_header_64 *head=(const void *)_dyld_get_image_header(i);
        if(head->magic!=MH_MAGIC_64)return @"";
        const uint8_t *end=(const uint8_t *)(head+1)+head->sizeofcmds;
        const struct load_command *command=(const void *)(head+1);
        for(uint32_t j=0;j<head->ncmds;j++){
            if((const uint8_t *)command+sizeof(*command)>end || command->cmdsize<sizeof(*command) ||
                command->cmdsize>(size_t)(end-(const uint8_t *)command))return @"";
            if(command->cmd==LC_UUID && command->cmdsize==sizeof(struct uuid_command))
                return [[NSUUID alloc] initWithUUIDBytes:((const struct uuid_command *)command)->uuid].UUIDString;
            command=(const void *)((const uint8_t *)command+command->cmdsize);
        }
    }
    return @"";
}
NSDictionary *A23ReadExecutionContext(NSString *binary)
{
    uint64_t begin=mach_absolute_time();
    // Null operation asks about this process's sandbox only. It neither tests
    // an IOKit operation nor changes a sandbox. Missing/unknown results stop.
    int (*query)(pid_t,const char *,int,...)=dlsym(RTLD_DEFAULT,"sandbox_check");
    errno=0;int status=query ? query(getpid(),NULL,0) : -1;int saved=query ? errno : ENOSYS;
    return @{@"schema":@"A23-execution-context-1",@"pid":@(getpid()),@"ppid":@(getppid()),
        @"uid":@(getuid()),@"euid":@(geteuid()),@"gid":@(getgid()),@"egid":@(getegid()),
        @"os_build":systemString("kern.osversion"),@"os_version":systemString("kern.osproductversion"),
        @"machine":systemString("hw.machine"),@"receiver_path":binary,@"receiver_sha256":binarySHA(binary),
        @"framework_uuid":frameworkUUID(),@"sandbox_query_available":@((BOOL)(query!=NULL)),
        @"sandbox_query_result":@(status),@"sandbox_query_errno":@(saved),
        @"sample_begin_ticks":@(begin),@"sample_end_ticks":@(mach_absolute_time()),
        @"usb_open_permission_proven":@NO,@"automatic_privilege_change":@NO};
}
static BOOL number(id value)
{
    return [value isKindOfClass:NSNumber.class] && CFGetTypeID((__bridge CFTypeRef)value)!=CFBooleanGetTypeID() &&
        !CFNumberIsFloatType((__bridge CFNumberRef)value) && ![[value description] hasPrefix:@"-"];
}
static BOOL flag(id value,BOOL expected)
{return [value isKindOfClass:NSNumber.class] && CFGetTypeID((__bridge CFTypeRef)value)==CFBooleanGetTypeID() && [value boolValue]==expected;}
BOOL A23ValidateExecutionContext(NSDictionary *c,NSString *receiverSHA)
{
    NSSet *keys=[NSSet setWithArray:@[@"schema",@"pid",@"ppid",@"uid",@"euid",@"gid",@"egid",@"os_build",@"os_version",@"machine",
        @"receiver_path",@"receiver_sha256",@"framework_uuid",@"sandbox_query_available",@"sandbox_query_result",@"sandbox_query_errno",
        @"sample_begin_ticks",@"sample_end_ticks",@"usb_open_permission_proven",@"automatic_privilege_change"]];
    if(![c isKindOfClass:NSDictionary.class] || ![[NSSet setWithArray:c.allKeys] isEqual:keys] ||
       ![c[@"schema"] isEqual:@"A23-execution-context-1"])return NO;
    for(NSString *key in @[@"pid",@"ppid",@"uid",@"euid",@"gid",@"egid",@"sample_begin_ticks",@"sample_end_ticks",@"sandbox_query_result",@"sandbox_query_errno"])
        if(!number(c[key]))return NO;
    for(NSString *key in @[@"os_build",@"os_version",@"machine",@"receiver_path",@"receiver_sha256",@"framework_uuid"])
        if(![c[key] isKindOfClass:NSString.class] || ![c[key] length])return NO;
    NSDictionary *policy=A23ExecutionContextPolicy();
    return [c[@"pid"] unsignedLongLongValue]>0 && [c[@"sample_begin_ticks"] unsignedLongLongValue]>0 &&
        [c[@"sample_end_ticks"] unsignedLongLongValue]>=[c[@"sample_begin_ticks"] unsignedLongLongValue] &&
        [c[@"receiver_path"] isAbsolutePath] && receiverSHA.length==64 && [c[@"receiver_sha256"] isEqual:receiverSHA] &&
        [c[@"os_build"] isEqual:policy[@"required_os_build"]] && [c[@"framework_uuid"] isEqual:policy[@"required_framework_uuid"]] &&
        flag(c[@"sandbox_query_available"],YES) && [c[@"sandbox_query_result"] isEqual:@0] && [c[@"sandbox_query_errno"] isEqual:@0] &&
        flag(c[@"usb_open_permission_proven"],NO) && flag(c[@"automatic_privilege_change"],NO);
}
