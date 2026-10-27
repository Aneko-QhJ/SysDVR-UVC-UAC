"""Q2c static budget and handoff audit. No device, SDK or acquisition entry."""
import argparse
import json
from pathlib import Path
import build_a23_live132_q1 as b
import audit_a23_q2_generation_model as q2b
from analyze_ep0_execution_v3 import decode_execution

w=b.w;core=b.base.base.base.core
PARENT=w.A/'A23-q2b-generation-model-closeout-20261026'
PARENT_SEAL='bfd01aa921ca2644be9125bb9e377671afd7f196463ac0193457e37f42d3bfba'
NEW='tools/audit_a23_q2_evidence_budget.py'


def replay_ready_groups(start, groups, *, capacity=256, reserve=17):
    """Conditional CPU replay of source guard over provided record counts."""
    used=start;steps=[]
    for phase,interface,cost in groups:
        if used>capacity-reserve:
            return dict(accepted_all=False,final_count=used,steps=steps,
                refused=dict(phase=phase,interface=interface,before_count=used,
                             required_request_reserve=reserve,available=capacity-used))
        b.require(type(cost) is int and 0<=cost<=reserve,'provided shape violates17-record envelope')
        steps.append(dict(phase=phase,interface=interface,before=used,records=cost,after=used+cost))
        used+=cost
    return dict(accepted_all=True,final_count=used,steps=steps,refused=None)


