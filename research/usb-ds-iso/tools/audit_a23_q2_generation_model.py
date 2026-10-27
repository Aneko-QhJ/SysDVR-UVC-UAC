"""Run finite Q2b symbolic checks and seal evidence; never use SDK or hardware."""
import argparse
import ast
import importlib.util
import io
import json
import sys
import unittest
from pathlib import Path
import build_a23_live132_q1 as b

w=b.w;core=b.base.base.base.core
NEW=('tools/a23_q2_generation_model.py','tests/test_a23_q2_generation_model.py',
     'tools/audit_a23_q2_generation_model.py')
PARENT=w.A/'A23-q2a-sdk-handoff-closeout-20261026'
PARENT_SEAL='d7183f84d4350d4fe4aeb01fa99f6361e910be6bdbbee8ab97bcc75bf535b063'


def run(out):
    out=w.canonical(out)
    b.require(not out.exists(),'fresh model review directory required')
    b.require(core.verify_seal(PARENT)==PARENT_SEAL,'Q2a parent drift')
    ticket=w.A/'A23-context65-pending.json';actual=w.A/'A23-live132-q1-once-20261026-r1.json'
    b.require(w.plain(ticket)==w.plain(PARENT/'ticket.json') and
              w.plain(actual)==w.plain(PARENT/'actual465-unchanged.json'),'state drift')
    base_sources=b.sources();b.require(len(base_sources)==672 and base_sources==w.load(PARENT/'source-hashes.json'),
                                     'base672 source drift')
    protected=b.base.base.prior.protected();actual_raw=w.plain(actual)
    ledger={p.relative_to(b.FORMAL_ROOT).as_posix():b.sha(w.plain(p)) for p in b.FORMAL_ROOT.rglob('*') if p.is_file()}
    b.require(ledger==w.load(PARENT/'namespace465-hashes.json'),'namespace465 drift')
    new_sources={'research/usb-ds-iso/'+name:b.sha(w.plain(w.ROOT/name)) for name in NEW}
    b.require(not(base_sources.keys() & new_sources.keys()),'new model source overlaps frozen bundle')
    sources=base_sources|new_sources;b.require(len(sources)==675,'research source count differs')
    model=w.plain(w.ROOT/NEW[0]);tree=ast.parse(model)
    imports=[node for node in ast.walk(tree) if isinstance(node,(ast.Import,ast.ImportFrom))]
    b.require(len(imports)==1 and isinstance(imports[0],ast.ImportFrom) and imports[0].module=='dataclasses',
              'symbolic model must import dataclasses only')
    out.mkdir(mode=0o700)
    for name in NEW:w.card.put(out,'source/'+name,w.plain(w.ROOT/name))
    w.write(out/'base672-source-hashes.json',base_sources);w.write(out/'source-hashes.json',sources)
    w.write(out/'protected-before.json',protected);w.write(out/'namespace465-hashes.json',ledger)
    w.card.put(out,'actual465-unchanged.json',actual_raw);w.card.put(out,'ticket-before.json',w.plain(ticket))
    log=io.StringIO()
    try:
        path=w.ROOT/NEW[1];spec=importlib.util.spec_from_file_location('q2b_generation_model_checks',path)
        checks=importlib.util.module_from_spec(spec);sys.modules[spec.name]=checks;spec.loader.exec_module(checks)
        suite=unittest.defaultTestLoader.loadTestsFromModule(checks)
        result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
        w.card.put(out,'tests.log',log.getvalue().encode())
        w.write(out/'cases.json',checks.RESULTS)
        b.require(result.wasSuccessful() and not result.skipped and not result.expectedFailures,
                  'Q2b model checks failed')
        assumed=checks.RESULTS['orders_assumed_handoff'];unknown=checks.RESULTS['orders_unknown_handoff']
        b.require((assumed['schedules'],assumed['conditional_recycles'])==(5040,42) and
                  (unknown['schedules'],unknown['conditional_recycles'])==(720,0),'order coverage differs')
        b.require(b.sources()==base_sources and b.base.base.prior.protected()==protected and
                  w.plain(actual)==actual_raw,'protected source/state drift')
        b.require(new_sources=={'research/usb-ds-iso/'+name:b.sha(w.plain(w.ROOT/name)) for name in NEW},
                  'new candidate changed during review')
        b.require(ledger=={p.relative_to(b.FORMAL_ROOT).as_posix():b.sha(w.plain(p)) for p in b.FORMAL_ROOT.rglob('*') if p.is_file()},
                  'namespace465 changed')
        report=dict(schema='A23-q2b-generation-model-review-1',passed=True,research_source_count=675,
            frozen_receiver_source_count=672,base672_unchanged=True,new_research_sources=3,
            test_methods=result.testsRun,finite_event_schedules=5760,assumed_handoff_schedules=5040,
            conditional_model_recycles=42,unknown_handoff_schedules=720,unknown_handoff_recycles=0,
            independent_order_oracle='dependency_DAG_order_only',pointer_only_counterexample_saved=True,
            model_imports_dataclasses_only=True,actual_backing_allocated=False,
            native_handoff_proven=False,all_callback_drain_proven=False,physical_buffer_reuse_enabled=False,
            real_evidence_commit_verified=False,concurrent_interleavings_verified=False,
            candidate_integrated_with_receiver=False,source_closed_metadata_GC_implemented=False,
            metadata_is_bounded_and_never_evicted=True,evidence_credit_is_symbolic_not_device_trace_budget=True,
            compiler_jobs=0,python_model_review_processes=1,native_fixture_processes=0,
            SDK_objects=0,SDK_method_calls=0,usb_requests=0,sd_accesses=0,
            formal_ranges=0,formal_authorizations=0,model_namespaces=0,remaining=0,
            actual465_and_namespace465_unchanged=True,old_actual_and_nine_namespaces_unchanged=True,
            parent=str(PARENT),parent_seal=PARENT_SEAL)
        w.write(out/'report.json',report);w.b.seal(out);w.card.seal_verify(out)
        return dict(seal=core.verify_seal(out),report=report)
    except BaseException as error:
        if not(out/'COMMITTED').exists():
            if not(out/'tests.log').exists():w.card.put(out,'tests.log',log.getvalue().encode())
            w.write(out/'failure.json',dict(type=type(error).__name__,error=str(error),
                usb_requests=0,sd_accesses=0,remaining=0))
            w.b.seal(out)
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True,type=Path)
    print(json.dumps(run(parser.parse_args().output)))
