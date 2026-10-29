#define _POSIX_C_SOURCE 200809L
#include <libusb.h>
#include <errno.h>
#include <signal.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "../../../source/uvc/iso_probe_protocol.h"

static volatile sig_atomic_t interrupted;
static bool done, payload_ok, burst_mode, alt1_mode;
static unsigned matched, unexpected;
static uint16_t sequence;
static FILE *logfile;
static const char *logpath;
#ifndef ISO_HOST_SLOT_SIZE
#define ISO_HOST_SLOT_SIZE ISO_PROBE_PACKET_SIZE
#endif
_Static_assert(ISO_HOST_SLOT_SIZE == 192 || ISO_HOST_SLOT_SIZE == 256, "unsupported host slot size");

static void on_signal(int sig) { (void)sig; interrupted = 1; }
static double now(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec + t.tv_nsec / 1e9;
}
static void pause_ms(unsigned ms) {
    struct timespec t = {ms / 1000, (long)(ms % 1000) * 1000000};
    while (nanosleep(&t, &t) && errno == EINTR && !interrupted) {}
}
static void hex(FILE *out, const unsigned char *data, unsigned n) {
    for (unsigned i = 0; i < n; ++i) fprintf(out, "%02x", data[i]);
}
static void LIBUSB_CALL received(struct libusb_transfer *transfer) {
    fprintf(logfile, "{\"kind\":\"host_callback_time\",\"sequence\":%u,\"monotonic_seconds\":%.9f}\n",
            sequence, now());
    /* Public packet lengths may be left at zero by Darwin on overall errors.
     * Preserve the allocation as independent diagnostic evidence, never as a
     * substitute for successful per-packet status/length validation. */
    size_t path_size = strlen(logpath) + 40;
    char *path = malloc(path_size);
    bool saved = false;
    if (path) {
        snprintf(path, path_size, "%s.seq%u.buffer.bin", logpath, sequence);
        FILE *raw = fopen(path, "wx");
        if (raw) {
            saved = fwrite(transfer->buffer, 1, (size_t)transfer->length, raw) == (size_t)transfer->length;
            if (fclose(raw)) saved = false;
        }
        free(path);
    }
    unsigned nonzero = 0, raw_patterns = 0;
    for (int i = 0; i < transfer->length; ++i) nonzero += transfer->buffer[i] != 0;
    for (int i = 0; i + ISO_PROBE_PACKET_SIZE <= transfer->length; i += ISO_HOST_SLOT_SIZE) {
        bool exact = true;
        for (unsigned j = 0; j < ISO_PROBE_PACKET_SIZE; ++j)
            if (transfer->buffer[i+j] != isoProbeByte(sequence, j)) { exact = false; break; }
        raw_patterns += exact;
    }
    fprintf(logfile, "{\"kind\":\"raw_buffer\",\"sequence\":%u,\"size\":%d,"
            "\"saved\":%s,\"nonzero_bytes\":%u,\"aligned_test_patterns\":%u,"
            "\"packet_receipt_verified\":false}\n", sequence, transfer->length,
            saved ? "true" : "false", nonzero, raw_patterns);
    fprintf(logfile, "{\"kind\":\"iso_transfer\",\"sequence\":%u,\"status\":%d,\"packets\":[",
            sequence, transfer->status);
    matched = unexpected = 0;
    unsigned seen = 0;
    int first_packet = -1;
    bool ordered = true;
    for (int i = 0; i < transfer->num_iso_packets; ++i) {
        const struct libusb_iso_packet_descriptor *p = &transfer->iso_packet_desc[i];
        unsigned char *data = libusb_get_iso_packet_buffer_simple(transfer, (unsigned)i);
        bool exact = p->status == LIBUSB_TRANSFER_COMPLETED && p->actual_length == ISO_PROBE_PACKET_SIZE;
        unsigned ordinal = 0;
        uint16_t packet_sequence = sequence;
        if (exact && burst_mode) {
            packet_sequence = (uint16_t)(data[4] | (unsigned)data[5] << 8);
            ordinal = (uint16_t)(packet_sequence - sequence);
            exact = ordinal < ISO_PROBE_BURST_PACKETS;
        }
        if (exact) {
            for (unsigned j = 0; j < ISO_PROBE_PACKET_SIZE; ++j)
                if (data[j] != isoProbeByte(packet_sequence, j)) { exact = false; break; }
        }
        if (exact && burst_mode) {
            if (seen & (1u << ordinal)) exact = false;
            else {
                seen |= 1u << ordinal;
                if (first_packet < 0) first_packet = i;
                if (ordinal != matched || i - first_packet != (int)ordinal) ordered = false;
            }
        }
        if (exact) ++matched;
        else if (p->actual_length) ++unexpected;
        if (i) fputc(',', logfile);
        fprintf(logfile, "{\"index\":%d,\"status\":%d,\"length\":%u,\"matches\":%s",
                i, p->status, p->actual_length, exact ? "true" : "false");
        if (p->actual_length) {
            fprintf(logfile, ",\"data_hex\":\"");
            hex(logfile, data, p->actual_length <= p->length ? p->actual_length : p->length);
            fputc('"', logfile);
        }
        fputc('}', logfile);
    }
    fprintf(logfile, "]}\n"); fflush(logfile);
    payload_ok = matched == (burst_mode ? ISO_PROBE_BURST_PACKETS : 1) && unexpected == 0 &&
        (!burst_mode || (ordered && seen == 0xffff && transfer->status == LIBUSB_TRANSFER_COMPLETED));
    done = true;
}

