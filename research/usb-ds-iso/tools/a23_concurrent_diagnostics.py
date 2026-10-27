"""Pure byte-cache diagnostics for declared offline cases; no filesystem calls."""
import hashlib,json
import analyze_a23_two_epoch_sdk as sdk
DEADLINES=tuple('-'.join((t,m,r,e)) for t in ('control','iso') for m in ('arrival','poll') for r in ('1to1','2to3') for e in ('before','equal','after'))
PROFILES=tuple('profile-'+s+'-'+p for s in ('start','end') for p in ('numerator','denominator','domain','instance','aba'))
BASE_NAMES=DEADLINES+PROFILES+('duplicate-iso','duplicate-control','foreign-pointer','control-error','control-bytes','iso-error','callback-queued-delay','old-control-between-epochs','early-iso','iso-reject','trigger-reject','iso-abort-late','normal','between-captures-aba','after-capture-aba','append-aba-attempt','append-visible-attempt','append-callback','append-journal-failure','post-receipt-aba','object-replaced','zero-quiet-start','fractional-short-equal','append-object-replaced','profile-end-bypass')
NEW=('gate-publish','gate-aba','gate-noop','gate-two-publishers','gate-iso-before-write','gate-write-before-iso','gate-control-before-write','gate-write-before-control','gate-journal-failure','after-release-aba','after-receipt-aba','after-receipt-noop','capture-return-aba')
ALL=BASE_NAMES+NEW
VERSION_KEYS={'schema','constructor_generation','start_generation','end_generation','released_generation','expected_generation','current_generation','write_attempts','write_successes','busy_writes','last_write_status','append_generation','object_bound','short_poll_observed','short_poll_complete','contract_enforced','actual_clock_authenticated'}


def require(value,message):
    if not value:raise ValueError(message)


def encode(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(raw):return hashlib.sha256(raw).hexdigest()
def unique(pairs):
    out={}
    for key,value in pairs:require(key not in out,'duplicate diagnostic key');out[key]=value
    return out

def parse(raw):
    require(type(raw) is bytes and len(raw)<=2*1024*1024,'diagnostic bytes required')
    return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _:require(False,'nonfinite diagnostic'))

def bundle(cache,prefix,names):
    expected=set(names)|{'SHA256SUMS','COMMITTED'}
    require({k[len(prefix):] for k in cache if k.startswith(prefix)}==expected,'cached bundle inventory differs')
    sums=''.join(sha(cache[prefix+n])+'  '+n+'\n' for n in sorted(names)).encode()
    require(cache[prefix+'SHA256SUMS']==sums and cache[prefix+'COMMITTED']==(sha(sums)+'\n').encode(),'cached bundle seal differs')


def trace_expected(name):
    require(name in NEW,'unknown concurrency case')
    count=2 if name=='gate-two-publishers' else 1
    stage='commit' if name.startswith('gate-') else 'after_receipt' if name.startswith('after-receipt-') else 'after_release' if name.startswith('after-release-') else 'capture_return'
    before=3 if stage=='commit' else 2 if stage=='capture_return' else 4
    writes=2 if 'aba' in name else 1;after=before if stage=='commit' else before+2*writes
    actions=['publish']*writes
    kind='iso' if 'iso' in name else 'control' if 'control' in name else None
    if kind:actions=([kind]+actions) if 'before-write' in name else (actions+[kind])
    workers=[dict(index=n,before_generation=before,after_generation=after,statuses=[3 if stage=='commit' else 0]*writes,actions=actions) for n in range(count)]
    return dict(schema='A23-commit-concurrency-trace-1',case=name,stage=stage,worker_count=count,ready_count=count,workers=workers,injected_fixture=True,actual_clock_authenticated=False)


