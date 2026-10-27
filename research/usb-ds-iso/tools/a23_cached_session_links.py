"""Pure entry/driver/receipt/session byte relations; no clock-domain attestation."""
import uuid
import a23_cached_build_relations as build

prior = build.prior
view, ar, a, f = build.view, build.ar, build.a, build.f
HOST = prior.HOST
FALSE = {**build.FALSE, 'production_permit_authenticated': False,
         'owner_driver_clock_domain_relation_verified': False}
EPOCH_EVENTS = ('before_intent','before','iso_intent','iso_return','trigger_intent',
                'trigger_return','control_callback','iso_callback','after_intent','save_intent','saved')


def number(value, low=0, high=2**64-1):
    return type(value) is int and low <= value <= high


def equal(left, right, message):
    f.require(f.encode(left) == f.encode(right), message)


def session_binding(value):
    f.require(type(value) is dict and set(value) == {'session_id','identity','descriptor_sha256',
              'first_sequence','execution_mode'} and value['execution_mode'] == 'sdk_observation' and
              number(value['first_sequence'],81,81), 'SDK binding shape differs')
    session = value['session_id']
    f.require(type(session) is str and str(uuid.UUID(session)).upper() == session.upper(), 'SDK session UUID differs')
    identity, hashes = value['identity'], value['descriptor_sha256']
    f.require(type(identity) is dict and set(identity) == {'device_id','interface_id','parent_device_id'} and
              all(number(v,1) for v in identity.values()) and
              identity['device_id'] == identity['parent_device_id'] != identity['interface_id'], 'SDK identity differs')
    f.require(type(hashes) is dict and set(hashes) == {'device_descriptor','configuration_descriptor','active_interface'} and
              all(f.hex64(v) for v in hashes.values()), 'SDK descriptor digest shape differs')
    return value


def events(raw, sdk):
    f.require(type(raw) is bytes and len(raw) <= 128*4096 and raw.endswith(b'\n'), 'partial/large event journal')
    lines = raw.splitlines()
    f.require(len(lines) == (25 if sdk else 12) and all(0 < len(line) <= 4095 for line in lines), 'event count/size differs')
    rows = [prior.native_metadata(line) for line in lines]
    previous = 1
    for index, row in enumerate(rows,1):
        expected = {'schema','index','ticks','event','details','hardware_verified'}
        if sdk: expected |= {'execution_mode','session_id','hardware_entry_enabled'}
        f.require(set(row) == expected and row['schema'] == ('A23-two-epoch-sdk-event-1' if sdk else 'A23-two-epoch-entry-event-1') and
                  number(row['index'],index,index) and number(row['ticks'],previous) and
                  type(row['event']) is str and type(row['details']) is dict and row['hardware_verified'] is False,
                  'event schema/type/order differs')
        if sdk:
            f.require(row['execution_mode'] == 'sdk_observation' and row['hardware_entry_enabled'] is False,
                      'SDK event authority differs')
        previous = row['ticks']
    return rows


def receipt_links(raw):
    def obj(name): return prior.native_metadata(raw[HOST+name])
    entry, final = obj('entry-current.json'), obj('entry-final/entry.json')
    equal(entry, final, 'entry checkpoint differs')
    f.require(entry.get('schema') == 'A23-two-epoch-entry-result-1', 'entry schema differs')
    for key in ('begun','process_claimed','selection_claimed','prepared','started','complete','waiter_closed','resources_retained'):
        f.require(entry.get(key) is True, 'entry incomplete: '+key)
    for key in ('stopped','journal_failed','active_resources_released','callback_drain_verified',
                'hardware_verified','hardware_entry_enabled','process_origin_authenticated'):
        f.require(entry.get(key) is False, 'entry uncertainty/authority: '+key)
    f.require(entry.get('failure_reasons') == [] and number(entry.get('waiter_failed_releases'),0,0), 'entry failed')
    wanted = dict(schema='A23-two-epoch-entry-final-status-1',attempted=True,saved=True,stale=False,hardware_verified=False)
    equal(obj('entry-final-status.json'), wanted, 'entry final status differs')
    driver = obj('result.json')
    for value in (entry.get('driver'), obj('entry-final/driver.json'), obj('sdk-receipt/snapshot.json')):
        equal(value, driver, 'driver snapshot copy differs')
    f.require(driver.get('schema') == 'A23-two-epoch-sdk-result-1' and driver.get('execution_mode') == 'sdk_observation', 'driver mode differs')
    for key in ('complete','epochs_saved_complete','observation_complete','all_stores_retained','shared_resources_retained'):
        f.require(driver.get(key) is True, 'driver incomplete: '+key)
    for key in ('stopped','journal_failed','hardware_verified','hardware_entry_enabled','device_trace_verified','callback_drain_verified'):
        f.require(driver.get(key) is False, 'driver uncertainty/authority: '+key)
    f.require(driver.get('failure_reasons') == [] and number(driver.get('first_sequence'),81,81) and
              all(number(driver.get(k),v,v) for k,v in {'iso_attempts':2,'trigger_attempts':2,'saved_epochs':2,'aborts':0}.items()), 'driver count/failure differs')
    prior.sdk.sdk_lease(driver.get('lease'))
    status = dict(schema='A23-two-epoch-sdk-receipt-status-1',attempted=True,saved=True,stale=False,hardware_verified=False)
    for value in (entry.get('driver_receipt'), obj('entry-final/receipt-status.json'), obj('receipt-status.json')):
        equal(value,status,'SDK receipt status differs')
    receipt = obj('sdk-receipt/receipt.json')
    f.require(set(receipt) == {'schema','binding','execution_mode','hardware_verified','hardware_entry_enabled',
              'physical_run_authenticated','snapshot','snapshot_sha256'} and receipt['schema'] == 'A23-two-epoch-sdk-receipt-1' and
              receipt['execution_mode'] == 'sdk_observation' and
              all(receipt[k] is False for k in ('hardware_verified','hardware_entry_enabled','physical_run_authenticated')),
              'SDK receipt shape/authority differs')
    equal(receipt['snapshot'],driver,'embedded SDK snapshot differs')
    f.require(receipt['snapshot_sha256'] == f.sha(raw[HOST+'sdk-receipt/snapshot.json']), 'SDK snapshot byte digest differs')
    binding = session_binding(receipt['binding'])
    f.require(binding['session_id'] == driver.get('session_id'), 'receipt/driver session differs')
    return entry, driver, binding


