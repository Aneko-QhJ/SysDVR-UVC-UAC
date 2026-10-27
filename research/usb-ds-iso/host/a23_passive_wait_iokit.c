/* Real bindings, dormant and never invoked by the injected adapter fixtures.
 * No runloop/dispatch notification source and no IOUSBHost SDK objects. */
#include "a23_passive_wait_adapter.h"
#include <CoreFoundation/CoreFoundation.h>
#include <IOKit/IOKitKeys.h>
#include <IOKit/OSMessageNotification.h>
#include <IOKit/usb/IOUSBHostFamilyDefinitions.h>
#include <mach/mach.h>
#include <string.h>

static IONotificationPortRef create(void *context) { (void)context;return IONotificationPortCreate(kIOMainPortDefault); }
static kern_return_t matching(void *context,IONotificationPortRef port,IOServiceMatchingCallback callback,void *ref,io_iterator_t *iterator) {
    (void)context;
    CFMutableDictionaryRef match=IOServiceMatching("IOUSBHostInterface");
    CFMutableDictionaryRef properties=CFDictionaryCreateMutable(NULL,0,&kCFTypeDictionaryKeyCallBacks,&kCFTypeDictionaryValueCallBacks);
    if(!match || !properties) { if(match)CFRelease(match);if(properties)CFRelease(properties);return kIOReturnNoMemory; }
    const CFStringRef keys[]={CFSTR(kUSBHostMatchingPropertyVendorID),CFSTR(kUSBHostMatchingPropertyProductID),
        CFSTR(kUSBHostMatchingPropertyInterfaceNumber),CFSTR(kUSBHostMatchingPropertyInterfaceClass),
        CFSTR(kUSBHostMatchingPropertyInterfaceSubClass),CFSTR(kUSBHostMatchingPropertyInterfaceProtocol),
        CFSTR(kUSBHostMatchingPropertySpeed)};
    const int32_t values[]={0x1209,0xca57,2,0xff,0x49,1,3};
    for(unsigned i=0;i<7;i++) {
        CFNumberRef value=CFNumberCreate(NULL,kCFNumberSInt32Type,&values[i]);
        if(!value) { CFRelease(match);CFRelease(properties);return kIOReturnNoMemory; }
        CFDictionarySetValue(properties,keys[i],value);CFRelease(value);
    }
    CFDictionarySetValue(match,CFSTR(kIOPropertyMatchKey),properties);CFRelease(properties);
    /* This API consumes match even on error. */
    return IOServiceAddMatchingNotification(port,kIOFirstMatchNotification,match,callback,ref,iterator);
}
static bool valid(void *context,io_iterator_t iterator) { (void)context;return IOIteratorIsValid(iterator); }
static io_service_t next(void *context,io_iterator_t iterator) { (void)context;return IOIteratorNext(iterator); }
static bool identity(void *context,io_service_t service,A23WaitIdentity *out) {
    (void)context;io_registry_entry_t parent=0;A23WaitIdentity id={0};int32_t speed=0;
    if(!IOObjectConformsTo(service,"IOUSBHostInterface") || IORegistryEntryGetRegistryEntryID(service,&id.interface_id) ||
       IORegistryEntryGetParentEntry(service,kIOServicePlane,&parent))return false;
    bool ok=IOObjectConformsTo(parent,"IOUSBHostDevice") && !IORegistryEntryGetRegistryEntryID(parent,&id.device_id);
    CFTypeRef property=ok ? IORegistryEntryCreateCFProperty(parent,CFSTR(kUSBHostMatchingPropertySpeed),NULL,0):NULL;
    ok=property && CFGetTypeID(property)==CFNumberGetTypeID() && !CFNumberIsFloatType((CFNumberRef)property) &&
        CFNumberGetValue((CFNumberRef)property,kCFNumberSInt32Type,&speed) && speed==3;
    if(property)CFRelease(property);
    if(IOObjectRelease(parent))ok=false;
    id.speed=(uint32_t)speed;if(ok)*out=id;return ok;
}
static kern_return_t interest(void *context,IONotificationPortRef port,io_service_t service,
    IOServiceInterestCallback callback,void *ref,io_object_t *notifier) {
    (void)context;return IOServiceAddInterestNotification(port,service,kIOGeneralInterest,callback,ref,notifier);
}
/* Validate lengths/types before the system callout dispatcher. The port is
 * private to IOKit. Callback addresses and right ownership still rely on the
 * OS notification ABI; this is not an arbitrary-message execution interface. */
