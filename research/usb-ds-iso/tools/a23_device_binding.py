"""Separate parent, window recipe and final ELF identities; file-only checks."""
import json
from pathlib import Path
import re

import audit_a23_v3_runtime as runtime
import build_a23_waiting_receiver as old
from analyze_io_usb_host_evidence import require,unique_object

ROOT=old.ROOT;REPO=old.REPO;DEVICE=old.DEVICE
PARENT=ROOT/'private/analysis/A23-v3-runtime-review-20261015'
FILES=('full.elf','recipe.json','symbols.txt','source/uvc/ep0_candidate_recipe.h')


def load(path,limit=4*1024*1024):return json.loads(old.plain(Path(path),limit),object_pairs_hook=unique_object)


def identity(device=DEVICE/'window-30s'):
    device=Path(device);require(device.is_absolute() and device==device.resolve(),'canonical device source required')
    audit=load(DEVICE/'audit.json');expected=DEVICE/'window-30s'
    hashes={n:old.sha(old.plain(device/n)) for n in FILES}
    require(hashes=={n:old.sha(old.plain(expected/n)) for n in FILES},'device inputs differ from sealed window candidate')
    cfg=load(device/'recipe.json');runtime_digest=audit['builds']['window-30s']['runtime_recipe_digest']
    require(cfg['window_ms']==30000 and cfg['input_digest']==runtime_digest and
            cfg['parent_input_digest']==audit['recipe_digest'],'parent/window recipe mismatch')
    header=old.plain(device/FILES[3],65536).decode()
    match=re.fullmatch(r'static const uint8_t ep0CandidateRecipe\[32\]=\{([0-9,]+)\};\s*',header)
    require(match is not None,'unsupported device recipe header')
    recipe=bytes(int(n) for n in match[1].split(','));require(len(recipe)==32 and recipe.hex()==runtime_digest,'header/runtime mismatch')
    elf=runtime.Elf(device/'full.elf');symbols=old.plain(device/'symbols.txt',2*1024*1024).decode()
    addresses=[int(m[1],16) for m in re.finditer(r'^\s*\d+: ([0-9a-f]+)\s+32\s+OBJECT\s+LOCAL\s+DEFAULT\s+\d+\s+ep0CandidateRecipe$',symbols,re.M)]
    require(len(addresses)==2 and all(elf.bytes(a,32)==recipe for a in addresses),'linked runtime recipe differs')
    require(hashes['full.elf']==audit['builds']['window-30s']['elf_sha256'],'device ELF mismatch')
    return dict(schema='A23-device-binding-1',configuration='window-30s',device_source_root=str(device),
        parent_input_digest=audit['recipe_digest'],runtime_recipe_sha256=runtime_digest,
        device_elf_sha256=hashes['full.elf'],artifact_hashes=hashes)


def binding_hash(value):return old.sha(old.canonical(value))


def supplied_material(bound,folder):
    """Internal byte agreement only; does not follow device_source_root."""
    require(type(bound) is dict and set(bound)=={'schema','configuration','device_source_root',
        'parent_input_digest','runtime_recipe_sha256','device_elf_sha256','artifact_hashes'},'invalid device binding fields')
    require(bound['schema']=='A23-device-binding-1' and bound['configuration']=='window-30s' and
        type(bound['device_source_root']) is str,'invalid device binding shape')
    hashes=bound['artifact_hashes'];require(type(hashes) is dict and set(hashes)==set(FILES),'invalid device inventory')
    for key in ('parent_input_digest','runtime_recipe_sha256','device_elf_sha256'):
        require(type(bound[key]) is str and re.fullmatch('[0-9a-f]{64}',bound[key]),'invalid device digest')
    raws={n:old.plain(Path(folder)/n) for n in FILES}
    require(all(old.sha(raw)==hashes[n] for n,raw in raws.items()),'supplied device artifact hash mismatch')
    require(hashes['full.elf']==bound['device_elf_sha256'],'supplied ELF identity mismatch')
    cfg=json.loads(raws['recipe.json'],object_pairs_hook=unique_object)
    require(type(cfg) is dict and cfg.get('input_digest')==bound['runtime_recipe_sha256'] and
        cfg.get('parent_input_digest')==bound['parent_input_digest'] and type(cfg.get('window_ms')) is int and cfg['window_ms']==30000,
        'supplied parent/runtime configuration mismatch')
    match=re.fullmatch(r'static const uint8_t ep0CandidateRecipe\[32\]=\{([0-9,]+)\};\s*',raws[FILES[3]].decode())
    require(match is not None,'invalid supplied recipe header');recipe=bytes(int(n) for n in match[1].split(','))
    require(len(recipe)==32 and recipe.hex()==bound['runtime_recipe_sha256'],'supplied header/runtime mismatch')
    reader=runtime.Elf(Path(folder)/'full.elf')
    addresses=[int(m[1],16) for m in re.finditer(r'^\s*\d+: ([0-9a-f]+)\s+32\s+OBJECT\s+LOCAL\s+DEFAULT\s+\d+\s+ep0CandidateRecipe$',raws['symbols.txt'].decode(),re.M)]
    require(len(addresses)==2 and all(reader.bytes(a,32)==recipe for a in addresses),'supplied ELF recipe mismatch')
    require(raws=={n:old.plain(Path(folder)/n) for n in FILES},'device material changed during checking')
    return True


