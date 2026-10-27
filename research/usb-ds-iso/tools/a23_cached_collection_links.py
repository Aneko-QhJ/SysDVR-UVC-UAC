"""Pure joins of historical admission, verifier declarations and static collection.

This profile verifies cached metadata against cached bytes. It neither reruns
the verifier nor authenticates its count, a live source tree, or a child exit.
"""
import a23_cached_clock_domains as clock

permit=clock.permit
prior=clock.prior
view,ar,a,f=clock.view,clock.ar,clock.a,clock.f
ENV=permit.ENV
FINAL=ENV+'final/'
INPUTS=permit.INPUTS
HOST=permit.HOST
COLLECTION_FLAGS=('hardware_verified','hardware_entry_enabled','formal_issuance_available',
                  'process_origin_authenticated','callback_drain_verified','cleanup_authorized',
                  'allow_retry','sequences_allocated')
ENVELOPE_FLAGS=(*COLLECTION_FLAGS,'acquisition_permitted','parent_sandbox_evaluated',
                'production_execution_authorized','same_physical_run_verified')
FALSE={**clock.FALSE,'live_source_freshness_verified':False,'verifier_execution_authenticated':False,
       'verifier_check_count_authenticated':False,'saved_full_analysis_reproduced':False}


def equal(left,right,message):permit.equal(left,right,message)
def obj(raw,name):return permit.obj(raw,name)


def admission(raw,receiver,supervisor):
    expected=dict(schema='A23-model-source-admission-1',
                  source_sha256=receiver['scope']['workflow_source_sha256'],
                  observed_sha256=receiver['scope']['workflow_source_sha256'],
                  source_count=receiver['reference']['frozen_source_count'],source_match=True,
                  receiver_build=receiver['reference'],supervisor_build=supervisor['reference'],
                  point_in_time_only=True,production_execution_authorized=False)
    equal(obj(raw,ENV+'admission.json'),expected,'historical source admission differs')
    f.require(raw[ENV+'ADMISSION_ATTEMPT']==b'one source admission attempt\n','admission attempt differs')
    for name in ('scope.json','expected-scope.json'):
        equal(obj(raw,ENV+name),receiver['scope'],'envelope expected scope differs')
    return dict(historical_source_count=expected['source_count'],
                historical_source_sha256=expected['source_sha256'],point_in_time_only=True)


def verifier(raw):
    report=obj(raw,INPUTS+'report.json')
    f.require(set(report)=={'schema','case','command_valid','model_execute_admitted','actual_context',
              'execution_context','execution_context_injected','entry','native','final','calls',
              'verifier','real_sdk_objects','usb_requests','sd_accesses'} and
              report['schema']=='A23-verified-scope-fixture-1','report shape differs')
    v=report['verifier']
    f.require(type(v) is dict and set(v)=={'schema','checks','failed','model_roots',
              'binary_origin_authenticated','hardware_entry_enabled','hardware_verified'} and
              v['schema']=='A23-readonly-scope-verifier-result-1' and v['failed'] is False and
              v['model_roots'] is True and permit.session.number(v['checks'],1,2**32-1) and
              all(v[k] is False for k in ('binary_origin_authenticated','hardware_entry_enabled','hardware_verified')),
              'verifier declaration differs')
    equal(report['final'],obj(raw,HOST+'entry-final-status.json'),'report final checkpoint differs')
    driver=obj(raw,HOST+'result.json')
    equal(report['calls'],dict(aborts=driver['aborts'],burst_triggers=driver['trigger_attempts'],
          iso_submissions=driver['iso_attempts'],opens=1,wait_creates=1),'model call declarations differ')
    plan=obj(raw,ENV+'plan.json')
    f.require(type(report['case']) is str and report['case']==plan['case'],'report case differs')
    return dict(declared_checks=v['checks'],model_roots=True,declared_model_calls=report['calls'])


def collection(raw,journal,receiver):
    meta=obj(raw,FINAL+'collection.json')
    f.require(set(meta)=={'schema','origin','build_reference','raw_files','directories',
              'report_sha256','observation',*COLLECTION_FLAGS} and
              meta['schema']=='A23-final-collection-1' and
              all(meta[k] is False for k in COLLECTION_FLAGS),'collection shape/authority differs')
    equal(meta['build_reference'],receiver['reference'],'collection receiver differs')
    # Only the frozen static profile is supported; outer exit declarations
    # cannot promote this to an independently observed receiver execution.
    f.require(meta['origin']=='supplied_static_model','unsupported collection origin profile')
    equal(meta['observation'],dict(mode='supplied_static_model',child_exited=False,
          returncode=None,binary_sha256=None),'static collection claims exit')
    inputs={n[len(INPUTS):]:v for n,v in raw.items() if n.startswith(INPUTS)}
    equal(meta['raw_files'],a.inventory(inputs),'collection input inventory differs')
    directories=[n[len(INPUTS):] for n in journal[1]['directories'] if n.startswith(INPUTS)]
    equal(meta['directories'],directories,'declared collection directory coverage differs')
    f.require(raw[FINAL+'ATTEMPT']==b'one final collection attempt\n' and
              meta['report_sha256']==f.sha(raw[FINAL+'report.json']),'collection attempt/report pin differs')
    files=prior.sealed_bytes(raw,FINAL)
    f.require(set(files)=={'ATTEMPT','collection.json','analysis.json','report.json','process.stdout','process.stderr'} |
              {'inputs/'+n for n in inputs},'final member coverage differs')
    for stream in ('stdout','stderr'):
        f.require(raw[FINAL+'process.'+stream]==raw[ENV+'supervision/'+stream+'.bin'],
                  'collected supervisor stream copy differs')
    return dict(origin=meta['origin'],input_files=len(inputs),input_bytes=sum(map(len,inputs.values())),
                declared_directories=len(directories),receiver_exit_observed=False,
                report_sha256=meta['report_sha256'])


