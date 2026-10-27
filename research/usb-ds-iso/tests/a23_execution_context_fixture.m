#import "a23_execution_context.h"
#import <IOUSBHost/IOUSBHost.h>
#include <assert.h>

int main(int argc,const char *argv[])
{
    @autoreleasepool {
        // Reference the class to retain the linked image; do not initialize it.
        assert(NSClassFromString(@"IOUSBHostInterface")!=Nil);
        if(argc==2){
            NSDictionary *context=A23ReadExecutionContext(@(argv[1]));
            NSData *raw=[NSJSONSerialization dataWithJSONObject:context options:NSJSONWritingSortedKeys error:NULL];
            assert(raw);fwrite(raw.bytes,1,raw.length,stdout);putchar('\n');return 0;
        }
        assert(argc==1);
        NSDictionary *actual=A23ReadExecutionContext(@(argv[0]));
        assert(CFGetTypeID((__bridge CFTypeRef)actual[@"sandbox_query_available"])==CFBooleanGetTypeID());
        // Preserve every real observation except the admitted sandbox result;
        // this catches serializer/type errors that synthetic vectors miss.
        NSMutableDictionary *normalized=[actual mutableCopy];normalized[@"sandbox_query_result"]=@0;normalized[@"sandbox_query_errno"]=@0;
        assert(A23ValidateExecutionContext(normalized,actual[@"receiver_sha256"]));
        NSString *sha=[@"" stringByPaddingToLength:64 withString:@"a" startingAtIndex:0];
        NSDictionary *valid=@{@"schema":@"A23-execution-context-1",@"pid":@123,@"ppid":@122,@"uid":@501,@"euid":@501,@"gid":@20,@"egid":@20,
            @"os_build":@"26A434",@"os_version":@"27.0.1",@"machine":@"arm64",@"receiver_path":@"/private/tmp/receiver",@"receiver_sha256":sha,
            @"framework_uuid":@"B0D41EEF-C9BF-39DD-A1C4-226DCB94E78B",@"sandbox_query_available":@YES,
            @"sandbox_query_result":@0,@"sandbox_query_errno":@0,@"sample_begin_ticks":@1,@"sample_end_ticks":@2,
            @"usb_open_permission_proven":@NO,@"automatic_privilege_change":@NO};
        assert(A23ValidateExecutionContext(valid,sha));
        NSArray *faults=@[@{@"sandbox_query_result":@1},@{@"sandbox_query_result":@(-1)},@{@"sandbox_query_result":@NO},
            @{@"sandbox_query_available":@NO},@{@"sandbox_query_errno":@1},@{@"os_build":@"other"},@{@"framework_uuid":@"other"},
            @{@"receiver_sha256":@"wrong"},@{@"sample_end_ticks":@0},@{@"pid":@YES},@{@"usb_open_permission_proven":@YES},
            @{@"automatic_privilege_change":@YES},@{@"unexpected":@1}];
        for(NSDictionary *fault in faults){NSMutableDictionary *c=[valid mutableCopy];[c addEntriesFromDictionary:fault];assert(!A23ValidateExecutionContext(c,sha));}
        for(NSString *key in valid){NSMutableDictionary *c=[valid mutableCopy];[c removeObjectForKey:key];assert(!A23ValidateExecutionContext(c,sha));}
        printf("context admission: valid1 faults%lu missing%lu; native USB/SD0\n",(unsigned long)faults.count,(unsigned long)valid.count);
    }return 0;
}
