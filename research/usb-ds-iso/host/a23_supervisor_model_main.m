// File/context-only child. No registry enumeration, SDK objects or USB requests.
#import "a23_execution_context.h"
#include <CommonCrypto/CommonDigest.h>
#include <unistd.h>
static NSString *sha(NSData *r){unsigned char h[32];CC_SHA256(r.bytes,(CC_LONG)r.length,h);NSMutableString *s=[NSMutableString new];for(unsigned i=0;i<32;i++)[s appendFormat:@"%02x",h[i]];return s;}
static NSData *json(id v){NSMutableData *d=[[NSJSONSerialization dataWithJSONObject:v options:NSJSONWritingSortedKeys|NSJSONWritingWithoutEscapingSlashes error:NULL] mutableCopy];[d appendBytes:"\n" length:1];return d;}
static void emit(NSData *r){fwrite(r.bytes,1,r.length,stdout);fflush(stdout);}
int main(int argc,const char *argv[]){@autoreleasepool {
    if(argc!=4 || strcmp(argv[1],"--model"))return 2;NSString *mode=@(argv[2]);
    NSArray *modes=@[@"normal",@"hold-before",@"hold-after",@"nonce",@"pid",@"ppid",@"uid",@"bool-pid",@"binary",@"path",@"environment",@"handoff",@"duplicate",@"trailing",@"partial",@"stdout-limit",@"stderr-limit",@"exit3",@"no-hello"];
    if(![modes containsObject:mode])return 2;NSData *raw=[NSData dataWithContentsOfFile:@(argv[3])];NSDictionary *h=raw ? [NSJSONSerialization JSONObjectWithData:raw options:0 error:NULL] : nil;if(![h isKindOfClass:NSDictionary.class])return 3;
    if([mode isEqual:@"hold-before"])(void)getchar();
    if([mode isEqual:@"no-hello"])return 0;
    char *p=realpath(argv[0],NULL);if(!p)return 3;NSMutableDictionary *context=[A23ReadExecutionContext(@(p)) mutableCopy];free(p);
    if([mode isEqual:@"pid"])context[@"pid"]=@1;
    if([mode isEqual:@"ppid"])context[@"ppid"]=@1;
    if([mode isEqual:@"uid"])context[@"uid"]=@999999;
    if([mode isEqual:@"bool-pid"])context[@"pid"]=@YES;
    if([mode isEqual:@"binary"])context[@"receiver_sha256"]=[@"0" stringByPaddingToLength:64 withString:@"0" startingAtIndex:0];
    if([mode isEqual:@"path"])context[@"receiver_path"]=@"/injected/wrong-path";
    if([mode isEqual:@"environment"])setenv("PYTHONPATH","injected",1);
    NSMutableDictionary *environment=[NSMutableDictionary new];for(NSString *key in @[@"LANG",@"LC_ALL",@"PATH",@"TMPDIR"]){const char *v=getenv(key.UTF8String);if(!v)return 3;environment[key]=@(v);}
    BOOL forbidden=NO;for(NSString *key in @[@"DYLD_INSERT_LIBRARIES",@"DYLD_LIBRARY_PATH",@"LD_PRELOAD",@"PYTHONPATH",@"PYTHONHOME"])if(getenv(key.UTF8String))forbidden=YES;
    NSDictionary *hello=@{@"schema":@"A23-supervisor-model-hello-1",@"nonce":[mode isEqual:@"nonce"]?@"wrong":h[@"nonce"],@"handoff_sha256":sha(raw),@"environment_sha256":sha(json(environment)),@"forbidden_environment_present":@(forbidden),@"context":context,@"hardware_entry_enabled":@NO};
    if([mode isEqual:@"handoff"] && ![[@"changed\n" dataUsingEncoding:NSUTF8StringEncoding] writeToFile:@(argv[3]) options:0 error:NULL])return 3;
    NSData *line=json(hello);
    if([mode isEqual:@"stdout-limit"]){char bytes[8192];memset(bytes,'x',sizeof(bytes));emit([NSData dataWithBytes:bytes length:sizeof(bytes)]);return 0;}
    if([mode isEqual:@"partial"]){emit([line subdataWithRange:NSMakeRange(0,line.length-1)]);return 0;}
    emit(line);
    if([mode isEqual:@"duplicate"])emit(line);
    if([mode isEqual:@"trailing"])emit([@"unexpected\n" dataUsingEncoding:NSUTF8StringEncoding]);
    if([mode isEqual:@"stderr-limit"]){char bytes[1024];memset(bytes,'e',sizeof(bytes));fwrite(bytes,1,sizeof(bytes),stderr);fflush(stderr);}
    if([mode isEqual:@"hold-after"])(void)getchar();
    return [mode isEqual:@"exit3"]?3:0;
}}