def journal_links(raw, entry, driver, binding):
    native = events(raw[HOST+'session.jsonl'], True)
    erows = events(raw[HOST+'entry.jsonl'], False)
    f.require(all(row['session_id'] == binding['session_id'] for row in native), 'journal session differs')
    by = {}
    for row in native:
        epoch = row['details'].get('epoch')
        if 'epoch' in row['details']: f.require(number(epoch,0,1), 'event epoch type differs')
        key = row['event'],epoch
        f.require(key not in by, 'repeated SDK event')
        by[key] = row
    f.require(set(by) == {(n,e) for n in EPOCH_EVENTS for e in (0,1)} |
              {('prepared',None),('epochs_saved',None),('observation_complete',None)} and
              native[0]['event'] == 'prepared' and native[-1]['event'] == 'observation_complete', 'SDK event inventory differs')
    prepared = native[0]['details']
    equal(session_binding(prepared.get('binding')),binding,'prepared/receipt binding differs')
    f.require(number(prepared.get('max_epochs'),2,2) and number(prepared.get('lead_frames'),32,32) and
              number(prepared.get('timebase_numerator'),1,2**32-1) and number(prepared.get('timebase_denominator'),1,2**32-1),
              'prepared plan declaration differs')
    expected = ['context','process_claim',*(['adapter']*5),'sdk_claim','adapter','prepared','start','final_checkpoint']
    f.require([r['event'] for r in erows] == expected, 'entry event inventory differs')
    entry_by = {r['event']:r for r in erows if r['event'] != 'adapter'}
    equal(entry_by['context']['details'].get('binding'),entry['binding'],'entry journal binding differs')
    context_sha = f.sha(raw[HOST+'context.json'])
    f.require(entry.get('context_sha256') == context_sha == entry_by['context']['details'].get('sha256'), 'entry context byte link differs')
    for event, schema in (('process_claim','A23-two-epoch-entry-process-claim-1'),('sdk_claim','A23-two-epoch-entry-sdk-claim-1')):
        row = prior.native_metadata(raw[HOST+event.replace('_','-')+'.json'])
        f.require(row.get('schema') == schema and row.get('hardware_verified') is False and
                  number(row.get('pid'),1) and number(row.get('ticks'),1) and row.get('context_sha256') == context_sha,
                  'entry claim type/hash differs')
        equal(row.get('binding'),entry['binding'],'claim/build binding differs')
        equal(row,entry_by[event]['details'],'entry claim journal differs')
    claim = entry_by['sdk_claim']['details']
    identity = binding['identity']
    f.require(number(claim.get('device_id'),1) and number(claim.get('interface_id'),1) and
              claim['device_id'] == identity['device_id'] and claim['interface_id'] == identity['interface_id'], 'selected SDK identity differs')
    adapters = [r for r in erows if r['event']=='adapter']
    f.require(number(entry.get('waiter_events'),6,6), 'waiter event count differs')
    for n,row in enumerate(adapters,1):
        d=row['details']
        f.require(all(number(d.get(k),v,v) for k,v in {'event':n,'adapter_index':n,'phase':n,'count':0 if n<4 else 1,'native_result':0,'reason':0}.items()), 'adapter declaration differs')
        if n>=4:
            f.require(number(d.get('device_id'),identity['device_id'],identity['device_id']) and
                      number(d.get('interface_id'),identity['interface_id'],identity['interface_id']), 'adapter identity differs')
    f.require(adapters[-1]['ticks'] <= native[0]['ticks'] <= entry_by['prepared']['ticks'] <=
              entry_by['start']['ticks'] <= native[1]['ticks'] and entry_by['final_checkpoint']['ticks'] >= native[-1]['ticks'],
              'entry/session handoff order differs')
    return by


