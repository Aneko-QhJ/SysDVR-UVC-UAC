"""Isolated quiet-poll transitions and frozen arrival/poll deadline policy."""
from fractions import Fraction
from pathlib import Path
import argparse,json,math,random,subprocess
import audit_a23_clock_candidate as previous

view,ar,a,f=previous.view,previous.ar,previous.a,previous.f
U64,U32=previous.U64,previous.U32
PARENT='A23-clock-candidate-closeout-20261020'
PARENT_SUM='4701dc9a578dd7800ebdac29c0cb2ed1f4497c497d07265eed8914b53a65a528'
NEW=('host/a23_quiet_poll_candidate.h','host/a23_quiet_poll_candidate.c','tests/a23_quiet_poll_candidate_fixture.c',
     'tools/audit_a23_quiet_poll_candidate.py','tests/test_a23_quiet_poll_candidate.py')
FALSE={**previous.FALSE,'production_quiet_adapter_integrated':False,'guard_callbacks_authenticated':False,
       'journal_append_durability_authenticated':False,'quiet_state_machine_matches_full_driver':False}


def sources():
    import audit_a23_pinned_view as old
    w=old.w;root=w.A/PARENT;w.card.seal_verify(root)
    f.require(f.sha(w.plain(root/'SHA256SUMS'))==PARENT_SUM,'parent pin differs')
    parent=w.load(root/'closeout.json');out=previous.sources()
    f.require(out==parent['source_hashes'] and len(out)==442,'prior442 drift')
    for name in NEW:
        key='research/usb-ds-iso/'+name;f.require(key not in out,'source overlap');out[key]=f.sha(w.plain(w.ROOT/name))
    return dict(sorted(out.items()))


def stamp(ticks,domain=1,instance=1,n=1,d=1):return [ticks,domain,instance,n,d]
def step(ticks,*,before=1,after=1,complete=1,stop=1,**clock):return stamp(ticks,**clock)+[before,after,complete,stop]
def scenario(start,steps,flags=3):return dict(flags=flags,start=start,steps=steps)


def scenarios():
    out={
        'one-to-one':scenario(stamp(100),[step(250000099),step(250000100),step(250000101)]),
        'fractional-short-equal':scenario(stamp(100,n=2,d=3),[step(375000099,n=2,d=3),step(375000100,n=2,d=3),step(375000101,n=2,d=3)]),
        'unstarted':scenario(stamp(100),[step(250000100),step(250000101)],flags=0),
        'epochs-not-saved':scenario(stamp(100),[step(250000100),step(250000101)],flags=1),
        'already-stopped':scenario(stamp(100),[step(250000100),step(250000101)],flags=7),
        'already-journal-failed':scenario(stamp(100),[step(250000100),step(250000101)],flags=11),
        'zero-sentinel':scenario(stamp(0),[step(250000000),step(250000001)]),
        'preguard-failure':scenario(stamp(100),[step(250000100,before=0),step(250000101)]),
        'postguard-failure':scenario(stamp(100),[step(250000100,after=0),step(250000101)]),
        'completion-append-failure':scenario(stamp(100),[step(250000100,complete=0),step(250000101)]),
        'stop-append-failure':scenario(stamp(100),[step(250000100,before=0,stop=0),step(250000101)]),
        'postguard-stop-append-failure':scenario(stamp(100),[step(250000100,after=0,stop=0),step(250000101)]),
        'settled-then-guard-failure':scenario(stamp(100),[step(250000100),step(250000101,before=0),step(250000102)]),
        'short-does-not-call-postguard':scenario(stamp(100),[step(101,after=0),step(250000100)]),
        'reversed':scenario(stamp(100),[step(99),step(250000100)]),
        'cross-domain':scenario(stamp(100),[step(250000100,domain=2)]),
        'clock-instance-changed':scenario(stamp(100),[step(250000100,instance=2)]),
        'timebase-changed':scenario(stamp(100),[step(250000100,n=2)]),
        'unknown-timebase':scenario(stamp(100,n=0),[step(250000100,n=0)]),
        'owner-role-refused':scenario(stamp(100,domain=2),[step(250000100,domain=2)]),
        'supervisor-role-refused':scenario(stamp(100,domain=3),[step(250000100,domain=3)]),
        'overflow':scenario(stamp(1,n=U32),[step(U64,n=U32)]),
        'attempted-without-settlement':scenario(stamp(100),[step(250000100)],flags=35),
    }
    for flags in range(64):out[f'initial-flags-{flags:02d}']=scenario(stamp(100),[step(250000100),step(250000101)],flags)
    for n,d in ((1,1),(2,3),(125,3),(U32,U32),(1,U32)):
        ticks=math.ceil(Fraction(250000000*d,n))
        if ticks+100<=U64:
            out[f'minimum-{n}-{d}']=scenario(stamp(100,n=n,d=d),[
                step(100+ticks-1,n=n,d=d),step(100+ticks,n=n,d=d),step(101+ticks,n=n,d=d)])
    rng=random.Random(0xA23C110)
    for i in range(512):
        n,d=rng.choice(((1,1),(2,3),(125,3),(U32,1),(1,U32)))
        base=rng.randrange(1,10000);boundary=math.ceil(Fraction(250000000*d,n))
        steps=[step(base+max(0,boundary+offset),n=n,d=d,before=rng.randrange(2),after=rng.randrange(2),
                    complete=rng.randrange(2),stop=rng.randrange(2)) for offset in (-1,0,1)]
        out[f'random-{i:03d}']=scenario(stamp(base,n=n,d=d),steps,rng.choice((0,1,3,7,11)))
    return out


