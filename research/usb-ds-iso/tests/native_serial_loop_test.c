#define _POSIX_C_SOURCE 200809L
#include <libusb.h>
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdbool.h>
static unsigned submitted,triggered,cancelled,fail_at,bitmap_fail_at;
static struct libusb_transfer *pending;
static FILE *native_file;
static int fake_init(libusb_context **p){*p=(void *)1;return 0;}
static int fake_option(libusb_context *p,enum libusb_option o,...){(void)p;(void)o;return 0;}
static libusb_device_handle *fake_open(libusb_context *p,uint16_t a,uint16_t b){(void)p;(void)a;(void)b;return (void *)2;}
static libusb_device *fake_device(libusb_device_handle *p){(void)p;return (void *)3;}
static int fake_speed(libusb_device *p){(void)p;return LIBUSB_SPEED_HIGH;}
static int fake_config(libusb_device *,struct libusb_config_descriptor **);
static int fake_claim(libusb_device_handle *p,int i){(void)p;assert(i==2);return 0;}
static int fake_release(libusb_device_handle *p,int i){(void)p;(void)i;return 0;}
static void fake_close(libusb_device_handle *p){(void)p;}
static void fake_exit(libusb_context *p){(void)p;}
static void fake_free_config(struct libusb_config_descriptor *p){(void)p;}
static int fake_control(libusb_device_handle *,uint8_t,uint8_t,uint16_t,uint16_t,unsigned char *,uint16_t,unsigned);
static int fake_submit(struct libusb_transfer *t){assert(!pending);pending=t;++submitted;return 0;}
static int fake_events(libusb_context *,struct timeval *);
static int fake_cancel(struct libusb_transfer *t){(void)t;++cancelled;return 0;}
#define libusb_init fake_init
#define libusb_set_option fake_option
#define libusb_open_device_with_vid_pid fake_open
#define libusb_get_device fake_device
#define libusb_get_device_speed fake_speed
#define libusb_get_active_config_descriptor fake_config
#define libusb_claim_interface fake_claim
#define libusb_release_interface fake_release
#define libusb_close fake_close
#define libusb_exit fake_exit
#define libusb_free_config_descriptor fake_free_config
#define libusb_control_transfer fake_control
#define libusb_submit_transfer fake_submit
#define libusb_handle_events_timeout fake_events
#define libusb_cancel_transfer fake_cancel
#define main receiver_main
#include ISO_RECEIVER_SOURCE
#undef main
static IsoProbeStatus device_state;
static int fake_config(libusb_device *d,struct libusb_config_descriptor **p) {
 (void)d;
 static const struct libusb_endpoint_descriptor ep={.bEndpointAddress=0x83,.bmAttributes=1,.wMaxPacketSize=256,.bInterval=1};
 static const struct libusb_interface_descriptor alt={.bInterfaceNumber=2,.bNumEndpoints=1,.bInterfaceClass=0xff,.bInterfaceSubClass=0x49,.bInterfaceProtocol=1,.endpoint=&ep};
 static const struct libusb_interface i={.altsetting=&alt,.num_altsetting=1};
 static struct libusb_config_descriptor cfg={.bNumInterfaces=1,.wTotalLength=25,.interface=&i};*p=&cfg;return 0;
}
static int fake_control(libusb_device_handle *d,uint8_t type,uint8_t req,uint16_t value,uint16_t index,unsigned char *data,uint16_t length,unsigned timeout) {
 (void)d;(void)type;(void)timeout;assert(index==2);
 if(req==ISO_PROBE_STATUS){assert(length==sizeof(device_state));memcpy(data,&device_state,length);return length;}
 assert(req==ISO_PROBE_BURST && pending);++triggered;assert(value==triggered);
 device_state.sequence=value;device_state.state=ISO_PROBE_COMPLETE;device_state.urb_id=device_state.report_id=386+triggered;
 device_state.requested=device_state.transferred=3072;device_state.urb_status=3;
 IsoProbeBurstContextDiagnostics diag={.magic=ISO_PROBE_BURST_INTERVAL_MAGIC,.terminal=1,.completed_bitmap=triggered==bitmap_fail_at?0x7fff:0xffff,.actual_sum=3072};
 memcpy(&device_state.diagnostics,&diag,sizeof(diag));return 0;
}
static int fake_events(libusb_context *ctx,struct timeval *wait) {
 (void)ctx;(void)wait;if(!pending)return 0;
 struct libusb_transfer *t=pending;t->status=LIBUSB_TRANSFER_COMPLETED;
 for(unsigned i=0;i<960;++i){unsigned actual=i>=567 && i<583?192:0;t->iso_packet_desc[i].status=LIBUSB_TRANSFER_COMPLETED;t->iso_packet_desc[i].actual_length=actual;
 if(actual)for(unsigned j=0;j<192;++j)t->buffer[i*192+j]=isoProbeByte((uint16_t)(triggered+i-567),j);
 fprintf(native_file,"{\"kind\":\"darwin_iso_native\",\"index\":%u,\"overall\":0,\"status\":%u,\"requested\":192,\"actual\":%u}\n",i,actual?(triggered==fail_at?0xe00002ed:0):0xe00002e7,actual);}
 fflush(native_file);pending=NULL;t->callback(t);return 0;
}
int main(int argc,char **argv) {
 assert(argc==5);fail_at=(unsigned)atoi(argv[3]);bitmap_fail_at=(unsigned)atoi(argv[4]);
 native_file=fopen(argv[2],"wx");assert(native_file);assert(setenv("ISO_NATIVE_LOG_PATH",argv[2],1)==0);
 device_state.magic=ISO_PROBE_STATUS_MAGIC;device_state.version=1;device_state.endpoint=0x83;
 char *args[]={"test","--burst","--repeat","3","--packets","960","--trigger-delay-ms","1","--log",argv[1]};
 int result=receiver_main(10,args);unsigned expected=fail_at?fail_at:(bitmap_fail_at?bitmap_fail_at:3);
 assert(submitted==expected && triggered==expected && cancelled==0 && pending==NULL);
 assert(result==((fail_at || bitmap_fail_at)?1:0));fclose(native_file);
 printf("Real CLI submitted=%u triggered=%u cancel=%u exit=%d\n",submitted,triggered,cancelled,result);
}
