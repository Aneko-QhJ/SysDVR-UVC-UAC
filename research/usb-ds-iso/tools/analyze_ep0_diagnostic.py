#!/usr/bin/env python3
"""Independent simulation-only diagnostic decoder; never accepts safe ownership."""
import argparse
import json
from pathlib import Path
import struct
import zlib
from analyze_ep0_trace import decode,require

def decode_diagnostic(data,expected_recipe=None):
    require(len(data)>=128,'short diagnostic')
    require(data[:8]==b'EP0DIA1\0','diagnostic magic')
    require(struct.unpack_from('<4H',data,8)==(1,128,16,16),'diagnostic layout')
    flags,count,fault,pending=struct.unpack_from('<4I',data,16)
    require(flags==3 and count<=16 and fault<=1 and pending<=count,'diagnostic flags/count')
    writer,exporter=struct.unpack_from('<2Q',data,32)
    require(writer and exporter and writer!=exporter,'diagnostic identities')
    recipe=data[48:80].hex();require(any(data[48:80]),'missing diagnostic recipe')
    if expected_recipe is not None:require(recipe==expected_recipe,'diagnostic recipe mismatch')
    length,ledger_crc,trace_crc,header_crc,unmatched,denials,reason,video,audio,phase=struct.unpack_from('<10I',data,80)
    require(video==audio==0 and phase==3 and not any(data[120:128]),'diagnostic join/phase/reserved')
    require(reason<=6 and ((denials==0)==(reason==0)),'diagnostic denial metadata')
    require(not denials or fault,'diagnostic denial without permanent fault')
    offset=128+count*16;require(len(data)==offset+length,'diagnostic length')
    header=bytearray(data[:128]);header[92:96]=bytes(4)
    require(zlib.crc32(header)==header_crc,'diagnostic header CRC')
    require(zlib.crc32(data[128:offset])==ledger_crc,'diagnostic ledger CRC')
    require(zlib.crc32(data[offset:])==trace_crc,'diagnostic trace CRC')
    entries=[];seen=set()
    for i in range(count):
        channel,active,reserved,urb,status,tail=struct.unpack_from('<BBHIII',data,128+i*16)
        require(channel<9 and active<=1 and reserved==tail==0,'diagnostic ledger entry')
        require(bool(active)!=(status in (3,4,5)),'diagnostic terminal/active disagreement')
        require((channel,urb) not in seen,'duplicate diagnostic identity');seen.add((channel,urb))
        entries.append(dict(channel=channel,id=urb,status=status,active=bool(active)))
    require(sum(r['active'] for r in entries)==pending,'diagnostic pending mismatch')
    trace=decode(data[offset:]);require(trace['freeze_reason']=='stopped','diagnostic stopped boundary')
    require(fault or pending or denials or trace['dropped_records'] or trace['invalid_records'],'clean snapshot is not a diagnostic')
    accepted=set();reused=0;failed_posts=0
    for r in trace['records']:
        if r['stage'] not in ('iso_post','ctrl_post'):continue
        if r['result_u32']:
            failed_posts+=1;continue
        channel=8 if r['stage']=='iso_post' else r['interface']*2+(0 if r['direction']=='in' else 1)
        identity=(channel,r['arg1']);reused+=identity in accepted;accepted.add(identity)
    require(not (reused or failed_posts) or fault,'post failure/reuse without permanent fault')
    require(accepted<=seen,'diagnostic observed post missing from ledger')
    if not trace['dropped_records'] and not trace['invalid_records']:require(accepted==seen,'diagnostic unrecorded post')
    return dict(schema='A23-EP0-diagnostic-analysis-1',simulation=True,diagnostic_only=True,
        ownership_export_accepted=False,cleanup_authorized=False,hardware_verified=False,root_cause_confirmed=False,
        source_authenticated=False,join_results_authenticated=False,recipe_digest=recipe,
        recipe_correlated=expected_recipe is not None,writer=writer,exporter=exporter,fault=bool(fault),pending=pending,
        guard_denials=denials,guard_reason=reason,unmatched_reports=unmatched,urbs=entries,trace=trace,
        observed_failed_posts=failed_posts,reused_observed_post_identities=reused)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('diagnostic',type=Path)
    p.add_argument('--expected-recipe',required=True);args=p.parse_args()
    print(json.dumps(decode_diagnostic(args.diagnostic.read_bytes(),args.expected_recipe),indent=2))
if __name__=='__main__':main()
