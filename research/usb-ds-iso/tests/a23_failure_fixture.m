// Fault injection around the frozen fake SDK main; no real device operations.
static NSString *failureName,*failureExecution;
static char *failureRead(char *line,int size,FILE *stream){
    char *value=fgets(line,size,stream);
    if([@[@"exit-after-command",@"partial-report",@"non-object-report",@"empty-report"] containsObject:failureName]){
        NSData *raw=nil;
        if([failureName isEqual:@"partial-report"])raw=[@"{\"schema\":" dataUsingEncoding:NSUTF8StringEncoding];
        if([failureName isEqual:@"non-object-report"])raw=[@"[]\n" dataUsingEncoding:NSUTF8StringEncoding];
        if([failureName isEqual:@"empty-report"])raw=[NSData data];
        if(raw && ![raw writeToFile:[failureExecution stringByAppendingPathComponent:@"report.json"] options:NSDataWritingWithoutOverwriting error:NULL])_exit(79);
        _exit(72);
    }
    return value;
}
static int failureMain(int argc,const char *argv[]){@autoreleasepool {
    if(argc!=4)return 2;
    NSString *root=@(argv[3]).stringByDeletingLastPathComponent.stringByDeletingLastPathComponent;
    failureName=brokerLoad([root stringByAppendingPathComponent:@"plan.json"])[@"case"];
    failureExecution=[root stringByAppendingPathComponent:@"execution"];
    if([failureName isEqual:@"exit-before-hello"])_exit(71);
    if([failureName isEqual:@"partial-hello"]){fputs("{\"schema\":",stdout);fflush(stdout);_exit(71);}
    return frozenBrokerMain(argc,argv);
}}
int main(int argc,const char *argv[]){return failureMain(argc,argv);}