static int status(libusb_device_handle *device, int iface, IsoProbeStatus *out) {
    memset(out, 0, sizeof(*out));
    int rc = libusb_control_transfer(device, 0xc1, ISO_PROBE_STATUS, 0, (uint16_t)iface,
                                    (unsigned char *)out, sizeof(*out), 3000);
    if (rc != sizeof(*out)) return rc < 0 ? rc : LIBUSB_ERROR_IO;
    if (out->magic != ISO_PROBE_STATUS_MAGIC || out->version != 1) return LIBUSB_ERROR_IO;
    fprintf(logfile, "{\"kind\":\"device_status\",\"sequence\":%u,\"state\":%u,"
            "\"post_result\":%u,\"urb_id\":%u,\"report_id\":%u,\"requested\":%u,"
            "\"raw_count\":%u,\"urb_status\":%u,\"speed\":%u,\"endpoint\":%u,"
            "\"report_count\":%u,\"report_result\":%u,\"diagnostics_hex\":\"",
            out->sequence, out->state, out->post_result, out->urb_id, out->report_id,
            out->requested, out->transferred, out->urb_status, out->speed, out->endpoint,
            out->report_count, out->report_result);
    hex(logfile, (const unsigned char *)&out->diagnostics, sizeof(out->diagnostics));
    fprintf(logfile, "\"}\n"); fflush(logfile);
    return 0;
}

static void drain(libusb_context *ctx, struct libusb_transfer *transfer) {
    if (!done) libusb_cancel_transfer(transfer);
    while (!done) {
        struct timeval wait = {0, 100000};
        int rc = libusb_handle_events_timeout(ctx, &wait);
        if (rc && rc != LIBUSB_ERROR_INTERRUPTED)
            fprintf(stderr, "Waiting for cancellation callback: %s\n", libusb_error_name(rc));
    }
    /* Darwin cancels the endpoint's transfers; callback, not Cancel's return,
       proves that libusb no longer owns this allocation. */
}

