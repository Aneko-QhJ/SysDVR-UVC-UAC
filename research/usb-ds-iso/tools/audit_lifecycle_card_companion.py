#!/usr/bin/env python3
"""Freeze the observed companion and isolated deployment models. No real card."""
import argparse,json,shutil,sys
from pathlib import Path
import lifecycle_card_companion_deploy as v
import lifecycle_card_workflow as w
sys.path.insert(0,str(w.b.ROOT/'tests'))
from test_lifecycle_card_companion import CompanionTests

b=w.b;ANALYSIS=w.once.ANALYSIS
PARENT=ANALYSIS/'A23-lifecycle-card-files-review-20261016'
NEW=('tools/lifecycle_card_companion_deploy.py','tools/audit_lifecycle_card_companion.py','tests/test_lifecycle_card_companion.py')
CASES={'matching':('valid',False),'none':('none',False),'rename-removes-companion':('valid',True),
       'wrong-content':('invalid',False),'unrelated-file':('unrelated',False),'modified-original':('modified-original',False)}


def run(output):
    output=w.pkg.output_path(output);parent=b.load(PARENT/'audit.json');hashes=dict(parent['source_hashes']);b.require(len(hashes)==210,'parent source count')
    for n,h in hashes.items():b.require(b.sha(b.plain(b.REPO/n))==h,'parent drift')
    for n in NEW:hashes['research/usb-ds-iso/'+n]=b.sha(b.plain(b.ROOT/n))
    protected=b.load(PARENT/'protected-inputs.json');live=ANALYSIS/'A23-quiet-once-20261016-interface2.json';before=b.plain(live)
    output.mkdir(mode=0o700,parents=True)
    for n in NEW:w.pkg.put(output,'inputs/'+n,b.plain(b.ROOT/n))
    w.pkg.put(output,'observed-companion.bin',b.plain(v.EVIDENCE/'observed-card'/v.TEMPLATE_NAME))
    cases={}
    for name,(kind,rename) in CASES.items():
        test=CompanionTests();test.setUp()
        try:
            error=None;receipt=None
            try:receipt=test.run_deploy(kind=kind,rename_companion=rename)
            except ValueError as e:error=str(e)
            good=name in ('matching','none','rename-removes-companion');b.require((error is None)==good,'unexpected companion case')
            folder=output/'models'/name;folder.mkdir(parents=True)
            shutil.copytree(test.snap,folder/'snapshot');shutil.copytree(test.out,folder/'deployment')
            for n,raw in w.selected(test.card.root).items():w.put(folder,'card-after/'+n,raw)
            cases[name]=dict(success=good,error=error,receipt=receipt,simulation=True,actual_card_accesses=0,attempt_issued=False,remaining=0)
            b.write(folder/'case.json',cases[name])
        finally:test.doCleanups()
    refs=[]
    paths=[v.EVIDENCE,b.ROOT/'private/deployments/20261016-141004-lifecycle-window-30s',
           b.ROOT/'private/card-cycles/20261016-141004-lifecycle-predeploy',
           b.ROOT/'private/card-cycles/20261016-141004-lifecycle-deploy-failure-recovery',
           ANALYSIS/'A23-lifecycle-card-deploy-20261016-141004']
    for p in paths:
        w.seal_verify(p);refs.append(dict(folder=str(p),files=len((p/'SHA256SUMS').read_text().splitlines()),manifest_sha256=b.sha(b.plain(p/'SHA256SUMS'))))
    for n,h in hashes.items():b.require(b.sha(b.plain(b.REPO/n))==h,'source drift')
    for n,h in protected['production'].items():b.require(b.sha(b.plain(b.REPO/n))==h,'production drift')
    for group in ('tickets','offline_records_sha256'):
        for n,h in protected[group].items():b.require(b.sha(b.plain(ANALYSIS/n))==h,'record drift')
    b.require(b.plain(live)==before==b.plain(PARENT/'live-record-snapshot.json'),'live record drift')
    result=dict(schema='A23-lifecycle-companion-review-1',source_hashes=hashes,parent_sources_unchanged=210,new_sources=3,
        observed_companion_sha256=v.COMPANION_SHA256,source_references=refs,model_cases=cases,model_count=len(cases),
        new_variant_only=True,original_card_tool_unchanged=True,automatic_retry=False,automatic_rollback=False,
        actual_card_accesses=0,actual_card_write=False,formal_record_created=False,attempt_issued=False,remaining=0,
        device_candidate_changed=False,receiver_changed=False,usb_requests=0,hardware_verified=False,root_cause_confirmed=False)
    b.write(output/'audit.json',result);b.write(output/'protected-inputs.json',protected);w.pkg.put(output,'live-record-snapshot.json',before)
    b.seal(output);w.seal_verify(output);return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);a=p.parse_args();r=run(a.output)
    print(json.dumps(dict(source_files=len(r['source_hashes']),models=r['model_count'])))
