"""Build isolated C clock arithmetic and compare it with a Fraction oracle."""
from fractions import Fraction
from pathlib import Path
import argparse,json,math,random,subprocess,sys
import audit_a23_cached_outer_forensics as previous

view,ar,a,f=previous.view,previous.ar,previous.a,previous.f
PARENT='A23-outer-forensics-closeout-20261020'
PARENT_SUM='a735466ee5a01822cfe08fea7105365d6dd675b01bf812cf0fef89133e4f11dc'
NEW=('host/a23_clock_candidate.h','host/a23_clock_candidate.c','tests/a23_clock_candidate_fixture.c',
     'tools/audit_a23_clock_candidate.py','tests/test_a23_clock_candidate.py')
U64=2**64-1
U32=2**32-1
FALSE={**previous.model.FALSE,'native_clock_candidate_integrated':False,
       'native_receiver_rebuilt':False,'actual_timebase_queried':False,'clock_labels_authenticated':False}
MODES=('optimized','ubsan')


def sources():
    import audit_a23_pinned_view as old
    w=old.w;root=w.A/PARENT;w.card.seal_verify(root)
    f.require(f.sha(w.plain(root/'SHA256SUMS'))==PARENT_SUM,'parent pin differs')
    parent=w.load(root/'closeout.json');out=previous.sources()
    f.require(out==parent['source_hashes'] and len(out)==437,'prior437 drift')
    for name in NEW:
        key='research/usb-ds-iso/'+name;f.require(key not in out,'source overlap');out[key]=f.sha(w.plain(w.ROOT/name))
    return dict(sorted(out.items()))


def row(begin=0,end=0,n=1,d=1,minimum=0,maximum=U64,domain=1,instance=1):
    return [begin,domain,instance,n,d,end,domain,instance,n,d,minimum,maximum]


