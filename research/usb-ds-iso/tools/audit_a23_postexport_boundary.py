"""Audit late-fault cut points in the frozen receiver; no new receiver candidate."""
import argparse
import json
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
import build_a23_live132_terminal as b
import a23_live132_terminal_consumer as consumer
import audit_a23_live91_checked as templates

w=b.w
PARENT=w.A/'A23-live132-terminal-closeout-20261026'
PARENT_SUM='aaf54f9b4b58952d22aa7b387658bf62edf3e1bfd259620eed553b922cfe5b36'
REVIEW=w.A/'A23-live132-terminal-review-20261026-r4'
REVIEW_SUM='50505814e014009b5284fbcd72ea8e92856c09b8ddab98270ec96794057b7798'
BUILD=REVIEW/'build'
NEW='tools/audit_a23_postexport_boundary.py'
# stage, delivery, expected loop success, expected final supplied-disk acceptance
CASES={
    'normal':('', '', True, True),
    'precheck-direct':('before_precheck','interest',False,False),
    'payload-direct':('after_payload','interest',False,False),
    'postcheck-direct':('after_postcheck','interest',True,False),
    'receipt-direct':('after_receipt','interest',True,False),
    'payload-queued':('after_payload','queued_interest',True,False),
    'postcheck-oldiso':('after_postcheck','old_iso',True,False),
    'postcheck-source':('after_postcheck','source',True,True),
}

def sources():
    old=b.sources();b.require(old==w.load(PARENT/'source-hashes.json'),'old662 drift')
    return dict(sorted((old|{'research/usb-ds-iso/'+NEW:b.sha(w.plain(w.ROOT/NEW))}).items()))

PREFIX=r'''
#include <time.h>
static SDKModelInterface *auditResources;
static dispatch_queue_t auditQueue;
static BOOL auditDelivered,auditQueued,auditCaptured;
static NSMutableArray *auditEvents;
static NSDictionary *auditCapture;
static uint64_t auditNow(void){struct timespec t;assert(!clock_gettime(CLOCK_MONOTONIC_RAW,&t));return (uint64_t)t.tv_sec*1000000000ULL+t.tv_nsec;}
static void auditEvent(NSString *name){[auditEvents addObject:@{@"event":name,@"ns":@(auditNow())}];}
static void auditCheckpoint(NSString *stage){
    auditEvent([@"checkpoint_" stringByAppendingString:stage]);
    if(![stage isEqual:exportConfig[@"audit_stage"]])return;
    NSString *kind=exportConfig[@"audit_delivery"];
    if([kind isEqual:@"queued_interest"]){
        assert(!auditQueued);auditQueued=YES;auditEvent(@"interest_queued");
        dispatch_async(auditQueue,^{auditDelivered=YES;auditEvent(@"interest_delivered");auditResources.interest(0xffffffffU);});
    }else if([kind isEqual:@"interest"]){auditDelivered=YES;auditEvent(@"interest_delivered");auditResources.interest(0xffffffffU);}
    else if([kind isEqual:@"old_iso"]){auditDelivered=YES;auditEvent(@"old_iso_delivered");[auditResources oldISO];}
    else if([kind isEqual:@"source"]){auditDelivered=YES;auditEvent(@"source_changed");change([exportConfig[@"repository"] stringByAppendingPathComponent:@"research/usb-ds-iso/host/a23_scope_verifier.m"]);}
}
static void auditCaptureAfterTick(A23CheckedTwoEpochRun *loop){
    if(auditCaptured || ![loop.status[@"finished"] boolValue] || ![loop.status[@"success"] boolValue])return;
    auditCaptured=YES;auditEvent(@"loop_return_before_live_probe");
    // The exporter just returned on its owner queue. Read only controller-owned
    // values before a live result getter can append fault/stop journal events.
    auditCapture=@{@"loop":loop.status,@"delivered":@(auditDelivered),@"queued":@(auditQueued),
        @"terminal":exportCoordinator.terminalGuardResult,@"events":[auditEvents copy]};
    assert([[NSFileManager defaultManager] copyItemAtPath:exportConfig[@"host"] toPath:exportConfig[@"audit_capture"] error:NULL]);
}
'''

