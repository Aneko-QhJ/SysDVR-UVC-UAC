#include <string.h>
#include "uvc_device.h"
#include "uac_standard.h"
#ifdef ALT1_PROBE
#include "alt1_probe_protocol.h"
#endif
#include "../core.h"
#ifdef ISO_PROBE
#include "iso_probe_protocol.h"
#ifdef ISO_RUNTIME_PATCH
#include "iso_runtime_patch.h"
#include "iso_runtime_payload.h"
#include "iso_runtime_stream_payload.h"
#endif
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

static UvcDeviceContext g_uvcCtx;

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

#ifdef ISO_RUNTIME_PATCH
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
        if (diag.magic == ISO_PROBE_DIAG_MAGIC || isoProbeIsBurstDiagnostics(diag.magic) || diag.magic == ISO_PROBE_REPORT_MARKER ||
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

    R_RET_ON_FAIL(usbDsInterface_AppendConfigurationData(g_uacCtx.acInterface,
        UsbDeviceSpeed_High, g_uacAcDescriptors, acLen));
    R_RET_ON_FAIL(usbDsInterface_AppendConfigurationData(g_uacCtx.acInterface,
        UsbDeviceSpeed_Super, g_uacAcDescriptors, acLen));
    R_RET_ON_FAIL(usbDsInterface_EnableInterface(g_uacCtx.acInterface));

    R_RET_ON_FAIL(usbDsInterface_AppendConfigurationData(g_uacCtx.asInterface,
        UsbDeviceSpeed_High, g_uacAsHsDescriptors, hsLen));
    R_RET_ON_FAIL(usbDsInterface_AppendConfigurationData(g_uacCtx.asInterface,
        UsbDeviceSpeed_Super, g_uacAsSsDescriptors, ssLen));
    R_RET_ON_FAIL(usbDsInterface_RegisterEndpoint(g_uacCtx.asInterface,
        &g_uacCtx.audioEndpointIn, epAddress));
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

        // UAC remains disabled until device ISO and alt-setting support are
        // verified. ISO_PROBE tests a separate vendor alt0 interface first.
        (void)_setupAudioInterfaces5x;  // suppress unused warning

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

// UAC1 standard/class control requests.  SET_CUR sampling frequency carries a
// 3-byte OUT data stage; read it before deciding ACK vs STALL.
static void _handleUacSetup(UsbDsInterface* iface, const UsbSetupPacket* setup)
{
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
        u8 payload[3];
        u32 transferred = 0;
        Result rc = _ctrlOutXfer(iface, payload, sizeof(payload), &transferred);
        if (R_FAILED(rc) || transferred != sizeof(payload)) {
            usbDsInterface_StallCtrl(iface);
            return;
        }
        result = UacStandardHandle(&g_uacStd, &packet, payload, transferred);
        if (result.action == UAC_ACT_STALL) {
            usbDsInterface_StallCtrl(iface);
            return;
        }
        _ctrlAck(iface);
        return;
    }

    result = UacStandardHandle(&g_uacStd, &packet, NULL, 0);
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

    LOG("EP0[%u]: reqType=0x%02x req=0x%02x wVal=0x%04x wIdx=0x%04x wLen=%u\n",
        iface->interface_index, setup.bmRequestType, setup.bRequest,
        setup.wValue, setup.wIndex, setup.wLength);

    u8 type = setup.bmRequestType & 0x60;       // 0x00 standard, 0x20 class
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
    }
}

// ============================================================================
// UAC (Audio) Implementation
// ============================================================================

bool UacDeviceIsStreaming(void)
{
    return g_uacCtx.initialized && g_uacCtx.streaming;
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