def version_expected(name,state):
    n,d=(2,3) if '-2to3-' in name or name=='fractional-short-equal' else (1,1)
    constructor=6 if d==3 else 2;saved=state['saved_epochs']
    started=saved==2 and not (name.startswith('profile-start-') or name=='zero-quiet-start')
    gate=state['complete'] or name in ('append-callback','append-journal-failure','post-receipt-aba','append-object-replaced') or name in NEW and name!='capture-return-aba'
    attempts=2 if constructor==6 else 0;success=attempts;busy=0;status=0
    current=constructor+(2 if gate else 0)
    if name in PROFILES:
        writes=2 if name.endswith('-aba') else 1;attempts+=writes
        success+=0 if name.endswith('-domain') else writes;status=2 if name.endswith('-domain') else 0;current=constructor+2*writes
    if name in ('between-captures-aba','after-capture-aba','post-receipt-aba'):
        attempts+=2;success+=2;current=constructor+(4 if name=='between-captures-aba' else 6)
    if name in ('append-aba-attempt','append-visible-attempt'):
        busy=2 if name=='append-aba-attempt' else 1;attempts+=busy;status=3
    if name in NEW:
        trace=trace_expected(name);writes=sum(len(w['statuses']) for w in trace['workers']);attempts+=writes
        if trace['stage']=='commit':busy=writes;status=3
        else:success+=writes;current=trace['workers'][-1]['after_generation']+(2 if name=='capture-return-aba' else 0)
    end=constructor if gate or name in ('after-capture-aba','capture-return-aba') else 0
    return dict(schema='A23-versioned-driver-profile-1',constructor_generation=constructor,start_generation=constructor if started else 0,
        end_generation=end,released_generation=constructor+2 if gate else 0,expected_generation=constructor+2 if gate else constructor if started else 0,
        current_generation=current,write_attempts=attempts,write_successes=success,busy_writes=busy,last_write_status=status,
        append_generation=constructor+1 if gate and name not in ('append-journal-failure','gate-journal-failure') else 0,
        object_bound=True,short_poll_observed=name=='fractional-short-equal',short_poll_complete=False,contract_enforced=False,actual_clock_authenticated=False)


