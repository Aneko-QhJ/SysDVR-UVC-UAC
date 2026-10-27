#!/usr/bin/env python3
"""Guarded formatter dispatch and conditional default-locale pointer evidence."""
import hashlib,json,re,struct
from collections import deque
import analyze_a23_elf_boundaries as elf
from analyze_a23_session_stack import immediate

class FormatterError(ValueError):pass

def data_at(blob,metadata,address,length,readonly=False):
    owners=[s for s in metadata['sections'] if s['type']!=8 and s['flags']&2 and s['address']<=address and address+length<=s['address']+s['size']]
    if len(owners)!=1:raise FormatterError('Data outside unique allocated file section')
    s=owners[0]
    if readonly and s['flags']&1:raise FormatterError('Dispatch table is writable')
    start=s['offset']+address-s['address'];return blob[start:start+length]

def relative_relocations(blob,metadata):
    tables=[s for s in metadata['sections'] if s['type']==19 and s['name']=='.relr.dyn']
    if len(tables)!=1:raise FormatterError('Expected RELR table')
    s=tables[0]
    if s['entry_size']!=8 or s['size']%8:raise FormatterError('RELR shape')
    values=struct.unpack('<'+'Q'*(s['size']//8),blob[s['offset']:s['offset']+s['size']]);where=None;addresses=[]
    for value in values:
        if value&1:
            if where is None:raise FormatterError('RELR bitmap before base')
            addresses.extend(where+8*i for i in range(63) if value&(1<<(i+1)));where+=63*8
        else:
            if value%8:raise FormatterError('RELR address alignment')
            addresses.append(value);where=value+8
    if len(addresses)!=len(set(addresses)):raise FormatterError('Duplicate RELR location')
    for address in addresses:data_at(blob,metadata,address,8)
    return sorted(addresses)

def target(arg):
    m=re.search(r'\b([0-9a-f]+) <([^>]+)>',arg)
    if not m:raise FormatterError('Missing direct target')
    return int(m[1],16)

def writes_register(op,arg,register):
    if op in ('cmp','cmn','tst','ccmp','ccmn','svc','ret','br','blr','bl','b','nop') or op.startswith('b.') or op in ('tbz','tbnz','cbz','cbnz'):return False
    parts=[s.strip() for s in arg.split(',')];aliases={register,'w'+register[1:]}
    if op.startswith('st'):
        return bool(re.search(r'\['+register+r'(?:,.*?)?\](?:!|,)',arg))
    if op in ('ldp','ldpsw') and any(s in aliases for s in parts[:2]):return True
    if parts and parts[0] in aliases:return True
    return op.startswith('ld') and bool(re.search(r'\['+register+r'(?:,.*?)?\](?:!|,)',arg))

def origins(f,register,jump_site,jump_targets):
    code={p:(op,arg) for p,op,arg in f['instructions']};incoming={f['start']:{-1}};work=deque([f['start']])
    while work:
        pc=work.popleft()
        if pc not in code:continue
        op,arg=code[pc];out={pc} if writes_register(op,arg,register) else incoming[pc];successors=[]
        if op=='b':successors=[target(arg)]
        elif op=='br':successors=jump_targets if pc==jump_site else []
        elif op in ('ret','udf','brk','hlt'):pass
        else:
            successors=[pc+4]
            if op.startswith('b.') or op in ('cbz','cbnz','tbz','tbnz'):successors.append(target(arg))
        for nxt in successors:
            if nxt not in code:continue
            merged=incoming.get(nxt,set())|out
            if merged!=incoming.get(nxt,set()):incoming[nxt]=merged;work.append(nxt)
    return {str(pc):sorted(s) for pc,s in incoming.items()}

def decode_dispatch(blob,text):
    fs,metadata=elf.build_functions(blob,text);named={n:a for a,f in fs.items() for n in f['aliases']};f=fs[named['_svfprintf_r']]
    code={p:(op,arg) for p,op,arg in f['instructions']};branches=[pc for pc,(op,arg) in code.items() if (op,arg)==('br','x1')]
    if len(branches)!=1:raise FormatterError('Formatter dispatch count drift')
    pc=branches[0]
    expected={-24:('sub','w1, w0, #0x20'),-20:('cmp','w1, #0x5a'),-12:('ldrh','w1, [x26, w1, uxtw #1]'),-4:('add','x1, x2, w1, sxth #2')}
    for offset,value in expected.items():
        if code.get(pc+offset)!=value:raise FormatterError('Guard/load/scale instruction drift')
    if code[pc-16][0]!='b.hi' or code[pc-8][0]!='adr' or not code[pc-8][1].startswith('x2, '):raise FormatterError('Dispatch guard/base drift')
    default=target(code[pc-16][1]);jump_base=target(code[pc-8][1])
    # x26's table definition is required on every path to the guarded load.
    defs=[]
    for p,(op,arg) in code.items():
        m=re.fullmatch(r'x26, x26, #(0x[0-9a-f]+)',arg)
        if op=='add' and m and p<pc:
            prior=[(q,a) for q,(o,a) in code.items() if q<p and o=='adrp' and a.startswith('x26, ')]
            if prior:defs.append((p,max(prior),int(m[1],16)))
    if not defs:raise FormatterError('No table base definition')
    definition,(page_pc,page_arg),offset=max(defs,key=lambda row:row[0]);table=target(page_arg)+offset
    raw=data_at(blob,metadata,table,182,readonly=True);deltas=struct.unpack('<91h',raw);targets=[jump_base+4*d for d in deltas]
    if not all(f['start']<=t<f['end'] and t in code for t in [default,*targets]):raise FormatterError('Dispatch target outside formatter instructions')
    protected=set(range(pc-20,pc+4,4))
    for p,(op,arg) in code.items():
        if op=='bl' and f['start']<=target(arg)<f['end']:raise FormatterError('Internal call bypasses supported guard CFG')
        if op in ('b','bl') or op.startswith('b.') or op in ('tbz','tbnz','cbz','cbnz'):
            if target(arg) in protected and p not in protected and p!=pc-24:raise FormatterError('Branch bypasses dispatch guard')
    if any(t in protected for t in targets):raise FormatterError('Table target bypasses guard')
    x26=origins(f,'x26',pc,sorted(set(targets)))
    if x26.get(str(pc-12))!=[definition] or x26.get(str(definition))!=[page_pc]:raise FormatterError('Dispatch table base is not stable on all CFG paths')
    rows=[dict(index=i,character=i+32,halfword=d,target=targets[i]) for i,d in enumerate(deltas)]
    return dict(schema='A23-formatter-dispatch-1',elf_sha256=metadata['elf_sha256'],formatter_start=f['start'],formatter_end=f['end'],formatter_sha256=elf.function_digest(f),
                at=pc,guard_start=pc-24,index_min=0,index_max=90,character_min=32,character_max=122,default_target=default,
                table_address=table,table_bytes=182,table_sha256=hashlib.sha256(raw).hexdigest(),jump_base=jump_base,entries=rows,targets=sorted(set(targets)),
                x26_page_definition=page_pc,x26_table_definition=definition,x26_origins_at_load=x26[str(pc-12)],x26_origins_at_add=x26[str(definition)],
                readonly_table_verified=True,unsigned_guard_verified=True,sign_extended_scaled_halfwords=True,guard_bypass_edges_found=False,
                callee_saved_x26_abi_assumed=True,valid_readonly_mapping_assumed=True,hardware_verified=False)

def select_dispatch(profile,character):
    w0=character&0xffffffff;index=(w0-32)&0xffffffff
    return profile['entries'][index]['target'] if index<=90 else profile['default_target']

def default_locale(blob,text):
    fs,metadata=elf.build_functions(blob,text);named={n:a for a,f in fs.items() for n in f['aliases']};f=fs[named['_svfprintf_r']]
    code={p:(op,arg) for p,op,arg in f['instructions']};sites=[pc for pc,(op,arg) in code.items() if (op,arg)==('blr','x23')]
    if len(sites)!=1:raise FormatterError('Locale callback count drift')
    pc=sites[0]
    expected={-48:('bl',None),-44:('ldr','x0, [x0, #64]'),-40:('ldr','x1, [sp, #248]'),-36:('cmp','x0, #0x0'),-32:('csel','x0, x0, x1, ne'),-28:('ldr','x23, [x0, #464]')}
    for offset,(op,arg) in expected.items():
        actual=code.get(pc+offset)
        if not actual or actual[0]!=op or (arg is not None and actual[1]!=arg):raise FormatterError('Locale selection sequence drift')
    if not code[pc-48][1].endswith('<__getreent>'):raise FormatterError('Reent getter drift')
    setup=[]
    for q,(op,arg) in code.items():
        if op=='str' and arg=='x0, [sp, #248]' and q<pc:setup.append(q)
    if len(setup)!=1:raise FormatterError('Default locale saved pointer drift')
    q=setup[0]
    definitions=[p for p,(op,arg) in code.items() if p<q and writes_register(op,arg,'x0')]
    if not definitions:raise FormatterError('Default locale GOT definition absent')
    load=max(definitions)
    if code[load][0]!='ldr' or not code[load][1].startswith('x0, [x0, #') or code[load-4][0]!='adrp':raise FormatterError('Default locale GOT setup drift')
    if any(code[p][0] in ('b','br','blr','bl') or code[p][0].startswith('b.') for p in range(load+4,q,4)):raise FormatterError('Default pointer setup not straight line')
    page=target(code[load-4][1]);m=re.fullmatch(r'x0, \[x0, #(\d+)\]',code[load][1]);got=page+int(m[1]);relr=relative_relocations(blob,metadata)
    locale=struct.unpack('<Q',data_at(blob,metadata,got,8))[0]
    symbols=[s for s in metadata['symbols'] if s['name']=='__global_locale' and s['type']==1]
    if len(symbols)!=1 or symbols[0]['address']!=locale or symbols[0]['size']<592:raise FormatterError('Global locale object mismatch')
    callback_slot=locale+464;callback=struct.unpack('<Q',data_at(blob,metadata,callback_slot,8))[0]
    if got not in relr or callback_slot not in relr:raise FormatterError('Locale pointer lacks load-bias relocation')
    if callback!=named['__utf8_mbtowc']:raise FormatterError('Default locale callback changed')
    initial_max=data_at(blob,metadata,locale+584,1)[0]
    if initial_max!=6:raise FormatterError('Default multibyte bound drift')
    impure=next(s for s in metadata['symbols'] if s['name']=='_impure_data');initial_thread_locale=struct.unpack('<Q',data_at(blob,metadata,impure['address']+64,8))[0]
    if initial_thread_locale:raise FormatterError('Initial reent locale no longer null')
    callback_frame=elf.frame_range(fs[callback],fs)
    if callback_frame['unresolved'] or callback_frame['edges'] or callback_frame['frame_bytes']!=16:raise FormatterError('UTF8 callback frame drift')
    return dict(schema='A23-default-locale-callback-1',elf_sha256=metadata['elf_sha256'],formatter_sha256=elf.function_digest(f),at=pc,
                reent_locale_offset=64,locale_callback_offset=464,locale_max_offset=584,default_locale_got=got,global_locale_address=locale,
                global_locale_bytes_sha256=hashlib.sha256(data_at(blob,metadata,locale,symbols[0]['size'])).hexdigest(),callback_slot=callback_slot,
                initial_callback_target=callback,initial_callback_name='__utf8_mbtowc',initial_callback_user_frame=16,initial_mb_cur_max=6,
                initial_impure_locale_null=True,relative_relocation_locations=relr,relative_relocation_count=len(relr),
                load_bias_relocation_assumed=True,thread_locale_null_assumed=True,global_locale_unchanged_assumed=True,valid_reent_tls_assumed=True,
                nonnull_thread_locale_resolved=False,runtime_locale_measured=False,hardware_verified=False)


def frame_dispatch(f,functions,reported=None,contracts=None,resolved=None):
    resolved=resolved or {};contracts=contracts or {};code={p:(op,arg) for p,op,arg in f['instructions']};work=[(f['start'],0)];seen={};edges=[];unknown=[];terminal=[];required=set();maximum=0
    while work:
        pc,depth=work.pop()
        if pc not in code:unknown.append(f'{pc:x}: instruction missing within function range');continue
        if pc in seen:
            if seen[pc]!=depth:unknown.append(f'{pc:x}: inconsistent SP')
            continue
        seen[pc]=depth;op,arg=code[pc];new=depth
        try:
            if op in ('add','sub') and arg.startswith('sp, sp, '):new+=immediate(arg[8:])*(1 if op=='sub' else -1)
            elif re.search(r'\[sp(?:,\s*#(-?(?:0x[0-9a-f]+|\d+)))?\]!',arg):
                m=re.search(r'\[sp(?:,\s*(#-?(?:0x[0-9a-f]+|\d+)))?\]!',arg);new-=immediate(m[1] or '#0')
            elif re.search(r'\[sp\],\s*#',arg):new-=immediate(arg.split('[sp],',1)[1].strip())
            elif arg.startswith('sp,'):raise ValueError('unsupported SP write: '+op+' '+arg)
            if new<0:raise ValueError('SP above entry')
        except ValueError as e:unknown.append(f'{pc:x}: {e}')
        maximum=max(maximum,new)
        target=re.search(r'\b([0-9a-f]+) <([^>]+)>',arg);address=int(target[1],16) if target else None
        resolution=resolved.get(pc)
        if resolution:
            if op=='br' and resolution['kind']=='internal-jump':
                work.extend((address,new) for address in resolution['targets']);continue
            elif op=='blr' and resolution['kind']=='conditional-call':
                edges.append(dict(at=pc,target=resolution['target'],kind='conditional-call',held_bytes=new))
            else:raise FormatterError('Indirect resolution opcode drift')
        if op in ('br','blr') and not resolution:
            unknown.append(f'{pc:x}: indirect {op} {arg}')
            if op=='br':continue
        if op.startswith('.') or op in ('udf','brk','hlt'):
            unknown.append(f'{pc:x}: trap/data opcode {op}');terminal.append(dict(at=pc,kind='unmodeled-trap'));continue
        if op=='svc' and f['start'] in contracts and 'syscall' in contracts[f['start']]:
            required.add(f['start']);terminal.append(dict(at=pc,kind='kernel-no-return-contract',name=f['name']));continue
        internal=address is not None and f['start']<=address<f['end']
        if op=='bl' or (op=='b' and not internal):
            if address in functions:
                edges.append(dict(at=pc,target=address,kind='call' if op=='bl' else 'tail',held_bytes=new))
                if address in contracts:
                    required.add(address);terminal.append(dict(at=pc,kind='callee-no-return-contract',name=functions[address]['name']));continue
            else:unknown.append(f'{pc:x}: unresolved {op} target {arg}')
            if op=='b':continue
        if op=='ret':
            if f['start'] in contracts:unknown.append(f'{pc:x}: no-return function has reachable ret')
            if new:unknown.append(f'{pc:x}: return with allocated SP {new}')
            continue
        if op=='b' and internal:work.append((address,new));continue
        if op.startswith('b.') or op in ('cbz','cbnz','tbz','tbnz'):
            if internal:work.append((address,new))
            else:unknown.append(f'{pc:x}: conditional edge outside symbol range')
        if pc+4<f['end']:work.append((pc+4,new))
        elif f['start'] in contracts and contracts[f['start']].get('end_after_returning_svc_break') and pc==f['end']-4:
            required.add(f['start']);terminal.append(dict(at=pc,kind='abort-boundary-contract',name=f['name']))
        else:unknown.append(f'{pc:x}: falls outside symbol range')
    if reported is not None and maximum!=reported:unknown.append(f'SP/{reported} byte .su disagreement (machine {maximum})')
    return dict(frame_bytes=maximum if not unknown else None,machine_observed_frame=maximum,compiler_reported_frame=reported,edges=edges,
                unresolved=sorted(set(unknown)),abi_contract_addresses=sorted(required),terminal_edges=terminal,instructions_reached=len(seen),instructions_total=len(code))


def analyze_formatter(blob,text,stack_rows,policy=None,wait_certificate=None,roots=elf.ROOTS,dispatch=None,locale=None):
    functions,metadata=elf.build_functions(blob,text);contracts={}
    if policy:
        if metadata['elf_sha256']!=policy['elf_sha256']:raise FormatterError('No-return policy ELF drift')
        if policy['schema']!='A23-SDK-no-return-policy-1' or not policy['sdk_no_return_contract_assumed'] or policy['kernel_contract_measured']:raise FormatterError('No-return policy cannot assert measured contract')
        allowed={'diagAbortWithResult','fatalThrow','svcExitProcess','svcExitThread','svcReturnFromException'}
        if {c['name'] for c in policy['contracts'].values()}!=allowed or len(policy['contracts'])!=5:raise FormatterError('No-return policy unsupported function set')
        for address,c in policy['contracts'].items():
            address=int(address)
            if address not in functions or elf.function_digest(functions[address])!=c['function_sha256']:raise FormatterError('No-return policy function drift')
            f=functions[address]
            if c['name'] not in f['aliases']:raise FormatterError('No-return policy function alias drift')
            expected={'svcExitProcess':7,'svcExitThread':10,'svcReturnFromException':40}.get(c['name'])
            if expected is not None and c.get('syscall')!=expected:raise FormatterError('No-return syscall contract drift')
            if c['name']=='diagAbortWithResult' and not (c.get('end_after_returning_svc_break') and c.get('following_word_is_udf_zero')):raise FormatterError('Abort policy drift')
            contracts[address]=c
    resolved={};formatter=next(a for a,f in functions.items() if '_svfprintf_r' in f['aliases'])
    if dispatch is not None:
        if dispatch!=decode_dispatch(blob,text):raise FormatterError('Dispatch certificate drift')
        resolved[dispatch['at']]=dict(kind='internal-jump',targets=dispatch['targets'])
    if locale is not None:
        if locale!=default_locale(blob,text):raise FormatterError('Locale certificate drift')
        resolved[locale['at']]=dict(kind='conditional-call',target=locale['initial_callback_target'])
    reported={r['function']:r['bytes'] for r in stack_rows if r['kind']=='static'}
    frames={a:frame_dispatch(f,functions,reported.get(f['name']),contracts,resolved if a==formatter else None) for a,f in functions.items()}
    names={}
    for a,f in functions.items():
        for name in f['aliases']:names.setdefault(name,[]).append(a)
    overrides={}
    if wait_certificate:
        # Keep the previous profile's exact machine-body binding. Typed ranges
        # differ in metadata, so verify against the original label parser.
        from analyze_a23_session_stack import parse_disassembly
        from audit_a23_thread_paths import digest_function
        old=parse_disassembly(text);old_names={f['name']:a for a,f in old.items()}
        for n,h in wait_certificate['functions_sha256'].items():
            if n not in old_names or digest_function(old[old_names[n]])!=h:raise FormatterError('Wait certificate machine drift')
        if wait_certificate['full_symbolic_proof'] or not wait_certificate['observed_profiles_only']:raise FormatterError('Wait profile is not full proof')
        for s in wait_certificate['sites']:
            address=s['caller_address'];pc=s['at'];matches=[e for e in frames[address]['edges'] if e['at']==pc and functions[e['target']]['name']=='waitObjects']
            if len(matches)!=1 or s['count'] not in (1,3) or s['wait_objects_observed_peak_bytes']!={1:304,3:400}[s['count']]:raise FormatterError('Wait profile edge drift')
            overrides[address,pc]=s
    cache={}
    def walk(address,ancestors):
        f=frames[address];name=functions[address]['name']
        if address in ancestors:return dict(known_user_prefix_bytes=0,path=[],unresolved=[name+': recursive call cycle'],contracts=[],wait_sites=[],reachable=[])
        if address in cache:return cache[address]
        unknown=[name+': '+s for s in f['unresolved']];best=f['machine_observed_frame'];path=[name];used=set(f['abi_contract_addresses']);waits=[];reachable={address}
        for edge in f['edges']:
            profile=overrides.get((address,edge['at']))
            if profile:
                amount=edge['held_bytes']+profile['wait_objects_observed_peak_bytes'];subpath=['waitObjects[handle-profile n='+str(profile['count'])+']'];waits.append(profile['at'])
            else:
                sub=walk(edge['target'],ancestors|{address});unknown.extend(sub['unresolved']);used.update(sub['contracts']);waits.extend(sub['wait_sites']);reachable.update(sub['reachable'])
                amount=edge['held_bytes']+sub['known_user_prefix_bytes'];subpath=sub['path']
            if amount>best:best=amount;path=[name,*subpath]
        result=dict(known_user_prefix_bytes=best,path=path,unresolved=sorted(set(unknown)),contracts=sorted(used),wait_sites=sorted(set(waits)),reachable=sorted(reachable))
        if not any('recursive call cycle' in v for v in unknown):cache[address]=result
        return result
    output={};used=set()
    for name in roots:
        if len(names.get(name,[]))!=1:raise FormatterError('Missing/ambiguous root '+name)
        r=dict(walk(names[name][0],set()));reachable=r.pop('reachable');used.update(reachable)
        r['sdk_no_return_contracts']=[contracts[a]['name'] for a in r.pop('contracts')];r['reachable_function_addresses']=reachable
        r['default_locale_conditions_required']=bool(locale and formatter in reachable and locale['initial_callback_target'] in reachable)
        r['formatter_dispatch_resolved']=bool(dispatch and formatter in reachable)
        r['closed_user_prefix_graph']=not r['unresolved'];r['contains_wait_profile_substitution']=bool(r['wait_sites'])
        r['user_prefix_bound_bytes']=r['known_user_prefix_bytes'] if not r['unresolved'] and not r['contains_wait_profile_substitution'] else None
        # Never equate a prefix to an entire thread or exception stack.
        r['whole_thread_stack_bound_bytes']=None;output[name]=r
    details={functions[a]['name']+'@'+format(a,'x'):dict(**{k:v for k,v in functions[a].items() if k!='instructions'},**frames[a]) for a in sorted(used)}
    return dict(schema='A23-formatter-stack-1',elf_sha256=metadata['elf_sha256'],roots=output,functions=details,
                dispatch_resolved=dispatch is not None,default_locale_callback_assumed=locale is not None,nonnull_thread_locale_resolved=False,runtime_locale_measured=False,
                function_count=len(functions),symbol_size_ranges=sum(bool(f['symbol_size']) for f in functions.values()),zero_size_ceiling_ranges=sum(not f['symbol_size'] for f in functions.values()),
                symbol_types_and_raw_words_checked=True,zero_size_symbols_use_ceiling_not_declared_size=True,whole_thread_stack_verified=False,
                exception_and_kernel_stack_included=False,sdk_no_return_contract_assumed=bool(contracts),kernel_contract_measured=False,
                actual_abort_executed=False,runtime_peak_measured=False,hardware_verified=False,source_authenticated=False)
