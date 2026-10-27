#!/usr/bin/env python3
"""Narrow literal printf inventory and final-ELF snprintf buffer contract."""
import ast,hashlib,re
import analyze_a23_elf_boundaries as elf

class LogContractError(ValueError):pass
STRING=r'"(?:\\.|[^"\\])*"'

def literal(expression):
    parts=re.findall(STRING,expression)
    if not parts or re.sub(STRING,'',expression).strip():raise LogContractError('Nonliteral format/string')
    value=''.join(ast.literal_eval(part) for part in parts)
    if not value.isascii() or '\0' in value:raise LogContractError('Non-ASCII or embedded NUL literal')
    return value

def arguments(text,start):
    parts=[];depth=0;mark=start;i=start
    while i<len(text):
        c=text[i]
        if c=='"' or c=="'":
            q=c;i+=1
            while i<len(text):
                if text[i]=='\\':i+=2;continue
                if text[i]==q:break
                i+=1
        elif c in '([{':depth+=1
        elif c in ')]}':
            if c==')' and not depth:parts.append(text[mark:i].strip());return parts,i+1
            depth-=1
        elif c==',' and not depth:parts.append(text[mark:i].strip());mark=i+1
        i+=1
    raise LogContractError('Unclosed logger arguments')

def format_contract(fmt,args):
    conversions=[];literal_bytes=0;i=0;ai=0
    while i<len(fmt):
        if fmt[i]!='%':literal_bytes+=len(fmt[i].encode('utf-8'));i+=1;continue
        if i+1<len(fmt) and fmt[i+1]=='%':literal_bytes+=1;i+=2;continue
        m=re.match(r'%([-+ #0]*)(\d*)(hh|h|ll|l|z|j|t)?([diuoxXscp])',fmt[i:])
        if not m:raise LogContractError('Unsupported or dynamic printf conversion: '+fmt[i:])
        if ai>=len(args):raise LogContractError('Missing printf argument')
        flags,width,length,kind=m.groups();length=length or '';width=int(width or 0);arg=args[ai];ai+=1
        if width>256:raise LogContractError('Oversized literal width')
        if kind=='s':
            if length:raise LogContractError('Wide string not in narrow contract')
            if arg=='g_serialNumber':maximum=31;source='serial array32, terminated at31'
            elif arg=='build':maximum=64;source='build array65, hex32bytes then NUL'
            else:maximum=len(literal(arg).encode('utf-8'));source='literal string'
            ctype='const char *';sample='"'+'S'*maximum+'"'
        elif kind in 'diuoxX':
            if length not in ('','ll'):raise LogContractError('Unreviewed integer length')
            bits=64 if length=='ll' else 32;signed=kind in 'di'
            maximum=(20 if bits==64 else 11) if signed else (20 if bits==64 else 10) if kind=='u' else (16 if bits==64 else 8) if kind in 'xX' else (22 if bits==64 else 11)
            if kind in 'xX' and '#' in flags:maximum+=2
            if kind=='o' and '#' in flags:maximum+=1
            if signed and ('+' in flags or ' ' in flags):maximum=max(maximum,21 if bits==64 else 11)
            ctype=('long long' if signed else 'unsigned long long') if bits==64 else ('int' if signed else 'unsigned int')
            sample=('(-9223372036854775807LL-1)' if bits==64 else '(-2147483647-1)') if signed else ('18446744073709551615ULL' if bits==64 else '4294967295U')
            source='full '+str(bits)+'bit argument range'
        else:raise LogContractError('Conversion needs separate bounds: '+kind)
        maximum=max(maximum,width);conversions.append(dict(spec=m[0],flags=flags,width=width,length=length,kind=kind,argument=arg,max_output_bytes=maximum,bound_source=source,sample_expression=sample,sample_type=ctype))
        i+=len(m[0])
    if ai!=len(args):raise LogContractError('Extra printf arguments')
    return dict(format=fmt,literal_bytes=literal_bytes,conversions=conversions,max_output_bytes=literal_bytes+sum(r['max_output_bytes'] for r in conversions),
                conversion_kinds=sorted({r['kind'] for r in conversions}),static_widths_only=True,narrow_only=True,positional_or_star_or_precision_present=False,
                valid_arguments_and_string_termination_assumed=True,actual_runtime_argument_values_verified=False)

