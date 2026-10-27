#!/usr/bin/env python3
"""Build an isolated, fresh-idle-only A23 no-TD receiver; never accesses USB."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / 'private'
OUT = PRIVATE / 'host-A23-no-td-window'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_once(text, old, new):
    assert text.count(old) == 1, old[:100]
    return text.replace(old, new)


def receiver_patch(text):
    text = replace_once(text, 'static bool done, payload_ok, burst_mode;',
                        'static bool done, payload_ok, burst_mode, baseline_callback_ok;')
    text = replace_once(text, '    if (!outpath) {', '''    if (!receive_only || empty_window || cancel_only || frame_only || burst_mode ||
        repeats != 1 || packets != 960 || trigger_delay_ms != 40) {
        fprintf(stderr, "No-TD diagnostic requires --receive-only --packets 960 --trigger-delay-ms 40; one fresh window only\\n");
        return 2;
    }
    if (!outpath) {''')
    text = replace_once(text, 'speed != LIBUSB_SPEED_HIGH && speed != LIBUSB_SPEED_SUPER',
                        'speed != LIBUSB_SPEED_HIGH')
    text = replace_once(text, '(ep->wMaxPacketSize != 192 && ep->wMaxPacketSize != 256)',
                        'ep->wMaxPacketSize != 256')
    text = replace_once(text, '    payload_ok = payload_ok && native_pass && saved;',
                        '    baseline_callback_ok = native_pass && saved && nonzero == 0 && transfer->status == LIBUSB_TRANSFER_COMPLETED;\n    payload_ok = payload_ok && native_pass && saved;')
    text = text.replace('native_serial_gate', 'native_empty_gate')
    text = replace_once(text, '        sequence = 0; done = payload_ok = false;',
                        '        sequence = 0; done = payload_ok = baseline_callback_ok = false;')
    old = '''        rc = libusb_submit_transfer(transfer);
        if (rc) { done = true; goto fail; }
        double deadline = now() + 3.0;'''
    new = r'''        double submit_before = now();
        rc = libusb_submit_transfer(transfer);
        double submit_after = now();
        if (rc) { done = true; goto fail; }
        pause_ms(trigger_delay_ms);
        double pump_before = now();
        fprintf(logfile, "{\"kind\":\"no_td_window_timing\",\"submit_before\":%.9f,\"submit_after\":%.9f,\"pump_before\":%.9f,\"requested_wait_ms\":%u,\"actual_wait_ms\":%.6f,\"burst_control_sent\":false}\n",
                submit_before, submit_after, pump_before, trigger_delay_ms, (pump_before-submit_after)*1000);
        fflush(logfile);
        double deadline = now() + 3.0;'''
    text = replace_once(text, old, new)
    text = replace_once(text, 'result = !interrupted && unchanged && nonzero == 0 ? 0 : 1;',
                        'result = !interrupted && unchanged && nonzero == 0 && done && !cancelled && baseline_callback_ok ? 0 : 1;')
    # All future control calls are restricted at runtime too, including dead CLI branches.
    text = replace_once(text, 'static volatile sig_atomic_t interrupted;', r'''static int no_td_control(libusb_device_handle *device, uint8_t type, uint8_t request,
                         uint16_t value, uint16_t index, unsigned char *data,
                         uint16_t length, unsigned timeout) {
    if (type != 0xc1 || request != ISO_PROBE_STATUS || value != 0 || index != 2 ||
        length != sizeof(IsoProbeStatus)) return LIBUSB_ERROR_NOT_SUPPORTED;
    return libusb_control_transfer(device, type, request, value, index, data, length, timeout);
}
#undef libusb_control_transfer
#define libusb_control_transfer no_td_control
static volatile sig_atomic_t interrupted;''')
    return text


def guard_patch(text):
    text = text.replace('if (overall || requested!=192',
                        'if ((overall && overall!=0xe00002e7u) || (status && status!=0xe00002e7u) || requested!=192')
    text = replace_once(text, '*payloads==16', '*payloads==0')
    return text


def backend_patch(text):
    text = replace_once(text, 'static int submit_iso_transfer(struct usbi_transfer *itransfer) {', '''static uint64_t iso_diag_ns(void) {
  struct timespec value;
  usbi_get_monotonic_time(&value);
  return (uint64_t)value.tv_sec * 1000000000ULL + (uint64_t)value.tv_nsec;
}

static int submit_iso_transfer(struct usbi_transfer *itransfer) {''')
    text = replace_once(text, '  kresult = (*IOINTERFACE(cInterface))->GetBusFrameNumber(IOINTERFACE(cInterface), &frame, &atTime);', '''  tpriv->diag_frame_before = iso_diag_ns();
  kresult = (*IOINTERFACE(cInterface))->GetBusFrameNumber(IOINTERFACE(cInterface), &frame, &atTime);
  tpriv->diag_frame_after = iso_diag_ns();''')
    text = replace_once(text, '  /* submit the request */\n  if (IS_XFERIN(transfer))',
                        '  /* submit the request */\n  tpriv->diag_queue_before = iso_diag_ns();\n  if (IS_XFERIN(transfer))')
    text = replace_once(text, '  iso_host_microframe(DARWIN_CACHED_DEVICE(transfer->dev_handle->dev)->device, "iso_after_queue");', '''  tpriv->diag_queue_after = iso_diag_ns();
  tpriv->diag_queue_result = kresult;
  iso_host_microframe(DARWIN_CACHED_DEVICE(transfer->dev_handle->dev)->device, "iso_after_queue");''')
    text = replace_once(text, 'static void darwin_async_io_callback (void *refcon, IOReturn result, void *arg0) {',
                        'static void darwin_async_io_callback (void *refcon, IOReturn result, void *arg0) {\n  uint64_t callback_entry_ns = iso_diag_ns();')
    text = replace_once(text, '  tpriv->result = result;',
                        '  tpriv->diag_callback_entry = callback_entry_ns;\n  tpriv->result = result;')
    text = replace_once(text, '  if (is_isoc && tpriv->isoc_framelist) {', r'''  if (is_isoc && tpriv->isoc_framelist) {
    fprintf(stderr, "{\"kind\":\"darwin_iso_queue_timing\",\"clock\":\"CLOCK_MONOTONIC\",\"frame_before_ns\":%llu,\"frame_after_ns\":%llu,\"queue_before_ns\":%llu,\"queue_after_ns\":%llu,\"queue_result\":%u,\"callback_entry_ns\":%llu,\"overall\":%u}\n",
            (unsigned long long)tpriv->diag_frame_before, (unsigned long long)tpriv->diag_frame_after,
            (unsigned long long)tpriv->diag_queue_before, (unsigned long long)tpriv->diag_queue_after,
            (unsigned)tpriv->diag_queue_result, (unsigned long long)tpriv->diag_callback_entry,
            (unsigned)tpriv->result);''') if text.count('  if (is_isoc && tpriv->isoc_framelist) {') == 1 else text.replace(
            '  if (is_isoc && tpriv->isoc_framelist) {\n    unsigned native_count', r'''  if (is_isoc && tpriv->isoc_framelist) {
    fprintf(stderr, "{\"kind\":\"darwin_iso_queue_timing\",\"clock\":\"CLOCK_MONOTONIC\",\"frame_before_ns\":%llu,\"frame_after_ns\":%llu,\"queue_before_ns\":%llu,\"queue_after_ns\":%llu,\"queue_result\":%u,\"callback_entry_ns\":%llu,\"overall\":%u}\n",
            (unsigned long long)tpriv->diag_frame_before, (unsigned long long)tpriv->diag_frame_after,
            (unsigned long long)tpriv->diag_queue_before, (unsigned long long)tpriv->diag_queue_after,
            (unsigned)tpriv->diag_queue_result, (unsigned long long)tpriv->diag_callback_entry,
            (unsigned)tpriv->result);
    unsigned native_count''', 1)
    assert text.count('darwin_iso_queue_timing') == 1
    return text


def main():
    reference = PRIVATE / 'host-A23-native-guard-serial'
    meta = json.loads((reference / 'manifest.json').read_text())
    lib = Path(meta['library'])
    assert sha(reference / 'receiver-source.c') == meta['receiver_source_sha256']
    assert sha(lib) == meta['static_library_sha256']
    original_backend = lib.parent.parent / 'os/darwin_usb.c'
    assert sha(original_backend) == meta['backend_after_sha256']
    OUT.mkdir(exist_ok=False)
    tree = OUT / 'libusb-1.0.30'
    shutil.copytree(lib.parents[2], tree, symlinks=True)
    backend = tree / 'libusb/os/darwin_usb.c'
    backend.write_text(backend_patch(backend.read_text()))
    header = tree / 'libusb/os/darwin_usb.h'
    header.write_text(replace_once(header.read_text(), '  /* Isoc */', '''  uint64_t diag_frame_before, diag_frame_after, diag_queue_before, diag_queue_after, diag_callback_entry;
  IOReturn diag_queue_result;
  /* Isoc */'''))
    (OUT / 'receiver-source.c').write_text(receiver_patch((reference / 'receiver-source.c').read_text()))
    (OUT / 'native_file_guard.h').write_text(guard_patch((reference / 'native_file_guard.h').read_text()))
    shutil.copyfile(reference / 'iso_probe_protocol.h', OUT / 'iso_probe_protocol.h')
    preflight = PRIVATE / 'runs/A-A23-host-microframe-20261008-015927/preflight.c'
    shutil.copyfile(preflight, OUT / 'preflight.c')
    with (OUT / 'backend-build.log').open('x') as log:
        subprocess.run(['make', '-C', str(tree / 'libusb'), '-j4'], stdout=log, stderr=subprocess.STDOUT, check=True)
    newlib = tree / 'libusb/.libs/libusb-1.0.a'
    base = ['cc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-DISO_NATIVE_DIAGNOSTICS',
            '-I' + str(tree / 'libusb'), '-I' + str(OUT)]
    commands = []
    for src, target in [('receiver-source.c', 'iso-probe-no-td'), ('preflight.c', 'preflight')]:
        cmd = base + [str(OUT / src), str(newlib), '-framework', 'IOKit', '-framework', 'CoreFoundation',
                      '-framework', 'Security', '-lobjc', '-o', str(OUT / target)]
        commands.append(cmd)
        with (OUT / (target + '-build.log')).open('x') as log:
            subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=True)
    meta = dict(device_revision='A23', host_revision='no-td-window-1', device_code_changed=False,
                fresh_idle_required=True, only_status_control_allowed=True, repeats=1, packets=960,
                host_frame_lead=64, requested_bytes=192, wait_ms=40, interval=1, mps=256,
                native_errors_preserved=True, timestamps_deferred_until_completion=True,
                timing_observation_can_perturb=True, hardware_verified=False, validation_passed=False,
                reference_source_sha256=sha(reference / 'receiver-source.c'),
                reference_backend_sha256=sha(original_backend), build_commands=commands,
                receiver_sha256=sha(OUT / 'iso-probe-no-td'), receiver_source_sha256=sha(OUT / 'receiver-source.c'),
                static_library_sha256=sha(newlib), library=str(newlib),
                backend_sha256=sha(backend), protocol_header_sha256=sha(OUT / 'iso_probe_protocol.h'))
    (OUT / 'manifest.json').write_text(json.dumps(meta, indent=2) + '\n')
    print(OUT)


if __name__ == '__main__':
    main()
