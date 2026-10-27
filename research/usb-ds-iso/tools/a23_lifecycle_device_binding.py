"""Bind the sealed lifecycle candidate's six files, including NPDM. File-only."""
import json
from pathlib import Path
import re
import struct

import a23_device_binding as previous
import a23_quiet_device_binding as quiet
from workflows.artifacts import verify

old=previous.old;runtime=previous.runtime
ROOT=old.ROOT;REPO=old.REPO
DEVICE=ROOT/'private/analysis/A23-lifecycle-device-review-20261016'
PARENT=DEVICE
FILES=(*previous.FILES,'sysmodule.json','main.npdm')
load=previous.load;binding_hash=previous.binding_hash;once=previous.once
EXTRA=('device_npdm_sha256','device_config_sha256','main_thread_stack_request_bytes')


def supplied_material(bound,folder):
    """Check packet bytes without reading its recorded live device root."""
    fields={'schema','configuration','device_source_root','parent_input_digest','runtime_recipe_sha256',
        'device_elf_sha256','artifact_hashes',*EXTRA}
    old.require(type(bound) is dict and set(bound)==fields,'invalid lifecycle device binding fields')
    old.require(bound['schema']=='A23-lifecycle-host-device-binding-1' and bound['configuration']=='lifecycle-window-30s' and
        type(bound['device_source_root']) is str,'invalid lifecycle device binding shape')
    hashes=bound['artifact_hashes']
    old.require(type(hashes) is dict and set(hashes)==set(FILES),'invalid six-file device inventory')
    for key in ('parent_input_digest','runtime_recipe_sha256','device_elf_sha256',*EXTRA[:2]):
        old.require(type(bound[key]) is str and re.fullmatch('[0-9a-f]{64}',bound[key]),'invalid lifecycle device digest')
    old.require(all(type(h) is str and re.fullmatch('[0-9a-f]{64}',h) for h in hashes.values()),'invalid device artifact hash')
    raws={n:old.plain(Path(folder)/n) for n in FILES}
    old.require(all(old.sha(raw)==hashes[n] for n,raw in raws.items()),'supplied lifecycle device artifact hash mismatch')
    old.require(hashes['full.elf']==bound['device_elf_sha256'] and hashes['main.npdm']==bound['device_npdm_sha256'] and
        hashes['sysmodule.json']==bound['device_config_sha256'],'supplied ELF/NPDM/config identity mismatch')
    cfg=json.loads(raws['recipe.json'],object_pairs_hook=previous.unique_object)
    old.require(type(cfg) is dict and cfg.get('schema')=='A23-lifecycle-device-recipe-1' and
        cfg.get('runtime_recipe_sha256')==bound['runtime_recipe_sha256'] and cfg.get('parent_runtime_recipe')==bound['parent_input_digest'] and
        type(cfg.get('window_ms')) is int and cfg['window_ms']==30000,'supplied lifecycle recipe mismatch')
    config=json.loads(raws['sysmodule.json'],object_pairs_hook=previous.unique_object);npdm=raws['main.npdm']
    old.require(type(config) is dict and len(npdm)>=0x80 and npdm[:4]==b'META','invalid NPDM/config material')
    stack=bound['main_thread_stack_request_bytes']
    old.require(type(stack) is int and stack==8192 and type(config.get('main_thread_stack_size')) is str and
        int(config['main_thread_stack_size'],0)==stack==struct.unpack_from('<I',npdm,28)[0] and
        type(config.get('main_thread_priority')) is int and config['main_thread_priority']==npdm[14]==44 and
        type(config.get('default_cpu_id')) is int and config['default_cpu_id']==npdm[15]==3,'NPDM main request mismatch')
    match=re.fullmatch(r'static const uint8_t ep0CandidateRecipe\[32\]=\{([0-9,]+)\};\s*',raws[FILES[3]].decode())
    old.require(match is not None,'invalid lifecycle recipe header')
    recipe=bytes(int(n) for n in match[1].split(','))
    old.require(len(recipe)==32 and recipe.hex()==bound['runtime_recipe_sha256'],'lifecycle header/runtime mismatch')
    reader=runtime.Elf(Path(folder)/'full.elf')
    addresses=[int(m[1],16) for m in re.finditer(r'^\s*\d+: ([0-9a-f]+)\s+32\s+OBJECT\s+LOCAL\s+DEFAULT\s+\d+\s+ep0CandidateRecipe$',raws['symbols.txt'].decode(),re.M)]
    old.require(len(addresses)==2 and all(reader.bytes(a,32)==recipe for a in addresses),'supplied lifecycle ELF recipe mismatch')
    old.require(raws=={n:old.plain(Path(folder)/n) for n in FILES},'lifecycle material changed during checking')
    return True


def identity(device=DEVICE/'candidate'):
    device=Path(device)
    old.require(device.is_absolute() and device==device.resolve(),'canonical lifecycle device required')
    verify(DEVICE)
    audit=load(DEVICE/'audit.json');artifact=audit['device_binding']
    old.require((DEVICE/'COMMITTED').read_text().strip()==old.sha(old.plain(DEVICE/'SHA256SUMS')),'device review commit mismatch')
    hashes={n:old.sha(old.plain(device/n)) for n in FILES}
    old.require(hashes==artifact['artifact_hashes'],'device differs from sealed lifecycle candidate')
    bound=dict(schema='A23-lifecycle-host-device-binding-1',configuration='lifecycle-window-30s',device_source_root=str(device),
        parent_input_digest=artifact['parent_runtime_recipe'],runtime_recipe_sha256=artifact['runtime_recipe_sha256'],
        device_elf_sha256=hashes['full.elf'],device_npdm_sha256=hashes['main.npdm'],device_config_sha256=hashes['sysmodule.json'],
        main_thread_stack_request_bytes=artifact['main_thread_stack_request_bytes'],artifact_hashes=hashes)
    supplied_material(bound,device);return bound


def receipt(record):
    d=record['device_binding']
    return dict(schema='A23-waiting-burst-consumed-receipt-4',backend='a23-waiting-burst-1',attempt_consumed=True,
        receiver_sha256=record['receiver_sha256'],build_manifest_sha256=record['build_manifest_sha256'],
        parent_input_digest=d['parent_input_digest'],device_elf_sha256=d['device_elf_sha256'],
        **{n:d[n] for n in EXTRA},device_binding_sha256=record['device_binding_sha256'],recipe_sha256=record['recipe_sha256'],
        plan=old.WAIT_PLAN,preparation_id=record['preparation_id'])


def generated(sources,device):
    result={n:raw.decode() for n,raw in quiet.generated(sources,device).items()}
    for n,text in result.items():
        text=text.replace('A23-waiting-burst-consumed-receipt-3','A23-waiting-burst-consumed-receipt-4')
        text=text.replace('A23-waiting-receiver-description-3','A23-waiting-receiver-description-4')
        text=text.replace('A23-quiet-host-device-binding-1','A23-lifecycle-host-device-binding-1')
        text=text.replace('quiet-window-30s','lifecycle-window-30s')
        if n=='a23_waiting_build_guard.m':
            text=once(text,'"a23_quiet_device_guard.inc"','"a23_lifecycle_device_guard.inc"')
            text=once(text,'hashes.count>200','hashes.count>224')
        result[n]=text.encode()
    return result
