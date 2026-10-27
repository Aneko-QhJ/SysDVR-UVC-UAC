#!/usr/bin/env python3
"""Exercise the entry's file-only modes and injected runtime persistence."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import unittest
import uuid

from analyze_a23_short24_session import analyze
from build_a23_short24_candidate import verify_tree

ROOT=Path(__file__).resolve().parents[1]
A=ROOT/'private/analysis'
MODELS=A/'A23-short24-audit-20261027-r4'
SDK=A/'A23-short24-sdk-20261027-r5'


def sha(raw):return hashlib.sha256(raw).hexdigest()
def require(v,m):
    if not v:raise ValueError(m)
def inventory(root):return {p.relative_to(root).as_posix():sha(p.read_bytes()) for p in root.rglob('*') if p.is_file()} if root.exists() else None


def run(entry,output):
    entry,output=entry.resolve(),output.resolve();require(not output.exists(),'fresh audit output required')
    binding=json.loads((entry/'build.json').read_text())
    for n,h in binding['source_hashes'].items():require(sha((ROOT/n).read_bytes())==h,'entry source drift: '+n)
    require(sha((entry/'short24-receiver').read_bytes())==binding['receiver_sha256'],'receiver drift')
    parents={str(p):verify_tree(p) for p in (SDK,MODELS)}
    scope=ROOT/'private/short24-once';scope_before=inventory(scope)
    output.mkdir(parents=True);commands=[]
    def command(args,expected=0):
        args=[str(x) for x in args];commands.append(args)
        p=subprocess.run(args,capture_output=True,text=True)
        with (output/'commands.log').open('a') as f:f.write(p.stdout+p.stderr)
        require(p.returncode==expected,'command returned '+str(p.returncode)+': '+str(args[:2]))
        return p.stdout
    binary=entry/'short24-receiver'
    description=json.loads(command([binary,'--describe']))
    prototype={k:description[k] for k in ('recipe','package_manifest_sha256','nsp_sha256','ips_sha256','baseline_manifest_sha256',
                                        'first_sequence','last_sequence','max_bursts')}
    prototype.update(schema='A23-short24-once-authorization-1',nonce='00000000-0000-4000-8000-000000000024',
        receiver_sha256=binding['receiver_sha256'],model_only=True,human_authorized=False,
        deployment_readback_verified=False,power_off_sd_installed_usb_confirmed=False)
    model=output/'MODEL-authorization.json';model.write_text(json.dumps(prototype))
    checked=json.loads(command([binary,'--check-authorization',model]))
    require(checked['model_only'] is True and checked['claimed'] is False and checked['device_accessed'] is False,'model checker claims authority')
    blocked=ROOT/'private/runs'/('A-MODEL-NOT-CREATED-'+str(uuid.uuid4()))
    command([binary,'--acquire-once',model,blocked],2)
    require(not blocked.exists(),'model authorization created a run')
    refusals=[]
    changes=[('old-schema','schema','A23-waiting-receiver-record-4'),('spent-range','first_sequence',465),
             ('wrong-receiver','receiver_sha256','0'*64),('wrong-package','package_manifest_sha256','0'*64),
             ('wrong-ips','ips_sha256','0'*64),('wrong-recipe','recipe','0'*64),('boolean-count','max_bursts',True),
             ('bad-nonce-type','nonce',{}),('integer-model','model_only',1),('false-readiness-as-human','model_only',False)]
    for name,key,value in changes:
        bad={**prototype,key:value};path=output/('MODEL-'+name+'.json');path.write_text(json.dumps(bad))
        command([binary,'--check-authorization',path],2);refusals.append(name)
    require(inventory(scope)==scope_before,'file-only tests changed formal range claims')
    flags=['-std=gnu11','-fobjc-arc','-fblocks','-Wall','-Wextra','-Werror','-Wno-deprecated-declarations',
           '-mmacosx-version-min=26.4','-fsanitize=address,undefined']
    command(['clang',*flags,ROOT/'host/a23_short24_capture.m',ROOT/'host/a23_short24_runtime.m',
             ROOT/'tests/a23_short24_runtime_fixture.m','-framework','Foundation','-framework','IOKit','-framework','IOUSBHost',
             '-o',output/'runtime-fixture'])
    cases=output/'cases';cases.mkdir()
    native=json.loads(command([output/'runtime-fixture',MODELS,cases,description['recipe']]))
    partial=output/'partial-write';partial.mkdir()
    partial_result=json.loads(command([output/'runtime-fixture','--partial-write',partial]))
    ex=(SDK/'MODEL-execution.bin').read_bytes();primary=(SDK/'MODEL-primary.bin').read_bytes()

    class PersistenceTests(unittest.TestCase):
        def test_observations_are_sealed_and_relation_remains_conditional(self):
            for name in ('complete','late-duplicate','notice-capacity','notice-write-failure'):
                verify_tree(cases/name/'observation')
                result=analyze(cases/name/'observation',ex,primary,description['recipe'])
                self.assertTrue(result['supplied_device_relation_consistent'])
                self.assertFalse(result['hardware_verified'])
                self.assertFalse(result['process_exit_authorized'])

        def test_late_fault_does_not_rewrite_historical_observation(self):
            root=cases/'late-duplicate'
            old=json.loads((root/'observation/metadata.json').read_text())
            later=json.loads((root/'later-0001.json').read_text())
            self.assertTrue(old['observation_complete'])
            self.assertFalse(old['stopped'])
            self.assertTrue(later['capture']['stopped'])
            self.assertEqual(later['capture']['iso_callbacks'],2)

        def test_failure_and_pending_keep_resources_without_retry(self):
            for name in ('existing-intent','existing-observation','pending','notice-write-failure'):
                state=json.loads((cases/name/'runtime-result.json').read_text())
                self.assertTrue(state['holding_runtime_resources'])
                self.assertFalse(state['process_exit_authorized'])
            state=json.loads((cases/'pending/runtime-result.json').read_text())
            self.assertTrue(state['capture']['io_unresolved'])
            self.assertEqual(state['capture']['abort_attempts'],1)
            self.assertEqual((cases/'existing-observation/observation/keep').read_bytes(),b'PRESERVE')

        def test_partial_write_does_not_create_committed_evidence(self):
            self.assertEqual(partial_result['partial_file_bytes_retained'],16)
            self.assertFalse(partial_result['saved'])
            self.assertFalse((partial/'observation/COMMITTED').exists())

        def test_later_attempts_and_commits_are_distinct_and_bounded(self):
            failed=json.loads((cases/'notice-write-failure/runtime-result.json').read_text())
            self.assertEqual((failed['later_attempts'],failed['later_records']),(1,0))
            self.assertEqual((cases/'notice-write-failure/later-0001.json').read_bytes(),b'PRESERVE')
            full=json.loads((cases/'notice-capacity/runtime-result.json').read_text())
            self.assertEqual((full['later_attempts'],full['later_records']),(8,8))
            self.assertTrue(full['later_write_failed'])
            self.assertFalse((cases/'notice-capacity/later-0009.json').exists())

    stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PersistenceTests))
    (output/'tests.log').write_text(stream.getvalue())
    require(result.wasSuccessful() and not result.skipped,'persistence checks failed')
    new=['tests/a23_short24_runtime_fixture.m','tests/a23_short24_installer_fixture.c','tools/audit_a23_short24_entry.py']
    report=dict(schema='A23-short24-entry-offline-audit-1',entry_build_sha256=sha((entry/'build.json').read_bytes()),
        parent_seals=parents,source_hashes={**binding['source_hashes'],**{n:sha((ROOT/n).read_bytes()) for n in new}},
        commands=commands,model_authorization_checked_not_consumed=True,authorization_refusals=refusals,
        native_runtime_scenarios=native['runtime_scenarios'],partial_write_bytes_retained=16,
        persistence_checks_passed=result.testsRun,formal_scope_unchanged=True,real_authorization_issued=False,
        sdk_objects_created=0,usb_operations=0,sd_accesses=0,hardware_verified=False,process_exit_authorized=False)
    (output/'report.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--entry',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();r=run(args.entry,args.output)
    print(json.dumps({k:r[k] for k in ('native_runtime_scenarios','persistence_checks_passed','sdk_objects_created')}))
