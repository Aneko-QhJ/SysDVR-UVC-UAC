#!/usr/bin/env python3
"""Build isolated ISO and rollback clients, verify NPDM IDs, package A/B/C."""
import hashlib
import argparse
import json
import shutil
import struct
import subprocess
import sys
from pathlib import Path
from build_patch import validate_module, read_mapped, BUILD_ID, SHA256

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
PROGRAM = 0x00ff0000a53bb666
PACKAGES = ROOT/'private/packages'


def runtime_payload(variant):
    nso = validate_module((ROOT/'private/module/exefs/main').read_bytes())
    package = PACKAGES/variant
    m = json.loads((package/'manifest.json').read_text())
    if m['build_id'] != BUILD_ID or m['original_sha256'] != SHA256:
        raise ValueError('runtime manifest target mismatch')
    ips = package/'atmosphere/exefs_patches/SysDVR-ISO'/(BUILD_ID+'.ips')
    if hashlib.sha256(ips.read_bytes()).hexdigest() != m['patch_sha256']:
        raise ValueError('runtime IPS hash mismatch')
    lines = ['/* Generated from validated private module and patch manifest. */',
             'static const unsigned char isoRuntimeBuildId[32] = {'+
             ','.join('0x'+BUILD_ID[i:i+2] for i in range(0,64,2))+'};']
    records = []
    for i, e in enumerate(m['edits']):
        address = int(e['address'],16)
        before, after = bytes.fromhex(e['before']), bytes.fromhex(e['after'])
        if before != read_mapped(nso,address,len(before)) or len(before)!=len(after) or len(before)>1024:
            raise ValueError('runtime original bytes/size mismatch')
        for label, data in [('before',before),('after',after)]:
            lines.append(f'static const unsigned char isoRuntime_{i}_{label}[] = {{'+
                         ','.join(str(x) for x in data)+'};')
        records.append(f'{{{address},{len(before)},isoRuntime_{i}_before,isoRuntime_{i}_after}}')
    lines.append('static const IsoRuntimeEdit isoRuntimeEdits[] = {'+','.join(records)+'};')
    (ROOT/'private/iso_runtime_payload.h').write_text('\n'.join(lines)+'\n')


def compatible_config():
    config = json.loads((REPO / 'sysmodule.json').read_text())
    for old, new in [('title_id', 'program_id'), ('title_id_range_min', 'program_id_range_min'),
                     ('title_id_range_max', 'program_id_range_max')]:
        config[new] = config[old]
    config.update(system_resource_size='0x0', version='0x0', optimize_memory_allocation=False,
                  disable_device_address_space_merge=False, enable_alias_region_extra_size=False,
                  prevent_code_reads=False, signature_key_generation=0)
    for cap in config['kernel_capabilities']:
        if cap['type'] == 'debug_flags': cap['value']['force_debug_prod'] = False
    return config


def verify_npdm(path):
    b = path.read_bytes()
    if b[:4] != b'META': raise ValueError('invalid NPDM')
    aci, acid = struct.unpack_from('<I', b, 0x70)[0], struct.unpack_from('<I', b, 0x78)[0]
    if b[aci:aci+4] != b'ACI0' or b[acid+0x200:acid+0x204] != b'ACID':
        raise ValueError('invalid NPDM sections')
    if struct.unpack_from('<Q', b, aci+0x10)[0] != PROGRAM or struct.unpack_from('<QQ', b, acid+0x210) != (PROGRAM, PROGRAM):
        raise ValueError('NPDM program ID/range mismatch')


def validate_revision(controller, revision, burst):
    audit = burst and controller.get('bounded_event_audit', False)
    publication = audit and controller.get('publication_mfi_snapshot', False)
    doorbell = publication and controller.get('doorbell_tail_mfi_snapshot', False)
    context = audit and controller.get('prepublication_context_snapshot', False)
    followup = controller.get('followup_sia', False)
    interval = controller.get('interval', 4)
    if (context != (revision in ('A21', 'A22', 'A23')) or doorbell != (revision == 'A20') or
            publication != (revision in ('A19', 'A20')) or followup != (revision in ('A22', 'A23')) or
            interval != (1 if revision == 'A23' else 4) or
            (revision == 'A23' and controller.get('diagnostics_magic') != 'ISO7')):
        raise ValueError('A19/A20/A21/A22/A23 revision and controller diagnostic/scheduling mismatch')
    return audit, publication, doorbell, context, followup