def epoch_links(raw, driver, binding, by):
    clocks = []
    for epoch in (0,1):
        prefix = HOST+'epoch-%d/'%epoch
        meta = prior.native_metadata(raw[prefix+'metadata.json'])
        equal(meta['binding'],binding,'epoch/session binding differs')
        f.require(by['before',epoch]['details'].get('sha256') == f.sha(raw[prefix+'before.bin']) and
                  by['saved',epoch]['details'].get('metadata_sha256') == f.sha(raw[prefix+'metadata.json']), 'event/epoch byte digest differs')
        equal(by['iso_intent',epoch]['details'].get('sample'),meta.get('sample'),'frame sample link differs')
        equal(by['iso_return',epoch]['details'].get('budget'),meta.get('budget'),'runtime budget link differs')
        f.require(by['iso_return',epoch]['details'].get('accepted') is True and
                  by['trigger_return',epoch]['details'].get('accepted') is True and
                  number(by['trigger_intent',epoch]['details'].get('first_sequence'),81+16*epoch,81+16*epoch), 'request declaration differs')
        control = by['control_callback',epoch]['details'];owner = by['iso_callback',epoch]['details'].get('owner')
        f.require(all(number(control.get(k),v,v) for k,v in {'count':1,'status':0,'bytes':0}.items()) and
                  number(control.get('arrival_ticks'),1) and control['arrival_ticks'] == meta.get('control_arrival_ticks'), 'control callback link differs')
        f.require(type(owner) is dict and number(owner.get('count'),1,1) and number(owner.get('status_u32'),0,0) and
                  owner.get('pointer_mismatch') is False and number(owner.get('arrival_ticks'),1) and
                  number(owner.get('owner_state_before'),1,1), 'ISO callback declaration differs')
        f.require(number(meta.get('iso_arrival_ticks'),1), 'driver ISO arrival type differs')
        clocks.append(dict(epoch=epoch,driver_arrival_ticks=meta['iso_arrival_ticks'],
                           owner_arrival_ticks=owner['arrival_ticks'],journal_ticks=by['iso_callback',epoch]['ticks'],
                           owner_later_than_journal_if_compared=owner['arrival_ticks']>by['iso_callback',epoch]['ticks']))
        order = {n:by[n,epoch]['index'] for n in EPOCH_EVENTS}
        f.require(order['before_intent']<order['before']<order['iso_intent']<order['iso_return']<order['trigger_intent']<order['trigger_return']<
                  min(order['iso_callback'],order['control_callback']) and max(order['iso_callback'],order['control_callback'])<
                  order['after_intent']<order['save_intent']<order['saved'], 'epoch journal order differs')
    f.require(by['saved',0]['index']<by['before_intent',1]['index'], 'second epoch precedes first save')
    quiet = by['observation_complete',None]['details']
    f.require(number(by['epochs_saved',None]['details'].get('saved_epochs'),2,2) and
              number(quiet.get('minimum_ns'),250000000,250000000) and
              all(number(driver.get(k),1) and number(quiet.get(k),1) and driver[k] == quiet[k]
                  for k in ('quiet_start_ticks','quiet_end_ticks')), 'quiet record link differs')
    return clocks


def consume(receiver, supervisor, journal, link_bytes, link_digest):
    base = build.consume(receiver,supervisor,journal,link_bytes,link_digest)
    result = dict(schema='A23-cached-session-links-1',classification='inconsistent_session_subset',
                  errors=[],reasons={},build_subset_consistent=not base['errors'],
                  driver_receipt_links_consistent=False,session_journal_links_consistent=False,
                  entry_to_epoch_session_links_consistent=False,clock_observations=[], **FALSE)
    if base['errors']:
        result['errors']=['build_subset'];result['reasons']['build_subset']=','.join(base['errors']);return result
    raw = prior.verify_scope(*journal)
    def check(name, action):
        try:return action()
        except (ValueError,KeyError,TypeError,UnicodeError,RecursionError,IndexError) as exc:
            result['errors'].append(name);result['reasons'][name]=str(exc);return None
    links = check('driver_receipt',lambda:receipt_links(raw))
    if links is not None:
        result['driver_receipt_links_consistent']=True
        entry,driver,binding=links
        by=check('session_journals',lambda:journal_links(raw,entry,driver,binding))
        if by is not None:
            result['session_journal_links_consistent']=True
            clocks=check('epoch_links',lambda:epoch_links(raw,driver,binding,by))
            if clocks is not None:
                result['entry_to_epoch_session_links_consistent']=True;result['clock_observations']=clocks
    if not result['errors']:result['classification']='consistent_cached_session_link_subset'
    return result
