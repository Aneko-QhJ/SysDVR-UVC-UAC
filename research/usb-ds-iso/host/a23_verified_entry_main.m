#import "a23_scope_verifier.h"
#include <stdlib.h>
#include <string.h>
static int print(NSDictionary *v){NSData *r=[NSJSONSerialization dataWithJSONObject:v options:NSJSONWritingSortedKeys error:NULL];if(!r)return 2;fwrite(r.bytes,1,r.length,stdout);puts("");return 0;}
int main(int argc,const char *argv[]){@autoreleasepool {
    if(argc==2 && !strcmp(argv[1],"--describe"))return print(A23VerifiedEntryDescription());
    if(argc==3 && (!strcmp(argv[1],"--check-build") || !strcmp(argv[1],"--check-archive"))){
        char *p=realpath(argv[0],NULL);if(!p)return 2;NSString *binary=@(p);free(p);NSString *build=@(argv[2]);if(![binary isEqual:[build stringByAppendingPathComponent:@"verified-entry"]])return 2;
        BOOL live=!strcmp(argv[1],"--check-build");A23ReadOnlyScopeVerifier *v=live ? [[A23ReadOnlyScopeVerifier alloc] initWithBuild:build] : [[A23ReadOnlyScopeVerifier alloc] initWithArchive:build];BOOL ok=live ? [v verifyCore] : [v verifyArchive];
        return ok ? print(@{@"schema":@"A23-verified-entry-file-check-1",@"live_sources_checked":@(live),@"scope":v.scope,@"verifier":v.result,@"formal_issuance_available":@NO,@"hardware_entry_enabled":@NO}) : 2;
    }
    if(argc==2 && !strcmp(argv[1],"--inspect-context")){char *p=realpath(argv[0],NULL);if(!p)return 2;NSString *binary=@(p);free(p);NSDictionary *c=A23ReadExecutionContext(binary);return print(@{@"schema":@"A23-verified-entry-context-1",@"context":c,@"policy_pass":@(A23ValidateExecutionContext(c,c[@"receiver_sha256"])),@"hardware_entry_enabled":@NO});}
    fputs("Only file checks/context inspection are implemented; acquisition is unavailable.\n",stderr);return 2;
}}
