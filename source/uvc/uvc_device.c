#include <string.h>
#include "uvc_device.h"
#include "uac_standard.h"
#ifdef ALT1_PROBE
#include "alt1_probe_protocol.h"
#endif
#include "../core.h"
#ifdef ISO_PROBE
#include "iso_probe_protocol.h"
#endif
#if defined(ISO_RUNTIME_PATCH) || defined(UAC_DESCRIPTOR_PATCH) || \
    defined(UAC_U2_BASE_PATCH) || defined(UAC_U2_PATCH)
#include "iso_runtime_patch.h"
#endif
#ifdef ISO_RUNTIME_PATCH
#include "iso_runtime_payload.h"
#include "iso_runtime_stream_payload.h"
#endif
#ifdef UAC_DESCRIPTOR_PATCH
#include "uac_descriptor_payload.h"
#endif
#ifdef UAC_U2_BASE_PATCH
#include "uac_u2_base_payload.h"
#endif
#ifdef UAC_U2_PATCH
#include "uac_u2_payload.h"
#endif

// USB class codes not defined in libnx
#ifndef USB_CLASS_MISC
#define USB_CLASS_MISC 0xEF
#endif

// USB Setup Packet (standard 8-byte format)
typedef struct __attribute__((packed)) {
    u8  bmRequestType;
    u8  bRequest;
    u16 wValue;
    u16 wIndex;
    u16 wLength;
} UsbSetupPacket;

#define USB_REQTYPE_DIR_MASK     0x80
#define USB_REQTYPE_DIR_TO_HOST  0x80

// ============================================================================
// Static buffers - must be aligned for USB DMA
// ============================================================================

static u8 alignas(0x1000) g_videoBuffer[0x60000];       // ~384KB for video frames
static u8 alignas(0x1000) g_controlBuffer[0x1000];     // 4KB for VS control transfers
static u8 alignas(0x1000) g_vcControlBuffer[0x1000];   // 4KB for VC control transfers (separate from VS)
static u8 alignas(0x1000) g_uacControlBuffer[0x1000];  // 4KB for UAC control transfers
static u8 alignas(0x1000) g_endpointInBuffer[0x4000];  // Video transfer staging buffer (must fit maxPayload + header)
static u8 alignas(0x1000) g_audioEndpointBuffer[0x1000]; // Audio transfer staging buffer
#ifdef UAC_U2_PATCH
/* Sequential post count.  The v11 32-post train left its second request
   pending after a 100 ms timeout, and alt0 teardown then crashed the usb
   sysmodule; v13/v14 posted exactly one request and cancelled on timeout.
   UAC_U2_BURSTS only raises the *sequential* count: each request is posted
   after the previous completion, a timeout cancels before the loop exits, so
   at most one request is ever pending.  1 is the v14 one-shot clone; the
   continuous trial uses 2..4. */
#if defined(UAC_U2_ONE_SHOT)
#define UAC_U2_TRAIN_POSTS 1
#elif defined(UAC_U2_BURSTS)
#define UAC_U2_TRAIN_POSTS UAC_U2_BURSTS
#else
#define UAC_U2_TRAIN_POSTS 1
#endif
#if defined(UAC_U2_PIPELINE)
/* v26A keeps two requests in flight so the ring never runs dry; the cave
   writes the next TD set at prod without replaying the endpoint setup. */
#if UAC_U2_TRAIN_POSTS < 2 || UAC_U2_TRAIN_POSTS > 8
#error "UAC_U2_PIPELINE needs UAC_U2_BURSTS 2..8"
#endif
#else
#if UAC_U2_TRAIN_POSTS < 1 || UAC_U2_TRAIN_POSTS > 4
#error "UAC_U2_BURSTS must be 1..4: only one request may be pending at a time"
#endif
#endif
/* v28: one transfer carries UAC_U2_FRAMES x 192 B frames (default 16, the
   v24 one-segment request).  v27 proved the usb:ds AS endpoint is
   single-transfer (a second post while one request is in flight never
   reaches the cave and completes xfer=0/status=5), so the burst is widened by
   making one request larger instead of posting twice.  The v28 cave builds
   one Isoch+ED pair per 192 B frame of the request; its ED bitmap is 32 bits,
   so 32 frames is the hard ceiling.  32 frames (6144 B) hung the console, so
   v28b probes 20 frames (3840 B). */
#ifndef UAC_U2_SEGMENTS
#define UAC_U2_SEGMENTS 1
#endif
#if UAC_U2_SEGMENTS < 1 || UAC_U2_SEGMENTS > 2
#error "UAC_U2_SEGMENTS must be 1..2 (the cave's ED bitmap is 32 bits)"
#endif
#ifndef UAC_U2_FRAMES
#define UAC_U2_FRAMES (16 * UAC_U2_SEGMENTS)
#endif
#if UAC_U2_FRAMES < 1 || UAC_U2_FRAMES > 32
#error "UAC_U2_FRAMES must be 1..32 (the cave's ED bitmap is 32 bits)"
#endif
#define UAC_U2_BURST_BYTES (UAC_ISO_PACKET_SIZE * UAC_U2_FRAMES)
/* v29c: keep posting buffers until this many posts have gone out (the
   pipeline recycles the buffer pool only after a completion). */
#ifndef UAC_U2_STREAM_POSTS
#define UAC_U2_STREAM_POSTS UAC_U2_TRAIN_POSTS
#endif
#if UAC_U2_STREAM_POSTS < UAC_U2_TRAIN_POSTS
#error "UAC_U2_STREAM_POSTS must be >= UAC_U2_TRAIN_POSTS"
#endif
/* One DMA row per post: rounded up to a page so every row stays 0x1000
   aligned (the cave's TDs point into it). */
#define UAC_U2_BUF_BYTES ((UAC_U2_BURST_BYTES + 0xFFFu) & ~0xFFFu)
#if defined(UAC_U2_PIPELINE) && UAC_U2_FRAMES > 16
#error "a pipeline build keeps two transfers in flight; v28 uses one multi-frame transfer"
#endif
static u8 alignas(0x1000) g_u2BurstBuffers[UAC_U2_TRAIN_POSTS][UAC_U2_BUF_BYTES];
#endif

static UvcDeviceContext g_uvcCtx;

#if defined(ISO_RUNTIME_PATCH) || defined(UAC_DESCRIPTOR_PATCH) || \
    defined(UAC_U2_BASE_PATCH) || defined(UAC_U2_PATCH)
typedef struct { Handle debug; u64 base; Result last_result; } IsoPatchContext;
static int _isoPatchRead(void *context, uint32_t offset, void *bytes, size_t size)
{
    IsoPatchContext *c = context;
    c->last_result = svcReadDebugProcessMemory(bytes, c->debug, c->base + offset, size);
    return R_FAILED(c->last_result);
}
static int _isoPatchWrite(void *context, uint32_t offset, void *bytes, size_t size)
{
    IsoPatchContext *c = context;
    c->last_result = svcWriteDebugProcessMemory(c->debug, bytes, c->base + offset, size);
    return R_FAILED(c->last_result);
}
#endif

#if defined(UAC_DESCRIPTOR_PATCH) || defined(UAC_U2_BASE_PATCH) || \
    defined(UAC_U2_PATCH)
#ifdef UAC_U2_PATCH
/* usb:ds target recorded by _applyUacPatch; used by the U2 pre-check. */
static u64 g_uacUsbPid;
static u64 g_uacUsbBase;
#endif
/* Apply a bounded usb:ds runtime payload.  Fail closed: a build that requires
   a patch must not enable the device with an unpatched module. */
static bool _applyUacPatch(const IsoRuntimeEdit *edits, size_t edit_count,
                           const unsigned char *build_id, const char *tag)
{
    static bool applied;
    if (applied) return true;
    Result rc = pmdmntInitialize();
    if (R_FAILED(rc)) {
        LOG("UAC %s patch pm:dmnt init rc=0x%x\n", tag, rc);
        return false;
    }
    u64 pid = 0;
    rc = pmdmntGetProcessId(&pid, 0x0100000000000006ULL);
    pmdmntExit();
    if (R_FAILED(rc) || pid == 0) {
        LOG("UAC %s patch usb pid rc=0x%x pid=%llu\n", tag, rc,
            (unsigned long long)pid);
        return false;
    }
    rc = ldrDmntInitialize();
    if (R_FAILED(rc)) {
        LOG("UAC %s patch ldr:dmnt init rc=0x%x\n", tag, rc);
        return false;
    }
    LoaderModuleInfo modules[4] = {0};
    s32 count = 0;
    rc = ldrDmntGetProcessModuleInfo(pid, modules, 4, &count);
    ldrDmntExit();
    if (R_FAILED(rc) || count != 1 || modules[0].size != 0x369000 ||
        memcmp(modules[0].build_id, build_id, 32)) {
        LOG("UAC %s patch target mismatch rc=0x%x count=%d size=%llx\n", tag,
            rc, count, (unsigned long long)(count > 0 ? modules[0].size : 0));
        return false;
    }
    Handle debug = INVALID_HANDLE;
    rc = svcDebugActiveProcess(&debug, pid);
    if (R_FAILED(rc)) {
        LOG("UAC %s patch attach rc=0x%x\n", tag, rc);
        return false;
    }
    IsoPatchContext context = {debug, modules[0].base_address, 0};
    size_t failed = 0;
    int result = isoApplyRuntimePatch(edits, edit_count,
        _isoPatchRead, _isoPatchWrite, &context, &failed);
    LOG("UAC %s patch result=%d record=%u last-rc=0x%x\n",
        tag, result, (unsigned)failed, context.last_result);
    if (result == -4) {
        /* Do not resume a target whose original code cannot be restored. */
        LOG("UAC %s patch rollback unverified; usb remains paused\n", tag);
        for (;;) svcSleepThread(1000000000ULL);
    }
#ifdef UAC_U2_PATCH
    /* Remember the target so the U2 pre-check can attach briefly later; the
       debug session itself is not kept open (an attached usb would intercept
       its own faults instead of producing a crash report). */
    if (result >= 0) {
        g_uacUsbPid = pid;
        g_uacUsbBase = modules[0].base_address;
    }
#endif
    svcCloseHandle(debug);
    applied = result >= 0;
    return applied;
}
#endif

#ifdef UAC_DESCRIPTOR_PATCH
static bool _applyUacDescriptorPatch(void)
{
    return _applyUacPatch(uacRuntimeEdits,
        sizeof(uacRuntimeEdits) / sizeof(uacRuntimeEdits[0]),
        uacRuntimeBuildId, "descriptor");
}
#endif

#ifdef UAC_U2_BASE_PATCH
static bool _applyUacU2BasePatch(void)
{
    return _applyUacPatch(uacU2BaseEdits,
        sizeof(uacU2BaseEdits) / sizeof(uacU2BaseEdits[0]),
        uacU2BaseBuildId, "u2-base");
}
#endif

#ifdef UAC_U2_PATCH
static bool _applyUacU2Patch(void)
{
    return _applyUacPatch(uacU2Edits,
        sizeof(uacU2Edits) / sizeof(uacU2Edits[0]),
        uacU2BuildId, "u2");
}
#endif


#ifdef ISO_PROBE
static UsbDsInterface* g_isoInterface;
static UsbDsEndpoint* g_isoEndpoint;
static u8 alignas(0x1000) g_isoBuffer[0x1000];
static IsoProbeStatus g_isoStatus;
static u8 g_isoAlt;

#ifdef ISO_PROBE_STREAM
#define ISO_STREAM_BUFFERS 3
#define ISO_STREAM_BYTES (ISO_PROBE_BURST_PACKETS * ISO_PROBE_PACKET_SIZE)
/* Each URB buffer must start on a 4 KiB boundary; usb:ds rejects a misaligned
   address with 0xce8c before the producer hook runs. */
static u8 alignas(0x1000) g_isoStreamBuf[ISO_STREAM_BUFFERS][0x1000];
static u32 g_isoStreamUrb[ISO_STREAM_BUFFERS];
static bool g_isoStreamBusy[ISO_STREAM_BUFFERS];
static bool g_isoStreamUsed[ISO_STREAM_BUFFERS];
static Thread g_isoStreamThread;
static u8 alignas(0x1000) g_isoStreamStack[0x4000];
static volatile bool g_isoStreamRun;
static volatile bool g_isoStreamStop;
static volatile bool g_isoStreamExited;
static u32 g_isoStreamSeq;
static u32 g_isoStreamPosts, g_isoStreamCompletes, g_isoStreamErrors, g_isoStreamLate;
static u32 g_isoStreamAttempts;
#endif

static bool _logIsoTarget(void)
{
#ifdef ISO_PROBE_BURST_MODE
#ifdef ISO_PROBE_INTERVAL_EXPERIMENT
    LOG("ISO diagnostic revision A23 HS ISO7 bInterval1 followup-SIA experiment\n");
#elif defined(ISO_PROBE_FOLLOWUP_SIA)
    LOG("ISO diagnostic revision A22 HS ISO6 first-explicit followup-SIA experiment\n");
#elif defined(ISO_PROBE_CONTEXT_AUDIT)
    LOG("ISO diagnostic revision A21 HS ISO6 pre-publication context audit\n");
#elif defined(ISO_PROBE_DOORBELL_AUDIT)
    LOG("ISO diagnostic revision A20 HS ISO5 doorbell-tail/MFI audit\n");
#elif defined(ISO_PROBE_PUBLICATION_AUDIT)
    LOG("ISO diagnostic revision A19 HS ISO4 publication/MFI audit\n");
#elif defined(ISO_PROBE_EVENT_AUDIT)
    LOG("ISO diagnostic revision A18 HS bounded ISO3 event/MFI audit\n");
#else
    LOG("ISO diagnostic revision A17 HS defer submit log until after ACK\n");
#endif
#else
    LOG("ISO diagnostic revision A12 EP0 ownership fix\n");
#endif
    Result rc = setsysInitialize();
    if (R_SUCCEEDED(rc)) {
        SetSysFirmwareVersion fw = {0};
        rc = setsysGetFirmwareVersion(&fw);
        if (R_SUCCEEDED(rc)) LOG("ISO HOS %u.%u.%u\n", fw.major, fw.minor, fw.micro);
        setsysExit();
    }
    LOG("ISO firmware query rc=0x%x\n", rc);
    rc = pmdmntInitialize();
    if (R_FAILED(rc)) { LOG("ISO pm:dmnt init rc=0x%x\n", rc); return false; }
    u64 pid = 0;
    rc = pmdmntGetProcessId(&pid, 0x0100000000000006ULL);
    pmdmntExit();
    LOG("ISO usb pid=%llu query rc=0x%x\n", (unsigned long long)pid, rc);
    if (R_FAILED(rc)) return false;
    rc = ldrDmntInitialize();
    if (R_FAILED(rc)) { LOG("ISO ldr:dmnt init rc=0x%x\n", rc); return false; }
    LoaderModuleInfo modules[4] = {0};
    s32 count = 0;
    rc = ldrDmntGetProcessModuleInfo(pid, modules, 4, &count);
    ldrDmntExit();
    LOG("ISO usb module query rc=0x%x count=%d\n", rc, count);
    if (R_FAILED(rc)) return false;
    for (s32 i = 0; i < count && i < 4; ++i) {
        char build[65];
        static const char hex[] = "0123456789ABCDEF";
        for (unsigned j = 0; j < 32; ++j) {
            build[j*2] = hex[modules[i].build_id[j] >> 4];
            build[j*2+1] = hex[modules[i].build_id[j] & 15];
        }
        build[64] = 0;
        LOG("ISO usb module[%d] BuildID=%s base=%llx size=%llx\n", i, build,
            (unsigned long long)modules[i].base_address, (unsigned long long)modules[i].size);
    }
#ifdef ISO_RUNTIME_PATCH
    if (count != 1 || modules[0].size != 0x369000 ||
        memcmp(modules[0].build_id, isoRuntimeBuildId, sizeof(isoRuntimeBuildId))) {
        LOG("ISO runtime target mismatch; refusing writes\n");
        return false;
    }
#endif
    /* Close before later usb:ds calls; all preflight/writes/readback happen
       while the target is paused. Failed writes restore the original ranges. */
    Handle debug = INVALID_HANDLE;
    rc = svcDebugActiveProcess(&debug, pid);
    LOG("ISO usb debug attach rc=0x%x\n", rc);
    bool ready = false;
    if (R_SUCCEEDED(rc)) {
        if (count == 1 && modules[0].size >= 0x69000) {
            const u32 offsets[] = {0x30364, 0x2cbe0, 0x68d54};
            for (unsigned i = 0; i < sizeof(offsets)/sizeof(offsets[0]); ++i) {
                u32 words[4] = {0};
                Result read = svcReadDebugProcessMemory(words, debug,
                    modules[0].base_address + offsets[i], sizeof(words));
                LOG("ISO usb memory +%x rc=0x%x words=%08x %08x %08x %08x\n",
                    offsets[i], read, words[0], words[1], words[2], words[3]);
            }
        }
#ifdef ISO_RUNTIME_PATCH
        IsoPatchContext context = {debug, modules[0].base_address, 0};
        size_t failed = 0;
        int result = isoApplyRuntimePatch(isoRuntimeEdits,
            sizeof(isoRuntimeEdits)/sizeof(isoRuntimeEdits[0]),
            _isoPatchRead, _isoPatchWrite, &context, &failed);
        LOG("ISO runtime patch result=%d record=%u last-rc=0x%x\n",
            result, (unsigned)failed, context.last_result);
        ready = result >= 0;
        if (result == -4) {
            /* Do not resume a target whose original code cannot be restored. */
            LOG("ISO rollback unverified; usb remains paused, reboot required\n");
            for (;;) svcSleepThread(1000000000ULL);
        }
#else
        ready = true;
#endif
        svcCloseHandle(debug);
    }
    return ready;
}

#ifdef ISO_RUNTIME_PATCH
static bool _applyIsoStreamPatch(void)
{
    static bool applied;
    if (applied) return true;
    Result rc = pmdmntInitialize();
    if (R_FAILED(rc)) return false;
    u64 pid = 0;
    rc = pmdmntGetProcessId(&pid, 0x0100000000000006ULL);
    pmdmntExit();
    if (R_FAILED(rc) || pid == 0) return false;
    rc = ldrDmntInitialize();
    if (R_FAILED(rc)) return false;
    LoaderModuleInfo modules[4] = {0};
    s32 count = 0;
    rc = ldrDmntGetProcessModuleInfo(pid, modules, 4, &count);
    ldrDmntExit();
    if (R_FAILED(rc) || count != 1 || modules[0].size != 0x369000 ||
        memcmp(modules[0].build_id, isoRuntimeBuildId, sizeof(isoRuntimeBuildId))) {
        LOG("STREAM delta target mismatch\n");
        return false;
    }
    Handle debug = INVALID_HANDLE;
    rc = svcDebugActiveProcess(&debug, pid);
    if (R_FAILED(rc)) {
        LOG("STREAM delta attach rc=0x%x\n", rc);
        return false;
    }
    IsoPatchContext context = {debug, modules[0].base_address, 0};
    size_t failed = 0;
    int result = isoApplyRuntimePatch(isoRuntimeStreamEdits,
        sizeof(isoRuntimeStreamEdits) / sizeof(isoRuntimeStreamEdits[0]),
        _isoPatchRead, _isoPatchWrite, &context, &failed);
    LOG("STREAM delta result=%d record=%u last-rc=0x%x\n",
        result, (unsigned)failed, context.last_result);
    if (result == -4) {
        LOG("STREAM delta rollback unverified; usb remains paused\n");
        for (;;) svcSleepThread(1000000000ULL);
    }
    svcCloseHandle(debug);
    applied = result >= 0;
    return applied;
}
#endif