def main():
    global PACKAGES
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packages', type=Path, default=PACKAGES)
    parser.add_argument('--revision', default='A6')
    parser.add_argument('--burst', action='store_true', help='Package A13 A and rollback only')
    args = parser.parse_args()
    PACKAGES = args.packages.resolve()
    private = ROOT / 'private'
    config_path = private / 'sysmodule-iso.json'
    config_path.write_text(json.dumps(compatible_config(), indent=2) + '\n')
    logs = private / 'logs'; logs.mkdir(exist_ok=True)
    controller = json.loads((PACKAGES/'A/manifest.json').read_text())
    audit, publication, doorbell, context, followup = validate_revision(controller, args.revision, args.burst)
    interval = controller.get('interval', 4)
    layout = controller.get('diagnostics_magic', 'ISO3' if audit else 'ISO2' if args.burst else 'ISO1')
    host_packets = 960 if interval == 1 else 256
    audit_doc = 'INTERVAL_EXPERIMENT.md' if interval == 1 else 'FOLLOWUP_SIA.md' if followup else 'CONTEXT_AUDIT.md' if context else 'DOORBELL_AUDIT.md' if doorbell else 'PUBLICATION_AUDIT.md' if publication else 'EVENT_AUDIT.md'
    receiver = ROOT/('private/darwin-diag-A23-interval1' if interval == 1 else 'private/darwin-diag-A22-followup-sia' if followup else 'private/darwin-diag-A21-context-audit' if context else 'private/darwin-diag-A20-doorbell-audit' if doorbell else 'private/darwin-diag-A19-publication-audit' if publication else 'private/darwin-diag-A18-event-audit')
    if audit:
        subprocess.run([sys.executable, str(ROOT/'tools/build_event_audit_receiver.py'),
                        '--revision', 'A23' if interval == 1 else 'A22' if followup else 'A21' if context else 'A20' if doorbell else 'A19' if publication else 'A18', '--out', str(receiver)], check=True)
    else:
        subprocess.run(['make', '-C', str(ROOT / 'host')], check=True)
    for variant in (['A', 'rollback'] if args.burst else ['A', 'B', 'C', 'rollback']):
        if variant != 'rollback': runtime_payload(variant)
        target = 'exefs-rollback' if variant == 'rollback' else 'exefs-iso-'+variant
        build = 'build-rollback' if variant == 'rollback' else 'build-iso-'+variant
        defines = '' if variant == 'rollback' else '-DISO_PROBE -DISO_RUNTIME_PATCH -DFILE_LOGGING'
        if variant != 'rollback':
            mps = json.loads((PACKAGES/variant/'manifest.json').read_text()).get('mps',192)
            if mps not in (192,256): raise ValueError('unsupported experimental MPS')
            count = json.loads((PACKAGES/variant/'manifest.json').read_text()).get('burst_packets',1)
            if (count == 16) != args.burst: raise ValueError('burst client/controller mismatch')
            if args.burst: defines += ' -DISO_PROBE_BURST_MODE'
            if json.loads((PACKAGES/variant/'manifest.json').read_text()).get('bounded_event_audit'):
                defines += ' -DISO_PROBE_EVENT_AUDIT'
            if publication:
                defines += ' -DISO_PROBE_PUBLICATION_AUDIT'
            if doorbell:
                defines += ' -DISO_PROBE_DOORBELL_AUDIT'
            if context:
                defines += ' -DISO_PROBE_CONTEXT_AUDIT'
            if followup:
                defines += ' -DISO_PROBE_FOLLOWUP_SIA'
            if interval == 1:
                defines += ' -DISO_PROBE_INTERVAL_EXPERIMENT'
            defines += ' -DISO_PROBE_INTERVAL='+str(interval)
            defines += ' -DISO_PROBE_MPS='+str(mps)
        with (logs / (target + '-build.log')).open('w') as log:
            subprocess.run(['make', '-B', '-j4', 'TARGET='+target, 'BUILD='+build,
                            'CONFIG_JSON='+str(config_path.relative_to(REPO)), 'DEFINES='+defines,
                            'INCLUDES=include research/usb-ds-iso/private'],
                           cwd=REPO, stdout=log, stderr=subprocess.STDOUT, check=True)
        verify_npdm(REPO / (target + '.npdm'))
        package = PACKAGES / variant
        content = package / 'atmosphere/contents/00FF0000A53BB666'
        content.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / (target + '.nsp'), content / 'exefs.nsp')
        shutil.copyfile(REPO / 'toolbox.json', content / 'toolbox.json')
        shutil.copytree(REPO / 'flags', content / 'flags', dirs_exist_ok=True)
        if variant != 'rollback' and audit:
            for source, dest in [('iso-probe-native-diag','iso-probe-native-diag'),
                                 ('manifest.json','host-manifest.json'),('iso-probe.c','receiver-source.c'),
                                 ('iso_probe_protocol.h','iso_probe_protocol.h')]:
                shutil.copy2(receiver/source, package/dest)
            # Remove the generic tool if this directory was packaged earlier.
            # The controlled experiment uses the verified lead64 backend.
            (package/'iso-probe').unlink(missing_ok=True)
        elif variant != 'rollback':
            shutil.copy2(ROOT / 'host/iso-probe', package / 'iso-probe')
        manifest = {'variant': variant, 'sysmodule_sha256': hashlib.sha256((content/'exefs.nsp').read_bytes()).hexdigest(),
                    'program_id': f'{PROGRAM:016X}', 'revision': args.revision,
                    'runtime_patch': variant != 'rollback', 'controller_hardware_verified': False,
                    'iso_payload_verified': False, 'wire_trace_verified': False}
        install = ('Back up atmosphere/contents/00FF0000A53BB666 before copying.\n'
                   'Merge this package atmosphere directory into the SD card atmosphere directory.\n')
        if variant != 'rollback':
            manifest['frame_lead'] = json.loads((package/'manifest.json').read_text()).get('frame_lead', 0)
            manifest['retain_success'] = json.loads((package/'manifest.json').read_text()).get('retain_success', False)
            manifest['mps'] = mps
            manifest['burst_packets'] = count
            manifest['diagnostics_layout'] = layout
            manifest['followup_sia'] = followup
            manifest['interval'] = interval
        if variant != 'rollback':
            install += ('Use only ONE A/B/C patch and reboot after switching variants.\n'
                        'Client embeds the matching variant; replace BOTH client and IPS when switching.\n'
                        'At startup it validates the live usb Build ID and all original bytes, then installs/readbacks the same patch in RAM if IPS was not loaded.\n'
                        'Remove this client and reboot to remove runtime writes; NAND is unchanged.\n'
                        'Move overlapping older patches for the same usb Build ID out of exefs_patches first.\n'
                        'Keep the JSONL and SD /logfile.txt. Hardware ISO support is UNVERIFIED.\n'
                        'Full instructions: research/usb-ds-iso/README.md in the project.\n')
            if audit:
                install += (f'{args.revision} {layout} audit: fresh boot, USB2/HS, video closed. SINGLE burst ONLY.\n'
                            f'(set -C; ./iso-probe-native-diag --burst --packets {host_packets} --trigger-delay-ms 40 --log {args.revision}-001.jsonl 2>{args.revision}-001-native.log)\n'
                            f'python3 ./summarize_run.py {args.revision}-001.jsonl --out {args.revision}-001-summary.json\n'
                            'Exit0/public success do not prove native status0; independently check all16 payload slots in the native log.\n'
                            'Host lead64/request192/backend are frozen; device lead32/MPS256/16TD remain unchanged.\n'
                            'On the first failure preserve native/JSONL/raw/STATUS; do not repost.\n'
                            'Cancel only a pending/retained device URB, without --burst; collect Switch logfile.txt.\n'
                            f'See the included {audit_doc} for validity and snapshot priority.\n')
                host = json.loads((package/'host-manifest.json').read_text())
                experiment = dict(device_revision=args.revision, variant=variant,
                    baseline='A17 deferred-log with request192 host64 timing receiver',
                    diagnostics_layout=layout, device_frame_lead=32, device_mps=256,
                    burst_packets=16, payload_bytes=192, host_frame_lead=64,
                    requested_bytes=192, trigger_delay_ms=40, packets=host_packets, repeats=1,
                    video_closed=True, fresh_boot=True, required_speed='HS',
                    receiver_sha256=host['receiver_sha256'],
                    static_library_sha256=host['static_library_sha256'],
                    controller_patch_sha256=json.loads((package/'manifest.json').read_text())['patch_sha256'],
                    sysmodule_sha256=manifest['sysmodule_sha256'],
                    hardware_verified=False, wire_trace_verified=False,
                    on_failure='preserve raw/native/JSONL/STATUS, no repost; cancel only if pending or retained',
                    acceptance='16 consecutive ordered packets, exact192 and native/public status0, overall0; '
                               'own URB status3/requested=transferred3072 and terminal1/bitmapFFFF/actual3072; '
                               f'verify Switch {args.revision} install and collect timing/logs')
                if publication:
                    experiment.update(baseline='A18 scheduling and frozen A17 host64-timing receiver',
                        diagnostic_acceptance='ISO4 phase_valid1 and frame_select_mfi/first FrameID relation consistent; '
                                              'retain the three software anchors and first-two ED samples; '
                                              'anchors do not timestamp the doorbell MMIO write',
                        filtered_event_sampling=False, post_terminal_event_sampling=False)
                    if doorbell:
                        experiment.update(baseline='A19 scheduling and frozen A17 host64-timing receiver',
                            diagnostic_acceptance='ISO5 doorbell_marker0x700 and frame_select_mfi/first FrameID relation consistent; '
                                'MFI reads bracket the original tail, including its original MMIO store, and are not a hardware acceptance timestamp')
                        install += 'ISO5 anchors: require doorbell_marker0x700 and header consistency; original tail return and MMIO write are preserved.\n'
                    else:
                        install += 'ISO4 anchors: require phase_valid1 and header consistency in summary; reserved bytes are ignored.\n'
                if context:
                    experiment.update(baseline='A20 evidence; unchanged scheduling and frozen A17 receiver',
                        diagnostic_acceptance='ISO6 context_valid1 and selection/first-control consistency; '
                            'capture EP7 context words before first-cycle publication without modifying them; '
                            'snapshot is not atomic and does not verify wire DATA PID',
                        filtered_event_sampling=False, post_terminal_event_sampling=False,
                        prepublication_context_snapshot=True)
                    install += f'{layout} context: require context_valid1 and header consistency; raw words remain evidence even if configured fields mismatch.\n'
                if followup:
                    experiment.update(baseline='A21 ISO6 context audit and identical A21 host receiver',
                        followup_sia=True,
                        scheduling_policy='TD0 explicit FrameID lead32; TD1..15 SIA1 and FrameID0',
                        changed_variable='following 15 TD scheduling policy only',
                        revision_identity='ISO6 alone does not identify A22; verify installed NSP/IPS hashes and Switch A22 startup marker')
                    install += ('Scheduling: TD0 explicit lead32, remaining15 TDs SIA1/FrameID0.\n'
                                f'Require installed pair hashes and Switch {args.revision} startup marker.\n')
                if interval == 1:
                    experiment.update(baseline='A22 first-explicit/followup-SIA, HS bInterval4',
                        interval=1, service_interval_microframes=1, nominal_capture_window_ms=120,
                        nominal_host_slots_per_frame=8,
                        changed_variable='HS service interval bInterval4 to bInterval1; host window256 to960 slots to preserve sufficient time coverage',
                        revision_identity='ISO7 expected; collect Switch A23 startup marker and verify installed NSP/IPS pair',
                        receiver_changes='ISO7 compatibility, bInterval1 descriptor guard, CLI packet limit960; schedule/callback/backend unchanged',
                        diagnostic_acceptance='ISO7 context_valid1 and selection/first-control consistency; configured interval1/MPS256; context remains read-only/non-atomic')
                    install += ('A23 bInterval1: 125us service opportunity; require960 slots covering120ms (256 slots cover only32ms).\n'
                                'Host lead64 frames/wait40ms/request192 and TD0 explicit lead32/TD1..15 SIA remain frozen; window size is a documented measurement change.\n'
                                'Use eight nominal packet slots per frame in FrameID comparisons; require ISO7 and A23 startup log.\n')
                (package/'experiment.json').write_text(json.dumps(experiment,indent=2)+'\n')
                shutil.copy2(ROOT/audit_doc, package/audit_doc)
                shutil.copy2(ROOT/'tools/summarize_run.py', package/'summarize_run.py')
            elif args.burst:
                install += ('A13 HS ONLY: use ./iso-probe --burst --packets 128 --log A13-burst-001.jsonl\n'
                            'One URB contains 16 independent 1ms TDs; this is NOT sustained streaming.\n')
            else:
                install += 'On this Mac: ./iso-probe --log '+variant+'-001.jsonl\n'
        else:
            install += ('Before reboot, REMOVE atmosphere/exefs_patches/SysDVR-ISO from the SD loading directory.\n'
                        'Copying this rollback package does not remove an installed patch.\n')
        (package / 'INSTALL.txt').write_text(install)
        (package / 'client-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
        shutil.make_archive(str(PACKAGES / ('SysDVR-ISO-'+variant)), 'zip', package)
        print(package)


if __name__ == '__main__': main()
