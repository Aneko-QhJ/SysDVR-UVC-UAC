/* Included after the sealed guard's file/JSON helpers, in a new generated unit.
 * These checks bind local files only; they do not identify a physical device. */
static BOOL deviceCheck(NSDictionary *binding,NSString *build)
{
    NSDictionary *d=binding[@"device_binding"],*hashes=d[@"artifact_hashes"],*generated=binding[@"generated_hashes"];
    if(![d isKindOfClass:NSDictionary.class] || ![hashes isKindOfClass:NSDictionary.class] || hashes.count!=4 ||
       ![generated isKindOfClass:NSDictionary.class] || generated.count!=4 ||
       ![d[@"schema"] isEqual:@"A23-device-binding-1"] || ![d[@"configuration"] isEqual:@"window-30s"] ||
       ![binding[@"schema"] isEqual:@"A23-waiting-receiver-build-2"] ||
       !hex(d[@"parent_input_digest"]) || !hex(d[@"runtime_recipe_sha256"]) || !hex(d[@"device_elf_sha256"]) ||
       ![binding[@"recipe_sha256"] isEqual:d[@"runtime_recipe_sha256"]] ||
       ![binding[@"device_binding_sha256"] isEqual:sha(encode(d))] ||
       ![readFile([build stringByAppendingPathComponent:@"device-binding.json"],16384) isEqual:encode(d)] ||
       ![hashes[@"full.elf"] isEqual:d[@"device_elf_sha256"]] || !canonical(d[@"device_source_root"]))return NO;
    for(NSString *name in hashes){
        if(!relative(name) || !hex(hashes[name]))return NO;
        NSData *live=readFile([d[@"device_source_root"] stringByAppendingPathComponent:name],32*1024*1024);
        NSData *frozen=readFile([[build stringByAppendingPathComponent:@"device"] stringByAppendingPathComponent:name],32*1024*1024);
        if(!live || !frozen || ![sha(live) isEqual:hashes[name]] || ![sha(frozen) isEqual:hashes[name]])return NO;
    }
    for(NSString *name in generated){
        if(!relative(name) || !hex(generated[name]))return NO;
        NSData *raw=readFile([[build stringByAppendingPathComponent:@"generated"] stringByAppendingPathComponent:name],2*1024*1024);
        if(!raw || ![sha(raw) isEqual:generated[name]])return NO;
    }
    return YES;
}
