"""Bind the sealed quiet candidate's six files, including NPDM. File-only."""
import json
from pathlib import Path
import re
import struct

import a23_device_binding as previous
from workflows.artifacts import verify

old=previous.old;runtime=previous.runtime
ROOT=old.ROOT;REPO=old.REPO
DEVICE=ROOT/'private/analysis/A23-quiet-window-review-20261015'
PARENT=DEVICE
FILES=(*previous.FILES,'sysmodule.json','main.npdm')
load=previous.load;binding_hash=previous.binding_hash;once=previous.once
EXTRA=('device_npdm_sha256','device_config_sha256','main_thread_stack_request_bytes')


def supplied_material(bound,folder):
    """Check packet bytes without reading its recorded live device root."""
    fields={'schema','configuration','device_source_root','parent_input_digest','runtime_recipe_sha256',
        'device_elf_sha256','artifact_hashes',*EXTRA}
    old.require(type(bound) is dict and set(bound)==fields,'invalid quiet device binding fields')
    old.require(bound['schema']=='A23-quiet-host-device-binding-1' and bound['configuration']=='quiet-window-30s' and
        type(bound['device_source_root']) is str,'invalid quiet device binding shape')
    hashes=bound['artifact_hashes']
    old.require(type(hashes) is dict and set(hashes)==set(FILES),'invalid six-file device inventory')
    for key in ('parent_input_digest','runtime_recipe_sha256','device_elf_sha256',*EXTRA[:2]):
        old.require(type(bound[key]) is str and re.fullmatch('[0-9a-f]{64}',bound[key]),'invalid quiet device digest')
    old.require(all(type(h) is str and re.fullmatch('[0-9a-f]{64}',h) for h in hashes.values()),'invalid device artifact hash')
    raws={n:old.plain(Path(folder)/n) for n in FILES}
    old.require(all(old.sha(raw)==hashes[n] for n,raw in raws.items()),'supplied quiet device artifact hash mismatch')
    old.require(hashes['full.elf']==bound['device_elf_sha256'] and hashes['main.npdm']==bound['device_npdm_sha256'] and
        hashes['sysmodule.json']==bound['device_config_sha256'],'supplied ELF/NPDM/config identity mismatch')
    cfg=json.loads(raws['recipe.json'],object_pairs_hook=previous.unique_object)
    old.require(type(cfg) is dict and cfg.get('schema')=='A23-quiet-window-recipe-1' and
        cfg.get('input_digest')==bound['runtime_recipe_sha256'] and cfg.get('parent_input_digest')==bound['parent_input_digest'] and
        type(cfg.get('window_ms')) is int and cfg['window_ms']==30000 and cfg.get('production_capture') is False and
        cfg.get('quiet_until_both_joins') is True and type(cfg.get('diagnostic_pacing_ns')) is int and cfg['diagnostic_pacing_ns']==1000000,
        'supplied quiet recipe/policy mismatch')
    old.require(type(cfg.get('config_hashes')) is dict and cfg['config_hashes'].get('sysmodule.json')==bound['device_config_sha256'],
        'recipe does not bind NPDM configuration')
    config=json.loads(raws['sysmodule.json'],object_pairs_hook=previous.unique_object);npdm=raws['main.npdm']
    old.require(type(config) is dict and len(npdm)>=0x80 and npdm[:4]==b'META','invalid NPDM/config material')
    stack=bound['main_thread_stack_request_bytes']
    old.require(type(stack) is int and stack==8192 and type(config.get('main_thread_stack_size')) is str and
        int(config['main_thread_stack_size'],0)==stack==struct.unpack_from('<I',npdm,28)[0] and
        type(config.get('main_thread_priority')) is int and config['main_thread_priority']==npdm[14]==44 and
        type(config.get('default_cpu_id')) is int and config['default_cpu_id']==npdm[15]==3,'NPDM main request mismatch')
    match=re.fullmatch(r'static const uint8_t ep0CandidateRecipe\[32\]=\{([0-9,]+)\};\s*',raws[FILES[3]].decode())
    old.require(match is not None,'invalid quiet recipe header')
    recipe=bytes(int(n) for n in match[1].split(','))
    old.require(len(recipe)==32 and recipe.hex()==bound['runtime_recipe_sha256'],'quiet header/runtime mismatch')
    reader=runtime.Elf(Path(folder)/'full.elf')
    addresses=[int(m[1],16) for m in re.finditer(r'^\s*\d+: ([0-9a-f]+)\s+32\s+OBJECT\s+LOCAL\s+DEFAULT\s+\d+\s+ep0CandidateRecipe$',raws['symbols.txt'].decode(),re.M)]
    old.require(len(addresses)==2 and all(reader.bytes(a,32)==recipe for a in addresses),'supplied quiet ELF recipe mismatch')
    old.require(raws=={n:old.plain(Path(folder)/n) for n in FILES},'quiet material changed during checking')
    return True


