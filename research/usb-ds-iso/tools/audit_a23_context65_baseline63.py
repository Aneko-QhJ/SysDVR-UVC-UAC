"""Exercise injected owned invocations and static collections; never issue formally."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile

import context65_baseline63 as w
import prepare_a23_context65_baseline63 as once
from workflows import capture_a23_context65_baseline63 as gate
import collect_a23_context65_baseline63 as collection


def run(output):
    output=w.canonical(output);w.require(not output.exists(),'new workflow audit required');output.mkdir()
    sys.path.insert(0,str(w.ROOT/'tests'));import test_a23_context65_baseline63 as fixture
    before=w.hashes();cases={}
    with tempfile.TemporaryDirectory(dir='/private/tmp',prefix='a23-context65-audit-') as temporary:
        work=Path(temporary).resolve();baseline=fixture.baseline(work/'baseline')
        path=work/'A23-context65-once-audit.json';once.prepare(path,issue=True,deployment=fixture.DEPLOYMENT,recovery=baseline,ledger=work/'ledger')
        runs=work/'runs';runs.mkdir();result=gate.capture(path,_model_runner=fixture.positive_runner,_model_runs=runs)
        w.require(result['host_observation_complete'],'injected invocation did not complete');run=Path(result['run'])
        # Each collection preserves disposable copies. The real sealed run and
        # all project evidence remain read-only; no native acquisition executes.
        saved={p.relative_to(run).as_posix():p.read_bytes() for p in run.rglob('*') if p.is_file()}
        for mode in ('matching','missing-launch','bad-launch','missing-context','bad-context','missing-execution','old49-execution','multiple-lifecycle'):
            for p in list(run.iterdir()):
                if p.is_dir():shutil.rmtree(p)
                else:p.unlink()
            for n,raw in saved.items():p=run/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
            if mode=='missing-launch':(run/'launch-environment.json').unlink()
            if mode=='bad-launch':
                p=run/'launch-environment.json';v=json.loads(p.read_text());v['sandbox_query_result']=1;p.write_bytes(w.b.canonical(v))
            if mode=='missing-context':(run/'execution-context.json').unlink()
            if mode=='bad-context':(run/'execution-context.json').write_bytes(b'{')
            life=work/'supplied'/mode;life.mkdir(parents=True);p=life/fixture.LIFE;shutil.copyfile(fixture.REVIEW/'models/joined.bin',p);lifecycle=[p]
            if mode=='multiple-lifecycle':q=life/'ep0-life-other.bin';shutil.copyfile(p,q);lifecycle.append(q)
            ex=fixture.REVIEW/'models/matching.execution.bin';primary=fixture.REVIEW/'models/matching.primary.bin'
            if mode=='missing-execution':ex=primary=None
            if mode=='old49-execution':ex=w.A/'A23-sequence-receiver-review-20261017-r5/models/matching.execution.bin';primary=ex.with_name('matching.primary.bin')
            value=collection.freeze(run/'host',output/('collection-'+mode),path,run,lifecycle,ex,primary)
            w.require(value['analysis']['supplied_chain_complete'] is (mode=='matching'),'bad owned collection classification '+mode)
            cases[mode]=dict(complete=value['analysis']['supplied_chain_complete'],manifest_sha256=value['manifest_sha256'])
        for mode in ('missing-reservation','bad-reservation','changed-commitment','bad-issuance','missing-baseline','bad-baseline-log','bad-baseline-adoption'):
            target=output/('collection-'+mode);shutil.copytree(output/'collection-matching',target)
            for name in ('analysis.json','collection.json','SHA256SUMS','COMMITTED'):(target/name).unlink()
            if mode=='missing-reservation':(target/'binding/reservation.json').unlink()
            if mode=='bad-reservation':(target/'binding/reservation.json').write_bytes(b'{')
            if mode in ('changed-commitment','bad-issuance'):
                p=target/'binding/record.json';v=w.load(p)
                if mode=='changed-commitment':v['issuance']['recovery']['manifest_sha256']='0'*64
                else:v['issuance']['maximum_invocations']=2
                p.write_bytes(w.b.canonical(v))
            if mode=='missing-baseline':(target/'binding/baseline63-adoption.json').unlink()
            if mode=='bad-baseline-log':(target/'binding/baseline63-current-logfile.txt').write_bytes(b'changed')
            if mode=='bad-baseline-adoption':
                p=target/'binding/baseline63-adoption.json';v=w.load(p);v['raw_files']=59;p.write_bytes(w.b.canonical(v))
            raw=collection.c.tree(target);value=collection.analyze_inputs(target,w.load(path)['recipe_sha256'])
            w.require(not value['supplied_chain_complete'] and (not value['baseline63_adoption_consistent'] if mode in ('missing-baseline','bad-baseline-log','bad-baseline-adoption') else not value['reservation_commitment_consistent']),'bad supplied binding classified complete')
            w.write(target/'analysis.json',value);w.write(target/'collection.json',collection.metadata(raw,w.load(path)['recipe_sha256']));w.b.seal(target)
            checked=collection.analyze(target);cases[mode]=dict(complete=False,manifest_sha256=checked['manifest_sha256'])
        moved=work/'moved';shutil.copytree(output/'collection-matching',moved);w.require(collection.analyze(moved)['analysis']['supplied_chain_complete'],'moved collection failed')
        # Restore model files for the final transition/commitment check.
        for p in list(run.iterdir()):shutil.rmtree(p) if p.is_dir() else p.unlink()
        for n,raw in saved.items():p=run/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
        w.verify_scope(w.load(path),path)
    w.require(w.hashes()==before,'source changed during audit');w.transition()
    result=dict(schema='A23-context65-baseline63-review-1',passed=True,source_hashes=before,source_count=len(before),
        cases=cases,collection_count=len(cases),moved_collection_verified=True,model_only=True,formal_reservations=0,formal_records=0,
        receiver_acquire_invoked=False,real_sdk_objects=0,usb_requests=0,sd_accesses=0,remaining=0)
    w.write(output/'audit.json',result);w.b.seal(output);return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);a=p.parse_args();v=run(a.output)
    print(json.dumps(dict(sources=v['source_count'],collections=v['collection_count'],remaining=0)))