def validate(name,row,cache):
    require(name in ALL and type(row) is dict and type(cache) is dict and all(type(k) is str and type(v) is bytes for k,v in cache.items()),'declared diagnostic input required')
    state=row['result'];version=row['version'];facts=row['facts'];receipt=row['receipt_status']
    for file,value in (('result.json',state),('version-profile.json',version),('fault-facts.json',facts),('receipt-status.json',receipt)):
        require(encode(parse(cache[file]))==encode(value),'diagnostic export differs '+file)
    require(set(version)==VERSION_KEYS and encode(version)==encode(version_expected(name,state)),'complete version diagnostics differ '+name)
    events=[parse(line) for line in cache['session.jsonl'].splitlines()];prepared=events[0]['details']
    require(all(e['session_id']==state['session_id'] and e['index']==i and e['hardware_verified'] is False for i,e in enumerate(events,1)),'diagnostic journal binding differs')
    n,d=(2,3) if '-2to3-' in name or name=='fractional-short-equal' else (1,1)
    require(prepared['timebase_numerator']==n and prepared['timebase_denominator']==d,'prepared profile differs')
    target=25000100 if name=='callback-queued-delay' else 100
    if name in DEADLINES:
        t,_,_,edge=name.split('-');target+=((16000000 if t=='control' else 2000000000)*d//n)+{'before':-1,'equal':0,'after':1}[edge]
    if name=='iso-abort-late':target=2000000100
    saved=state['saved_epochs'];start=state['quiet_start_ticks']
    mutations=int(name.startswith('profile-') or name in ('after-capture-aba','capture-return-aba'))
    endn=2 if name in ('profile-start-numerator','profile-end-numerator') else n
    endd=2 if name in ('profile-start-denominator','profile-end-denominator') else d
    instance=2 if name in ('profile-start-instance','profile-end-instance') else 1
    lease=state['lease'];owners=[]
    require(lease['iso_attempts']==state['iso_attempts'] and lease['trigger_attempts']==state['trigger_attempts'] and lease['aborts']==state['aborts'],'lease/runtime counters differ')
    require(lease['frame_reads']==state['iso_attempts'] and lease['status_reads']==2*saved+int(saved<state['iso_attempts']),'lease diagnostic read counts differ')
    for i in range(2):
        count=lease['iso_callbacks'][i];require(type(count) is int and 0<=count<=2,'owner callback declaration differs')
        ack=i<saved;timeout=i==0 and state['aborts']==1
        status=4 if ack or count else 0 if i>=state['iso_attempts'] else 5 if name=='iso-reject' else 2 if timeout else 1
        if name=='foreign-pointer' and i==0:status=3
        owners.append(dict(state=status,callbacks=count,retained=not ack,timed_out=timeout))
    expected=dict(schema='A23-injected-driver-fault-facts-1',case=name,start_accepted=name not in ('early-iso','iso-reject','trigger-reject'),initial_ticks=100,target_end_ticks=target,
        initial_numerator=n,initial_denominator=d,end_numerator=endn,end_denominator=endd,end_domain=1,end_instance=instance,mutations=mutations,
        quiet_start_ticks=start,quiet_test_end_ticks=start+(250000000*d+n-1)//n if start else 0,injected_fixture=True,profile_reads_atomic=False,actual_clock_authenticated=False,owners=owners)
    require(encode(facts)==encode(expected),'complete fault diagnostics differ '+name)
    if start:
        saved_events=[e for e in events if e['event']=='epochs_saved'];require(len(saved_events)==1 and start==saved_events[0]['ticks'],'quiet start/journal link differs')
    observation=[e for e in events if e['event']=='observation_complete']
    if observation:
        details=observation[0]['details'];require(len(observation)==1 and details['quiet_start_ticks']==start and details['quiet_end_ticks']==facts['quiet_test_end_ticks'],'quiet endpoint diagnostics differ')
    for i in range(saved):
        prefix='epoch-'+str(i)+'/';bundle(cache,prefix,('raw.bin','transactions.bin','before.bin','after.bin','metadata.json'))
        sdk.payload(cache[prefix+'raw.bin'],cache[prefix+'transactions.bin'],81+i*16);sdk.status(cache[prefix+'before.bin'],None if i==0 else 81);sdk.status(cache[prefix+'after.bin'],81+i*16)
        metadata=parse(cache[prefix+'metadata.json']);require(metadata['binding']['session_id']==state['session_id'] and metadata['epoch']==i,'metadata session differs')
        require(metadata['budget']['timebase_numerator']==n and metadata['budget']['timebase_denominator']==d,'metadata timebase differs')
        require(all(metadata[k]['injected_fixture'] is True for k in ('before_observation','after_observation','sample')),'metadata provenance claim differs')
    bundle(cache,'sdk-receipt/',('receipt.json','snapshot.json'));saved_receipt=parse(cache['sdk-receipt/receipt.json']);snapshot=parse(cache['sdk-receipt/snapshot.json'])
    require(saved_receipt['snapshot_sha256']==sha(cache['sdk-receipt/snapshot.json']) and encode(snapshot)==encode(saved_receipt['snapshot']) and snapshot['session_id']==state['session_id'],'cached receipt link differs')
    stale=name in ('post-receipt-aba','after-receipt-aba','after-receipt-noop')
    require(receipt['attempted'] is True and receipt['saved'] is (not stale) and receipt['stale'] is stale,'receipt invalidation state differs')
    require((encode(snapshot)!=encode(state) and snapshot['complete'] is True and state['complete'] is False and 'observation_version' in state['failure_reasons']) if stale else encode(snapshot)==encode(state),'receipt/current snapshot relation differs')
    if name in NEW:
        trace=trace_expected(name);require(encode(row['concurrency'])==encode(trace) and encode(parse(cache['concurrency.json']))==encode(trace),'concurrency trace differs')
    return dict(passed=True,case=name,version_fields=len(VERSION_KEYS),facts_fields=len(expected),receipt_stale=stale,
        workers=trace_expected(name)['worker_count'] if name in NEW else 0,consumer_filesystem_calls=0,provenance_authenticated=False)
