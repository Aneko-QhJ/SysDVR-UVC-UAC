#!/usr/bin/env python3
"""Offline replay matrix and sequence-witness feasibility audit. Never acquire.

Compile a verbatim frozen C handler with injected services on this Mac. This is
not a receiver build, ARM execution, a reserved sequence, or permission to test.
"""
import argparse
import json
from pathlib import Path
import subprocess

import a23_sequence_witness_model as model
import collect_a23_lead32_envelope as envelope
import prepare_a23_lead32_once as once
import path_span_card_workflow as card

b=once.build;ROOT=b.ROOT;A=once.ANALYSIS
NEW=('tools/a23_sequence_witness_model.py','tools/audit_a23_sequence_witness.py',
     'tests/a23_sequence_witness_fixture.c','tests/test_a23_sequence_witness_model.py')


def handler(text):
    start=text.index('static void _handleIsoSetup(')
    return text[start:text.index('\n#endif\n\nstatic void _handleSetupPacket',start)]


def run(output):
    output=Path(output)
    b.require(output.is_absolute() and output==output.resolve() and not output.exists() and
              (output.parent==A or Path('/private/tmp') in output.parents),'new analysis or temporary directory required')
    pending=b.plain(A/'A23-lead32-pending.json')
    validation=b.load(A/'A23-lead32-workflow-validation-20261017/validation.json')
    hashes=dict(validation['source_hashes']);b.require(len(hashes)==251,'expected frozen source closure')
    for name,h in hashes.items():b.require(b.sha(b.plain(b.REPO/name))==h,'prior source changed: '+name)
    for name in NEW:hashes['research/usb-ds-iso/'+name]=b.sha(b.plain(ROOT/name))
    records={p.name:b.plain(p) for p in A.glob('A23-lead32-once-20261017-*.json')}
    b.require(len(records)==3,'unexpected lead32 records')
    for raw in records.values():
        value=json.loads(raw);b.require(value['remaining']==0 and value['acquisition_enabled'] is False,'live record not dormant')
    binding=b.load(A/'A23-lead32-receiver-review-20261017-r4/receiver-build/device-binding.json')
    device=Path(binding['device_source_root']);card.seal_verify(device.parent)
    snapshot=ROOT/'private/card-cycles/20261017-133944-lead32-repeat1-live-read'
    card.verify_snapshot(snapshot);source= b.plain(device/'source/uvc/uvc_device.c').decode();actual=handler(source)
    b.require('g_isoStatus.sequence = setup->wValue;' in actual and
              'isoProbeByte((uint16_t)(setup->wValue + packet), i)' in actual,'sequence echo path changed')
    output.mkdir(mode=0o700)
    for name in NEW:card.pkg.put(output,'inputs/'+name,b.plain(ROOT/name))
    for name,raw in records.items():card.pkg.put(output,'records/'+name,raw)
    card.pkg.put(output,'pending.before.json',pending)
    matrix=[];files=snapshot/'card';recipe=binding['runtime_recipe_sha256']
    for label,run_name in [('first','A-A23-lead32-waiting-20261017-051230-52dbb0b2'),
                           ('repeat1','A-A23-lead32-waiting-20261017-053747-70aa8f79')]:
        run_path=ROOT/'private/runs'/run_name;card.seal_verify(run_path)
        for ex in sorted(files.glob('ep0-*.execution.bin')):
            primary=ex.with_name(ex.name.replace('.execution.bin','.capture.bin'))
            if not primary.exists():primary=ex.with_name(ex.name.replace('.execution.bin','.diagnostic.bin'))
            checked=envelope.analyze_inputs(run_path/'host',ex,recipe,primary)
            name=label+'-'+ex.stem+'.json';card.pkg.put(output,'matrix/'+name,b.canonical(checked))
            matrix.append(dict(host=label,execution=ex.name,execution_sha256=b.sha(b.plain(ex)),
                consistent=checked['supplied_comparison_consistent'],comparison=checked.get('comparison'),
                physical_run_authenticated=False))
    b.require(len(matrix)==10 and sum(r['consistent'] for r in matrix)==4,'unexpected replay matrix')
    b.write(output/'replay-matrix.json',matrix)
    model_dir=output/'native-model';model_dir.mkdir()
    fixture=(ROOT/'tests/a23_sequence_witness_fixture.c').read_text()
    b.require(fixture.count('/* INSERT_FROZEN_HANDLER */')==1,'fixture marker changed')
    card.pkg.put(model_dir,'frozen-handler.c',actual.encode())
    card.pkg.put(model_dir,'iso_probe_protocol.h',b.plain(device/'source/uvc/iso_probe_protocol.h'))
    card.pkg.put(model_dir,'probe.c',fixture.replace('/* INSERT_FROZEN_HANDLER */',actual).encode())
    command=['/usr/bin/cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function',
             '-fsanitize=address,undefined','-fno-omit-frame-pointer','-g','-DISO_PROBE_BURST_MODE',
             '-I'+str(model_dir),str(model_dir/'probe.c'),'-o',str(model_dir/'probe')]
    compiled=subprocess.run(command,capture_output=True,text=True)
    b.write(output/'compiler.json',dict(command=command,returncode=compiled.returncode,stdout=compiled.stdout,stderr=compiled.stderr))
    b.require(compiled.returncode==0,'native model compilation failed; preserve compiler.json')
    cases=[]
    for seed,mode in [(s,'normal') for s in (0,1,17,33,65505,65520,65521,65535)]+[(17,s) for s in
                      ('pending','retained','wrong-interface','admission-denied','speed-error','post-failed')]:
        raw=model_dir/(str(seed)+'-'+mode+'.bin')
        proc=subprocess.run([str(model_dir/'probe'),str(seed),mode,str(raw)],capture_output=True,text=True)
        b.write(model_dir/(raw.stem+'.result.json'),dict(returncode=proc.returncode,stdout=proc.stdout,stderr=proc.stderr))
        b.require(proc.returncode==0 and not proc.stderr,'native model failed: '+raw.stem)
        value=json.loads(proc.stdout)
        if mode=='normal':
            b.require(b.plain(raw)==model.expected_payload(seed),'frozen handler payload differs from independent Python decoder')
            value['comparison']=model.compare_model(seed,seed,value['trace_sequence'],value['status_sequence'],b.plain(raw))
            b.require(value['comparison']['supplied_sequence_agreement'],'model sequence chain mismatch')
        cases.append(dict(seed=seed,mode=mode,observation=value,payload_sha256=b.sha(b.plain(raw))))
    proposed=model.propose_block([1,1]);b.require(proposed==17,'model proposal changed')
    b.write(output/'modeled-old-record-rejection.json',dict(proposed=proposed,proposal_reserved=False,
        global_historical_ledger_complete=False,old=model.compare_model(proposed,1,1,1,model.expected_payload(1)),
        matching=model.compare_model(proposed,proposed,proposed,proposed,model.expected_payload(proposed))))
    protected=b.load(A/'A23-path-span-readiness-review-20261016/protected-inputs.json')
    for group,root in [('production',b.REPO),('tickets',A),('offline_records_sha256',A)]:
        for name,h in protected[group].items():b.require(b.sha(b.plain(root/name))==h,'protected input changed')
    old_live=b.load(A/'A23-lead32-receiver-review-20261017-r4/audit.json')['live_records_sha256']
    for name,h in old_live.items():b.require(b.sha(b.plain(A/name))==h,'old live record changed')
    for name,h in hashes.items():b.require(b.sha(b.plain(b.REPO/name))==h,'source changed during audit')
    for name,raw in records.items():b.require(b.plain(A/name)==raw,'lead32 record changed')
    b.require(b.plain(A/'A23-lead32-pending.json')==pending,'pending changed during audit')
    result=dict(schema='A23-sequence-witness-feasibility-1',source_hashes=hashes,prior_sources_unchanged=251,
        device_source_sha256=b.sha(source.encode()),handler_sha256=b.sha(actual.encode()),device_elf_sha256=binding['device_elf_sha256'],
        runtime_recipe_sha256=recipe,reference_device_directory=str(device),replay_matrix_count=10,replay_consistent_pairs=4,
        native_model_cases=cases,proposed_next_block=proposed,proposal_reserved=False,
        firmware_rebuild_required_by_source_model=False,existing_receiver_accepts_variable_sequence=False,
        existing_parser_accepts_variable_sequence=False,new_host_receiver_built=False,new_issuer_implemented=False,
        historical_global_uniqueness_verified=False,cryptographic_authentication=False,physical_run_authenticated=False,
        root_cause_confirmed=False,hardware_verified=False,usb_strict_pass=False,sd_accesses=0,usb_requests=0,
        remaining=0,attempt_issued=False)
    b.write(output/'audit.json',result);b.seal(output);card.seal_verify(output);return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);a=p.parse_args();r=run(a.output)
    print(json.dumps(dict(sources=len(r['source_hashes']),matrix=r['replay_matrix_count'],consistent=r['replay_consistent_pairs'],
                         native_cases=len(r['native_model_cases']),proposed=r['proposed_next_block'],reserved=False,remaining=0)))
