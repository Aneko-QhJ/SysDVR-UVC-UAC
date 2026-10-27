#!/usr/bin/env python3
"""ELF symbol ranges and explicit SDK no-return contracts; never assume thread safety."""
import hashlib,json,re,struct
from analyze_a23_session_stack import immediate,ROOTS

class BoundaryError(ValueError):pass

def elf_metadata(blob):
    def read(fmt,offset):
        if offset<0 or offset+struct.calcsize(fmt)>len(blob):raise BoundaryError('Truncated ELF record')
        return struct.unpack_from(fmt,blob,offset)
    if len(blob)<64 or blob[:7]!=b'\x7fELF\x02\x01\x01':raise BoundaryError('Expected ELF64 little endian')
    h=read('<16sHHIQQQIHHHHHH',0)
    if h[2]!=183 or h[8]!=64 or h[11]!=64 or not h[12] or h[13]>=h[12]:raise BoundaryError('Unsupported ELF machine/section header')
    sections=[]
    for i in range(h[12]):
        s=read('<IIQQQQIIQQ',h[6]+64*i);sections.append(dict(index=i,name_offset=s[0],type=s[1],flags=s[2],address=s[3],offset=s[4],size=s[5],link=s[6],entry_size=s[9]))
    def data(s):
        if s['type']==8:return b''
        if s['offset']+s['size']>len(blob):raise BoundaryError('Truncated ELF section')
        return blob[s['offset']:s['offset']+s['size']]
    def string(table,index):
        if index>=len(table):raise BoundaryError('ELF string offset')
        end=table.find(b'\0',index)
        if end<0:raise BoundaryError('Unterminated ELF string')
        return table[index:end].decode('utf-8')
    shstr=data(sections[h[13]])
    for s in sections:s['name']=string(shstr,s['name_offset'])
    symbols=[]
    tables=[s for s in sections if s['type']==2]
    if len(tables)!=1:raise BoundaryError('Expected one full symbol table')
    s=tables[0]
    if s['entry_size']!=24 or s['size']%24 or s['link']>=len(sections):raise BoundaryError('ELF symbol table shape')
    names=data(sections[s['link']]);table=data(s)
    for i in range(0,len(table),24):
        n,info,other,section,address,size=struct.unpack_from('<IBBHQQ',table,i)
        symbols.append(dict(name=string(names,n),type=info&15,bind=info>>4,section=section,address=address,size=size))
    return dict(sections=sections,symbols=symbols,elf_sha256=hashlib.sha256(blob).hexdigest())

def raw_word(blob,metadata,address):
    owners=[s for s in metadata['sections'] if s['flags']&4 and s['address']<=address and address+4<=s['address']+s['size']]
    if len(owners)!=1:raise BoundaryError('Instruction outside unique executable section')
    s=owners[0];offset=s['offset']+address-s['address']
    if offset+4>len(blob):raise BoundaryError('Truncated executable word')
    return struct.unpack_from('<I',blob,offset)[0]

def build_functions(blob,text):
    metadata=elf_metadata(blob);instructions={};labels=[]
    for line in text.splitlines():
        m=re.match(r'^([0-9a-f]+) <([^>]+)>:$',line)
        if m:labels.append(dict(address=int(m[1],16),name=m[2]));continue
        m=re.match(r'^\s*([0-9a-f]+):\s+([0-9a-f]{8})\s+(\S+)\s*(.*)$',line)
        if not m:continue
        address=int(m[1],16);word=int(m[2],16)
        if raw_word(blob,metadata,address)!=word:raise BoundaryError('Disassembly byte drift at '+format(address,'x'))
        if address in instructions:raise BoundaryError('Duplicate disassembled instruction')
        instructions[address]=(address,m[3],m[4].split('//',1)[0].strip())
    groups={}
    for s in metadata['symbols']:
        if s['type']!=2 or not 0<s['section']<len(metadata['sections']):continue
        section=metadata['sections'][s['section']]
        if not section['flags']&4:continue
        if s['address']%4 or not section['address']<=s['address']<section['address']+section['size']:raise BoundaryError('Function start outside executable section')
        groups.setdefault(s['address'],[]).append(s)
    functions={};ordered=sorted(groups)
    for start in ordered:
        symbols=groups[start];sections={s['section'] for s in symbols};sizes={s['size'] for s in symbols if s['size']}
        if len(sections)!=1 or len(sizes)>1:raise BoundaryError('Conflicting function aliases')
        section=metadata['sections'][symbols[0]['section']];next_start=min([a for a in ordered if a>start and groups[a][0]['section']==section['index']]+[section['address']+section['size']])
        size=next(iter(sizes),0);end=start+size if size else next_start
        if end>next_start or end>section['address']+section['size'] or end%4:raise BoundaryError('Overlapping or unaligned function range')
        aliases=sorted({s['name'] for s in symbols});name=next((l['name'] for l in labels if l['address']==start and l['name'] in aliases),aliases[0])
        locals_=[s for s in metadata['symbols'] if s['type']==0 and s['bind']==0 and s['section']==section['index'] and start<=s['address']<end and not s['name'].startswith('$')]
        f=dict(name=name,aliases=aliases,start=start,end=end,symbol_size=size,range_kind='symbol-size' if size else 'next-function-ceiling',section=section['name'],
               local_labels=[dict(name=s['name'],address=s['address']) for s in locals_],instructions=[instructions[a] for a in sorted(instructions) if start<=a<end])
        if not f['instructions'] or f['instructions'][0][0]!=start:raise BoundaryError('Function entry not disassembled: '+name)
        functions[start]=f
    if not functions:raise BoundaryError('No executable functions')
    return functions,metadata

