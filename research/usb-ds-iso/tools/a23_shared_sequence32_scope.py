"""Live read-only scope for the dormant shared issuer and native permit."""
from pathlib import Path
import argparse,json
import a23_two_epoch_baseline69 as prior
from a23_sequence32_model import encode,sha,require
w=prior.w
PARENT=w.A/'A23-workflow32-closeout-20261019'
PARENT_SUM='7b9516711631de8ebbca67574479c394164e2c68170879e92ffcc8bd71fa0db7'
NEW=('host/a23_shared_sequence_permit.h','host/a23_shared_sequence_permit.m','tools/a23_shared_sequence32.py','tools/a23_shared_sequence32_scope.py',
     'tools/analyze_a23_shared_sequence32.py','tools/audit_a23_shared_sequence32.py','tests/a23_shared_sequence_permit_fixture.m','tests/test_a23_shared_sequence32.py')

def sources():
    w.card.seal_verify(PARENT);require(sha(w.plain(PARENT/'SHA256SUMS'))==PARENT_SUM,'parent closeout differs')
    c=w.load(PARENT/'closeout.json');out=prior.sources();require(out==c['source_hashes'] and len(out)==351,'prior351 drift')
    for n,h in c['protected_sha256'].items():require(sha(w.plain(Path(n)))==h,'protected drift')
    actual={p.name:sha(w.plain(p)) for p in w.LEDGER.iterdir() if p.is_file()};require(actual==c['actual_ledger_sha256'],'real ledger changed')
    for n in NEW:
        key='research/usb-ds-iso/'+n;require(key not in out,'new overlap');out[key]=sha(w.plain(w.ROOT/n))
    return dict(sorted(out.items()))

def materials():
    hashes=sources();a=prior.adoption()
    s=dict(schema='A23-shared32-scope-1',baseline_manifest_sha256=a['snapshot']['manifest_sha256'],baseline_inventory_sha256=a['inventory_sha256'],
        workflow_source_sha256=sha(encode(hashes)),build_manifest_sha256=a['build']['manifest_sha256'],receiver_sha256=a['receiver_sha256'],
        device_binding_sha256='a10e3750ed104576c05b205145e8a8efefe8811d20dec0d1e1debc8c368c61cf',recipe_sha256='37269528ee3baa2941e1cb9268ccd4702d9db5b0fec87e913d3111c99b6e894f',
        history_sha256=sha(encode(a['history'])),first_sequence=81,last_sequence=112,formal_issuance_available=False,acquisition_mode_implemented=False,hardware_entry_enabled=False)
    return dict(schema='A23-shared32-preview-1',scope=s,history=a['history'],source_hashes=hashes,baseline_snapshot=a['snapshot'],
        remaining=0,formal_issuance_available=False,production_shared_engine_implemented=True,production_issuance_ready=False,
        native_permit_hardware_verified=False,actual_sequence81_reserved=False,usb_requests=0,sd_accesses=0)

if __name__=='__main__':
    argparse.ArgumentParser(description=__doc__).parse_args();print(json.dumps(materials(),indent=2))