def vectors():
    out={
        'fractional-shortfall':row(end=374999999,n=2,d=3,minimum=250000000),
        'fractional-equality':row(end=375000000,n=2,d=3,minimum=250000000),
        'fractional-after':row(end=375000001,n=2,d=3,minimum=250000000),
        'current-profile-short':row(end=249999999,minimum=250000000),
        'current-profile-equal':row(end=250000000,minimum=250000000),
        'current-profile-after':row(end=250000101,minimum=250000000),
        'zero-origin':row(end=1,minimum=1,maximum=1),
        'zero-interval':row(maximum=0),
        'zero-short':row(minimum=1),
        'maximum-equal':row(end=48,n=2,d=3,maximum=32),
        'maximum-over':row(end=49,n=2,d=3,maximum=32),
        'limit-product-wide':row(end=U64,n=U32,d=U32,minimum=U64,maximum=U64),
        'duration-max':row(end=U64,minimum=U64,maximum=U64),
        'duration-overflow':row(end=U64,n=U32),
        'ceil-only-overflow':row(end=(U64*(U32-2))//(U32-1)+1,n=U32-1,d=U32-2),
        'large-denominator':row(end=1,n=1,d=U32,minimum=1),
        'reversed':row(begin=2,end=1),
        'limits-reversed':row(minimum=2,maximum=1),
        'unknown-both':row(domain=0),
        'unknown-owner-timebase':row(domain=2,n=0,d=0),
        'owner-declared-ratio':row(domain=2,end=6,n=125,d=3,minimum=250,maximum=250),
        'supervisor-ns':row(domain=3,end=250000000,minimum=250000000),
        'supervisor-scaled':row(domain=3,end=1,n=2,d=2),
        'zero-instance':row(instance=0),
        'numerator-zero':row(n=0),
        'denominator-zero':row(d=0),
    }
    for name,index,value in (('cross-domain',6,2),('different-instance',7,2),
                             ('changed-numerator',8,2),('changed-denominator',9,2),
                             ('unknown-end-domain',6,99),('end-unknown-timebase',8,0)):
        v=row(end=1);v[index]=value;out[name]=v
    # Same rational scale expressed differently must not hide a profile change.
    v=row(end=3,n=2,d=3);v[8:10]=[4,6];out['equivalent-but-different-timebase']=v
    for n,d in ((1,1),(2,3),(125,3),(U32,1),(1,U32),(U32,U32)):
        for begin in (0,1,U64-6):
            for delta in (0,1,2,3,6):
                exact=Fraction(delta*n,d);ceiling=math.ceil(exact)
                for limit in sorted({max(0,ceiling-1),min(U64,ceiling),min(U64,ceiling+1)}):
                    out[f'boundary-{n}-{d}-{begin}-{delta}-{limit}']=row(begin,begin+delta,n,d,limit,limit)
    rng=random.Random(0xA23C10C)
    for i in range(2048):
        begin=rng.randrange(2**64);end=rng.randrange(begin,2**64)
        n=rng.choice((1,2,125,U32,rng.randrange(1,2**32)));d=rng.choice((1,3,U32,rng.randrange(1,2**32)))
        low=rng.randrange(2**64);high=rng.randrange(low,2**64)
        out[f'random-{i:04d}']=row(begin,end,n,d,low,high,domain=rng.choice((1,2)))
    return out


def oracle(v):
    f.require(type(v) is list and len(v)==12 and all(type(x) is int and 0<=x<=U64 for x in v),'oracle wire integer differs')
    f.require(all(v[i]<=U32 for i in (3,4,8,9)) and all(v[i]<=2**31-1 for i in (1,6)),'oracle native field width differs')
    b,bd,bi,bn,bden,e,ed,ei,en,eden,low,high=v
    status=0;value=None
    if low>high:status=1
    elif bd not in (1,2,3) or ed not in (1,2,3):status=2
    elif not all((bn,bden,en,eden)) or (bd==3 and (bn,bden)!=(1,1)) or (ed==3 and (en,eden)!=(1,1)):status=3
    elif not bi or not ei or (bd,bi,bn,bden)!=(ed,ei,en,eden):status=4
    elif e<b:status=5
    else:
        value=Fraction(e-b)*Fraction(bn,bden)
        if math.ceil(value)>U64:status=6
    if status:return dict(status=status,rounded_up_ns=0,minimum_met=False,maximum_met=False,within_interval=False)
    return dict(status=0,rounded_up_ns=math.ceil(value),minimum_met=value>=low,
                maximum_met=value<=high,within_interval=low<=value<=high)


def wire(cases):return ''.join(' '.join(map(str,v))+'\n' for v in cases.values()).encode()


def compile_fixture(source_root,output,mode):
    f.require(mode in MODES,'unknown build mode')
    flags=['-std=c11','-Wall','-Wextra','-Werror','-Wconversion','-Wsign-conversion','-O2']
    if mode=='ubsan':flags+=['-fsanitize=undefined','-fno-sanitize-recover=all']
    command=['/usr/bin/clang',*flags,'-I',str(source_root/'host'),str(source_root/'host/a23_clock_candidate.c'),
             str(source_root/'tests/a23_clock_candidate_fixture.c'),'-o',str(output)]
    child=subprocess.run(command,capture_output=True,timeout=60)
    f.require(child.returncode==0 and child.stdout==b'' and child.stderr==b'','compile failed '+child.stderr.decode(errors='replace'))
    return dict(command=command,returncode=child.returncode,compiler_stdout='',compiler_stderr='',binary_sha256=f.sha(a.read(output)))


def run_fixture(binary,cases):
    child=subprocess.run([str(binary)],input=wire(cases),capture_output=True,timeout=30)
    f.require(child.returncode==0 and child.stderr==b'','arithmetic fixture failed '+child.stderr.decode(errors='replace'))
    lines=child.stdout.splitlines();f.require(len(lines)==len(cases),'native output count differs')
    rows={name:f.parse(value) for name,value in zip(cases,lines)}
    for name,v in cases.items():f.require(f.encode(rows[name])==f.encode(oracle(v)),'Fraction oracle differs '+name)
    pointer=subprocess.run([str(binary),'--pointer-checks'],capture_output=True,timeout=10)
    f.require(pointer.returncode==0 and pointer.stdout==pointer.stderr==b'','null pointer/output reset checks failed')
    return rows


def malformed_protocol(binary):
    valid=wire({'normal':row()})
    bad={'negative':b'-1 '+valid[2:],'uint64-overflow':str(2**64).encode()+valid[1:],
         'uint32-overflow':wire({'bad':row(n=2**32)}),'missing-newline':valid[:-1],
         'extra-column':valid[:-1]+b' 0\n','partial':b'0\n','overlong':b'9'*600+b'\n',
         'nondigit':b'x'+valid[1:]}
    result={}
    for name,data in bad.items():
        child=subprocess.run([str(binary)],input=data,capture_output=True,timeout=10)
        f.require(child.returncode==2 and child.stdout==child.stderr==b'','malformed protocol accepted '+name)
        result[name]=dict(returncode=child.returncode,stdout_empty=True,stderr_empty=True)
    return result


def exercise(source_root,build_root):
    build_root.mkdir(mode=0o700);cases=vectors();out={};builds={};malformed={}
    for mode in MODES:
        binary=build_root/('clock-fixture-'+mode);builds[mode]=compile_fixture(source_root,binary,mode)
        out[mode]=run_fixture(binary,cases);malformed[mode]=malformed_protocol(binary)
    f.require(f.encode(out['optimized'])==f.encode(out['ubsan']),'optimization/sanitizer results differ')
    rows=out['optimized'];counter=rows['fractional-shortfall']
    f.require(counter['rounded_up_ns']==250000000 and counter['minimum_met'] is False,'fractional counterexample lost')
    return dict(passed=True,case_count=len(cases),cases=cases,results=rows,builds=builds,malformed_protocol=malformed,
                status_counts={str(code):sum(v['status']==code for v in rows.values()) for code in range(7)},
                native_fixture_builds=2,native_fixture_executions=20,real_sdk_objects=0,usb_requests=0,sd_accesses=0,
                production_receiver_executions=0,**FALSE)


def verify(root,pin):
    root=a.canonical(root);_,_,digest=a.sealed(root);f.require(f.hex64(pin) and pin==digest,'external review pin differs')
    report=f.load(root/'results.json');cases=vectors()
    f.require(report['passed'] is True and report['case_count']==len(cases) and
              f.encode(report['cases'])==f.encode(cases),'saved vectors differ')
    for name,v in cases.items():f.require(f.encode(report['results'][name])==f.encode(oracle(v)),'saved oracle differs '+name)
    for mode in MODES:
        f.require(f.sha(a.read(root/'build'/('clock-fixture-'+mode)))==report['builds'][mode]['binary_sha256'],'saved fixture binary differs')
    f.require(all(report[k] is False for k in FALSE),'candidate claims authority')
    return report


def run(output):
    import audit_a23_pinned_view as old
    w=old.w;output=a.canonical(output);f.require(not output.exists(),'new native-clock review required')
    frozen=sources();output.mkdir(mode=0o700)
    for name,digest in frozen.items():
        value=w.plain(w.b.REPO/name);f.require(f.sha(value)==digest,'source drift');a.put(output,'source/'+name,value)
    source_root=output/'source/research/usb-ds-iso'
    result=exercise(source_root,output/'build');a.put(output,'results.json',f.encode(result))
    compiler=subprocess.run(['/usr/bin/clang','--version'],capture_output=True,timeout=10)
    f.require(compiler.returncode==0 and compiler.stderr==b'','compiler identity unavailable')
    a.put(output,'compiler-version.txt',compiler.stdout)
    f.require(sources()==frozen,'source drift after native audit')
    a.put(output,'audit.json',f.encode(dict(passed=True,source_count=442,prior_sources_unchanged=437,source_hashes=frozen,
          case_count=result['case_count'],native_fixture_builds=2,native_fixture_executions=20,
          real_sdk_objects=0,usb_requests=0,sd_accesses=0,formal_records=0,formal_reservations=0,**FALSE)))
    a.seal(output);return dict(passed=True,review_sha256=f.sha(a.read(output/'SHA256SUMS')),case_count=result['case_count'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--output',type=Path);group.add_argument('--check',type=Path);parser.add_argument('--expected-sha256');args=parser.parse_args()
    if args.check and not args.expected_sha256:parser.error('--check requires --expected-sha256')
    try:result=run(args.output) if args.output else verify(args.check,args.expected_sha256)
    except (ValueError,OSError,KeyError,TypeError,subprocess.SubprocessError) as exc:print(json.dumps(dict(passed=False,error=str(exc))));raise SystemExit(2)
    if args.output:print(json.dumps(result,indent=2))
    else:print(json.dumps(dict(passed=True,case_count=result['case_count'],native_execution=False)))
