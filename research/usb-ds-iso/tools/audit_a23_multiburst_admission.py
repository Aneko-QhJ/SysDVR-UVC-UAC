"""File-only bounded multiburst research; no receiver, firmware, USB or card API.

Native service fixtures exercise copied deployed ISO/dispatch functions. The
Python coordinator is a proposed protocol model, never executable permission.
"""
import argparse
from dataclasses import dataclass
from pathlib import Path
import json
import re
import subprocess
import context65_baseline63 as w
from workflows.artifacts import verify as legacy_verify

PARENT=w.A/'A23-context65-first-live-closeout-20261018'
PARENT_SUM='986c331bbc9c67ad653e02b68e9591081e0de4919530c9152f8cb004bd8e77ec'
FIXTURE=w.A/'A23-bounded-candidate-review-20261014'
NEW=('tools/audit_a23_multiburst_admission.py','tests/a23_multiburst_admission.c','tests/test_a23_multiburst_admission.py')
SIGNATURES=('static void _pollIsoProbe(void)',
    'static void _handleIsoSetup(UsbDsInterface* iface, const UsbSetupPacket* setup)',
    'static bool _serviceSetup(UsbDsInterface* iface)','static void _candidateProcessRequests(void)',
    'void UvcDeviceProcessRequests(void)')
CASES=('single','full-two','chained-two','chained-three','chained-extra','pending','foreign-terminal','report-error',
    'duplicate-id','terminal4','terminal5','disconnect','full-four','chained-five','chained-six','five-extra',*('prefix-'+str(n) for n in range(257)))


def sources():
    w.card.seal_verify(PARENT);w.require(w.sha(w.plain(PARENT/'SHA256SUMS'))==PARENT_SUM,'live closeout changed')
    parent=w.load(PARENT/'closeout.json');current=w.hashes()
    w.require(current==parent['source_hashes'] and len(current)==310,'old310 source drift')
    for name,digest in parent['protected_sha256'].items():w.require(w.sha(w.plain(Path(name)))==digest,'protected state changed: '+name)
    for name in NEW:
        key='research/usb-ds-iso/'+name;w.require(key not in current,'new source overlap');current[key]=w.sha(w.plain(w.ROOT/name))
    return dict(sorted(current.items()))


