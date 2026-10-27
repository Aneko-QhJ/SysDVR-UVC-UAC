#define _POSIX_C_SOURCE 200809L
#include <libusb.h>
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
static unsigned mode, submitted, cancelled, controls;
static long long fake_ns;
static long long submitted_ns;
static struct libusb_transfer *pending;
static FILE *native_file;
static int fake_clock(clockid_t clock, struct timespec *out) {
    (void)clock; fake_ns += 1000000; out->tv_sec=fake_ns/1000000000;
    out->tv_nsec=fake_ns%1000000000; return 0;
}
static int fake_sleep(const struct timespec *wait, struct timespec *remaining) {
    (void)remaining; fake_ns+=wait->tv_sec*1000000000LL+wait->tv_nsec; return 0;
}
static int fake_init(libusb_context **p){*p=(void *)1;return 0;}
static int fake_option(libusb_context *p,enum libusb_option o,...){(void)p;(void)o;return 0;}
static libusb_device_handle *fake_open(libusb_context *p,uint16_t a,uint16_t b){(void)p;(void)a;(void)b;return (void *)2;}
static libusb_device *fake_device(libusb_device_handle *p){(void)p;return (void *)3;}
static int fake_speed(libusb_device *p){(void)p;return mode==7?LIBUSB_SPEED_SUPER:LIBUSB_SPEED_HIGH;}
static int fake_config(libusb_device *,struct libusb_config_descriptor **);
static int fake_claim(libusb_device_handle *p,int i){(void)p;assert(i==2);return 0;}
static int fake_release(libusb_device_handle *p,int i){(void)p;(void)i;return 0;}
static void fake_close(libusb_device_handle *p){(void)p;}
static void fake_exit(libusb_context *p){(void)p;}
static void fake_free_config(struct libusb_config_descriptor *p){(void)p;}
static int fake_control(libusb_device_handle *,uint8_t,uint8_t,uint16_t,uint16_t,unsigned char *,uint16_t,unsigned);
static int fake_submit(struct libusb_transfer *t){assert(!pending);pending=t;++submitted;submitted_ns=fake_ns;return 0;}
static int fake_events(libusb_context *,struct timeval *);
static int fake_cancel(struct libusb_transfer *t){assert(t==pending);++cancelled;return 0;}
#define clock_gettime fake_clock
#define nanosleep fake_sleep
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
static int fake_config(libusb_device *device,struct libusb_config_descriptor **p) {
    (void)device;
    static struct libusb_endpoint_descriptor ep={.bEndpointAddress=0x83,.bmAttributes=1,.wMaxPacketSize=256,.bInterval=1};
    static const struct libusb_interface_descriptor alt={.bInterfaceNumber=2,.bNumEndpoints=1,.bInterfaceClass=0xff,.bInterfaceSubClass=0x49,.bInterfaceProtocol=1,.endpoint=&ep};
    static const struct libusb_interface interface={.altsetting=&alt,.num_altsetting=1};
    static struct libusb_config_descriptor cfg={.bNumInterfaces=1,.wTotalLength=25,.interface=&interface};
    if(mode==8)ep.wMaxPacketSize=192;
    *p=&cfg;return 0;
}
static int fake_control(libusb_device_handle *device,uint8_t type,uint8_t req,uint16_t value,uint16_t index,unsigned char *data,uint16_t length,unsigned timeout) {
    (void)device;(void)timeout;
    assert(type==0xc1 && req==ISO_PROBE_STATUS && value==0 && index==2);
    assert(length==sizeof(device_state) && !pending);++controls;
    if(mode==5 && controls==2)device_state.sequence=1;
    memcpy(data,&device_state,length);return length;
}
static int fake_events(libusb_context *ctx,struct timeval *wait) {
    (void)ctx;(void)wait;assert(fake_ns-submitted_ns>=40000000);
    if(!pending)return 0;
    if(mode==9 && !cancelled){fake_ns+=1000000000LL;return 0;}
    struct libusb_transfer *t=pending;t->status=mode==9?LIBUSB_TRANSFER_CANCELLED:LIBUSB_TRANSFER_COMPLETED;
    if(mode==4)t->buffer[0]=1;
    for(unsigned i=0;i<960;++i){
        t->iso_packet_desc[i].status=LIBUSB_TRANSFER_COMPLETED;t->iso_packet_desc[i].actual_length=0;
        unsigned overall=mode==1?0xe000400e:0;
        unsigned status=mode==1 && i<3?0xe000400e:0xe00002e7;
        if(mode==2 && i==959)continue;
        if(mode==3 && i==0){fprintf(native_file,"{\"kind\":\"darwin_iso_native\",broken}\n");continue;}
        fprintf(native_file,"{\"kind\":\"darwin_iso_native\",\"index\":%u,\"overall\":%u,\"status\":%u,\"requested\":192,\"actual\":0}\n",i,overall,status);
    }
    fflush(native_file);pending=NULL;t->callback(t);return 0;
}
int main(int argc,char **argv) {
    assert(argc==4);mode=(unsigned)atoi(argv[3]);native_file=fopen(argv[2],"wx");assert(native_file);
    assert(setenv("ISO_NATIVE_LOG_PATH",argv[2],1)==0);
    if(mode==10)unsetenv("ISO_NATIVE_LOG_PATH");
    if(mode==11){char name[4096];snprintf(name,sizeof(name),"%s.seq0.buffer.bin",argv[1]);FILE *file=fopen(name,"wx");assert(file);fclose(file);}
    device_state.magic=ISO_PROBE_STATUS_MAGIC;device_state.version=1;device_state.endpoint=0x83;
    if(mode==6){device_state.state=ISO_PROBE_COMPLETE;device_state.sequence=1;device_state.urb_id=387;}
    char *args[]={"test","--receive-only","--packets","960","--trigger-delay-ms","40","--log",argv[1]};
    int result=receiver_main(8,args);
    unsigned expected=mode==6 || mode==7 || mode==8?0:1;
    assert(submitted==expected && cancelled==(unsigned)(mode==9) && pending==NULL);
    assert(result==(mode==0?0:1));fclose(native_file);
    printf("mode=%u submitted=%u controls=%u cancelled=%u result=%d\n",mode,submitted,controls,cancelled,result);
}