def inventory(preprocessed,unit):
    rows=[]
    for m in re.finditer(r'\bLogFunctionImpl\s*\(',preprocessed):
        args,end=arguments(preprocessed,m.end())
        if args[0].startswith('const char'):continue # declaration or definition
        fmt=literal(args[0]);row=format_contract(fmt,args[1:]);row.update(unit=unit,preprocessed_line=preprocessed.count('\n',0,m.start())+1,argument_expressions=args[1:]);rows.append(row)
    return rows

def machine_contract(blob,text,stdio_header):
    fs,metadata=elf.build_functions(blob,text);named={n:a for a,f in fs.items() for n in f['aliases']}
    f=fs[named['LogFunctionImpl']];code={p:(o,a) for p,o,a in f['instructions']}
    calls=[p for p,(o,a) in code.items() if o=='bl' and a.endswith('<vsnprintf>')]
    if len(calls)!=1:raise LogContractError('Logger snprintf call drift')
    p=calls[0]
    if code.get(p-12)!=('mov','x1, #0x200'):raise LogContractError('Logger buffer capacity drift')
    writes=[q for q,(o,a) in code.items() if o=='bl' and a.endswith('<fsFileWrite>')]
    if len(writes)!=1 or code[writes[0]-4]!=('ldrsw','x3, [sp, #24]') or not any(o=='str' and a=='w4, [sp, #24]' for o,a in code.values()):raise LogContractError('Logger unbounded length handoff drift')
    if code[p+4]!=('mov','w4, w0') or code[p+8]!=('cmp','w0, #0x0') or code[p+12][0]!='b.le':raise LogContractError('Logger result filter drift')
    sn=fs[named['_vsnprintf_r']];ins=sn['instructions'];sncode={p:(o,a) for p,o,a in ins}
    sc=[p for p,(o,a) in sncode.items() if o=='bl' and a.endswith('<_svfprintf_r>')]
    if len(sc)!=1:raise LogContractError('snprintf formatter drift')
    setter=[p for p,(o,a) in sncode.items() if (o,a)==('mov','w1, #0xffff0208')]
    if len(setter)!=1 or sncode[setter[0]+4]!=('str','w1, [sp, #88]'):raise LogContractError('String FILE flags drift')
    if sncode[sc[0]-16]!=('add','x1, sp, #0x48'):raise LogContractError('String FILE base drift')
    names={'__SWR':8,'__SSTR':512,'__SMBF':128,'__SOPT':1024}
    for name,value in names.items():
        m=re.search(r'^#define\s+'+name+r'\s+(0x[0-9a-fA-F]+)',stdio_header,re.M)
        if not m or int(m[1],16)!=value:raise LogContractError('stdio flag definition drift')
    printf=fs[named['_svfprintf_r']];pf={p:(o,a) for p,o,a in printf['instructions']}
    check=[p for p,(o,a) in pf.items() if o=='tbz' and a.startswith('w0, #7,')]
    if len(check)!=1 or pf[check[0]-4]!=('ldrh','w0, [x18, #16]'):raise LogContractError('Formatter dynamic buffer guard drift')
    puts=fs[named['__ssputs_r']];pt={p:(o,a) for p,o,a in puts['instructions']}
    checks=[p for p,(o,a) in pt.items() if (o,a)==('tst','w6, w1')]
    if len(checks)!=1 or pt[checks[0]-8]!=('mov','w1, #0x480') or pt[checks[0]+4][0]!='b.eq':raise LogContractError('String append growth guard drift')
    return dict(schema='A23-log-snprintf-contract-1',elf_sha256=metadata['elf_sha256'],buffer_bytes=512,max_stored_text_bytes=511,logger_frame_bytes=elf.frame_range(f,fs)['frame_bytes'],
                logger_function_sha256=elf.function_digest(f),snprintf_function_sha256=elf.function_digest(sn),snprintf_call=calls[0],file_write_call=writes[0],
                file_flags=0x208,file_flags_offset=16,file_remaining_space_for_logger=511,file_string_mode=True,file_write_mode=True,
                file_malloc_bit_initially_clear=True,file_growth_mask_initially_clear=True,initial_buffer_allocation_branch_not_taken=True,
                string_append_growth_branch_not_taken_if_flags_preserved=True,file_flags_preserved_at_runtime_verified=False,
                logger_uses_unclamped_required_length=True,negative_or_zero_return_skips_fs=True,current_callers_under_capacity_proven_from_values=False,
                whole_formatter_paths_pruned=False,whole_thread_stack_verified=False,hardware_verified=False)
