"""Run the one-segment lease model checks and seal source-bound offline evidence."""
import argparse
import ast
import importlib.util
import io
import json
import sys
import unittest
from pathlib import Path
import build_a23_live132_q1 as b
import audit_a23_q2_generation_model as q2b
import audit_a23_q2_evidence_budget as q2c

w=b.w;core=b.base.base.base.core
PARENT=w.A/'A23-q2c-evidence-budget-closeout-20261027'
PARENT_SEAL='cc680ee4f563e7bbedf3d7f1be1ec7bccfa07c86802471e07875f11cefb5c165'
NEW=('tools/a23_q2_epoch_lease_model.py','tests/test_a23_q2_epoch_lease_model.py',
     'tools/audit_a23_q2_epoch_lease_model.py')


def prior_sources():
    return b.sources()|{'research/usb-ds-iso/'+n:b.sha(w.plain(w.ROOT/n)) for n in (*q2b.NEW,q2c.NEW)}


def run(out):
    out=w.canonical(out);b.require(not out.exists(),'fresh model review required')
    b.require(core.verify_seal(PARENT)==PARENT_SEAL,'Q2c parent drift')
    ticket=w.A/'A23-context65-pending.json';actual=w.A/'A23-live132-q1-once-20261026-r1.json'
    b.require(w.plain(ticket)==w.plain(PARENT/'ticket.json') and
              w.plain(actual)==w.plain(PARENT/'actual465-unchanged.json'),'actual state drift')
    prior=prior_sources();b.require(len(prior)==676 and prior==w.load(PARENT/'source-hashes.json'),'prior676 drift')
    extra={'research/usb-ds-iso/'+n:b.sha(w.plain(w.ROOT/n)) for n in NEW}
    b.require(not(prior.keys()&extra.keys()),'new source overlaps prior676')
    sources=prior|extra;b.require(len(sources)==679,'research source count differs')
    protected=b.base.base.prior.protected()
    for p,h in w.load(PARENT/'protected-before.json').items():
        if Path(p)!=ticket:b.require(protected[p]==h,'older protected state drift')
    actual_raw=w.plain(actual)
    ledger={p.relative_to(b.FORMAL_ROOT).as_posix():b.sha(w.plain(p)) for p in b.FORMAL_ROOT.rglob('*') if p.is_file()}
    b.require(ledger==w.load(PARENT/'namespace465-hashes.json'),'namespace465 drift')
    tree=ast.parse(w.plain(w.ROOT/NEW[0]));imports=[]
    for node in ast.walk(tree):
        if isinstance(node,ast.ImportFrom):imports.append(node.module)
        elif isinstance(node,ast.Import):imports.extend(alias.name for alias in node.names)
    b.require(sorted(imports)==['dataclasses','hashlib','json'],'model imports exceed pure symbolic dependencies')
    out.mkdir(mode=0o700)
    for n in NEW:w.card.put(out,'source/'+n,w.plain(w.ROOT/n))
    w.write(out/'source-hashes.json',sources);w.write(out/'prior676-source-hashes.json',prior)
    w.write(out/'base672-source-hashes.json',b.sources());w.write(out/'protected-before.json',protected)
    w.write(out/'namespace465-hashes.json',ledger);w.card.put(out,'actual465-unchanged.json',actual_raw)
    w.card.put(out,'ticket-before.json',w.plain(ticket));log=io.StringIO()
    try:
        path=w.ROOT/NEW[1];spec=importlib.util.spec_from_file_location('q2_epoch_lease_checks',path)
        checks=importlib.util.module_from_spec(spec);sys.modules[spec.name]=checks;spec.loader.exec_module(checks)
        result=unittest.TextTestRunner(stream=log,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(checks))
        w.card.put(out,'tests.log',log.getvalue().encode());w.write(out/'cases.json',checks.RESULTS)
        b.require(result.wasSuccessful() and not result.skipped and not result.expectedFailures,'epoch lease checks failed')
        grid=checks.RESULTS['capacity_grid'];time=checks.RESULTS['delayed_claim_grid'];cuts=checks.RESULTS['bounded_nonrequest_cuts']
        b.require((grid['cases'],grid['conditional_model_reservations'])==(8481,4862) and
                  (time['cases'],time['conditional_model_claims'])==(121,89) and cuts['cases']==10,'coverage counts differ')
        b.require(prior_sources()==prior and extra=={'research/usb-ds-iso/'+n:b.sha(w.plain(w.ROOT/n)) for n in NEW},'source drift')
        b.require(b.base.base.prior.protected()==protected and w.plain(actual)==actual_raw,'protected state drift')
        b.require(ledger=={p.relative_to(b.FORMAL_ROOT).as_posix():b.sha(w.plain(p)) for p in b.FORMAL_ROOT.rglob('*') if p.is_file()},
                  'namespace465 changed')
        report=dict(schema='A23-q2c-epoch-lease-model-review-1',passed=True,test_methods=result.testsRun,
            research_source_count=679,frozen_receiver_source_count=672,new_research_sources=3,prior676_unchanged=True,
            capacity_combinations=8481,conditional_model_reservations=4862,delayed_claim_cases=121,
            conditional_model_claims=89,bounded_nonrequest_cuts=10,current216_rejected_before_symbolic_ISO=True,
            shape_trace_reserve=69,shape_identity_reserve=6,unknown_condition_reserve_allowed=False,
            second_segment_implemented=False,credit_refunded=False,unexpected_observations_mark_counters_untrusted=True,
            actual_device_grant_authenticated=False,global_cross_controller_serialization=False,
            native_handoff_proven=False,hard_deadline_proven=False,lossless_rollover_verified=False,
            candidate_integrated_with_receiver=False,real_evidence_commit_verified=False,
            concurrent_interleavings_verified=False,python_model_review_processes=1,compiler_jobs=0,
            native_fixture_processes=0,SDK_objects=0,SDK_method_calls=0,usb_requests=0,sd_accesses=0,
            formal_ranges=0,formal_authorizations=0,model_namespaces=0,remaining=0,
            actual465_and_namespace465_unchanged=True,old_actual_and_nine_namespaces_unchanged=True,
            parent=str(PARENT),parent_seal=PARENT_SEAL)
        w.write(out/'report.json',report);w.b.seal(out);w.card.seal_verify(out)
        return dict(seal=core.verify_seal(out),report=report)
    except BaseException as error:
        if not(out/'COMMITTED').exists():
            if not(out/'tests.log').exists():w.card.put(out,'tests.log',log.getvalue().encode())
            w.write(out/'failure.json',dict(type=type(error).__name__,error=str(error),usb_requests=0,sd_accesses=0,remaining=0))
            w.b.seal(out)
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True,type=Path)
    print(json.dumps(run(parser.parse_args().output)))