def quiet_wire(cases):
    return ''.join(' '.join(map(str,[v['flags'],*v['start'],len(v['steps']),*(x for s in v['steps'] for x in s)]))+'\n'
                   for v in cases.values()).encode()


def quiet_oracle(case):
    bits=case['flags'];settled_at=reason=clock_status=0
    counts=dict(guard_calls=0,complete_attempts=0,complete_successes=0,stop_attempts=0,stop_successes=0,trace=0)
    rows=[]
    def event(code):counts['trace']=counts['trace']*8+code
    for now in case['steps']:
        before,after,complete_ok,stop_ok=now[5:]
        def stop(why):
            nonlocal bits,reason
            bits=(bits|4)&~(2|16)
            if not reason:
                reason=why;counts['stop_attempts']+=1;counts['stop_successes']+=stop_ok;event(5 if stop_ok else 6)
                if not stop_ok:bits|=8
            return 4 if bits&8 else 3
        if bits&(4|8):
            bits=(bits|4)&~(2|16);status=4 if bits&8 else 3
        elif bits&16 and (not bits&1 or not bits&2 or not bits&32 or not settled_at):status=stop(4)
        elif not bits&1:status=0
        else:
            counts['guard_calls']+=1;event(1 if before else 2)
            if not before:status=stop(2)
            elif not bits&2:status=0
            elif bits&16:status=2
            elif bits&32:status=stop(4)
            else:
                clock_status=(4 if case['start'][1]!=1 else 1 if not case['start'][0] else
                              previous.oracle([*case['start'],*now[:5],250000000,U64])['status'])
                if clock_status:status=stop(1)
                elif Fraction((now[0]-case['start'][0])*case['start'][3],case['start'][4])<250000000:status=1
                else:
                    bits|=32;counts['complete_attempts']+=1;counts['complete_successes']+=complete_ok;event(3 if complete_ok else 4)
                    if not complete_ok:
                        bits=(bits|4|8)&~(2|16);reason=3;status=4
                    else:
                        counts['guard_calls']+=1;event(1 if after else 2)
                        if not after:status=stop(2)
                        else:bits|=16;settled_at=now[0];status=2
        rows.append(dict(poll_status=status,flags=bits,settled_at=settled_at,reason=reason,clock_status=clock_status,**counts))
    return dict(steps=rows)


