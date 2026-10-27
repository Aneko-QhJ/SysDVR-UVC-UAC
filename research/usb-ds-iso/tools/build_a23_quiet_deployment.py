#!/usr/bin/env python3
"""Prepare a file-only quiet deployment review. Never accesses a card or USB device."""
import argparse
import json
from pathlib import Path
import re
import struct
import subprocess

import a23_quiet_device_binding as device
import build_a23_quiet_receiver as common
import build_patch
from analyze_a23_elf_boundaries import elf_metadata
from analyze_ep0_execution_v3 import decode_execution
from nso2elf import Nso
from workflows.artifacts import verify

ROOT = common.ROOT
ANALYSIS = ROOT / 'private/analysis'
BASE = ROOT / 'private/packages-A23-interval1/A'
CARD = ROOT / 'private/card-cycles/20261013-174348-A23-IOUSBHost-burst-read'
DEVICE = device.DEVICE / 'window-30s'
RECEIVER = ANALYSIS / 'A23-quiet-receiver-review-20261015/receiver-build'
TITLE = '00FF0000A53BB666'
CONTENT = 'atmosphere/contents/' + TITLE + '/'
PATCH = 'atmosphere/exefs_patches/SysDVR-ISO/' + build_patch.BUILD_ID + '.ips'
PATHS = (CONTENT + 'exefs.nsp', CONTENT + 'flags/boot2.flag', CONTENT + 'toolbox.json', PATCH)
ELF2NSO = Path('/opt/devkitpro/tools/bin/elf2nso')
PFS_TOOL = Path('/opt/devkitpro/tools/bin/build_pfs0')
require = common.require
sha = common.sha


def output_path(path):
    path = Path(path)
    require(path.is_absolute() and path == path.resolve() and not path.exists(), 'new canonical output required')
    require(path.parent == ANALYSIS.resolve() or Path('/private/tmp') in path.parents,
            'offline output must be a new direct analysis child or inside /private/tmp')
    return path


def pfs_files(raw):
    require(16 <= len(raw) <= 2 * 1024 * 1024 and raw[:4] == b'PFS0', 'PFS0 header')
    count, strings, reserved = struct.unpack_from('<3I', raw, 4)
    require(count == 2 and reserved == 0 and 0 < strings <= 256, 'PFS0 inventory/header')
    table = 16 + 24 * count
    start = table + strings
    require(start <= len(raw), 'PFS0 truncated name table')
    names = raw[table:start]
    result = {}; spans = []
    for i in range(count):
        off, size, name, zero = struct.unpack_from('<QQII', raw, 16 + 24 * i)
        require(zero == 0 and name < len(names) and (name == 0 or names[name-1] == 0), 'PFS0 name offset')
        end = names.find(b'\0', name)
        require(end >= 0, 'PFS0 unterminated name')
        key = names[name:end].decode('ascii')
        require(key in ('main', 'main.npdm') and key not in result, 'PFS0 duplicate/unknown name')
        require(size > 0 and off + size <= len(raw) - start, 'PFS0 truncated member')
        result[key] = raw[start+off:start+off+size]; spans.append((off, off+size))
    spans.sort()
    require(spans[0][0] == 0 and spans[0][1] == spans[1][0] and spans[1][1] == len(raw)-start,
            'PFS0 overlapping/gapped/trailing data')
    return result


