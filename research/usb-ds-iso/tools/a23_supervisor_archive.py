"""Read-only model supervisor evidence; no executable launch or live roots."""
from pathlib import Path
import a23_final_archive as a
from a23_execution_context import KEYS,validate as validate_context
f=a.f
FALSE={**a.FALSE,'acquisition_permitted':False,'parent_sandbox_evaluated':False}
MODES=('normal','hold-before','hold-after','nonce','pid','ppid','uid','bool-pid','binary','path','environment','handoff','duplicate','trailing','partial','stdout-limit','stderr-limit','exit3','no-hello')

def build_info(root):
    files,dirs,digest=a.sealed(root);m=f.parse(files['build.json']);f.require(set(m)=={'schema','source_hashes','binary_sha256','model_only'} and m['schema']=='A23-supervisor-model-build-1' and m['model_only'] is True,'model build differs');expected={'build.json','compile.log','model-child'}|{'source/'+n for n in m['source_hashes']}
    f.require(set(files)==expected and dirs==a.prefixes(expected),'model build inventory differs')
    for n,h in m['source_hashes'].items():f.require(f.hex64(h) and f.sha(files['source/'+n])==h,'model source differs')
    f.require(f.sha(files['model-child'])==m['binary_sha256'],'model binary differs');return dict(manifest_sha256=digest,binary_sha256=m['binary_sha256'],source_count=len(m['source_hashes']))

def link(hello,handoff,child_pid,binary):
    f.require(type(hello) is dict and set(hello)=={'schema','nonce','handoff_sha256','environment_sha256','forbidden_environment_present','context','hardware_entry_enabled'} and hello['schema']=='A23-supervisor-model-hello-1','hello inventory differs')
    f.require(hello['nonce']==handoff['nonce'] and hello['handoff_sha256']==f.sha(f.encode(handoff)),'hello handoff differs');f.require(hello['environment_sha256']==handoff['environment_sha256'] and hello['forbidden_environment_present'] is False and hello['hardware_entry_enabled'] is False,'child environment differs')
    c=hello['context'];f.require(type(c) is dict and set(c)==KEYS and c['schema']=='A23-execution-context-1','child context inventory differs')
    for k in ('pid','ppid','uid','euid','gid','egid','sample_begin_ticks','sample_end_ticks','sandbox_query_result','sandbox_query_errno'):f.require(type(c[k]) is int,'child context number differs')
    f.require(c['pid']==child_pid and child_pid>0 and c['ppid']==handoff['parent']['pid'],'child process identity differs')
    for k in ('uid','euid','gid','egid'):f.require(c[k]==handoff['parent'][k],'child credentials differ')
    for k in ('os_build','os_version','machine','receiver_path','receiver_sha256','framework_uuid'):f.require(type(c[k]) is str and c[k],'child context string differs')
    f.require(type(c['sandbox_query_available']) is bool,'child sandbox flag differs')
    f.require(c['receiver_path']==binary and c['receiver_sha256']==handoff['build']['binary_sha256'],'child binary differs');f.require(0<c['sample_begin_ticks']<=c['sample_end_ticks'],'child sample differs')
    f.require(c['usb_open_permission_proven'] is False and c['automatic_privilege_change'] is False,'child grants unsupported authority')
    try:validate_context(c,handoff['build']['binary_sha256'])
    except ValueError:policy=False
    else:policy=True
    return policy