def deadlines():
    out={}
    for n,d in ((1,1),(2,3),(125,3),(U32,U32),(U32,1),(1,U32)):
        for limit in (0,1,32,16000000,2000000000):
            near=math.floor(Fraction(limit*d,n))
            for delta in sorted({max(0,near-1),near,near+1}):
                for arrival in (0,1):
                    if delta+100<=U64:out[f'edge-{n}-{d}-{limit}-{delta}-{arrival}']=[*stamp(100,n=n,d=d),*stamp(100+delta,n=n,d=d),limit,arrival]
    special={
        'fractional-poll-conservative':[*stamp(100,n=2,d=3),*stamp(147,n=2,d=3),32,0],
        'fractional-arrival-before':[*stamp(100,n=2,d=3),*stamp(147,n=2,d=3),32,1],
        'arrival-exact':[*stamp(100),*stamp(16000100),16000000,1],
        'poll-exact':[*stamp(100),*stamp(16000100),16000000,0],
        'zero-start':[*stamp(0),*stamp(16000000),16000000,1],
        'reversed':[*stamp(100),*stamp(99),1,1],
        'cross-domain':[*stamp(100),*stamp(101,domain=2),1,1],
        'instance':[*stamp(100),*stamp(101,instance=2),1,0],
        'unknown-timebase':[*stamp(100,n=0),*stamp(101,n=0),1,0],
        'overflow':[*stamp(1,n=U32),*stamp(U64,n=U32),U64,1],
    }
    out.update(special);return out


def deadline_oracle(v):
    start,end,limit,arrival=v[:5],v[5:10],v[10],v[11]
    status=1 if not start[0] else previous.oracle([*start,*end,0,limit])['status']
    if status:return dict(clock_status=status,expired=True)
    duration=Fraction((end[0]-start[0])*start[3],start[4])
    return dict(clock_status=0,expired=duration>limit if arrival else math.ceil(duration)>=limit)


def compile_fixture(source_root,output,mode):
    flags=['-std=c11','-Wall','-Wextra','-Werror','-Wconversion','-Wsign-conversion','-O2']
    if mode=='ubsan':flags+=['-fsanitize=undefined','-fno-sanitize-recover=all']
    command=['/usr/bin/clang',*flags,'-I',str(source_root/'host'),str(source_root/'host/a23_clock_candidate.c'),
             str(source_root/'host/a23_quiet_poll_candidate.c'),str(source_root/'tests/a23_quiet_poll_candidate_fixture.c'),'-o',str(output)]
    child=subprocess.run(command,capture_output=True,timeout=60)
    f.require(child.returncode==0 and child.stdout==child.stderr==b'','compile failed '+child.stderr.decode(errors='replace'))
    return dict(command=command,returncode=0,compiler_stdout='',compiler_stderr='',binary_sha256=f.sha(a.read(output)))


def batch(binary,args,cases,data,oracle):
    child=subprocess.run([str(binary),*args],input=data,capture_output=True,timeout=30)
    f.require(child.returncode==0 and child.stderr==b'','fixture batch failed')
    rows=child.stdout.splitlines();f.require(len(rows)==len(cases),'fixture row count differs')
    out={name:f.parse(raw) for name,raw in zip(cases,rows)}
    for name,value in cases.items():f.require(f.encode(out[name])==f.encode(oracle(value)),'transition/oracle differs '+name+': '+str(out[name]))
    return out


def malformed(binary):
    valid=quiet_wire({'valid':scenario(stamp(100),[step(250000100)])})
    bad={'negative':b'-1'+valid[1:],'overflow':str(2**64).encode()+valid[1:],'missing-newline':valid[:-1],
         'partial':b'0\n','extra-column':valid[:-1]+b' 0\n','overlong':b'9'*2200+b'\n',
         'bool-outcome':quiet_wire({'bad':scenario(stamp(100),[step(250000100,before=2)])}),
         'too-many-steps':quiet_wire({'bad':scenario(stamp(100),[step(250000100)]*5)})}
    result={}
    for name,data in bad.items():
        child=subprocess.run([str(binary)],input=data,capture_output=True,timeout=10)
        f.require(child.returncode==2 and child.stdout==child.stderr==b'','bad quiet protocol accepted '+name)
        result[name]=2
    v=[*stamp(100),*stamp(101),1,1]
    for name,index,value in (('arrival-type',11,2),('ratio-width',3,2**32),('domain-width',1,2**31),('ticks-overflow',0,2**64)):
        row=list(v);row[index]=value
        child=subprocess.run([str(binary),'--deadlines'],input=(' '.join(map(str,row))+'\n').encode(),capture_output=True,timeout=10)
        f.require(child.returncode==2 and child.stdout==child.stderr==b'','bad deadline protocol accepted '+name)
        result[name]=2
    return result


