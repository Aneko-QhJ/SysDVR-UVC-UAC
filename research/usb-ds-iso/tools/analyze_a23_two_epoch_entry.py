"""Verify supplied SDK entry, context, wait/claim order and final checkpoint."""
import argparse,json
from pathlib import Path
from analyze_a23_two_epoch_sdk import analyze as sdk_analyze,read,load,require,sha,integer
from a23_execution_context import validate as context_validate

def typed(v):return json.dumps(v,sort_keys=True,separators=(',',':'))
def checkpoint(root):
    require(root.is_dir() and not root.is_symlink() and {p.name for p in root.iterdir()}=={'entry.json','driver.json','receipt-status.json','SHA256SUMS','COMMITTED'},'entry checkpoint inventory differs')
    files={n:read(root/n,65536) for n in ('entry.json','driver.json','receipt-status.json')}
    sums=''.join(sha(files[n])+'  '+n+'\n' for n in sorted(files)).encode()
    require(read(root/'SHA256SUMS')==sums and read(root/'COMMITTED',65)==(sha(sums)+'\n').encode(),'entry checkpoint integrity differs');return {n:load(raw) for n,raw in files.items()}

def analyze(root):
    root=Path(root);require(root==root.resolve() and root.is_dir(),'canonical run required')
    result=load(read(root/'entry-current.json',65536));final=load(read(root/'entry-final-status.json',16384));saved=checkpoint(root/'entry-final')
    require(type(result) is dict and result.get('schema')=='A23-two-epoch-entry-result-1' and typed(result)==typed(saved['entry.json']),'entry final checkpoint not current')
    for k in ('begun','process_claimed','selection_claimed','prepared','started','complete','waiter_closed','resources_retained'):require(result.get(k) is True,'entry gate missing: '+k)
    for k in ('stopped','journal_failed','active_resources_released','callback_drain_verified','hardware_verified','hardware_entry_enabled','process_origin_authenticated'):require(result.get(k) is False,'entry uncertainty/claim: '+k)
    require(result.get('failure_reasons')==[] and integer(result.get('waiter_failed_releases'),0,0),'entry failed')
    require(type(final) is dict and final.get('schema')=='A23-two-epoch-entry-final-status-1' and final.get('attempted') is True and final.get('saved') is True and final.get('stale') is False and final.get('hardware_verified') is False,'entry final status differs')
    b=result.get('binding');require(type(b) is dict and set(b)=={'schema','build_manifest_sha256','receiver_sha256','authorization_receipt_sha256','first_sequence','last_sequence'} and b.get('schema')=='A23-two-epoch-entry-binding-1','entry binding differs')
    for k in ('build_manifest_sha256','receiver_sha256','authorization_receipt_sha256'):require(type(b.get(k)) is str and len(b[k])==64 and set(b[k])<=set('0123456789abcdef'),'entry digest malformed')
    require(integer(b.get('first_sequence'),81,65504) and b['first_sequence']%16==1 and integer(b.get('last_sequence'),b['first_sequence']+31,b['first_sequence']+31),'entry range differs')
    context_raw=read(root/'context.json',16384);context=load(context_raw);context_validate(context,b['receiver_sha256']);require(sha(context_raw)==result.get('context_sha256'),'entry context binding differs')
    process=load(read(root/'process-claim.json',16384));claim=load(read(root/'sdk-claim.json',16384))
    for row,schema in ((process,'A23-two-epoch-entry-process-claim-1'),(claim,'A23-two-epoch-entry-sdk-claim-1')):
        require(type(row) is dict and row.get('schema')==schema and typed(row.get('binding'))==typed(b) and row.get('context_sha256')==sha(context_raw) and integer(row.get('pid'),context['pid'],context['pid']) and integer(row.get('ticks'),context['sample_end_ticks']) and row.get('hardware_verified') is False,'entry claim differs')
    require(claim['ticks']>=process['ticks'] and integer(claim.get('device_id'),1) and integer(claim.get('interface_id'),1) and claim['interface_id']!=claim['device_id'],'entry identity/clock differs')
    raw=read(root/'entry.jsonl',128*4096);require(raw.endswith(b'\n'),'entry partial journal');rows=[load(r) for r in raw.splitlines()];require(8<=len(rows)<=128,'entry events count differs')
    last=1;by={};adapter=[]
    for n,row in enumerate(rows,1):
        require(type(row) is dict and row.get('schema')=='A23-two-epoch-entry-event-1' and integer(row.get('index'),n,n) and integer(row.get('ticks'),last) and type(row.get('details')) is dict and row.get('hardware_verified') is False,'entry journal invalid');last=row['ticks']
        if row.get('event')=='adapter':adapter.append(row)
        else:require(row.get('event') not in by,'repeated entry event');by[row['event']]=row
    require(set(by)=={'context','process_claim','sdk_claim','prepared','start','final_checkpoint'} and rows[0]['event']=='context' and rows[-1]['event']=='final_checkpoint','entry event inventory differs')
    require(integer(process['ticks'],context['sample_end_ticks'],by['process_claim']['ticks']) and integer(claim['ticks'],process['ticks'],by['sdk_claim']['ticks']),'claim time exceeds journal')
    require(by['context']['details'].get('sha256')==sha(context_raw) and typed(by['context']['details'].get('binding'))==typed(b) and typed(by['process_claim']['details'])==typed(process) and typed(by['sdk_claim']['details'])==typed(claim),'entry journal claim binding differs')
    require([r['details'].get('event') for r in adapter]==[1,2,3,4,5,6] and integer(result.get('waiter_events'),6,6),'passive wait order differs')
    previous=process['ticks']
    for n,row in enumerate(adapter,1):
        d=row['details'];require(integer(d.get('adapter_index'),n,n) and integer(d.get('ticks'),previous,row['ticks']) and integer(d.get('native_result'),0,0) and integer(d.get('reason'),0,0),'adapter event differs');previous=d['ticks']
        if n<=3:require(integer(d.get('count'),0,0),'device existed before WAITING')
        if n>=4:require(d.get('interface_id')==claim['interface_id'] and d.get('device_id')==claim['device_id'] and integer(d.get('count'),1,1),'adapter selected identity differs')
    require(by['process_claim']['index']<adapter[0]['index']<adapter[2]['index']<adapter[3]['index']<adapter[4]['index']<by['sdk_claim']['index']<adapter[5]['index']<by['prepared']['index']<by['start']['index']<by['final_checkpoint']['index'],'entry claim/wait/start order differs')
    require(typed(result.get('driver'))==typed(saved['driver.json'])==typed(load(read(root/'result.json',16384))) and typed(result.get('driver_receipt'))==typed(saved['receipt-status.json'])==typed(load(read(root/'receipt-status.json',16384))),'entry driver snapshot differs')
    sdk=sdk_analyze(root);require(result['driver']['first_sequence']==b['first_sequence'],'SDK range differs')
    native=[load(line) for line in read(root/'session.jsonl').splitlines()];prepared=native[0]['details'];identity=prepared['binding']['identity']
    require(identity['device_id']==claim['device_id'] and identity['interface_id']==claim['interface_id'] and adapter[-1]['ticks']<=native[0]['ticks']<=by['prepared']['ticks']<=by['start']['ticks']<=native[1]['ticks'] and by['final_checkpoint']['ticks']>=native[-1]['ticks'],'entry/native handoff differs')
    return dict(schema='A23-two-epoch-entry-analysis-1',supplied_entry_chain_complete=True,sdk=sdk,
        supplied_context_consistent=True,claims_and_wait_order_consistent=True,production_permit_authenticated=False,
        process_origin_authenticated=False,physical_run_authenticated=False,hardware_verified=False,hardware_entry_enabled=False,
        callback_drain_verified=False,formal_issuance_available=False,sequences_allocated=False)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);print(json.dumps(analyze(p.parse_args().directory),indent=2))