def identity(device=DEVICE/'window-30s'):
    device=Path(device)
    old.require(device.is_absolute() and device==device.resolve(),'canonical quiet device source required')
    verify(DEVICE)
    audit=load(DEVICE/'audit.json');expected=DEVICE/'window-30s'
    hashes={n:old.sha(old.plain(device/n)) for n in FILES}
    old.require(hashes=={n:old.sha(old.plain(expected/n)) for n in FILES},'device inputs differ from sealed quiet candidate')
    artifact=audit['device_binding'];cfg=load(device/'recipe.json')
    bound=dict(schema='A23-quiet-host-device-binding-1',configuration='quiet-window-30s',device_source_root=str(device),
        parent_input_digest=cfg['parent_input_digest'],runtime_recipe_sha256=audit['runtime_recipe_sha256'],
        device_elf_sha256=artifact['device_elf_sha256'],device_npdm_sha256=artifact['npdm_sha256'],
        device_config_sha256=artifact['config_sha256'],main_thread_stack_request_bytes=artifact['main_thread_stack_request_bytes'],
        artifact_hashes=hashes)
    old.require(artifact['artifact_hashes']==hashes,'candidate audit/artifact mismatch')
    supplied_material(bound,device)
    return bound


def receipt(record):
    d=record['device_binding']
    return dict(schema='A23-waiting-burst-consumed-receipt-3',backend='a23-waiting-burst-1',attempt_consumed=True,
        receiver_sha256=record['receiver_sha256'],build_manifest_sha256=record['build_manifest_sha256'],
        parent_input_digest=d['parent_input_digest'],device_elf_sha256=d['device_elf_sha256'],
        **{n:d[n] for n in EXTRA},device_binding_sha256=record['device_binding_sha256'],recipe_sha256=record['recipe_sha256'],
        plan=old.WAIT_PLAN,preparation_id=record['preparation_id'])


def generated(sources,device):
    """Derive a new generation from original units; never edit sealed inputs."""
    result={n:raw.decode() for n,raw in previous.generated(sources,device).items()}
    for n in result:
        result[n]=result[n].replace('A23-waiting-burst-consumed-receipt-2','A23-waiting-burst-consumed-receipt-3')
    guard=result['a23_waiting_build_guard.m'].replace('"a23_device_binding_guard.inc"','"a23_quiet_device_guard.inc"')
    for anchor in ('binding[@"device_binding_sha256"]}', 'checked[@"device_binding_sha256"],'):
        suffix='}' if anchor.endswith('}') else ','
        container='binding[@"device_binding"]' if anchor.startswith('binding') else 'checked'
        added=''.join(',@"'+key+'":'+container+'[@"'+key+'"]' for key in EXTRA)
        guard=once(guard,anchor,anchor[:-1]+added+suffix)
    result['a23_waiting_build_guard.m']=guard
    entry=result['a23_waiting_burst_entry.m']
    extra=',@"device_npdm_sha256":@A23_BOUND_NPDM,@"device_config_sha256":@A23_BOUND_CONFIG,@"main_thread_stack_request_bytes":@(A23_BOUND_MAIN_STACK)'
    entry=entry.replace('@"device_binding_sha256":@A23_BOUND_BINDING', '@"device_binding_sha256":@A23_BOUND_BINDING'+extra)
    result['a23_waiting_burst_entry.m']=entry
    receiver=result['a23_waiting_receiver.m'].replace('A23-waiting-receiver-description-2','A23-waiting-receiver-description-3')
    receiver=receiver.replace('A23-device-binding-1','A23-quiet-host-device-binding-1').replace('@"device_configuration":@"window-30s"','@"device_configuration":@"quiet-window-30s"')
    receiver=once(receiver,'@"device_binding_sha256":@A23_BOUND_BINDING,','@"device_binding_sha256":@A23_BOUND_BINDING'+extra+',')
    result['a23_waiting_receiver.m']=receiver
    result['a23_device_binding_constants.h']+=''.join('#define '+key+' "'+device[field]+'"\n' for key,field in (
        ('A23_BOUND_NPDM','device_npdm_sha256'),('A23_BOUND_CONFIG','device_config_sha256')))
    result['a23_device_binding_constants.h']+='#define A23_BOUND_MAIN_STACK '+str(device['main_thread_stack_request_bytes'])+'\n'
    return {n:text.encode() for n,text in result.items()}
