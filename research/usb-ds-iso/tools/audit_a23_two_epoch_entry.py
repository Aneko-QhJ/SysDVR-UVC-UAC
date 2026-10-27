"""Build the dormant entry, run only injected models and reject altered evidence."""
import argparse,json,shutil,subprocess
from pathlib import Path
import build_a23_two_epoch_entry as b
from analyze_a23_two_epoch_entry import analyze
from analyze_a23_two_epoch_sdk import sha
w=b.w

def generated_fixture(source):
    root=Path(source)/'research/usb-ds-iso';parts=[]
    for name in ('a23_two_epoch_receiver_test.m','a23_paired_sdk_fixture.inc','a23_two_epoch_sdk_fixture.inc'):
        text=(root/'tests'/name).read_text();w.require(text.count('\nint main(')==1,'entry prefix ambiguous');parts.append(text.split('\nint main(')[0])
    return '\n'.join(parts)+'\n'+(root/'tests/a23_two_epoch_entry_fixture.inc').read_text()

def write(path,value):path.write_text(json.dumps(value,sort_keys=True,separators=(',',':')))
def rebind(folder):
    final=folder/'entry-final';names=('entry.json','driver.json','receipt-status.json')
    sums=''.join(sha((final/n).read_bytes())+'  '+n+'\n' for n in sorted(names)).encode();(final/'SHA256SUMS').write_bytes(sums);(final/'COMMITTED').write_text(sha(sums)+'\n')

def negatives(normal,root):
    root.mkdir();out={}
    cases=('sandbox','context-bool','context-digest','process-binding','selection-pid','selection-id','wait-order','wait-existing','wait-release',
           'start-order','range','final-stale','snapshot','hardware-claim','released','missing-final','duplicate-json','partial-journal')
    for case in cases:
        folder=root/case;shutil.copytree(normal,folder);result=json.loads((folder/'entry-current.json').read_text());context=json.loads((folder/'context.json').read_text())
        process=json.loads((folder/'process-claim.json').read_text());claim=json.loads((folder/'sdk-claim.json').read_text());rows=[json.loads(r) for r in (folder/'entry.jsonl').read_text().splitlines()]
        final=json.loads((folder/'entry-final-status.json').read_text())
        if case=='sandbox':context['sandbox_query_result']=1
        elif case=='context-bool':context['pid']=True
        elif case=='context-digest':result['context_sha256']='b'*64
        elif case=='process-binding':process['binding']['first_sequence']=97
        elif case=='selection-pid':claim['pid']+=1
        elif case=='selection-id':claim['interface_id']=999
        elif case=='wait-order':
            adapter=[r for r in rows if r['event']=='adapter'];adapter[2]['details']['event']=4;adapter[3]['details']['event']=3
        elif case=='wait-existing':[r for r in rows if r['event']=='adapter'][2]['details']['count']=1
        elif case=='wait-release':result['waiter_failed_releases']=1
        elif case=='start-order':
            i=next(i for i,r in enumerate(rows) if r['event']=='prepared');rows[i],rows[i+1]=rows[i+1],rows[i]
            for n,row in enumerate(rows,1):row['index']=n
        elif case=='range':result['binding']['last_sequence']=111
        elif case=='final-stale':final['stale']=True
        elif case=='hardware-claim':result['hardware_verified']=True
        elif case=='released':result['active_resources_released']=True
        if case in ('sandbox','context-bool'):
            write(folder/'context.json',context)
            result['context_sha256']=sha((folder/'context.json').read_bytes());process['context_sha256']=result['context_sha256'];claim['context_sha256']=result['context_sha256'];rows[0]['details']['sha256']=result['context_sha256']
        for row in rows:
            if row['event']=='process_claim':row['details']=process
            if row['event']=='sdk_claim':row['details']=claim
        write(folder/'process-claim.json',process);write(folder/'sdk-claim.json',claim);write(folder/'entry-current.json',result);write(folder/'entry-final-status.json',final)
        write(folder/'entry-final/entry.json',result);rebind(folder)
        if case=='snapshot':
            altered=dict(result);altered['started']=False;write(folder/'entry-final/entry.json',altered);rebind(folder)
        if case=='missing-final':(folder/'entry-final/COMMITTED').unlink()
        journal=''.join(json.dumps(r,sort_keys=True,separators=(',',':'))+'\n' for r in rows);(folder/'entry.jsonl').write_text(journal[:-1] if case=='partial-journal' else journal)
        if case=='duplicate-json':
            raw=(folder/'entry-current.json').read_text();(folder/'entry-current.json').write_text('{"complete":true,'+raw[1:])
        try:analyze(folder)
        except (ValueError,KeyError,TypeError,FileNotFoundError) as error:out[case]=dict(rejected=True,reason=str(error),checkpoint_hashes_rebound=True)
        else:raise ValueError('bad entry accepted: '+case)
    return out

