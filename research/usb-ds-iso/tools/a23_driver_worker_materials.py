"""Pure cached-byte admission for fifteen specified driver/worker schedules."""
import a23_concurrent_diagnostics as d
import analyze_a23_two_epoch_sdk as sdk
from a23_driver_worker_failure_model import CASES
require,encode,parse,sha=d.require,d.encode,d.parse,d.sha
U64=2**64-1
GOOD={'capture-worker-error','capture-worker-exit','gate-worker-busy-error'}


def trace_expected(name):
    require(name in CASES,'unknown driver worker case')
    stage='capture_return' if name.startswith('capture-return-') else 'capture' if name.startswith('capture-') else 'commit' if name.startswith('gate-') else 'after_receipt' if name.startswith('after-receipt-') else 'after_release'
    before=3 if stage=='commit' else 4 if stage.startswith('after_') else 2
    no_begin=name in ('capture-worker-error','capture-worker-exit');unfinished='unfinished' in name;exhausted='exhausted' in name;invalid='invalid-finish' in name;wrong='wrong-ticket' in name
    after=U64-1 if exhausted else before+1 if unfinished or wrong else before+2 if invalid else before
    status=-1 if no_begin else 6 if exhausted else 3 if stage=='commit' else 0
    capture=(5 if invalid or exhausted else 3 if unfinished or wrong else 0) if stage=='capture' else 0 if stage=='capture_return' else -1
    return dict(schema='A23-driver-worker-failure-1',case=name,stage=stage,created=True,joined=True,join_status=0,
                exit_code=9 if name in ('capture-worker-exit','capture-worker-unfinished-exit') else 7 if unfinished or name in ('capture-worker-error','gate-worker-busy-error') else 0,
                tail_reached=name not in ('capture-worker-exit','capture-worker-unfinished-exit'),before_generation=before,after_generation=after,
                ticket=before+1 if status==0 else 0,begin_status=status,finish_status=2 if invalid else 4 if wrong else -1,
                poisoned=invalid or exhausted,capture_status=capture,capture_output_zeroed=capture in (3,5),injected_fixture=True,provenance_authenticated=False)


def version_expected(name):
    trace=trace_expected(name);stage=trace['stage'];gate=stage in ('commit','after_receipt','after_release') or name in GOOD
    return dict(schema='A23-versioned-driver-profile-1',constructor_generation=2,start_generation=2,end_generation=2 if gate or stage=='capture_return' else 0,
                released_generation=4 if gate else 0,expected_generation=4 if gate else 2,current_generation=4 if stage=='commit' or name in GOOD else trace['after_generation'],
                write_attempts=0,write_successes=0,busy_writes=0,last_write_status=0,append_generation=3 if gate else 0,object_bound=True,
                short_poll_observed=False,short_poll_complete=False,contract_enforced=False,actual_clock_authenticated=False)


def inventory():
    paths={'result.json','receipt-status.json','fault-facts.json','version-profile.json','session.jsonl','worker-failure.json'}
    for i in range(2):paths.update('epoch-'+str(i)+'/'+n for n in ('raw.bin','transactions.bin','before.bin','after.bin','metadata.json','SHA256SUMS','COMMITTED'))
    paths.update('sdk-receipt/'+n for n in ('receipt.json','snapshot.json','SHA256SUMS','COMMITTED'));return paths



def contract(name,cache):
    files={n:dict(bytes=len(v),sha256=sha(v)) for n,v in cache.items() if n!='worker-materials.json'}
    return encode(dict(schema='A23-driver-worker-byte-contract-1',case=name,files=files,origin='outer_cached_native_exports',provenance_authenticated=False))