def function_digest(f):return hashlib.sha256(json.dumps(f,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def no_return_policy(blob,text,headers):
    functions,metadata=build_functions(blob,text);names={n:a for a,f in functions.items() for n in f['aliases']}
    if not re.search(r'#define NX_NORETURN\s+__attribute__\(\(noreturn\)\)',headers['switch/types.h']):raise BoundaryError('SDK no-return macro drift')
    declarations={
      'diagAbortWithResult':('switch/runtime/diag.h',r'void NX_NORETURN diagAbortWithResult\(Result res\);'),
      'fatalThrow':('switch/services/fatal.h',r'void NX_NORETURN fatalThrow\(Result err\);'),
      'svcExitProcess':('switch/kernel/svc.h',r'void NX_NORETURN svcExitProcess\(void\);'),
      'svcExitThread':('switch/kernel/svc.h',r'void NX_NORETURN svcExitThread\(void\);'),
      'svcReturnFromException':('switch/kernel/svc.h',r'void NX_NORETURN svcReturnFromException\(Result res\);')}
    contracts={}
    for name,(header,pattern) in declarations.items():
        if name not in names or not re.search(pattern,headers[header]):raise BoundaryError('SDK no-return declaration missing: '+name)
        f=functions[names[name]];contracts[names[name]]=dict(name=name,declaration_header=header,function_sha256=function_digest(f))
    # svcBreak returns Result; it must never be silently declared no-return.
    if not re.search(r'Result svcBreak\(u32 breakReason, uintptr_t address, uintptr_t size\);',headers['switch/kernel/svc.h']):raise BoundaryError('svcBreak ABI drift')
    for name,svc in (('svcExitProcess',7),('svcExitThread',10),('svcReturnFromException',40)):
        f=functions[names[name]];body=[(op,arg) for _,op,arg in f['instructions']]
        if body!=[('svc','#'+hex(svc)),('ret','')]:raise BoundaryError('No-return syscall wrapper drift: '+name)
        contracts[names[name]]['syscall']=svc
    f=functions[names['diagAbortWithResult']];last=f['instructions'][-1]
    if last[1]!='bl' or not last[2].endswith('<svcBreak>') or last[0]+4!=f['end'] or raw_word(blob,metadata,f['end'])!=0:raise BoundaryError('Abort boundary or padding drift')
    contracts[names['diagAbortWithResult']].update(end_after_returning_svc_break=True,following_word_is_udf_zero=True)
    f=functions[names['fatalThrow']]
    if not f['instructions'][-1][2].endswith('<svcExitProcess>'):raise BoundaryError('Fatal exit wrapper drift')
    return dict(schema='A23-SDK-no-return-policy-1',elf_sha256=metadata['elf_sha256'],contracts={str(a):c for a,c in contracts.items()},
                headers_sha256={n:hashlib.sha256(s.encode()).hexdigest() for n,s in headers.items()},
                sdk_no_return_contract_assumed=True,kernel_contract_measured=False,svc_break_is_returning=True,
                exception_and_kernel_stack_included=False,actual_abort_executed=False)

def frame_range(f,functions,reported=None,contracts=None):
    contracts=contracts or {};code={p:(op,arg) for p,op,arg in f['instructions']};work=[(f['start'],0)];seen={};edges=[];unknown=[];terminal=[];required=set();maximum=0
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
        if op in ('br','blr'):
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

def analyze(blob,text,stack_rows,policy=None,wait_certificate=None,roots=ROOTS):
    functions,metadata=build_functions(blob,text);contracts={}
    if policy:
        if metadata['elf_sha256']!=policy['elf_sha256']:raise BoundaryError('No-return policy ELF drift')
        if policy['schema']!='A23-SDK-no-return-policy-1' or not policy['sdk_no_return_contract_assumed'] or policy['kernel_contract_measured']:raise BoundaryError('No-return policy cannot assert measured contract')
        allowed={'diagAbortWithResult','fatalThrow','svcExitProcess','svcExitThread','svcReturnFromException'}
        if {c['name'] for c in policy['contracts'].values()}!=allowed or len(policy['contracts'])!=5:raise BoundaryError('No-return policy unsupported function set')
        for address,c in policy['contracts'].items():
            address=int(address)
            if address not in functions or function_digest(functions[address])!=c['function_sha256']:raise BoundaryError('No-return policy function drift')
            f=functions[address]
            if c['name'] not in f['aliases']:raise BoundaryError('No-return policy function alias drift')
            expected={'svcExitProcess':7,'svcExitThread':10,'svcReturnFromException':40}.get(c['name'])
            if expected is not None and c.get('syscall')!=expected:raise BoundaryError('No-return syscall contract drift')
            if c['name']=='diagAbortWithResult' and not (c.get('end_after_returning_svc_break') and c.get('following_word_is_udf_zero')):raise BoundaryError('Abort policy drift')
            contracts[address]=c
    reported={r['function']:r['bytes'] for r in stack_rows if r['kind']=='static'}
    frames={a:frame_range(f,functions,reported.get(f['name']),contracts) for a,f in functions.items()}
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
            if n not in old_names or digest_function(old[old_names[n]])!=h:raise BoundaryError('Wait certificate machine drift')
        if wait_certificate['full_symbolic_proof'] or not wait_certificate['observed_profiles_only']:raise BoundaryError('Wait profile is not full proof')
        for s in wait_certificate['sites']:
            address=s['caller_address'];pc=s['at'];matches=[e for e in frames[address]['edges'] if e['at']==pc and functions[e['target']]['name']=='waitObjects']
            if len(matches)!=1 or s['count'] not in (1,3) or s['wait_objects_observed_peak_bytes']!={1:304,3:400}[s['count']]:raise BoundaryError('Wait profile edge drift')
            overrides[address,pc]=s
    def walk(address,ancestors):
        f=frames[address];name=functions[address]['name']
        if address in ancestors:return dict(known_user_prefix_bytes=0,path=[],unresolved=[name+': recursive call cycle'],contracts=[],wait_sites=[],reachable=[])
        unknown=[name+': '+s for s in f['unresolved']];best=f['machine_observed_frame'];path=[name];used=set(f['abi_contract_addresses']);waits=[];reachable={address}
        for edge in f['edges']:
            profile=overrides.get((address,edge['at']))
            if profile:
                amount=edge['held_bytes']+profile['wait_objects_observed_peak_bytes'];subpath=['waitObjects[handle-profile n='+str(profile['count'])+']'];waits.append(profile['at'])
            else:
                sub=walk(edge['target'],ancestors|{address});unknown.extend(sub['unresolved']);used.update(sub['contracts']);waits.extend(sub['wait_sites']);reachable.update(sub['reachable'])
                amount=edge['held_bytes']+sub['known_user_prefix_bytes'];subpath=sub['path']
            if amount>best:best=amount;path=[name,*subpath]
        return dict(known_user_prefix_bytes=best,path=path,unresolved=sorted(set(unknown)),contracts=sorted(used),wait_sites=sorted(set(waits)),reachable=sorted(reachable))
    output={};used=set()
    for name in roots:
        if len(names.get(name,[]))!=1:raise BoundaryError('Missing/ambiguous root '+name)
        r=walk(names[name][0],set());reachable=r.pop('reachable');used.update(reachable)
        r['sdk_no_return_contracts']=[contracts[a]['name'] for a in r.pop('contracts')];r['reachable_function_addresses']=reachable
        r['closed_user_prefix_graph']=not r['unresolved'];r['contains_wait_profile_substitution']=bool(r['wait_sites'])
        r['user_prefix_bound_bytes']=r['known_user_prefix_bytes'] if not r['unresolved'] and not r['contains_wait_profile_substitution'] else None
        # Never equate a prefix to an entire thread or exception stack.
        r['whole_thread_stack_bound_bytes']=None;output[name]=r
    details={functions[a]['name']+'@'+format(a,'x'):dict(**{k:v for k,v in functions[a].items() if k!='instructions'},**frames[a]) for a in sorted(used)}
    return dict(schema='A23-ELF-boundary-stack-1',elf_sha256=metadata['elf_sha256'],roots=output,functions=details,
                function_count=len(functions),symbol_size_ranges=sum(bool(f['symbol_size']) for f in functions.values()),zero_size_ceiling_ranges=sum(not f['symbol_size'] for f in functions.values()),
                symbol_types_and_raw_words_checked=True,zero_size_symbols_use_ceiling_not_declared_size=True,whole_thread_stack_verified=False,
                exception_and_kernel_stack_included=False,sdk_no_return_contract_assumed=bool(contracts),kernel_contract_measured=False,
                actual_abort_executed=False,runtime_peak_measured=False,hardware_verified=False,source_authenticated=False)