def receipt(record):
    """Serialize a consumed receipt only; caller must consume a new issued use."""
    return dict(schema='A23-waiting-burst-consumed-receipt-2',backend='a23-waiting-burst-1',attempt_consumed=True,
        receiver_sha256=record['receiver_sha256'],build_manifest_sha256=record['build_manifest_sha256'],
        parent_input_digest=record['device_binding']['parent_input_digest'],
        device_elf_sha256=record['device_binding']['device_elf_sha256'],
        device_binding_sha256=record['device_binding_sha256'],recipe_sha256=record['recipe_sha256'],
        plan=old.WAIT_PLAN,preparation_id=record['preparation_id'])


def once(text,before,after):
    require(text.count(before)==1,'generation anchor changed: '+before[:80]);return text.replace(before,after)


def generated(sources,device):
    """Derive three new native units without editing any previous input."""
    prefix='research/usb-ds-iso/host/'
    guard=sources[prefix+'a23_waiting_build_guard.m'].decode()
    guard=once(guard,'static BOOL sourceCheck(', '#include "a23_device_binding_guard.inc"\nstatic BOOL sourceCheck(')
    guard=once(guard,'[names sortedArrayUsingSelector:@selector(compare:)]',
        '[names sortedArrayUsingComparator:^NSComparisonResult(NSString *a,NSString *b){int n=strcmp(a.UTF8String,b.UTF8String);return n<0?NSOrderedAscending:n>0?NSOrderedDescending:NSOrderedSame;}]')
    guard=once(guard,'    for(NSString *name in binding[@"source_hashes"])[expected addObject:[@"source/" stringByAppendingString:name]];',
        '    for(NSString *name in binding[@"source_hashes"])[expected addObject:[@"source/" stringByAppendingString:name]];\n'
        '    [expected addObject:@"device-binding.json"];\n'
        '    for(NSString *name in binding[@"generated_hashes"])[expected addObject:[@"generated/" stringByAppendingString:name]];\n'
        '    for(NSString *name in binding[@"device_binding"][@"artifact_hashes"])[expected addObject:[@"device/" stringByAppendingString:name]];')
    guard=once(guard,'!sourceCheck(binding,build) || !sourceCheck(binding,build)',
        '!deviceCheck(binding,build) || !sourceCheck(binding,build) || !sourceCheck(binding,build) || !deviceCheck(binding,build)')
    guard=once(guard,'@"source_closure_checked":@YES}',
        '@"source_closure_checked":@YES,@"parent_input_digest":binding[@"device_binding"][@"parent_input_digest"],'
        '@"device_elf_sha256":binding[@"device_binding"][@"device_elf_sha256"],@"device_binding_sha256":binding[@"device_binding_sha256"]}')
    guard=guard.replace('@"A23-waiting-burst-consumed-receipt-1"','@"A23-waiting-burst-consumed-receipt-2"')
    guard=once(guard,'@"recipe_sha256":checked[@"recipe_sha256"],',
        '@"recipe_sha256":checked[@"recipe_sha256"],@"parent_input_digest":checked[@"parent_input_digest"],'
        '@"device_elf_sha256":checked[@"device_elf_sha256"],@"device_binding_sha256":checked[@"device_binding_sha256"],')
    entry=sources[prefix+'a23_waiting_burst_entry.m'].decode()
    entry='#include "a23_device_binding_constants.h"\n'+entry
    entry=entry.replace('@"A23-waiting-burst-consumed-receipt-1"','@"A23-waiting-burst-consumed-receipt-2"')
    entry=once(entry,'@"build_manifest_sha256":_manifest,@"recipe_sha256":_recipe,@"plan":A23WaitingBurstPlan(),',
        '@"build_manifest_sha256":_manifest,@"recipe_sha256":_recipe,@"parent_input_digest":@A23_BOUND_PARENT,'
        '@"device_elf_sha256":@A23_BOUND_ELF,@"device_binding_sha256":@A23_BOUND_BINDING,@"plan":A23WaitingBurstPlan(),')
    entry=once(entry,'@"build_manifest_sha256":_manifest,@"recipe_sha256":_recipe};',
        '@"build_manifest_sha256":_manifest,@"recipe_sha256":_recipe,@"parent_input_digest":@A23_BOUND_PARENT,'
        '@"device_elf_sha256":@A23_BOUND_ELF,@"device_binding_sha256":@A23_BOUND_BINDING};')
    receiver=sources[prefix+'a23_waiting_receiver.m'].decode()
    receiver='#include "a23_device_binding_constants.h"\n'+receiver
    receiver=once(receiver,'@"schema":@"A23-waiting-receiver-description-1",',
        '@"schema":@"A23-waiting-receiver-description-2",@"device_binding_schema":@"A23-device-binding-1",@"device_configuration":@"window-30s",'
        '@"parent_input_digest":@A23_BOUND_PARENT,@"runtime_recipe_sha256":@A23_BOUND_RUNTIME,'
        '@"device_elf_sha256":@A23_BOUND_ELF,@"device_binding_sha256":@A23_BOUND_BINDING,')
    constants='/* Offline build identities; no hardware authorization. */\n'+''.join(
        '#define '+key+' "'+value+'"\n' for key,value in (
            ('A23_BOUND_PARENT',device['parent_input_digest']),('A23_BOUND_RUNTIME',device['runtime_recipe_sha256']),
            ('A23_BOUND_ELF',device['device_elf_sha256']),('A23_BOUND_BINDING',binding_hash(device))))
    return {n:raw.encode() for n,raw in {'a23_waiting_build_guard.m':guard,'a23_waiting_burst_entry.m':entry,
        'a23_waiting_receiver.m':receiver,'a23_device_binding_constants.h':constants}.items()}
