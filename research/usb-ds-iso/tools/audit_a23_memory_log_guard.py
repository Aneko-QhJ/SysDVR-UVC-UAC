#!/usr/bin/env python3
"""SDK leaf-helper evidence and isolated GetSize guard; no hardware or production edits."""
import argparse
import hashlib
import json
import re
import shutil
import struct
from pathlib import Path
import audit_a23_format_loop as prior
import analyze_a23_sdk_memory as memory
import audit_a23_log_contract as logs
from workflows.artifacts import verify

ROOT,REPO,ELFS,base=prior.ROOT,prior.REPO,prior.ELFS,prior.base
SEALED=ELFS.parent/'A23-format-loop-review-20261015'
INPUTS=('tools/analyze_a23_sdk_memory.py','tools/audit_a23_memory_log_guard.py','tests/a23_log_size_guard_fixture.c','tests/test_a23_memory_log_guard.py')
COPY_LENGTHS=(0,1,2,3,4,7,8,15,16,17,31,32,33,63,64,65,95,96,97,127,128,129,191,192,229,255,307,511,512)
COPY_ALIGNMENTS=((0,0),(0,1),(1,0),(15,15),(7,9),(15,0),(0,15))
SET_LENGTHS=(0,1,2,3,4,7,8,15,16,17,31,32,63,64,65,95,96)
STRING_LENGTHS=(0,1,7,8,15,16,17,31,32,33,63,64,65)
STRING_OFFSETS=(0,1,7,15,16,31,32,63,64,127,0xfd0,0xfdf,0xfe0,0xfe1,0xfef,0xff0,0xffe,0xfff)
SIZE_FAILURES=('size-error','size-poison','size-negative','size-huge')
FAULTS=('unmounted','format-error','open-error',*SIZE_FAILURES,'write-error','partial-write')


def logger_source(guard=False):
    source=logs.logger_source(True)
    old='        fsFileGetSize(&file, &offset);\n        fsFileWrite(&file, offset, buf, len, FsWriteOption_Flush);'
    new='        if (R_SUCCEEDED(fsFileGetSize(&file, &offset))) {\n            fsFileWrite(&file, offset, buf, len, FsWriteOption_Flush);\n        }'
    assert source.count(old)==1
    return source.replace(old,new) if guard else source


def native_source(catalog,guard):
    fixture=(ROOT/'tests/a23_log_size_guard_fixture.c').read_text()
    cases=[]
    for row in catalog:
        arguments=[c['sample_expression'] for c in row['conversions']]
        cases.append('    case '+str(row['case'])+': LogFunctionImpl('+json.dumps(row['format'])+(' ,'+','.join(arguments) if arguments else '')+'); break;')
    return fixture.replace('/* INSERT_LOGGER */',logger_source(guard)).replace('/* INSERT_CATALOG */','\n'.join(cases))


def native_audit(output,catalog,commands):
    data={}
    for guarded in (False,True):
        label='guarded' if guarded else 'baseline';source=output/(label+'-native.c');binary=output/(label+'-native')
        source.write_text(native_source(catalog,guarded));commands.append(base.trace.compile_native(source,binary,[]))
        rows=[]
        scenarios=[('catalog',r['case']) for r in catalog]+[('length',n) for n in (0,1,511,512,513,1024)]+[(s,n) for s in FAULTS for n in (7,513)]
        for scenario,value in scenarios:
            row=json.loads(base.owner.command([str(binary),scenario,str(value)]));row.update(scenario=scenario,value=value)
            assert row['requested']<=511 and row['usb_calls']==row['sd_calls']==0
            if scenario in SIZE_FAILURES:
                assert row['opens']==row['sizes']==row['closes']==1 and row['writes']==int(not guarded)
                if guarded:assert row['existing_file_unchanged'] and row['file_size']==99
                elif scenario in ('size-error','size-poison'):assert not row['existing_file_unchanged']
            rows.append(row)
        data[label]=rows
    before={(r['scenario'],r['value']):r for r in data['baseline']};after={(r['scenario'],r['value']):r for r in data['guarded']}
    assert before.keys()==after.keys()
    for key in before:
        if key[0] not in SIZE_FAILURES:assert before[key]==after[key],key
    return dict(rows=data,total_checks=sum(len(v) for v in data.values()),
        unchanged_non_size_failure_cases=sum(key[0] not in SIZE_FAILURES for key in before),
        size_failure_cases_per_variant=sum(key[0] in SIZE_FAILURES for key in before),
        native_vsnprintf_and_exact_logger_body=True,fs_is_memory_model=True,
        guarded_size_errors_never_write=True,guarded_size_errors_close_once=True,
        partial_write_has_no_rollback=True,actual_filesystem_or_sd_accessed=False)


