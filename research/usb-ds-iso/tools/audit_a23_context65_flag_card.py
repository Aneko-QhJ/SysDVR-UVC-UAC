"""Freeze two-stage card adapter models using fake command transport only."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile

import context65_flag_card as adapter
w=adapter.w


def run(output):
    output=w.canonical(output);w.require(not output.exists() and output.parent==w.A,'new card adapter audit required')
    source=adapter.source_hashes();output.mkdir(mode=0o700)
    sys.path.insert(0,str(w.ROOT/'tests'));import test_a23_context65_flag_card as fixture
    cases={}
    with tempfile.TemporaryDirectory(dir='/private/tmp',prefix='a23-flag-card-audit-') as temporary:
        work=Path(temporary).resolve()
        for mode in ('success-renumbered','backup-mount-failure','backup-eject-failure','reinsert-drift',
                     'writable-mount-failure','postcreate-corruption','timeout-before','timeout-after'):
            root=work/mode;card,job,first=fixture.case(root);second=fixture.FakeBackend(card,number=99)
            if mode=='backup-mount-failure':first.fault=lambda c,b:1 if c[1:2]==['mount'] else None
            if mode=='backup-eject-failure':first.keep_mount_on_eject=True
            if mode=='timeout-before':
                def unresolved(c,b):raise adapter.UnresolvedCommand(2777)
                first.fault=unresolved
            if mode=='writable-mount-failure':second.fault=lambda c,b:1 if c[1:-1]==['mount','nobrowse'] else None
            if mode=='postcreate-corruption':second.on_sync=lambda b:(card/adapter.repair.FLAG).write_bytes(b'corrupt')
            if mode=='timeout-after':
                def unresolved_after(c,b):
                    if c==['/bin/sync']:raise adapter.UnresolvedCommand(2888)
                second.fault=unresolved_after
            try:
                adapter.backup(job,repair_authorized=True,shutdown_card_connected=True,_backend=first)
                if mode=='reinsert-drift':(card/'logfile.txt').write_bytes(b'drift after eject')
                adapter.execute(job,repair_authorized=True,shutdown_card_reinserted=True,_backend=second)
                w.require(mode=='success-renumbered','failure case unexpectedly succeeded')
            except (OSError,ValueError):w.require(mode!='success-renumbered','positive adapter failed')
            state=w.load(job/'state.json');expected='complete' if mode=='success-renumbered' else ('unresolved_no_retry' if mode.startswith('timeout-') else 'failed_no_retry')
            w.require(state['stage']==expected and state['actual_card_repaired'] is False,'model state differs')
            target=output/mode;target.mkdir();shutil.copytree(job,target/'job')
            owner=root/'A23-context65-flag-card-volume-owner.json'
            w.require(owner.exists() is (mode!='success-renumbered'),'volume ownership not retained/released correctly')
            if owner.exists():shutil.copyfile(owner,target/'volume-owner.json')
            for name,raw in w.card.selected(card).items():w.card.put(target,'observed-card/'+name,raw)
            if (root/'before').exists():shutil.copytree(root/'before',target/'external-before')
            if (root/'after').exists():shutil.copytree(root/'after',target/'external-after')
            if mode=='success-renumbered':
                value=adapter.analyze(target/'job');w.write(target/'analysis.json',value)
                moved=work/'moved';shutil.copytree(target/'job',moved);w.require(adapter.analyze(moved)==value,'moved adapter archive differs')
                import prepare_a23_context65_once as once
                preview=once.prepare(w.A/'A23-context65-once-card-audit-preview.json',
                    deployment=w.ROOT/'private/deployments/20261016-191203-path-span-window-30s',recovery=root/'after')
                w.require(preview['issuance_available'] is False and preview['record_written'] is False,'model promoted to formal baseline')
                w.write(output/'formal-preview-rejects-model.json',preview)
            else:
                if expected=='unresolved_no_retry':w.require(not (job/'COMMITTED').exists(),'live command job was sealed')
                else:w.card.seal_verify(job)
            cases[mode]=dict(stage=state['stage'],backup_commands=len(first.events),repair_commands=len(second.events),
                job_sealed=(job/'COMMITTED').exists(),model_flag_created=(card/adapter.repair.FLAG).exists(),
                pending_volume_owner=owner.exists(),formal_baseline_accepted=False,real_disk_commands=0)
    for name in adapter.NEW:
        target=output/'source'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(w.plain(w.ROOT/name,2*1024*1024))
    # Local manual, not a disk utility invocation or a media probe.
    manual=Path('/usr/share/man/man8/diskutil.8').read_bytes();(output/'diskutil.8').write_bytes(manual)
    w.require(adapter.source_hashes()==source,'sources changed during adapter audit');w.transition()
    result=dict(schema='A23-context65-flag-card-review-1',passed=True,source_hashes=source,source_count=len(source),case_count=len(cases),
        cases=cases,moved_archive_verified=True,model_baseline_rejected_formally=True,manual_sha256=w.sha(manual),
        formal_records=0,formal_reservations=0,real_sdk_objects=0,usb_requests=0,sd_accesses=0,physical_jobs_executed=0,
        actual_card_repaired=False,remaining=0)
    w.write(output/'audit.json',result);w.b.seal(output);w.card.seal_verify(output);return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path);args=parser.parse_args()
    value=run(args.output);print(json.dumps(dict(sources=value['source_count'],cases=value['case_count'],remaining=0)))
