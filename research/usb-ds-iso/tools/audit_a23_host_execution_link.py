#!/usr/bin/env python3
"""Audit a dormant IOKit adapter and supplied EXE3 collections, offline only."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

import collect_a23_execution_v3 as collection
from workflows.artifacts import verify

ROOT=Path(__file__).resolve().parents[1];REPO=ROOT.parents[1]
SEALED=ROOT/'private/analysis/A23-execution-v3-candidate-review-20261015'
VALIDATED=SEALED.parent/'A23-execution-v3-candidate-validation-20261015'
HISTORICAL=ROOT/'private/runs/A-A23-HS-IOUSBHost-burst-20261013-090224-3c3789da'
INPUTS=('host/a23_passive_wait_adapter.h','host/a23_passive_wait_adapter.c','host/a23_passive_wait_iokit.c',
        'tests/a23_passive_wait_adapter_fixture.c','tools/collect_a23_execution_v3.py',
        'tools/audit_a23_host_execution_link.py','tests/test_a23_host_execution_link.py')
MODES=('ok','existing','initial-flood','create-error','matching-error','early-callback',
    'invalid-initial-before','invalid-initial-after','invalid-arrival-before','invalid-arrival-after',
    'bad-identity','zero-identity','same-parent','wrong-speed','identity-changed-watch','identity-changed-take',
    'interest-error','detach-during-watch','deadline-in-drain','deadline-after-watch','deadline-before-take',
    'timeout','clock-backwards','pump-error','bad-pump-result','message-flood','wrong-iterator',
    'detach-before-take','close-before-take','extra-arrival','detach-after-take','second-take',
    'journal-begin','journal-registered','journal-waiting','journal-selected','journal-handoff','journal-stop',
    'stop-waiting','stop-selected','stop-handoff','reentrant-poll',
    'release-service-error','release-iterator-error','release-interest-error','release-all-error','release-all-extra-arrival')


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def adapter(output,compiler,sdk):
    binary=output/'injected-adapter'
    command=[compiler,'-isysroot',str(sdk),'-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
        '-I'+str(ROOT/'host'),str(ROOT/'host/a23_passive_wait_adapter.c'),str(ROOT/'host/a23_passive_wait_iokit.c'),
        str(ROOT/'tests/a23_passive_wait_adapter_fixture.c'),'-framework','CoreFoundation','-framework','IOKit','-o',str(binary)]
    subprocess.run(command,check=True,capture_output=True,text=True)
    rows=[]
    cases=list(dict.fromkeys([(mode,1) for mode in MODES]+[('ok',n) for n in range(67)]))
    directory=output/'notifications';directory.mkdir()
    for mode,n in cases:
        p=subprocess.run([str(binary),mode,str(n)],check=True,capture_output=True,text=True)
        row=json.loads(p.stdout);rows.append(row)
        (directory/f'{mode}-batch{n}.json').write_text(json.dumps(row,indent=2)+'\n')
    return rows,command


def collections(output):
    directory=output/'collections';directory.mkdir()
    def file(name):return SEALED/name
    examples=[('normal',HISTORICAL/'host',file('normal-primary-ok-execution-ok.execution.bin'),
               file('normal-primary-ok-execution-ok.primary.disk.bin'),'03'+'00'*31),
              ('primary-commit-failed',HISTORICAL/'host',file('diagnostic-primary-commit-error-execution-ok.execution.bin'),
               file('diagnostic-primary-commit-error-execution-ok.primary.disk.bin'),'03'+'00'*31),
              ('primary-partial',HISTORICAL/'host',file('normal-primary-silent-short-write-execution-ok.execution.bin'),
               file('normal-primary-silent-short-write-execution-ok.primary.disk.bin'),'03'+'00'*31),
              ('execution-partial',HISTORICAL/'host',file('normal-primary-ok-execution-write-error.execution.disk.bin'),
               None,'03'+'00'*31),
              ('wrong-recipe',HISTORICAL/'host',file('normal-primary-ok-execution-ok.execution.bin'),None,'04'+'00'*31)]
    incomplete=output/'incomplete-host';incomplete.mkdir()
    (incomplete/'session.jsonl').write_bytes((HISTORICAL/'host/session.jsonl').read_bytes()[:120])
    (incomplete/'failure-note.txt').write_text('Injected partial host copy; no receiver or device operation.\n')
    examples.append(('host-partial',incomplete,file('normal-primary-ok-execution-ok.execution.bin'),None,'03'+'00'*31))
    rows={}
    for name,host,execution,primary,recipe in examples:
        rows[name]=collection.freeze(host,execution,directory/name,recipe,primary)
    return rows


def run(output):
    output=Path(output).resolve()
    if output.exists():raise ValueError('Refusing existing output: '+str(output))
    seals=[verify(p) for p in (SEALED,VALIDATED,HISTORICAL)]
    old=json.loads((SEALED/'audit.json').read_text())
    for name,expected in old['source_hashes'].items():
        if sha(ROOT/name)!=expected:raise ValueError('Prior source drift: '+name)
    production={n:sha(REPO/n) for n in old['production_sources_sha256']}
    tickets={n:sha(SEALED.parent/n) for n in old['tickets_sha256']}
    if production!=old['production_sources_sha256'] or tickets!=old['tickets_sha256']:
        raise ValueError('Protected source/ticket drift')
    names=list(dict.fromkeys([*old['source_hashes'],*INPUTS]))
    sources={n:sha(ROOT/n) for n in names}
    sdk=Path(subprocess.run(['xcrun','--show-sdk-path'],check=True,capture_output=True,text=True).stdout.strip())
    header_paths=['System/Library/Frameworks/IOKit.framework/Headers/'+s for s in
                  ('IOKitLib.h','IOKitKeys.h','IOMessage.h','OSMessageNotification.h','usb/IOUSBHostFamilyDefinitions.h')]
    header_paths+=['usr/include/mach/message.h']
    headers={str(sdk/n):sha(sdk/n) for n in header_paths}
    compiler=subprocess.run(['xcrun','-f','clang'],check=True,capture_output=True,text=True).stdout.strip()
    external={compiler:sha(compiler)}
    output.mkdir(parents=True)
    try:rows,command=adapter(output,compiler,sdk)
    except subprocess.CalledProcessError as error:
        (output/'native-failure.txt').write_text((error.stdout or '')+(error.stderr or ''));raise
    supplied=collections(output)
    for group,base in ((sources,ROOT),(production,REPO),(tickets,SEALED.parent)):
        if group!={n:sha(base/n) for n in group}:raise ValueError('Source changed during audit')
    if headers!={n:sha(n) for n in headers} or external!={n:sha(n) for n in external}:
        raise ValueError('Compiler/SDK drift')
    for p in (SEALED,VALIDATED,HISTORICAL):verify(p)
    for name in names:
        p=output/'inputs'/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,p)
    result=dict(schema='A23-host-execution-link-1',source_hashes=sources,production_sources_sha256=production,
        tickets_sha256=tickets,sealed_inputs=seals,compiler_command=command,compiler_sha256=external,sdk_headers_sha256=headers,
        compiler_version=subprocess.run([compiler,'--version'],check=True,capture_output=True,text=True).stdout,
        notification_cases=rows,notification_case_count=len(rows),collections=supplied,
        original_host_and_device_models_deliberately_unrelated=True,
        native_iokit_bindings_compiled_and_linked=True,native_iokit_bindings_executed=False,
        synchronous_callouts_only=True,capture_entry_integrated=False,receiver_invoked=False,
        usb_accessed=False,sd_accessed=False,attempt_issued=False,hardware_verified=False,root_cause_confirmed=False)
    (output/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    (output/'SHA256SUMS').write_text(''.join(sha(p)+'  '+str(p.relative_to(output))+'\n'
        for p in sorted(output.rglob('*')) if p.is_file()))
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    print(json.dumps(run(args.output),indent=2))


if __name__=='__main__':main()
