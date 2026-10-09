#!/usr/bin/env python3
"""Build audit compatibility using the frozen A17 host64 timing receiver.

Preserves its request192/lead64 schedule, callback, timing and cancellation.
Reuses the verified static backend; never installs/replaces a system library.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
SOURCE_HASH = '5d3fea2caa73b70e09ea0f41d62a2a3ee2d73a20547952a3edb6d3e142e3da82'
LIBRARY_HASH = 'b4f39ceba401c90f5ffe48d938a358a927b391edccab297a5b9c73e415298627'
BACKEND_HASH = 'a6f70f2f606310cac6a3c43f8acf1a44f4610506b074b92bde6de98d9a38de9d'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT/'private/darwin-diag-A18-event-audit')
    parser.add_argument('--revision', choices=('A18', 'A19', 'A20', 'A21', 'A22', 'A23'), default='A18')
    args = parser.parse_args()
    frozen = ROOT/'private/darwin-diag-host64-timing'
    backend = ROOT/'private/darwin-diag-host64/libusb-1.0.30/libusb'
    library = backend/'.libs/libusb-1.0.a'
    old_manifest = json.loads((frozen/'manifest.json').read_text())
    if (sha(frozen/'iso-probe.c') != SOURCE_HASH or sha(library) != LIBRARY_HASH or
            sha(backend/'os/darwin_usb.c') != BACKEND_HASH or
            old_manifest.get('receiver_source_sha256') != SOURCE_HASH or
            old_manifest.get('static_library_sha256') != LIBRARY_HASH or
            old_manifest.get('host_frame_lead') != 64):
        raise ValueError('frozen source/backend provenance mismatch')
    source = (frozen/'iso-probe.c').read_text()
    changes = {
        '#include "../../../source/uvc/iso_probe_protocol.h"': '#include "iso_probe_protocol.h"',
        '(state.diagnostics.magic == ISO_PROBE_DIAG_MAGIC || state.diagnostics.magic == ISO_PROBE_BURST_DIAG_MAGIC)':
            '(state.diagnostics.magic == ISO_PROBE_DIAG_MAGIC || isoProbeIsBurstDiagnostics(state.diagnostics.magic))',
        'state.diagnostics.magic == (burst_mode ? ISO_PROBE_BURST_DIAG_MAGIC : ISO_PROBE_DIAG_MAGIC)':
            '(burst_mode ? isoProbeIsBurstDiagnostics(state.diagnostics.magic) : state.diagnostics.magic == ISO_PROBE_DIAG_MAGIC)',
    }
    if args.revision == 'A23':
        changes['ep->bInterval != 4'] = 'ep->bInterval != 1'
        changes['n < 64 || n > 512'] = 'n < 64 || n > 960'
        changes['packets must be 64..512'] = 'packets must be 64..960'
        changes['[--packets 64..512]'] = '[--packets 64..960]'
    for before, after in changes.items():
        if source.count(before) != 1:
            raise ValueError('frozen receiver compatibility anchor mismatch')
        source = source.replace(before, after)
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    receiver_source = out/'iso-probe.c'
    receiver_source.write_text(source)
    shutil.copyfile(REPO/'source/uvc/iso_probe_protocol.h', out/'iso_probe_protocol.h')
    # Keep earlier receivers' policies after the shared header adds layouts.
    header = (out/'iso_probe_protocol.h').read_text()
    for magic, excluded in [('INTERVAL', args.revision != 'A23'),
                            ('CONTEXT', args.revision not in ('A21', 'A22', 'A23')),
                            ('DOORBELL', args.revision not in ('A20', 'A21', 'A22', 'A23')),
                            ('PUBLICATION', args.revision == 'A18')]:
        if excluded:
            anchor = ' ||\n           magic == ISO_PROBE_BURST_'+magic+'_MAGIC'
            if header.count(anchor) != 1:
                raise ValueError('receiver protocol policy anchor mismatch')
            header = header.replace(anchor, '')
    (out/'iso_probe_protocol.h').write_text(header)
    receiver = out/'iso-probe-native-diag'
    command = ['cc','-std=c11','-O2','-Wall','-Wextra','-Werror',
               '-DISO_NATIVE_DIAGNOSTICS','-I'+str(backend),str(receiver_source),str(library),
               '-framework','IOKit','-framework','CoreFoundation','-framework','Security','-lobjc',
               '-o',str(receiver)]
    with (out/'build.log').open('w') as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
    manifest = dict(old_manifest)
    manifest.update(device_revision=args.revision,
                    diagnostics_layouts=['ISO1','ISO2','ISO3'] + (['ISO4'] if args.revision != 'A18' else []) + (['ISO5'] if args.revision in ('A20', 'A21', 'A22', 'A23') else []) + (['ISO6'] if args.revision in ('A21', 'A22', 'A23') else []) + (['ISO7'] if args.revision == 'A23' else []),
                    frozen_receiver_source_sha256=SOURCE_HASH, receiver_source_sha256=sha(receiver_source),
                    protocol_header_sha256=sha(out/'iso_probe_protocol.h'), receiver_sha256=sha(receiver),
                    static_library_sha256=LIBRARY_HASH, backend_after_sha256=BACKEND_HASH,
                    requested_bytes=192, trigger_delay_ms=40, packets=960 if args.revision == 'A23' else 256, repeats=1,
                    expected_interval=1 if args.revision == 'A23' else 4,
                    service_interval_microframes=1 if args.revision == 'A23' else 8,
                    nominal_capture_window_ms=120 if args.revision == 'A23' else 256,
                    receiver_changes=[('ISO3/ISO4/ISO5/ISO6/ISO7' if args.revision == 'A23' else 'ISO3/ISO4/ISO5/ISO6' if args.revision in ('A21', 'A22') else 'ISO3/ISO4/ISO5' if args.revision == 'A20' else 'ISO3/ISO4' if args.revision == 'A19' else 'ISO3')+' completion/empty-window magic compatibility','local header include path'] + (['descriptor guard requires bInterval1', 'packet limit/help 512 to960 for sufficient interval1 coverage'] if args.revision == 'A23' else []),
                    homebrew_library_replaced=False, overall_status_modified=False,
                    hardware_verified=False, build_command=command)
    (out/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(receiver)


if __name__ == '__main__':
    main()