static Result _setupIsoProbe(void)
{
#ifndef ISO_PROBE_MPS
#define ISO_PROBE_MPS 192
#endif
#ifndef ISO_PROBE_INTERVAL
#define ISO_PROBE_INTERVAL 4
#endif
    if (!_logIsoTarget()) return MAKERESULT(Module_Libnx, LibnxError_BadInput);
    Result rc = usbDsRegisterInterface(&g_isoInterface);
    if (R_FAILED(rc)) return rc;
    /* The matching controller patch is deliberately restricted to EP 83. */
    if (g_isoInterface->interface_index != 2)
        return MAKERESULT(Module_Libnx, LibnxError_BadInput);
#ifndef ISO_PROBE_ALT1
    const struct usb_interface_descriptor iface_only = {
        .bLength = USB_DT_INTERFACE_SIZE, .bDescriptorType = USB_DT_INTERFACE,
        .bInterfaceNumber = 2, .bAlternateSetting = 0, .bNumEndpoints = 1,
        .bInterfaceClass = 0xff, .bInterfaceSubClass = 0x49, .bInterfaceProtocol = 1,
    };
#else
    const struct usb_interface_descriptor iface_alt0 = {
        .bLength = USB_DT_INTERFACE_SIZE, .bDescriptorType = USB_DT_INTERFACE,
        .bInterfaceNumber = 2, .bAlternateSetting = 0, .bNumEndpoints = 0,
        .bInterfaceClass = 0xff, .bInterfaceSubClass = 0x49, .bInterfaceProtocol = 1,
    };
    const struct usb_interface_descriptor iface_alt1 = {
        .bLength = USB_DT_INTERFACE_SIZE, .bDescriptorType = USB_DT_INTERFACE,
        .bInterfaceNumber = 2, .bAlternateSetting = 1, .bNumEndpoints = 1,
        .bInterfaceClass = 0xff, .bInterfaceSubClass = 0x49, .bInterfaceProtocol = 1,
    };
#endif
    const struct usb_endpoint_descriptor ep = {
        .bLength = USB_DT_ENDPOINT_SIZE, .bDescriptorType = USB_DT_ENDPOINT,
        .bEndpointAddress = 0x83, .bmAttributes = USB_TRANSFER_TYPE_ISOCHRONOUS,
        .wMaxPacketSize = ISO_PROBE_MPS, .bInterval = ISO_PROBE_INTERVAL,
    };
    const struct usb_ss_endpoint_companion_descriptor companion = {
        .bLength = sizeof(companion), .bDescriptorType = USB_DT_SS_ENDPOINT_COMPANION,
        .bMaxBurst = 0, .bmAttributes = 0, .wBytesPerInterval = ISO_PROBE_PACKET_SIZE,
    };
    const UsbDeviceSpeed speeds[] = {UsbDeviceSpeed_High, UsbDeviceSpeed_Super};
    for (unsigned i = 0; i < 2; ++i) {
        struct usb_endpoint_descriptor speed_ep = ep;
        if (speeds[i] == UsbDeviceSpeed_Super) speed_ep.bInterval = 4;
#ifdef ISO_PROBE_ALT1
        rc = usbDsInterface_AppendConfigurationData(g_isoInterface, speeds[i],
            &iface_alt0, sizeof(iface_alt0));
        if (R_FAILED(rc)) return rc;
        rc = usbDsInterface_AppendConfigurationData(g_isoInterface, speeds[i],
            &iface_alt1, sizeof(iface_alt1));
#else
        rc = usbDsInterface_AppendConfigurationData(g_isoInterface, speeds[i],
            &iface_only, sizeof(iface_only));
#endif
        if (R_FAILED(rc)) return rc;
        rc = usbDsInterface_AppendConfigurationData(g_isoInterface, speeds[i], &speed_ep, USB_DT_ENDPOINT_SIZE);
        if (R_FAILED(rc)) return rc;
        if (speeds[i] == UsbDeviceSpeed_Super) {
            rc = usbDsInterface_AppendConfigurationData(g_isoInterface, speeds[i], &companion, sizeof(companion));
            if (R_FAILED(rc)) return rc;
        }
    }
    rc = usbDsInterface_RegisterEndpoint(g_isoInterface, &g_isoEndpoint, 0x83);
    if (R_FAILED(rc)) return rc;
    g_isoStatus.magic = ISO_PROBE_STATUS_MAGIC;
    g_isoStatus.version = 1;
    g_isoStatus.endpoint = 0x83;
    return usbDsInterface_EnableInterface(g_isoInterface);
}

