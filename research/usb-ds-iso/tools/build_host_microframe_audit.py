#!/usr/bin/env python3
"""Build isolated A23 host microframe audit; preserve frozen A23 artifacts."""
import hashlib,json,shutil,subprocess,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'private'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
HELPER=r'''/* Read-only host observation; query failure does not change transfer status. */
static void iso_host_microframe(usb_device_t device, const char *stage) {
  UInt64 microframe = 0;
  AbsoluteTime at_time = {0};
  uint64_t before = mach_absolute_time();
  IOReturn result = (*device)->GetBusMicroFrameNumber(device, &microframe, &at_time);
  uint64_t after = mach_absolute_time();
  mach_timebase_info_data_t timebase;
  mach_timebase_info(&timebase);
  fprintf(stderr, "{\"kind\":\"darwin_microframe_observation\",\"stage\":\"%s\",\"result\":%u,\"valid\":%s,\"microframe\":%llu,\"at_time_ticks\":%llu,\"before_ticks\":%llu,\"after_ticks\":%llu,\"timebase_numer\":%u,\"timebase_denom\":%u}\n",
          stage, (unsigned)result, result == kIOReturnSuccess ? "true" : "false",
          (unsigned long long)microframe, (unsigned long long)(((UInt64)at_time.hi << 32) | at_time.lo),
          (unsigned long long)before, (unsigned long long)after, timebase.numer, timebase.denom);
}

'''
CHANGES=[
('static int submit_iso_transfer(struct usbi_transfer *itransfer) {',HELPER+'static int submit_iso_transfer(struct usbi_transfer *itransfer) {'),
('  /* submit the request */\n  if (IS_XFERIN(transfer))\n    kresult = (*IOINTERFACE(cInterface))->ReadIsochPipeAsync',
 '  iso_host_microframe(DARWIN_CACHED_DEVICE(transfer->dev_handle->dev)->device, "iso_before_queue");\n  /* submit the request */\n  if (IS_XFERIN(transfer))\n    kresult = (*IOINTERFACE(cInterface))->ReadIsochPipeAsync'),
('  if (LIBUSB_SPEED_FULL == transfer->dev_handle->dev->speed)\n    /* Full speed */',
 '  iso_host_microframe(DARWIN_CACHED_DEVICE(transfer->dev_handle->dev)->device, "iso_after_queue");\n  if (LIBUSB_SPEED_FULL == transfer->dev_handle->dev->speed)\n    /* Full speed */'),
('  /* all transfers in libusb-1.0 are async */\n',
 '  /* Only the experiment burst request, never STATUS/preflight/other controls. */\n  const bool observe_burst = !transfer->endpoint && setup->bmRequestType == 0x41 && setup->bRequest == 0x54;\n  if (observe_burst) iso_host_microframe(dpriv->device, "burst_before_queue");\n  /* all transfers in libusb-1.0 are async */\n'),
('  if (kresult != kIOReturnSuccess)\n    usbi_err (TRANSFER_CTX (transfer), "control request failed: %s", darwin_error_str(kresult));',
 '  if (observe_burst) iso_host_microframe(dpriv->device, "burst_after_queue");\n  if (kresult != kIOReturnSuccess)\n    usbi_err (TRANSFER_CTX (transfer), "control request failed: %s", darwin_error_str(kresult));')]
def patch(original):
    text=original
    for before,after in CHANGES:
        assert text.count(before)==1,'frozen backend anchor mismatch'
        text=text.replace(before,after)
    inverse=text
    for before,after in reversed(CHANGES):
        assert inverse.count(after)==1
        inverse=inverse.replace(after,before)
    assert inverse==original,'non-observation backend change'
    return text

def main():
    frozen=P/'darwin-diag-host64/libusb-1.0.30/libusb/os/darwin_usb.c'
    assert sha(frozen)=='a6f70f2f606310cac6a3c43f8acf1a44f4610506b074b92bde6de98d9a38de9d'
    archive=P/'libusb-v1.0.30.tar.gz'
    assert sha(archive)=='2ae28adb0bb9558c86135c4e1c11b320b0805461e207a64a6e520a114094bf07'
    out=P/'host-A23-microframe-audit'
    out.mkdir(exist_ok=False)
    with tarfile.open(archive) as tar:tar.extractall(out,filter='data')
    src=out/'libusb-1.0.30'; backend=src/'libusb/os/darwin_usb.c'
    backend.write_text(patch(frozen.read_text()))
    A=P/'packages-A23-interval1/A'
    for name in ['receiver-source.c','iso_probe_protocol.h','summarize_run.py']:shutil.copyfile(A/name,out/name)
    assert sha(out/'receiver-source.c')==json.loads((A/'host-manifest.json').read_text())['receiver_source_sha256']
    library=src/'libusb/.libs/libusb-1.0.a'
    commands=[['glibtoolize','--force','--copy'],['autoreconf','-fi'],['./configure','--disable-shared','--enable-static'],['make','-j4']]
    with (out/'build.log').open('w') as log:
        for cmd in commands:subprocess.run(cmd,cwd=src,stdout=log,stderr=subprocess.STDOUT,check=True)
        cc=['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-DISO_NATIVE_DIAGNOSTICS','-I'+str(src/'libusb'),'-I'+str(out),str(out/'receiver-source.c'),str(library),'-framework','IOKit','-framework','CoreFoundation','-framework','Security','-lobjc','-o',str(out/'iso-probe-native-diag')]
        subprocess.run(cc,stdout=log,stderr=subprocess.STDOUT,check=True)
    manifest=dict(device_revision='A23',host_revision='microframe-audit-1',hardware_verified=False,receiver_source_sha256=sha(out/'receiver-source.c'),protocol_header_sha256=sha(out/'iso_probe_protocol.h'),backend_before_sha256=sha(frozen),backend_after_sha256=sha(backend),static_library_sha256=sha(library),receiver_sha256=sha(out/'iso-probe-native-diag'),archive_sha256=sha(archive),host_frame_lead=64,requested_bytes=192,trigger_delay_ms=40,packets=960,repeats=1,expected_interval=1,overall_status_modified=False,homebrew_library_replaced=False,backend_inverse_patch_matches_frozen=True,observations=['iso_before_queue','iso_after_queue','burst_before_queue','burst_after_queue'],observation_failure_changes_transfer_result=False,query_timestamp_sdk_accuracy_ms=1,queue_observations_are_not_completion_or_wire_times=True,build_commands=commands+[cc])
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(out)
if __name__=='__main__':main()
