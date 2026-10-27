#!/usr/bin/env python3
"""Conservative final-ELF SP/call audit; unresolved edges never yield a bound."""
import re
ROOTS=('session_capture','Ep0SessionStartupOnly','Ep0SessionJoined','Ep0SessionSaveJoined','__appInit','main','VideoStreamThread','AudioStreamThread','__appExit')

def parse_disassembly(text):
    functions={};current=None
    for line in text.splitlines():
        m=re.match(r'^([0-9a-f]+) <([^>]+)>:$',line)
        if m:current=int(m[1],16);functions[current]=dict(name=m[2],instructions=[]);continue
        m=re.match(r'^\s*([0-9a-f]+):\s+[0-9a-f]{8}\s+(\S+)\s*(.*)$',line)
        if m and current is not None:functions[current]['instructions'].append((int(m[1],16),m[2],m[3].split('//',1)[0].strip()))
    return functions

def immediate(text):
    m=re.fullmatch(r'#(-?(?:0x[0-9a-f]+|\d+))(?:,\s*lsl\s*#(\d+))?',text)
    if not m:raise ValueError('nonconstant SP amount: '+text)
    n=int(m[1],16 if '0x' in m[1] else 10);return n<<int(m[2] or 0)

def frame(function,functions,reported=None):
    instructions=function['instructions'];pcmap={p:(op,arg) for p,op,arg in instructions};pcset=set(pcmap)
    if not instructions:return dict(frame_bytes=None,edges=[],unresolved=['empty body'])
    work=[(instructions[0][0],0)];seen={};edges=[];unknown=[];maximum=0
    while work:
        pc,depth=work.pop()
        if pc not in pcmap:unknown.append(f'control flow outside body at {pc:x}');continue
        if pc in seen:
            if seen[pc]!=depth:unknown.append(f'inconsistent SP at {pc:x}')
            continue
        seen[pc]=depth;op,arg=pcmap[pc];new=depth
        try:
            if op in ('add','sub') and arg.startswith('sp, sp, '):
                amount=immediate(arg[len('sp, sp, '):]);new+=amount if op=='sub' else -amount
            elif re.search(r'\[sp(?:,\s*#(-?(?:0x[0-9a-f]+|\d+)))?\]!',arg):
                m=re.search(r'\[sp(?:,\s*(#-?(?:0x[0-9a-f]+|\d+)))?\]!',arg);new-=immediate(m[1] or '#0')
            elif re.search(r'\[sp\],\s*#',arg):
                new-=immediate(arg.split('[sp],',1)[1].strip())
            elif arg.startswith('sp,'):
                raise ValueError('unsupported SP write: '+op+' '+arg)
            if new<0:raise ValueError('SP above entry')
        except ValueError as e:unknown.append(f'{pc:x}: {e}')
        maximum=max(maximum,new)
        target=re.search(r'\b([0-9a-f]+) <([^>]+)>',arg)
        address=int(target[1],16) if target else None
        if op in ('blr','br'):
            unknown.append(f'{pc:x}: indirect {op} {arg}')
            if op=='br':continue
        if op=='bl' or (op=='b' and address not in pcset):
            if address in functions:edges.append(dict(at=pc,target=address,kind='call' if op=='bl' else 'tail',held_bytes=new))
            else:unknown.append(f'{pc:x}: unresolved {op} target {arg}')
            if op=='b':continue
        if op=='ret':
            if new:unknown.append(f'{pc:x}: return with allocated SP {new}')
            continue
        if op=='b' and address in pcset:work.append((address,new));continue
        if op.startswith('b.') or op in ('cbz','cbnz','tbz','tbnz'):
            if address in pcset:work.append((address,new))
            else:unknown.append(f'{pc:x}: conditional edge outside body')
        if pc+4 in pcset:work.append((pc+4,new))
        elif op not in ('b','ret','br'):unknown.append(f'{pc:x}: falls outside function')
    if reported is not None and maximum!=reported:unknown.append(f'SP/{reported} byte .su disagreement (machine {maximum})')
    return dict(frame_bytes=maximum if not unknown else None,machine_observed_frame=maximum,compiler_reported_frame=reported,
                edges=edges,unresolved=sorted(set(unknown)),instructions_reached=len(seen),instructions_total=len(instructions))

def analyze(text,stack_rows):
    functions=parse_disassembly(text);names={v['name']:a for a,v in functions.items()}
    reported={r['function']:r['bytes'] for r in stack_rows if r['kind']=='static'}
    frames={a:frame(v,functions,reported.get(v['name'])) for a,v in functions.items()}
    def walk(address,ancestors):
        f=frames[address];name=functions[address]['name']
        if address in ancestors:return dict(known_path_bytes=0,path=[],unresolved=[name+': recursive call cycle'])
        unknown=[name+': '+s for s in f['unresolved']];best=f['machine_observed_frame'];path=[name];reachable={address}
        for e in f['edges']:
            sub=walk(e['target'],ancestors|{address});reachable.update(sub.get('reachable',[]));unknown.extend(sub['unresolved'])
            amount=e['held_bytes']+sub['known_path_bytes']
            if amount>best:best=amount;path=[name,*sub['path']]
        return dict(known_path_bytes=best,path=path,unresolved=sorted(set(unknown)),reachable=sorted(reachable))
    results={};used=set()
    for name in ROOTS:
        if name not in names or sum(v['name']==name for v in functions.values())!=1:raise ValueError('Missing/ambiguous root '+name)
        data=walk(names[name],set());reachable=data.pop('reachable');used.update(reachable)
        data['reachable_function_addresses']=[f'{a:x}' for a in reachable]
        data['reachable_functions']=[functions[a]['name'] for a in reachable]
        data['closed_direct_graph']=not data['unresolved'];data['stack_bound_bytes']=data['known_path_bytes'] if data['closed_direct_graph'] else None
        results[name]=data
    details={functions[a]['name']+'@'+format(a,'x'):frames[a] for a in sorted(used)}
    return dict(schema='A23-final-elf-stack-analysis-1',roots=results,functions=details,whole_thread_stack_verified=False,
                exception_and_kernel_stack_included=False,indirect_targets_assumed=False,format_specific_branch_pruning=False,
                runtime_peak_measured=False,hardware_verified=False)