static void _pollIsoProbe(void)
{
    if (!g_isoEndpoint) return;
    UsbDsReportData report = {0};
    Result rc = usbDsEndpoint_GetReportData(g_isoEndpoint, &report);
    g_isoStatus.report_result = rc;
    if (R_FAILED(rc)) return;
    g_isoStatus.report_count = report.report_count;
    if (report.report_count <= 1) {
        IsoProbeDiagnostics diag;
        memcpy(&diag, &report.report[1], sizeof(diag));
        if (diag.magic == ISO_PROBE_DIAG_MAGIC || isoProbeIsBurstDiagnostics(diag.magic) ||
            diag.magic == ISO_PROBE_URB_TRACE_MAGIC ||
            diag.magic == ISO_PROBE_URB_ENTRIES_MAGIC || diag.magic == ISO_PROBE_REPORT_MARKER ||
            diag.magic == ISO_PROBE_ENTER_MARKER)
            memcpy(&g_isoStatus.diagnostics, &diag, sizeof(diag));
        if ((diag.magic == ISO_PROBE_DIAG_MAGIC || isoProbeIsBurstDiagnostics(diag.magic)) &&
            ((diag.terminal & 0x80000000u) || diag.terminal == ISO_PROBE_SUCCESS_RETAINED) &&
            (g_isoStatus.state == ISO_PROBE_PENDING || g_isoStatus.state == ISO_PROBE_RETAINED))
            g_isoStatus.state = ISO_PROBE_RETAINED;
    }
    for (u32 i = 0; i < report.report_count && i < 8; ++i) {
        const UsbDsReportEntry* r = &report.report[i];
        if (r->id != g_isoStatus.urb_id) continue;
        g_isoStatus.report_id = r->id;
        g_isoStatus.requested = r->requestedSize;
        g_isoStatus.transferred = r->transferredSize;
        g_isoStatus.urb_status = r->urb_status;
        /* usb:ds states 3/4/5 are terminal; 1/2 retain DMA ownership. */
        if (r->urb_status >= 3 && r->urb_status <= 5) {
            g_isoStatus.state = r->urb_status == 3 ? ISO_PROBE_COMPLETE : ISO_PROBE_FAILED;
            eventClear(&g_isoEndpoint->CompletionEvent);
#ifdef ISO_PROBE_BURST_MODE
            LOG("ISO seq=%u URB=%u requested=%u raw-count=%u status=%u diag-word2=%u\n",
#else
            LOG("ISO seq=%u URB=%u requested=%u raw-count=%u status=%u events=%u\n",
#endif
                g_isoStatus.sequence, r->id, r->requestedSize, r->transferredSize,
                r->urb_status, g_isoStatus.diagnostics.event_count);
        }
    }
}
#endif

#ifdef ISO_PROBE_STREAM
/* Three 16 ms URBs in flight, posted every 16 ms.  The A23 producer derives
   each first FrameID from MFI+32 ms, so post_k+32ms = start_{k-1}+16ms. */
static void _isoStreamFill(u8 *buffer, u16 sequence)
{
    for (u32 packet = 0; packet < ISO_PROBE_BURST_PACKETS; ++packet) {
        u8 *p = buffer + packet * ISO_PROBE_PACKET_SIZE;
        p[0] = 'I'; p[1] = 'S'; p[2] = 'O'; p[3] = '1';
        p[4] = (u8)sequence;
        p[5] = (u8)(sequence >> 8);
        for (u32 i = 6; i < ISO_PROBE_PACKET_SIZE; ++i)
            p[i] = (u8)(i ^ sequence ^ (sequence >> 8));
        ++sequence;
    }
}

static void _isoStreamThreadFunc(void *arg)
{
    (void)arg;
    LOG("ISO stream thread start\n");
    /* The host has already queued its first ISO read when it sends START; give
       the START ACK a moment to land before the first submission. */
    svcSleepThread(10E+6);
    const u64 step = armGetSystemTickFreq() * 16 / 1000;
    u64 next = svcGetSystemTick();
    while (!g_isoStreamStop) {
        UsbDsReportData report = {0};
        Result rc = usbDsEndpoint_GetReportData(g_isoEndpoint, &report);
        if (R_SUCCEEDED(rc)) {
            for (u32 i = 0; i < report.report_count && i < 8; ++i) {
                for (u32 b = 0; b < ISO_STREAM_BUFFERS; ++b) {
                    if (g_isoStreamBusy[b] && g_isoStreamUrb[b] == report.report[i].id) {
                        g_isoStreamBusy[b] = false;
                        if (g_isoStreamCompletes < 3)
                            LOG("ISO stream complete urb=%u\n", g_isoStreamUrb[b]);
                        ++g_isoStreamCompletes;
                    }
                }
            }
        }
        const u64 now = svcGetSystemTick();
        if (now >= next) {
            for (u32 b = 0; b < ISO_STREAM_BUFFERS; ++b) {
                if (g_isoStreamBusy[b] || g_isoStreamUsed[b]) continue;
                _isoStreamFill(g_isoStreamBuf[b], (u16)g_isoStreamSeq);
                g_isoStreamSeq += ISO_PROBE_BURST_PACKETS;
                armDCacheFlush(g_isoStreamBuf[b], ISO_STREAM_BYTES);
                eventClear(&g_isoEndpoint->CompletionEvent);
                u32 urb = 0;
                ++g_isoStreamAttempts;
                if (g_isoStreamAttempts <= 3)
                    LOG("ISO stream try b=%u len=%u\n", b, (unsigned)ISO_STREAM_BYTES);
                rc = usbDsEndpoint_PostBufferAsync(g_isoEndpoint, g_isoStreamBuf[b],
                    ISO_STREAM_BYTES, &urb);
                if (g_isoStreamAttempts <= 3)
                    LOG("ISO stream post rc=0x%x urb=%u\n", rc, urb);
                if (R_SUCCEEDED(rc)) {
                    g_isoStreamBusy[b] = true;
                    g_isoStreamUsed[b] = true;
                    g_isoStreamUrb[b] = urb;
                    ++g_isoStreamPosts;
                    if (g_isoStreamPosts % 100 == 0)
                        LOG("ISO stream posts=%u completes=%u errors=%u late=%u\n",
                            g_isoStreamPosts, g_isoStreamCompletes,
                            g_isoStreamErrors, g_isoStreamLate);
                } else {
                    ++g_isoStreamErrors;
                }
                break;
            }
            next += step;
            if (next < now) {
                ++g_isoStreamLate;
                next = now + step;
            }
        }
        svcSleepThread(1000000);
    }
    if (g_isoEndpoint) {
        usbDsEndpoint_Cancel(g_isoEndpoint);
        eventWait(&g_isoEndpoint->CompletionEvent, 100E+6);
        UsbDsReportData report = {0};
        usbDsEndpoint_GetReportData(g_isoEndpoint, &report);
    }
    for (u32 b = 0; b < ISO_STREAM_BUFFERS; ++b) g_isoStreamBusy[b] = false;
    g_isoStreamExited = true;
}

static Result _isoStartStream(void)
{
    if (g_isoStreamRun) return 0;
    g_isoStreamStop = false;
    g_isoStreamExited = false;
    g_isoStreamSeq = 0;
    g_isoStreamPosts = g_isoStreamCompletes = g_isoStreamErrors = g_isoStreamLate = 0;
    g_isoStreamAttempts = 0;
    for (u32 b = 0; b < ISO_STREAM_BUFFERS; ++b) {
        g_isoStreamBusy[b] = false;
        g_isoStreamUsed[b] = false;
    }
    Result rc = threadCreate(&g_isoStreamThread, _isoStreamThreadFunc, NULL,
        g_isoStreamStack, sizeof(g_isoStreamStack), 0x2C, -2);
    LOG("ISO stream create rc=0x%x\n", rc);
    if (R_SUCCEEDED(rc)) {
        rc = threadStart(&g_isoStreamThread);
        LOG("ISO stream start rc=0x%x\n", rc);
        if (R_FAILED(rc)) threadClose(&g_isoStreamThread);
    }
    if (R_SUCCEEDED(rc)) g_isoStreamRun = true;
    return rc;
}

static void _isoStopStream(void)
{
    if (!g_isoStreamRun) return;
    g_isoStreamStop = true;
    for (u32 i = 0; i < 1000 && !g_isoStreamExited; ++i) svcSleepThread(1000000);
    LOG("ISO stream stop exited=%u posts=%u completes=%u errors=%u late=%u attempts=%u\n",
        g_isoStreamExited, g_isoStreamPosts, g_isoStreamCompletes,
        g_isoStreamErrors, g_isoStreamLate, g_isoStreamAttempts);
    if (g_isoStreamExited) {
        threadWaitForExit(&g_isoStreamThread);
        threadClose(&g_isoStreamThread);
    }
    g_isoStreamRun = false;
}
#endif

#ifdef ALT1_PROBE
// Vendor alt1 probe: one interface with alt0 (no endpoint) and alt1 (bulk IN
// 0x84).  It answers whether usb:ds installs an explicitly registered endpoint
// that only appears in alt1, without UAC descriptors or the ISO patch.
static UsbDsInterface* g_alt1Interface;
static UsbDsEndpoint* g_alt1Endpoint;
static u8 alignas(0x1000) g_alt1Buffer[ALT1_PROBE_BUFFER_SIZE];
static u8 g_alt1DescriptorsHs[64];
static u8 g_alt1DescriptorsSs[64];
static Alt1ProbeStatus g_alt1Status;

static size_t _buildAlt1Descriptors(u8 iface, bool superspeed, u8* out, size_t cap)
{
    size_t n = 0;
#ifdef ALT1_PROBE_ENDPOINT_ALT0
    const bool endpoint_in_alt0 = true;
#else
    const bool endpoint_in_alt0 = false;
#endif
#define ALT1_PUT(value) do { if (n >= cap) return 0; out[n++] = (u8)(value); } while (0)
    for (int alt = 0; alt < 2; ++alt) {
        const bool has_endpoint = alt == 1 || endpoint_in_alt0;
        ALT1_PUT(9); ALT1_PUT(USB_DT_INTERFACE); ALT1_PUT(iface);
        ALT1_PUT((u8)alt); ALT1_PUT(has_endpoint ? 1 : 0);
        ALT1_PUT(0xFF); ALT1_PUT(0); ALT1_PUT(0); ALT1_PUT(0);
        if (!has_endpoint) continue;
        ALT1_PUT(USB_DT_ENDPOINT_SIZE); ALT1_PUT(USB_DT_ENDPOINT); ALT1_PUT(0x84);
        ALT1_PUT(0x02); ALT1_PUT(0x00); ALT1_PUT(superspeed ? 0x04 : 0x02); ALT1_PUT(0);
        if (superspeed) {
            ALT1_PUT(6); ALT1_PUT(USB_DT_SS_ENDPOINT_COMPANION);
            ALT1_PUT(0); ALT1_PUT(0); ALT1_PUT(0); ALT1_PUT(0);
        }
    }
#undef ALT1_PUT
    return n;
}

static Result _setupAlt1Probe(void)
{
    Result rc = usbDsRegisterInterface(&g_alt1Interface);
    if (R_FAILED(rc)) {
        LOG("ALT1 register interface failed: 0x%x\n", rc);
        return rc;
    }
    const u8 iface = g_alt1Interface->interface_index;
    const size_t hsLen = _buildAlt1Descriptors(iface, false, g_alt1DescriptorsHs,
                                               sizeof(g_alt1DescriptorsHs));
    const size_t ssLen = _buildAlt1Descriptors(iface, true, g_alt1DescriptorsSs,
                                               sizeof(g_alt1DescriptorsSs));
    if (!hsLen || !ssLen) return MAKERESULT(Module_Libnx, LibnxError_BadInput);

    R_RET_ON_FAIL(usbDsInterface_AppendConfigurationData(g_alt1Interface,
        UsbDeviceSpeed_High, g_alt1DescriptorsHs, hsLen));
    R_RET_ON_FAIL(usbDsInterface_AppendConfigurationData(g_alt1Interface,
        UsbDeviceSpeed_Super, g_alt1DescriptorsSs, ssLen));
    R_RET_ON_FAIL(usbDsInterface_RegisterEndpoint(g_alt1Interface,
        &g_alt1Endpoint, 0x84));
    R_RET_ON_FAIL(usbDsInterface_EnableInterface(g_alt1Interface));

    memset(&g_alt1Status, 0, sizeof(g_alt1Status));
    g_alt1Status.magic = ALT1_PROBE_STATUS_MAGIC;
    g_alt1Status.version = 1;
    LOG("ALT1 probe iface=%u ep=0x84 hs=%u ss=%u\n",
        iface, (unsigned)hsLen, (unsigned)ssLen);
    return 0;
}

static void _pollAlt1Probe(void)
{
    if (!g_alt1Endpoint || g_alt1Status.state != ALT1_PROBE_PENDING) return;
    UsbDsReportData report = {0};
    if (R_FAILED(usbDsEndpoint_GetReportData(g_alt1Endpoint, &report))) return;
    for (u32 i = 0; i < report.report_count && i < 8; ++i) {
        const UsbDsReportEntry* r = &report.report[i];
        if (r->id != g_alt1Status.urb_id) continue;
        g_alt1Status.reports++;
        g_alt1Status.transferred = r->transferredSize;
        g_alt1Status.urb_status = r->urb_status;
        if (r->urb_status >= 3 && r->urb_status <= 5) {
            g_alt1Status.completed = 1;
            g_alt1Status.state = r->urb_status == 3 ? ALT1_PROBE_COMPLETE : ALT1_PROBE_FAILED;
            eventClear(&g_alt1Endpoint->CompletionEvent);
        }
    }
}
#endif

// UAC (Audio) context
static struct {
    bool initialized;
    bool streaming;

    UsbDsInterface* acInterface;    // Audio Control
    UsbDsInterface* asInterface;    // Audio Streaming
    UsbDsEndpoint* audioEndpointIn;

#ifdef UAC_U2_PATCH
    bool burstPosted;               // U2: one bounded train per boot
    u32 postSeq;                    // U2: diagnostic post sequence
    u32 patternFrame;               // U2: running 48 kHz stereo frame phase
#endif

    Mutex audioMutex;
} g_uacCtx;

// ============================================================================
// USB Descriptor Data
// ============================================================================

// Interface Association Descriptor (groups VC and VS interfaces)
static struct __attribute__((packed)) {
    u8  bLength;
    u8  bDescriptorType;
    u8  bFirstInterface;
    u8  bInterfaceCount;
    u8  bFunctionClass;
    u8  bFunctionSubClass;
    u8  bFunctionProtocol;
    u8  iFunction;
} g_iadDescriptor = {
    .bLength = 8,
    .bDescriptorType = USB_DT_INTERFACE_ASSOCIATION,
    .bFirstInterface = 0,
    .bInterfaceCount = 2,
    .bFunctionClass = USB_CLASS_VIDEO,
    .bFunctionSubClass = UVC_SC_VIDEO_INTERFACE_COLLECTION,
    .bFunctionProtocol = UVC_PC_PROTOCOL_UNDEFINED,
    .iFunction = 0,
};

// Video Control Interface Descriptor
static struct usb_interface_descriptor g_vcInterfaceDesc = {
    .bLength = USB_DT_INTERFACE_SIZE,
    .bDescriptorType = USB_DT_INTERFACE,
    .bInterfaceNumber = 0,
    .bAlternateSetting = 0,
    .bNumEndpoints = 0,  // No interrupt endpoint for simplicity
    .bInterfaceClass = USB_CLASS_VIDEO,
    .bInterfaceSubClass = UVC_SC_VIDEOCONTROL,
    .bInterfaceProtocol = UVC_PC_PROTOCOL_15,
    .iInterface = 0,
};

// Video Control Class-Specific Descriptors
static struct __attribute__((packed)) {
    // VC Header
    UvcVcHeaderDescriptor header;
    // Input Terminal (Camera). Must be the full 18-byte camera terminal:
    // Linux uvc_parse_standard_control() rejects the ENTIRE device (-EINVAL,
    // no /dev/video node) if an ITT_CAMERA terminal is shorter than
    // 15 + bControlSize bytes - the focal-length fields are not optional.
    UvcInputTerminalDescriptor inputTerminal;
    // Output Terminal (USB)
    UvcOutputTerminalDescriptor outputTerminal;
} g_vcDescriptors = {
    .header = {
        .bLength = sizeof(UvcVcHeaderDescriptor),
        .bDescriptorType = UVC_CS_INTERFACE,
        .bDescriptorSubType = UVC_VC_HEADER,
        .bcdUVC = 0x0150,  // UVC 1.5
        .wTotalLength = sizeof(g_vcDescriptors),
        .dwClockFrequency = UVC_CLOCK_FREQUENCY,
        .bInCollection = 1,
        .baInterfaceNr1 = 1,  // VideoStreaming interface
    },
    .inputTerminal = {
        .bLength = sizeof(UvcInputTerminalDescriptor),
        .bDescriptorType = UVC_CS_INTERFACE,
        .bDescriptorSubType = UVC_VC_INPUT_TERMINAL,
        .bTerminalID = UVC_ENTITY_INPUT_TERMINAL,
        .wTerminalType = UVC_ITT_CAMERA,
        .bAssocTerminal = 0,
        .iTerminal = 0,
        .wObjectiveFocalLengthMin = 0,
        .wObjectiveFocalLengthMax = 0,
        .wOcularFocalLength = 0,
        .bControlSize = 3,
        .bmControls = { 0, 0, 0 },  // No camera controls supported
    },
    .outputTerminal = {
        .bLength = sizeof(UvcOutputTerminalDescriptor),
        .bDescriptorType = UVC_CS_INTERFACE,
        .bDescriptorSubType = UVC_VC_OUTPUT_TERMINAL,
        .bTerminalID = UVC_ENTITY_OUTPUT_TERMINAL,
        .wTerminalType = UVC_TT_STREAMING,
        .bAssocTerminal = 0,
        .bSourceID = UVC_ENTITY_INPUT_TERMINAL,
        .iTerminal = 0,
    },
};

// Video Streaming Interface Descriptor (single alternate setting 0).
// For a BULK-transfer UVC stream the streaming endpoint MUST live in the
// default alternate setting (alt 0). The zero-bandwidth-alt0 / streaming-alt1
// split is an isochronous-only convention (iso endpoints reserve bus bandwidth
// and need a zero-bw setting to release it). Host bulk drivers (Linux uvcvideo,
// Windows usbvideo.sys) locate the bulk VS endpoint in alt 0 and never issue
// SET_INTERFACE for bulk - if the endpoint is hidden in alt 1 the host opens no
// pipe and no frames flow even though the device enumerates. This mirrors the
// proven libnx usbComms / SysDVR bulk USB mode (single interface, endpoint in
// the default setting).
static struct usb_interface_descriptor g_vsInterfaceDesc0 = {
    .bLength = USB_DT_INTERFACE_SIZE,
    .bDescriptorType = USB_DT_INTERFACE,
    .bInterfaceNumber = 1,
    .bAlternateSetting = 0,
    .bNumEndpoints = 1,  // Bulk video endpoint in the default alt setting
    .bInterfaceClass = USB_CLASS_VIDEO,
    .bInterfaceSubClass = UVC_SC_VIDEOSTREAMING,
    .bInterfaceProtocol = UVC_PC_PROTOCOL_UNDEFINED,
    .iInterface = 0,
};

// Video Streaming Class-Specific Descriptors
static struct __attribute__((packed)) {
    // VS Input Header
    UvcVsInputHeaderDescriptor inputHeader;
    // H.264 Format - VS_FORMAT_FRAME_BASED (UVC spec: 28 bytes)
    struct __attribute__((packed)) {
        u8  bLength;
        u8  bDescriptorType;
        u8  bDescriptorSubType;
        u8  bFormatIndex;
        u8  bNumFrameDescriptors;
        u8  guidFormat[16];
        u8  bBitsPerPixel;
        u8  bDefaultFrameIndex;
        u8  bAspectRatioX;
        u8  bAspectRatioY;
        u8  bmInterlaceFlags;
        u8  bCopyProtect;
        u8  bVariableSize;
    } h264Format;
    // H.264 Frame - VS_FRAME_FRAME_BASED (UVC spec: 26 + 4*n bytes)
    struct __attribute__((packed)) {
        u8  bLength;
        u8  bDescriptorType;
        u8  bDescriptorSubType;
        u8  bFrameIndex;
        u8  bmCapabilities;
        u16 wWidth;
        u16 wHeight;
        u32 dwMinBitRate;
        u32 dwMaxBitRate;
        u32 dwDefaultFrameInterval;
        u8  bFrameIntervalType;
        u32 dwBytesPerLine;
        u32 dwFrameInterval1;
    } h264Frame;
    // Color Matching Descriptor
    UvcColorMatchingDescriptor colorMatching;
} g_vsDescriptors = {
    .inputHeader = {
        .bLength = sizeof(UvcVsInputHeaderDescriptor),
        .bDescriptorType = UVC_CS_INTERFACE,
        .bDescriptorSubType = UVC_VS_INPUT_HEADER,
        .bNumFormats = 1,
        .wTotalLength = sizeof(g_vsDescriptors),
        .bEndpointAddress = USB_ENDPOINT_IN | 1,
        .bmInfo = 0,
        .bTerminalLink = UVC_ENTITY_OUTPUT_TERMINAL,
        .bStillCaptureMethod = 0,
        .bTriggerSupport = 0,
        .bTriggerUsage = 0,
        .bControlSize = 1,
        .bmaControls1 = 0,
    },
    .h264Format = {
        .bLength = 28,  // VS_FORMAT_FRAME_BASED: 28 bytes per UVC spec
        .bDescriptorType = UVC_CS_INTERFACE,
        .bDescriptorSubType = UVC_VS_FORMAT_FRAME_BASED,
        .bFormatIndex = 1,
        .bNumFrameDescriptors = 1,
        .guidFormat = UVC_GUID_FORMAT_H264,
        .bBitsPerPixel = 0,         // variable for H.264
        .bDefaultFrameIndex = 1,
        .bAspectRatioX = 16,
        .bAspectRatioY = 9,
        .bmInterlaceFlags = 0,
        .bCopyProtect = 0,
        .bVariableSize = 1,
    },
    .h264Frame = {
        .bLength = 30,  // VS_FRAME_FRAME_BASED: 26 + 4*1 = 30 bytes (1 interval)
        .bDescriptorType = UVC_CS_INTERFACE,
        .bDescriptorSubType = UVC_VS_FRAME_FRAME_BASED,
        .bFrameIndex = 1,
        .bmCapabilities = 0,
        .wWidth = UVC_VIDEO_WIDTH,
        .wHeight = UVC_VIDEO_HEIGHT,
        .dwMinBitRate = UVC_MIN_BITRATE,
        .dwMaxBitRate = UVC_MAX_BITRATE,
        .dwDefaultFrameInterval = UVC_FRAME_INTERVAL_30FPS,
        .bFrameIntervalType = 1,
        .dwBytesPerLine = 0,        // variable for H.264
        .dwFrameInterval1 = UVC_FRAME_INTERVAL_30FPS,
    },
    .colorMatching = {
        .bLength = sizeof(UvcColorMatchingDescriptor),
        .bDescriptorType = UVC_CS_INTERFACE,
        .bDescriptorSubType = UVC_VS_COLORFORMAT,
        .bColorPrimaries = 1,           // BT.709 (sRGB)
        .bTransferCharacteristics = 1,  // BT.709
        .bMatrixCoefficients = 4,       // SMPTE 170M
    },
};

// Bulk endpoint for video streaming
static struct usb_endpoint_descriptor g_videoEndpointDesc = {
    .bLength = USB_DT_ENDPOINT_SIZE,
    .bDescriptorType = USB_DT_ENDPOINT,
    .bEndpointAddress = USB_ENDPOINT_IN | 1,
    .bmAttributes = USB_TRANSFER_TYPE_BULK,
    .wMaxPacketSize = 512,  // High-speed bulk max
    .bInterval = 0,
};

// Super-speed endpoint companion
static struct usb_ss_endpoint_companion_descriptor g_ssCompanionDesc = {
    .bLength = sizeof(struct usb_ss_endpoint_companion_descriptor),
    .bDescriptorType = USB_DT_SS_ENDPOINT_COMPANION,
    .bMaxBurst = 15,
    .bmAttributes = 0,
    .wBytesPerInterval = 0,
};

// ============================================================================
// UAC (Audio) Standard Layer
//
// Descriptor bytes and the control state machine live in uac_standard.c and
// are covered by research/usb-ds-iso/tests/test_uac_standard.py.  The
// configuration path stays uncalled until the device-side ISO producer and
// the alt1 lifecycle are verified on hardware.

static UacStandardState g_uacStd;
static u8 g_uacAcDescriptors[64];
static u8 g_uacAsHsDescriptors[64];
static u8 g_uacAsSsDescriptors[64];

// ============================================================================
// Helper Functions
// ============================================================================

void UvcBuildDefaultProbeControl(UvcProbeCommitControl* ctrl, UvcVideoFormat format)
{
    memset(ctrl, 0, sizeof(UvcProbeCommitControl));

    ctrl->bmHint = 0x0001;  // dwFrameInterval field is valid
    ctrl->bFormatIndex = 1;
    ctrl->bFrameIndex = 1;
    ctrl->dwFrameInterval = UVC_FRAME_INTERVAL_30FPS;
    ctrl->wKeyFrameRate = 0;
    ctrl->wPFrameRate = 0;
    ctrl->wCompQuality = 0;
    ctrl->wCompWindowSize = 0;
    ctrl->wDelay = 0;
    ctrl->dwMaxVideoFrameSize = UVC_H264_MAX_FRAME_SIZE;
    ctrl->dwMaxPayloadTransferSize = 0x4000;  // 16KB chunks
    ctrl->dwClockFrequency = UVC_CLOCK_FREQUENCY;
    ctrl->bmFramingInfo = 0x03;  // Frame ID required, EOF required
    ctrl->bPreferedVersion = 1;
    ctrl->bMinVersion = 1;
    ctrl->bMaxVersion = 1;
}

u8 UvcBuildPayloadHeader(u8* header, u32 pts, bool eof, u8 frameId)
{
    (void)pts;

    // Minimal 2-byte header: EOH + FID/EOF only, NO PTS/SCR.
    // Linux uvcvideo delimits frames by the FID toggle + EOF bit and ignores
    // the payload clock fields, but Windows usbvideo.sys schedules frame
    // presentation against them - a device clock it cannot correlate to bus
    // time makes it queue frames defensively (seconds of capture latency).
    // Omitting PTS is fully spec-compliant and makes every host render
    // frames on arrival, which is exactly what a live capture device wants.
    header[0] = 2;
    header[1] = UVC_STREAM_HEADER_EOH;

    if (eof) {
        header[1] |= UVC_STREAM_HEADER_EOF;
    }

    if (frameId & 1) {
        header[1] |= UVC_STREAM_HEADER_FID;
    }

    return 2;
}

// ============================================================================
// USB Descriptor Setup (HOS 5.0+)
// ============================================================================

static Result _setupDescriptors5x(const UvcDeviceConfig* config)
{
    Result rc = 0;
    u8 iManufacturer, iProduct, iSerialNumber;

    static const u16 supportedLangs[] = { 0x0409 };  // English US

    rc = usbDsAddUsbLanguageStringDescriptor(NULL, supportedLangs, 1);
    if (R_FAILED(rc)) return rc;

    rc = usbDsAddUsbStringDescriptor(&iManufacturer, config->manufacturer);
    if (R_FAILED(rc)) return rc;

    rc = usbDsAddUsbStringDescriptor(&iProduct, config->product);
    if (R_FAILED(rc)) return rc;

    rc = usbDsAddUsbStringDescriptor(&iSerialNumber, config->serialNumber);
    if (R_FAILED(rc)) return rc;

    struct usb_device_descriptor deviceDesc = {
        .bLength = USB_DT_DEVICE_SIZE,
        .bDescriptorType = USB_DT_DEVICE,
        .bcdUSB = 0x0200,
        .bDeviceClass = USB_CLASS_MISC,      // Multi-interface device
        .bDeviceSubClass = 0x02,              // Common Class
        .bDeviceProtocol = 0x01,              // Interface Association
        .bMaxPacketSize0 = 64,
        .idVendor = config->vendorId,
        .idProduct = config->productId,
        .bcdDevice = 0x0100,
        .iManufacturer = iManufacturer,
        .iProduct = iProduct,
        .iSerialNumber = iSerialNumber,
        .bNumConfigurations = 1,
    };

    // High Speed (USB 2.0)
    deviceDesc.bcdUSB = 0x0200;
    rc = usbDsSetUsbDeviceDescriptor(UsbDeviceSpeed_High, &deviceDesc);
    if (R_FAILED(rc)) return rc;

    // Super Speed (USB 3.0)
    deviceDesc.bcdUSB = 0x0300;
    deviceDesc.bMaxPacketSize0 = 9;  // 2^9 = 512 bytes
    rc = usbDsSetUsbDeviceDescriptor(UsbDeviceSpeed_Super, &deviceDesc);
    if (R_FAILED(rc)) return rc;

    // BOS Descriptor for USB 3.0
    static const u8 bosDescriptor[] = {
        0x05,                   // bLength
        USB_DT_BOS,             // bDescriptorType
        0x16, 0x00,             // wTotalLength
        0x02,                   // bNumDeviceCaps

        // USB 2.0 Extension
        0x07,                   // bLength
        USB_DT_DEVICE_CAPABILITY,
        0x02,                   // bDevCapabilityType (USB 2.0 Extension)
        0x02, 0x00, 0x00, 0x00, // bmAttributes (LPM supported)

        // SuperSpeed USB
        0x0A,                   // bLength
        USB_DT_DEVICE_CAPABILITY,
        0x03,                   // bDevCapabilityType (SuperSpeed)
        0x00,                   // bmAttributes
        0x0E, 0x00,             // wSpeedsSupported (FS, HS, SS)
        0x03,                   // bFunctionalitySupport (SS)
        0x00,                   // bU1DevExitLat
        0x00, 0x00,             // wU2DevExitLat
    };
    rc = usbDsSetBinaryObjectStore(bosDescriptor, sizeof(bosDescriptor));
    if (R_FAILED(rc)) return rc;

    return 0;
}

// ============================================================================
// Interface Setup
// ============================================================================

static Result _setupInterfaces5x(void)
{
    Result rc = 0;

    // Register Video Control interface FIRST (gets index 0).
    // The IAD must be appended on the first registered interface.
    rc = usbDsRegisterInterface(&g_uvcCtx.controlInterface);
    if (R_FAILED(rc)) return rc;

    u8 vcIfaceNum = g_uvcCtx.controlInterface->interface_index;
    LOG("VC interface registered (idx=%u)\n", vcIfaceNum);

    // Register Video Streaming interface SECOND (gets index 1)
    rc = usbDsRegisterInterface(&g_uvcCtx.streamingInterface);
    if (R_FAILED(rc)) return rc;

    u8 vsIfaceNum = g_uvcCtx.streamingInterface->interface_index;
    LOG("VS interface registered (idx=%u)\n", vsIfaceNum);

    // Update descriptor interface numbers
    g_iadDescriptor.bFirstInterface = vcIfaceNum;
    g_vcInterfaceDesc.bInterfaceNumber = vcIfaceNum;
    g_vcDescriptors.header.baInterfaceNr1 = vsIfaceNum;
    g_vsInterfaceDesc0.bInterfaceNumber = vsIfaceNum;
    g_videoEndpointDesc.bEndpointAddress = USB_ENDPOINT_IN | (vsIfaceNum + 1);
    g_vsDescriptors.inputHeader.bEndpointAddress = g_videoEndpointDesc.bEndpointAddress;

    // Append VC descriptors (with IAD - must be on the first registered interface)
    // UVC order: IAD → VC Interface → VC CS → VS Interface (alt0) → VS CS → VS bulk EP

    // High Speed VC (IAD + VC interface + VC class-specific)
    R_RET_ON_FAIL(usbDsInterface_AppendConfigurationData(g_uvcCtx.controlInterface,
        UsbDeviceSpeed_High, &g_iadDescriptor, sizeof(g_iadDescriptor)));
    R_RET_ON_FAIL(usbDsInterface_AppendConfigurationData(g_uvcCtx.controlInterface,
        UsbDeviceSpeed_High, &g_vcInterfaceDesc, USB_DT_INTERFACE_SIZE));
    R_RET_ON_FAIL(usbDsInterface_AppendConfigurationData(g_uvcCtx.controlInterface,
        UsbDeviceSpeed_High, &g_vcDescriptors, sizeof(g_vcDescriptors)));

    // Super Speed VC
    R_RET_ON_FAIL(usbDsInterface_AppendConfigurationData(g_uvcCtx.controlInterface,
        UsbDeviceSpeed_Super, &g_iadDescriptor, sizeof(g_iadDescriptor)));
    R_RET_ON_FAIL(usbDsInterface_AppendConfigurationData(g_uvcCtx.controlInterface,
        UsbDeviceSpeed_Super, &g_vcInterfaceDesc, USB_DT_INTERFACE_SIZE));
    R_RET_ON_FAIL(usbDsInterface_AppendConfigurationData(g_uvcCtx.controlInterface,
        UsbDeviceSpeed_Super, &g_vcDescriptors, sizeof(g_vcDescriptors)));

    R_RET_ON_FAIL(usbDsInterface_EnableInterface(g_uvcCtx.controlInterface));

    // Append VS descriptors (single alt 0: interface → VS class-specific → bulk EP)
    // High Speed VS
    R_RET_ON_FAIL(usbDsInterface_AppendConfigurationData(g_uvcCtx.streamingInterface,
        UsbDeviceSpeed_High, &g_vsInterfaceDesc0, USB_DT_INTERFACE_SIZE));
    R_RET_ON_FAIL(usbDsInterface_AppendConfigurationData(g_uvcCtx.streamingInterface,
        UsbDeviceSpeed_High, &g_vsDescriptors, sizeof(g_vsDescriptors)));
    g_videoEndpointDesc.wMaxPacketSize = 512;
    R_RET_ON_FAIL(usbDsInterface_AppendConfigurationData(g_uvcCtx.streamingInterface,
        UsbDeviceSpeed_High, &g_videoEndpointDesc, USB_DT_ENDPOINT_SIZE));

    // Super Speed VS
    R_RET_ON_FAIL(usbDsInterface_AppendConfigurationData(g_uvcCtx.streamingInterface,
        UsbDeviceSpeed_Super, &g_vsInterfaceDesc0, USB_DT_INTERFACE_SIZE));
    R_RET_ON_FAIL(usbDsInterface_AppendConfigurationData(g_uvcCtx.streamingInterface,
        UsbDeviceSpeed_Super, &g_vsDescriptors, sizeof(g_vsDescriptors)));
    g_videoEndpointDesc.wMaxPacketSize = 1024;
    R_RET_ON_FAIL(usbDsInterface_AppendConfigurationData(g_uvcCtx.streamingInterface,
        UsbDeviceSpeed_Super, &g_videoEndpointDesc, USB_DT_ENDPOINT_SIZE));
    R_RET_ON_FAIL(usbDsInterface_AppendConfigurationData(g_uvcCtx.streamingInterface,
        UsbDeviceSpeed_Super, &g_ssCompanionDesc, sizeof(g_ssCompanionDesc)));

    // Register the video endpoint on VS
    R_RET_ON_FAIL(usbDsInterface_RegisterEndpoint(g_uvcCtx.streamingInterface,
        &g_uvcCtx.videoEndpointIn, g_videoEndpointDesc.bEndpointAddress));

    R_RET_ON_FAIL(usbDsInterface_EnableInterface(g_uvcCtx.streamingInterface));
    LOG("VS interface enabled (idx=%u)\n", vsIfaceNum);

    return 0;
}

// ============================================================================
// UAC Interface Setup - DEAD CODE, never called.
//
// Re-enable only after device Isoch submission and alt-setting lifecycle are
// verified. Appended configuration data cannot be removed for fallback.
// ============================================================================

static Result _setupAudioInterfaces5x(void)
{
#ifdef ISO_PROBE
    // libnx/usb:ds expose four interface slots. UVC uses VC+VS; ISO_PROBE
    // would take the third, leaving only one for AC+AS. UAC needs both.
    LOG("UAC setup refused: ISO_PROBE occupies an interface slot\n");
    return MAKERESULT(Module_Libnx, LibnxError_BadInput);
#endif

    Result rc = 0;

    rc = usbDsRegisterInterface(&g_uacCtx.acInterface);
    if (R_FAILED(rc)) {
        LOG("Failed to register AC interface: 0x%x\n", rc);
        return rc;
    }

    rc = usbDsRegisterInterface(&g_uacCtx.asInterface);
    if (R_FAILED(rc)) {
        LOG("Failed to register AS interface: 0x%x\n", rc);
        usbDsInterface_Close(g_uacCtx.acInterface);
        g_uacCtx.acInterface = NULL;
        return rc;
    }

    const u8 acIfaceNum = g_uacCtx.acInterface->interface_index;
    const u8 asIfaceNum = g_uacCtx.asInterface->interface_index;
    const u8 epAddress = USB_ENDPOINT_IN | 4;  // 0x84, independent of interface numbers

    const size_t acLen = UacBuildAcConfiguration(acIfaceNum, asIfaceNum,
                                                 g_uacAcDescriptors,
                                                 sizeof(g_uacAcDescriptors));
    const size_t hsLen = UacBuildAsConfiguration(asIfaceNum, epAddress, false,
                                                 g_uacAsHsDescriptors,
                                                 sizeof(g_uacAsHsDescriptors));
    const size_t ssLen = UacBuildAsConfiguration(asIfaceNum, epAddress, true,
                                                 g_uacAsSsDescriptors,
                                                 sizeof(g_uacAsSsDescriptors));
    if (!acLen || !hsLen || !ssLen) {
        LOG("Failed to build UAC descriptors\n");
        return MAKERESULT(Module_Libnx, LibnxError_BadInput);
    }

    // Appended configuration data cannot be removed.  Validate both speed
    // variants before the first append; a failed lint must leave the existing
    // video configuration untouched.
    if (!UacLintConfiguration(g_uacAcDescriptors, acLen, g_uacAsHsDescriptors, hsLen, NULL, 0) ||
        !UacLintConfiguration(g_uacAcDescriptors, acLen, g_uacAsSsDescriptors, ssLen, NULL, 0)) {
        LOG("UAC descriptor lint failed; refusing to append\n");
        return MAKERESULT(Module_Libnx, LibnxError_BadInput);
    }

    // Append both functions before enabling either interface.  Enabling AC
    // before the AS descriptors/endpoint exist can leave the host with an
    // incomplete audio function (observed as a USB device with no audio card
    // on macOS in U0).
    R_RET_ON_FAIL(usbDsInterface_AppendConfigurationData(g_uacCtx.acInterface,
        UsbDeviceSpeed_High, g_uacAcDescriptors, acLen));
    R_RET_ON_FAIL(usbDsInterface_AppendConfigurationData(g_uacCtx.acInterface,
        UsbDeviceSpeed_Super, g_uacAcDescriptors, acLen));
    R_RET_ON_FAIL(usbDsInterface_AppendConfigurationData(g_uacCtx.asInterface,
        UsbDeviceSpeed_High, g_uacAsHsDescriptors, hsLen));
    R_RET_ON_FAIL(usbDsInterface_AppendConfigurationData(g_uacCtx.asInterface,
        UsbDeviceSpeed_Super, g_uacAsSsDescriptors, ssLen));
    R_RET_ON_FAIL(usbDsInterface_RegisterEndpoint(g_uacCtx.asInterface,
        &g_uacCtx.audioEndpointIn, epAddress));
    R_RET_ON_FAIL(usbDsInterface_EnableInterface(g_uacCtx.acInterface));
    R_RET_ON_FAIL(usbDsInterface_EnableInterface(g_uacCtx.asInterface));

    UacStandardInit(&g_uacStd, acIfaceNum, asIfaceNum, epAddress);
    g_uacCtx.initialized = true;
    LOG("UAC initialized: AC=%u AS=%u EP=0x%02x\n", acIfaceNum, asIfaceNum, epAddress);
    return 0;
}

// ============================================================================
// Public API Implementation
// ============================================================================

Result UvcDeviceInitialize(const UvcDeviceConfig* config)
{
    Result rc = 0;

    if (g_uvcCtx.initialized) {
        return MAKERESULT(Module_Libnx, LibnxError_AlreadyInitialized);
    }

    memset(&g_uvcCtx, 0, sizeof(g_uvcCtx));
    rwlockInit(&g_uvcCtx.lock);
    mutexInit(&g_uvcCtx.streamingMutex);

    rc = usbDsInitialize();
    if (R_FAILED(rc)) {
        LOG("usbDsInitialize failed: 0x%x\n", rc);
        return rc;
    }

    memset(&g_uacCtx, 0, sizeof(g_uacCtx));
    mutexInit(&g_uacCtx.audioMutex);

    if (hosversionAtLeast(5, 0, 0)) {
#if (defined(UAC_DESCRIPTOR_PATCH) + defined(UAC_U2_BASE_PATCH) + \
    defined(UAC_U2_PATCH)) > 1
#error "define only one UAC usb patch payload"
#endif
#if defined(UAC_DESCRIPTOR_PATCH) || defined(UAC_U2_BASE_PATCH) || \
    defined(UAC_U2_PATCH)
        bool patch_ok;
#if defined(UAC_U2_PATCH)
        patch_ok = _applyUacU2Patch();
#elif defined(UAC_U2_BASE_PATCH)
        patch_ok = _applyUacU2BasePatch();
#else
        patch_ok = _applyUacDescriptorPatch();
#endif
        if (!patch_ok) {
            LOG("UAC patch failed; refusing to enable the device\n");
            rc = MAKERESULT(Module_Libnx, LibnxError_BadInput);
            goto cleanup;
        }
#endif
/* WARNING: UAC_ONLY removes the USB device entirely on hardware
 * (2026-10-29). Keep it only for offline descriptor inspection; never deploy
 * a UAC_ONLY build. */
#if !(defined(UAC_HOST_PROBE) && defined(UAC_ONLY))
        rc = _setupDescriptors5x(config);
        if (R_FAILED(rc)) {
            LOG("_setupDescriptors5x failed: 0x%x\n", rc);
            goto cleanup;
        }

        rc = _setupInterfaces5x();
        if (R_FAILED(rc)) {
            LOG("_setupInterfaces5x failed: 0x%x\n", rc);
            goto cleanup;
        }
#else
        // UAC-only isolation build: no UVC interfaces, so a 97-byte AC+AS
        // configuration can be used to test usb:ds independently.
        (void)_setupDescriptors5x;
        (void)_setupInterfaces5x;
#endif

#ifdef UAC_HOST_PROBE
#if defined(ISO_PROBE) || defined(ALT1_PROBE)
#error UAC_HOST_PROBE cannot be combined with ISO_PROBE/ALT1_PROBE
#endif
        // Enumeration/control-only UAC build: AC+AS take the two remaining
        // interface slots. The audio thread stays idle because
        // UacDeviceIsStreaming() is false under UAC_HOST_PROBE.
        rc = _setupAudioInterfaces5x();
        if (R_FAILED(rc)) {
            LOG("_setupAudioInterfaces5x failed: 0x%x\n", rc);
            goto cleanup;
        }
#else
        // UAC remains disabled until device ISO and alt-setting support are
        // verified. ISO_PROBE tests a separate vendor alt0 interface first.
        (void)_setupAudioInterfaces5x;  // suppress unused warning
#endif

#ifdef ISO_PROBE
#ifdef ALT1_PROBE
        // Apply the runtime NOP patch through the existing dmnt installer,
        // but do not register the ISO probe interface (the ALT1 probe uses
        // interface 2 and the four-interface budget is tight).
        if (!_logIsoTarget()) {
            LOG("ALT1 runtime patch failed\n");
            rc = MAKERESULT(Module_Libnx, LibnxError_BadInput);
            goto cleanup;
        }
        (void)_setupIsoProbe;
#else
        rc = _setupIsoProbe();
        if (R_FAILED(rc)) goto cleanup;
#endif
#endif
#ifdef ALT1_PROBE
        rc = _setupAlt1Probe();
        if (R_FAILED(rc))
            LOG("ALT1 probe setup failed: 0x%x (video continues)\n", rc);
#endif

        rc = usbDsEnable();
        if (R_FAILED(rc)) {
            LOG("usbDsEnable failed: 0x%x\n", rc);
            goto cleanup;
        }
    }
    else {
        // Pre-5.0 firmware not supported for UVC
        LOG("UVC requires HOS 5.0+\n");
        rc = MAKERESULT(Module_Libnx, LibnxError_IncompatSysVer);
        goto cleanup;
    }

    g_uvcCtx.videoBuffer = g_videoBuffer;
    g_uvcCtx.controlBuffer = g_controlBuffer;

    // Probe and commit start from the same defaults; the host overwrites
    // them during the probe/commit negotiation.
    UvcBuildDefaultProbeControl(&g_uvcCtx.probeControl, UVC_FORMAT_H264);
    memcpy(&g_uvcCtx.commitControl, &g_uvcCtx.probeControl, sizeof(UvcProbeCommitControl));

    g_uvcCtx.state = UVC_STATE_DISCONNECTED;
    g_uvcCtx.initialized = true;

    LOG("UVC device initialized\n");
    return 0;

cleanup:
    usbDsExit();
    return rc;
}

