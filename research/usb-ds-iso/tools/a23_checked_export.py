"""Pinned, model-only checked export and its pure archive consumer."""
from pathlib import Path
import json
import a23_guard_cadence_revision as prior
from a23_sequence32_model import encode,sha,require

w=prior.w;b=prior.parent
PARENT=w.A/'A23-guard-cadence-closeout-20261022'
PARENT_SUM='446b9eedda57a9f6709f3263b1136237250e789659d6ecc7419a4143a01b5246'
NEW=('host/a23_checked_export.h','host/a23_checked_export.m','tools/a23_checked_export.py',
     'tools/audit_a23_checked_export.py','tests/a23_checked_export_fixture.inc','tests/test_a23_checked_export.py')


def sources():
    w.card.seal_verify(PARENT);require(sha(w.plain(PARENT/'SHA256SUMS'))==PARENT_SUM,'cadence closeout drift')
    old=prior.guards();require(old==w.load(PARENT/'source-hashes.json') and len(old)==601,'original601 drift')
    out=dict(old)
    for name in NEW:out['research/usb-ds-iso/'+name]=sha(w.plain(w.ROOT/name))
    require(len(out)==607,'checked export source count differs')
    return dict(sorted(out.items()))


def render_scope(raw):
    raw='#import "a23_checked_export.h"\n'+prior.render_scope(raw,candidate=True)
    return prior.once(raw,'- (NSDictionary *)result {return _entry.result;}',
        '''- (NSDictionary *)exportEvidence {
    return @{@"schema":@"A23-export-boundary-evidence-1",@"entry_binding":_entry.result[@"binding"],
        @"scope":_scope,@"verifier":_verifier.result,@"cadence":_verifier.cadenceMetrics,
        @"future_disk_freshness_verified":@NO,@"physical_run_authenticated":@NO};
}
- (NSDictionary *)result {return _entry.result;}''')


def binding(hashes,build,scope_raw,fixture_raw):
    return dict(schema='A23-checked-export-candidate-1',source_closure_sha256=sha(encode(hashes)),
        parent_manifest_sha256=PARENT_SUM,input_build_manifest_sha256=sha(w.plain(build/'SHA256SUMS')),
        generated_scope_sha256=sha(scope_raw),controller_sha256=sha(w.plain(w.ROOT/'host/a23_checked_export.m')),
        fixture_sha256=sha(fixture_raw),model_only=True)


def binding_header(value):
    return ('static const unsigned char A23CheckedExportBinding[]={'+','.join(str(v) for v in encode(value))+'};\n').encode()


def fixture(source):
    import audit_a23_live75_two_epoch as old
    raw=old.fixture(source).split('\nint main(',1)[0]
    raw=raw.split('static void mutation(',1)[0]
    return raw+'\n'+w.plain(w.ROOT/'tests/a23_checked_export_fixture.inc').decode()


def _integer(v):return type(v) is int and v>=0


def _evidence(value,entry_binding):
    require(value.get('schema')=='A23-export-boundary-evidence-1' and value['entry_binding']==entry_binding,'boundary binding differs')
    require(value['verifier']['failed'] is False and value['future_disk_freshness_verified'] is False and value['physical_run_authenticated'] is False,'boundary claims differ')
    scope=value['scope']
    for k in ('build_manifest_sha256','receiver_sha256','first_sequence','last_sequence'):require(scope[k]==entry_binding[k],'scope/entry binding differs')
    metrics=value['cadence'];rows=metrics['full_checks']
    require(metrics['clock_domain']=='host_CLOCK_MONOTONIC_RAW' and metrics['sdk_clock_is_synthetic'] is True and
        _integer(metrics['full_invocations']) and metrics['full_invocations']==len(rows)>0,'timing count/domain differs')
    previous_end=0
    for i,row in enumerate(rows,1):
        require(row['index']==i and _integer(row['begin_ns']) and _integer(row['end_ns']) and _integer(row['elapsed_ns']) and
            row['begin_ns']>=previous_end and row['end_ns']>=row['begin_ns'] and row['elapsed_ns']==row['end_ns']-row['begin_ns'] and row['passed'] is True,'invalid full-check timing')
        previous_end=row['end_ns']
    require(rows[-1]['phase']=='export_boundary','last check is not an export boundary')
    return metrics


def accept(root,*,expected_binding):
    """Validate supplied disk evidence, never infer current live source or wait."""
    root=w.canonical(root)
    final=w.card.seal_verify(root/'live-final');accepted=w.card.seal_verify(root/'live-acceptance')
    require(set(final)=={'entry-current.json','entry-final-status.json','result.json','receipt-status.json','live.json',
        'candidate-binding.json','validation-before.json'},'payload inventory differs')
    require(set(accepted)=={'receipt.json','validation-after.json'},'acceptance inventory differs')
    bound=json.loads(final['candidate-binding.json']);receipt=json.loads(accepted['receipt.json'])
    require(bound==expected_binding and bound['schema']=='A23-checked-export-candidate-1' and bound['model_only'] is True,'external candidate pin differs')
    require(receipt['schema']=='A23-checked-export-receipt-1','receipt schema differs')
    for k in ('validated','snapshot_equal','payload_files_equal'):require(receipt[k] is True,'incomplete acceptance')
    for k in ('hardware_verified','physical_run_authenticated','atomic_directory_snapshot_verified','future_disk_freshness_verified'):
        require(receipt[k] is False,'unsupported acceptance claim')
    checks={'payload_manifest_sha256':w.plain(root/'live-final/SHA256SUMS'),
        'candidate_binding_sha256':final['candidate-binding.json'],'pre_evidence_sha256':final['validation-before.json'],
        'post_evidence_sha256':accepted['validation-after.json'],'entry_snapshot_sha256':final['entry-current.json']}
    for key,raw in checks.items():require(receipt[key]==sha(raw),'receipt digest differs: '+key)
    entry=json.loads(final['entry-current.json']);state=json.loads(final['entry-final-status.json'])
    require(entry['complete'] is True and entry['stopped'] is False and state['saved'] is True and state['stale'] is False,'entry is not complete')
    require(json.loads(final['result.json'])==entry['driver'] and json.loads(final['receipt-status.json'])==entry['driver_receipt'],'entry payload snapshots differ')
    before=json.loads(final['validation-before.json']);after=json.loads(accepted['validation-after.json'])
    pre=_evidence(before,entry['binding']);post=_evidence(after,entry['binding'])
    require(post['full_invocations']==pre['full_invocations']+1 and post['full_checks'][:-1]==pre['full_checks'],'missing distinct post-export check')
    require(receipt['pre_full_check_index']==pre['full_invocations'] and receipt['post_full_check_index']==post['full_invocations'],'receipt timing indexes differ')
    return dict(schema='A23-checked-export-analysis-1',supplied_export_chain_complete=True,candidate_binding=bound,
        entry_binding=entry['binding'],pre_full_checks=pre['full_invocations'],post_full_checks=post['full_invocations'],
        pre_check_ns=pre['full_checks'][-1]['elapsed_ns'],post_check_ns=post['full_checks'][-1]['elapsed_ns'],
        payload_manifest_sha256=receipt['payload_manifest_sha256'],receipt_sha256=sha(accepted['receipt.json']),
        source_code_labels_authenticated=False,current_disk_freshness_verified=False,atomic_directory_snapshot_verified=False,
        physical_run_authenticated=False,hardware_verified=False,creator_wait_verified=False,callback_drain_verified=False)
