"""Seal disposable flag-repair success/failure models. No physical-card API."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from unittest.mock import patch

import context65_flag_repair as repair
w=repair.w


def run(output):
    output=w.canonical(output);w.require(not output.exists() and output.parent==w.A,'new local repair review required')
    source=repair.source_hashes();output.mkdir(mode=0o700)
    sys.path.insert(0,str(w.ROOT/'tests'));import test_a23_context65_flag_repair as fixture
    cases={};original_open=os.open
    with tempfile.TemporaryDirectory(dir='/private/tmp',prefix='a23-flag-audit-') as temporary:
        work=Path(temporary).resolve();plan=work/'plan';repair.prepare(plan);shutil.copytree(plan,output/'plan')
        for mode in ('success','create-failure','sync-failure','readback-corruption','recovery-failure','concurrent-change'):
            card,before,destination,after=fixture.case(work/mode)
            def denied(path,*args,**kwargs):
                if path=='boot2.flag' and 'dir_fd' in kwargs:raise OSError('injected create failure')
                return original_open(path,*args,**kwargs)
            def corrupted():(card.root/repair.FLAG).write_bytes(b'wrong')
            old_check=card.check;checks=0
            def concurrent(**kwargs):
                nonlocal checks
                checks+=1
                if checks==2:(card.root/'logfile.txt').write_bytes(b'concurrent change')
                return old_check(**kwargs)
            if mode=='create-failure':inject=patch.object(repair.os,'open',side_effect=denied)
            elif mode=='sync-failure':inject=patch.object(card,'sync',side_effect=OSError('injected sync failure'))
            elif mode=='readback-corruption':inject=patch.object(card,'sync',side_effect=corrupted)
            elif mode=='recovery-failure':inject=patch.object(w.card,'recover',side_effect=OSError('injected readonly recovery failure'))
            elif mode=='concurrent-change':inject=patch.object(card,'check',side_effect=concurrent)
            else:inject=patch.object(card,'sync',return_value=None)
            with inject:
                try:
                    result=repair.model_repair(plan,card,before,destination,after)
                    w.require(mode=='success','failure model unexpectedly succeeded')
                except (OSError,ValueError):
                    w.require(mode!='success','positive repair model failed');w.card.seal_verify(destination)
                    result=w.load(destination/'failure.json');w.require(result['passed'] is False,'failure not preserved')
            shutil.copytree(destination,output/mode)
            cases[mode]=dict(passed=result['passed'],manifest_sha256=w.sha(w.plain(destination/'SHA256SUMS')),
                created=result.get('model_flag_created',True),automatic_retry=result['automatic_retry'])
            if mode=='success':
                scope=w.materials()[1];w.verify_recovery(after,scope,simulation=True)
                try:w.verify_recovery(after,scope,simulation=False)
                except ValueError:pass
                else:raise ValueError('model recovery promoted to real baseline')
                import prepare_a23_context65_once as once
                preview=once.prepare(w.A/'A23-context65-once-flag-repair-preview.json',
                    deployment=w.ROOT/'private/deployments/20261016-191203-path-span-window-30s',recovery=after)
                w.require(preview['issuance_available'] is False and preview['record_written'] is False,'formal preview promoted model')
                w.write(output/'formal-preview-rejects-model.json',preview)
        analysis=repair.analyze_model(output/'success');w.write(output/'success-analysis.json',analysis)
        moved=work/'moved';shutil.copytree(output/'success',moved)
        w.require(repair.analyze_model(moved)==analysis,'moved model analysis differs')
    w.require(repair.source_hashes()==source,'repair sources changed during audit');w.transition()
    for name in repair.NEW:
        target=output/'source'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(w.plain(w.ROOT/name,2*1024*1024))
    result=dict(schema='A23-context65-flag-repair-review-1',passed=True,source_hashes=source,source_count=len(source),
        cases=cases,case_count=len(cases),moved_model_verified=True,model_baseline_rejected_formally=True,
        preserved_originals=59,allowed_changed_files=[repair.FLAG],physical_card_execution_supported=False,
        actual_card_repaired=False,formal_reservations=0,formal_records=0,real_sdk_objects=0,usb_requests=0,sd_accesses=0,remaining=0)
    w.write(output/'audit.json',result);w.b.seal(output);w.card.seal_verify(output);return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path);args=parser.parse_args()
    value=run(args.output);print(json.dumps(dict(sources=value['source_count'],cases=value['case_count'],remaining=0)))
