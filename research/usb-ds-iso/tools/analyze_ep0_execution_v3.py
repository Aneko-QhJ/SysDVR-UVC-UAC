#!/usr/bin/env python3
"""Decode an independent EXE3 envelope; local correlation is not provenance."""
import argparse
import json
from pathlib import Path
import struct
import zlib
from analyze_ep0_candidate_capture_v2 import decode_capture
from analyze_ep0_diagnostic_v2 import decode_diagnostic
from analyze_ep0_startup import decode_startup, require


def decode_execution(data, expected_recipe=None):
    require(256 <= len(data) <= 14432, 'execution envelope length')
    require(data[:8] == b'EP0EXE3\0' and struct.unpack_from('<4H',data,8) ==
            (3,256,1120,13056), 'execution envelope magic/layout')
    flags,kind,ini,n,phase,result,sink_flags,saved = struct.unpack_from('<8I',data,16)
    require(flags in (27,31) and kind in (1,2) and ini<=1120 and
            n<=(13040 if kind==1 else 13056) and len(data)==256+ini+n, 'execution fields')
    verified,freq,start,ready,stop=struct.unpack_from('<5Q',data,48)
    ms,reason=struct.unpack_from('<2I',data,88)
    writer,exporter=struct.unpack_from('<2Q',data,96)
    boot,session,recipe=data[112:128].hex(),data[128:144].hex(),data[144:176].hex()
    require(freq and start<=stop and ms<=60000 and reason in (1,2), 'execution clock/window')
    require(start<=ready<=stop if flags&4 else ready==0, 'execution ready clock')
    require(any(data[112:128]) and any(data[128:144]) and any(data[144:176]) and
            writer and exporter and writer!=exporter, 'execution identities')
    if expected_recipe is not None:require(recipe==expected_recipe,'execution recipe mismatch')
    require(reason!=1 or ms and stop-start>=(freq*ms+999)//1000,'early/disabled expiry')
    ini_crc,primary_crc,head_crc=struct.unpack_from('<3I',data,176)
    require(not any(data[188:192]) and not any(data[208:256]),'execution reserved')
    head=bytearray(data[:256]);head[184:188]=bytes(4)
    require(zlib.crc32(head)==head_crc and zlib.crc32(data[256:256+ini])==ini_crc and
            zlib.crc32(data[256+ini:])==primary_crc, 'execution CRC')
    status,identity,starter=struct.unpack_from('<2IQ',data,192)
    startup=decode_startup(data[256:256+ini],recipe) if ini else None
    require(status==2 and identity==0 and startup['writer']==starter if startup else
            status==3 and starter==0, 'execution startup binding')
    primary=(decode_capture if kind==1 else decode_diagnostic)(data[256+ini:],recipe)
    trace=primary['trace']
    require(primary['writer']==writer and primary['exporter']==exporter and
            (not starter or starter==exporter) and trace['boot_id_hex']==boot and
            trace['session_id_hex']==session, 'execution inner identity mismatch')
    require(trace['tick_frequency']==freq and trace['start_tick']<=start<=stop==trace['freeze_tick'],
            'execution inner clock mismatch')
    require(phase<=9 and sink_flags<=15 and saved in (0,1) and verified<=n,'execution receipt')
    attempted,may_exist,content,commit=(bool(sink_flags&b) for b in (1,2,4,8))
    require(attempted or not(phase or result or sink_flags or verified),'unattempted receipt fields')
    require(not may_exist or attempted,'receipt file without attempt')
    require(not content or attempted and may_exist and verified==n and phase>=8,'receipt verification')
    require(not commit or content and phase==9 and result==0,'receipt commit')
    require(phase!=9 or commit,'acknowledged receipt without commit')
    require(bool(saved)==commit,'save return contradicts receipt')
    return dict(schema='A23-execution-envelope-analysis-3',simulation=True,diagnostic_only=True,
        source_authenticated=False,join_results_authenticated=False,hardware_verified=False,
        root_cause_confirmed=False,usb_strict_pass=False,cleanup_authorized=False,
        envelope_own_commit_authenticated=False,primary_save_return_authenticated=False,
        recipe_digest=recipe,recipe_correlated=expected_recipe is not None,
        primary_kind='ownership' if kind==1 else 'diagnostic',writer=writer,exporter=exporter,
        boot_id_hex=boot,session_id_hex=session,startup=startup,primary=primary,
        window=dict(frequency=freq,start_tick=start,ready_tick=ready if flags&4 else None,
                    stop_tick=stop,window_ms=ms,stop_reason='expired' if reason==1 else 'requested',
                    elapsed_ticks=stop-start,interrupts_synchronous_calls=False),
        primary_receipt=dict(phase=phase,result=result,attempted=attempted,file_may_exist=may_exist,
            content_verified=content,commit_acknowledged=commit,verified_bytes=verified,
            save_returned=True,save_return_value=bool(saved)),primary_payload_crc32=primary_crc)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('envelope',type=Path)
    p.add_argument('--expected-recipe',required=True);args=p.parse_args()
    print(json.dumps(decode_execution(args.envelope.read_bytes(),args.expected_recipe),indent=2))


if __name__=='__main__':main()
