"""Offline execution of recovered ISO7 patch and injected host owner lifetimes.

No USB enumeration, SDK client creation, card access, reservation or receiver.
Unicorn executes producer/event hooks; original completion is a stopped boundary.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys

import audit_a23_multiburst_admission as prior

w=prior.w
PARENT=w.A/'A23-multiburst-admission-closeout-20261018'
PARENT_SUM='4cf8caf33f8748cd163796b3953bb9a26a880df818502a3892691696ce3b54a7'
PATCH=w.A/'A23-iso-retention-window-review-20261017-r3'
IPS_SUM='80991e082dda79da38f016b635715cec0bae4ec7c4963820a769cde17280416f'
NEW=('tools/audit_a23_rearm.py','tests/test_a23_rearm.py','tests/a23_rearm_owner.m','tests/test_patch.py')


def sources():
    w.card.seal_verify(PARENT)
    w.require(w.sha(w.plain(PARENT/'SHA256SUMS'))==PARENT_SUM,'parent closeout changed')
    parent=w.load(PARENT/'closeout.json');current=prior.sources()
    w.require(current==parent['source_hashes'] and len(current)==313,'prior313 drift')
    for name in NEW:
        key='research/usb-ds-iso/'+name
        w.require(key not in current,'new closure overlap')
        current[key]=w.sha(w.plain(w.ROOT/name))
    return dict(sorted(current.items()))


def patch_inputs(output):
    w.card.seal_verify(PATCH)
    manifest=w.load(PATCH/'patch-rebuild/manifest.json')
    from build_patch import BUILD_ID,validate_module,read_mapped,ips32
    module=w.plain(w.ROOT/'private/module/exefs/main');nso=validate_module(module)
    expected=dict(variant='A',frame_lead=0,mps=256,burst_packets=16,
        followup_sia=True,interval=1,diagnostics_magic='ISO7',retain_success=False)
    w.require(all(type(manifest[k]) is type(v) and manifest[k]==v for k,v in expected.items()),'wrong patch profile')
    edits=[]
    for edit in manifest['edits']:
        addr=int(edit['address'],16);raw=bytes.fromhex(edit['after'])
        w.require(read_mapped(nso,addr,len(raw)).hex()==edit['before'],'original patch bytes differ')
        edits.append((addr,raw))
    rebuilt=ips32(edits)
    w.require(len(edits)==22 and len(rebuilt)==905 and w.sha(rebuilt)==IPS_SUM,'recovered patch differs')
    snapshot=w.ROOT/'private/card-cycles/20261018-context65-first-live-read'
    saved=w.card.seal_verify(snapshot)
    name='card/atmosphere/exefs_patches/SysDVR-ISO/'+BUILD_ID+'.ips'
    w.require(saved[name]==rebuilt,'latest69 IPS differs')
    w.card.put(output,'inputs/private/module/exefs/main',module)
    (output/'inputs/packages/A').mkdir(parents=True)
    w.write(output/'inputs/packages/A/manifest.json',manifest)
    w.card.put(output,'inputs/recovered.ips',rebuilt)
    return dict(manifest_sha256=w.sha(w.plain(PATCH/'patch-rebuild/manifest.json')),
        patch_review=w.reference(PATCH),snapshot=w.reference(snapshot),ips_sha256=IPS_SUM,
        module_sha256=w.sha(module),edits=22,firmware_rebuilt=False,
        metadata_frame_lead=0,effective_machine_code_lead_frames=32)


def machine_module(inputs):
    sys.path.insert(0,str(w.ROOT/'tests'))
    import test_patch as tp
    tp.ROOT=Path(inputs);tp.PACKAGES=Path(inputs)/'packages'
    return tp


def arm_cases(inputs):
    tp=machine_module(inputs);R=tp.RING;E=tp.ENTRY
    def state(m):
        terminal,bitmap,total=m.read(R+0xf8c,'<III')
        return dict(terminal=terminal,bitmap=bitmap,total=total,
            producer=(m.read(E+0x18,'<Q')[0]-R)//16,
            consumer=(m.read(E+0x20,'<Q')[0]-R)//16,
            cycle=m.read(E+0x40,'<B')[0])
    def pointer(start,p):return R+((start+2*p+1)%247)*16
    def complete(m,start):
        calls=[]
        for p in range(16):calls+=m.event(pointer(start,p),True)
        w.require(calls==[(0x2a980,[tp.MANAGER,0x83,0,1,3072,1])],'wrong original completion boundary')
        s=state(m);w.require(s['terminal']==1 and s['bitmap']==65535 and s['total']==3072 and s['producer']==s['consumer'],'bad completion')
    results={}
    for start in range(247):
        m=tp.Machine('A')
        sample=(start*67)%16384;m.write(tp.MMIO+0x48,'<I',sample)
        for off in (0x18,0x20):m.write(E+off,'<Q',R+start*16)
        cycle=m.read(E+0x40,'<B')[0]
        w.require(m.submit(3072)==0,'first producer rejected')
        first=state(m)
        w.require((m.read(R+0xf88,'<I')[0]>>20 & 2047)==(((sample>>3)+32)%2048),'effective lead is not32')
        # Pending and duplicate calls must not publish another ring.
        before=bytes(m.uc.mem_read(R,4096))
        w.require(m.submit(3072)==0x1908c and bytes(m.uc.mem_read(R,4096))==before,'pending producer changed ring')
        complete(m,start);done=state(m)
        for p in range(16):w.require(m.event(pointer(start,p),True)==[],'post-terminal event completed twice')
        second=done['producer'];sample=(sample+13)%16384;m.write(tp.MMIO+0x48,'<I',sample)
        w.require(m.submit(3072,dma=tp.DMA+4096)==0,'second producer rejected')
        w.require((m.read(R+0xf88,'<I')[0]>>20 & 2047)==(((sample>>3)+32)%2048),'second lead differs')
        w.require(m.read(R+second*16,'<Q')[0]==tp.DMA+4096,'second DMA not published')
        reset=state(m)
        w.require((reset['terminal'],reset['bitmap'],reset['total'])==(0,0,0),'mailbox not reset')
        w.require(m.read(R+0xf98,'<Q')[0]==R+second*16,'second first pointer stale')
        for p in range(16):
            w.require(m.event(pointer(start,p),True)==[] and state(m)==reset,'previous burst ED accepted in second')
        complete(m,second);end=state(m)
        w.require(end['producer']==(start+64)%247 and end['cycle']==(cycle^((start+64)//247)),'wrap/cycle mismatch')
        results['two-'+str(start)]=dict(first=first,first_complete=done,second_reset=reset,second_complete=end,
            old_events_accepted=0,completion_boundaries=2)
    for packet in range(16):
        m=tp.Machine('A');w.require(m.submit(3072)==0,'error first rejected')
        for p in range(packet):m.event(pointer(0,p),True)
        m.event(tp.RING_DMA+packet*32,False,23,0)
        failed=state(m);before=bytes(m.uc.mem_read(R,4096))
        w.require(failed['terminal']==0x80000017 and failed['consumer']==0,'error ownership advanced')
        w.require(m.submit(3072)==0x1908c and bytes(m.uc.mem_read(R,4096))==before,'error reposted')
        results['error-'+str(packet)]=dict(state=failed,second_rejected=True)
    # Every prior generation is injected after each publication. This is an
    # adversarial event stream, not evidence that the controller emits it.
    history=[];m=tp.Machine('A');alias=None
    for ordinal in range(1,17):
        start=state(m)['producer'];w.require(m.submit(3072)==0,'serial producer rejected')
        original=state(m)
        for old_start in history:
            for p in range(16):m.event(pointer(old_start,p),True)
        injected=state(m)
        if injected['bitmap']:
            alias=dict(ordinal=ordinal,start=start,after_old_events=injected,
                prior_generations=len(history),actual_current_events_delivered=0)
            break
        w.require(injected==original,'old event mutated unaliased publication')
        complete(m,start);history.append(start)
    w.require(alias is not None and alias['ordinal']==16,'unexpected first alias boundary')
    # Focused single-generation witness: first burst alone supplies nine of the
    # sixteenth burst bitmap bits before ANY sixteenth-burst success event.
    m=tp.Machine('A')
    for ordinal in range(1,16):
        start=state(m)['producer'];w.require(m.submit(3072)==0,'serial rejected');complete(m,start)
    start=state(m)['producer'];w.require(m.submit(3072)==0,'sixteenth rejected')
    for p in range(16):m.event(pointer(0,p),True)
    mixed=state(m)
    w.require(start==233 and mixed['bitmap']==0xff80 and mixed['total']==1728,'first generation alias differs')
    calls=[]
    for p in range(7):calls+=m.event(pointer(start,p),True)
    w.require(len(calls)==1 and state(m)['terminal']==1,'mixed-generation witness did not complete')
    results['old-generation-alias']=dict(first_alias=alias,first_generation_only=mixed,
        genuine_current_success_events=7,stale_success_events_counted=9,mixed_completion=state(m),
        controller_emission_observed=False,host_payload_or_urb_success_implied=False)
    # Exact same first slot returns after 247 publications (32 coprime to247).
    results['geometry']=dict(ring_slots=247,slots_per_burst=32,first_slot_repeat_period=247,
        earliest_prior_ED_overlap_burst=16,two_bursts_disjoint_for_all_starts=True,
        event_generation_token_present=False,urb_id_visible_in_event_handler=False)
    return results


def run(output):
    output=w.canonical(output);w.require(not output.exists(),'new rearm review required')
    before=sources();output.mkdir(mode=0o700);binding=patch_inputs(output)
    arm=arm_cases(output/'inputs')
    for name in ('host/io_usb_host_transaction_owner.h','host/io_usb_host_transaction_owner.m','tests/a23_rearm_owner.m'):
        w.card.put(output,'native/'+name,w.plain(w.ROOT/name))
    command=['clang','-fobjc-arc','-fblocks','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
        '-fno-omit-frame-pointer','-g','-framework','Foundation','-framework','IOUSBHost',
        str(output/'native/host/io_usb_host_transaction_owner.m'),str(output/'native/tests/a23_rearm_owner.m'),
        '-o',str(output/'native/owner-test')]
    built=subprocess.run(command,capture_output=True,text=True)
    w.card.put(output,'compile.log',(built.stdout+built.stderr).encode());w.require(built.returncode==0,'native owner compile failed')
    native=subprocess.run([str(output/'native/owner-test')],capture_output=True,text=True)
    w.card.put(output,'native.stdout',native.stdout.encode());w.card.put(output,'native.stderr',native.stderr.encode())
    w.require(native.returncode==0,'native owner test failed');host=json.loads(native.stdout)
    # Preserve concrete current capability blockers, rather than treating a mock
    # transport as a reusable SDK lease or changing the old one-shot guard.
    adapter=w.plain(w.ROOT/'host/io_usb_host_sdk_adapter.m').decode()
    checks=('if (_pipe)', '_burstAttempted=YES;', '_transport = nil;',
        'lease.dataStorage = [interface allocate:184320 shared:NO',
        'lease.transactionStorage = [interface allocate:26880 shared:YES')
    w.require(all(s in adapter for s in checks),'current resource capability changed')
    capability=dict(current_lease_one_burst=True,current_lease_owns_one_pair=True,
        close_destroys_shared_interface=True,new_two_epoch_session_owner_required=True,
        prototype_uses_foundation_stores=True,sdk_allocations_tested=False,real_sdk_objects=0)
    w.require(sources()==before,'source drift during review')
    result=dict(schema='A23-rearm-audit-1',source_hashes=before,source_count=len(before),prior_sources_unchanged=313,
        binding=binding,arm=arm,host=host,host_capability=capability,
        arm_two_start_cases=247,arm_error_cases=16,completed_original_function_emulated=False,
        original_completion_boundary_stopped=True,events_and_hardware_context_injected=True,
        actual_URB_generation_service_emulated=False,device_package_reuse_established=False,
        usb_requests=0,sd_accesses=0,formal_reservations=0,real_sdk_objects=0,remaining=0,
        hardware_verified=False,continuous_streaming_verified=False,passed=True)
    w.write(output/'audit.json',result);w.b.seal(output)
    return dict(output=str(output),reference=w.reference(output),source_count=len(before),
        two_start_cases=247,error_cases=16,first_alias_burst=16,host=host,passed=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    print(json.dumps(run(parser.parse_args().output),indent=2))