def file_modes(build,root):
    root.mkdir();binary=build/'entry-inspector';out={}
    for name,args in (('describe',['--describe']),('build',['--check-build',str(build)]),('context',['--inspect-context']),('acquire',['--acquire-once','unused','unused']),('empty',[])):
        r=subprocess.run([str(binary),*args],capture_output=True,text=True);w.card.put(root,name+'.stdout',r.stdout.encode());w.card.put(root,name+'.stderr',r.stderr.encode());out[name]=r.returncode
    w.require(out==dict(describe=0,build=0,context=0,acquire=2,empty=2),'file modes differ');return out

def run(output):
    output=w.canonical(output);w.require(not output.exists(),'new review required');hashes=b.sources();output.mkdir(mode=0o700)
    build=output/'build';reference=b.build(build);w.require(b.verify_build(build)==reference,'build verification differs')
    modes=file_modes(build,output/'file-modes');fixture=build/'source/research/usb-ds-iso/tests/generated_entry_test.m'
    # Keep sealed build immutable; compile a separate exact source/header copy.
    work=output/'native';shutil.copytree(build/'source',work/'source');shutil.copyfile(build/'a23_two_epoch_entry_binding.h',work/'a23_two_epoch_entry_binding.h')
    fixture=work/'source/research/usb-ds-iso/tests/generated_entry_test.m';fixture.write_text(generated_fixture(work/'source'))
    command=b.compile_command(work,work/'entry-test',True);compiled=subprocess.run(command,capture_output=True,text=True)
    w.card.put(output,'native-compile.log',(compiled.stdout+compiled.stderr).encode());w.require(compiled.returncode==0,'entry fixture compile failed')
    models=output/'models';models.mkdir();native=subprocess.run([str(work/'entry-test'),str(models)],capture_output=True,text=True)
    w.card.put(output,'native.stdout',native.stdout.encode());w.card.put(output,'native.stderr',native.stderr.encode());w.require(native.returncode==0,'entry native matrix failed')
    matrix=json.loads(native.stdout);w.require(matrix['case_count']==33,'entry matrix count differs');accepted={};rejected={}
    for name in matrix['cases']:
        try:accepted[name]=analyze(models/name)
        except (ValueError,KeyError,TypeError,FileNotFoundError) as error:rejected[name]=str(error)
    w.require(set(accepted)=={'normal','queued-delay'} and len(rejected)==31,'entry classification differs')
    negative=negatives(models/'normal',output/'negative-entries');w.require(len(negative)==18,'entry negative count differs')
    w.require(b.sources()==hashes,'source drift');audit=dict(schema='A23-two-epoch-entry-audit-1',passed=True,source_hashes=hashes,source_count=len(hashes),prior_sources_unchanged=336,
        build=reference,native_cases=33,matrix=matrix,accepted=accepted,rejected=rejected,negative_entries=negative,file_modes=modes,compiler_command=command,
        usb_requests=0,sd_accesses=0,real_sdk_objects=0,native_iokit_calls=0,formal_records=0,formal_reservations=0,remaining=0,
        actual_sdk_mapping_tested=False,hardware_verified=False,firmware_built=False,formal_issuance_available=False,acquisition_mode_implemented=False)
    w.write(output/'audit.json',audit);w.b.seal(output);return dict(reference=w.reference(output),source_count=len(hashes),native_cases=33,negative_entries=18,passed=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);print(json.dumps(run(p.parse_args().output),indent=2))