def helper_profiles(blob,text,catalog):
    fs,meta,_,literals=prior.prior.build_inputs(blob,text,catalog);address=next(iter(literals.values()));rows=[];certificates={}
    for name in ('memcpy','memset','strlen'):
        f=next(f for f in fs.values() if f['name']==name)
        frame=memory.fmt.scan.parser.arg.elf.frame_range(f,fs)
        assert frame['frame_bytes']==0 and not frame['edges'] and not frame['unresolved']
        certificates[name]=dict(function_sha256=memory.fmt.scan.parser.arg.elf.function_digest(f),frame=frame)
    for length in COPY_LENGTHS:
        for src,dst in COPY_ALIGNMENTS:
            rows.append(memory.MemoryMachine(fs,blob,meta,address,'memcpy',length,source_offset=src,destination_offset=dst).run_helper())
    for length in SET_LENGTHS:
        for offset in (0,1,7,15):
            for byte in (0,0x5a,0x1ff):
                row=memory.MemoryMachine(fs,blob,meta,address,'memset',length,destination_offset=offset,byte=byte).run_helper();row['input_byte']=byte;rows.append(row)
    for length in STRING_LENGTHS:
        for offset in STRING_OFFSETS:
            rows.append(memory.MemoryMachine(fs,blob,meta,address,'strlen',length,source_offset=offset).run_helper())
    return dict(certificates=certificates,profiles=rows,profile_count=len(rows),
        counts={name:sum(r['helper']==name for r in rows) for name in certificates},
        strlen_max_read_before=max(r['logical_string_read_before'] for r in rows),
        strlen_max_read_after_nul=max(r['logical_string_read_after_nul'] for r in rows),
        strlen_padding_and_pages_mapped_assumed=True,memset_large_zeroing_architecture_unresolved=True,
        full_formatter_models_replaced=False,whole_thread_stack_verified=False)


