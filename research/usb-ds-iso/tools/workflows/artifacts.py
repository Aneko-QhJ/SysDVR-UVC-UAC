"""Restore immutable archive inputs without overwriting current experiment state."""
from pathlib import Path
import hashlib
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
PRIVATE = ROOT / 'private'

def archive_path():
    repo = ROOT.parents[1]
    git = Path(subprocess.check_output(['git','rev-parse','--git-common-dir'],cwd=repo,text=True).strip())
    if not git.is_absolute(): git=repo/git
    branch=subprocess.check_output(['git','branch','--show-current'],cwd=repo,text=True).strip()
    name=branch.removeprefix('experiment/')
    if not name or '/' in name or name in ('.','..'):
        raise ValueError('Specify --archive for this branch')
    return git/'experiment-artifacts'/name/'research/usb-ds-iso/private'

def relative_pointer(value):
    marker='/research/usb-ds-iso/private/'
    if marker in value:value=value.split(marker,1)[1]
    p=Path(value)
    if p.is_absolute() or '..' in p.parts:raise ValueError('Archive pointer is outside private')
    return p

def selected_paths(archive, scope):
    capture=['darwin-diag-host64','host-A23-microframe-audit','host-A23-native-guard-serial',
             'packages-A23-interval1','analysis','deployments/latest-A23.txt',
             'runs/latest-A19-run.txt','runs/latest-A23-run.txt','runs/latest-A23-preflight.txt',
             'collections/latest-A23.txt']
    if scope=='patch':return [Path('module/exefs/main')]
    if scope!='capture':raise ValueError('Unknown restore scope')
    paths=[Path(p) for p in capture]
    for pointer in ['deployments/latest-A23.txt','runs/latest-A19-run.txt','runs/latest-A23-run.txt','collections/latest-A23.txt']:
        paths.append(relative_pointer((archive/pointer).read_text().strip()))
    return list(dict.fromkeys(paths))

def restore(archive, destination=PRIVATE, scope='capture', dry_run=False):
    archive=Path(archive).resolve();destination=Path(destination)
    if not archive.is_dir():raise FileNotFoundError('Archive directory missing: '+str(archive))
    paths=selected_paths(archive,scope)
    # Check the complete source selection before creating anything.
    for relative in paths:
        if not (archive/relative).exists():raise FileNotFoundError(str(archive/relative))
    restored=[];kept=[]
    for relative in paths:
        source=archive/relative;target=destination/relative
        if target.exists():kept.append(str(relative));continue
        restored.append(str(relative))
        if dry_run:continue
        target.parent.mkdir(parents=True,exist_ok=True)
        if source.is_dir():shutil.copytree(source,target,symlinks=True)
        else:shutil.copy2(source,target)
    return dict(archive=str(archive),destination=str(destination),scope=scope,dry_run=dry_run,
                restored=restored,existing_preserved=kept,archive_modified=False)

def verify(folder):
    folder=Path(folder);entries=(folder/'SHA256SUMS').read_text().splitlines()
    for line in entries:
        expected,name=line.split('  ',1);relative=Path(name)
        if relative.is_absolute() or '..' in relative.parts:raise ValueError('Unsafe checksum path')
        actual=hashlib.sha256((folder/relative).read_bytes()).hexdigest()
        if actual!=expected:raise ValueError('Checksum mismatch: '+str(folder/relative))
    return dict(folder=str(folder),files=len(entries),sha256_verified=True)