def run(out):
    out=w.canonical(out);b.require(not out.exists(),'fresh review required')
    b.require(core.verify_seal(PARENT)==PARENT_SEAL,'Q2b parent drift')
    ticket=w.A/'A23-context65-pending.json';record=w.A/'A23-live132-q1-once-20261026-r1.json'
    b.require(w.plain(ticket)==w.plain(PARENT/'ticket.json') and
              w.plain(record)==w.plain(PARENT/'actual465-unchanged.json'),'state drift')
    frozen=b.sources();prior=frozen|{'research/usb-ds-iso/'+n:b.sha(w.plain(w.ROOT/n)) for n in q2b.NEW}
    b.require(len(prior)==675 and prior==w.load(PARENT/'source-hashes.json'),'675 source drift')
    sources=prior|{'research/usb-ds-iso/'+NEW:b.sha(w.plain(w.ROOT/NEW))}
    b.require(len(sources)==676,'new research source inventory differs')
    protected=b.base.base.prior.protected();record_raw=w.plain(record)
    ledger={p.relative_to(b.FORMAL_ROOT).as_posix():b.sha(w.plain(p)) for p in b.FORMAL_ROOT.rglob('*') if p.is_file()}
    b.require(ledger==w.load(PARENT/'namespace465-hashes.json'),'namespace465 drift')
    actual=w.load(record);build=Path(actual['build']);archive=b.verify(build,current=False)
    package=w.card.once.PACKAGE;package_ref=w.card.pkg.verify_review(package)
    binding=w.load(package/'device-binding.json');device=Path(binding['device_source_root'])
    device_seal=core.verify_seal(device.parent);recipe=w.load(device/'recipe.json')
    b.require(recipe['runtime_recipe_sha256']==binding['runtime_recipe_sha256']==w.load(build/'descriptor.json')['recipe_sha256']
              and recipe['window_ms']==30000,'device recipe differs')
    snapshot=Path(actual['card_snapshot']);saved=w.card.verify_snapshot(snapshot)
    b.require(w.latest_snapshot()==snapshot and len([n for n in saved if n.startswith('card/')])==138,'latest138 differs')
    analysis=Path(actual['device_analysis']);w.card.seal_verify(analysis);d=w.load(analysis/'report.json')
    execution_raw=saved['card/'+d['matched_execution']]
    decoded=decode_execution(execution_raw,recipe['runtime_recipe_sha256'])
    b.require(decoded==w.load(analysis/(d['matched_execution']+'.decoded.json')),'original execution decode differs')
    trace=decoded['primary']['trace'];groups=trace['requests']
    b.require(trace['capacity']==256 and trace['record_count']==216 and not trace['dropped_records'] and
              not trace['invalid_records'] and len(groups)==30,'trace shape differs')
    b.require(sorted(r['ordinal'] for g in groups for r in g['records'])==list(range(1,217)),
              'groups do not partition the original trace')
    files=['uvc/ep0_trace.h','uvc/ep0_trace_owner.h','uvc/ep0_request_admission.h',
        'uvc/ep0_request_admission.c','uvc/ep0_candidate_guard.c','uvc/ep0_buffer_guard.h',
        'uvc/ep0_candidate.c','uvc/uvc_device.c','uvc/ep0_candidate_window.h','sysmodule/main.c',
        'uvc/ep0_execution_v3.h','uvc/ep0_session_runtime.c','uvc/ep0_candidate_file.c',
        'uvc/ep0_session_file.c','uvc/ep0_execution_sink_v3.h','uvc/ep0_candidate_sink.h',
        'uvc/ep0_cleanup_gate.h']
    raw={'device/'+n:w.plain(device/'source'/n,4*1024*1024) for n in files}
    raw['host/live_driver.m']=w.plain(build/'generated/live_driver.m')
    facts=[]
    def fact(id,path,text,claim):
        lines=[i+1 for i,line in enumerate(raw[path].decode().splitlines()) if text in line]
        b.require(lines,'missing bound source fact '+id)
        facts.append(dict(id=id,path=path,lines=lines,needle=text,sha256=b.sha(raw[path]),claim=claim))
    fact('F1','device/uvc/ep0_trace.h','#define EP0_TRACE_CAPACITY 256u','deployed trace capacity256')
    fact('F2','device/uvc/ep0_trace_owner.h','#define EP0_OWNER_SLOTS 32u','deployed identity capacity32')
    fact('F3','device/uvc/ep0_request_admission.h','#define EP0_REQUEST_RECORD_RESERVE 17u','ready request reserve17')
    fact('F4','device/uvc/ep0_request_admission.c','o->trace.count>EP0_TRACE_CAPACITY-EP0_REQUEST_RECORD_RESERVE',
         'local ready request checks before recording; not an epoch reservation')
    fact('F5','device/uvc/ep0_request_admission.c','o->trace.count-admission_state.before_count>EP0_REQUEST_RECORD_RESERVE',
         'post-request envelope violation stops, not successful budget extension')
    fact('F6','device/uvc/ep0_request_admission.c','One possible disconnect record outside ready-request handling.',
         'one nonrequest record per owner call is not a whole-window external-traffic bound')
    fact('F7','device/uvc/ep0_candidate.c','storage.fault=1;Ep0CandidateRequestStop();','capacity/guard failure requests stop')
    fact('F8','device/uvc/uvc_device.c','if(!Ep0CandidateAdmissionReady())return false;',
         'denial precedes trace_request/eventClear/setup handling')
    fact('F9','device/uvc/uvc_device.c','(setup.wIndex & 0xFF) != iface->interface_index',
         'non-target interface returns after3 records only under intended interface setup shape')
    fact('F10','device/uvc/ep0_trace_owner.h','Never reuse a (channel,id) within a session;',
         'terminal identities continue consuming session slots')
    fact('F11','device/uvc/ep0_buffer_guard.h','o->used>EP0_OWNER_SLOTS-reserve',
         'backing guard includes remaining identity capacity before modifications')
    fact('F12','device/uvc/ep0_request_admission.c','Both use the total',
         'ISO plus ACK reserves two identities in total, not two twice')
    fact('F13','device/uvc/ep0_candidate_window.h','checked ONLY between synchronous owner calls.',
         'local window is not a preemptive owner-call deadline')
    fact('F14','device/sysmodule/main.c','UvcDeviceProcessRequests();',
         'window is checked around the synchronous call')
    fact('F15','device/sysmodule/main.c','Ep0ExecutionWindowStarted(window.start,armGetSystemTickFreq(),30000)',
         '30s window begins before waiting for readiness, not at first ISO')
    fact('F16','device/uvc/uvc_device.c','while (serviced && !Ep0CandidateStopRequested()',
         'one owner call may service multiple setup groups without checking window expiry inside this loop')
    fact('F17','device/uvc/ep0_trace_owner.h','s->writer || !ep0_trace_init',
         'owner initialization is one-shot for current storage')
    fact('F18','device/uvc/ep0_execution_v3.h','atomic_compare_exchange_strong_explicit(&w->phase,&expected,3',
         'execution window start consumes its unused phase')
    fact('F19','device/uvc/ep0_session_runtime.c','atomic_compare_exchange_strong_explicit(&execution_phase,&expected,1',
         'execution envelope build consumes its phase once')
    fact('F20','device/uvc/ep0_trace_owner.h','No polling',
         'writer join/ownership handoff does not itself request USB closure')
    fact('F21','device/uvc/ep0_trace_owner.h','s->processing || s->fault || ep0_owner_pending(s))return 0;',
         'normal memory export needs stopped/joined/no-fault/no-pending owner')
    fact('F22','device/sysmodule/main.c','Result video_join=threadWaitForExit(&g_videoThread);','real video join before export')
    fact('F23','device/sysmodule/main.c','Result audio_join=threadWaitForExit(&g_audioThread);','real audio join before export')
    fact('F24','device/sysmodule/main.c','Ep0LifeFinish(EP0_L_RETAIN,0,4);for(;;)',
         'diagnostic branch preserves failure rather than authorizing cleanup or next segment')
    fact('F25','device/uvc/ep0_candidate_file.c','if(R_FAILED(rc))return rc;',
         'exclusive create failure has no delete/truncate fallback')
    fact('F26','device/uvc/ep0_execution_sink_v3.h','if(!s || s->attempted)return false;',
         'execution sink has one attempt')
    fact('F27','device/uvc/ep0_execution_sink_v3.h','s->commit_acknowledged=true;',
         'byte readback and commit acknowledgment precede sink success')
    fact('F28','device/uvc/ep0_candidate_sink.h','not power-loss proof.',
         'API success is not physical power-loss durability')
    fact('F29','device/sysmodule/main.c','if(!normal_saved || !execution_saved)',
         'normal cleanup fails closed if either evidence save fails')
    fact('F30','host/live_driver.m','_pending=YES;_submittedAt[_epoch]',
         'host ISO is armed after before STATUS and before the scoped BURST')
    main=raw['device/sysmodule/main.c'].decode();driver=raw['host/live_driver.m'].decode()
    b.require(main.index('Result video_join=threadWaitForExit')<main.index('bool ownership_ready=Ep0CandidateFinish') and
              main.index('Result audio_join=threadWaitForExit')<main.index('bool ownership_ready=Ep0CandidateFinish') and
              main.index('if(!normal_saved || !execution_saved)')<main.index('threadClose(&g_videoThread)')<
              main.index('if(!ep0_cleanup_authorize'), 'join/save/cleanup source order differs')
    b.require(driver.index('NSDictionary *reply=[_resources readStatus];uint64_t lower=_epoch')<
              driver.index('_pending=YES;_submittedAt[_epoch]')<driver.index('if(![self emit:@"trigger_intent"'),
              'host STATUS/ISO/BURST order differs')
    observed=[]
    for n in range(3):
        phase_counts=[];phase_ids=[]
        for phase in range(3):
            subset=groups[3+n*9+phase*3:3+n*9+(phase+1)*3]
            phase_counts.append(sum(len(g['records']) for g in subset))
            phase_ids.append(sum(r['stage'] in ('ctrl_post','iso_post') and r['result_u32']==0 for g in subset for r in g['records']))
        b.require(phase_counts==[23,20,23] and phase_ids==[2,2,2],'observed per-phase shape differs')
        observed.append(dict(epoch=n,phase_records=phase_counts,records=sum(phase_counts),phase_identities=phase_ids,identities=sum(phase_ids)))
    shape=[(('before','burst','after')[i//3],g['interface'],len(g['records'])) for i,g in enumerate(groups[-9:])]
    original_shape=[('bootstrap' if i<3 else 'epoch',g['interface'],len(g['records'])) for i,g in enumerate(groups)]
    replay=replay_ready_groups(0,original_shape)
    b.require(replay['accepted_all'] and replay['final_count']==216,'original trace local admission replay differs')
    fourth=replay_ready_groups(216,shape)
    b.require(not fourth['accepted_all'] and fourth['final_count']==242 and
              fourth['refused']['phase']=='burst' and fourth['refused']['interface']==1 and len(fourth['steps'])==4,
              'conditional mid-epoch witness differs')
    fourth.update(hypothetical_only=True,not_executed=True,host_ISO_may_already_be_pending_under_source_order=True,
                  current_driver_max3_unchanged=True,remaining_range_authorization=0)
    boundaries=[]
    for used in range(257):
        row=replay_ready_groups(used,shape)
        b.require(row['final_count']<=256 and row['final_count']>=used,'local replay arithmetic invalid')
        boundaries.append(dict(trace_used=used,accepted_all=row['accepted_all'],final_count=row['final_count']))
    capacities=[]
    for used in range(257):
        for label,cost in [('conditional_interface_shape',69),('generic_nine_ready_handlers',153)]:
            fits=used+cost+1<=256
            b.require(fits==(used<=256-cost-1),'whole epoch credit threshold differs')
            capacities.append(dict(trace_used=used,basis=label,trace_cost=cost,illustrative_stop_margin=1,
                                   capacity_fits=fits,actual_admission_authorized=False))
    b.require(sum(r['capacity_fits'] for r in capacities if r['basis']=='conditional_interface_shape')==187 and
              sum(r['capacity_fits'] for r in capacities if r['basis']=='generic_nine_ready_handlers')==103,
              'threshold case counts differ')
    urbs=decoded['primary']['urbs'];b.require(len(urbs)==19 and all(u['status']==3 for u in urbs),'identity ledger differs')
    budget=dict(schema='A23-q2c-budget-bases-1',observed_bootstrap_records=18,observed_epochs=observed,
        observed_trace=216,trace_capacity=256,observed_identity_used=19,identity_capacity=32,
        terminal_identity_reclaimed=False,observed_same_shape_epoch_records=66,
        observed_four_projection=282,observed_four_projection_not_permission=True,
        source_per_ready_envelope=17,conditional_interface_shape_epoch_reserve=3*(3+3+17),
        generic_nine_ready_handler_reserve=9*17,conditional_identity_cost_per_epoch=6,
        illustrative_extra_record_margin=1,whole_epoch_reservation_implemented=False,
        nonrequest_traffic_whole_epoch_bound_established=False,ready_group_count_runtime_enforced=False,
        time_budget_for_epoch_established=False,all_fits_results_capacity_only=True)
    window=dict(schema='A23-q2c-window-boundary-1',configured_ms=30000,starts_before_USB_ready=True,
        hard_preemptive_deadline_proven=False,synchronous_owner_call_bound_proven=False,
        checked_between_owner_calls=True,observed_Q1_seconds=d['device_window_seconds'],
        hypothetical_call_begin_ns=29999000000,hypothetical_call_duration_ns=250000000,
        hypothetical_call_return_ns=30249000000,hypothetical_overrun_ns=249000000,
        example_is_not_a_measurement_or_upper_bound=True,host_device_clocks_absolutely_calibrated=False)
    requirements=[
      ('E1','segment_identity','Bind unique segment/session,recipe,source closure,sequence domain and predecessor manifest. Do not reset identity history.'),
      ('E2','pre_admission_credit','Reserve complete bounded request schedule plus nonrequest/stop evidence, identities and local metadata before ISO submission.'),
      ('E3','time_policy','Declare owner-call duration/time assumptions;30s outer polling is not a preemptive bound. Unknown duration does not authorize deadline admission.'),
      ('E4','stop_new_work','Coordinate host and device stop of new admission; do not treat a single local flag as every source closed.'),
      ('E5','pending_ownership','Finish or retain admitted requests. Pending/fault/unknown native handoff never permits overwrite, ledger clear or cleanup.'),
      ('E6','writer_handoff','Freeze at owner boundary and require successful real joins,stopped writer,authorized exporter and appropriate pending/fault checks.'),
      ('E7','immutable_evidence','Create uniquely,read back,commit and seal complete evidence. Diagnostic evidence never becomes a normal-release receipt.'),
      ('E8','consumer_ack','Bind acknowledgment to exact segment manifest and continuity. Missing/contradictory ack cannot free evidence credit by assumption.'),
      ('E9','new_segment_gate','Require separate backing/callback safety plus completed evidence handoff; existing one-shot owner/window/sink cannot simply be reset.'),
      ('E10','scope','New real work requires a new latest-baseline candidate,range,authorization and readiness. This audit proposes no range or device change.')]
    contract=dict(schema='A23-q2c-evidence-handoff-contract-1',implemented=False,source_closed_rollover_proven=False,
        lossless_rollover_verified=False,native_buffer_handoff_proven=False,actual_admission_enabled=False,
        requirements=[dict(id=i,topic=t,requirement=r,status='required_not_implemented') for i,t,r in requirements])
    out.mkdir(mode=0o700)
    for name,data in raw.items():w.card.put(out,'inputs/'+name,data)
    w.card.put(out,'source/'+NEW,w.plain(w.ROOT/NEW));w.card.put(out,'matched-execution.bin',execution_raw)
    w.write(out/'decoded-execution.json',decoded);w.write(out/'source-facts.json',facts)
    w.write(out/'budget-bases.json',budget);w.write(out/'mid-epoch-witness.json',fourth)
    w.write(out/'local-boundary-replays.json',boundaries);w.write(out/'capacity-only-cases.json',capacities)
    w.write(out/'window-boundary.json',window);w.write(out/'handoff-contract.json',contract)
    w.write(out/'source-hashes.json',sources);w.write(out/'base672-source-hashes.json',frozen)
    w.write(out/'prior675-source-hashes.json',prior);w.write(out/'protected-before.json',protected)
    w.write(out/'namespace465-hashes.json',ledger);w.card.put(out,'actual465-unchanged.json',record_raw)
    w.card.put(out,'ticket-before.json',w.plain(ticket))
    w.write(out/'references.json',dict(parent=str(PARENT),parent_seal=PARENT_SEAL,build=archive,
        package=package_ref,device_review=str(device.parent),device_review_seal=device_seal,
        runtime_recipe=recipe['runtime_recipe_sha256'],snapshot=str(snapshot),snapshot_seal=core.verify_seal(snapshot),
        device_analysis=str(analysis),device_analysis_seal=core.verify_seal(analysis)))
    b.require(b.sources()==frozen and prior==frozen|{'research/usb-ds-iso/'+n:b.sha(w.plain(w.ROOT/n)) for n in q2b.NEW} and
              sources==prior|{'research/usb-ds-iso/'+NEW:b.sha(w.plain(w.ROOT/NEW))},'source drift')
    b.require(b.base.base.prior.protected()==protected and w.plain(record)==record_raw,'protected drift')
    b.require(ledger=={p.relative_to(b.FORMAL_ROOT).as_posix():b.sha(w.plain(p)) for p in b.FORMAL_ROOT.rglob('*') if p.is_file()},'namespace465 drift')
    report=dict(schema='A23-q2c-evidence-budget-review-1',passed=True,research_source_count=676,
        frozen_receiver_source_count=672,prior675_unchanged=True,new_research_sources=1,
        source_fact_checks=len(facts),original_execution_redecoded_equal=True,original_request_groups=30,
        original_trace_records=216,local_ready_boundary_replays=257,capacity_only_cases=514,
        hypothetical_mid_epoch_refusal_count=242,handoff_requirements=10,
        reservation_implemented=False,lossless_rollover_verified=False,hard_deadline_proven=False,
        native_buffer_handoff_proven=False,compiler_jobs=0,native_fixture_processes=0,
        SDK_objects=0,SDK_method_calls=0,usb_requests=0,sd_accesses=0,
        formal_ranges=0,formal_authorizations=0,model_namespaces=0,remaining=0,
        actual465_and_namespace465_unchanged=True,old_actual_and_nine_namespaces_unchanged=True)
    w.write(out/'report.json',report);w.b.seal(out);w.card.seal_verify(out)
    return dict(seal=core.verify_seal(out),report=report)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path)
    print(json.dumps(run(p.parse_args().output)))