def object_certificate(blob,text,guarded):
    elf=memory.fmt.scan.parser.arg.elf;meta=elf.elf_metadata(blob)
    symbol=next(s for s in meta['symbols'] if s['name']=='LogFunctionImpl' and s['type']==2)
    section=meta['sections'][symbol['section']];assert section['name']=='.text.LogFunctionImpl'
    code={};words={};calls={}
    for line in text.splitlines():
        match=re.match(r'^\s*([0-9a-f]+):\s+([0-9a-f]{8})\s+(\S+)\s*(.*)$',line)
        if match:
            pc,word=int(match[1],16),int(match[2],16);offset=section['offset']+pc
            assert int.from_bytes(blob[offset:offset+4],'little')==word
            words[pc]=word
            code[pc]=(match[3],match[4].split('//',1)[0].strip())
        relocation=re.match(r'^\s*([0-9a-f]+):\s+R_AARCH64_CALL26\s+(\S+)',line)
        if relocation:calls[relocation[2]]=int(relocation[1],16)
    assert set(calls)=={'vsnprintf','fsFsOpenFile','fsFileGetSize','fsFileWrite','fsFileClose'}
    relocations=next(s for s in meta['sections'] if s['name']=='.rela.text.LogFunctionImpl')
    assert relocations['type']==4 and relocations['entry_size']==24
    bound_calls={}
    for offset in range(relocations['offset'],relocations['offset']+relocations['size'],24):
        pc,info,addend=struct.unpack_from('<QQq',blob,offset)
        if info & 0xffffffff==283: # R_AARCH64_CALL26
            assert addend==0 and words[pc] & 0xfc000000==0x94000000
            bound_calls[meta['symbols'][info>>32]['name']]=pc
    assert bound_calls==calls
    size,write,close=calls['fsFileGetSize'],calls['fsFileWrite'],calls['fsFileClose']
    assert code[0]==('sub','sp, sp, #0x340')
    def target(pc,arg,bits,shift):
        raw=(words[pc]>>shift)&((1<<bits)-1)
        if raw & (1<<(bits-1)):raw-=1<<bits
        actual=pc+4*raw
        assert actual==memory.fmt.scan.parser.fmt.target(arg)
        return actual
    opened=calls['fsFsOpenFile'];op,arg=code[opened+4]
    assert op=='cbnz' and arg.startswith('w0, ') and words[opened+4] & 0xff00001f==0x35000000
    exit_pc=target(opened+4,arg,19,5)
    assert code[exit_pc]==('ldp','x29, x30, [sp]') and code[exit_pc+4]==('add','sp, sp, #0x340') and code[exit_pc+8][0]=='ret'
    assert [(pc,op,arg) for pc,(op,arg) in code.items() if arg.startswith('sp,')]==[(0,'sub','sp, sp, #0x340'),(exit_pc+4,'add','sp, sp, #0x340')]
    def path(status):
        pc=size+4;value=status;events=[];visited=[]
        while True:
            assert pc in code and pc not in visited
            visited.append(pc);op,arg=code[pc];next_pc=pc+4
            name=next((n for n,p in calls.items() if p==pc),None)
            if name:
                assert name in ('fsFileWrite','fsFileClose');events.append(name);value=None
            elif op=='ret':break
            elif op=='b':
                assert words[pc] & 0xfc000000==0x14000000
                next_pc=target(pc,arg,26,0)
            elif op in ('cbz','cbnz'):
                assert arg.startswith('w0, ') and value is not None
                assert words[pc] & 0xff00001f==(0x34000000 if op=='cbz' else 0x35000000)
                destination=target(pc,arg,19,5)
                if (value==0)==(op=='cbz'):next_pc=destination
            elif op.startswith('b.') or op in ('br','blr','tbz','tbnz'):raise AssertionError('Unmodeled object guard branch')
            elif arg.startswith(('w0,','x0,')):
                # After the Result guard x0 is reused as the file pointer or
                # clamp immediate; a later Result test must not reuse it.
                value=None
            pc=next_pc
        return dict(result=status,calls=events,visited=visited)
    paths=[path(value) for value in (0,72,0xffffffff)]
    assert paths[0]['calls']==['fsFileWrite','fsFileClose']
    assert all(p['calls']==(['fsFileClose'] if guarded else ['fsFileWrite','fsFileClose']) for p in paths[1:])
    return dict(object_sha256=meta['elf_sha256'],function_section_sha256=hashlib.sha256(blob[section['offset']:section['offset']+section['size']]).hexdigest(),
        function_bytes=symbol['size'],logger_frame_bytes=832,calls=calls,result_paths=paths,size_failure_skips_write=guarded,
        close_once_after_successful_open=True,relocatable_object_only=True,full_elf_linked=False,arm_executed=False)