def saved_summary(raw,journal,clock_result):
    """Compare saved summaries to established subsets, without adopting claims."""
    saved=obj(raw,FINAL+'analysis.json')
    f.require(set(saved)=={'schema','classification','supplied_model_chain_complete','errors','entry','shared',*COLLECTION_FLAGS} and
              saved['schema']=='A23-final-input-analysis-1' and saved['classification']=='complete_model_chain' and
              saved['supplied_model_chain_complete'] is True and saved['errors']==[] and
              all(saved[k] is False for k in COLLECTION_FLAGS),'saved summary shape/authority differs')
    shared=dict(schema='A23-shared32-native-analysis-1',native_process_and_selection_claimed=True,
                receiver_launched=False,remaining=0,reserved_sequences=32,shared_reservation_files=1,
                supplied_model_chain_complete=True,formal_issuance_available=False,hardware_entry_enabled=False,
                hardware_verified=False,process_origin_authenticated=False)
    equal(saved['shared'],shared,'saved shared summary differs')
    packets=prior.consume(*journal)
    epochs=[dict(epoch=r['epoch'],first_sequence=r['first_sequence'],urb_id=r['urb_id'],
                 effective_slots=r['effective_slots'],bytes=r['effective_bytes']) for r in packets['epochs']]
    sdk=dict(schema='A23-two-epoch-sdk-analysis-1',input_origin='injected_sdk_model',epochs=epochs,
             total_bytes=packets['total_effective_bytes'],observation_window_ns=clock_result['model_quiet_interval_ns'],
             resource_and_epoch_checks=True,supplied_sdk_chain_complete=True,
             **{k:False for k in ('callback_drain_verified','continuous_streaming_verified','device_trace_verified',
                'hardware_entry_enabled','hardware_verified','physical_run_authenticated','sequences_allocated')})
    entry=dict(schema='A23-two-epoch-entry-analysis-1',claims_and_wait_order_consistent=True,
               supplied_context_consistent=True,supplied_entry_chain_complete=True,sdk=sdk,
               **{k:False for k in ('callback_drain_verified','formal_issuance_available','hardware_entry_enabled',
                  'hardware_verified','physical_run_authenticated','process_origin_authenticated',
                  'production_permit_authenticated','sequences_allocated')})
    equal(saved['entry'],entry,'saved entry/packet/quiet summary differs')
    return dict(saved_full_chain_claim=True,summary_fields_match_established_subsets=True,
                total_effective_bytes=packets['total_effective_bytes'])


def envelope(raw,receiver,supervisor):
    meta=obj(raw,ENV+'envelope.json')
    f.require(set(meta)=={'schema','receiver_build','supervisor_build','producer_exited','child_pid',
              'control_delivery','complete_injected_model_chain','report_state',*ENVELOPE_FLAGS} and
              meta['schema']=='A23-model-failure-envelope-1' and
              all(meta[k] is False for k in ENVELOPE_FLAGS),'envelope shape/authority differs')
    equal(meta['receiver_build'],receiver['reference'],'envelope receiver differs')
    equal(meta['supervisor_build'],supervisor['reference'],'envelope supervisor differs')
    f.require(meta['producer_exited'] is True and meta['complete_injected_model_chain'] is True and
              meta['report_state']=='object' and meta['control_delivery']=='whole_written',
              'envelope success declaration differs')
    f.require(raw[ENV+'FINAL_ATTEMPT']==b'one model failure envelope attempt\n','envelope attempt differs')
    files=prior.sealed_bytes(raw,ENV)
    top={'FINAL_ATTEMPT','envelope.json','plan.json','scope.json','expected-scope.json',
         'admission.json','ADMISSION_ATTEMPT','control.json'}
    f.require(set(files)==top | {n for n in files if n.startswith(('supervision/','final/'))},
              'envelope member coverage differs')
    return dict(producer_exit_declared=True,full_chain_claim_declared=True,report_state='object')


def consume(receiver,supervisor,journal,link_bytes,link_digest,profile_bytes,profile_digest):
    base=clock.consume(receiver,supervisor,journal,link_bytes,link_digest,profile_bytes,profile_digest)
    result=dict(schema='A23-cached-collection-links-1',classification='inconsistent_collection_metadata_subset',
                errors=[],reasons={},prior_subsets_consistent=not base['errors'],observations={},**FALSE)
    if base['errors']:
        result['errors']=['prior_subset'];result['reasons']['prior_subset']=','.join(base['errors']);return result
    raw=prior.verify_scope(*journal)
    rcache,_=permit.session.build.grouped.consume(*receiver)
    scache,_=permit.session.build.grouped.consume(*supervisor)
    r=permit.session.build.verify_receiver(rcache);s=permit.session.build.verify_supervisor(scache)
    for name,action in (
        ('admission',lambda:admission(raw,r,s)),('verifier',lambda:verifier(raw)),
        ('collection',lambda:collection(raw,journal,r)),
        ('saved_summary',lambda:saved_summary(raw,journal,base)),('envelope',lambda:envelope(raw,r,s))):
        try:result['observations'][name]=action()
        except (ValueError,KeyError,TypeError,UnicodeError,RecursionError,IndexError) as exc:
            result['errors'].append(name);result['reasons'][name]=str(exc)
    if not result['errors']:result['classification']='consistent_cached_static_collection_metadata_subset'
    return result
