"""Post-sample semantics audit and status presentation; frozen receiver, no new candidate."""
import argparse
import copy
import json
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
import build_a23_live132_completion as b
import a23_live132_completion_consumer as consumer
import a23_completion_status_view as view
import audit_a23_live132_completion as previous

w=b.w
PARENT=w.A/'A23-live132-completion-closeout-20261026'
PARENT_SUM='ee0e2f7d31ef200ad336d3883269e3726099552c50efb027dbc640a6132c0716'
REVIEW=w.A/'A23-live132-completion-review-20261026-r2'
REVIEW_SUM='550dfe97fdea47d478e4fb4fb99f1f0bbe114e0f22b777602956b371ffd9323d'
BUILD=REVIEW/'build'
NEW=('tools/a23_completion_status_view.py','tools/audit_a23_postcompletion_semantics.py')
CASES={
    'normal':('', '',True),
    'before-sample':('completion_entered','interest',False),
    'after-sample':('completion_sampled','interest',True),
    'after-record':('completion_recorded','interest',True),
    'after-sample-queued':('completion_sampled','queued_interest',True),
    'after-finished':('observer_before_probe','interest',True),
}

def sources():
    old=b.sources();b.require(old==w.load(PARENT/'source-hashes.json'),'old666 drift')
    return dict(sorted((old|{'research/usb-ds-iso/'+n:b.sha(w.plain(w.ROOT/n)) for n in NEW}).items()))

def instrumented_export():
    raw=w.plain(BUILD/'generated/live_export.m').decode()
    edits=[('_completionRecordSaved=exportFiles','checkpoint(@"completion_sampled");\n    _completionRecordSaved=exportFiles'),
        ('_completionAccepted=accepted && _completionRecordSaved;','checkpoint(@"completion_recorded");\n    _completionAccepted=accepted && _completionRecordSaved;')]
    changed=raw
    for old,new in edits:
        b.require(changed.count(old)==1,'instrumentation anchor');changed=changed.replace(old,new)
    restored=changed
    for old,new in reversed(edits):restored=restored.replace(new,old)
    b.require(restored==raw,'diagnostic diff beyond two hooks')
    return changed

def fixture():
    raw=previous.fixture()
    old='        row=@{'
    b.require(raw.count(old)==1,'observer hook anchor')
    raw=raw.replace(old,r'''
        auditCheckpoint(@"observer_before_probe");
        NSDictionary *observedEntry=entry.result;uint64_t observedNS=auditNow();
        row=@{@"observer_ns":@(observedNS),''')
    raw=raw.replace('@"entry":entry.result,','@"entry":observedEntry,')
    return raw

def rejected(call):
    try:call()
    except (ValueError,OSError) as error:return str(error)
    raise ValueError('view unexpectedly accepted invalid input')

def view_rejections(analysis,binding,observation,loop):
    result={'raw-loop-as-proof':rejected(lambda:view.present(loop,binding))}
    changes={
        'different-record':lambda o:o.update(binding_sha256='0'*64),
        'not-after-sample':lambda o:o.update(observed_ns=analysis['completion']['sample_end_ns']),
        'numeric-stopped':lambda o:o.update(entry_stopped=1),
        'claim-real-device':lambda o:o.update(model_only=False),
        'contradictory-flags':lambda o:o.update(entry_complete=True,entry_stopped=True),
        'unknown-clock':lambda o:o.update(clock='mach_absolute_time'),
    }
    for name,change in changes.items():
        o=copy.deepcopy(observation);change(o);result[name]=rejected(lambda o=o:view.present(analysis,binding,o))
    spoof=copy.deepcopy(analysis);spoof['current_state_after_sample_verified']=True
    result['historical-proof-as-current']=rejected(lambda:view.present(spoof,binding))
    return result