def fixture():
    raw=w.plain(REVIEW/'native/generated/model_fixture.m').decode()
    marker='void A23ExportModelCheckpoint(NSString *stage){'
    b.require(raw.count(marker)==1,'checkpoint hook inventory')
    raw=raw.replace(marker,PREFIX+'\n'+marker+'\n    auditCheckpoint(stage);')
    raw=raw.replace('op.interface=r;terminalModelClock=r.clock;','op.interface=r;terminalModelClock=r.clock;auditResources=r;auditEvents=[NSMutableArray new];')
    raw=raw.replace('workerHookQueue=q;','workerHookQueue=q;auditQueue=q;')
    anchor='[loop tick];\n                NSDictionary *term=exportCoordinator.terminalGuardResult;'
    b.require(raw.count(anchor)==1,'return snapshot anchor')
    raw=raw.replace(anchor,'[loop tick];auditCaptureAfterTick(loop);\n                NSDictionary *term=exportCoordinator.terminalGuardResult;')
    raw=raw.replace('@"schema":@"A23-checked-export-fixture-1",@"case":name,',
        '@"audit_capture":auditCapture?:@{},@"audit_events":[auditEvents copy],@"audit_delivered":@(auditDelivered),@"audit_queued":@(auditQueued),@"schema":@"A23-checked-export-fixture-1",@"case":name,')
    old='BOOL complete=[@[@"normal",@"tail128",@"queued-delay",@"after-post-source",@"after-receipt-bytes"] containsObject:name];'
    b.require(raw.count(old)==1,'expected-result anchor')
    raw=raw.replace(old,'BOOL complete=[exportConfig[@"audit_expected_success"] boolValue];')
    return raw

def static_findings():
    scope=w.plain(BUILD/'generated/live_scope.m').decode()
    export=w.plain(BUILD/'generated/live_export.m').decode()
    needles=('checkpoint(@"after_payload")','NSDictionary *latest=_target.result,*lastFinal=_target.finalStatus;',
        'checkpoint(@"after_postcheck")','_acceptanceSaved=exportFiles','checkpoint(@"after_receipt")','_success=_finished=YES;')
    offsets=[export.index(n) for n in needles];b.require(offsets==sorted(offsets),'export call order drift')
    for name,text in [('loop',export),('coordinator',scope)]:
        b.require('if(!_begun || _finished)return;' in text if name=='loop' else '- (NSDictionary *)result {return _entry.result;}' in text,'getter/finished behavior drift')
    metrics=w.load(REVIEW/'report.json')['cases']['normal'];last=metrics['terminal_guard']['samples_ns'][-1]
    return dict(export_source_sha256=b.sha(export.encode()),
        line_anchors={n:export[:export.index(n)].count('\n')+1 for n in needles},
        latest_live_snapshot_before_postcheck_checkpoint=True,no_live_health_read_after_receipt=True,
        finished_tick_returns_before_target_poll=True,status_getter_reads_controller_fields_only=True,
        historical_reference='frozen r4 normal model, RAW nanoseconds only',
        full_checks_after_window=[dict(phase=r['phase'],begin_after_window_ns=r['begin_ns']-last,
            end_after_window_ns=r['end_ns']-last,elapsed_ns=r['elapsed_ns'])
            for r in metrics['cadence']['full_checks'] if r['begin_ns']>=last])

