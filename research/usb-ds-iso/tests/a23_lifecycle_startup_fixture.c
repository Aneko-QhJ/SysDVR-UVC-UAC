/* Execute the generated main startup body with modeled services only. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "ep0_lifecycle_file.h"
typedef uint32_t Result;
#define R_FAILED(rc) ((rc)!=0)
#define LOG(...) ((void)0)
#define UVC_VENDOR_ID 1
#define UVC_PRODUCT_ID 2
#define VIDEO_THREAD_STACK_SIZE 8
#define AUDIO_THREAD_STACK_SIZE 8
#define STREAM_THREAD_PRIORITY 44
typedef struct { unsigned vendorId,productId;const char *manufacturer,*product,*serialNumber; } UvcDeviceConfig;
static unsigned usb_calls,launches,quiet_enter,life_finishes,notes;
static const char *scenario;
static int g_videoThread,g_audioThread;
static uint8_t g_videoThreadStack[8],g_audioThreadStack[8],ep0CandidateRecipe[32]={3};
static void VideoStreamThread(void *p) { (void)p; }
static void AudioStreamThread(void *p) { (void)p; }
uint32_t Ep0LifePrepare(const uint8_t recipe[32]) { assert(recipe==ep0CandidateRecipe);return !strcmp(scenario,"prepare-error")?91:0; }
uint32_t Ep0LifeLastPhase(void) { return EP0_LF_CREATE; }
bool Ep0LifeNote(unsigned stage,uint32_t result,uint32_t arg0,uint32_t arg1) { (void)stage;(void)result;(void)arg0;(void)arg1;notes++;return true; }
void Ep0LifeFinish(unsigned stage,uint32_t result,uint32_t reason) { (void)result;(void)reason;assert(stage==EP0_L_MAIN_RETURN);life_finishes++; }
static const char *CoreGetSerialNumber(void) { return "model"; }
static Result UvcDeviceInitialize(const UvcDeviceConfig *c) { (void)c;usb_calls++;return !strcmp(scenario,"usb-error")?92:0; }
static bool Ep0StartupSeal(void) { return true; }
static bool Ep0SessionStartupOnly(const uint8_t *recipe) { (void)recipe;return true; }
static void CaptureSetInjectSPSPPS(bool b) { assert(b); }
static void CoreSetDiagnosticQuiet(bool b) { assert(b);quiet_enter++; }
static void Ep0StartupBindThreads(void *a,void *b) { assert(a!=b); }
static void LaunchThread(int *t,void(*fn)(void*),void *arg,uint8_t *stack,unsigned n,unsigned priority) {
 (void)t;(void)fn;(void)arg;(void)stack;assert(n==8 && priority==44 && quiet_enter==1);launches++;
}
/* ACTUAL_STARTUP_BODY */
int main(int argc,char **argv) {
 assert(argc==2);scenario=argv[1];int result=replay_start(0,NULL);
 if(!strcmp(scenario,"prepare-error"))assert(result==1 && !usb_calls && !launches && !notes);
 else if(!strcmp(scenario,"usb-error"))assert(result==1 && usb_calls==1 && !launches && life_finishes==1);
 else assert(result==42 && usb_calls==1 && launches==2 && quiet_enter==1);
 printf("{\"result\":%d,\"usb_calls\":%u,\"launches\":%u,\"quiet_enter\":%u,\"simulation\":true}\n",result,usb_calls,launches,quiet_enter);
}
