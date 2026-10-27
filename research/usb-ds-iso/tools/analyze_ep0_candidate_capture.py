#!/usr/bin/env python3
"""Decode a simulation-only ownership snapshot + inner EP0 trace envelope."""
import argparse
import json
from pathlib import Path
import struct
import zlib
from analyze_ep0_trace import decode,require


def decode_capture(data,expected_recipe=None):
    require(len(data)>=112,'short candidate capture')
    require(data[:8]==b'EP0OWN1\0','bad candidate magic')
    require(struct.unpack_from('<4H',data,8)==(1,112,16,16),'bad candidate layout')
    flags,count,fault,pending=struct.unpack_from('<4I',data,16)
    require(flags==1 and count<=16 and fault==0 and pending==0,'unsafe/relabelled ownership snapshot')
    writer,exporter=struct.unpack_from('<2Q',data,32)
    require(writer and exporter and writer!=exporter,'bad handoff identities')
    recipe=data[48:80].hex();require(any(data[48:80]),'missing recipe digest')
    if expected_recipe is not None:require(recipe==expected_recipe,'recipe digest mismatch')
    length,ledger_crc,trace_crc,header_crc,unmatched=struct.unpack_from('<5I',data,80)
    require(not any(data[100:112]),'reserved header bytes')
    offset=112+count*16;require(len(data)==offset+length,'capture length mismatch')
    header=bytearray(data[:112]);header[92:96]=bytes(4)
    require(zlib.crc32(header)==header_crc,'capture header CRC')
    require(zlib.crc32(data[112:offset])==ledger_crc,'ledger CRC')
    require(zlib.crc32(data[offset:])==trace_crc,'inner trace CRC')
    entries=[];seen=set()
    for i in range(count):
        p=data[112+i*16:128+i*16];channel,active,reserved,urb,status,tail=struct.unpack('<BBHIII',p)
        require(channel<9 and active==0 and reserved==0 and tail==0,'invalid ledger entry')
        require(status in (3,4,5),'nonterminal exported ledger')
        require((channel,urb) not in seen,'duplicate ledger identity');seen.add((channel,urb))
        entries.append(dict(channel=channel,id=urb,status=status))
    trace=decode(data[offset:])
    require(trace['freeze_reason']=='stopped','candidate must use explicit stopped boundary')
    accepted=set()
    for r in trace['records']:
        if r['stage'] not in ('iso_post','ctrl_post'):continue
        require(r['result_u32']==0,'failed post in safe capture')
        channel=8 if r['stage']=='iso_post' else r['interface']*2+(0 if r['direction']=='in' else 1)
        identity=(channel,r['arg1']);require(identity not in accepted,'reused observed post identity')
        accepted.add(identity)
    require(accepted<=seen,'observed post missing from ledger')
    if not trace['dropped_records'] and not trace['invalid_records']:
        require(accepted==seen,'unrecorded post in lossless capture')
    return dict(schema='A23-EP0-candidate-capture-analysis-1',recipe_digest=recipe,
                recipe_correlated=expected_recipe is not None,writer=writer,exporter=exporter,
                urbs=entries,unmatched_reports=unmatched,trace=trace,
                simulation=True,hardware_verified=False,root_cause_confirmed=False,
                source_authenticated=False,runtime_ownership_authenticated=False)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('capture',type=Path)
    p.add_argument('--expected-recipe',required=True);args=p.parse_args()
    print(json.dumps(decode_capture(args.capture.read_bytes(),args.expected_recipe),indent=2))


if __name__=='__main__':main()