def run(out):
    out=Path(out).resolve();b.require(not out.exists(),'fresh boundary audit required');out.mkdir(mode=0o700)
    done=[]
    def process(cmd,name,timeout=60):
        p=subprocess.run(cmd,capture_output=True,timeout=timeout)
        w.card.put(out,name+'.stdout',p.stdout);w.card.put(out,name+'.stderr',p.stderr)
        w.write(out/(name+'.process.json'),dict(command=cmd,returncode=p.returncode,creator_wait_verified=True))
        b.require(p.returncode==0,'process failed '+name);return p
    try:
        b.require(b.base.core.verify_seal(PARENT)==PARENT_SUM and b.base.core.verify_seal(REVIEW)==REVIEW_SUM,'parent evidence drift')
        b.verify(BUILD);before=b.prior.protected();hashes=sources();b.require(len(hashes)==663,'source count')
        w.write(out/'source-hashes.json',hashes);w.write(out/'protected-before.json',before)
        w.card.put(out,'source/'+NEW,w.plain(w.ROOT/NEW));w.write(out/'static-findings.json',static_findings())
        native=out/'native';shutil.copytree(BUILD,native);target=native/'generated/boundary_fixture.m';target.write_text(fixture())
        w.write(out/'fixture-binding.json',dict(frozen_receiver_manifest_sha256=b.sha(w.plain(BUILD/'SHA256SUMS')),
            receiver_source_count=662,audit_source_count=663,fixture_sha256=b.sha(target.read_bytes()),
            export_code_unchanged=True,only_fixture_hooks_and_capture_changed=True))
        process(b.command(native,target),'fixture-compile');engine=consumer.module(BUILD,'fixed48')
        rows={};acceptance={};proofs={}
        with tempfile.TemporaryDirectory(prefix='a23-postexport-',dir='/private/tmp') as temp:
            scratch=Path(temp);template=scratch/'template';templates.template(BUILD,template)
            for n in (145,177,225,273,321,369,417):shutil.copytree(BUILD/f'history/spent{n}',template/f'spent{n}')
            cases=scratch/'cases';cases.mkdir()
            try:
                for name,(stage,delivery,expected_success,expected_final_acceptance) in CASES.items():
                    case=cases/name;case.mkdir();host=case/'host';host.mkdir();model=case/'model';shutil.copytree(template,model)
                    store=engine.SharedSequence48(case/'namespace',simulation=True,fresh_scope=lambda:b.scope(BUILD));store.initialize(b.inputs()[4])
                    job=str(uuid.uuid4());ns=store.validate();store.prepare(job,dict(schema='A23-shared48-authorization-1',job_id=job,
                        scope_sha256=ns['scope_sha256'],maximum_invocations=1,simulation=True,hardware_test_authorized=False))
                    store.issue(job);store.consume(job)
                    config=dict(case=name,build=str(BUILD),host=str(host),repository=str(model/'repository'),cards=str(model/'cards'),
                        ledger=str(model/'ledger'),records=str(model/'records'),job=str(store.root/'jobs'/job),binding=store.binding(job),
                        audit_stage=stage,audit_delivery=delivery,audit_expected_success=expected_success,audit_capture=str(case/'at-return'))
                    w.write(case/'config.json',config)
                    p=subprocess.run([str(native/'live-fixture'),str(case/'config.json')],capture_output=True,timeout=60)
                    w.card.put(case,'native.stdout',p.stdout);w.card.put(case,'native.stderr',p.stderr)
                    w.write(case/'process.json',dict(returncode=p.returncode,creator_wait_verified=True))
                    b.require(p.returncode==0 and not p.stderr,'native failed '+name)
                    row=json.loads(p.stdout);rows[name]=row;done.append(name)
                    proofs[name]={}
                    for label,folder in [('at_return',case/'at-return'),('after_live_probe',host)]:
                        try:accepted=consumer.analyze(folder,BUILD,job=config['job'],simulation=True)
                        except (ValueError,OSError) as error:proofs[name][label]=dict(accepted=False,error=str(error))
                        else:proofs[name][label]=dict(accepted=True,sdk_bytes=accepted['entry']['sdk']['total_bytes'],service=accepted['service'])
                    b.require(proofs[name]['at_return']['accepted'] is expected_success,'at-return evidence expectation '+name)
                    b.require(proofs[name]['after_live_probe']['accepted'] is expected_final_acceptance,'post-probe expectation '+name)
                    if delivery=='queued_interest':
                        b.require(row['audit_capture']['delivered'] is False and row['audit_capture']['queued'] is True and row['audit_delivered'] is True,'queued handoff not observed')
                    if delivery=='source':
                        changed=model/'repository/research/usb-ds-iso/host/a23_scope_verifier.m'
                        w.card.put(case,'changed-model-source.m',w.plain(changed))
                    acceptance[name]=dict(loop_success=row['loop']['success'],entry_complete_after_probe=row['entry']['complete'],
                        entry_stopped_after_probe=row['entry']['stopped'],capture_delivered=row.get('audit_capture',{}).get('delivered'),
                        at_return_disk_accepted=proofs[name]['at_return']['accepted'],after_probe_disk_accepted=proofs[name]['after_live_probe']['accepted'])
                    shutil.rmtree(model)
            finally:shutil.copytree(cases,out/'cases')
        b.require(b.sources()==w.load(PARENT/'source-hashes.json') and sources()==hashes and b.prior.protected()==before,'protected source/state drift')
        w.write(out/'report.json',dict(schema='A23-postexport-boundary-audit-1',source_count=663,frozen_receiver_source_count=662,
            old662_unchanged=True,parent_manifest_sha256=PARENT_SUM,frozen_review_manifest_sha256=REVIEW_SUM,
            static=static_findings(),matrix=rows,summary=acceptance,consumers=proofs,completed=done,
            native_compiler_jobs=1,native_fixture_processes=len(done),creator_wait_verified=True,model_namespaces=len(done),
            new_receiver_builds=0,receiver_fix_implemented=False,model_sdk_operations_only=True,hardware_entry_enabled=False,
            usb_requests=0,sd_accesses=0,real_sdk_objects=0,formal_namespaces_added=0,formal_ranges=0,formal_authorizations=0,
            remaining=0,callback_drain_verified=False,future_events_excluded=False,producer_history_authenticated=False))
        w.b.seal(out);return dict(directory=str(out),seal=b.base.core.verify_seal(out),cases=len(done))
    except BaseException as e:
        w.write(out/'failure.json',dict(error=str(e),completed=done));w.b.seal(out);raise

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);print(json.dumps(run(p.parse_args().output)))