def analyze(root,build):
    files,dirs,_=a.sealed(root);f.require(set(files)=={'OWNER','OWNER-original','handoff.json','handoff-original.json','launch-attempt','result.json','stdout.bin','stderr.bin'},'supervisor archive inventory differs');f.require(dirs==['scratch'],'supervisor archive directories differ');h=f.parse(files['handoff-original.json']);r=f.parse(files['result.json']);ref=build_info(build)
    f.require(h['schema']=='A23-supervisor-handoff-1' and h['build']==ref and f.hex64(h['nonce']) and files['OWNER-original']==(h['nonce']+'\n').encode() and files['launch-attempt']==b'one model launch attempt\n','supervisor handoff/owner differs')
    f.require(set(h)=={'schema','nonce','parent','build','environment_sha256','model_only','inherited_environment'} and h['model_only'] is True and h['inherited_environment'] is False and f.hex64(h['environment_sha256']),'handoff inventory/authority differs')
    f.require(type(h['parent']) is dict and set(h['parent'])=={'pid','ppid','uid','euid','gid','egid'} and all(type(n) is int and n>=0 for n in h['parent'].values()) and h['parent']['pid']>0,'parent identity type differs')
    expected={'schema','launch_begin_ns','deadline_ns','hello_observed_ns','settled_ns','child_pid','binary_path','producer_exited','returncode','timed_out','truncated','hello_consistent','child_execution_policy_pass','supervision_complete','stdout_eof','stderr_eof','failure_reasons',*FALSE}
    f.require(type(r) is dict and set(r)==expected and type(r['child_pid']) is int and r['child_pid']>0 and type(r['binary_path']) is str and Path(r['binary_path']).is_absolute() and type(r['stdout_eof']) is bool and type(r['stderr_eof']) is bool,'supervisor result inventory differs')
    f.require(type(r['failure_reasons']) is list and all(type(n) is str for n in r['failure_reasons']) and len(r['failure_reasons'])==len(set(r['failure_reasons'])),'supervisor reasons differ')
    f.require(r.get('schema')=='A23-supervisor-result-1' and all(r.get(k) is False for k in FALSE),'supervisor authority differs');f.require(r['producer_exited'] is True and type(r['returncode']) is int,'producer not exited');f.require(type(r['timed_out']) is bool and type(r['truncated']) is bool and type(r['hello_consistent']) is bool and type(r['supervision_complete']) is bool and type(r['child_execution_policy_pass']) is bool,'supervisor flags differ')
    for k in ('launch_begin_ns','deadline_ns','hello_observed_ns','settled_ns'):f.require(type(r[k]) is int and r[k]>=0,'supervisor clock type differs')
    f.require(0<r['launch_begin_ns']<r['deadline_ns'] and r['settled_ns']>=r['launch_begin_ns'] and r['deadline_ns']-r['launch_begin_ns']<=5000000000,'supervisor clock bounds differ')
    f.require(r['timed_out'] is (r['settled_ns']>=r['deadline_ns']),'deadline verdict differs')
    if r['supervision_complete']:f.require(files['handoff.json']==files['handoff-original.json'] and files['OWNER']==files['OWNER-original'],'complete owner/handoff changed')
    f.require(0<=len(files['stdout.bin'])<=4096 and 0<=len(files['stderr.bin'])<=256,'supervisor byte limit differs');lines=files['stdout.bin'].splitlines(keepends=True);valid=False;policy=False
    if lines and lines[0].endswith(b'\n'):
        try:policy=link(f.parse(lines[0]),h,r['child_pid'],r['binary_path']);valid=True
        except (ValueError,KeyError,TypeError):pass
    # A deadline or earlier failure never admits a late hello. Partial/failure
    # receipts stay failures even if their final bytes later look consistent.
    if r['hello_consistent']:f.require(r['launch_begin_ns']<=r['hello_observed_ns']<r['deadline_ns'] and valid and r['child_execution_policy_pass']==policy,'saved hello verdict differs')
    complete=len(lines)==1 and valid and r['hello_consistent'] and not r['failure_reasons'] and not r['timed_out'] and not r['truncated'] and r['returncode']==0 and r['stdout_eof'] and r['stderr_eof']
    f.require(r['supervision_complete'] is complete,'saved supervision verdict differs');return dict(schema='A23-supervisor-analysis-1',archive_integrity_valid=True,supervision_complete=complete,hello_consistent=r['hello_consistent'],child_execution_policy_pass=r['child_execution_policy_pass'],timed_out=r['timed_out'],truncated=r['truncated'],failure_reasons=r['failure_reasons'],**FALSE)

if __name__=='__main__':
    import argparse,json
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('archive',type=Path);p.add_argument('--build',type=Path,required=True);v=p.parse_args()
    try:r=analyze(v.archive,v.build)
    except (ValueError,OSError,KeyError,TypeError) as e:print(json.dumps(dict(archive_integrity_valid=False,error=str(e))));raise SystemExit(2)
    print(json.dumps(r,indent=2))
