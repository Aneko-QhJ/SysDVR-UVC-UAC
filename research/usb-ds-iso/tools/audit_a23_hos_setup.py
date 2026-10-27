#!/usr/bin/env python3
"""Bind HOS shared EP0 setup paths to saved A23 and replay scheduling hypotheses.

Read-only USB/SD evidence audit. Creates a NEW output directory; never deploys,
changes acquisition tickets, changes timeouts, or emulates HOS machine code.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import subprocess

from audit_a23_ep0 import (CARD, COLLECTION, PACKAGE, REPO, ROOT, RUN,
                          actual_source, bind_elf, sha)
from build_patch import BUILD_ID, branch, read_mapped, validate_module
from workflows.artifacts import PRIVATE, archive_path, verify

SCENARIOS=('no-delay','20ms-kept','28ms-kept','32ms-replaced',
           '32ms-delayed-arrival','32ms-no-replacement')
RANGES={
    'interface_ipc':(0x254e0,0x26820), 'setup_thunks':(0x27d50,0x27d80),
    'setup_store':(0x2a0f0,0x2a150), 'setup_read':(0x2a150,0x2a1e0),
    'event_register':(0x2a1e0,0x2a2c0), 'setup_notify':(0x2a2c0,0x2a2e0),
    'setup_dispatch':(0x2aa20,0x2ac00), 'interface_init':(0x2cc80,0x2cd50),
    'setup_event':(0x2cf00,0x2cf90), 'interface_read':(0x2cf90,0x2cfc0),
    'event_signal_clear':(0xb470,0xb4d0), 'local_signal_clear':(0xafd0,0xb0a0),
    'remote_signal_clear':(0xc0b0,0xc0e0), 'svc_signal_clear':(0x191d4,0x191e4),
    'controller_events':(0x30700,0x30940),
}


def parse_ips(data):
    if not data.startswith(b'IPS32'):
        raise ValueError('Expected IPS32')
    records=[];pos=5;end=0
    while data[pos:pos+4]!=b'EEOF':
        if pos+6>len(data):raise ValueError('Truncated IPS32 header')
        address,size=struct.unpack_from('>IH',data,pos);pos+=6;address-=0x100
        if not size or address<end or pos+size>len(data):
            raise ValueError('Invalid/overlapping/truncated IPS32 record')
        records.append((address,data[pos:pos+size]));pos+=size;end=address+size
    if pos+4!=len(data):raise ValueError('Trailing IPS32 data')
    return records


def check_paths(nso, edits):
    """Fail if the frozen patch modifies a reviewed EP0 instruction/table."""
    covered={**RANGES,'interface_vtable':(0x8fed0,0x8ff58)}
    permitted=(0x30898,branch(0x30898,0x30f70,True))
    for address,data in edits:
        for label,(begin,end) in covered.items():
            lo,hi=max(begin,address),min(end,address+len(data))
            if lo>=hi:continue
            if (lo,hi)==(permitted[0],permitted[0]+4) and label=='controller_events':
                if read_mapped(nso,lo,4)!=permitted[1]:raise ValueError('Transfer hook original changed')
                continue
            raise ValueError('Patch changes reviewed EP0 path: '+label)
    return dict(reviewed_paths_unchanged=True,
                controller_exception=dict(address='0x30898',kind='transfer_type_0x20_call',
                                          setup_type_0x3f_branch_unchanged=True))


def machine_checks(nso):
    pointers=struct.unpack('<17Q',read_mapped(nso,0x8fed0,17*8))
    if pointers[5:7]!=(0x27d50,0x27d60):raise ValueError('Setup command vtable mismatch')
    direct=((0x27d54,0x2cf00,False),(0x27d6c,0x2cf90,False),
            (0x2cfb0,0x2a150,True),(0x2a114,0xba60,True),(0x2a134,0xbab0,True),
            (0x2a180,0xba60,True),(0x2a1ac,0x60e40,True),(0x2a1b8,0xb4a0,True),
            (0x2a1c4,0xbab0,True),(0x308cc,0x2a0f0,True),(0x308d4,0x2a2c0,True),
            (0x2ab68,0xb470,True),(0x2ab74,0xb470,True),
            (0x2ab84,0xb470,True),(0x2aba0,0xb470,False))
    for address,target,link in direct:
        if read_mapped(nso,address,4)!=branch(address,target,link):
            raise ValueError('Machine branch mismatch: '+hex(address))
    anchors={0x2a12c:0xf90bf668, # str x8, [x19,#0x17e8]
             0x2a194:0x5282fd08, # mov w8,#0x17e8
             0x2a198:0xf10022df, # cmp x22,#8
             0x2cfa4:0x91048004, # interface event address +0x120
             0x2cfa8:0x2a1f03e1, # endpoint selector 0
             0x2cfb4:0x2a1f03e0, # interface wrapper returns 0
             0x191d4:0xd4000221,0x191dc:0xd4000241}
    for address,word in anchors.items():
        if read_mapped(nso,address,4)!=struct.pack('<I',word):
            raise ValueError('Machine anchor mismatch: '+hex(address))
    return dict(interface_vtable_address='0x8fed0', setup_event_slot='0x28',
                setup_read_slot='0x30', vtable_targets=[hex(v) for v in pointers],
                checked_direct_branches=len(direct),checked_instruction_anchors=len(anchors))


def host_timing():
    rows=[json.loads(line) for line in (RUN/'host/session.jsonl').read_text().splitlines()]
    num,den=(rows[0]['details'][key] for key in ('timebase_numerator','timebase_denominator'))
    events={r['details']['event']:r['details']['details'] for r in rows if r['event']=='adapter'}
    trigger=events['trigger_return']['start_ticks']
    def ms(t):return (t-trigger)*num/den/1000000
    after=events['status_after']['observation']
    return dict(control_callback_ms=ms(events['control_callback']['arrival_ticks']),
                after_status_begin_ms=ms(after['begin_ticks']),after_status_end_ms=ms(after['end_ticks']),
                timebase_numerator=num,timebase_denominator=den,
                host_begin_is_bus_arrival=False,device_clock_alignment_verified=False)


def source_probe(output,timing):
    template=(ROOT/'tests/a23_ep0_dispatch_fixture.c').read_text()
    services=template.split('/* INSERT_ACTUAL_SOURCE */')[0]
    names={'record_log':'legacy_record_log','eventWait':'legacy_eventWait','waitMulti':'legacy_waitMulti',
           'usbDsInterface_GetSetupPacket':'legacy_GetSetupPacket',
           'usbDsInterface_CtrlInPostBufferAsync':'legacy_CtrlInPost'}
    defines='\n'.join('#define '+k+' '+v for k,v in names.items())+'\n'
    undef='\n'.join('#undef '+k for k in names)+'\n'
    fixture=ROOT/'tests/a23_hos_setup_fixture.c'
    text=fixture.read_text()
    if text.count('/* INSERT_ACTUAL_SOURCE */')!=1:raise ValueError('Invalid source marker')
    generated=defines+services+undef+text.replace('/* INSERT_ACTUAL_SOURCE */',actual_source())
    (output/'shared-setup-probe.c').write_text(generated)
    command=['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function',
             '-fsanitize=address,undefined','-fno-omit-frame-pointer','-g',
             '-DISO_PROBE','-DISO_PROBE_BURST_MODE','-DISO_PROBE_EVENT_AUDIT',
             '-DISO_PROBE_CONTEXT_AUDIT','-DISO_PROBE_FOLLOWUP_SIA',
             '-DSTATUS_BEGIN_NS='+str(math.ceil(timing['after_status_begin_ms']*1000000)),
             '-DSTATUS_END_NS='+str(math.ceil(timing['after_status_end_ms']*1000000)),
             '-I'+str(REPO),str(output/'shared-setup-probe.c'),'-o',str(output/'shared-setup-probe')]
    subprocess.run(command,check=True,capture_output=True,text=True)
    rows=[]
    for name in SCENARIOS:
        result=subprocess.run([str(output/'shared-setup-probe'),name],check=True,capture_output=True,text=True)
        if result.stderr:raise ValueError('Unexpected sanitizer output: '+result.stderr)
        rows.append(json.loads(result.stdout))
    return dict(kind='actual_client_source_with_modeled_hos_services',scenarios=rows,
                scenario_count=len(rows),compiler_command=command,fixture_sha256=sha(fixture),
                hardware_observation=False,hos_machine_code_emulated=False,
                log_durations_and_bus_arrival_assumed=True)


def audit(output,module):
    verified=[verify(p) for p in (RUN,CARD,COLLECTION,PACKAGE)]
    original=(module/'exefs/main').read_bytes();nso=validate_module(original)
    segments=bind_elf(original,(module/'usb.elf').read_bytes())
    validation=json.loads((PACKAGE/'validation.json').read_text())
    for name in ('source/uvc/uvc_device.c','source/sysmodule/main.c','source/uvc/iso_probe_protocol.h'):
        if sha(REPO/name)!=validation['sources_sha256'][name]:raise ValueError('Source differs from frozen A23')
    manifest=json.loads((PACKAGE/'manifest.json').read_text())
    ips=PACKAGE/'atmosphere/exefs_patches/SysDVR-ISO'/(BUILD_ID+'.ips')
    if sha(ips)!=manifest['patch_sha256']:raise ValueError('Frozen patch hash mismatch')
    records=parse_ips(ips.read_bytes())
    if records!=sorted((int(e['address'],16),bytes.fromhex(e['after'])) for e in manifest['edits']):
        raise ValueError('IPS differs from frozen edit manifest')
    for entry in manifest['edits']:
        before=bytes.fromhex(entry['before'])
        if read_mapped(nso,int(entry['address'],16),len(before))!=before:raise ValueError('Patch original mismatch')
    patch_scope=check_paths(nso,records);machine=machine_checks(nso)
    blocks={}
    for block in re.split(r'(?=// ---- )',(module/'decompiled.c').read_text()):
        found=re.search(r'@ ([0-9a-f]+)',block)
        if found:blocks[int(found[1],16)]=block
    # Decompiled excerpts aid review; machine listings and bound bytes are the evidence.
    for name,(begin,end) in RANGES.items():
        listing=subprocess.check_output(['/opt/devkitpro/devkitA64/bin/aarch64-none-elf-objdump',
                    '-d','--start-address='+hex(begin),'--stop-address='+hex(end),str(module/'usb.elf')],text=True)
        (output/(name+'.asm.txt')).write_text(listing)
        excerpts=''.join(block for address,block in blocks.items() if begin<=address<end)
        (output/(name+'.decompiled.txt')).write_text(excerpts)
    timing=host_timing();probe=source_probe(output,timing)
    ticket=PRIVATE/'analysis/A23-IOUSBHost-burst-next-test.json'
    if ticket.read_bytes()!=(CARD/'ticket-after.json').read_bytes():raise ValueError('Ticket differs from saved card cycle')
    result=dict(schema='A23-HOS-shared-setup-audit-1',root_cause_confirmed=False,fix_verified=False,
                usb_accessed=False,sd_accessed=False,acquisition_state_modified=False,firmware_modified=False,
                verified_evidence=verified,original_nso_sha256=hashlib.sha256(original).hexdigest(),
                hos_elf_sha256=sha(module/'usb.elf'),hos_elf_load_segments=segments,
                decompiled_input_sha256=sha(module/'decompiled.c'),decompile_independently_regenerated=False,
                frozen_patch_sha256=sha(ips),patch_records=len(records),patch_scope=patch_scope,
                machine_binding=machine,host_timing=timing,source_probe=probe,ticket_sha256=sha(ticket),
                setup_model=dict(storage_offset='0x17e8',lock_offset='0x17f0',bytes=8,
                                 interface_event_offset='0x120',event_slots_offset='0x1810',event_slots=4,
                                 per_interface_queue=False,read_clears_interface_event=True,
                                 timeout_alone_invalidates_setup_proven=False))
    (output/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    (output/'SHA256SUMS').write_text(''.join(sha(p)+'  '+p.name+'\n' for p in sorted(output.iterdir()) if p.is_file()))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--module',type=Path,default=archive_path()/'module')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    result=audit(args.output,args.module)
    print(json.dumps(dict(output=str(args.output),scenario_count=result['source_probe']['scenario_count'],
                         machine_binding=result['machine_binding'],host_timing=result['host_timing'],
                         root_cause_confirmed=False),indent=2))


if __name__=='__main__':main()