def run(out):
    out=Path(out).resolve();b.require(not out.exists(),'fresh semantics audit required');out.mkdir(mode=0o700)
    done=[]
    def process(cmd,name,timeout=60):
        p=subprocess.run(cmd,capture_output=True,timeout=timeout);w.card.put(out,name+'.stdout',p.stdout);w.card.put(out,name+'.stderr',p.stderr)
        w.write(out/(name+'.process.json'),dict(command=cmd,returncode=p.returncode,creator_wait_verified=True))
        b.require(p.returncode==0,'process failed '+name);return p
    try:
        b.require(b.base.base.core.verify_seal(PARENT)==PARENT_SUM and b.base.base.core.verify_seal(REVIEW)==REVIEW_SUM,'parent evidence drift')
        b.verify(BUILD);before=b.base.prior.protected();hashes=sources();b.require(len(hashes)==668,'source count')
        w.write(out/'source-hashes.json',hashes);w.write(out/'protected-before.json',before)
        for name in NEW:w.card.put(out,'source/'+name,w.plain(w.ROOT/name))
        native=out/'native';shutil.copytree(BUILD,native);target=native/'generated/semantics_fixture.m';target.write_text(fixture())
        export=native/'generated/live_export.m';export.write_text(instrumented_export())
        w.write(out/'diagnostic-binding.json',dict(receiver_manifest_sha256=b.sha(w.plain(BUILD/'SHA256SUMS')),
            receiver_source_count=666,research_source_count=668,fixture_sha256=b.sha(target.read_bytes()),
            original_export_sha256=b.sha(w.plain(BUILD/'generated/live_export.m')),instrumented_export_sha256=b.sha(export.read_bytes()),
            only_export_change_two_fixture_checkpoints=True,new_receiver_candidate=False))
        process(b.command(native,target),'fixture-compile');engine=consumer.module(BUILD,'fixed48');rows={};proofs={};views={};errors={}
        with tempfile.TemporaryDirectory(prefix='a23-postcompletion-',dir='/private/tmp') as temp:
            scratch=Path(temp);template=scratch/'template';previous.old.templates.template(BUILD,template)
            for n in (145,177,225,273,321,369,417):shutil.copytree(BUILD/f'history/spent{n}',template/f'spent{n}')
            cases=scratch/'cases';cases.mkdir()
            try:
                for name,(stage,kind,success) in CASES.items():
                    case=cases/name;case.mkdir();host=case/'host';host.mkdir();model=case/'model';shutil.copytree(template,model)
                    scope=b.scope(BUILD);store=engine.SharedSequence48(case/'namespace',simulation=True,fresh_scope=lambda:scope);store.initialize(b.inputs()[4])
                    job=str(uuid.uuid4());ns=store.validate();store.prepare(job,dict(schema='A23-shared48-authorization-1',job_id=job,scope_sha256=ns['scope_sha256'],
                        maximum_invocations=1,simulation=True,hardware_test_authorized=False));store.issue(job);store.consume(job)
                    config=dict(case=name,build=str(BUILD),host=str(host),repository=str(model/'repository'),cards=str(model/'cards'),ledger=str(model/'ledger'),
                        records=str(model/'records'),job=str(store.root/'jobs'/job),binding=store.binding(job),audit_stage=stage,audit_delivery=kind,
                        audit_expected_success=success,audit_capture=str(case/'at-return'))
                    w.write(case/'config.json',config)
                    p=subprocess.run([str(native/'live-fixture'),str(case/'config.json')],capture_output=True,timeout=60)
                    w.card.put(case,'native.stdout',p.stdout);w.card.put(case,'native.stderr',p.stderr);w.write(case/'process.json',dict(returncode=p.returncode,creator_wait_verified=True))
                    b.require(p.returncode==0 and not p.stderr,'native failed '+name)
                    row=json.loads(p.stdout);rows[name]=row;done.append(name)
                    if not success:
                        errors[name]=rejected(lambda:consumer.analyze(host,BUILD,job=config['job'],simulation=True));shutil.rmtree(model);continue
                    archived=case/'at-return';analysis=consumer.analyze(archived,BUILD,job=config['job'],simulation=True);proofs[name]=analysis
                    fact=json.loads(w.card.seal_verify(archived/'live-completion')['completion.json'])
                    o=dict(schema='A23-postcut-model-observation-1',binding_sha256=b.sha(b.encode(fact['binding'])),clock='CLOCK_MONOTONIC_RAW_ns',
                        observed_ns=row['observer_ns'],model_only=True,entry_complete=row['entry']['complete'],entry_stopped=row['entry']['stopped'],source='offline_fixture_entry_result_getter')
                    w.write(case/'later-model-observation.json',o)
                    views[name]=dict(archive_only=view.present(analysis,fact['binding']),with_later_observation=view.present(analysis,fact['binding'],o))
                    b.require(views[name]['archive_only']['current_device_state']=='unverified' and views[name]['archive_only']['latest_supplied_model_observation']['state']=='not_supplied','archive promoted to current')
                    expected='complete_at_observation' if name=='normal' else 'stopped_at_observation'
                    b.require(views[name]['with_later_observation']['latest_supplied_model_observation']['state']==expected and
                        views[name]['with_later_observation']['current_live_health_verified'] is False,'later observation misrepresented')
                    if name=='normal':errors.update(view_rejections(analysis,fact['binding'],o,row['loop']))
                    else:errors[name+'-after-probe-consumer']=rejected(lambda:consumer.analyze(host,BUILD,job=config['job'],simulation=True))
                    shutil.rmtree(model)
            finally:shutil.copytree(cases,out/'cases')
        # Exercise the actual read-only CLI once in both presentation modes.
        case=out/'cases/after-sample';config=w.load(case/'config.json');script=w.ROOT/'tools/a23_completion_status_view.py'
        command=[__import__('sys').executable,str(script),'--host',str(case/'at-return'),'--build',str(BUILD),'--job',config['job']]
        for label,args in [('archive-only',[]),('with-model-observation',['--model-observation',str(case/'later-model-observation.json')])]:
            p=process(command+args,'view-'+label);v=json.loads(p.stdout)
            b.require(v==views['after-sample']['archive_only' if not args else 'with_later_observation'],'CLI view drift')
        b.require(sources()==hashes and b.sources()==w.load(PARENT/'source-hashes.json') and b.base.prior.protected()==before,'source/protected drift')
        w.write(out/'report.json',dict(schema='A23-postcompletion-semantics-audit-1',source_count=668,frozen_receiver_source_count=666,old666_unchanged=True,
            completed=done,cases=rows,historical_proofs=proofs,status_views=views,rejections=errors,native_compiler_jobs=1,native_fixture_processes=len(done),
            cli_processes=2,creator_wait_verified=True,model_namespaces=len(done),new_receiver_builds=0,model_sdk_operations_only=True,
            view_is_offline_archive_presentation=True,current_live_health_verified=False,hardware_entry_enabled=False,usb_requests=0,sd_accesses=0,
            real_sdk_objects=0,formal_namespaces_added=0,formal_ranges=0,formal_authorizations=0,remaining=0,callback_drain_verified=False,future_events_excluded=False))
        w.b.seal(out);return dict(directory=str(out),seal=b.base.base.core.verify_seal(out),cases=len(done),rejections=len(errors))
    except BaseException as e:
        w.write(out/'failure.json',dict(error=str(e),completed=done));w.b.seal(out);raise

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);print(json.dumps(run(p.parse_args().output)))
