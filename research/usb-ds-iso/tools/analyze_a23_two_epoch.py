"""Standalone offline two-epoch archive verification; integrity is not provenance."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import uuid


def require(value,message):
    if not value:raise ValueError(message)


def integer(v,low=0,high=2**64-1):return type(v) is int and low<=v<=high
def sha(raw):return hashlib.sha256(raw).hexdigest()


def unique(pairs):
    out={}
    for k,v in pairs:
        require(k not in out,'duplicate JSON key');out[k]=v
    return out


def read(path,limit=2*1024*1024):
    require(not path.is_symlink() and path.is_file() and path.stat().st_size<=limit,'invalid file: '+str(path))
    return path.read_bytes()


def load(raw):return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _:require(False,'nonfinite JSON'))


def sealed(root):
    require(root.is_dir() and not root.is_symlink(),'invalid epoch directory')
    names={'raw.bin','transactions.bin','before.bin','after.bin','metadata.json'}
    require({p.name for p in root.iterdir()}==names|{'SHA256SUMS','COMMITTED'},'epoch inventory differs')
    files={n:read(root/n) for n in names};sums=''.join(sha(files[n])+'  '+n+'\n' for n in sorted(files)).encode()
    require(read(root/'SHA256SUMS')==sums and read(root/'COMMITTED',65)==(sha(sums)+'\n').encode(),'epoch hash mismatch')
    return files


def status(raw,first=None):
    require(type(raw) is bytes and len(raw)==168,'STATUS size differs');v=struct.unpack_from('<14I',raw)
    require(v[0]==0x31505349 and v[1]==1 and v[11]==0x83,'STATUS header differs')
    if first is None:
        require(all(v[i]==0 for i in (2,3,4,5,6,7,8,9,12,13)) and v[10] in (0,3),'initial STATUS not fresh')
    else:
        require(v[2]==first and v[3]==2 and not v[4] and v[5]==v[6]>0 and v[7]==v[8]==3072 and
            v[9]==3 and v[10]==3 and v[12]==1 and not v[13],'STATUS sequence/URB/transfer mismatch')
        d=struct.unpack_from('<6IQ',raw,56);mfi,valid=struct.unpack_from('<2I',raw,128)
        require(d[0]==0x374f5349 and d[3]==1 and d[4]==65535 and d[5]==3072 and valid==1 and mfi<16384 and
            (d[2]>>10 & 63)==5 and not d[2]>>31 and (d[2]>>20 & 2047)==(((mfi>>3)+32)&2047),'ISO7 mismatch')
    return v


def payload(raw,transactions,first):
    require(len(raw)==184320 and len(transactions)==26880,'snapshot sizes differ');slots=[]
    for i in range(960):
        rc,requested,offset,count,timestamp,options=struct.unpack_from('<iIIIQI',transactions,i*28)
        require(rc==0 and requested==192 and offset==i*192 and not options and count in (0,192),'transaction invalid')
        if count:
            n=len(slots);require(n<16,'too many packets');seq=first+n
            expected=b'ISO1'+struct.pack('<H',seq)+bytes((j^seq^(seq>>8))&255 for j in range(6,192))
            require(raw[offset:offset+192]==expected,'payload sequence/body differs');slots.append(i)
    require(len(slots)==16,'missing packets');return slots


def observation(o,lower):
    expected=dict(request_type=193,request=81,value=0,index=2,length=168,timeout_ms=3000)
    require(type(o) is dict and o.get('source')=='mock_control_reply' and o.get('accepted') is True and 'error' not in o and
        integer(o.get('bytes_transferred'),168,168) and type(o.get('control')) is dict and o['control']==expected and
        all(type(v) is int for v in o['control'].values()) and integer(o.get('begin_ticks'),lower) and
        integer(o.get('end_ticks'),o['begin_ticks']),'STATUS observation differs')
    return o['end_ticks']


def analyze(root):
    root=Path(root);require(root==root.resolve() and root.is_dir(),'canonical run required')
    result=load(read(root/'result.json',16384));require(type(result) is dict,'invalid result')
    require(result.get('schema')=='A23-two-epoch-result-1' and result.get('execution_mode')=='offline_simulation' and
        result.get('complete') is True and result.get('stopped') is False and result.get('journal_failed') is False and
        result.get('failure_reasons')==[],'run not cleanly complete')
    for k,v in dict(iso_attempts=2,trigger_attempts=2,saved_epochs=2,aborts=0).items():require(integer(result.get(k),v,v),'result bound differs')
    for k in ('hardware_verified','hardware_entry_enabled','device_trace_verified','callback_drain_verified'):require(result.get(k) is False,'unsupported claim')
    require(result.get('all_stores_retained') is True and result.get('shared_resources_retained') is True,'resource lifetime claim missing')
    first=result.get('first_sequence');require(integer(first,81,65504) and first%16==1,'model range invalid')
    session=result.get('session_id');require(type(session) is str and str(uuid.UUID(session)).upper()==session.upper(),'session ID invalid')
    journal=read(root/'session.jsonl',128*4096);require(journal.endswith(b'\n'),'partial journal')
    lines=journal.splitlines();require(len(lines)==24 and all(len(line)<=4095 for line in lines),'event count/size differs')
    rows=[load(line) for line in lines];previous=1;by={}
    for i,row in enumerate(rows,1):
        require(type(row) is dict and row.get('schema')=='A23-two-epoch-event-1' and row.get('execution_mode')=='offline_simulation' and
            row.get('session_id')==session and integer(row.get('index'),i,i) and integer(row.get('ticks'),previous) and
            row.get('hardware_verified') is False and row.get('hardware_entry_enabled') is False and type(row.get('details')) is dict,'journal record invalid')
        previous=row['ticks'];epoch=row['details'].get('epoch')
        require(integer(epoch,0,1) if 'epoch' in row['details'] else row.get('event') in ('prepared','complete'),'event epoch invalid')
        key=(row.get('event'),epoch)
        require(key not in by,'repeated event');by[key]=row
    require(rows[0]['event']=='prepared' and rows[-1]['event']=='complete','journal endpoints differ')
    prepared=rows[0]['details'];binding=prepared.get('binding');require(type(binding) is dict and binding.get('session_id')==session and
        binding.get('execution_mode')=='offline_simulation' and integer(binding.get('first_sequence'),first,first),'prepared binding differs')
    identity=binding.get('identity');hashes=binding.get('descriptor_sha256')
    require(type(identity) is dict and set(identity)=={'device_id','interface_id','parent_device_id'} and
        all(integer(v,1) for v in identity.values()) and identity['device_id']==identity['parent_device_id']!=identity['interface_id'],'identity differs')
    require(type(hashes) is dict and set(hashes)=={'device_descriptor','configuration_descriptor','active_interface'} and
        all(type(v) is str and len(v)==64 and set(v)<=set('0123456789abcdef') for v in hashes.values()),'descriptor hashes differ')
    n,d=prepared.get('timebase_numerator'),prepared.get('timebase_denominator')
    require(integer(n,1,2**32-1) and integer(d,1,2**32-1) and integer(prepared.get('max_epochs'),2,2) and integer(prepared.get('lead_frames'),32,32),'plan/timebase differs')
    def ns(ticks):require(integer(ticks),'negative time delta');return (ticks*n+d-1)//d
    events=('before_intent','before','iso_intent','iso_return','trigger_intent','trigger_return','control_callback','iso_callback','after_intent','save_intent','saved')
    require(set(by)=={('prepared',None),('complete',None)}|{(name,e) for name in events for e in (0,1)},'event inventory differs')
    out=[];old=None;old_id=None
    for epoch in (0,1):
        order={name:by[name,epoch]['index'] for name in events}
        require(order['before_intent']<order['before']<order['iso_intent']<order['iso_return']<order['trigger_intent']<order['trigger_return'] and
            order['trigger_return']<min(order['iso_callback'],order['control_callback']) and max(order['iso_callback'],order['control_callback'])<order['after_intent']<order['save_intent']<order['saved'],'event order differs')
        if epoch:require(by['saved',0]['index']<order['before_intent'],'second epoch preceded first save')
        files=sealed(root/('epoch-'+str(epoch)));m=load(files['metadata.json'])
        require(type(m) is dict and m.get('schema')=='A23-two-epoch-bundle-1' and m.get('binding')==binding and
            integer(m.get('epoch'),epoch,epoch) and integer(m.get('first_sequence'),first+epoch*16,first+epoch*16) and
            m.get('execution_mode')=='offline_simulation' and m.get('hardware_verified') is False and m.get('hardware_entry_enabled') is False and
            m.get('device_trace_verified') is False and integer(m.get('overall_u32'),0,0) and integer(m.get('callback_count'),1,1) and integer(m.get('control_count'),1,1),'epoch metadata differs')
        require(by['before',epoch]['details'].get('sha256')==sha(files['before.bin']) and by['saved',epoch]['details'].get('metadata_sha256')==sha(files['metadata.json']),'journal file binding differs')
        if not epoch:status(files['before.bin'])
        else:require(files['before.bin']==old,'second before differs from first after')
        state=status(files['after.bin'],first+epoch*16);require(state[5]!=old_id,'URB ID reused');old_id=state[5];old=files['after.bin']
        sample=m.get('sample');b=m.get('budget');require(type(sample) is dict and sample==by['iso_intent',epoch]['details'].get('sample') and
            sample.get('source')=='mock_frame_number' and integer(sample.get('current_frame'),1,2**64-33) and integer(m.get('first_frame'),sample['current_frame']+32,sample['current_frame']+32),'frame differs')
        before_end=observation(m.get('before_observation'),by['before_intent',epoch]['ticks'])
        require(integer(sample.get('begin_ticks'),before_end) and integer(sample.get('end_ticks'),sample['begin_ticks']) and type(b) is dict and
            b==by['iso_return',epoch]['details'].get('budget') and b.get('source')=='mock_runtime_budget' and b.get('admitted') is True and b.get('budget_pass') is True and
            b.get('accepted') is True and b.get('forwarded') is True and b.get('converted') is True and b.get('duration_valid') is True and
            integer(b.get('timebase_numerator'),n,n) and integer(b.get('timebase_denominator'),d,d) and integer(b.get('check_ticks'),sample['end_ticks']) and integer(b.get('return_ticks'),b['check_ticks']),'budget invalid')
        require(integer(b.get('query_ns'),ns(sample['end_ticks']-sample['begin_ticks']),ns(sample['end_ticks']-sample['begin_ticks'])) and integer(b.get('age_ns'),ns(b['check_ticks']-sample['begin_ticks']),ns(b['check_ticks']-sample['begin_ticks'])) and integer(b.get('call_ns'),ns(b['return_ticks']-b['check_ticks']),ns(b['return_ticks']-b['check_ticks'])) and ns(sample['end_ticks']-sample['begin_ticks'])<=2000000 and ns(b['check_ticks']-sample['begin_ticks'])<=16000000 and ns(b['return_ticks']-b['check_ticks'])<=8000000,'budget exceeded')
        submit,trigger,iso,control=(m.get(k) for k in ('submit_ticks','trigger_ticks','iso_arrival_ticks','control_arrival_ticks'))
        require(integer(submit,1,b['check_ticks']) and integer(trigger,b['return_ticks']) and integer(iso,trigger) and integer(control,trigger) and
            ns(iso-submit)<=2000000000 and ns(control-trigger)<=16000000 and ns(trigger-b['return_ticks'])<=8000000 and ns(trigger-sample['begin_ticks'])<=32000000,'callback/trigger deadline exceeded')
        observation(m.get('after_observation'),max(iso,control))
        trigger_row=by['trigger_return',epoch]['details'];callback=by['control_callback',epoch]['details'];iso_row=by['iso_callback',epoch]['details'].get('owner')
        require(trigger_row.get('accepted') is True and by['iso_return',epoch]['details'].get('accepted') is True and
            integer(callback.get('count'),1,1) and integer(callback.get('status'),0,0) and integer(callback.get('bytes'),0,0) and callback.get('arrival_ticks')==control and
            type(iso_row) is dict and integer(iso_row.get('count'),1,1) and integer(iso_row.get('status_u32'),0,0) and iso_row.get('pointer_mismatch') is False,'callback journal differs')
        out.append(dict(epoch=epoch,first_sequence=first+epoch*16,urb_id=state[5],effective_slots=payload(files['raw.bin'],files['transactions.bin'],first+epoch*16),bytes=3072))
    return dict(schema='A23-two-epoch-analysis-1',offline_chain_complete=True,epochs=out,total_bytes=6144,
        hardware_verified=False,hardware_entry_enabled=False,device_trace_verified=False,physical_run_authenticated=False,
        callback_drain_verified=False,continuous_streaming_verified=False,sequences_allocated=False)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path)
    print(json.dumps(analyze(p.parse_args().directory),indent=2))
