/* New generated receiver only. Local software identity, never physical origin. */
static BOOL deviceCheck(NSDictionary *binding,NSString *build)
{
    NSDictionary *d=binding[@"device_binding"],*hashes=d[@"artifact_hashes"],*generated=binding[@"generated_hashes"];
    NSSet *files=[NSSet setWithArray:@[@"full.elf",@"recipe.json",@"symbols.txt",@"source/uvc/ep0_candidate_recipe.h",@"sysmodule.json",@"main.npdm"]];
    if(![d isKindOfClass:NSDictionary.class] || ![hashes isKindOfClass:NSDictionary.class] ||
       ![[NSSet setWithArray:hashes.allKeys] isEqual:files] || ![generated isKindOfClass:NSDictionary.class] || generated.count!=4 ||
       ![d[@"schema"] isEqual:@"A23-path-span-host-device-binding-1"] || ![d[@"configuration"] isEqual:@"path-span-window-30s"] ||
       ![binding[@"schema"] isEqual:@"A23-waiting-receiver-build-5"] ||
       !hex(d[@"parent_input_digest"]) || !hex(d[@"runtime_recipe_sha256"]) || !hex(d[@"device_elf_sha256"]) ||
       !hex(d[@"device_npdm_sha256"]) || !hex(d[@"device_config_sha256"]) || !equal(d[@"main_thread_stack_request_bytes"],@8192) ||
       ![binding[@"recipe_sha256"] isEqual:d[@"runtime_recipe_sha256"]] ||
       ![binding[@"device_binding_sha256"] isEqual:sha(encode(d))] ||
       ![readFile([build stringByAppendingPathComponent:@"device-binding.json"],16384) isEqual:encode(d)] ||
       ![hashes[@"full.elf"] isEqual:d[@"device_elf_sha256"]] || ![hashes[@"main.npdm"] isEqual:d[@"device_npdm_sha256"]] ||
       ![hashes[@"sysmodule.json"] isEqual:d[@"device_config_sha256"]] || !canonical(d[@"device_source_root"]))return NO;
    for(NSString *name in hashes){
        if(!relative(name) || !hex(hashes[name]))return NO;
        NSData *live=readFile([d[@"device_source_root"] stringByAppendingPathComponent:name],32*1024*1024);
        NSData *frozen=readFile([[build stringByAppendingPathComponent:@"device"] stringByAppendingPathComponent:name],32*1024*1024);
        if(!live || !frozen || ![sha(live) isEqual:hashes[name]] || ![sha(frozen) isEqual:hashes[name]])return NO;
    }
    NSData *npdm=readFile([[build stringByAppendingPathComponent:@"device"] stringByAppendingPathComponent:@"main.npdm"],1024*1024);
    const uint8_t *bytes=npdm.bytes;
    if(npdm.length<0x80 || memcmp(bytes,"META",4) || bytes[14]!=44 || bytes[15]!=3 ||
       bytes[28]!=0 || bytes[29]!=0x20 || bytes[30]!=0 || bytes[31]!=0)return NO;
    for(NSString *name in generated){
        if(!relative(name) || !hex(generated[name]))return NO;
        NSData *raw=readFile([[build stringByAppendingPathComponent:@"generated"] stringByAppendingPathComponent:name],2*1024*1024);
        if(!raw || ![sha(raw) isEqual:generated[name]])return NO;
    }
    return YES;
}