def arm_objects(output,commands):
    old=json.loads((ELFS/'audit.json').read_text());result={}
    for label in ('dormant','window-30s'):
        parent=output/label;parent.mkdir();result[label]={}
        for guarded in (False,True):
            name='guarded' if guarded else 'baseline';folder=parent/name;folder.mkdir();original=ELFS/label/'source'
            shutil.copytree(original,folder/'source');core=folder/'source/core.c';source=core.read_text()
            assert source.count(logger_source(False))==1
            if guarded:core.write_text(source.replace(logger_source(False),logger_source(True)))
            command=next(c for c in old['compiler_commands'] if '-c' in c and c[c.index('-c')+1]==str(original/'core.c'))
            flags=[v.replace(str(original),str(folder/'source')) for v in command[1:command.index('-c')]]
            obj=folder/'core.o';cmd=[command[0],*flags,'-Wformat=2','-c',str(core),'-o',str(obj)]
            base.owner.command(cmd);commands.append(cmd)
            cmd=['/opt/devkitpro/devkitA64/bin/aarch64-none-elf-objdump','-dr','--section=.text.LogFunctionImpl',str(obj)]
            disassembly=base.owner.command(cmd);commands.append(cmd);(folder/'logger-disassembly.txt').write_text(disassembly)
            certificate=object_certificate(obj.read_bytes(),disassembly,guarded)
            (folder/'certificate.json').write_text(json.dumps(certificate,indent=2)+'\n');result[label][name]=certificate
            changed=[str(p.relative_to(original)) for p in original.rglob('*') if p.is_file() and p.read_bytes()!=(folder/'source'/p.relative_to(original)).read_bytes()]
            assert changed==(['core.c'] if guarded else [])
    return result


def run(output):
    verify(SEALED);verify(ELFS);old=json.loads((SEALED/'audit.json').read_text())
    hashes={n:base.ep0.sha(ROOT/n) for n in dict.fromkeys([*old['source_hashes'],*INPUTS])}
    assert all(hashes[n]==h for n,h in old['source_hashes'].items())
    production={n:base.ep0.sha(REPO/n) for n in old['production_sources_sha256']}
    tickets={n:base.ep0.sha(ELFS.parent/n) for n in old['tickets_sha256']}
    assert production==old['production_sources_sha256'] and tickets==old['tickets_sha256']
    source=base.owner.source_audit();assert source==old['source_audit'];commands=[]
    catalog=json.loads((SEALED/'linked-catalog.json').read_text());helpers={}
    for label in ('dormant','window-30s'):
        helpers[label]=helper_profiles((ELFS/label/'full.elf').read_bytes(),(ELFS/label/'disassembly.txt').read_text(),catalog)
        (output/(label+'-sdk-memory.json')).write_text(json.dumps(helpers[label],indent=2)+'\n')
    native=native_audit(output,catalog,commands);objects=arm_objects(output,commands)
    assert hashes=={n:base.ep0.sha(ROOT/n) for n in hashes}
    assert production=={n:base.ep0.sha(REPO/n) for n in production}
    assert tickets=={n:base.ep0.sha(ELFS.parent/n) for n in tickets} and source==base.owner.source_audit()
    result=dict(schema='A23-memory-log-guard-1',source_hashes=hashes,production_sources_sha256=production,tickets_sha256=tickets,source_audit=source,
        sealed_inputs=[verify(SEALED),verify(ELFS)],helper_profiles=helpers,native=native,arm_objects=objects,commands=commands,
        helper_instruction_profiles=sum(p['profile_count'] for p in helpers.values()),native_checks=native['total_checks'],
        sdk_helper_static_frame_bytes=0,strlen_may_read_outside_logical_string=True,mapped_page_precondition_verified_on_device=False,
        size_failure_guard_prepared=True,full_formatter_models_replaced=False,full_arm_candidate_built=False,arm_objects_built=True,
        whole_thread_stack_verified=False,formatter_cfg_pruned=False,actual_sdk_helpers_executed_natively=False,
        actual_filesystem_or_sd_accessed=False,production_modified=False,prior_runtime_modified=False,prior_evidence_modified=False,
        arm_executed=False,firmware_packaged=False,usb_accessed=False,sd_accessed=False,hardware_verified=False,root_cause_confirmed=False)
    (output/'audit.json').write_text(json.dumps(result,indent=2)+'\n');prior.prior.prior.seal(output);return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False);r=run(args.output)
    print(json.dumps({k:r[k] for k in ('helper_instruction_profiles','native_checks','sdk_helper_static_frame_bytes','size_failure_guard_prepared')},indent=2))


if __name__=='__main__':main()
