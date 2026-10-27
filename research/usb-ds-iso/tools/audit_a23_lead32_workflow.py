#!/usr/bin/env python3
"""Exercise copied static files and file-only claims. No issuer or acquisition."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import struct
import zlib

import build_a23_lead32_receiver as b
import collect_a23_lead32_execution as c
import analyze_a23_lead32_entry as waiting
import analyze_io_usb_host_lead32 as sdk
import path_span_card_workflow as card
from workflows import capture_a23_lead32_receiver as gate

PARENT=b.ROOT/'private/analysis/A23-lead32-receiver-review-20261017-r4'
SERIALIZERS=b.ROOT/'private/analysis/A23-path-span-receiver-review-20261016'
NAME='ep0-life-'+('03'+'00'*15)+'.bin'


def run(output):
    output=Path(output);b.require(output.is_absolute() and output==output.resolve() and not output.exists(),'new workflow review required')
    card.seal_verify(PARENT);card.seal_verify(SERIALIZERS)
    source=b.load(PARENT/'offline-record.json');build=b.verify_build(source)
    output.mkdir(mode=0o700)
    native={}
    for group,fn,expected in [('driver-models',sdk.analyze,{'final-save-failed','retained-save-failed'}),
                              ('loop-models',waiting.analyze,{'signal-before-begin'})]:
        rows={}
        for path in sorted((PARENT/group).iterdir()):
            try:rows[path.name]=dict(valid=True,analysis=fn(path));b.require(path.name not in expected,'expected incomplete journal passed')
            except ValueError as error:
                b.require(path.name in expected,'unexpected new analysis failure '+path.name+': '+str(error))
                rows[path.name]=dict(valid=False,error=str(error),raw_preserved_in=str(path))
        native[group]=rows
    models=SERIALIZERS/'models';runs=output/'mock-runs';runs.mkdir()
    base=runs/'matching';base.mkdir();shutil.copytree(PARENT/'loop-models/normal',base/'host')
    mock={**source,'stage':'consumed','artifact_origin':'injected_consumed_model','run':str(base)}
    b.write(base/'record.json',mock);b.write(base/'waiting-authorization.json',b.device.receipt(mock))
    for mode in ('--claim-process-only','--claim-sdk-only'):
        subprocess.run([str(PARENT/'injected-loop'),mode,str(base),str(build)],check=True,capture_output=True)
    card.pkg.put(runs,'MOCK_ONLY.txt',b'Copied injected bytes; file-only exclusive claims; no issuer or receiver acquisition.\n')
    collections=output/'collections';collections.mkdir();supplied=output/'supplied';supplied.mkdir();cases={}
    joined=b.plain(models/'joined.bin')
    def collect(name,raws=None,execution='matching',primary='matching',run=base):
        folder=supplied/name;folder.mkdir();paths=[]
        for n,raw in (raws if raws is not None else {NAME:joined}).items():
            path=folder/n;b.old.durable_write(path,raw);paths.append(path)
        cases[name]=c.freeze(run/'host',collections/name,run/'record.json',run,paths,
            models/(execution+'.execution.bin') if execution is not None else None,
            models/(primary+'.primary.bin') if primary is not None else None)
    collect('matching');collect('missing-execution',execution=None);collect('missing-primary',primary=None)
    collect('missing-both',execution=None,primary=None);collect('missing-lifecycle',{})
    for name in ('prepared','quiet','before-context'):
        collect(name,{NAME:b.plain(models/(name+'.bin'))})
    collect('short-zero-tail',{NAME:joined[:128+12*96]+bytes(17)})
    collect('truncated-header',{NAME:joined[:80]});collect('partial-after-context',{NAME:joined[:128+12*96+17]})
    corrupt=bytearray(joined);corrupt[128+12*96+25]^=1;collect('bad-tail-crc',{NAME:bytes(corrupt)})
    corrupt=bytearray(joined);corrupt[124]^=1;collect('bad-header-crc',{NAME:bytes(corrupt)})
    def header(offset,value):
        raw=bytearray(joined);raw[offset:offset+len(value)]=value;struct.pack_into('<I',raw,124,zlib.crc32(raw[:124]));return bytes(raw)
    collect('wrong-recipe',{NAME:header(56,bytes(32))});collect('wrong-writer',{NAME:header(16,struct.pack('<Q',99))})
    collect('wrong-frequency',{NAME:header(24,struct.pack('<Q',1001))})
    collect('different-nonce',{NAME:header(40,bytes([4])+bytes(15))})
    collect('multiple-lifecycle',{NAME:joined,'ep0-life-'+('04'+'00'*15)+'.bin':header(40,bytes([4])+bytes(15))})
    for mode in ('sequence-mismatch','shape-mismatch','primary-receipt-failure'):
        collect(mode,execution=mode,primary=mode)
    collect('primary-mismatch',primary='shape-mismatch')
    for fault in ('old-receipt','wrong-lead','wrong-npdm','missing-process','sdk-mismatch','duplicate-receipt'):
        run=runs/fault;shutil.copytree(base,run);path=run/'waiting-authorization.json';receipt=b.load(path)
        if fault=='old-receipt':receipt['schema']='A23-waiting-burst-consumed-receipt-5'
        if fault=='wrong-lead':receipt['plan']['sdk_plan']['first_frame_lead']=64
        if fault=='wrong-npdm':receipt['device_npdm_sha256']='00'*32
        if fault in ('old-receipt','wrong-lead','wrong-npdm'):path.write_bytes(b.canonical(receipt))
        if fault=='missing-process':(run/'WAIT_PROCESS_CLAIMED').unlink()
        if fault=='sdk-mismatch':
            path=run/'WAIT_RECEIVER_CLAIMED';value=b.load(path);value['interface_id']=999;path.write_bytes(b.canonical(value))
        if fault=='duplicate-receipt':path.write_bytes(path.read_bytes().replace(b'{',b'{"attempt_consumed":true,',1))
        collect(fault,run=run)
    b.require(cases['matching']['analysis']['supplied_chain_complete'],'new supplied model chain incomplete')
    b.require(not any(row['analysis']['supplied_chain_complete'] for n,row in cases.items() if n!='matching'),'failure model completed')
    for row in cases.values():
        b.require(row['collection_integrity_verified'] and all(row[k] is False for k in c.POLICY),'collection elevated hardware authority')
    hashes={**b.source_hashes(),**{'research/usb-ds-iso/'+n:h for n,h in gate.workflow_hashes().items()}}
    for name,h in hashes.items():
        raw=b.plain(b.REPO/name);b.require(b.sha(raw)==h,'source changed during review');card.pkg.put(output,'source/'+name,raw)
    for path in (b.ROOT/'private/analysis/A23-path-span-readiness-review-20261016/records').iterdir():
        b.require(b.plain(path)==b.plain(path.parent.parent.parent/path.name),'old live record drift')
    result=dict(schema='A23-lead32-workflow-review-1',passed=True,source_hashes=hashes,native_cases=native,
        collection_cases=cases,collection_count=len(cases),receiver_sha256=source['receiver_sha256'],
        build_manifest_sha256=source['build_manifest_sha256'],prior_sources_unchanged=241,
        remaining=0,attempt_issued=False,receiver_acquire_invoked=False,usb_requests=0,sd_accesses=0,
        hardware_verified=False,root_cause_confirmed=False,physical_run_authenticated=False)
    b.write(output/'audit.json',result);b.seal(output);return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);a=p.parse_args();r=run(a.output)
    print(json.dumps(dict(collections=r['collection_count'],sources=len(r['source_hashes']),remaining=0)))