void UvcDeviceExit(void)
{
#ifdef ISO_PROBE
#ifdef ISO_PROBE_STREAM
    _isoStopStream();
#endif
    if (g_isoInterface) {
        usbDsInterface_Close(g_isoInterface);
        g_isoInterface = NULL;
        g_isoEndpoint = NULL;
    }
#endif
#ifdef ALT1_PROBE
    if (g_alt1Endpoint) {
        usbDsEndpoint_Close(g_alt1Endpoint);
        g_alt1Endpoint = NULL;
    }
    if (g_alt1Interface) {
        usbDsInterface_Close(g_alt1Interface);
        g_alt1Interface = NULL;
    }
#endif
    if (!g_uvcCtx.initialized) {
        return;
    }

    rwlockWriteLock(&g_uvcCtx.lock);

    g_uvcCtx.state = UVC_STATE_DISCONNECTED;
    g_uacCtx.streaming = false;

    if (g_uacCtx.asInterface) {
        usbDsInterface_Close(g_uacCtx.asInterface);
        g_uacCtx.asInterface = NULL;
    }

    if (g_uacCtx.acInterface) {
        usbDsInterface_Close(g_uacCtx.acInterface);
        g_uacCtx.acInterface = NULL;
    }

    g_uacCtx.initialized = false;

    if (g_uvcCtx.streamingInterface) {
        usbDsInterface_Close(g_uvcCtx.streamingInterface);
        g_uvcCtx.streamingInterface = NULL;
    }
    if (g_uvcCtx.controlInterface) {
        usbDsInterface_Close(g_uvcCtx.controlInterface);
        g_uvcCtx.controlInterface = NULL;
    }

    usbDsExit();

    g_uvcCtx.initialized = false;

    rwlockWriteUnlock(&g_uvcCtx.lock);

    LOG("UVC/UAC device exited\n");
}

bool UvcDeviceIsConnected(void)
{
    if (!g_uvcCtx.initialized) return false;

    u32 state = 0;
    if (R_SUCCEEDED(usbDsGetState(&state))) {
        return state == UsbState_Configured;
    }
    return false;
}

bool UvcDeviceIsStreaming(void)
{
    return g_uvcCtx.state == UVC_STATE_STREAMING;
}

UvcVideoFormat UvcDeviceGetFormat(void)
{
    if (g_uvcCtx.state != UVC_STATE_STREAMING) {
        return 0;
    }
    return g_uvcCtx.activeFormat;
}

Result UvcDeviceWaitReady(u64 timeout)
{
    return usbDsWaitReady(timeout);
}

bool UvcDeviceSendFrame(const void* data, size_t size, u64 timestamp, bool isKeyframe)
{
    if (!g_uvcCtx.initialized || g_uvcCtx.state != UVC_STATE_STREAMING) {
        return false;
    }

    mutexLock(&g_uvcCtx.streamingMutex);

    Result rc;
    bool success = false;
    u32 urbId;
    UsbDsReportData reportData;

    // 90kHz PTS, no longer transmitted (the minimal payload header omits
    // PTS/SCR on purpose); computed only to keep the header-builder API.
    u32 pts = (u32)((timestamp * 90) / 1000);

    const u8* srcData = (const u8*)data;
    size_t remaining = size;

    // Keep every payload strictly below dwMaxPayloadTransferSize (0x4000):
    // a payload that never fills 16KB always terminates in a short packet,
    // which is what delimits payloads for the host's bulk parser. The -12
    // slack is inherited from the old 12-byte header and intentionally kept.
    const size_t maxPayload = 0x4000 - 12;

    while (remaining > 0) {
        size_t chunkSize = remaining > maxPayload ? maxPayload : remaining;
        bool isLastChunk = (remaining <= maxPayload);

        u8* dest = g_endpointInBuffer;
        u8 headerLen = UvcBuildPayloadHeader(dest, pts, isLastChunk, g_uvcCtx.frameId);

        memcpy(dest + headerLen, srcData, chunkSize);

        size_t totalSize = headerLen + chunkSize;

        eventClear(&g_uvcCtx.videoEndpointIn->CompletionEvent);  // drop stale signal
        rc = usbDsEndpoint_PostBufferAsync(g_uvcCtx.videoEndpointIn, dest, totalSize, &urbId);
        if (R_FAILED(rc)) {
            LOG("PostBufferAsync failed: 0x%x\n", rc);
            break;
        }

        rc = eventWait(&g_uvcCtx.videoEndpointIn->CompletionEvent, 1E+9);
        if (R_FAILED(rc)) {
            // The host is not reading right now. This is NOT a reliable stop
            // signal: OBS routinely stalls its buffer dequeuing for >1s
            // (scene switches, render hiccups) without closing the device -
            // declaring the stream stopped here freezes its feed permanently,
            // because a host that never closed the device never re-issues
            // probe/commit. So: cancel and REAP the stalled URB (cancel
            // without reaping followed by re-posting asserts usb:ds), drop
            // this frame, and STAY in STREAMING. If the host genuinely
            // stopped (CLEAR_FEATURE(HALT) is invisible to us), this just
            // idles at one reaped cancel per second until the next commit
            // or disconnect.
            usbDsEndpoint_Cancel(g_uvcCtx.videoEndpointIn);
            if (R_SUCCEEDED(eventWait(&g_uvcCtx.videoEndpointIn->CompletionEvent, 100E+6))) {
                eventClear(&g_uvcCtx.videoEndpointIn->CompletionEvent);
                usbDsEndpoint_GetReportData(g_uvcCtx.videoEndpointIn, &reportData);
            }
            LOG("Video transfer timeout - dropping frame\n");
            break;
        }
        eventClear(&g_uvcCtx.videoEndpointIn->CompletionEvent);

        rc = usbDsEndpoint_GetReportData(g_uvcCtx.videoEndpointIn, &reportData);
        if (R_FAILED(rc)) {
            LOG("GetReportData failed: 0x%x\n", rc);
            break;
        }

        u32 transferred;
        rc = usbDsParseReportData(&reportData, urbId, NULL, &transferred);
        if (R_FAILED(rc)) {
            LOG("ParseReportData failed: 0x%x\n", rc);
            break;
        }

        // A payload that is an exact multiple of the bulk packet size (512
        // at high speed) produces no short packet, so the host cannot see
        // the payload boundary and fuses it with the next payload - random
        // corrupted frames (~1 in 512 frames). Terminate it with a ZLP.
        if ((totalSize % 512) == 0) {
            u32 zlpUrbId;
            eventClear(&g_uvcCtx.videoEndpointIn->CompletionEvent);
            if (R_SUCCEEDED(usbDsEndpoint_PostBufferAsync(
                    g_uvcCtx.videoEndpointIn, dest, 0, &zlpUrbId))) {
                if (R_SUCCEEDED(eventWait(&g_uvcCtx.videoEndpointIn->CompletionEvent, 1E+9))) {
                    eventClear(&g_uvcCtx.videoEndpointIn->CompletionEvent);
                    usbDsEndpoint_GetReportData(g_uvcCtx.videoEndpointIn, &reportData);
                } else {
                    usbDsEndpoint_Cancel(g_uvcCtx.videoEndpointIn);
                    if (R_SUCCEEDED(eventWait(&g_uvcCtx.videoEndpointIn->CompletionEvent, 100E+6))) {
                        eventClear(&g_uvcCtx.videoEndpointIn->CompletionEvent);
                        usbDsEndpoint_GetReportData(g_uvcCtx.videoEndpointIn, &reportData);
                    }
                    break;
                }
            }
        }

        srcData += chunkSize;
        remaining -= chunkSize;

        if (isLastChunk) {
            success = true;
        }
    }

    // Toggle the frame ID even when the frame was aborted mid-way: an
    // aborted frame never got its EOF, and re-using the same FID makes the
    // host APPEND the next frame to the unterminated one - merged corrupted
    // frames that stall the decoder, fill the host buffers, time out our
    // next transfer and snowball into permanent lag. A FID flip without EOF
    // instead makes uvcvideo close the bad frame immediately (one corrupted
    // frame, then clean).
    g_uvcCtx.frameId ^= 1;
    g_uvcCtx.frameNumber++;

    mutexUnlock(&g_uvcCtx.streamingMutex);
    return success;
}