def exercise(source_root,build_root):
    build_root.mkdir(mode=0o700);quiet=scenarios();deadline=deadlines();out={};builds={};bad={}
    for mode in previous.MODES:
        binary=build_root/('quiet-fixture-'+mode);builds[mode]=compile_fixture(source_root,binary,mode)
        qr=batch(binary,[],quiet,quiet_wire(quiet),quiet_oracle)
        dr=batch(binary,['--deadlines'],deadline,previous.wire(deadline),deadline_oracle)
        pointer=subprocess.run([str(binary),'--pointer-checks'],capture_output=True,timeout=10)
        f.require(pointer.returncode==0 and pointer.stdout==pointer.stderr==b'','pointer/state reset checks failed')
        bad[mode]=malformed(binary);out[mode]=dict(quiet=qr,deadlines=dr)
    f.require(f.encode(out['optimized'])==f.encode(out['ubsan']),'build modes differ')
    return dict(passed=True,quiet_scenarios=len(quiet),poll_steps=sum(len(v['steps']) for v in quiet.values()),deadline_cases=len(deadline),
                cases=dict(quiet=quiet,deadlines=deadline),results=out['optimized'],builds=builds,malformed_protocol=bad,
                native_fixture_builds=2,native_fixture_executions=30,real_sdk_objects=0,usb_requests=0,sd_accesses=0,
                production_receiver_executions=0,**FALSE)


def verify(root,pin):
    root=a.canonical(root);_,_,digest=a.sealed(root);f.require(f.hex64(pin) and pin==digest,'external review pin differs')
    report=f.load(root/'results.json');quiet=scenarios();deadline=deadlines()
    f.require(report['passed'] is True and report['quiet_scenarios']==len(quiet) and report['deadline_cases']==len(deadline) and
              f.encode(report['cases'])==f.encode(dict(quiet=quiet,deadlines=deadline)),'saved vectors differ')
    for name,value in quiet.items():f.require(f.encode(report['results']['quiet'][name])==f.encode(quiet_oracle(value)),'saved transition differs '+name)
    for name,value in deadline.items():f.require(f.encode(report['results']['deadlines'][name])==f.encode(deadline_oracle(value)),'saved deadline differs '+name)
    for mode in previous.MODES:f.require(f.sha(a.read(root/'build'/('quiet-fixture-'+mode)))==report['builds'][mode]['binary_sha256'],'fixture hash differs')
    f.require(all(report[k] is False for k in FALSE),'candidate claims authority');return report


def run(output):
    import audit_a23_pinned_view as old
    w=old.w;output=a.canonical(output);f.require(not output.exists(),'new quiet-poll review required')
    frozen=sources();output.mkdir(mode=0o700)
    for name,digest in frozen.items():
        value=w.plain(w.b.REPO/name);f.require(f.sha(value)==digest,'source drift');a.put(output,'source/'+name,value)
    result=exercise(output/'source/research/usb-ds-iso',output/'build');a.put(output,'results.json',f.encode(result))
    f.require(sources()==frozen,'source drift after native audit')
    a.put(output,'audit.json',f.encode(dict(passed=True,source_count=447,prior_sources_unchanged=442,source_hashes=frozen,
          quiet_scenarios=result['quiet_scenarios'],poll_steps=result['poll_steps'],deadline_cases=result['deadline_cases'],
          native_fixture_builds=2,native_fixture_executions=30,real_sdk_objects=0,usb_requests=0,sd_accesses=0,
          formal_records=0,formal_reservations=0,**FALSE)))
    a.seal(output);return dict(passed=True,review_sha256=f.sha(a.read(output/'SHA256SUMS')),quiet_scenarios=result['quiet_scenarios'],
                             poll_steps=result['poll_steps'],deadline_cases=result['deadline_cases'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--output',type=Path);group.add_argument('--check',type=Path);parser.add_argument('--expected-sha256');args=parser.parse_args()
    if args.check and not args.expected_sha256:parser.error('--check requires --expected-sha256')
    try:result=run(args.output) if args.output else verify(args.check,args.expected_sha256)
    except (ValueError,OSError,KeyError,TypeError,subprocess.SubprocessError) as exc:print(json.dumps(dict(passed=False,error=str(exc))));raise SystemExit(2)
    if args.output:print(json.dumps(result,indent=2))
    else:print(json.dumps(dict(passed=True,quiet_scenarios=result['quiet_scenarios'],native_execution=False)))
