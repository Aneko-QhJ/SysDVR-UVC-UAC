"""Decode an LCP1 prototype prefix. CRC/ordering are not physical provenance."""
import argparse
import json
from pathlib import Path
import re
import struct
import zlib

HEADER=128; RECORD=96; CAPACITY=40; MAX=HEADER+RECORD*CAPACITY
STAGES=dict(enumerate(('prepared','usb_init_call','usb_init_result','quiet_enter','main_loop_left',
 'cleanup_result','video_join_call','video_join_result','audio_join_call','audio_join_result',
 'exporter_result','owner_finish_result','primary_save_call','primary_save_result',
 'execution_build_result','execution_save_call','execution_save_result','sd_open_call',
 'sd_open_result','file_create_call','file_create_result','joined_context','retain','main_return'),1))

def require(ok,why):
    if not ok:raise ValueError(why)


def decode(raw,expected_recipe):
    require(type(expected_recipe) is str and re.fullmatch('[0-9a-f]{64}',expected_recipe),'expected recipe shape')
    require(HEADER<=len(raw)<=MAX,'capsule length')
    h=raw[:HEADER]
    require(h[:8]==b'EP0LCP1\0' and struct.unpack_from('<4H',h,8)==(1,HEADER,RECORD,CAPACITY),'capsule header')
    writer,frequency,start=struct.unpack_from('<3Q',h,16)
    require(writer and frequency and any(h[40:56]) and any(h[56:88]) and not any(h[88:124]),'capsule header fields')
    require(h[56:88].hex()==expected_recipe,'capsule recipe mismatch')
    require(zlib.crc32(h[:124])==struct.unpack_from('<I',h,124)[0],'capsule header CRC')
    notes=[];deferred=False;joins=0;join_calls=0;join_seen=0;closed=False;last_tick=start
    tail='capacity_end' if len(raw)==MAX else 'short_file';error=None
    for slot in range(CAPACITY):
        off=HEADER+slot*RECORD;record=raw[off:off+RECORD]
        if not record:break
        if not any(record):
            tail='zero_tail' if not any(raw[off:]) else 'gap_before_nonzero_tail'
            break
        if len(record)!=RECORD:tail='partial_record';break
        seq=struct.unpack_from('<I',record,4)[0];stage,flags=struct.unpack_from('<2H',record,8)
        tick=struct.unpack_from('<Q',record,12)[0];result,arg0,arg1=struct.unpack_from('<3I',record,20)
        try:
            require(record[:4]==b'LCPE' and seq==slot+1 and stage in STAGES and flags in (0,1),'record identity')
            require(zlib.crc32(record[:92])==struct.unpack_from('<I',record,92)[0] and not any(record[64:92]),'record CRC/reserved')
            require(not closed and tick>=last_tick,'record after close/backwards clock')
            require(slot or stage==1,'missing prepared record')
            require(not deferred or stage==5,'record emitted during deferred window')
            require(stage!=5 or deferred,'main loop exit without deferred window')
            require(stage!=7 or not join_calls&1,'repeated video join')
            require(stage!=9 or not join_calls&2,'repeated audio join')
            require(stage!=8 or notes and notes[-1]['stage_id']==7,'video join result without call')
            require(stage!=10 or notes and notes[-1]['stage_id']==9,'audio join result without call')
            require(stage!=8 or not join_seen&1,'repeated video join result')
            require(stage!=10 or not join_seen&2,'repeated audio join result')
            require(not (12<=stage<=22) or joins==3,'post-join note before both successful results')
            require(flags==(1 if stage==22 else 0),'unexpected context flag')
            require((any(record[32:48]) and any(record[48:64])) if flags else not any(record[32:64]),'context fields')
        except ValueError as e:tail='invalid_record';error=str(e);break
        notes.append(dict(sequence=seq,stage_id=stage,stage=STAGES[stage],tick=tick,result=result,arg0=arg0,arg1=arg1,
                          boot_id_hex=record[32:48].hex() if flags else None,session_id_hex=record[48:64].hex() if flags else None))
        if stage==4:deferred=True
        if stage==5:deferred=False
        if stage==7:join_calls|=1
        if stage==9:join_calls|=2
        if stage==8:join_seen|=1
        if stage==10:join_seen|=2
        if stage==8 and result==0:joins|=1
        if stage==10 and result==0:joins|=2
        if stage in (23,24):closed=True
        last_tick=tick
    return dict(schema='A23-lifecycle-capsule-prefix-1',prototype=True,recipe_digest=expected_recipe,main_nonce_hex=h[40:56].hex(),
        writer=writer,frequency=frequency,start_tick=start,records=notes,valid_prefix_records=len(notes),tail=tail,error=error,
        supplied_join_success_mask=joins,reported_closed=closed,header_content_valid=True,
        own_commit_authenticated=False,last_stage_is_latest_execution_proof=False,
        physical_run_authenticated=False,join_results_authenticated=False,cleanup_authorized=False,hardware_verified=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('capsule',type=Path)
    parser.add_argument('--expected-recipe',required=True);args=parser.parse_args()
    print(json.dumps(decode(args.capsule.read_bytes(),args.expected_recipe),indent=2))
