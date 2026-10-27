#!/usr/bin/env python3
"""Current logger language/length/FILE audit and host-only clamp control."""
import argparse,json,re,shutil,subprocess
from pathlib import Path
import audit_a23_formatter as prior
from analyze_a23_log_contract import inventory,machine_contract
from workflows.artifacts import verify
base=prior.base;ROOT=prior.ROOT;REPO=prior.REPO
SEALED=base.ep0.PRIVATE/'analysis/A23-formatter-frontier-review-20261014';ELFS=prior.ELFS
INPUTS=('tools/analyze_a23_log_contract.py','tools/audit_a23_log_contract.py','tests/a23_file_log_fixture.c')
BOUNDARIES=(0,1,511,512,513,1024)
FAULTS=('unmounted','format-error','open-error','size-error','write-error')

def compiler_calls():return json.loads((ELFS/'audit.json').read_text())['compiler_commands']

def preprocess(folder,label,commands):
    rows=[];fixed_rows=[];command_rows=[]
    annotation=folder/'printf-attribute.h';annotation.write_text('void LogFunctionImpl(const char *, ...) __attribute__((format(printf,1,2)));\n')
    original=ELFS/label/'source';reviewed=folder/'source-reviewed';shutil.copytree(original,reviewed)
    usb=reviewed/'uvc/uvc_device.c';text=usb.read_text()
    old='frequency=%u trigger=%llu';new='frequency=%llu trigger=%llu';assert text.count(old)==1;text=text.replace(old,new)
    old='setup->wValue, urbId, armGetSystemTickFreq(),';new='setup->wValue, urbId, (unsigned long long)armGetSystemTickFreq(),';assert text.count(old)==1;usb.write_text(text.replace(old,new))
    core=reviewed/'core.c';text=core.read_text();marker='    if (len <= 0) return;';assert text.count(marker)==1;core.write_text(text.replace(marker,marker+'\n    if (len >= (int)sizeof(buf)) len = (int)sizeof(buf) - 1;'))
    header=reviewed/'core.h';text=header.read_text();old='void LogFunctionImpl(const char* fmt, ...);';assert text.count(old)==1;header.write_text(text.replace(old,'void LogFunctionImpl(const char* fmt, ...) __attribute__((format(printf,1,2)));'))
    expected=[]
    for cmd in compiler_calls():
        if cmd[0]!='/opt/devkitpro/devkitA64/bin/aarch64-none-elf-gcc' or '-c' not in cmd:continue
        source=Path(cmd[cmd.index('-c')+1])
        if not source.is_relative_to(original):continue
        flags=[f for f in cmd[1:cmd.index('-c')] if f!='-fstack-usage'];unit=source.relative_to(original).as_posix();expected.append(unit)
        out=folder/'preprocessed'/Path(unit).with_suffix('.i');out.parent.mkdir(parents=True,exist_ok=True)
        command=[cmd[0],*flags,'-E','-P',str(source)];text=base.owner.command(command);out.write_text(text);commands.append(command);calls=inventory(text,unit);rows.extend(calls)
        command=[cmd[0],*flags,'-Wformat=2','-fsyntax-only','-include',str(annotation),str(source)]
        result=subprocess.run(command,capture_output=True,text=True);commands.append(command)
        report=folder/'format-diagnostics'/Path(unit).with_suffix('.txt');report.parent.mkdir(parents=True,exist_ok=True);report.write_text(result.stderr)
        expected_error=unit=='uvc/uvc_device.c'
        if expected_error:
            assert result.returncode!=0 and result.stderr.count('error: format ')==1 and 'armGetSystemTickFreq' in result.stderr and 'u64' in result.stderr,result.stderr
        else:assert result.returncode==0 and not result.stderr,result.stderr
        fixed_flags=[f.replace(str(original),str(reviewed)) for f in flags];fixed_source=reviewed/unit
        command=[cmd[0],*fixed_flags,'-Wformat=2','-fsyntax-only',str(fixed_source)];base.owner.command(command);commands.append(command)
        command=[cmd[0],*fixed_flags,'-E','-P',str(fixed_source)];text=base.owner.command(command);commands.append(command)
        out_fixed=folder/'reviewed-preprocessed'/Path(unit).with_suffix('.i');out_fixed.parent.mkdir(parents=True,exist_ok=True);out_fixed.write_text(text);fixed_rows.extend(inventory(text,unit))
        command_rows.append(dict(unit=unit,log_calls=len(calls),preprocessed_sha256=base.ep0.sha(out),original_printf_type_check_passed=not expected_error,original_printf_type_errors=int(expected_error),reviewed_printf_type_check_passed=True))
    assert len(expected)==13 and len(set(expected))==13
    for collection in (rows,fixed_rows):
        for i,row in enumerate(collection):row['case']=i
    return rows,fixed_rows,command_rows