// ============================================================================
// UVC Control Request Handler (EP0)
//
// usb:ds EP0 rules (mirrors ams::usb::DsInterface, Nintendo's own client
// library reimplemented in Atmosphère libstratosphere/source/usb/usb_device.cpp):
//  - Only touch EP0 inside the SetupEvent -> GetSetupPacket window. Posting
//    a CtrlIn/CtrlOut buffer with no pending setup drives the usb sysmodule
//    into an internal assertion (User Break) and crashes the whole console.
//  - The status stage is NOT automatic: a GET (data IN) must be completed
//    with a zero-length OUT, a SET (data OUT) with a zero-length IN.
//  - On any failure, StallCtrl (protocol-stalls EP0 in both directions).
// ============================================================================

#define EP0_XFER_TIMEOUT 1E+9  // 1s per stage

// VC Request Error Code Control (UVC 1.5 §4.2.1.2). Hosts read this after a
// stalled class request to learn why it failed.
static u8 g_lastErrorCode = UVC_ERROR_NONE;

static u8* _ctrlBufferFor(UsbDsInterface* iface)
{
    if (g_uacCtx.initialized &&
        (iface == g_uacCtx.acInterface || iface == g_uacCtx.asInterface))
        return g_uacControlBuffer;
    return (iface == g_uvcCtx.controlInterface) ? g_vcControlBuffer : g_controlBuffer;
}

// One EP0 IN transfer (device->host). Data must already be in buf.
static Result _ctrlInXfer(UsbDsInterface* iface, u8* buf, size_t len, u32* transferred)
{
    eventClear(&iface->CtrlInCompletionEvent);  // drop any stale signal

    u32 urbId;
    Result rc = usbDsInterface_CtrlInPostBufferAsync(iface, buf, len, &urbId);
    if (R_FAILED(rc)) return rc;

    rc = eventWait(&iface->CtrlInCompletionEvent, EP0_XFER_TIMEOUT);
    if (R_FAILED(rc)) return rc;
    eventClear(&iface->CtrlInCompletionEvent);

    UsbDsReportData rpt;
    rc = usbDsInterface_GetCtrlInReportData(iface, &rpt);
    if (R_FAILED(rc)) return rc;

    u32 t = 0;
    rc = usbDsParseReportData(&rpt, urbId, NULL, &t);
    if (transferred) *transferred = t;
    return rc;
}

// One EP0 OUT transfer (host->device). Data lands in buf.
static Result _ctrlOutXfer(UsbDsInterface* iface, u8* buf, size_t len, u32* transferred)
{
    eventClear(&iface->CtrlOutCompletionEvent);

    u32 urbId;
    Result rc = usbDsInterface_CtrlOutPostBufferAsync(iface, buf, len, &urbId);
    if (R_FAILED(rc)) return rc;

    rc = eventWait(&iface->CtrlOutCompletionEvent, EP0_XFER_TIMEOUT);
    if (R_FAILED(rc)) return rc;
    eventClear(&iface->CtrlOutCompletionEvent);

    UsbDsReportData rpt;
    rc = usbDsInterface_GetCtrlOutReportData(iface, &rpt);
    if (R_FAILED(rc)) return rc;

    u32 t = 0;
    rc = usbDsParseReportData(&rpt, urbId, NULL, &t);
    if (transferred) *transferred = t;
    return rc;
}

// GET-type request: data IN stage + zero-length OUT status stage.
static void _ctrlWrite(UsbDsInterface* iface, const void* data, size_t len)
{
    u8* buf = _ctrlBufferFor(iface);
    memcpy(buf, data, len);

    Result rc = _ctrlInXfer(iface, buf, len, NULL);
    if (R_SUCCEEDED(rc))
        rc = _ctrlOutXfer(iface, buf, 0, NULL);  // status stage

    if (R_FAILED(rc)) {
        LOG("EP0 write failed: 0x%x\n", rc);
        usbDsInterface_StallCtrl(iface);
    }
}

// SET-type request: data OUT stage + zero-length IN status stage.
// Fills data (up to len bytes) and returns true on success.
static bool _ctrlRead(UsbDsInterface* iface, void* data, size_t len)
{
    u8* buf = _ctrlBufferFor(iface);

    u32 transferred = 0;
    Result rc = _ctrlOutXfer(iface, buf, len, &transferred);
    if (R_SUCCEEDED(rc))
        rc = _ctrlInXfer(iface, buf, 0, NULL);  // status stage

    if (R_FAILED(rc)) {
        LOG("EP0 read failed: 0x%x\n", rc);
        usbDsInterface_StallCtrl(iface);
        return false;
    }

    memcpy(data, buf, transferred < len ? transferred : len);
    return true;
}

// Request with no data stage: zero-length IN status stage only.
static void _ctrlAck(UsbDsInterface* iface)
{
    if (R_FAILED(_ctrlInXfer(iface, _ctrlBufferFor(iface), 0, NULL)))
        usbDsInterface_StallCtrl(iface);
}

static void _ctrlStallError(UsbDsInterface* iface, u8 errorCode)
{
    g_lastErrorCode = errorCode;
    usbDsInterface_StallCtrl(iface);
}

// VideoStreaming interface class requests: Probe/Commit negotiation.
// Linux uvcvideo sequence: GET_DEF, SET_CUR(probe), GET_CUR(probe),
// GET_MIN, GET_MAX, SET_CUR(probe), GET_CUR(probe), SET_CUR(commit).
// GET_CUR must return the full 48-byte UVC 1.5 struct or the host bails.
// Windows additionally issues GET_INFO and GET_LEN.
static void _handleVsSetup(UsbDsInterface* iface, const UsbSetupPacket* setup)
{
    u8 cs = (setup->wValue >> 8) & 0xFF;

    if (cs != UVC_VS_PROBE_CONTROL && cs != UVC_VS_COMMIT_CONTROL) {
        LOG("VS: unsupported cs=%u -> stall\n", cs);
        _ctrlStallError(iface, UVC_ERROR_INVALID_CONTROL);
        return;
    }

    UvcProbeCommitControl* ctrl = (cs == UVC_VS_PROBE_CONTROL)
        ? &g_uvcCtx.probeControl
        : &g_uvcCtx.commitControl;

    switch (setup->bRequest) {
    case UVC_GET_CUR:
    case UVC_GET_MIN:
    case UVC_GET_MAX: {
        // Single fixed mode: MIN == MAX == CUR
        size_t len = setup->wLength;
        if (len > sizeof(UvcProbeCommitControl))
            len = sizeof(UvcProbeCommitControl);
        _ctrlWrite(iface, ctrl, len);
        break;
    }
    case UVC_GET_DEF: {
        UvcProbeCommitControl def;
        UvcBuildDefaultProbeControl(&def, UVC_FORMAT_H264);
        size_t len = setup->wLength;
        if (len > sizeof(def))
            len = sizeof(def);
        _ctrlWrite(iface, &def, len);
        break;
    }
    case UVC_GET_INFO: {
        u8 info = 0x03;  // supports GET and SET
        _ctrlWrite(iface, &info, 1);
        break;
    }
    case UVC_GET_LEN: {
        u16 len = sizeof(UvcProbeCommitControl);  // 48 for UVC 1.5
        _ctrlWrite(iface, &len, setup->wLength < 2 ? setup->wLength : 2);
        break;
    }
    case UVC_SET_CUR: {
        UvcProbeCommitControl host;
        memset(&host, 0, sizeof(host));
        size_t len = setup->wLength;
        if (len > sizeof(host))
            len = sizeof(host);
        if (!_ctrlRead(iface, &host, len))
            return;

        // Negotiate: we offer exactly one format/frame/payload size, so
        // override whatever the host asked for with our fixed parameters.
        host.bFormatIndex = 1;
        host.bFrameIndex = 1;
        host.dwMaxVideoFrameSize = UVC_H264_MAX_FRAME_SIZE;
        host.dwMaxPayloadTransferSize = 0x4000;  // matches g_endpointInBuffer
        host.dwClockFrequency = UVC_CLOCK_FREQUENCY;
        if (host.dwFrameInterval == 0)
            host.dwFrameInterval = UVC_FRAME_INTERVAL_30FPS;
        memcpy(ctrl, &host, sizeof(UvcProbeCommitControl));

        if (cs == UVC_VS_COMMIT_CONTROL) {
            g_uvcCtx.activeFormat = UVC_FORMAT_H264;
            g_uvcCtx.state = UVC_STATE_STREAMING;
            g_uacCtx.streaming = g_uacCtx.initialized;
            LOG("Commit received - streaming started\n");
        } else {
            LOG("Probe SET_CUR: interval=%u\n", (unsigned)host.dwFrameInterval);
        }
        break;
    }
    default:
        LOG("VS: unsupported bRequest=0x%02x -> stall\n", setup->bRequest);
        _ctrlStallError(iface, UVC_ERROR_INVALID_REQUEST);
        return;
    }

    g_lastErrorCode = UVC_ERROR_NONE;
}

// VideoControl interface class requests. We advertise no camera/terminal
// controls (bmControls all zero), so only the interface-level controls
// (entity 0 in the high byte of wIndex) need real answers.
static void _handleVcSetup(UsbDsInterface* iface, const UsbSetupPacket* setup)
{
    u8 entity = (setup->wIndex >> 8) & 0xFF;
    u8 cs = (setup->wValue >> 8) & 0xFF;

    if (entity == 0) {
        if (cs == UVC_VC_REQUEST_ERROR_CODE_CONTROL) {
            // Must support GET_CUR + GET_INFO and never stall (hosts read
            // this right after any other request stalls).
            if (setup->bRequest == UVC_GET_CUR) {
                _ctrlWrite(iface, &g_lastErrorCode, 1);
                return;
            }
            if (setup->bRequest == UVC_GET_INFO) {
                u8 info = 0x01;  // GET only
                _ctrlWrite(iface, &info, 1);
                return;
            }
        }
        else if (cs == UVC_VC_VIDEO_POWER_MODE_CONTROL) {
            if (setup->bRequest == UVC_GET_CUR) {
                u8 power = 0x00;  // full power
                _ctrlWrite(iface, &power, 1);
                g_lastErrorCode = UVC_ERROR_NONE;
                return;
            }
            if (setup->bRequest == UVC_SET_CUR) {
                u8 power = 0;
                if (_ctrlRead(iface, &power, 1))
                    g_lastErrorCode = UVC_ERROR_NONE;
                return;
            }
            if (setup->bRequest == UVC_GET_INFO) {
                u8 info = 0x03;
                _ctrlWrite(iface, &info, 1);
                g_lastErrorCode = UVC_ERROR_NONE;
                return;
            }
        }
        LOG("VC: unsupported cs=%u req=0x%02x -> stall\n", cs, setup->bRequest);
        _ctrlStallError(iface, UVC_ERROR_INVALID_CONTROL);
        return;
    }

    LOG("VC: entity=%u cs=%u req=0x%02x -> stall\n", entity, cs, setup->bRequest);
    _ctrlStallError(iface, (entity == UVC_ENTITY_INPUT_TERMINAL ||
                            entity == UVC_ENTITY_OUTPUT_TERMINAL)
        ? UVC_ERROR_INVALID_CONTROL : UVC_ERROR_INVALID_UNIT);
}

// Standard request codes that may be forwarded to us on EP0
#define USB_REQUEST_GET_INTERFACE 0x0A
#define USB_REQUEST_SET_INTERFACE 0x0B

#ifdef ISO_PROBE
static void _handleIsoSetup(UsbDsInterface* iface, const UsbSetupPacket* setup)
{
    if (setup->wIndex != iface->interface_index) {
        /* usb:ds broadcasts SetupEvent. Another interface owns this request;
           stalling shared EP0 here breaks that owner's Probe/Commit transfer. */
        LOG("ISO EP0: request for interface %u, ignoring\n", setup->wIndex);
        return;
    }
    if (setup->bmRequestType == 0xc1 && setup->bRequest == ISO_PROBE_FRAMES &&
        setup->wLength == sizeof(IsoProbeFrameReport) && setup->wValue == 0) {
        if (g_isoStatus.state == ISO_PROBE_PENDING || g_isoStatus.state == ISO_PROBE_RETAINED) {
            usbDsInterface_StallCtrl(iface);
            return;
        }
        static IsoProbeFrameReport frames;
        memset(&frames, 0, sizeof(frames));
        frames.magic = ISO_PROBE_FRAMES_MAGIC;
        frames.version = 1;
        frames.count = ISO_PROBE_FRAME_SAMPLES;
        frames.tick_frequency = armGetSystemTickFreq();
        frames.verified = 1;
        for (unsigned i = 0; i < ISO_PROBE_FRAME_SAMPLES; ++i) {
            IsoProbeFrameSample *s = &frames.samples[i];
            s->ticks_before = svcGetSystemTick();
            _pollIsoProbe();
            s->ticks_after = svcGetSystemTick();
            s->result = g_isoStatus.report_result;
            if (!s->result && (g_isoStatus.diagnostics.magic != ISO_PROBE_REPORT_MARKER ||
                              !g_isoStatus.diagnostics.iso_physical))
                s->result = MAKERESULT(Module_Libnx, LibnxError_BadInput);
            s->raw_mfi = g_isoStatus.diagnostics.context[0];
            s->control = g_isoStatus.diagnostics.context[1];
            s->portsc = g_isoStatus.diagnostics.context[2];
            s->mmio = g_isoStatus.diagnostics.iso_physical;
            if (s->result || (s->raw_mfi & ~0x3fffu)) frames.verified = 0;
            if (i) {
                const IsoProbeFrameSample *p = &frames.samples[i-1];
                u64 dt = (s->ticks_before/2 + s->ticks_after/2) -
                         (p->ticks_before/2 + p->ticks_after/2);
                u64 du = (s->raw_mfi - p->raw_mfi) & 0x3fff;
                u64 measured = du * frames.tick_frequency;
                if (!dt || measured < dt*7200 || measured > dt*8800) frames.verified = 0;
            }
            LOG("ISO frame[%u] ticks=%llu..%llu mfi=%x ctrl=%x port=%x rc=0x%x mmio=%llx\n",
                i, (unsigned long long)s->ticks_before, (unsigned long long)s->ticks_after,
                s->raw_mfi, s->control, s->portsc, s->result, (unsigned long long)s->mmio);
            if (i + 1 < ISO_PROBE_FRAME_SAMPLES) svcSleepThread(20000000ULL);
        }
        LOG("ISO frame unit verified=%u tick-frequency=%u (no TD submitted)\n",
            frames.verified, frames.tick_frequency);
        _ctrlWrite(iface, &frames, sizeof(frames));
        return;
    }
    if (setup->bmRequestType == 0xc1 && setup->bRequest == ISO_PROBE_STATUS &&
        setup->wLength == sizeof(g_isoStatus) && setup->wValue == 0) {
        _pollIsoProbe();
        _ctrlWrite(iface, &g_isoStatus, sizeof(g_isoStatus));
        return;
    }
    if (setup->bmRequestType == 0x41 && setup->bRequest ==
#ifdef ISO_PROBE_BURST_MODE
        ISO_PROBE_BURST
#else
        ISO_PROBE_TRIGGER
#endif
        && setup->wLength == 0) {
        u64 triggerTicks = svcGetSystemTick();
        _pollIsoProbe();
        if (g_isoStatus.state == ISO_PROBE_PENDING || g_isoStatus.state == ISO_PROBE_RETAINED) {
            usbDsInterface_StallCtrl(iface);
            return;
        }
        UsbDeviceSpeed speed;
        Result rc = usbDsGetSpeed(&speed);
        if (R_FAILED(rc) || (speed != UsbDeviceSpeed_High && speed != UsbDeviceSpeed_Super)) {
            usbDsInterface_StallCtrl(iface);
            return;
        }
#ifdef ISO_PROBE_BURST_MODE
        if (speed != UsbDeviceSpeed_High) {
            usbDsInterface_StallCtrl(iface);
            return;
        }
        const unsigned packetCount = ISO_PROBE_BURST_PACKETS;
#else
        const unsigned packetCount = 1;
#endif
        const unsigned length = packetCount * ISO_PROBE_PACKET_SIZE;
        memset(&g_isoStatus, 0, sizeof(g_isoStatus));
        g_isoStatus.magic = ISO_PROBE_STATUS_MAGIC;
        g_isoStatus.version = 1;
        g_isoStatus.sequence = setup->wValue;
        g_isoStatus.speed = speed;
        g_isoStatus.endpoint = 0x83;
        for (unsigned packet = 0; packet < packetCount; ++packet)
            for (unsigned i = 0; i < ISO_PROBE_PACKET_SIZE; ++i)
                g_isoBuffer[packet * ISO_PROBE_PACKET_SIZE + i] =
                    isoProbeByte((uint16_t)(setup->wValue + packet), i);
        armDCacheFlush(g_isoBuffer, sizeof(g_isoBuffer));
        eventClear(&g_isoEndpoint->CompletionEvent);
        u32 urbId = 0;
        u64 postBeforeTicks = svcGetSystemTick();
        rc = usbDsEndpoint_PostBufferAsync(g_isoEndpoint, g_isoBuffer,
            length, &urbId);
        u64 postAfterTicks = svcGetSystemTick();
        g_isoStatus.urb_id = urbId;
        g_isoStatus.post_result = rc;
        g_isoStatus.state = R_SUCCEEDED(rc) ? ISO_PROBE_PENDING : ISO_PROBE_FAILED;
        u64 ackBeforeTicks = svcGetSystemTick();
        _ctrlAck(iface);
        u64 ackAfterTicks = svcGetSystemTick();
        LOG("ISO submit seq=%u speed=%u length=%u rc=0x%x urb=%u\n",
            setup->wValue, speed, length, rc, urbId);
        LOG("ISO timing seq=%u urb=%u frequency=%u trigger=%llu post-before=%llu post-after=%llu ack-before=%llu ack-after=%llu\n",
            setup->wValue, urbId, armGetSystemTickFreq(),
            (unsigned long long)triggerTicks, (unsigned long long)postBeforeTicks,
            (unsigned long long)postAfterTicks, (unsigned long long)ackBeforeTicks,
            (unsigned long long)ackAfterTicks);
        return;
    }
    if (setup->bmRequestType == 0x41 && setup->bRequest == ISO_PROBE_CANCEL &&
        setup->wLength == 0 && setup->wValue == 0) {
        if (g_isoStatus.state == ISO_PROBE_PENDING || g_isoStatus.state == ISO_PROBE_RETAINED) {
            g_isoStatus.state = ISO_PROBE_RETAINED;
            usbDsEndpoint_Cancel(g_isoEndpoint);
            /* Reap synchronously before ACK; unknown ownership blocks retrigger. */
            eventWait(&g_isoEndpoint->CompletionEvent, 500E+6);
            _pollIsoProbe();
        }
        _ctrlAck(iface);
        return;
    }
    if (setup->bmRequestType == 0x01 && setup->bRequest == USB_REQUEST_SET_INTERFACE &&
        setup->wLength == 0) {
#ifdef ISO_PROBE_ALT1
        if (setup->wValue > 1) { usbDsInterface_StallCtrl(iface); return; }
#else
        if (setup->wValue != 0) { usbDsInterface_StallCtrl(iface); return; }
#endif
        g_isoAlt = (u8)setup->wValue;
#ifdef ISO_PROBE_STREAM
        if (g_isoAlt == 0) _isoStopStream();
#endif
        _ctrlAck(iface);
        return;
    }
#ifdef ISO_PROBE_STREAM
    if (setup->bmRequestType == 0x41 && setup->bRequest == ISO_PROBE_STREAM_START &&
        setup->wValue == 0 && setup->wLength == 0) {
#ifdef ISO_RUNTIME_PATCH
        if (!_applyIsoStreamPatch()) {
            LOG("ISO stream delta patch failed\n");
            usbDsInterface_StallCtrl(iface);
            return;
        }
#endif
        Result src = _isoStartStream();
        if (R_FAILED(src)) {
            LOG("ISO stream start rc=0x%x\n", src);
            usbDsInterface_StallCtrl(iface);
            return;
        }
        _ctrlAck(iface);
        return;
    }
#endif
    if (setup->bmRequestType == 0x81 && setup->bRequest == USB_REQUEST_GET_INTERFACE &&
        setup->wValue == 0 && setup->wLength == 1) {
        u8 alt = g_isoAlt;
        _ctrlWrite(iface, &alt, 1);
        return;
    }
    usbDsInterface_StallCtrl(iface);
}
#endif

