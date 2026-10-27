"""Typed, separate clock domains and model-only timing arithmetic over caches."""
import a23_cached_permit_context as permit

prior=permit.prior
view,ar,a,f=permit.view,permit.ar,permit.a,permit.f
HOST=permit.HOST
FALSE={**permit.FALSE,'runtime_clock_provenance_verified':False,'native_owner_timebase_verified':False}
DRIVER='injected_driver'
OWNER='native_owner'
SUPERVISOR='supervisor_ns'
SOURCE_HASHES={
    'research/usb-ds-iso/tests/a23_broker_model_fixture.m':'420c15394a8f39f3dda780df28f356d2a5fd6c24b7f36ddc7770e9803141c80a',
    'research/usb-ds-iso/host/io_usb_host_transaction_owner.m':'01851a51a8dab35b5c2c35f80fd68abb4503b9ac702252bbfb3e181b5fb5a70c',
    'research/usb-ds-iso/host/a23_two_epoch_sdk_driver.m':'4f7f46345f1dbadf12b02bcf8c2322caacde33a63addd219976c9b942bfe8797'}
DOMAINS={DRIVER:dict(kind='step100_fixture',numerator=1,denominator=1),
         OWNER:dict(kind='mach_absolute_time',numerator=None,denominator=None),
         SUPERVISOR:dict(kind='declared_monotonic_ns',numerator=1,denominator=1)}


def duration_ns(begin,end,begin_domain,end_domain,domains):
    f.require(type(begin_domain) is str and begin_domain==end_domain and begin_domain in domains,
              'cross-domain subtraction is unavailable')
    domain=domains[begin_domain];n,d=domain['numerator'],domain['denominator']
    f.require(permit.session.number(begin) and permit.session.number(end,begin) and
              permit.session.number(n,1,2**32-1) and permit.session.number(d,1,2**32-1),
              'invalid ticks or unknown timebase')
    value=((end-begin)*n+d-1)//d
    f.require(value<=2**64-1,'nanosecond conversion overflow')
    return value


def minimum_elapsed(begin,end,domain,domains,minimum_ns):
    # A rounded-up duration can overstate a fractional minimum interval.
    duration_ns(begin,end,domain,domain,domains)
    f.require(permit.session.number(minimum_ns),'invalid minimum interval')
    clock=domains[domain]
    return (end-begin)*clock['numerator'] >= minimum_ns*clock['denominator']


def profile(receiver,journal):
    return dict(schema='A23-cached-clock-profile-1',profile='frozen_broker_step100_fixture',
                receiver_manifest_sha256=receiver[4],journal_manifest_sha256=journal[3],
                source_hashes=dict(SOURCE_HASHES),domains={k:dict(v) for k,v in DOMAINS.items()},
                cross_domain_mappings=[],**FALSE)


def verify_profile(value,receiver,journal):
    expected=profile(receiver,journal)
    f.require(f.encode(value)==f.encode(expected),'clock profile/domain/source/authority differs')
    cache,_=permit.session.build.grouped.consume(*receiver)
    for name,digest in SOURCE_HASHES.items():
        f.require(permit.session.build.digest_file(cache,'source/'+name)==digest,'frozen clock implementation differs')
    return value['domains']


