#!/usr/bin/env python3
"""Independent EP0INI1 CPU startup journal decoder; never authenticates ownership."""
import argparse,json,struct,zlib
from pathlib import Path
STEPS=('fs_initialize','sd_open','log_delete','log_create','video_open','audio_open','usb_initialize',
       'descriptors','interfaces','iso_setup','usb_enable','video_create','video_start','audio_create','audio_start',
       'sm_initialize','setsys_initialize','firmware_get','serial_get','core_initialize','usb_device_initialize',
       'fs_exit','sd_close','video_close','audio_close','fatal')
EVENTS=('call','result','void_return','fatal_result')
def require(value,message):
    if not value:raise ValueError(message)
def decode_startup(data,expected_recipe=None):
    require(len(data)>=96,'short startup journal')
    require(data[:8]==b'EP0INI1\0','startup magic')
    require(struct.unpack_from('<4H',data,8)==(1,96,16,64),'startup layout')
    flags,status,count,reserved=struct.unpack_from('<4I',data,16)
    require(flags==3 and status<=15 and count<=64 and reserved==0,'startup flags/count')
    require(not(status&1 and status&8),'sealed writer in progress')
    require(not status&2 or count==64,'overflow before capacity')
    require(len(data)==96+16*count,'startup size')
    writer=struct.unpack_from('<Q',data,32)[0];recipe=data[40:72].hex()
    require(writer and any(data[40:72]) and not any(data[80:96]),'startup identity/reserved')
    if expected_recipe is not None:require(recipe==expected_recipe,'startup recipe mismatch')
    entries_crc,header_crc=struct.unpack_from('<2I',data,72)
    header=bytearray(data[:96]);header[76:80]=bytes(4)
    require(zlib.crc32(header)==header_crc,'startup header CRC')
    require(zlib.crc32(data[96:])==entries_crc,'startup entries CRC')
    records=[];stack=[];successes=[];failures=[];fatal=None
    for i in range(count):
        step,event,result,ordinal,reserved=struct.unpack_from('<HHIII',data,96+i*16)
        require(1<=step<=26 and 1<=event<=4 and ordinal==i+1 and not reserved,'startup entry fields')
        require(event not in (1,3) or result==0,'result on call/void return')
        require((step==26)==(event==4) and (event!=4 or result),'startup fatal entry')
        require(event!=3 or 22<=step<=25,'void return step')
        require(event!=2 or step<22,'Result on void step')
        require(fatal is None,'record after fatal')
        name=STEPS[step-1]
        if event==1:stack.append(step)
        elif event in (2,3):
            require(stack and stack.pop()==step,'startup return has no matching call')
            if event==2:
                (failures if result else successes).append(dict(step=name,result=result,ordinal=ordinal))
        else:fatal=dict(result=result,ordinal=ordinal)
        records.append(dict(step=name,event=EVENTS[event-1],ordinal=ordinal,result=result if event in (2,4) else None))
    return dict(schema='A23-startup-journal-analysis-1',simulation=True,startup_only=True,
        ownership_export_accepted=False,cleanup_authorized=False,source_authenticated=False,
        thread_liveness_authenticated=False,hardware_verified=False,root_cause_confirmed=False,
        writer=writer,recipe_digest=recipe,recipe_correlated=expected_recipe is not None,
        count=count,capacity=64,journal_sealed=bool(status&1),overflow=bool(status&2),invalid=bool(status&4),
        writer_in_progress=bool(status&8),records=records,successful_api_results=successes,failed_api_results=failures,
        unfinished_calls=[STEPS[n-1] for n in stack],fatal=fatal,
        complete_journal=bool(status&1) and not(status&14) and not stack)
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('journal',type=Path);p.add_argument('--expected-recipe',required=True);a=p.parse_args()
    print(json.dumps(decode_startup(a.journal.read_bytes(),a.expected_recipe),indent=2))
if __name__=='__main__':main()