#ifdef ALT1_PROBE
static void _handleAlt1Setup(UsbDsInterface* iface, const UsbSetupPacket* setup)
{
    const u8 ifaceNum = iface->interface_index;

    if (setup->bmRequestType == 0x01 && setup->bRequest == 0x0B &&
        setup->wIndex == ifaceNum && setup->wLength == 0) {
        if (setup->wValue > 1) { usbDsInterface_StallCtrl(iface); return; }
        g_alt1Status.alt = setup->wValue;
        LOG("ALT1 SET_INTERFACE %u\n", setup->wValue);
        _ctrlAck(iface);
        return;
    }
    if (setup->bmRequestType == 0x81 && setup->bRequest == 0x0A &&
        setup->wIndex == ifaceNum && setup->wLength == 1) {
        u8 alt = (u8)g_alt1Status.alt;
        _ctrlWrite(iface, &alt, 1);
        return;
    }
    if (setup->bmRequestType == 0x41 && setup->bRequest == ALT1_PROBE_TRIGGER &&
        setup->wLength == 0) {
        if (!g_alt1Endpoint) {
            usbDsInterface_StallCtrl(iface);
            return;
        }
        _pollAlt1Probe();
        if (g_alt1Status.state == ALT1_PROBE_PENDING) {
            usbDsInterface_StallCtrl(iface);
            return;
        }
        for (u32 i = 0; i < ALT1_PROBE_BUFFER_SIZE; ++i)
            g_alt1Buffer[i] = (u8)(0xA0 + i);
        g_alt1Buffer[0] = 'A'; g_alt1Buffer[1] = 'L';
        g_alt1Buffer[2] = 'T'; g_alt1Buffer[3] = '1';
        eventClear(&g_alt1Endpoint->CompletionEvent);
        armDCacheFlush(g_alt1Buffer, sizeof(g_alt1Buffer));
        u32 urbId = 0;
        Result rc = usbDsEndpoint_PostBufferAsync(g_alt1Endpoint,
            g_alt1Buffer, sizeof(g_alt1Buffer), &urbId);
        g_alt1Status.triggers++;
        g_alt1Status.post_result = rc;
        g_alt1Status.urb_id = urbId;
        g_alt1Status.completed = 0;
        g_alt1Status.transferred = 0;
        g_alt1Status.urb_status = 0;
        g_alt1Status.state = R_SUCCEEDED(rc) ? ALT1_PROBE_PENDING : ALT1_PROBE_FAILED;
        LOG("ALT1 trigger rc=0x%x urb=%u\n", rc, urbId);
        _ctrlAck(iface);
        return;
    }
    if (setup->bmRequestType == 0xC1 && setup->bRequest == ALT1_PROBE_STATUS &&
        setup->wLength == sizeof(g_alt1Status)) {
        _pollAlt1Probe();
        _ctrlWrite(iface, &g_alt1Status, sizeof(g_alt1Status));
        return;
    }
    if (setup->bmRequestType == 0x41 && setup->bRequest == ALT1_PROBE_CANCEL &&
        setup->wLength == 0) {
        if (g_alt1Status.state == ALT1_PROBE_PENDING) {
            usbDsEndpoint_Cancel(g_alt1Endpoint);
            eventWait(&g_alt1Endpoint->CompletionEvent, 500E+6);
            _pollAlt1Probe();
            if (g_alt1Status.state == ALT1_PROBE_PENDING)
                g_alt1Status.state = ALT1_PROBE_FAILED;
        }
        _ctrlAck(iface);
        return;
    }
    usbDsInterface_StallCtrl(iface);
}
#endif

#ifdef UAC_U2_PATCH
/* U2: one bounded URB on AS alt1 EP 0x84, UAC_U2_BURST_BYTES long (16 x 192 B
   per segment).  usb:ds has no working ISO submit path of its own (the
   original branch returns 0x1908c), so the runtime cave builds the Isoch+ED
   TRBs and rings the doorbell.  The host must already be polling: uac-burst
   submits its ISO transfer before sending this SET_CUR trigger.  Post exactly
   once per boot; a timeout is reported, never retried or cancelled here. */
#ifdef UAC_U2_ATTR01
#define UAC_U2_EP_WORD 0x00C00184u  /* addr 0x84, attrs 0x01, MPS192 */
#else
#define UAC_U2_EP_WORD 0x00C00584u  /* addr 0x84, attrs 0x05, MPS192 */
#endif
/* Endpoint 0x84 object inside usb:ds, from the 0x302e0 submit path:
   manager = module base + 0xD3000 (device) + 0x7000; the object is at
   manager + 0x22000 + ((0x84 & 0xf) << 1 | 1) * 0x48 + 0x78.  The
   2026-10-30 crash report pinned the manager at base + 0xDA000 (x21).
   Reading this state before posting keeps a rejected submit (0x1908c,
   which the driver's error completion turns into a stack overflow) from
   ever reaching the driver. */
/* All offsets are relative to the usb module base.  The manager object sits at
   0xDA000 (device 0xD3000 + 0x7000); reading the 2026-10-30 precheck log with
   manager-relative values without the 0xDA000 bias returned instruction words
   for speed/installed/table, which is why the first precheck run skipped every
   post even though word/interval/ring were correct. */
#define UAC_U2_EP_OBJ 0xFC300ULL             /* manager + 0x22300 */
#define UAC_U2_SPEED_OFFSET 0xFCA58ULL       /* manager + 0x22 * 0x1000 + 0xa58 */
/* The installer (0x295d0) and complete_original (0x2a980) do not run on the
   manager itself.  The completion caller loads a separate install object from
   manager + 0x229b8 (0x30294/0x302a8: ldr x0, [x21, #0x229b8]; bl 0x2a980),
   and the installer is invoked with that same pointer (0x2f17c/0x2f188).
   Both 2026-10-30 crash reports pin it in x0 while x21 is the manager:
   0x714857b038 - 0x71484da000 = 0xa1038.  For EP 0x84, 0x3a30(0x84) = 0x14,
   so the flag is at object + 0x14d0 + 0x140 = 0x1610 and the entry pointer at
   object + 0x14c8 + 0x140 = 0x1608.  Reading manager + 0x1610 instead returns
   unrelated bytes (the observed 0/1/0x90/0xa2/0xf0 values). */
#define UAC_U2_INSTALL_OBJ_PTR_OFFSET 0xFC9B8ULL /* manager + 0x229b8 */
#define UAC_U2_INSTALL_OBJ_OFFSET 0x17B038ULL    /* manager + 0xa1038 */
#define UAC_U2_INSTALL_FLAG_OFF 0x1610ULL
#define UAC_U2_INSTALL_FLAG1_OFF 0x1611ULL
#define UAC_U2_INSTALL_TABLE_OFF 0x1608ULL
/* v18: per-DCI "transfer event pending" mask (manager+0x22A5C).  event_original
   sets a bit on 0x31324 and clears it (plus the regs+0x78 poll) on 0x311a8;
   the cave handles DCI-9 events itself and never runs that path. */
#define UAC_U2_PENDING_MASK_OFFSET 0xFCA5CULL
typedef struct {
    u8 state[0x48];
    u32 speed;
    u32 pending_mask;
    bool mask_ok;
    u64 install_obj;
    bool install_ok;
    u8 installed;
    u8 installed1;
    u64 table_ptr;
    bool mgr_ok;
    u8 mgr_installed;
    u8 mgr_installed1;
    u64 mgr_table_ptr;
} UacUsbEpState;

static bool _uacReadUsbState(UacUsbEpState *out)
{
    if (!g_uacUsbPid) return false;
    Handle h = INVALID_HANDLE;
    if (R_FAILED(svcDebugActiveProcess(&h, g_uacUsbPid))) return false;
    Result rc = svcReadDebugProcessMemory(out->state, h,
        g_uacUsbBase + UAC_U2_EP_OBJ, sizeof(out->state));
    if (R_SUCCEEDED(rc)) {
        rc = svcReadDebugProcessMemory(&out->speed, h,
            g_uacUsbBase + UAC_U2_SPEED_OFFSET, sizeof(out->speed));
    }
    /* A failed mask read is diagnostic only; it must not fail the precheck. */
    out->mask_ok = false;
    {
        Result mrc = svcReadDebugProcessMemory(&out->pending_mask, h,
            g_uacUsbBase + UAC_U2_PENDING_MASK_OFFSET,
            sizeof(out->pending_mask));
        out->mask_ok = R_SUCCEEDED(mrc);
    }
    if (R_SUCCEEDED(rc)) {
        rc = svcReadDebugProcessMemory(&out->install_obj, h,
            g_uacUsbBase + UAC_U2_INSTALL_OBJ_PTR_OFFSET,
            sizeof(out->install_obj));
    }

    out->install_ok = false;
    if (R_SUCCEEDED(rc) && out->install_obj) {
        Result orc = svcReadDebugProcessMemory(&out->installed, h,
            out->install_obj + UAC_U2_INSTALL_FLAG_OFF,
            sizeof(out->installed));
        if (R_SUCCEEDED(orc)) {
            orc = svcReadDebugProcessMemory(&out->installed1, h,
                out->install_obj + UAC_U2_INSTALL_FLAG1_OFF,
                sizeof(out->installed1));
        }
        if (R_SUCCEEDED(orc)) {
            orc = svcReadDebugProcessMemory(&out->table_ptr, h,
                out->install_obj + UAC_U2_INSTALL_TABLE_OFF,
                sizeof(out->table_ptr));
        }
        out->install_ok = R_SUCCEEDED(orc);
        if (R_FAILED(orc)) rc = orc;
    }

    /* Keep the old manager-relative reads as a one-run diagnostic: they are
       the values every earlier gate actually used.  They are not the install
       state and must never decide whether to post. */
    out->mgr_ok = false;
    {
        Result mrc = svcReadDebugProcessMemory(&out->mgr_installed, h,
            g_uacUsbBase + 0xDB610ULL, sizeof(out->mgr_installed));
        if (R_SUCCEEDED(mrc)) {
            mrc = svcReadDebugProcessMemory(&out->mgr_installed1, h,
                g_uacUsbBase + 0xDB611ULL, sizeof(out->mgr_installed1));
        }
        if (R_SUCCEEDED(mrc)) {
            mrc = svcReadDebugProcessMemory(&out->mgr_table_ptr, h,
                g_uacUsbBase + 0xDB608ULL, sizeof(out->mgr_table_ptr));
        }
        out->mgr_ok = R_SUCCEEDED(mrc);
    }
    svcCloseHandle(h);
    return R_SUCCEEDED(rc);
}

/* The value at install_obj + 0x1608 is the request entry used by 0x2c690:
   +0x10 IOVA, +0x20 requested, +0x28 status, +0x2c transferred. */
static void _uacLogEntry(const char *tag, Handle h, u64 address)
{
    u8 entry[0x30] = {0};
    Result rc = svcReadDebugProcessMemory(entry, h, address, sizeof(entry));
    if (R_FAILED(rc)) {
        LOG("UAC U2 entry %s addr=0x%llx rd=0x%x\n", tag,
            (unsigned long long)address, rc);
        return;
    }
    u32 status = 0, requested = 0, transferred = 0;
    u64 iova = 0;
    memcpy(&iova, entry + 0x10, sizeof(iova));
    memcpy(&requested, entry + 0x20, sizeof(requested));
    memcpy(&status, entry + 0x28, sizeof(status));
    memcpy(&transferred, entry + 0x2c, sizeof(transferred));
    LOG("UAC U2 entry %s addr=0x%llx iova=0x%llx req=%u xfer=%u status=%u\n",
        tag, (unsigned long long)address, (unsigned long long)iova,
        requested, transferred, status);
}

static void _uacLogInstallState(void)
{
    if (!g_uacUsbPid) return;
    Handle h = INVALID_HANDLE;
    if (R_FAILED(svcDebugActiveProcess(&h, g_uacUsbPid))) return;

    u64 obj = 0, table = 0;
    Result rc = svcReadDebugProcessMemory(&obj, h,
        g_uacUsbBase + UAC_U2_INSTALL_OBJ_PTR_OFFSET, sizeof(obj));
    if (R_SUCCEEDED(rc) && obj) {
        rc = svcReadDebugProcessMemory(&table, h,
            obj + UAC_U2_INSTALL_TABLE_OFF, sizeof(table));
    }
    LOG("UAC U2 install obj=0x%llx table=0x%llx rd=0x%x\n",
        (unsigned long long)obj, (unsigned long long)table, rc);
    if (R_SUCCEEDED(rc) && table) _uacLogEntry("table", h, table);
    svcCloseHandle(h);
}

/* v16 instrumentation: the cave's iso_enter only builds TDs while the ring is
   empty (it requires prod == cons).  A rejected submit returns 0, so the driver
   reports success and the app then waits for a completion that can never come.
   Log the full accept state before/after every post: word/interval/speed/dci
   must stay at their burst-1 values, and prod/cons/copy show whether the gate
   would accept.  No behaviour change. */
#if defined(UAC_U2_CURSOR_DIAG)
/* v27 read-only diagnostic: the cave keeps its next free frame in the
   mailbox scratch (ring+0xFB8).  Log the cursor and the ring pointers around
   every pipeline post to tell "cursor not written/read" from "ring reset
   between posts".  Reads only. */
static void _uacLogCursor(const char *tag, u32 seq)
{
    if (!g_uacUsbPid) return;
    Handle h = INVALID_HANDLE;
    if (R_FAILED(svcDebugActiveProcess(&h, g_uacUsbPid))) return;
    u8 st[0x48];
    Result rc = svcReadDebugProcessMemory(st, h,
        g_uacUsbBase + UAC_U2_EP_OBJ, sizeof(st));
    if (R_SUCCEEDED(rc)) {
        u64 ring = 0, prod = 0, cons = 0;
        memcpy(&ring, st + 0x10, sizeof(ring));
        memcpy(&prod, st + 0x18, sizeof(prod));
        memcpy(&cons, st + 0x20, sizeof(cons));
        u16 cursor = 0;
        Result crc = 0xdead;
        if (ring) {
            crc = svcReadDebugProcessMemory(&cursor, h, ring + 0xFB8,
                                            sizeof(cursor));
        }
        LOG("UAC U2 cursor %s seq=%u ring=0x%llx prod=0x%llx cons=0x%llx cycle=%u cur=%u rc=0x%x\n",
            tag, seq, (unsigned long long)ring, (unsigned long long)prod,
            (unsigned long long)cons, st[0x40], cursor, crc);
    }
    svcCloseHandle(h);
}
#endif

#if !defined(UAC_U2_PIPELINE)
/* v26A pipeline builds do not use the per-burst submit-state dump; the ring
   and install dumps after the train still serve as evidence. */
static void _uacLogSubmitState(const char *tag, u32 seq)
{
    UacUsbEpState ep = {0};
    if (!_uacReadUsbState(&ep)) {
        LOG("UAC U2 state %s seq=%u read=0\n", tag, seq);
        return;
    }
    u32 word = (u32)ep.state[2] | ((u32)ep.state[3] << 8) |
               ((u32)ep.state[4] << 16) | ((u32)ep.state[5] << 24);
    u64 ring = 0, prod = 0, cons = 0, copy = 0;
    memcpy(&ring, ep.state + 0x10, sizeof(ring));
    memcpy(&prod, ep.state + 0x18, sizeof(prod));
    memcpy(&cons, ep.state + 0x20, sizeof(cons));
    memcpy(&copy, ep.state + 0x28, sizeof(copy));
    LOG("UAC U2 state %s seq=%u word=0x%08x int=%u dci=%u cycle=%u speed=%u ring=0x%llx prod=0x%llx cons=0x%llx copy=0x%llx empty=%u mask=0x%08x bit9=%u ep10=0x%02x\n",
        tag, seq, word, ep.state[6], ep.state[0x42], ep.state[0x40],
        ep.speed, (unsigned long long)ring, (unsigned long long)prod,
        (unsigned long long)cons, (unsigned long long)copy,
        (ring && prod == cons) ? 1u : 0u,
        ep.mask_ok ? ep.pending_mask : 0u,
        (ep.mask_ok ? (ep.pending_mask >> 9) & 1u : 0u), ep.state[0x0A]);
}
#endif /* !UAC_U2_PIPELINE */

#ifdef UAC_U2_RING_ADVANCE
/* v17 diagnostic: the driver resets prod/cons to the ring base when a request
   completes (v16 "done" line), but the controller has already consumed one
   0x200-byte TD set, so its dequeue is past the base.  The next cave enter then
   writes 16+16 TRBs at the base, behind the dequeue, and they are never
   fetched.  Move the cave's write window to the next 0x200 slot before posting
   burst 2..N.  This is a one-shot dmnt write to the same ring fields the cave
   updates at submit time; it is a diagnostic, not the final design.  The four
   bursts stay below 0xf70, so no Link/slot wrap is involved. */
