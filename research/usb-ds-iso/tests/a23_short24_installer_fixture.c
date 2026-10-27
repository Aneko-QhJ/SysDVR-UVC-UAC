#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include "iso_runtime_patch.h"
#include "iso_runtime_payload.h"
static uint8_t image[0x69000],expected[0x69000];
static unsigned writes;
static int read_image(void *context,uint32_t offset,void *data,size_t n) {
    (void)context;assert(offset<=sizeof(image) && n<=sizeof(image)-offset);memcpy(data,image+offset,n);return 0;
}
static int write_image(void *context,uint32_t offset,void *data,size_t n) {
    (void)context;assert(offset<=sizeof(image) && n<=sizeof(image)-offset);memcpy(image+offset,data,n);writes++;return 0;
}
static void load(const char *path,uint8_t *out) {
    FILE *f=fopen(path,"rb");assert(f);assert(fread(out,1,sizeof(image),f)==sizeof(image));assert(fgetc(f)==EOF);assert(!fclose(f));
}
int main(int argc,char **argv) {
    assert(argc==4);load(argv[3],expected);size_t failed=0;
    load(argv[1],image);writes=0;
    assert(isoApplyRuntimePatch(isoRuntimeEdits,sizeof(isoRuntimeEdits)/sizeof(*isoRuntimeEdits),read_image,write_image,NULL,&failed)==0);
    assert(writes==22 && !memcmp(image,expected,sizeof(image)));
    writes=0;assert(isoApplyRuntimePatch(isoRuntimeEdits,22,read_image,write_image,NULL,&failed)==1 && !writes);
    load(argv[2],image);writes=0;
    assert(isoApplyRuntimePatch(isoRuntimeEdits,22,read_image,write_image,NULL,&failed)==-2 && !writes);
    load(argv[3],image);image[0x68d54]^=1;writes=0;
    assert(isoApplyRuntimePatch(isoRuntimeEdits,22,read_image,write_image,NULL,&failed)==-2 && !writes);
    puts("{\"installer_cases\":4,\"old_ips_rejected_without_writes\":true,\"simulation\":true}");return 0;
}