def driver_timing(raw,domains):
    rows=permit.session.events(raw[HOST+'session.jsonl'],True)
    by={(r['event'],r['details'].get('epoch')):r for r in rows}
    prepared=rows[0]['details']
    f.require(permit.session.number(prepared.get('timebase_numerator'),1,1) and
              permit.session.number(prepared.get('timebase_denominator'),1,1),'fixture timebase differs')
    def ns(begin,end):return duration_ns(begin,end,DRIVER,DRIVER,domains)
    result=[]
    for e in (0,1):
        m=prior.native_metadata(raw[HOST+'epoch-%d/metadata.json'%e]);s=m['sample'];b=m['budget']
        tick=lambda event:by[event,e]['ticks']
        for key in ('submit_ticks','trigger_ticks','iso_arrival_ticks','control_arrival_ticks','first_frame'):
            f.require(permit.session.number(m.get(key),1),'driver timestamp type differs: '+key)
        for key in ('begin_ticks','end_ticks','current_frame','frame_time'):
            f.require(permit.session.number(s.get(key),1),'frame field type differs: '+key)
        f.require(s.get('source')=='sdk_frame_number' and s.get('injected_fixture') is True and
                  s['current_frame']<=2**64-33 and m['first_frame']==s['current_frame']+32,'fixture frame declaration differs')
        before=m['before_observation'];after=m['after_observation']
        prior.sdk.observation(before,tick('before_intent'))
        prior.sdk.observation(after,max(m['iso_arrival_ticks'],m['control_arrival_ticks']))
        f.require(before.get('injected_fixture') is True and after.get('injected_fixture') is True,'fixture clock origin label differs')
        for key in ('check_ticks','return_ticks','query_ns','age_ns','call_ns'):
            f.require(permit.session.number(b.get(key)),'budget integer type differs: '+key)
        f.require(b.get('source')=='sdk_runtime_budget' and
                  all(b.get(k) is True for k in ('admitted','accepted','forwarded','converted','duration_valid','budget_pass')) and
                  permit.session.number(b.get('timebase_numerator'),1,1) and permit.session.number(b.get('timebase_denominator'),1,1),
                  'budget clock/acceptance declaration differs')
        query=ns(s['begin_ticks'],s['end_ticks']);age=ns(s['begin_ticks'],b['check_ticks']);call=ns(b['check_ticks'],b['return_ticks'])
        f.require((query,age,call)==(b['query_ns'],b['age_ns'],b['call_ns']),'budget arithmetic differs')
        f.require(query<=2000000 and age<=16000000 and call<=8000000,'frame/enqueue budget exceeded')
        submit,trigger,iso,control=(m[k] for k in ('submit_ticks','trigger_ticks','iso_arrival_ticks','control_arrival_ticks'))
        gap=ns(b['return_ticks'],trigger);trigger_age=ns(s['begin_ticks'],trigger)
        f.require(gap<=8000000 and trigger_age<=32000000,'trigger budget exceeded')
        detail=by['trigger_return',e]['details']
        f.require(permit.session.number(detail.get('gap_ns')) and permit.session.number(detail.get('age_ns')) and
                  detail['gap_ns']==gap and detail['age_ns']==trigger_age,'trigger arithmetic differs')
        iso_ns=ns(submit,iso);control_ns=ns(trigger,control)
        f.require(iso_ns<=2000000000 and control_ns<=16000000,'callback deadline exceeded')
        f.require(tick('before_intent')<=before['begin_ticks']<=before['end_ticks']<=tick('before')<=s['begin_ticks']<=s['end_ticks']<=
                  tick('iso_intent')<=submit<=b['check_ticks']<=b['return_ticks']<=tick('iso_return')<=tick('trigger_intent')<=trigger<=tick('trigger_return'),
                  'driver arm/trigger causal order differs')
        f.require(trigger<=iso<=tick('iso_callback') and trigger<=control<=tick('control_callback') and
                  max(tick('iso_callback'),tick('control_callback'))<=tick('after_intent')<=after['begin_ticks']<=after['end_ticks']<=
                  tick('save_intent')<=tick('saved'),'driver callback/save causal order differs')
        if e:f.require(by['saved',0]['ticks']<=before['begin_ticks'],'second before precedes first save')
        owner=by['iso_callback',e]['details']['owner']['arrival_ticks']
        result.append(dict(epoch=e,query_ns=query,frame_age_ns=age,enqueue_call_ns=call,trigger_gap_ns=gap,
                           trigger_age_ns=trigger_age,iso_arrival_ns=iso_ns,control_arrival_ns=control_ns,
                           iso_journal_delay_ns=ns(iso,tick('iso_callback')),
                           control_journal_delay_ns=ns(control,tick('control_callback')),
                           owner_arrival_ticks=owner,owner_domain=OWNER,owner_duration_ns=None))
    return result,by


def quiet_timing(raw,domains,by):
    last=by['observation_complete',None];q=last['details'];saved=by['epochs_saved',None]
    driver=prior.native_metadata(raw[HOST+'result.json'])
    f.require(saved['index']==24 and last['index']==25 and
              saved['ticks']<=q['quiet_start_ticks']<=q['quiet_end_ticks']<=last['ticks'],'quiet causal order differs')
    value=duration_ns(q['quiet_start_ticks'],q['quiet_end_ticks'],DRIVER,DRIVER,domains)
    f.require(minimum_elapsed(q['quiet_start_ticks'],q['quiet_end_ticks'],DRIVER,domains,250000000),
              'model quiet interval too short')
    f.require(permit.session.number(q.get('minimum_ns'),250000000,250000000) and
              driver['quiet_start_ticks']==q['quiet_start_ticks'] and driver['quiet_end_ticks']==q['quiet_end_ticks'],'quiet snapshot differs')
    return value


def consume(receiver,supervisor,journal,link_bytes,link_digest,profile_bytes,profile_digest):
    f.require(type(profile_bytes) is bytes and len(profile_bytes)<=16384 and f.hex64(profile_digest) and
              f.sha(profile_bytes)==profile_digest,'external clock profile pin differs')
    value=permit.session.build.json_object(profile_bytes)
    base=permit.consume(receiver,supervisor,journal,link_bytes,link_digest)
    result=dict(schema='A23-cached-clock-domains-1',classification='inconsistent_model_clock_subset',errors=[],reasons={},
                permit_context_subset_consistent=not base['errors'],clock_profile_consistent=False,
                model_driver_timing_arithmetic_consistent=False,model_quiet_interval_arithmetic_consistent=False,
                epochs=[],model_quiet_interval_ns=None,excluded_domains=[OWNER,SUPERVISOR],**FALSE)
    if base['errors']:
        result['errors']=['prior_subset'];result['reasons']['prior_subset']=','.join(base['errors']);return result
    raw=prior.verify_scope(*journal)
    def check(name,action):
        try:return action()
        except (ValueError,KeyError,TypeError,UnicodeError,RecursionError,IndexError) as exc:
            result['errors'].append(name);result['reasons'][name]=str(exc);return None
    domains=check('clock_profile',lambda:verify_profile(value,receiver,journal))
    if domains is not None:
        result['clock_profile_consistent']=True
        timed=check('driver_timing',lambda:driver_timing(raw,domains))
        if timed is not None:
            result['model_driver_timing_arithmetic_consistent']=True;result['epochs'],by=timed
            quiet=check('quiet_timing',lambda:quiet_timing(raw,domains,by))
            if quiet is not None:
                result['model_quiet_interval_arithmetic_consistent']=True;result['model_quiet_interval_ns']=quiet
    if not result['errors']:result['classification']='consistent_injected_driver_clock_arithmetic_subset'
    return result