#define UAC_U2_TD_BYTES 0x200ULL
static bool _uacAdvanceRing(u32 seq, u32 slots)
{
    if (!g_uacUsbPid || slots == 0) return false;
    UacUsbEpState ep = {0};
    if (!_uacReadUsbState(&ep)) return false;
    u64 ring = 0;
    memcpy(&ring, ep.state + 0x10, sizeof(ring));
    if (!ring) return false;
    const u64 next = ring + (u64)slots * UAC_U2_TD_BYTES;
    Handle h = INVALID_HANDLE;
    if (R_FAILED(svcDebugActiveProcess(&h, g_uacUsbPid))) return false;
    Result rc = svcWriteDebugProcessMemory(h, &next,
        g_uacUsbBase + UAC_U2_EP_OBJ + 0x18, sizeof(next));
    if (R_SUCCEEDED(rc)) {
        rc = svcWriteDebugProcessMemory(h, &next,
            g_uacUsbBase + UAC_U2_EP_OBJ + 0x20, sizeof(next));
    }
    svcCloseHandle(h);
    LOG("UAC U2 ring advance seq=%u slots=%u from=0x%llx to=0x%llx rc=0x%x\n",
        seq, slots, (unsigned long long)ring, (unsigned long long)next, rc);
    return R_SUCCEEDED(rc);
}
#endif

/* The cave still writes its ISO2 mailbox even with the report hook removed:
   ring+0xf80 magic, +0xf90 completed bitmap, +0xf94 actual sum, +0xf98 first
   TRB, +0xfbc retained control.  Log the first Isoch/ED words too, so a
   wrong frame/type/endpoint is visible on the next run. */
static void _uacLogRingState(void)
{
    if (!g_uacUsbPid) return;
    Handle h = INVALID_HANDLE;
    if (R_FAILED(svcDebugActiveProcess(&h, g_uacUsbPid))) return;

    u8 state[0x48] = {0};
    Result rc = svcReadDebugProcessMemory(state, h,
        g_uacUsbBase + UAC_U2_EP_OBJ, sizeof(state));
    u64 ring = 0, prod = 0, cons = 0;
    if (R_SUCCEEDED(rc)) {
        memcpy(&ring, state + 0x10, sizeof(ring));
        memcpy(&prod, state + 0x18, sizeof(prod));
        memcpy(&cons, state + 0x20, sizeof(cons));
    }
    u64 regs = 0;
    u32 mfi = 0;
    Result mrc = svcReadDebugProcessMemory(&regs, h,
        g_uacUsbBase + 0xDA008ULL, sizeof(regs));
    if (R_SUCCEEDED(mrc) && regs) {
        mrc = svcReadDebugProcessMemory(&mfi, h, regs + 0x48, sizeof(mfi));
    }
    const u32 frame = ((mfi >> 3) + 32) & 0x7FF;
    LOG("UAC U2 ring dci=%u cycle=%u prod=0x%llx cons=0x%llx ring=0x%llx mfi=0x%x frame=%u regs=0x%llx rd=0x%x\n",
        state[0x42], state[0x40], (unsigned long long)prod,
        (unsigned long long)cons, (unsigned long long)ring, mfi, frame,
        (unsigned long long)regs, R_SUCCEEDED(rc) ? mrc : rc);
    if (R_SUCCEEDED(rc) && ring) {
        /* v19: the mailbox layout is magic +0, last event completion code +4,
           done flag +0xc, completed bitmap +0x10, actual +0x14, first TRB
           +0x18.  The old dump read +4/+8/+0xc as completed/actual/first. */
        u32 box[8] = {0};
        rc = svcReadDebugProcessMemory(box, h, ring + 0xF80, sizeof(box));
        if (R_SUCCEEDED(rc)) {
            u64 first = 0;
            memcpy(&first, (const u8 *)box + 0x18, sizeof(first));
            LOG("UAC U2 ring box magic=0x%08x event=0x%08x done=%u completed=0x%08x actual=%u first=0x%llx\n",
                box[0], box[1], box[3] ? 1u : 0u, box[4], box[5],
                (unsigned long long)first);
        }
        u8 trb[0x20] = {0};
        if (R_SUCCEEDED(rc)) {
            rc = svcReadDebugProcessMemory(trb, h, ring, sizeof(trb));
        }
        if (R_SUCCEEDED(rc)) {
            u64 addr0 = 0, addr1 = 0;
            u32 len0 = 0, ctl0 = 0, len1 = 0, ctl1 = 0;
            memcpy(&addr0, trb, 8);
            memcpy(&len0, trb + 8, 4);
            memcpy(&ctl0, trb + 12, 4);
            memcpy(&addr1, trb + 16, 8);
            memcpy(&len1, trb + 24, 4);
            memcpy(&ctl1, trb + 28, 4);
            LOG("UAC U2 trb0 addr=0x%llx len=%u ctl=0x%08x trb1 addr=0x%llx len=%u ctl=0x%08x\n",
                (unsigned long long)addr0, len0, ctl0,
                (unsigned long long)addr1, len1, ctl1);
        }
        /* v18: after a post the cave's TD set starts at cons (prod advanced by
           0x200), so dump there as well as at the ring base. */
        if (cons) {
            u8 td[0x20] = {0};
            Result trc = svcReadDebugProcessMemory(td, h, cons, sizeof(td));
            if (R_SUCCEEDED(trc)) {
                u64 addr0 = 0, addr1 = 0;
                u32 len0 = 0, ctl0 = 0, len1 = 0, ctl1 = 0;
                memcpy(&addr0, td, 8);
                memcpy(&len0, td + 8, 4);
                memcpy(&ctl0, td + 12, 4);
                memcpy(&addr1, td + 16, 8);
                memcpy(&len1, td + 24, 4);
                memcpy(&ctl1, td + 28, 4);
                LOG("UAC U2 td@cons addr=0x%llx trb0 addr=0x%llx len=%u ctl=0x%08x trb1 addr=0x%llx len=%u ctl=0x%08x\n",
                    (unsigned long long)cons, (unsigned long long)addr0, len0,
                    ctl0, (unsigned long long)addr1, len1, ctl1);
            }
        }
    }
    svcCloseHandle(h);
}

static void _postUacBurst(void)
{
    /* The host may trigger many times while chasing an alt1 window; log every
       miss so the device log shows how many SET_CURs arrived at alt0. */
    if (!g_uacCtx.audioEndpointIn || g_uacStd.alt_setting != 1) {
        LOG("UAC U2 skip alt=%u ep=%u\n", g_uacStd.alt_setting,
            g_uacCtx.audioEndpointIn ? 1u : 0u);
        return;
    }
    if (g_uacCtx.burstPosted) return;

    UacUsbEpState ep = {0};
    bool read_ok = _uacReadUsbState(&ep);
    u32 word = (u32)ep.state[2] | ((u32)ep.state[3] << 8) |
               ((u32)ep.state[4] << 16) | ((u32)ep.state[5] << 24);
    u64 ring = 0, prod = 0, cons = 0;
    if (read_ok) {
        memcpy(&ring, ep.state + 0x10, sizeof(ring));
        memcpy(&prod, ep.state + 0x18, sizeof(prod));
        memcpy(&cons, ep.state + 0x20, sizeof(cons));
    }
    LOG("UAC U2 precheck ok=%u word=0x%08x int=%u dci=%u cycle=%u speed=%u ring=0x%llx prod=0x%llx cons=0x%llx obj=0x%llx installed=%u flag1=%u table=0x%llx install_ok=%u mgr_ok=%u mgr_installed=%u mgr_flag1=%u mgr_table=0x%llx\n",
        read_ok, word, ep.state[6], ep.state[0x42], ep.state[0x40],
        ep.speed, (unsigned long long)ring,
        (unsigned long long)prod, (unsigned long long)cons,
        (unsigned long long)ep.install_obj, ep.installed, ep.installed1,
        (unsigned long long)ep.table_ptr, ep.install_ok, ep.mgr_ok,
        ep.mgr_installed, ep.mgr_installed1,
        (unsigned long long)ep.mgr_table_ptr);
    if (!read_ok || word != UAC_U2_EP_WORD || ep.state[6] != 4 || ep.speed != 3 ||
        ring == 0 || prod != cons) {
        LOG("UAC U2 post skipped: endpoint not ready for the cave\n");
        return;
    }
    /* 0x2fdfc stores a DCI-like index in endpoint+0x42: 0x84 -> 9,
       0x83 -> 7.  The cave's doorbell tail writes that value into the
       device doorbell.  A wrong value would point the burst at another
       endpoint, so never post with a mismatched DCI. */
    if (ep.state[0x42] != 9) {
        LOG("UAC U2 post skipped: endpoint dci=%u (want 9)\n", ep.state[0x42]);
        return;
    }
    /* The installer writes exactly 1 at install_obj + 0x1610 and the
       completion path reads the request entry from install_obj + 0x1608.
       Posting before both are visible produces the empty 0x748c completion.
       The manager-relative values are only logged, never gated on. */
    if (!ep.install_ok || ep.installed != 1 || ep.table_ptr == 0) {
        LOG("UAC U2 post skipped: install object not ready obj=0x%llx installed=%u flag1=%u table=0x%llx mgr_ok=%u mgr_installed=%u mgr_flag1=%u mgr_table=0x%llx\n",
            (unsigned long long)ep.install_obj, ep.installed, ep.installed1,
            (unsigned long long)ep.table_ptr, ep.mgr_ok, ep.mgr_installed,
            ep.mgr_installed1, (unsigned long long)ep.mgr_table_ptr);
        return;
    }

    g_uacCtx.burstPosted = true;
    LOG("UAC U2 train begin count=%u pattern=%u\n", UAC_U2_TRAIN_POSTS,
        g_uacCtx.patternFrame);
    LOG("UAC U2 pattern 1kHz 16ms train=%u\n", UAC_U2_TRAIN_POSTS);
#if UAC_U2_FRAMES > 16
    /* v28: one request carries the whole burst; the cave sizes its TD set
       from this length, so log it once with the frame count. */
    LOG("UAC U2 multi frames=%u size=%u\n", UAC_U2_FRAMES,
        UAC_U2_BURST_BYTES);
#endif

    /* Sequential train: every buffer is posted only after the previous
       completion, so the driver never holds two ISO requests at once (the
       v11 crash).  The 1 kHz phase continues across buffers, which lets the
       host check continuity instead of four separate 16 ms bursts. */
#if defined(UAC_U2_PIPELINE)
    /* v26A: 16 ms timer pipeline.  v29e keeps three requests in flight so
       the cave always has TD sets queued while the app posts about every
       30 ms.  v29f treats a status=5 as a single lost set (free the slot and
       keep posting) and only cancels + reposts after a 100 ms stall, so one
       miss does not reset the ring and trigger another.  The 1 kHz pattern
       phase continues across buffers. */
    u32 next = 0, posted = 0, completed = 0, xfer_total = 0;
    u32 misses = 0, recoveries = 0;
    bool pipe_failed = false;
    u8 free_slot[8];
    u32 urb_ids[8] = {0};
    const u32 stream_posts = UAC_U2_STREAM_POSTS;
    u64 last_progress = svcGetSystemTick();
    for (u32 i = 0; i < 8; ++i) free_slot[i] = 1;

    for (;;) {
        /* v29c: rolling train.  A slot is posted again only after the
           previous request that used it completed (free_slot), at most three
           requests in flight, and never more than STREAM_POSTS total. */
        while (posted < stream_posts && posted - completed < 3 &&
               free_slot[next]) {
            u8 *buf = g_u2BurstBuffers[next];
            s16 *samples = (s16 *)buf;
            const u32 base = g_uacCtx.patternFrame;
            for (u32 i = 0; i < UAC_U2_BURST_BYTES / sizeof(s16); ++i) {
                const u32 frame = base + (i / 2);
                samples[i] = ((frame / 24) & 1) ? 0x4000 : (s16)-0x4000;
            }
            g_uacCtx.patternFrame = base + UAC_U2_BURST_BYTES / sizeof(s16) / 2;
            armDCacheFlush(buf, UAC_U2_BURST_BYTES);
#if defined(UAC_U2_CURSOR_DIAG)
            _uacLogCursor("pre", posted + 1);
#endif
            u32 urb = 0;
            Result rc = usbDsEndpoint_PostBufferAsync(
                g_uacCtx.audioEndpointIn, buf, UAC_U2_BURST_BYTES, &urb);
            LOG("UAC U2 pipe post buf=%u urb=%u rc=0x%x seq=%u\n",
                next, urb, rc, posted + 1);
#if defined(UAC_U2_CURSOR_DIAG)
            _uacLogCursor("post", posted + 1);
#endif
            if (R_FAILED(rc)) {
                pipe_failed = true;
                break;
            }
            urb_ids[next] = urb;
            free_slot[next] = 0;
            ++posted;
            if (++next >= UAC_U2_TRAIN_POSTS) next = 0;
            last_progress = svcGetSystemTick();
        }
        if (pipe_failed) break;
        if (posted == stream_posts && completed == posted) break;
        if (posted == completed) break; /* nothing in flight and nothing left */

        Result wait = eventWait(&g_uacCtx.audioEndpointIn->CompletionEvent,
                                16E+6);
        if (R_FAILED(wait)) {
            if ((svcGetSystemTick() - last_progress) > 100ULL * 19200) {
                if (recoveries < 8 && posted < stream_posts) {
                    /* v29f: a miss leaves the endpoint idle; cancel what is
                       still queued and let the next post take the empty
                       re-arm path.  Bounded so a dead endpoint cannot spin. */
                    Result cancel = usbDsEndpoint_Cancel(
                        g_uacCtx.audioEndpointIn);
                    u32 freed = 0;
                    for (u32 c = 0; c < UAC_U2_TRAIN_POSTS; ++c) {
                        if (free_slot[c]) continue;
                        free_slot[c] = 1;
                        ++completed;
                        ++freed;
                    }
                    ++recoveries;
                    LOG("UAC U2 pipe stall recover cancelled=%u rc=0x%x\n",
                        freed, cancel);
                    last_progress = svcGetSystemTick();
                    continue;
                }
                LOG("UAC U2 pipe stall posted=%u completed=%u\n",
                    posted, completed);
                break;
            }
            continue;
        }
        eventClear(&g_uacCtx.audioEndpointIn->CompletionEvent);
        UsbDsReportData report;
        if (R_FAILED(usbDsEndpoint_GetReportData(
                g_uacCtx.audioEndpointIn, &report))) {
            LOG("UAC U2 pipe report failed\n");
            pipe_failed = true;
            break;
        }
        for (u32 i = 0; i < report.report_count && i < 8; ++i) {
            const u32 id = report.report[i].id;
            /* v29b: with two in-flight requests the driver can emit a
               report entry for an entry that is still active (status 2).
               That is not a completion; keep the buffer in flight and wait
               for the real status (3) or an error status. */
            if (report.report[i].urb_status == 2) continue;
            for (u32 b = 0; b < UAC_U2_TRAIN_POSTS; ++b) {
                if (free_slot[b] || urb_ids[b] != id) continue;
                free_slot[b] = 1;
                ++completed;
                xfer_total += report.report[i].transferredSize;
                LOG("UAC U2 pipe done buf=%u urb=%u xfer=%u status=%u\n",
                    b, id, report.report[i].transferredSize,
                    report.report[i].urb_status);
#if defined(UAC_U2_CURSOR_DIAG)
                _uacLogCursor("done", b + 1);
#endif
                if (report.report[i].urb_status != 3) {
                    /* v29f: a status=5 is one lost set, not a dead stream.
                       Keep the other requests in flight and let the loop
                       post a replacement; a real halt is caught by the
                       100 ms stall path above. */
                    ++misses;
                    LOG("UAC U2 pipe miss buf=%u status=%u\n",
                        b, report.report[i].urb_status);
                }
                break;
            }
        }
        last_progress = svcGetSystemTick();
    }
    if (completed < posted) {
        /* Do not leave ISO requests pending across the alt0 teardown. */
        Result cancel = usbDsEndpoint_Cancel(g_uacCtx.audioEndpointIn);
        LOG("UAC U2 pipe cancel pending=%u rc=0x%x\n", posted - completed,
            cancel);
    }
#if defined(UAC_U2_CURSOR_DIAG)
    _uacLogCursor("end", 0);
#endif
    LOG("UAC U2 pipe end posted=%u completed=%u bytes=%u misses=%u recoveries=%u\n",
        posted, completed, xfer_total, misses, recoveries);
    _uacLogInstallState();
    _uacLogRingState();
#else
    u32 posted = 0, completed = 0;
    u64 tPrev = svcGetSystemTick();
    for (u32 n = 0; n < UAC_U2_TRAIN_POSTS; ++n) {
        u8 *buf = g_u2BurstBuffers[n];
        s16 *samples = (s16 *)buf;
        const u32 base = g_uacCtx.patternFrame;
        for (u32 i = 0; i < UAC_U2_BURST_BYTES / sizeof(s16); ++i) {
            const u32 frame = base + (i / 2);
            samples[i] = ((frame / 24) & 1) ? 0x4000 : (s16)-0x4000;
        }
        g_uacCtx.patternFrame = base + UAC_U2_BURST_BYTES / sizeof(s16) / 2;
        u32 seq = ++g_uacCtx.postSeq;
        LOG("UAC U2 post begin seq=%u/%u pattern=%u\n", seq,
            UAC_U2_TRAIN_POSTS, base);
#ifdef UAC_U2_RING_ADVANCE
        if (seq > 1) _uacAdvanceRing(seq, seq - 1);
#endif
#ifndef UAC_U2_LIGHT_LOG
        _uacLogSubmitState("pre", seq);
#endif
#ifdef UAC_U2_IDLE_CANCEL
        if (seq > 1) {
            /* v21: the timeout cancel already resets the ring to base; test
               whether cancelling while idle also resets the endpoint /
               controller dequeue, so the next TD set at the base is fetched.
               No request is pending here, so this only asks the driver to
               reset the endpoint. */
            Result cancel = usbDsEndpoint_Cancel(g_uacCtx.audioEndpointIn);
            LOG("UAC U2 idle cancel seq=%u rc=0x%x\n", seq, cancel);
            _uacLogSubmitState("after-cancel", seq);
        }
#endif
        armDCacheFlush(buf, UAC_U2_BURST_BYTES);
        eventClear(&g_uacCtx.audioEndpointIn->CompletionEvent);

        u32 urbId = 0;
        const u64 tPre = svcGetSystemTick();
        Result rc = usbDsEndpoint_PostBufferAsync(g_uacCtx.audioEndpointIn,
            buf, UAC_U2_BURST_BYTES, &urbId);
        const u64 tPost = svcGetSystemTick();
        LOG("UAC U2 post rc=0x%x urb=%u size=%u seq=%u\n",
            rc, urbId, UAC_U2_BURST_BYTES, seq);
        if (R_FAILED(rc)) break;
        ++posted;
#ifndef UAC_U2_LIGHT_LOG
        /* v16: log the accept state and the cave ring after every post, not
           just the first one; a rejected second submit leaves the box empty.
           UAC_U2_LIGHT_LOG keeps only the cheap lines: each dump is a dmnt
           attach, and six of them per burst dominate the inter-burst gap. */
        _uacLogSubmitState("post", seq);
        _uacLogRingState();
        _uacLogInstallState();
#endif

        if (R_FAILED(eventWait(&g_uacCtx.audioEndpointIn->CompletionEvent, 100E+6))) {
            /* Do not leave the request pending across alt0 teardown: the usb
               sysmodule can touch a dangling ISO request and fatal. */
            Result cancel = usbDsEndpoint_Cancel(g_uacCtx.audioEndpointIn);
            LOG("UAC U2 no completion within 100ms seq=%u cancel=0x%x\n",
                seq, cancel);
            _uacLogSubmitState("timeout", seq);
            _uacLogInstallState();
            _uacLogRingState();
            break;
        }
        const u64 tDone = svcGetSystemTick();
        ++completed;
        eventClear(&g_uacCtx.audioEndpointIn->CompletionEvent);
        /* v19: read the mailbox right after the completion event, before the
           report path can clean it, so seq1's last event code is visible. */
#ifndef UAC_U2_LIGHT_LOG
        _uacLogRingState();
#endif
        UsbDsReportData report;
        rc = usbDsEndpoint_GetReportData(g_uacCtx.audioEndpointIn, &report);
        if (R_FAILED(rc)) {
            LOG("UAC U2 report rc=0x%x seq=%u\n", rc, seq);
            _uacLogSubmitState("report-fail", seq);
            _uacLogInstallState();
            _uacLogRingState();
            break;
        }
        u32 requested = 0, transferred = 0;
        LOG("UAC U2 report data count=%u urb=%u seq=%u\n",
            report.report_count, urbId, seq);
        for (u32 i = 0; i < report.report_count && i < 8; ++i) {
            LOG("UAC U2 report[%u] id=%u req=%u xfer=%u status=%u\n", i,
                report.report[i].id, report.report[i].requestedSize,
                report.report[i].transferredSize,
                report.report[i].urb_status);
        }
        Result prc = usbDsParseReportData(&report, urbId, &requested,
                                          &transferred);
        LOG("UAC U2 complete rc=0x%x requested=%u transferred=%u seq=%u\n",
            prc, requested, transferred, seq);
        /* v24: cheap phase timing.  loop_ms is the previous completion to
           this post, post_ms is the IPC (including the cave re-arm),
           wait_ms is post to completion, report_ms is the report path.
           The wire gap is report_ms + loop_ms + post_ms of the next burst. */
        const u64 tReport = svcGetSystemTick();
        LOG("UAC U2 timing seq=%u loop_ms=%u post_ms=%u wait_ms=%u report_ms=%u online_ms=%u\n",
            seq, (u32)((tPre - tPrev) / 19200), (u32)((tPost - tPre) / 19200),
            (u32)((tDone - tPost) / 19200), (u32)((tReport - tDone) / 19200),
            (u32)((tReport - tPrev) / 19200));
        tPrev = tReport;
#ifndef UAC_U2_LIGHT_LOG
        _uacLogSubmitState("done", seq);
#endif
        if (R_FAILED(prc)) break;
        if (transferred != UAC_U2_BURST_BYTES) {
            LOG("UAC U2 short seq=%u requested=%u transferred=%u\n",
                seq, requested, transferred);
        }
    }
    LOG("UAC U2 train end posted=%u completed=%u pattern=%u\n", posted,
        completed, g_uacCtx.patternFrame);
    _uacLogInstallState();
    _uacLogRingState();
#endif
}
#endif