def function_span(text,signature):
    w.require(text.count(signature)==1,'ambiguous function anchor: '+signature)
    start=text.index(signature);begin=text.index('{',start);depth=0
    tokens=re.compile(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[{}]',re.S)
    for token in tokens.finditer(text,begin):
        if token.group()=='{':depth+=1
        elif token.group()=='}':
            depth-=1
            if depth==0:return start,token.end()
    raise ValueError('unterminated function anchor')


def native_source():
    legacy_verify(FIXTURE)
    record=w.load(w.OFFLINE);device=Path(record['device_binding']['device_source_root'])
    w.verify_build(record)
    actual=w.plain(device/'source/uvc/uvc_device.c').decode()
    text=w.plain(FIXTURE/'bounded-buffers.c').decode();text=text[:text.index('int main(')]
    snippets={}
    for signature in SIGNATURES:
        a,b=function_span(actual,signature);snippet=actual[a:b];x,y=function_span(text,signature)
        text=text[:x]+snippet+text[y:];snippets[signature]=dict(sha256=w.sha(snippet.encode()),device_line=actual[:a].count('\n')+1)
    headers=('ep0_trace.h','ep0_trace_owner.h','ep0_buffer_guard.h','ep0_candidate_guard.h','ep0_request_admission.h')
    legacy_verify(device.parent)
    header_hashes={name:w.sha(w.plain(device/'source/uvc'/name)) for name in headers}
    def deployed_include(match):
        path=device/'source/uvc'/match[1];w.plain(path)
        return '#include '+json.dumps(str(path))
    text=re.sub(r'#include \"research/usb-ds-iso/device/([^\"]+)\"',deployed_include,text)
    text=text.replace('#include \"source/uvc/iso_probe_protocol.h\"','#include '+json.dumps(str(device/'source/uvc/iso_probe_protocol.h')))
    for name in ('ep0_request_admission.c','ep0_candidate_guard.c'):
        body=w.plain(device/'source/uvc'/name).decode().split('\n',1)[1].strip()
        w.require(body in text,'deployed policy implementation differs: '+name)

    return text+'\n'+w.plain(w.ROOT/'tests/a23_multiburst_admission.c').decode(),dict(
        device_source=str(device),device_elf_sha256=record['device_binding']['device_elf_sha256'],
        deployed_functions=snippets,policy_headers=header_hashes,deployed_trace_capacity=256,deployed_owner_slots=32,device_manifest_sha256=w.sha(w.plain(device.parent/'SHA256SUMS')),native_fixture_manifest_sha256=w.sha(w.plain(FIXTURE/'SHA256SUMS')),
        prefix_is_injected=True,usb_service_outcomes_injected=True,thread_join_success_injected=True)


def strict_int(value,low,high):return type(value) is int and low<=value<=high


@dataclass
class Owner:
    ordinal:int
    first:int
    data_id:int
    transactions_id:int
    callbacks:int=0
    control_callbacks:int=0
    triggered:bool=False
    saved:bool=False
    quarantined:bool=False


class ContinuationModel:
    """Proposed two-burst ordering and ownership, with all inputs injected.

    No allocation or SDK binding is implied by the distinct integer identities.
    Old stores are kept in the model for the entire session, including failures.
    """
    def __init__(self,first=81,count=2):
        w.require(strict_int(first,81,65504) and (first-1)%16==0 and type(count) is int and count==2 and first+31<=65535,
            'unallocated aligned32-sequence model scope required')
        self.first=first;self.limit=count;self.owners=[];self.phase='ready';self.reason=None
    def fail(self,reason):
        if self.phase!='stopped':self.reason=reason
        self.phase='stopped'
        for owner in self.owners:owner.quarantined=True
        return False
    def submit(self):
        if self.phase!='ready' or len(self.owners)>=self.limit:return self.fail('not_ready_or_limit')
        ordinal=len(self.owners);owner=Owner(ordinal,self.first+ordinal*16,ordinal*2+1,ordinal*2+2)
        self.owners.append(owner);self.phase='submitted';return owner
    def trigger(self):
        if self.phase!='submitted' or self.owners[-1].callbacks or self.owners[-1].triggered:return self.fail('trigger_order')
        self.owners[-1].triggered=True;self.phase='pending';return True
    def control_callback(self,ordinal,status=0):
        if self.phase not in ('pending','verifying') or not strict_int(ordinal,0,len(self.owners)-1):return self.fail('control_order')
        owner=self.owners[ordinal]
        if owner is not self.owners[-1] or owner.control_callbacks or not strict_int(status,0,0):return self.fail('control_identity_or_status')
        owner.control_callbacks+=1;return True
    def callback(self,ordinal,*,pointer_matches=True,status=0,actual=3072,sequences=None):
        if self.phase!='pending' or not strict_int(ordinal,0,len(self.owners)-1):return self.fail('callback_order')
        owner=self.owners[ordinal]
        if owner is not self.owners[-1] or owner.callbacks or not owner.triggered:return self.fail('callback_identity')
        owner.callbacks+=1
        if pointer_matches is not True or not strict_int(status,0,0) or not strict_int(actual,3072,3072) or \
            type(sequences) is not list or any(type(n) is not int for n in sequences) or sequences!=list(range(owner.first,owner.first+16)):
            return self.fail('callback_content')
        self.phase='verifying';return True
    def complete(self,device,*,saved=True):
        if self.phase!='verifying' or saved is not True:return self.fail('save_or_phase')
        owner=self.owners[-1]
        expected=dict(sequence=owner.first,state=2,urb_status=3,requested=3072,transferred=3072,
            iso7_bitmap=65535,iso7_actual=3072,iso7_terminal=1)
        if type(device) is not dict or owner.control_callbacks!=1:return self.fail('device_or_control_missing')
        if any(type(device.get(k)) is not int or device[k]!=v for k,v in expected.items()):return self.fail('device_witness')
        if not strict_int(device.get('urb_id'),1,2**32-1) or type(device.get('report_id')) is not int or device['report_id']!=device['urb_id']:
            return self.fail('urb_identity')
        if device.get('trace_lossless') is not True:return self.fail('trace_loss')
        owner.saved=True;self.phase='complete' if len(self.owners)==self.limit else 'ready';return True
    def stop(self,reason='exit_or_timeout'):return self.fail(reason)


def witness(first):
    return dict(sequence=first,state=2,urb_status=3,requested=3072,transferred=3072,
        iso7_bitmap=65535,iso7_actual=3072,iso7_terminal=1,urb_id=387+first,report_id=387+first,trace_lossless=True)


def model_cases():
    results={}
    for mode in ('normal','late-old-callback','pointer-mismatch','terminal-failure','save-failure','missing-control','detach','timeout'):
        m=ContinuationModel();o=m.submit();m.trigger()
        m.control_callback(0);m.callback(0,sequences=list(range(81,97)))
        m.complete(witness(81));second=m.submit();m.trigger()
        if mode=='late-old-callback':m.callback(0,sequences=list(range(81,97)))
        elif mode=='pointer-mismatch':m.callback(1,pointer_matches=False,sequences=list(range(97,113)))
        elif mode in ('detach','timeout'):m.stop(mode)
        else:
            if mode!='missing-control':m.control_callback(1)
            m.callback(1,sequences=list(range(97,113)));d=witness(97)
            if mode=='terminal-failure':d['urb_status']=4
            m.complete(d,saved=mode!='save-failure')
        w.require(m.phase==('complete' if mode=='normal' else 'stopped'),'bad model outcome')
        w.require(o.data_id!=second.data_id and o.transactions_id!=second.transactions_id,'model storage reused')
        results[mode]=dict(phase=m.phase,reason=m.reason,owners=len(m.owners),quarantined=sum(o.quarantined for o in m.owners),
            distinct_storage_identities=True,stores_retained_for_entire_model_session=True)
    return results


def run(output):
    output=w.canonical(output);w.require(not output.exists(),'new offline multiburst audit required');before=sources();output.mkdir(mode=0o700)
    text,binding=native_source();original_text=text
    device=Path(binding['device_source'])/'source/uvc'
    headers={p.name:w.plain(p) for p in sorted(device.glob('*.h'))}
    for name,raw in headers.items():w.card.put(output,'deployed-headers/'+name,raw)
    w.card.put(output,'deployed-input/uvc_device.c',w.plain(device/'uvc_device.c'))
    text=text.replace(str(device)+'/','deployed-headers/')
    cfile=output/'injected-device.c';cfile.write_text(text)
    binary=output/'injected-device'
    flags=['-DISO_PROBE','-DISO_PROBE_BURST_MODE','-DISO_PROBE_EVENT_AUDIT','-DISO_PROBE_CONTEXT_AUDIT','-DISO_PROBE_FOLLOWUP_SIA']
    command=['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-fsanitize=address,undefined',
        '-fno-omit-frame-pointer','-g','-I'+str(w.b.REPO),*flags,str(cfile),'-o',str(binary)]
    compiled=subprocess.run(command,capture_output=True,text=True)
    w.write(output/'compiler.json',dict(command=command,returncode=compiled.returncode,stdout=compiled.stdout,stderr=compiled.stderr))
    w.require(compiled.returncode==0,'native fixture compilation failed; see compiler.json')
    rows={}
    for case in CASES:
        result=subprocess.run([str(binary),case],capture_output=True,text=True)
        w.card.put(output,'native/'+case+'.stdout',result.stdout.encode());w.card.put(output,'native/'+case+'.stderr',result.stderr.encode())
        w.require(result.returncode==0,'native model failed: '+case);row=json.loads(result.stdout)
        w.require(not row['dropped'] and not row['model_copy_overlaps'] and not row['model_pointer_reposts'],'native loss/overlap')
        rows[case]=row
    models=model_cases();after_text,after_binding=native_source()
    w.require(after_text==original_text and after_binding==binding and
        {p.name:w.plain(p) for p in sorted(device.glob('*.h'))}==headers,'deployed inputs changed during audit')
    w.require(sources()==before,'sources changed during audit')
    result=dict(schema='A23-multiburst-admission-review-1',passed=True,source_hashes=before,source_count=len(before),prior_sources_unchanged=310,
        native_binding=binding,native_cases=rows,native_case_count=len(rows),coordinator_models=models,coordinator_case_count=len(models),
        proposed_sequences=[dict(first=81,last=96),dict(first=97,last=112)],sequences_allocated=False,
        remaining=0,acquisition_enabled=False,usb_requests=0,sd_accesses=0,formal_reservations=0,formal_records=0,real_sdk_objects=0,
        receiver_acquire_invoked=False,firmware_built=False,device_package_changed=False,hardware_verified=False,continuous_streaming_verified=False)
    w.write(output/'audit.json',result);w.b.seal(output);w.card.seal_verify(output);return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);args=p.parse_args();r=run(args.output)
    print(json.dumps(dict(sources=r['source_count'],native_cases=r['native_case_count'],coordinator_cases=r['coordinator_case_count'],remaining=0)))
