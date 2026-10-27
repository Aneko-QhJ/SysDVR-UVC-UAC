#import "a23_two_epoch_entry.h"
#include <stdlib.h>
#include <string.h>
static int print(NSDictionary *v){NSData *d=[NSJSONSerialization dataWithJSONObject:v options:NSJSONWritingSortedKeys error:NULL];if(!d)return 2;fwrite(d.bytes,1,d.length,stdout);puts("");return 0;}
int main(int argc,const char *argv[]){@autoreleasepool {
    if(argc==2 && !strcmp(argv[1],"--describe"))return print(A23TwoEpochEntryDescription());
    BOOL check=argc==3 && !strcmp(argv[1],"--check-build"),inspect=argc==2 && !strcmp(argv[1],"--inspect-context");
    if(!check && !inspect){fputs("Only --describe, --check-build PATH and --inspect-context are available. Acquisition is not implemented in this executable.\n",stderr);return 2;}
    char *p=realpath(argv[0],NULL);if(!p)return 2;NSString *binary=@(p);free(p);
    if(check){NSDictionary *r=A23TwoEpochEntryCheckBuild(@(argv[2]),binary);return r ? print(r) : 2;}
    NSDictionary *c=A23ReadExecutionContext(binary);return print(@{@"schema":@"A23-two-epoch-entry-context-inspection-1",@"context":c,@"policy":A23ExecutionContextPolicy(),@"policy_pass":@(A23ValidateExecutionContext(c,c[@"receiver_sha256"])),@"usb_open_permission_proven":@NO,@"hardware_entry_enabled":@NO});
}}
