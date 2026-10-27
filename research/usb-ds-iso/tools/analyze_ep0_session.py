#!/usr/bin/env python3
"""Decode startup/EP0 local correlation; no ownership or origin authentication."""
import argparse,json,struct,zlib
from pathlib import Path
from analyze_ep0_startup import decode_startup,require
from analyze_ep0_diagnostic import decode_diagnostic

def decode_session(data,expected_recipe=None):
    require(len(data)>=192,'short session envelope')
    require(data[:8]==b'EP0REL1\0','session magic')
    require(struct.unpack_from('<4H',data,8)==(1,192,1120,6656),'session layout')
    flags,mode,reason,ini,dia,video,audio,status,identity=struct.unpack_from('<9I',data,16)
    require(flags&3==3 and flags<=255 and mode<=3 and reason<=3 and status<=3,'session flags/mode')
    has_ini=bool(flags&4);has_dia=bool(flags&8);bound=bool(flags&16);requested=bool(flags&32);has_sink=bool(flags&64);has_admission=bool(flags&128)
    require(has_ini==bool(ini) and has_dia==bool(dia) and ini<=1120 and dia<=6656,'session component sizes')
    require(mode==(2 if ini and dia else 3 if dia else 1 if ini else 0),'session mode mismatch')
    require(len(data)==192+ini+dia,'session size')
    require(not any(data[84:88]),'session reserved')
    receipt_crc=struct.unpack_from('<I',data,188)[0]
    starter,writer=struct.unpack_from('<2Q',data,96);boot=data[112:128];session=data[128:144];recipe=data[144:176].hex()
    require(any(data[144:176]),'missing session recipe')
    if expected_recipe is not None:require(recipe==expected_recipe,'session recipe mismatch')
    ini_crc,dia_crc,head_crc=struct.unpack_from('<3I',data,176)
    head=bytearray(data[:192]);head[184:188]=bytes(4)
    require(zlib.crc32(head)==head_crc,'session header CRC')
    require(zlib.crc32(data[192:192+ini])==ini_crc,'session startup CRC')
    require(zlib.crc32(data[192+ini:])==dia_crc,'session diagnostic CRC')
    require(status==2 and identity==0 if ini else status!=2,'session startup status')
    require(status not in (0,1) or identity==0,'uncompleted identity Result')
    if not requested:require(reason==video==audio==0 and not dia,'unsolicited EP0 fields')
    elif video or audio:require(reason==1 and not dia,'failed join contains EP0')
    elif not bound:require(reason==2 and not dia,'unbound EP0 request')
    elif not dia:require(reason==3,'missing diagnostic reason')
    else:require(reason==0,'diagnostic fallback reason')
    if bound:
        require(writer and any(boot) and any(session),'empty session binding')
        if not ini:require(starter==0 and status==3,'missing startup identity')
    else:require(writer==0 and not any(boot) and not any(session),'nonce without context')
    startup=decode_startup(data[192:192+ini],recipe) if ini else None
    if startup:require(startup['writer']==starter,'startup writer mismatch')
    elif not bound:require(starter==0,'starter without snapshot')
    diagnostic=decode_diagnostic(data[192+ini:],recipe) if dia else None
    if diagnostic:
        require(requested and bound and video==audio==0,'diagnostic requires joined context')
        require(diagnostic['writer']==writer,'EP0 writer mismatch')
        if starter:require(diagnostic['exporter']==starter,'exporter differs from startup writer')
        require(diagnostic['trace']['boot_id_hex']==boot.hex() and diagnostic['trace']['session_id_hex']==session.hex(),'session nonce mismatch')
    admission_values=struct.unpack_from('<5I',data,52)
    require(not has_admission or diagnostic is not None,'admission without diagnostic')
    admission=None
    if has_admission:
        admitted,refusals,skips,violations,largest=admission_values
        require(largest<=128 and (largest<=17 or violations),'admission bound disagreement')
        require(not(refusals or violations) or diagnostic['fault'],'admission failure without fault')
        admission=dict(admitted=admitted,trace_refusals=refusals,stop_skips=skips,bound_violations=violations,largest_request=largest)
    else:require(not any(admission_values),'unmarked admission')
    phase,result,sink_flags=struct.unpack_from('<3I',data,72);verified=struct.unpack_from('<Q',data,88)[0]
    sink=None
    if has_sink:
        require(receipt_crc==dia_crc,'receipt diagnostic binding')
        require(diagnostic is not None and phase<=9 and sink_flags<=15 and verified<=dia,'sink fields')
        attempted,may_exist,content,commit=(bool(sink_flags&bit) for bit in (1,2,4,8))
        require(attempted or not(phase or result or sink_flags or verified),'unattempted sink fields')
        require(not may_exist or attempted,'file existence without attempt')
        require(not content or attempted and may_exist and verified==dia and phase>=8,'verified sink fields')
        require(not commit or content and phase==9 and result==0,'commit fields')
        require(phase!=9 or commit,'acknowledged phase without commit')
        sink=dict(target='embedded EP0DIA1',save_returned_claim=True,input_crc_matched=True,phase=phase,result=result,
                  attempted=attempted,file_may_exist=may_exist,content_verified=content,commit_acknowledged=commit,verified_bytes=verified)
    else:require(phase==result==sink_flags==verified==receipt_crc==0,'unmarked sink')
    return dict(schema='A23-session-correlation-analysis-1',simulation=True,diagnostic_only=True,
        ownership_export_accepted=False,cleanup_authorized=False,source_authenticated=False,join_results_authenticated=False,
        save_return_authenticated=False,hardware_verified=False,root_cause_confirmed=False,
        mode=('metadata_only','startup_only','startup_and_ep0','ep0_only')[mode],fallback_reason=reason,
        context_present=bound,startup_ep0_locally_correlated=bool(startup and diagnostic),
        recipe_digest=recipe,recipe_correlated=expected_recipe is not None,video_join=video,audio_join=audio,
        startup_status=status,startup_identity_result=identity,starter=starter,ep0_writer=writer,
        boot_id_hex=boot.hex() if bound else None,session_id_hex=session.hex() if bound else None,
        startup=startup,diagnostic=diagnostic,admission=admission,sink=sink,
        envelope_own_save_result_recorded=False,session_nonce_authenticated=False)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('envelope',type=Path);p.add_argument('--expected-recipe',required=True);a=p.parse_args()
    print(json.dumps(decode_session(a.envelope.read_bytes(),a.expected_recipe),indent=2))
if __name__=='__main__':main()
