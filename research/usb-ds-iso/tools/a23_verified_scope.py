"""Read-only authority inputs for an embedded native verifier; no issuance."""
from pathlib import Path
import a23_shared_sequence32_scope as prior
import a23_two_epoch_baseline69 as baseline
from a23_sequence32_model import encode,sha,require
w=prior.w
PARENT=w.A/'A23-shared32-closeout-20261019'
PARENT_SUM='1e2776a813543adc98d1422b5ca0468cf18a34dd81295bcae354b766662b8a72'
NEW=('host/a23_scope_verifier.h','host/a23_scope_verifier.m','host/a23_verified_entry_main.m','tools/build_a23_verified_entry.py',
     'tools/a23_verified_scope.py','tools/audit_a23_scope_verifier.py','tests/a23_scope_verifier_fixture.m','tests/test_a23_scope_verifier.py')
DESCRIPTION=dict(schema='A23-verified-entry-description-1',source_verifier_implemented=True,native_permit_linked=True,
    guard_at_begin_prestart_idle_and_final=True,full_hashing_while_io_pending=False,acquisition_mode_implemented=False,
    formal_issuance_available=False,hardware_entry_enabled=False,hardware_verified=False,
    modes=['--describe','--check-build','--check-archive','--inspect-context'])

def sources():
    w.card.seal_verify(PARENT);require(sha(w.plain(PARENT/'SHA256SUMS'))==PARENT_SUM,'parent closeout differs')
    c=w.load(PARENT/'closeout.json');out=prior.sources();require(out==c['source_hashes'] and len(out)==359,'prior359 drift')
    for n,h in c['protected_sha256'].items():require(sha(w.plain(Path(n)))==h,'protected drift')
    require(c['actual_ledger_sha256']=={p.name:sha(w.plain(p)) for p in w.LEDGER.iterdir() if p.is_file()},'real ledger drift')
    for n in NEW:
        key='research/usb-ds-iso/'+n;require(key not in out,'new overlap');out[key]=sha(w.plain(w.ROOT/n))
    return dict(sorted(out.items()))

def inputs():
    hashes=sources();a=baseline.adoption();saved=w.card.verify_snapshot(baseline.ANCHOR);history={}
    for p in w.LEDGER.iterdir():history['ledger/'+p.name]=w.plain(p)
    for row in baseline.legacy.entries(w.LEDGER).values():
        p=Path(row['value']['record']);history['records/'+p.name]=w.plain(p)
    index={p.parent.name+'/snapshot.json':w.plain(p) for p in (w.ROOT/'private/card-cycles').glob('*/snapshot.json')}
    d=dict(schema='A23-verified-entry-descriptor-1',description=DESCRIPTION,source_hashes=hashes,workflow_source_sha256=sha(encode(hashes)),
        baseline_directory=baseline.ANCHOR.name,baseline_files={n:sha(r) for n,r in saved.items()},baseline_manifest_sha256=baseline.ANCHOR_SUM,
        baseline_inventory_sha256=a['inventory_sha256'],history_files={n:sha(r) for n,r in history.items()},history_sha256=sha(encode(a['history'])),
        recovery_index={n:sha(r) for n,r in index.items()},device_binding_sha256='a10e3750ed104576c05b205145e8a8efefe8811d20dec0d1e1debc8c368c61cf',recipe_sha256='37269528ee3baa2941e1cb9268ccd4702d9db5b0fec87e913d3111c99b6e894f',
        live_roots=dict(repository=str(w.b.REPO),cards=str(w.ROOT/'private/card-cycles'),ledger=str(w.LEDGER),records=str(w.A)),parent_manifest_sha256=PARENT_SUM)
    return d,saved,history,index,a['history']