def logger_source(control=False):
    core=(REPO/'source/core.c').read_text().split('#elif FILE_LOGGING',1)[1].split('#endif',1)[0]
    body=core[core.index('void LogFunctionImpl('):]
    frozen=(ELFS/'dormant/source/core.c').read_text().split('#elif FILE_LOGGING',1)[1].split('#endif',1)[0]
    assert body==frozen[frozen.index('void LogFunctionImpl('):]
    if control:
        marker='    if (len <= 0) return;';assert body.count(marker)==1
        body=body.replace(marker,marker+'\n    if (len >= (int)sizeof(buf)) len = (int)sizeof(buf) - 1;')
    return body

def native_source(rows,control=False):
    fixture=(ROOT/'tests/a23_file_log_fixture.c').read_text();calls=[]
    for row in rows:
        # Every row uses conservative max-width correctly typed ASCII inputs;
        # original expressions/type checks remain separately in the catalog.
        args=[r['sample_expression'] for r in row['conversions']]
        calls.append('    case '+str(row['case'])+': LogFunctionImpl('+json.dumps(row['format'])+(' ,'+','.join(args) if args else '')+'); break;')
    return base.trace.replace(base.trace.replace(fixture,'/* INSERT_LOGGER */',logger_source(control)),'/* INSERT_CATALOG */','\n'.join(calls))

def native_audit(output,rows,reviewed_rows,commands):
    catalog=[];edges=[]
    for control in (False,True):
        tag='clamp-control' if control else 'actual';source=output/(tag+'-logger.c');source.write_text(native_source(rows,control));binary=output/tag;commands.append(base.trace.compile_native(source,binary,[]))
        for row in rows:
            result=json.loads(base.owner.command([str(binary),'catalog',str(row['case'])]));result.update(case=row['case'],control=control)
            assert result['required_length']<=row['max_output_bytes']<512 and result['requested']==result['required_length'] and not result['span_exceeds_buffer'] and not result['contains_nul'];catalog.append(result)
        for scenario,value in ([('length',n) for n in BOUNDARIES]+[(s,7) for s in FAULTS]):
            result=json.loads(base.owner.command([str(binary),scenario,str(value)]));result.update(scenario=scenario,input_length=value,control=control);edges.append(result)
    before=[{k:v for k,v in r.items() if k!='control'} for r in catalog if not r['control']];after=[{k:v for k,v in r.items() if k!='control'} for r in catalog if r['control']];assert before==after
    source=output/'reviewed-logger.c';source.write_text(native_source(reviewed_rows,True));binary=output/'reviewed';commands.append(base.trace.compile_native(source,binary,[]));reviewed_cases=[]
    for row in reviewed_rows:
        result=json.loads(base.owner.command([str(binary),'catalog',str(row['case'])]));result.update(case=row['case'])
        assert result['required_length']<=row['max_output_bytes']<512 and result['requested']==result['required_length'] and not result['contains_nul'] and not result['span_exceeds_buffer'];reviewed_cases.append(result)
    return dict(catalog_cases_per_source=len(rows),catalog_cases=len(catalog),boundary_cases_per_source=len(BOUNDARIES)+len(FAULTS),boundary_cases=len(edges),catalog=catalog,edges=edges,
                reviewed_catalog_cases=len(reviewed_cases),reviewed_catalog=reviewed_cases,total_checks=len(catalog)+len(edges)+len(reviewed_cases),
                real_file_logger_function_replayed=True,real_host_vsnprintf_used=True,host_printf_is_not_switch_newlib_execution=True,
                fs_read_size_error_originally_ignored=True,clamp_control_test_only=True,actual_fs_or_dma_reads_executed=False,actual_buffer_overread_executed=False)