def validate(name,row,cache):
    require(name in CASES and type(row) is dict and type(cache) is dict and set(cache)==inventory()|{'worker-materials.json'},'incomplete driver worker materials')
    require(all(type(k) is str and type(v) is bytes for k,v in cache.items()),'driver worker byte cache required')
    state=row['result'];version=row['version'];facts=row['facts'];receipt=row['receipt_status'];trace=row['worker_failure']
    require(encode(trace)==encode(trace_expected(name)),'worker trace differs')
    require(encode(version)==encode(version_expected(name)),'worker version differs')
    expected_facts=dict(schema='A23-injected-driver-fault-facts-1',case=name,start_accepted=True,initial_ticks=100,target_end_ticks=100,
                        initial_numerator=1,initial_denominator=1,end_numerator=1,end_denominator=1,end_domain=1,end_instance=1,mutations=0,
                        quiet_start_ticks=100,quiet_test_end_ticks=250000100,injected_fixture=True,profile_reads_atomic=False,actual_clock_authenticated=False,
                        owners=[dict(state=4,callbacks=1,retained=False,timed_out=False)]*2)
    require(encode(facts)==encode(expected_facts),'worker facts differ')
    for file,value in (('result.json',state),('version-profile.json',version),('fault-facts.json',facts),('receipt-status.json',receipt),('worker-failure.json',trace)):
        require(encode(parse(cache[file]))==encode(value),'worker export differs '+file)
    require(cache['worker-materials.json']==contract(name,cache),'worker byte contract differs')
    good=name in GOOD;stage=trace['stage'];historical=stage in ('after_receipt','after_release')
    expected=dict(schema='A23-two-epoch-sdk-result-1',session_id=state['session_id'],first_sequence=81,execution_mode='sdk_observation',
                  iso_attempts=2,trigger_attempts=2,saved_epochs=2,aborts=0,complete=good,epochs_saved_complete=good,observation_complete=good,
                  quiet_start_ticks=100,quiet_end_ticks=250000100 if good or historical else 0,lease=state['lease'],stopped=not good,
                  failure_reasons=state['failure_reasons'],journal_failed=False,all_stores_retained=True,shared_resources_retained=True,
                  callback_drain_verified=False,device_trace_verified=False,hardware_verified=False,hardware_entry_enabled=False)
    require(type(state['session_id']) is str and state['session_id'] and encode(state)==encode(expected),'worker terminal result differs')
    reasons=[] if good else ['observation_clock','observation_version'] if stage=='capture' or name=='gate-worker-object-replace' else ['observation_version']
    require(type(state['failure_reasons']) is list and sorted(state['failure_reasons'])==sorted(reasons),'worker rejection reasons differ')
    sdk.sdk_lease(state['lease'])
    lease=state['lease'];require(lease['iso_attempts']==lease['trigger_attempts']==2 and lease['aborts']==0 and lease['frame_reads']==2 and lease['status_reads']==4 and lease['iso_callbacks']==[1,1],'worker lease counts differ')
    events=[parse(line) for line in cache['session.jsonl'].splitlines()];names=[e['event'] for e in events]
    require(all(e['index']==i and e['session_id']==state['session_id'] and e['hardware_verified'] is False and e['hardware_entry_enabled'] is False for i,e in enumerate(events,1)),'worker journal binding differs')
    require(names.count('saved')==2 and names.count('epochs_saved')==1 and names.count('observation_complete')==int(good or historical or stage=='commit'),'worker event milestones differ')
    prepared=events[0]['details'];require(prepared['timebase_numerator']==prepared['timebase_denominator']==1,'worker prepared ratio differs')
    saved=next(e for e in events if e['event']=='epochs_saved');require(saved['ticks']==100,'worker quiet start differs')
    for event in events:
        if event['event']=='observation_complete':require(encode(event['details'])==encode(dict(quiet_start_ticks=100,quiet_end_ticks=250000100,minimum_ns=250000000)),'worker completion endpoint differs')
    for i in range(2):
        prefix='epoch-'+str(i)+'/';d.bundle(cache,prefix,('raw.bin','transactions.bin','before.bin','after.bin','metadata.json'))
        sdk.payload(cache[prefix+'raw.bin'],cache[prefix+'transactions.bin'],81+i*16);sdk.status(cache[prefix+'before.bin'],None if i==0 else 81);sdk.status(cache[prefix+'after.bin'],81+i*16)
        metadata=parse(cache[prefix+'metadata.json']);require(metadata['binding']['session_id']==state['session_id'] and metadata['epoch']==i and metadata['first_sequence']==81+i*16,'worker epoch binding differs')
        require(metadata['budget']['timebase_numerator']==metadata['budget']['timebase_denominator']==1 and all(metadata[k]['injected_fixture'] is True for k in ('before_observation','after_observation','sample')),'worker epoch profile differs')
    d.bundle(cache,'sdk-receipt/',('receipt.json','snapshot.json'));saved_receipt=parse(cache['sdk-receipt/receipt.json']);snapshot=parse(cache['sdk-receipt/snapshot.json'])
    require(saved_receipt['snapshot_sha256']==sha(cache['sdk-receipt/snapshot.json']) and encode(snapshot)==encode(saved_receipt['snapshot']) and snapshot['session_id']==state['session_id'],'worker receipt link differs')
    stale=stage=='after_receipt'
    expected_receipt=dict(schema='A23-two-epoch-sdk-receipt-status-1',attempted=True,saved=not stale,stale=stale,hardware_verified=False)
    require(encode(receipt)==encode(expected_receipt),'worker receipt state differs')
    if stale:
        before=dict(state,complete=True,epochs_saved_complete=True,stopped=False,observation_complete=True,failure_reasons=[])
        require(encode(snapshot)==encode(before),'worker stale snapshot relation differs')
    else:require(encode(snapshot)==encode(state),'worker receipt snapshot differs')
    healthy=trace['exit_code']==0 and trace['tail_reached'] and trace['begin_status'] in (-1,0) and trace['finish_status'] in (-1,0)
    require(not healthy,'failure fixture unexpectedly healthy')
    return dict(passed=True,case=name,evidence_complete=True,driver_complete=good,worker_success=healthy,completion_admitted=good and healthy,
                receipt_stale=stale,events=names,worker_trace=trace,version=version,consumer_filesystem_calls=0,provenance_authenticated=False)