bool a23_wait_message_valid(const mach_msg_header_t *msg,size_t available) {
    if(!msg || available<sizeof(*msg) || msg->msgh_id!=kOSNotificationMessageID ||
       msg->msgh_size<sizeof(*msg) || msg->msgh_size>available)return false;
    size_t at=sizeof(*msg);
    if(msg->msgh_bits&MACH_MSGH_BITS_COMPLEX) {
        if(msg->msgh_size-at<sizeof(mach_msg_body_t))return false;
        mach_msg_body_t body;memcpy(&body,(const uint8_t *)msg+at,sizeof(body));at+=sizeof(body);
        if(body.msgh_descriptor_count>1)return false;
        if(body.msgh_descriptor_count) {
            if(msg->msgh_size-at<sizeof(mach_msg_port_descriptor_t))return false;
            mach_msg_port_descriptor_t descriptor;memcpy(&descriptor,(const uint8_t *)msg+at,sizeof(descriptor));
            if(descriptor.type!=MACH_MSG_PORT_DESCRIPTOR)return false;
            at+=sizeof(descriptor);
        }
    }
    if(msg->msgh_size-at<sizeof(struct OSNotificationHeader64))return false;
    struct OSNotificationHeader64 head;memcpy(&head,(const uint8_t *)msg+at,sizeof(head));at+=sizeof(head);
    uint32_t type=head.type&kIOKitNoticationTypeMask;
    size_t adjustment=(head.type>>kIOKitNoticationTypeSizeAdjShift)&kIOKitNoticationMsgSizeMask;
    if(msg->msgh_size-at<adjustment)return false;
    size_t content=msg->msgh_size-at-adjustment;
    if(type==kIOServiceMatchedNotificationType)return true;
    return type==kIOServiceMessageNotificationType && content>=sizeof(struct IOServiceInterestContent64);
}
static int pump(void *context,IONotificationPortRef port) {
    (void)context;
    union { mach_msg_header_t header;uint64_t alignment;uint8_t bytes[8192]; } message={0};
    mach_port_t receive=IONotificationPortGetMachPort(port);
    if(!receive)return -1;
    mach_msg_return_t rc=mach_msg(&message.header,MACH_RCV_MSG|MACH_RCV_TIMEOUT|MACH_RCV_LARGE,
        0,sizeof(message),receive,0,MACH_PORT_NULL);
    if(rc==MACH_RCV_TIMED_OUT)return 0;
    if(rc!=MACH_MSG_SUCCESS)return -1;
    if(!a23_wait_message_valid(&message.header,sizeof(message))) { mach_msg_destroy(&message.header);return -1; }
    /* IODispatch consumes message-carried notifier/service send rights.
     * Do not mach_msg_destroy the same successfully dispatched message. */
    IODispatchCalloutFromMessage(NULL,&message.header,port);return 1;
}
static kern_return_t release(void *context,io_object_t token) { (void)context;return IOObjectRelease(token); }
static void destroy(void *context,IONotificationPortRef port) { (void)context;IONotificationPortDestroy(port); }
void a23_wait_native_ops(A23WaitOps *out,void *context,uint64_t (*now)(void *),bool (*emit)(void *,const A23WaitEvent *)) {
    if(!out)return;
    *out=(A23WaitOps){.context=context,.now=now,.create=create,.matching=matching,.valid=valid,.next=next,
        .identity=identity,.interest=interest,.pump=pump,.release=release,.destroy=destroy,.emit=emit};
}