def run(output):
    output=Path(output);verify(SEALED);verify(ELFS);old=json.loads((SEALED/'audit.json').read_text())
    inputs={n:base.ep0.sha(ROOT/n) for n in dict.fromkeys([*old['source_hashes'],*INPUTS])}
    for n,h in old['source_hashes'].items():assert inputs[n]==h,n
    production={n:base.ep0.sha(REPO/n) for n in old['production_sources_sha256']};assert production==old['production_sources_sha256']
    tickets={n:base.ep0.sha(base.ep0.PRIVATE/'analysis'/n) for n in base.owner.TICKETS};assert tickets==old['tickets_sha256'];source_audit=base.owner.source_audit();assert source_audit==old['source_audit']
    sdk=Path('/opt/devkitpro/devkitA64/aarch64-none-elf/include');header=sdk/'stdio.h';shutil.copyfile(header,output/'stdio.h');header_hash=base.ep0.sha(header);commands=[];profiles={}
    for label in ('dormant','window-30s'):
        folder=output/label;folder.mkdir();rows,fixed_rows,checks=preprocess(folder,label,commands);elf=ELFS/label/'full.elf';text=(ELFS/label/'disassembly.txt').read_text();contract=machine_contract(elf.read_bytes(),text,header.read_text())
        assert contract['elf_sha256']==old['profiles'][label]['elf_sha256'];assert all(r['max_output_bytes']<512 for r in rows)
        (folder/'catalog.json').write_text(json.dumps(rows,indent=2)+'\n');(folder/'reviewed-catalog.json').write_text(json.dumps(fixed_rows,indent=2)+'\n');(folder/'syntax-checks.json').write_text(json.dumps(checks,indent=2)+'\n');(folder/'machine-contract.json').write_text(json.dumps(contract,indent=2)+'\n')
        profiles[label]=dict(elf_sha256=base.ep0.sha(elf),catalog=rows,reviewed_catalog=fixed_rows,syntax_checks=checks,machine_contract=contract,current_log_calls=len(rows),max_conservative_output_bytes=max(r['max_output_bytes'] for r in rows),
                             reviewed_max_output_bytes=max(r['max_output_bytes'] for r in fixed_rows),conversion_kinds=sorted({c['kind'] for r in rows for c in r['conversions']}))
    rows=profiles['dormant']['catalog'];assert rows==profiles['window-30s']['catalog']
    core=(ELFS/'dormant/source/core.c').read_text();usb=(ELFS/'dormant/source/uvc/uvc_device.c').read_text()
    for marker in ('static char g_serialNumber[32]', 'strncpy(g_serialNumber, serial.number, sizeof(g_serialNumber) - 1);', r"g_serialNumber[sizeof(g_serialNumber) - 1] = '\0';"):
        assert marker in core,marker
    for marker in ('char build[65];','for (unsigned j = 0; j < 32; ++j)', 'build[64] = 0;'):assert marker in usb,marker
    for row in rows:
        for c in row['conversions']:
            if c['kind']=='s' and c['argument']=='g_serialNumber':assert row['unit']=='core.c'
            if c['kind']=='s' and c['argument']=='build':assert row['unit']=='uvc/uvc_device.c'
    native=native_audit(output,rows,profiles['dormant']['reviewed_catalog'],commands)
    assert source_audit==base.owner.source_audit() and inputs=={n:base.ep0.sha(ROOT/n) for n in inputs} and production=={n:base.ep0.sha(REPO/n) for n in production}
    assert tickets=={n:base.ep0.sha(base.ep0.PRIVATE/'analysis'/n) for n in tickets} and header_hash==base.ep0.sha(header);verify(SEALED);verify(ELFS)
    result=dict(schema='A23-log-contract-1',source_audit=source_audit,source_hashes=inputs,production_sources_sha256=production,tickets_sha256=tickets,stdio_header_sha256=header_hash,
                sealed_inputs=[verify(SEALED),verify(ELFS)],commands=commands,profiles=profiles,native=native,
                current_source_language_inventory_complete=True,printf_argument_types_checked=True,original_printf_argument_types_valid=False,original_printf_type_errors_per_config=1,reviewed_source_printf_types_pass=True,isolated_source_fix_prepared=True,all_linked_log_call_sites_bound=False,linked_dead_code_pruned=False,
                current_log_lengths_conditional_on_valid_arguments=True,generic_logger_truncation_hazard_confirmed=True,current_catalog_exceeds_capacity=False,
                file_flags_lifecycle_verified=False,formatter_cfg_pruned=False,whole_thread_stack_verified=False,thread_tls_lifecycle_verified=False,
                production_modified=False,prior_runtime_modified=False,prior_evidence_modified=False,clamp_control_in_arm_candidate=False,new_full_arm_build=False,
                arm_executed=False,firmware_packaged=False,usb_accessed=False,sd_accessed=False,actual_switch_threads_executed=False,cleanup_authorized=False,
                actual_buffer_overread_executed=False,hardware_verified=False,root_cause_confirmed=False,source_authenticated=False)
    (output/'audit.json').write_text(json.dumps(result,indent=2)+'\n');(output/'SHA256SUMS').write_text(''.join(base.ep0.sha(p)+'  '+str(p.relative_to(output))+'\n' for p in sorted(output.rglob('*')) if p.is_file()))
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);s=run(a.output)
    print(json.dumps(dict(profiles={n:dict(calls=p['current_log_calls'],max_output=p['max_conservative_output_bytes'],kinds=p['conversion_kinds']) for n,p in s['profiles'].items()},native_catalog=s['native']['catalog_cases'],native_boundaries=s['native']['boundary_cases']),indent=2))
if __name__=='__main__':main()