def verify_nso(elf, raw):
    meta = elf_metadata(elf)
    require(len(raw) >= 256 and raw[:4] == b'NSO0', 'NSO header')
    phoff = struct.unpack_from('<Q', elf, 32)[0]
    entry, count = struct.unpack_from('<2H', elf, 54)
    require(entry == 56 and phoff + entry * count <= len(elf), 'ELF program headers')
    loads = [struct.unpack_from('<II6Q', elf, phoff + i*entry) for i in range(count)]
    loads = [p for p in loads if p[0] == 1]
    require(len(loads) == 3 and [p[1] for p in loads] == [5, 4, 6], 'ELF load layout')
    nso = Nso(raw)
    require(nso.version == 0 and nso.flags == 63, 'expected compressed/hashed NSO')
    notes = [s for s in meta['sections'] if s['name'] == '.note.gnu.build-id']
    require(len(notes) == 1, 'ELF build ID note')
    note = elf[notes[0]['offset']:notes[0]['offset']+notes[0]['size']]
    name_size, desc_size, kind = struct.unpack_from('<3I', note)
    desc_off = 12 + ((name_size+3)//4)*4
    require(name_size == 4 and note[12:16] == b'GNU\0' and kind == 3 and 0 < desc_size <= 32 and
            desc_off + desc_size <= len(note), 'ELF build ID shape')
    require(nso.build_id == note[desc_off:desc_off+desc_size].ljust(32, b'\0'), 'ELF/NSO build ID mismatch')
    spans = []; result = []
    for i, (p, section, segment) in enumerate(zip(loads, nso.sections, nso.segments)):
        _, _, offset, address, _, size, memory, _ = p
        require(offset+size <= len(elf) and memory >= size, 'ELF load size')
        require(section['vaddr'] == address and section['content'] == elf[offset:offset+size] and
                section['size'] == size and section['bss'] == (memory-size if i == 2 else 0),
                'ELF/NSO segment mismatch')
        digest = sha(section['content'])
        require(raw[0xa0+32*i:0xc0+32*i].hex() == digest, 'NSO segment hash mismatch')
        begin = segment[0]; end = begin+nso.compressed_sizes[i]
        require(256 <= begin < end <= len(raw), 'NSO segment extent')
        spans.append((begin, end)); result.append(dict(address=address, bytes=size, bss=section['bss'], sha256=digest))
    require(spans[0][0] == 256 and all(spans[i][1] == spans[i+1][0] for i in (0, 1)) and
            spans[-1][1] == len(raw), 'NSO overlapping/gapped/trailing data')
    return dict(build_id=nso.build_id.hex(), segments=result)


def verify_npdm(raw):
    require(len(raw) >= 0x80 and raw[:4] == b'META', 'NPDM header')
    aci, aci_size, acid, acid_size = struct.unpack_from('<4I', raw, 0x70)
    require(aci >= 0x80 and acid >= 0x80 and aci_size >= 0x18 and acid_size >= 0x220 and
            aci+aci_size <= len(raw) and acid+acid_size <= len(raw), 'NPDM extent')
    require(raw[aci:aci+4] == b'ACI0' and raw[acid+0x200:acid+0x204] == b'ACID', 'NPDM access descriptors')
    ids = (struct.unpack_from('<Q', raw, aci+0x10)[0], *struct.unpack_from('<2Q', raw, acid+0x210))
    require(ids == (int(TITLE, 16),)*3, 'NPDM program ID/range mismatch')
    require(struct.unpack_from('<I', raw, 28)[0] == 8192 and raw[14:16] == bytes((44, 3)), 'NPDM thread request')
    return dict(program_id=TITLE, main_thread_stack_request_bytes=8192, actual_stack_budget_authenticated=False)


def verify_controller(header, manifest, original, patch):
    arrays = {name: bytes(int(v) for v in values.split(',')) for name, values in
              re.findall(r'static const unsigned char (\w+)\[\d*\]=\{([0-9,]+)\};', header)}
    require(arrays.get('isoRuntimeBuildId', b'').hex().upper() == manifest['build_id'] == build_patch.BUILD_ID,
            'controller build ID mismatch')
    require(sha(original) == manifest['original_sha256'], 'controller original hash mismatch')
    nso = build_patch.validate_module(original)
    edits = re.findall(r'\{(\d+),(\d+),isoRuntime_(\d+)_before,isoRuntime_(\d+)_after\}', header)
    require(len(edits) == len(manifest['edits']) == 22, 'controller edit inventory')
    output = []
    for (address, size, before, after), edit in zip(edits, manifest['edits']):
        address, size = int(address), int(size)
        b = arrays['isoRuntime_'+before+'_before']; a = arrays['isoRuntime_'+after+'_after']
        require(before == after and address == int(edit['address'], 16) and size == len(a) == len(b) and
                b.hex() == edit['before'] and a.hex() == edit['after'], 'embedded controller edit mismatch')
        require(build_patch.read_mapped(nso, address, size) == b, 'controller before bytes mismatch')
        output.append((address, a))
    require(build_patch.ips32(output) == patch and sha(patch) == manifest['patch_sha256'], 'controller IPS mismatch')
    return dict(build_id=manifest['build_id'], edits=len(output), patch_sha256=sha(patch), original_sha256=sha(original))


def assess_saved(execution, primary, expected_recipe):
    """Content/claimed receipt only. Callers must preserve original files and provenance."""
    decoded = decode_execution(execution, expected_recipe)
    startup_len = struct.unpack_from('<I', execution, 24)[0]
    payload = execution[256+startup_len:]
    relation = 'missing' if primary is None else ('matches' if primary == payload else 'different_or_partial')
    return dict(schema='A23-quiet-recovery-content-1', recipe_digest=decoded['recipe_digest'],
        boot_id_hex=decoded['boot_id_hex'], session_id_hex=decoded['session_id_hex'],
        primary_kind=decoded['primary_kind'], primary_file_relation=relation,
        primary_receipt=decoded['primary_receipt'], execution_content_valid=True,
        execution_own_commit_authenticated=False, join_results_authenticated=False,
        physical_run_authenticated=False, clean_exit_authenticated=False,
        diagnostic_retains_even_if_saves_succeed=decoded['primary_kind'] == 'diagnostic',
        hardware_verified=False, cleanup_authorized=False)


def put(root, name, raw):
    target = root / name; target.parent.mkdir(parents=True, exist_ok=True)
    common.old.durable_write(target, raw)


def verify_review(root):
    root = Path(root)
    require(root.is_absolute() and root == root.resolve(), 'canonical review required')
    verify(root)
    files = {p.relative_to(root).as_posix(): p for p in root.rglob('*')
             if p.is_file() and p not in (root/'SHA256SUMS', root/'COMMITTED')}
    sums = ''.join(sha(common.plain(files[n]))+'  '+n+'\n' for n in sorted(files)).encode()
    require(common.plain(root/'SHA256SUMS') == sums and common.plain(root/'COMMITTED') == (sha(sums)+'\n').encode(),
            'review inventory/seal mismatch')
    report = common.load(root/'package-report.json')
    require(report['schema'] == 'A23-quiet-deployment-review-1' and report['device_binding'] == device.identity() and
            report['device_binding_sha256'] == device.binding_hash(report['device_binding']), 'review device identity')
    require(all(report[key] is False for key in ('hardware_verified', 'acquisition_enabled', 'attempt_issued', 'deployed'))
            and type(report['remaining']) is int and report['remaining'] == 0, 'review is offline only')
    device.supplied_material(report['device_binding'], root/'device')
    require(common.load(root/'device-binding.json') == report['device_binding'] and
            common.load(root/'receiver-manifest.json') == common.load(RECEIVER/'manifest.json') and
            common.load(root/'receiver-manifest.json')['device_binding'] == report['device_binding'],
            'review receiver/device binding mismatch')
    elf = common.plain(root/'device/full.elf'); nso = common.plain(root/'exefs/main')
    npdm = common.plain(root/'exefs/main.npdm'); package = common.plain(root/'exefs.nsp')
    require(sha(package) == report['exefs_nsp_sha256'] and sha(nso) == report['main_nso_sha256'] and
            verify_nso(elf, nso) == report['conversion'] and verify_npdm(npdm) == report['npdm'] and
            npdm == common.plain(root/'device/main.npdm') and pfs_files(package) == {'main': nso, 'main.npdm': npdm},
            'review conversion/package mismatch')
    for n in PATHS:
        baseline = common.plain(BASE/n)
        before = common.plain(root/'rollback-review'/n); after = common.plain(root/'sd-review'/n)
        require(before == baseline and after == (package if n == CONTENT+'exefs.nsp' else baseline), 'review file mismatch')
        require(report['historical_baseline'][n] == dict(bytes=len(before), sha256=sha(before)) and
                report['deployment_files'][n] == dict(bytes=len(after), sha256=sha(after)), 'review file report mismatch')
    controller = verify_controller(common.plain(DEVICE/'source/uvc/iso_runtime_payload.h').decode(),
        common.load(BASE/'manifest.json'), common.plain(ROOT/'private/module/exefs/main'), common.plain(BASE/PATCH))
    require(report['controller'] == controller, 'review controller report mismatch')
    return dict(schema='A23-quiet-deployment-verification-1', files=len(files),
        manifest_sha256=sha(sums), exefs_nsp_sha256=sha(package), hardware_verified=False, deployed=False)


def build(output):
    output = output_path(output)
    for folder in (BASE, CARD, device.DEVICE, RECEIVER):
        verify(folder)
    bound = device.identity()
    require(common.load(RECEIVER/'device-binding.json') == bound, 'receiver/device mismatch')
    card = common.load(CARD/'card-cycle.json')
    baseline = {n: common.plain(BASE/n) for n in PATHS}
    # Compare with the sealed readback report, never with a currently mounted card.
    historical = {item['path']: (item['size'], item['sha256']) for item in card['files']}
    require(historical == {n: (len(raw), sha(raw)) for n, raw in baseline.items()}, 'historical card baseline mismatch')
    raw_inputs = {n: common.plain(DEVICE/n) for n in device.FILES}
    npdm = verify_npdm(raw_inputs['main.npdm'])
    controller = verify_controller(common.plain(DEVICE/'source/uvc/iso_runtime_payload.h').decode(),
        common.load(BASE/'manifest.json'), common.plain(ROOT/'private/module/exefs/main'), baseline[PATCH])
    output.mkdir(parents=True, mode=0o700)
    for n, raw in raw_inputs.items():
        put(output, 'device/'+n, raw)
    put(output, 'device-binding.json', common.canonical(bound))
    put(output, 'receiver-manifest.json', common.plain(RECEIVER/'manifest.json'))
    commands = [[str(ELF2NSO), str(output/'device/full.elf'), str(output/'exefs/main')],
                [str(PFS_TOOL), str(output/'exefs'), str(output/'exefs.nsp')]]
    (output/'exefs').mkdir()
    put(output, 'exefs/main.npdm', raw_inputs['main.npdm'])
    tools = {str(p): sha(common.plain(p)) for p in (ELF2NSO, PFS_TOOL)}
    for i, command in enumerate(commands):
        run = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True)
        put(output, 'command-'+str(i)+'.log', run.stdout)
    nso = common.plain(output/'exefs/main'); package = common.plain(output/'exefs.nsp')
    converted = verify_nso(raw_inputs['full.elf'], nso)
    require(pfs_files(package) == {'main': nso, 'main.npdm': raw_inputs['main.npdm']}, 'PFS0 material mismatch')
    for n, raw in baseline.items():
        put(output, 'rollback-review/'+n, raw)
        put(output, 'sd-review/'+n, package if n == CONTENT+'exefs.nsp' else raw)
    require(tools == {str(p): sha(common.plain(p)) for p in (ELF2NSO, PFS_TOOL)}, 'packager tool drift')
    require(bound == device.identity(), 'candidate changed during packaging')
    report = dict(schema='A23-quiet-deployment-review-1', device_binding=bound,
        device_binding_sha256=device.binding_hash(bound), exefs_nsp_sha256=sha(package), main_nso_sha256=sha(nso),
        npdm=npdm, conversion=converted, controller=controller, commands=commands, tool_hashes=tools,
        historical_baseline={n: dict(bytes=len(raw), sha256=sha(raw)) for n, raw in baseline.items()},
        deployment_files={n: dict(bytes=len(common.plain(output/'sd-review'/n)), sha256=sha(common.plain(output/'sd-review'/n))) for n in PATHS},
        rollback_scope='historical A23 four-file baseline; verify actual card before any future replacement',
        fresh_start_required=True, hot_toggle_validated=False, hardware_verified=False,
        acquisition_enabled=False, attempt_issued=False, remaining=0, deployed=False)
    common.write(output/'package-report.json', report)
    common.seal(output)
    verify_review(output)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path, nargs='?')
    parser.add_argument('--verify', type=Path)
    parser.add_argument('--execution', type=Path)
    parser.add_argument('--primary', type=Path)
    parser.add_argument('--expected-recipe')
    args = parser.parse_args()
    if sum(value is not None for value in (args.output, args.verify, args.execution)) != 1:
        parser.error('choose an offline output, --verify, or --execution')
    if args.execution:
        if not args.expected_recipe or not re.fullmatch('[0-9a-f]{64}', args.expected_recipe):
            parser.error('--execution requires a 64-hex --expected-recipe')
        result = assess_saved(common.plain(args.execution), common.plain(args.primary) if args.primary else None, args.expected_recipe)
    else:
        if args.primary or args.expected_recipe:
            parser.error('recovery arguments require --execution')
        result = verify_review(args.verify) if args.verify else build(args.output)
    print(json.dumps(result, indent=2))