// UAC1 standard/class control requests.  SET_CUR sampling frequency carries a
// 3-byte OUT data stage; read it before deciding ACK vs STALL.
// usb:ds may signal the same setup on several interfaces' SetupEvents, so this
// handler must ignore requests that are not addressed to AC/AS or EP 0x84.
static bool _uacOwnsSetup(UsbDsInterface* iface, const UsbSetupPacket* setup)
{
    const u8 recipient = setup->bmRequestType & 0x1F;
    if (recipient == 0x02) {  // endpoint: EP 0x84
        if (!(setup->bmRequestType & 0x80))  // OUT (SET_CUR): AC or AS
            return (iface == g_uacCtx.acInterface ||
                    iface == g_uacCtx.asInterface) &&
                   (setup->wIndex & 0xFF) == g_uacStd.ep_address;
        return iface == g_uacCtx.asInterface &&  // IN (GET_*): AS
               (setup->wIndex & 0xFF) == g_uacStd.ep_address;
    }
    if (recipient == 0x01) {  // interface: only the addressed interface replies
        if (setup->wIndex == g_uacStd.ac_interface)
            return iface == g_uacCtx.acInterface;
        if (setup->wIndex == g_uacStd.as_interface)
            return iface == g_uacCtx.asInterface;
    }
    return false;  // device recipient: not ours
}

static void _handleUacSetup(UsbDsInterface* iface, const UsbSetupPacket* setup)
{
    if (!_uacOwnsSetup(iface, setup)) {
#ifdef UAC_HOST_PROBE
        LOG("UAC setup ignored[%u]: type=%02x req=%02x idx=%04x\n",
            iface->interface_index, setup->bmRequestType, setup->bRequest,
            setup->wIndex);
#endif
        return;
    }
    UacSetupPacket packet = {
        .bmRequestType = setup->bmRequestType,
        .bRequest = setup->bRequest,
        .wValue = setup->wValue,
        .wIndex = setup->wIndex,
        .wLength = setup->wLength,
    };
    UacActionResult result;

    const uint8_t recipient = setup->bmRequestType & 0x1F;
    const bool set_cur = (setup->bmRequestType & 0x60) == 0x20 &&
        setup->bRequest == 0x01 && setup->wLength == 3 &&
        ((recipient == 0x02 && (setup->wIndex & 0xFF) == g_uacStd.ep_address) ||
         (recipient == 0x01 && setup->wIndex == g_uacStd.as_interface));
    if (set_cur) {
        u8* payload = g_uacControlBuffer;  // must be 4KB-aligned for usb:ds DMA
        u32 transferred = 0;
        Result rc = _ctrlOutXfer(iface, payload, 3, &transferred);
        if (R_FAILED(rc) || transferred != 3) {
#ifdef UAC_HOST_PROBE
            LOG("UAC SET_CUR data stage failed rc=0x%x transferred=%u iface=%u\n",
                rc, transferred, iface->interface_index);
#endif
            /* usb:ds may deliver the setup to both AC and AS; the other side
               may still consume the data stage, so do not poison the pipe. */
            return;
        }
        result = UacStandardHandle(&g_uacStd, &packet, payload, transferred);
#ifdef UAC_HOST_PROBE
        LOG("UAC setup[%u] type=%02x req=%02x val=%04x idx=%04x len=%u action=%d rate=%u\n",
            iface->interface_index, packet.bmRequestType, packet.bRequest,
            packet.wValue, packet.wIndex, packet.wLength, result.action,
            g_uacStd.sample_rate);
#endif
        if (result.action == UAC_ACT_STALL) {
            usbDsInterface_StallCtrl(iface);
            return;
        }
        _ctrlAck(iface);
#ifdef UAC_U2_PATCH
        /* alt1 SET_CUR is the U2 trigger; ACK is already queued, so the
           bounded completion wait cannot delay the control status stage. */
        _postUacBurst();
#endif
        return;
    }

    result = UacStandardHandle(&g_uacStd, &packet, NULL, 0);
#ifdef UAC_HOST_PROBE
    LOG("UAC setup[%u] type=%02x req=%02x val=%04x idx=%04x len=%u action=%d rate=%u\n",
        iface->interface_index, packet.bmRequestType, packet.bRequest,
        packet.wValue, packet.wIndex, packet.wLength, result.action,
        g_uacStd.sample_rate);
#endif
    switch (result.action) {
    case UAC_ACT_WRITE:
        _ctrlWrite(iface, result.data, result.data_len);
        break;
    case UAC_ACT_START:
        g_uacCtx.streaming = true;
        _ctrlAck(iface);
        break;
    case UAC_ACT_STOP:
        g_uacCtx.streaming = false;
#ifdef UAC_U2_ALT_RETRIGGER
        /* v22: a host alt0 -> alt1 cycle re-installs the endpoint; let the
           next alt1 SET_CUR post a fresh burst again. */
        g_uacCtx.burstPosted = false;
#endif
        _ctrlAck(iface);
        break;
    case UAC_ACT_ACK:
        _ctrlAck(iface);
        break;
    case UAC_ACT_STALL:
    default:
        usbDsInterface_StallCtrl(iface);
        break;
    }
}

static void _handleSetupPacket(UsbDsInterface* iface)
{
    UsbSetupPacket setup;
    Result rc = usbDsInterface_GetSetupPacket(iface, &setup, sizeof(setup));
    if (R_FAILED(rc)) {
        LOG("GetSetupPacket failed: 0x%x\n", rc);
        return;
    }

#ifdef ISO_PROBE
    if (iface == g_isoInterface) {
        _handleIsoSetup(iface, &setup);
        return;
    }
#endif

#ifdef ALT1_PROBE
    if (iface == g_alt1Interface) {
        _handleAlt1Setup(iface, &setup);
        return;
    }
#endif

    if (g_uacCtx.initialized &&
        (iface == g_uacCtx.acInterface || iface == g_uacCtx.asInterface)) {
        _handleUacSetup(iface, &setup);
        return;
    }

    u8 type = setup.bmRequestType & 0x60;       // 0x00 standard, 0x20 class
    // usb:ds broadcasts class requests to every interface; only the owner of
    // the addressed endpoint may answer.  Stalling here would race the UAC
    // handler and intermittently kill endpoint-recipient control transfers.
    if ((setup.bmRequestType & 0x1F) == 0x02) {
        u8 endpoint = setup.wIndex & 0xFF;
        bool owns = iface == g_uvcCtx.streamingInterface &&
                    endpoint == g_videoEndpointDesc.bEndpointAddress;
        if (!owns) {
            LOG("EP0[%u]: endpoint 0x%02x not ours, ignoring\n",
                iface->interface_index, endpoint);
            return;
        }
    }

    LOG("EP0[%u]: reqType=0x%02x req=0x%02x wVal=0x%04x wIdx=0x%04x wLen=%u\n",
        iface->interface_index, setup.bmRequestType, setup.bRequest,
        setup.wValue, setup.wIndex, setup.wLength);

    u8 recipient = setup.bmRequestType & 0x1F;  // 0x01 = interface

    // Only answer requests addressed to this interface. If usb:ds ever
    // signals the same request on both interfaces' SetupEvents, this keeps
    // exactly one of them responding.
    if (recipient == 0x01 &&
        (setup.wIndex & 0xFF) != iface->interface_index) {
        LOG("EP0[%u]: wIndex mismatch, ignoring\n", iface->interface_index);
        return;
    }

    if (type == 0x20 && recipient == 0x01) {  // class request to interface
        if (iface == g_uvcCtx.streamingInterface)
            _handleVsSetup(iface, &setup);
        else
            _handleVcSetup(iface, &setup);
        return;
    }

    if (type == 0x00) {  // standard request (usb:ds handles most itself)
        if (setup.bRequest == USB_REQUEST_SET_INTERFACE) {
            // Single alt setting: accept alt 0, reject anything else.
            // Linux sends SET_INTERFACE(0) once at device probe time and
            // tolerates a stall, but accepting is cleaner.
            if (setup.wValue == 0)
                _ctrlAck(iface);
            else
                usbDsInterface_StallCtrl(iface);
            return;
        }
        if (setup.bRequest == USB_REQUEST_GET_INTERFACE &&
            (setup.bmRequestType & USB_REQTYPE_DIR_MASK) == USB_REQTYPE_DIR_TO_HOST) {
            u8 alt = 0;
            _ctrlWrite(iface, &alt, 1);
            return;
        }
    }

    LOG("EP0[%u]: unhandled request -> stall\n", iface->interface_index);
    usbDsInterface_StallCtrl(iface);
}

// ============================================================================
// Process USB Events
// ============================================================================

// Check one interface's SetupEvent and service the request if one is pending.
static bool _serviceSetup(UsbDsInterface* iface)
{
    if (!iface)
        return false;
    if (R_FAILED(eventWait(&iface->SetupEvent, 0)))
        return false;
    eventClear(&iface->SetupEvent);
    _handleSetupPacket(iface);
    return true;
}

void UvcDeviceProcessRequests(void)
{
#ifdef ISO_PROBE
#ifndef ISO_PROBE_STREAM
    _pollIsoProbe();
#endif
#endif
#ifdef ALT1_PROBE
    _pollAlt1Probe();
#endif
    u32 state = 0;
    if (R_FAILED(usbDsGetState(&state))) {
        return;
    }

    if (state != UsbState_Configured) {
        if (g_uvcCtx.state != UVC_STATE_DISCONNECTED) {
            LOG("USB host disconnected\n");
            g_uvcCtx.state = UVC_STATE_DISCONNECTED;
            g_uacCtx.streaming = false;
            g_lastErrorCode = UVC_ERROR_NONE;
#ifdef ISO_PROBE
            if (g_isoStatus.state == ISO_PROBE_PENDING)
                g_isoStatus.state = ISO_PROBE_RETAINED;
#endif
#ifdef ALT1_PROBE
            if (g_alt1Status.state == ALT1_PROBE_PENDING)
                g_alt1Status.state = ALT1_PROBE_FAILED;
#endif
        }
        return;
    }

    if (g_uvcCtx.state == UVC_STATE_DISCONNECTED) {
        LOG("USB host connected\n");
        g_uvcCtx.state = UVC_STATE_CONNECTED;
        g_uvcCtx.frameId = 0;
        g_uvcCtx.frameNumber = 0;
        g_lastErrorCode = UVC_ERROR_NONE;
    }

    // Service pending setup requests. The host's probe/commit negotiation
    // arrives as a burst of EP0 requests; after servicing one, briefly wait
    // for the follow-up so the sequence isn't paced by our caller's sleep.
    bool serviced = _serviceSetup(g_uvcCtx.controlInterface);
    serviced |= _serviceSetup(g_uvcCtx.streamingInterface);
#ifdef ISO_PROBE
    serviced |= _serviceSetup(g_isoInterface);
#endif
#ifdef ALT1_PROBE
    serviced |= _serviceSetup(g_alt1Interface);
#endif
    // UAC is polled here.  When UAC is enabled, add its SetupEvents to the
    // waitMulti set below so a multi-request burst is not caller-paced.
    if (g_uacCtx.initialized) {
        serviced |= _serviceSetup(g_uacCtx.acInterface);
        serviced |= _serviceSetup(g_uacCtx.asInterface);
    }

    while (serviced &&
           g_uvcCtx.controlInterface && g_uvcCtx.streamingInterface) {
        s32 idx;
#if defined(ISO_PROBE) && !defined(ALT1_PROBE)
        if (R_FAILED(waitMulti(&idx, 20E+6,
                waiterForEvent(&g_uvcCtx.controlInterface->SetupEvent),
                waiterForEvent(&g_uvcCtx.streamingInterface->SetupEvent),
                waiterForEvent(&g_isoInterface->SetupEvent))))
            break;
#elif defined(ALT1_PROBE)
        if (R_FAILED(waitMulti(&idx, 20E+6,
                waiterForEvent(&g_uvcCtx.controlInterface->SetupEvent),
                waiterForEvent(&g_uvcCtx.streamingInterface->SetupEvent),
                waiterForEvent(&g_alt1Interface->SetupEvent))))
            break;
#elif defined(UAC_HOST_PROBE)
        if (R_FAILED(waitMulti(&idx, 20E+6,
                waiterForEvent(&g_uvcCtx.controlInterface->SetupEvent),
                waiterForEvent(&g_uvcCtx.streamingInterface->SetupEvent),
                waiterForEvent(&g_uacCtx.acInterface->SetupEvent),
                waiterForEvent(&g_uacCtx.asInterface->SetupEvent))))
            break;
#else
        if (R_FAILED(waitMulti(&idx, 20E+6,  // 20ms
                waiterForEvent(&g_uvcCtx.controlInterface->SetupEvent),
                waiterForEvent(&g_uvcCtx.streamingInterface->SetupEvent))))
            break;  // no follow-up request - burst is over
#endif

        serviced = _serviceSetup(g_uvcCtx.controlInterface);
        serviced |= _serviceSetup(g_uvcCtx.streamingInterface);
#ifdef ISO_PROBE
        serviced |= _serviceSetup(g_isoInterface);
#endif
#ifdef ALT1_PROBE
        serviced |= _serviceSetup(g_alt1Interface);
#endif
#ifdef UAC_HOST_PROBE
        serviced |= _serviceSetup(g_uacCtx.acInterface);
        serviced |= _serviceSetup(g_uacCtx.asInterface);
#endif
    }
}

// ============================================================================
// UAC (Audio) Implementation
// ============================================================================

bool UacDeviceIsStreaming(void)
{
#ifdef UAC_HOST_PROBE
    // U0 is enumeration/control only; do not let the audio thread post data
    // on an AS endpoint that has no ISO producer yet.
    return false;
#else
    return g_uacCtx.initialized && g_uacCtx.streaming;
#endif
}

bool UacDeviceSendAudio(const void* data, size_t size, u64 timestamp)
{
    (void)timestamp;

    if (!g_uacCtx.initialized || !g_uacCtx.streaming) {
        return false;
    }

    if (!g_uacCtx.audioEndpointIn) {
        return false;
    }

    mutexLock(&g_uacCtx.audioMutex);

    Result rc;
    bool success = true;
    u32 urbId;
    UsbDsReportData reportData;

    const u8* srcData = (const u8*)data;
    size_t remaining = size;

    // 192-byte packets = 1ms of 48kHz stereo 16-bit, matching the endpoint's
    // wMaxPacketSize and bInterval
    const size_t isoPacketSize = UAC_ISO_PACKET_SIZE;

    while (remaining > 0 && success) {
        size_t chunkSize = remaining >= isoPacketSize ? isoPacketSize : remaining;

        // Pad partial tail packets with silence
        memset(g_audioEndpointBuffer, 0, isoPacketSize);
        memcpy(g_audioEndpointBuffer, srcData, chunkSize);

        eventClear(&g_uacCtx.audioEndpointIn->CompletionEvent);  // drop stale signal
        rc = usbDsEndpoint_PostBufferAsync(g_uacCtx.audioEndpointIn,
            g_audioEndpointBuffer, isoPacketSize, &urbId);
        if (R_FAILED(rc)) {
            success = false;
            break;
        }

        // Iso packets go out on the next 1ms service interval; no completion
        // within 10ms means the host is not polling the endpoint.
        rc = eventWait(&g_uacCtx.audioEndpointIn->CompletionEvent, 10E+6);
        if (R_FAILED(rc)) {
            // Cancel AND reap the cancelled URB's report - cancelling without
            // reaping and then re-posting drives usb:ds into an assertion.
            usbDsEndpoint_Cancel(g_uacCtx.audioEndpointIn);
            if (R_SUCCEEDED(eventWait(&g_uacCtx.audioEndpointIn->CompletionEvent, 100E+6))) {
                eventClear(&g_uacCtx.audioEndpointIn->CompletionEvent);
                usbDsEndpoint_GetReportData(g_uacCtx.audioEndpointIn, &reportData);
            }
            success = false;
            break;
        }
        eventClear(&g_uacCtx.audioEndpointIn->CompletionEvent);

        rc = usbDsEndpoint_GetReportData(g_uacCtx.audioEndpointIn, &reportData);
        if (R_FAILED(rc)) {
            success = false;
            break;
        }

        u32 transferred;
        rc = usbDsParseReportData(&reportData, urbId, NULL, &transferred);
        if (R_FAILED(rc)) {
            success = false;
            break;
        }

        srcData += chunkSize;
        remaining -= chunkSize;

        // Small delay to maintain timing (approximately 1ms per packet)
        // This helps maintain proper audio timing
        if (remaining > 0) {
            svcSleepThread(800000);  // ~0.8ms - slightly less than 1ms to account for processing
        }
    }

    mutexUnlock(&g_uacCtx.audioMutex);
    return success;
}