int main(int argc, char **argv) {
    unsigned repeats = 1;
    unsigned packets = 512;
    unsigned trigger_delay_ms = 10;
    bool cancel_only = false, frame_only = false, receive_only = false, empty_window = false;
    bool status_only = false;
    bool report_only = false;
    const char *outpath = NULL;
    for (int i = 1; i < argc; ++i) {
        if (!strcmp(argv[i], "--repeat") && i + 1 < argc) {
            char *end;
            unsigned long n = strtoul(argv[++i], &end, 10);
            if (*end || n < 1 || n > 65535) { fprintf(stderr, "repeat must be 1..65535\n"); return 2; }
            repeats = (unsigned)n;
        } else if (!strcmp(argv[i], "--packets") && i + 1 < argc) {
            char *end;
            unsigned long n = strtoul(argv[++i], &end, 10);
            if (*end || n < 64 || n > 512) { fprintf(stderr, "packets must be 64..512\n"); return 2; }
            packets = (unsigned)n;
        } else if (!strcmp(argv[i], "--trigger-delay-ms") && i + 1 < argc) {
            char *end;
            unsigned long n = strtoul(argv[++i], &end, 10);
            if (*end || n < 1 || n > 500) { fprintf(stderr, "trigger delay must be 1..500 ms\n"); return 2; }
            trigger_delay_ms = (unsigned)n;
        } else if (!strcmp(argv[i], "--log") && i + 1 < argc) outpath = argv[++i];
        else if (!strcmp(argv[i], "--burst")) burst_mode = true;
        else if (!strcmp(argv[i], "--alt1")) alt1_mode = true;
        else if (!strcmp(argv[i], "--cancel")) cancel_only = true;
        else if (!strcmp(argv[i], "--frames")) frame_only = true;
        else if (!strcmp(argv[i], "--receive-only")) receive_only = true;
        else if (!strcmp(argv[i], "--empty-window")) { receive_only = true; empty_window = true; }
        else if (!strcmp(argv[i], "--status")) status_only = true;
        else if (!strcmp(argv[i], "--report")) report_only = true;
        else {
            fprintf(stderr, "Usage: %s --log run.jsonl [--repeat 100 | --cancel | --frames | --receive-only | --empty-window | --status] [--packets 64..512] [--burst] [--alt1] [--trigger-delay-ms 1..500]\n", argv[0]);
            return 2;
        }
    }
    if ((unsigned)cancel_only + (unsigned)frame_only + (unsigned)receive_only +
        (unsigned)status_only > 1 || ((cancel_only || frame_only || receive_only) && repeats != 1)) return 2;
    if (burst_mode && (cancel_only || frame_only || receive_only || status_only)) return 2;
    if (!outpath) { fprintf(stderr, "An explicit --log path is required\n"); return 2; }
    logpath = outpath;
    logfile = fopen(outpath, "wx");
    if (!logfile) { perror(outpath); return 2; }
#ifdef ISO_NATIVE_DIAGNOSTICS
    fprintf(logfile, "{\"kind\":\"receiver_backend\",\"name\":\"isolated libusb 1.0.30 native ISO diagnostics\",\"overall_status_modified\":false}\n");
#endif
    signal(SIGINT, on_signal); signal(SIGTERM, on_signal);
    libusb_context *ctx = NULL;
    libusb_device_handle *device = NULL;
    struct libusb_config_descriptor *config = NULL;
    struct libusb_transfer *transfer = NULL;
    unsigned char *buffer = NULL;
    int iface = -1, endpoint = -1, result = 1, rc;
    bool claimed = false;
    rc = libusb_init(&ctx);
    if (rc) goto fail;
    libusb_set_option(ctx, LIBUSB_OPTION_LOG_LEVEL, LIBUSB_LOG_LEVEL_WARNING);
    device = libusb_open_device_with_vid_pid(ctx, 0x1209, 0xca57);
    if (!device) { fprintf(stderr, "SysDVR 1209:ca57 not accessible\n"); goto cleanup; }
    int speed = libusb_get_device_speed(libusb_get_device(device));
    if (speed != LIBUSB_SPEED_HIGH && speed != LIBUSB_SPEED_SUPER) {
        fprintf(stderr, "Unsupported speed %d; requires HS or SS\n", speed); goto cleanup;
    }
    if (burst_mode && speed != LIBUSB_SPEED_HIGH) {
        fprintf(stderr, "A13 burst requires USB2/HS connection\n"); goto cleanup;
    }
    rc = libusb_get_active_config_descriptor(libusb_get_device(device), &config);
    if (rc) goto fail;
    for (unsigned i = 0; i < config->bNumInterfaces; ++i) {
        for (int j = 0; j < config->interface[i].num_altsetting; ++j) {
            const struct libusb_interface_descriptor *d = &config->interface[i].altsetting[j];
            if (d->bInterfaceClass != 0xff || d->bInterfaceSubClass != 0x49 ||
                d->bInterfaceProtocol != 1) continue;
            if (status_only || report_only) {
                if (d->bInterfaceNumber == 2) iface = 2;
                continue;
            }
            if (d->bAlternateSetting != (alt1_mode ? 1 : 0)) continue;
            if (iface != -1 || d->bInterfaceNumber != 2 || d->bNumEndpoints != 1) {
                fprintf(stderr, "Ambiguous/unexpected experiment interface\n"); goto cleanup;
            }
            const struct libusb_endpoint_descriptor *ep = &d->endpoint[0];
            if (ep->bEndpointAddress != 0x83 || (ep->bmAttributes & 3) != LIBUSB_TRANSFER_TYPE_ISOCHRONOUS ||
                (ep->wMaxPacketSize != 192 && ep->wMaxPacketSize != 256) || ep->bInterval != 4) {
                fprintf(stderr, "Unexpected experiment endpoint\n"); goto cleanup;
            }
            if (speed == LIBUSB_SPEED_SUPER) {
                struct libusb_ss_endpoint_companion_descriptor *ss = NULL;
                rc = libusb_get_ss_endpoint_companion_descriptor(ctx, ep, &ss);
                if (rc) goto fail;
                bool valid = ss->bMaxBurst == 0 && ss->bmAttributes == 0 && ss->wBytesPerInterval == 192;
                libusb_free_ss_endpoint_companion_descriptor(ss);
                if (!valid) { fprintf(stderr, "Unexpected SS companion\n"); goto cleanup; }
            }
            if (burst_mode && ep->wMaxPacketSize != 256) {
                fprintf(stderr, "A13 burst requires MPS256 descriptor\n"); goto cleanup;
            }
            iface = d->bInterfaceNumber; endpoint = ep->bEndpointAddress;
            fprintf(logfile, "{\"kind\":\"endpoint_descriptor\",\"mps\":%u,\"interval\":%u,\"payload_size\":192}\n",
                    ep->wMaxPacketSize, ep->bInterval);
        }
    }
    if (iface == -1) { fprintf(stderr, "ISO_PROBE interface missing\n"); goto cleanup; }
    fprintf(logfile, "{\"kind\":\"session\",\"host\":\"libusb\",\"speed\":%d,"
            "\"interface\":%d,\"endpoint\":%d,\"config_length\":%u,\"repeats\":%u,\"packets\":%u}\n",
            speed, iface, endpoint, config->wTotalLength, repeats, packets);
    /* Do not detach drivers, change configuration, or claim UVC interfaces. */
    rc = libusb_claim_interface(device, iface);
    if (rc) goto fail;
    claimed = true;
    if (status_only) {
        IsoProbeStatus state;
        result = status(device, iface, &state) ? 1 : 0;
        goto cleanup;
    }
    if (report_only) {
        unsigned char report[256] = {0};
        rc = libusb_control_transfer(device, 0xa1, 0x01, 0x0100, (uint16_t)iface,
                                     report, sizeof(report), 3000);
        if (rc < 0) {
            fprintf(stderr, "GET_REPORT failed: %s\n", libusb_error_name(rc));
            goto fail;
        }
        fprintf(logfile, "{\"kind\":\"report\",\"length\":%d,\"hex\":\"", rc);
        hex(logfile, report, (size_t)rc);
        fprintf(logfile, "\"}\n"); fflush(logfile);
        result = 0;
        goto cleanup;
    }
    if (alt1_mode) {
        rc = libusb_set_interface_alt_setting(device, iface, 1);
        if (rc) goto fail;
    }
    fprintf(logfile, "{\"kind\":\"experiment\",\"burst_packets\":%u,\"trigger_delay_ms\":%u}\n",
            burst_mode ? ISO_PROBE_BURST_PACKETS : 1, trigger_delay_ms);
    IsoProbeStatus state;
    rc = status(device, iface, &state);
    if (rc) goto fail;
    if (frame_only) {
        IsoProbeFrameReport frames = {0};
        rc = libusb_control_transfer(device, 0xc1, ISO_PROBE_FRAMES, 0,
                (uint16_t)iface, (unsigned char *)&frames, sizeof(frames), 3000);
        if (rc < 0) goto fail;
        if (rc != sizeof(frames) || frames.magic != ISO_PROBE_FRAMES_MAGIC ||
                frames.version != 1 || frames.count != ISO_PROBE_FRAME_SAMPLES ||
                !frames.tick_frequency) {
            fprintf(stderr, "Invalid frame report\n"); goto cleanup;
        }
        fprintf(logfile, "{\"kind\":\"frame_report\",\"count\":%u,\"tick_frequency\":%u,"
                "\"verified\":%u,\"no_td_submitted\":true}\n",
                frames.count, frames.tick_frequency, frames.verified);
        for (unsigned i = 0; i < frames.count; ++i) {
            const IsoProbeFrameSample *s = &frames.samples[i];
            fprintf(logfile, "{\"kind\":\"frame_sample\",\"index\":%u,"
                    "\"ticks_before\":%llu,\"ticks_after\":%llu,\"raw_mfi\":%u,"
                    "\"control\":%u,\"portsc\":%u,\"result\":%u,\"mmio\":\"%016llX\"}\n",
                    i, (unsigned long long)s->ticks_before, (unsigned long long)s->ticks_after,
                    s->raw_mfi, s->control, s->portsc, s->result, (unsigned long long)s->mmio);
        }
        fprintf(stderr, "Frame counter samples: %u, device rate check: %s; no TD submitted\n",
                frames.count, frames.verified ? "PASS" : "FAIL");
        result = frames.verified ? 0 : 1;
        goto cleanup;
    }
    if (cancel_only) {
        rc = libusb_control_transfer(device, 0x41, ISO_PROBE_CANCEL, 0, (uint16_t)iface, NULL, 0, 3000);
        if (rc < 0) goto fail;
        rc = status(device, iface, &state);
        if (rc) goto fail;
        result = state.state != ISO_PROBE_PENDING && state.state != ISO_PROBE_RETAINED ? 0 : 1;
        goto cleanup;
    }
    if (state.state == ISO_PROBE_PENDING || state.state == ISO_PROBE_RETAINED) {
        fprintf(stderr, "Device retains a previous URB; collect logs/use --cancel before retriggering\n"); goto cleanup;
    }
    transfer = libusb_alloc_transfer((int)packets);
    fprintf(logfile, "{\"kind\":\"host_slot_size\",\"requested_bytes\":%u,\"payload_bytes\":192}\n",
            (unsigned)ISO_HOST_SLOT_SIZE);
    buffer = calloc(packets, ISO_HOST_SLOT_SIZE);
    if (!transfer || !buffer) { fprintf(stderr, "allocation failed\n"); goto cleanup; }
    if (receive_only) {
        /* --receive-only keeps its fresh-boot requirement. --empty-window
         * is a separate post-completion diagnostic; never submits a device TD. */
        IsoProbeStatus before_window = state;
        bool terminal = state.state == ISO_PROBE_COMPLETE && state.urb_status == 3 &&
            state.urb_id == state.report_id && state.post_result == 0 && state.report_result == 0 &&
            state.requested > 0 && state.transferred == state.requested &&
            state.diagnostics.terminal == 1 &&
            (state.diagnostics.magic == ISO_PROBE_DIAG_MAGIC || isoProbeIsBurstDiagnostics(state.diagnostics.magic));
        if (empty_window ? !terminal :
            (state.state != ISO_PROBE_IDLE || state.sequence != 0 || state.urb_id != 0)) {
            fprintf(stderr, "Window baseline requires fresh idle (--receive-only) or verified terminal completion (--empty-window)\n");
            goto cleanup;
        }
        sequence = 0; done = payload_ok = false;
        libusb_fill_iso_transfer(transfer, device, (unsigned char)endpoint, buffer,
            (int)packets * ISO_HOST_SLOT_SIZE, (int)packets, received, NULL, 2000);
        libusb_set_iso_packet_lengths(transfer, ISO_HOST_SLOT_SIZE);
        rc = libusb_submit_transfer(transfer);
        if (rc) { done = true; goto fail; }
        double deadline = now() + 3.0;
        while (!done && now() < deadline && !interrupted) {
            struct timeval wait = {0, 10000};
            rc = libusb_handle_events_timeout(ctx, &wait);
            if (rc && rc != LIBUSB_ERROR_INTERRUPTED) { drain(ctx, transfer); goto fail; }
        }
        bool cancelled = !done;
        drain(ctx, transfer);
        rc = status(device, iface, &state);
        if (rc) goto fail;
        unsigned nonzero = 0;
        for (unsigned i = 0; i < packets * ISO_HOST_SLOT_SIZE; ++i) nonzero += buffer[i] != 0;
        bool unchanged = state.state == before_window.state && state.sequence == before_window.sequence &&
            state.urb_id == before_window.urb_id && state.urb_status == before_window.urb_status &&
            state.transferred == before_window.transferred && state.report_result == 0;
        fprintf(logfile, "{\"kind\":\"receive_only_baseline\",\"no_td_submitted\":true,"
                "\"device_idle\":%s,\"device_state_unchanged\":%s,\"after_terminal_completion\":%s,"
                "\"host_cancel_requested\":%s,\"nonzero_bytes\":%u,"
                "\"iso_payload_verified\":false,\"wire_trace_verified\":false}\n",
                state.state == ISO_PROBE_IDLE ? "true" : "false", unchanged ? "true" : "false",
                empty_window ? "true" : "false", cancelled ? "true" : "false", nonzero);
        fflush(logfile);
        /* Acquisition succeeded; native errors remain recorded, never normalized. */
        result = !interrupted && unchanged && nonzero == 0 ? 0 : 1;
        goto cleanup;
    }
    for (unsigned attempt = 1; attempt <= repeats && !interrupted; ++attempt) {
        sequence = (uint16_t)attempt;
        done = payload_ok = false;
        memset(buffer, 0, packets * ISO_HOST_SLOT_SIZE);
        libusb_fill_iso_transfer(transfer, device, (unsigned char)endpoint, buffer,
            (int)packets * ISO_HOST_SLOT_SIZE, (int)packets, received, NULL, 2000);
        libusb_set_iso_packet_lengths(transfer, ISO_HOST_SLOT_SIZE);
        double submit_before = now();
        rc = libusb_submit_transfer(transfer);
        double submit_after = now();
        if (rc) { done = true; goto fail; }
        pause_ms(trigger_delay_ms); /* Keep the device TD inside the explicitly logged host window. */
        double trigger_before = now();
        rc = libusb_control_transfer(device, 0x41, burst_mode ? ISO_PROBE_BURST : ISO_PROBE_TRIGGER, sequence,
                                     (uint16_t)iface, NULL, 0, 3000);
        double trigger_after = now();
        fprintf(logfile, "{\"kind\":\"host_trigger_timing\",\"sequence\":%u,"
                "\"submit_before\":%.9f,\"submit_after\":%.9f,"
                "\"trigger_before\":%.9f,\"trigger_after\":%.9f,"
                "\"submit_ms\":%.6f,\"actual_wait_ms\":%.6f,\"trigger_ms\":%.6f,\"trigger_result\":%d}\n",
                sequence, submit_before, submit_after, trigger_before, trigger_after,
                (submit_after-submit_before)*1000, (trigger_before-submit_after)*1000,
                (trigger_after-trigger_before)*1000, rc);
        if (rc < 0) { drain(ctx, transfer); goto fail; }
        double deadline = now() + 3.0, next_poll = 0;
        while ((!done || state.sequence != sequence || state.state == ISO_PROBE_PENDING) &&
               now() < deadline && !interrupted) {
            struct timeval wait = {0, 10000};
            rc = libusb_handle_events_timeout(ctx, &wait);
            if (rc && rc != LIBUSB_ERROR_INTERRUPTED) { drain(ctx, transfer); goto fail; }
            if (now() >= next_poll) {
                rc = status(device, iface, &state);
                if (rc) { drain(ctx, transfer); goto fail; }
                next_poll = now() + 0.05;
            }
        }
        if (!done) drain(ctx, transfer);
        rc = status(device, iface, &state);
        if (rc) goto fail;
        bool complete = state.sequence == sequence && state.state == ISO_PROBE_COMPLETE &&
                        (burst_mode ? isoProbeIsBurstDiagnostics(state.diagnostics.magic) :
                         state.diagnostics.magic == ISO_PROBE_DIAG_MAGIC) &&
                        state.diagnostics.terminal == 1 && state.post_result == 0 && state.report_result == 0 &&
                        state.urb_id == state.report_id && state.urb_status == 3 &&
                        state.requested == (burst_mode ? 3072u : 192u) &&
                        state.transferred == state.requested;
        fprintf(logfile, "{\"kind\":\"result\",\"sequence\":%u,\"iso_payload_verified\":%s,"
                "\"completion_verified\":%s,\"matched\":%u,\"unexpected\":%u,\"wire_trace_verified\":false}\n",
                sequence, payload_ok ? "true" : "false", complete ? "true" : "false", matched, unexpected);
        fflush(logfile);
        fprintf(stderr, "seq %u: ISO data %s, terminal completion %s, raw-count %u, events %u\n",
                sequence, payload_ok ? "PASS" : "FAIL", complete ? "PASS" : "FAIL",
                state.transferred, state.diagnostics.event_count);
        if (!payload_ok || !complete || interrupted) {
            fprintf(stderr, "Stopped; device URB is retained unless terminal was confirmed. Collect logs before --cancel.\n");
            goto cleanup;
        }
        /* A/C's trailing duplicate events must be drained before another TD. */
        pause_ms(50);
    }
    result = interrupted ? 130 : 0;
    goto cleanup;
fail:
    fprintf(stderr, "libusb: %s (%d)\n", libusb_error_name(rc), rc);
cleanup:
    if (transfer) libusb_free_transfer(transfer);
    free(buffer);
    if (claimed) libusb_release_interface(device, iface);
    if (config) libusb_free_config_descriptor(config);
    if (device) libusb_close(device);
    if (ctx) libusb_exit(ctx);
    fclose(logfile);
    return result;
}
