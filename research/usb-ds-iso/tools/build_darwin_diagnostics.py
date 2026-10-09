#!/usr/bin/env python3
"""Build an isolated libusb 1.0.30 receiver exposing native ISO evidence.

Download the official v1.0.30 codeload archive to private/libusb-v1.0.30.tar.gz.
Does not install or replace Homebrew libusb. Original overall status is kept.
"""
import argparse
import hashlib
import json
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHA256 = '2ae28adb0bb9558c86135c4e1c11b320b0805461e207a64a6e520a114094bf07'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host-frame-lead',type=int,choices=(4,32,64),default=4)
    parser.add_argument('--out',type=Path,default=ROOT/'private/darwin-diag')
    args = parser.parse_args()
    private = ROOT/'private'
    archive = private/'libusb-v1.0.30.tar.gz'
    if hashlib.sha256(archive.read_bytes()).hexdigest() != SHA256:
        raise ValueError('official source archive hash mismatch')
    build = args.out.resolve()
    build.mkdir(parents=True,exist_ok=True)
    with tarfile.open(archive) as tar:
        for member in tar.getmembers():
            path = Path(member.name)
            if path.is_absolute() or '..' in path.parts:
                raise ValueError('unexpected archive path/link')
        tar.extractall(build, filter='data')
    source = build/'libusb-1.0.30'
    backend = source/'libusb/os/darwin_usb.c'
    text = backend.read_text()
    original_hash = hashlib.sha256(backend.read_bytes()).hexdigest()
    anchor = '  if (kIOReturnSuccess == tpriv->result || kIOReturnUnderrun == tpriv->result || kIOUSBTransactionTimeout == tpriv->result) {'
    if text.count(anchor) != 1:
        raise ValueError('Darwin completion source mismatch')
    diagnostic = '''  /* Local experiment only: retain native results even on overall errors.
   * Preserve overall status, cancellation and kernel results; scheduling lead is explicitly logged. */
  if (is_isoc && tpriv->isoc_framelist) {
    unsigned native_count = transfer->num_iso_packets < 1024 ? transfer->num_iso_packets : 1024;
    for (unsigned i = 0; i < native_count; ++i) {
      fprintf(stderr, "{\\"kind\\":\\"darwin_iso_native\\",\\"index\\":%u,\\"overall\\":%u,\\"status\\":%u,\\"requested\\":%u,\\"actual\\":%u}\\n",
              i, (unsigned)tpriv->result, (unsigned)tpriv->isoc_framelist[i].frStatus,
              (unsigned)tpriv->isoc_framelist[i].frReqCount, (unsigned)tpriv->isoc_framelist[i].frActCount);
    }
    if (kIOReturnSuccess != tpriv->result && kIOReturnUnderrun != tpriv->result && kIOUSBTransactionTimeout != tpriv->result) {
      for (int i = 0; i < transfer->num_iso_packets; ++i) {
        transfer->iso_packet_desc[i].status = darwin_transfer_status(itransfer, tpriv->isoc_framelist[i].frStatus);
        transfer->iso_packet_desc[i].actual_length = tpriv->isoc_framelist[i].frActCount;
      }
    }
  }
'''
    backend.write_text(text.replace(anchor, diagnostic+anchor))
    text = backend.read_text()
    schedule_anchor = '  /* submit the request */\n  if (IS_XFERIN(transfer))\n    kresult = (*IOINTERFACE(cInterface))->ReadIsochPipeAsync'
    if text.count(schedule_anchor) != 1:
        raise ValueError('Darwin ISO schedule source mismatch')
    frame_anchor = '  frame += 4;'
    if text.count(frame_anchor) != 1:
        raise ValueError('Darwin frame lead source mismatch')
    text = text.replace(frame_anchor, f'  UInt64 queried_frame = frame;\n  frame += {args.host_frame_lead};')
    schedule = '''  fprintf(stderr, "{\\"kind\\":\\"darwin_iso_schedule\\",\\"frame_start\\":%llu,\\"queried_frame\\":%llu,\\"configured_lead_frames\\":%u,\\"packets\\":%d,\\"interval\\":%u,\\"speed\\":%d}\\n",
          (unsigned long long)frame, (unsigned long long)queried_frame, HOST_FRAME_LEAD, transfer->num_iso_packets,
          (unsigned)pipe_properties.interval, transfer->dev_handle->dev->speed);
'''
    backend.write_text(text.replace(schedule_anchor, schedule.replace('HOST_FRAME_LEAD',str(args.host_frame_lead))+schedule_anchor))
    log = build/'build.log'
    with log.open('w') as output:
        for command in (['glibtoolize','--force','--copy'], ['autoreconf','-fi'],
                        ['./configure','--disable-shared','--enable-static'], ['make','-j4']):
            subprocess.run(command, cwd=source, stdout=output, stderr=subprocess.STDOUT, check=True)
        subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror',
                        '-DISO_NATIVE_DIAGNOSTICS','-I'+str(source/'libusb'),
                        str(ROOT/'host/iso-probe.c'), str(source/'libusb/.libs/libusb-1.0.a'),
                        '-framework','IOKit','-framework','CoreFoundation','-framework','Security','-lobjc',
                        '-o',str(build/'iso-probe-native-diag')], stdout=output, stderr=subprocess.STDOUT, check=True)
    manifest = {'source':'https://codeload.github.com/libusb/libusb/tar.gz/refs/tags/v1.0.30',
                'archive_sha256':SHA256,'backend_before_sha256':original_hash,
                'backend_after_sha256':hashlib.sha256(backend.read_bytes()).hexdigest(),
                'receiver_sha256':hashlib.sha256((build/'iso-probe-native-diag').read_bytes()).hexdigest(),
                'host_frame_lead':args.host_frame_lead,
                'homebrew_library_replaced':False,'overall_status_modified':False}
    (build/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(build/'iso-probe-native-diag')


if __name__ == '__main__': main()
