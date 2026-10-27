#!/usr/bin/env python3
"""Decode the bounded EP0 trace prototype; simulation never authenticates capture."""
# Independent V2 decoder: fixed 256-record/32-identity wire contract.
# V1 decoders remain separate and reject these envelopes.
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zlib

STAGES={1:'event_ready',2:'event_clear',3:'setup_read',4:'iso_enter',5:'speed',6:'sequence',
        7:'iso_post',8:'ctrl_clear_pre',9:'ctrl_post',10:'ctrl_wait',11:'ctrl_clear_done',
        12:'ctrl_report',13:'ctrl_parse',14:'ack',15:'status_snapshot',16:'guard',17:'device_state'}


def require(condition,message):
    if not condition:raise ValueError(message)


def decode(data):
    require(len(data)>=128,'truncated trace header')
    require(data[:8]==b'EP0TRC2\0','trace magic mismatch')
    require(struct.unpack_from('<4H',data,8)==(2,128,48,256),'trace layout/version mismatch')
    flags,count,dropped,invalid,reason,reserved=struct.unpack_from('<6I',data,16)
    require(flags==1,'trace must retain simulation provenance')
    require(count<=256 and len(data)==128+count*48,'trace length/count mismatch')
    require(reason in (1,2) and reserved==0,'invalid freeze/reserved fields')
    polls=struct.unpack_from('<4H',data,104);poll_results=struct.unpack_from('<4I',data,112)
    require(all(n or not rc for n,rc in zip(polls,poll_results)),'poll result without a poll')
    frequency,start,frozen=struct.unpack_from('<3Q',data,40)
    require(frequency>0 and frozen>=start,'invalid trace clock')
    boot,session=data[64:80],data[80:96]
    require(any(boot) and any(session),'missing trace identity')
    payload_crc,header_crc=struct.unpack_from('<2I',data,96)
    require(zlib.crc32(data[128:])==payload_crc,'trace payload CRC mismatch')
    header=bytearray(data[:128]);header[100:104]=bytes(4)
    require(zlib.crc32(header)==header_crc,'trace header CRC mismatch')
    records=[];last=start;groups={};requests=[]
    for i in range(count):
        begin,end,ordinal,rid,result,a0,a1,stage,interface,rflags,setup=struct.unpack_from('<QQ5IHBB8s',data,128+i*48)
        require(ordinal==i+1,'noncontiguous trace ordinal')
        require(start<=begin<=end<=frozen and end>=last,'invalid trace record ticks');last=end
        require(stage in STAGES and rflags&~15==0,'invalid trace stage/flags')
        require((interface==255 and rid==0) if stage==17 else (interface<4 and rid>0),'invalid trace owner')
        require((rflags&2 or a0==0) and (rflags&4 or a1==0),'unmarked trace argument')
        require(rflags&1 or setup==bytes(8),'unmarked trace setup')
        require(not rflags&1 or stage in (3,4,16),'setup on unrelated trace stage')
        require(not rflags&8 or 8<=stage<=14,'direction on unrelated trace stage')
        if stage==3:require((result==0)==bool(rflags&1),'setup validity disagrees with result')
        if stage==5:require((result==0)==bool(rflags&2),'speed validity disagrees with result')
        if stage in (7,9):require(rflags&2 and ((result==0)==bool(rflags&4)),'post argument validity disagrees with result')
        if stage==13:require((result==0)==bool(rflags&2),'parse validity disagrees with result')
        row=dict(ordinal=ordinal,request_id=rid,stage=STAGES[stage],interface=interface,result_u32=result,
                 begin_ticks=begin,end_ticks=end,duration_ticks=end-begin,
                 duration_ms=(end-begin)*1000/frequency,arg0=a0 if rflags&2 else None,
                 arg1=a1 if rflags&4 else None,direction='in' if rflags&8 else ('out' if 8<=stage<=13 else None),
                 setup_hex=setup.hex() if rflags&1 else None)
        records.append(row)
        if stage==17:continue
        if stage==1:
            require(rid not in groups and result==0,'invalid/reused ready request ID')
            groups[rid]=dict(request_id=rid,interface=interface,records=[]);requests.append(groups[rid])
        require(rid in groups and groups[rid]['interface']==interface,'trace request has no matching event')
        group=groups[rid];previous=[r['stage'] for r in group['records']]
        if stage==2:require(previous==['event_ready'],'unexpected event clear')
        if stage==3:require(previous==['event_ready','event_clear'],'unexpected setup read')
        if stage>=4:require('setup_read' in previous,'stage precedes setup read')
        group['records'].append(row)
    complete_requests=True
    for interface in range(4):
        ready_count=sum(g['interface']==interface for g in requests)
        require(polls[interface]==65535 or ready_count<=polls[interface],'ready events exceed poll count')
    for group in requests:
        rows=group['records'];names=[r['stage'] for r in rows]
        complete_requests&='setup_read' in names
        helpers=[];helper=None
        next_stage={'ctrl_clear_pre':'ctrl_post','ctrl_post':'ctrl_wait',
                    'ctrl_wait':'ctrl_clear_done','ctrl_clear_done':'ctrl_report','ctrl_report':'ctrl_parse'}
        for row in rows:
            name=row['stage']
            if name=='ctrl_clear_pre':
                require(helper is None or helper['expected'] is None,'overlapping control helper')
                helper=dict(expected=name,direction=row['direction'],result=None);helpers.append(helper)
            if name in ('ctrl_clear_pre','ctrl_post','ctrl_wait','ctrl_clear_done','ctrl_report','ctrl_parse'):
                require(helper is not None and name==helper['expected'],'control stages out of order')
                require(row['direction']==helper['direction'],'control direction changed within helper')
                done=name=='ctrl_parse' or (name in ('ctrl_post','ctrl_wait','ctrl_report') and row['result_u32']!=0)
                helper['expected']=None if done else next_stage[name]
                if done:helper['result']=row['result_u32']
            if name=='ack':
                require(helper is not None and helper['expected'] is None and helper['direction']=='in',
                        'ACK without finished IN helper')
                require(row['result_u32']==helper['result'],'ACK result disagrees with IN helper')
        if helper is not None and helper['expected'] is not None:complete_requests=False
        setup_rows=[r for r in rows if r['stage']=='setup_read']
        group['setup_hex']=setup_rows[0]['setup_hex'] if setup_rows else None
        group['path']='setup_unfinished'
        if setup_rows:
            s=setup_rows[0]
            if s['result_u32']:group['path']='setup_read_failed'
            elif 'iso_enter' not in names:group['path']='other_interface'
            elif 'status_snapshot' in names:group['path']='iso_status'
            elif 'guard' in names:group['path']='iso_guard'
            elif 'iso_post' in names:
                post=next(r for r in rows if r['stage']=='iso_post')
                ack=next((r for r in rows if r['stage']=='ack'),None)
                group['path']=('iso_post_failed' if post['result_u32'] else
                               'iso_post_then_ack_failed' if ack and ack['result_u32'] else
                               'iso_post_and_ack_returned' if ack else 'iso_post_ack_unfinished')
            else:group['path']='iso_other'
            if group['interface']==2 and not s['result_u32'] and 'iso_enter' not in names:
                complete_requests=False
            if group['path']=='iso_post_ack_unfinished':complete_requests=False
            if group['path']=='iso_other' and bytes.fromhex(group['setup_hex'])[:2]==b'\x41\x54':
                complete_requests=False
            if group['path']=='iso_status':
                # A successful STATUS IN stage must be followed by its OUT
                # status stage; a failed helper is a complete failure path.
                if not helpers or helpers[0]['direction']!='in':complete_requests=False
                elif helpers[0]['result']==0:
                    if len(helpers)!=2 or helpers[1]['direction']!='out' or helpers[1]['expected'] is not None:
                        complete_requests=False
        # Preserve all record results; the path label does not accept a USB burst.
    first={}
    for group in requests:
        if group['setup_hex'] is not None:first.setdefault(group['interface'],group['setup_hex'])
    mixed=all(i in first for i in (0,1,2)) and first[0]==first[1] and first[2]!=first[0]
    return dict(schema='EP0-bounded-trace-analysis-2',simulation=True,hardware_verified=False,
                root_cause_confirmed=False,trace_format_valid=True,
                trace_window_complete=not dropped and not invalid and reason==1 and complete_requests,
                dropped_records=dropped,invalid_records=invalid,freeze_reason='finished' if reason==1 else 'stopped',
                record_count=count,capacity=256,tick_frequency=frequency,boot_id_hex=boot.hex(),
                poll_snapshots=[dict(interface=i,poll_count=polls[i],count_saturated=polls[i]==65535,
                                     last_result_u32=poll_results[i]) for i in range(4)],
                quiet_poll_timing_and_result_history_retained=False,
                session_id_hex=session.hex(),start_tick=start,freeze_tick=frozen,
                mixed_first_interface_setup=mixed,mixed_setup_proves_bus_overwrite=False,
                records=records,requests=requests,sha256=hashlib.sha256(data).hexdigest(),
                identity_and_crc_authenticate_origin=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('trace',type=Path)
    args=parser.parse_args()
    try:result=decode(args.trace.read_bytes())
    except (OSError,ValueError) as error:
        parser.exit(1,str(error)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
