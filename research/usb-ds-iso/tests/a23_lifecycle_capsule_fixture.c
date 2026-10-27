/* Native model only. No Switch SDK, filesystem service, USB or ARM execution. */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include "ep0_lifecycle_capsule.h"
static uint8_t disk[EP0_LCP_MAX];
static unsigned writes,fail_at,failed,denied;
static Ep0LifecycleCapsule capsule;
static uint8_t nonce[16]={1},recipe[32]={3},context[32]={[0]=4,[16]=5};
static uint32_t write_once(void *opaque,size_t off,const void *data,size_t n) {
 (void)opaque;assert(off+n<=sizeof(disk));writes++;
 /* Failure can occur after all bytes were copied, e.g. final commit failure. */
 memcpy(disk+off,data,n);if(writes==fail_at) { failed++;return 91; }return 0;
}
static bool note(unsigned stage,uint32_t rc) {
 return ep0_lcp_note(&capsule,22,stage,1000+capsule.count,rc,0,0,stage==EP0_L_CONTEXT?context:NULL);
}
static void deny(unsigned stage,const uint8_t *pointer) {
 unsigned before=writes;
 assert(!ep0_lcp_note(&capsule,22,stage,1000+capsule.count,0,0,0,pointer));
 assert(before==writes);denied++;
}
int main(int argc,char **argv) {
 assert(argc==4);const char *scenario=argv[1];fail_at=(unsigned)strtoul(argv[2],NULL,10);
 bool initialized=ep0_lcp_init(&capsule,NULL,write_once,22,1000,1000,nonce,recipe);
 unsigned old=writes;assert(!ep0_lcp_init(&capsule,NULL,write_once,22,1000,1000,nonce,recipe));assert(old==writes);
 if(!initialized)goto done;
 deny(EP0_L_CONTEXT,(void*)1);deny(EP0_L_VIDEO_JOIN_RESULT,NULL);
 if(!note(EP0_L_PREPARED,0))goto done;
 if(!strcmp(scenario,"prepared-only"))goto done;
 if(!note(EP0_L_USB_INIT_CALL,0) || !note(EP0_L_USB_INIT_RESULT,0) || !note(EP0_L_QUIET_ENTER,0))goto done;
 deny(EP0_L_RETAIN,NULL);deny(EP0_L_CONTEXT,(void*)1);deny(EP0_L_VIDEO_JOIN_CALL,NULL);
 if(!strcmp(scenario,"window-not-observed"))goto done;
 if(!note(EP0_L_MAIN_LOOP_LEFT,0) || !note(EP0_L_CLEANUP_RESULT,1) || !note(EP0_L_VIDEO_JOIN_CALL,0))goto done;
 if(!strcmp(scenario,"video-join-blocked"))goto done;
 if(!note(EP0_L_VIDEO_JOIN_RESULT,!strcmp(scenario,"video-join-failed")?78:0))goto done;
 deny(EP0_L_VIDEO_JOIN_CALL,NULL);
 if(!note(EP0_L_AUDIO_JOIN_CALL,0))goto done;
 if(!strcmp(scenario,"audio-join-blocked"))goto done;
 if(!note(EP0_L_AUDIO_JOIN_RESULT,0) || !note(EP0_L_EXPORTER_RESULT,0))goto done;
 if(!strcmp(scenario,"video-join-failed")) {
  deny(EP0_L_CONTEXT,(void*)1);deny(EP0_L_SD_OPEN_CALL,NULL);(void)note(EP0_L_RETAIN,78);goto done;
 }
 if(!note(EP0_L_CONTEXT,0) || !note(EP0_L_OWNER_FINISH_RESULT,0) || !note(EP0_L_PRIMARY_SAVE_CALL,0) || !note(EP0_L_SD_OPEN_CALL,0))goto done;
 if(!strcmp(scenario,"sd-open-blocked"))goto done;
 if(!note(EP0_L_SD_OPEN_RESULT,!strcmp(scenario,"sd-open-failed")?91:0))goto done;
 if(!strcmp(scenario,"sd-open-failed")) { (void)note(EP0_L_RETAIN,91);goto done; }
 if(!note(EP0_L_FILE_CREATE_CALL,0))goto done;
 if(!strcmp(scenario,"create-blocked"))goto done;
 if(!note(EP0_L_FILE_CREATE_RESULT,!strcmp(scenario,"create-failed")?92:0))goto done;
 if(!strcmp(scenario,"create-failed")) { (void)note(EP0_L_RETAIN,92);goto done; }
 if(!note(EP0_L_PRIMARY_SAVE_RESULT,1) || !note(EP0_L_EXEC_BUILD_RESULT,1) || !note(EP0_L_EXEC_SAVE_CALL,0) || !note(EP0_L_EXEC_SAVE_RESULT,1))goto done;
 if(!strcmp(scenario,"capacity")) {
  while(capsule.count<EP0_LCP_CAPACITY)if(!note(EP0_L_EXPORTER_RESULT,0))goto done;
  deny(EP0_L_EXPORTER_RESULT,NULL);
 } else {
  if(!note(EP0_L_RETAIN,0))goto done;
  deny(EP0_L_MAIN_RETURN,NULL);
 }
done:
 if(capsule.disabled) { unsigned before=writes;assert(!note(EP0_L_RETAIN,0));assert(before==writes); }
 FILE *f=fopen(argv[3],"wb");assert(f);assert(fwrite(disk,1,sizeof(disk),f)==sizeof(disk));assert(!fclose(f));
 printf("{\"scenario\":\"%s\",\"writes\":%u,\"acknowledged_records\":%u,\"disabled\":%s,\"failures\":%u,\"denied_without_io\":%u,\"simulation\":true}\n",
 scenario,writes,capsule.count,capsule.disabled?"true":"false",failed,denied);
}
