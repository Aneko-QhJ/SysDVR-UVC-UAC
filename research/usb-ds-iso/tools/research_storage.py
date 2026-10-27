#!/usr/bin/env python3
"""Lossless cold storage for explicitly selected offline research directories.

Independent of the frozen experiment imports. No USB, SDK, ticket or Git writes.
Packing retains the original; pruning requires a verified restore rehearsal.
Run only while the selected directory has no writers or active consumers.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
import zipfile

DEFAULT_ROOT = Path(__file__).resolve().parents[1] / 'private'
MANIFEST = '__storage_manifest__.json'
CHUNK = 1024 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    with Path(path).open('rb') as stream:
        return stream_digest(stream)


def stream_digest(stream):
    result = hashlib.sha256()
    for chunk in iter(lambda: stream.read(CHUNK), b''):
        result.update(chunk)
    return result.hexdigest()


def relative(name):
    p = PurePosixPath(name)
    require(isinstance(name, str) and name and not p.is_absolute() and
            '..' not in p.parts and str(p) == name and '\\' not in name,
            'unsafe archive path')
    return Path(*p.parts)


def canonical(path):
    path = Path(os.path.abspath(path))
    require(path == path.resolve(), 'symlink in path: ' + str(path))
    return path


def file_record(path):
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode), 'not a regular file: ' + str(path))
    result = dict(size=before.st_size, sha256=digest(path),
                  mode=stat.S_IMODE(before.st_mode), mtime_ns=before.st_mtime_ns)
    after = path.lstat()
    require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns),
            'file changed during read: ' + str(path))
    return result


def snapshot(root):
    require(root.is_dir() and not root.is_symlink(), 'source directory missing or linked')
    files, directories = {}, {}
    for parent, dirs, names in os.walk(root, followlinks=False):
        for name in sorted(dirs + names):
            path = Path(parent) / name
            st = path.lstat()
            key = path.relative_to(root).as_posix()
            if stat.S_ISDIR(st.st_mode):
                directories[key] = stat.S_IMODE(st.st_mode)
            else:
                files[key] = file_record(path)
    return files, directories


def check_seals(root, files):
    """Check existing checksum entries without inventing or rewriting a seal."""
    for name in files:
        if Path(name).name != 'SHA256SUMS':
            continue
        base = Path(name).parent
        sums = (root / name).read_bytes()
        for line in sums.decode().splitlines():
            expected, member = line.split('  ', 1)
            require(re.fullmatch('[0-9a-f]{64}', expected), 'invalid checksum')
            key = (base / relative(member)).as_posix()
            require(key in files and files[key]['sha256'] == expected,
                    'sealed file differs: ' + key)
        committed = root / base / 'COMMITTED'
        if committed.exists():
            require(committed.read_bytes() == (hashlib.sha256(sums).hexdigest() + '\n').encode(),
                    'COMMITTED differs: ' + str(committed))


def manifest_bound(root, path):
    for folder in (path.parent, *path.parent.parents):
        if folder != root and root not in folder.parents:
            break
        seal = folder / 'SHA256SUMS'
        if seal.exists():
            names = {line.split('  ', 1)[1] for line in seal.read_text().splitlines()}
            if path.relative_to(folder).as_posix() in names:
                return True
    return False


class Storage:
    def __init__(self, root=DEFAULT_ROOT):
        self.root = canonical(root)
        require(self.root.is_dir(), 'private root missing')
        self.store = canonical(self.root / 'storage')

    def archive(self, name):
        require(re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]*', name) is not None,
                'archive name must be one directory name')
        return self.store / (name + '.zip')

    @contextmanager
    def lock(self):
        self.store.mkdir(exist_ok=True)
        lock = self.store / '.lock'
        lock.mkdir()  # An interrupted operation leaves a visible lock, never auto-steal it.
        try:
            yield
        finally:
            lock.rmdir()

    def write(self, name, source, files, directories, kind):
        archive = self.archive(name)
        require(not archive.exists(), 'archive already exists')
        require(files and MANIFEST not in files, 'empty archive or reserved filename')
        manifest = dict(schema='research-storage-2', kind=kind, source=str(source),
                        root_mode=stat.S_IMODE(source.stat().st_mode),
                        files=files, directories=directories)
        partial = archive.with_suffix('.partial')
        # Keep incomplete archives for diagnosis; never replace an existing one.
        with partial.open('xb') as output:
            with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
                z.writestr(MANIFEST, json.dumps(manifest, sort_keys=True).encode())
                saved = set()
                for member in sorted(files):
                    key = 'objects/' + files[member]['sha256']
                    if key in saved:
                        continue
                    saved.add(key)
                    with (source / member).open('rb') as src, z.open(key, 'w', force_zip64=True) as dst:
                        shutil.copyfileobj(src, dst, CHUNK)
            output.flush()
            os.fsync(output.fileno())
        self.read(partial)
        os.rename(partial, archive)
        fd = os.open(self.store, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        return self.summary(archive, manifest)

    def read(self, archive):
        with zipfile.ZipFile(archive) as z:
            names = z.namelist()
            require(len(names) == len(set(names)), 'duplicate archive member')
            manifest = json.loads(z.read(MANIFEST))
            require(manifest['schema'] in ('research-storage-1', 'research-storage-2') and
                    manifest['kind'] in ('analysis', 'finder'), 'unknown archive schema/kind')
            files = manifest['files']
            for name in manifest['directories']:
                relative(name)
                require(name not in files, 'file/directory collision')
            objects = {}
            for name, record in files.items():
                relative(name)
                require(re.fullmatch('[0-9a-f]{64}', record['sha256']), 'invalid content hash')
                key = self.member(manifest, name)
                if key in objects:
                    require(objects[key]['size'] == record['size'], 'conflicting object size')
                objects[key] = record
            require(set(names) == set(objects) | {MANIFEST}, 'archive inventory differs')
            for key, record in objects.items():
                require(z.getinfo(key).file_size == record['size'], 'archive size differs')
                with z.open(key) as stream:
                    require(stream_digest(stream) == record['sha256'],
                            'archive checksum differs: ' + key)
        return manifest

    @staticmethod
    def member(manifest, name):
        return ('objects/' + manifest['files'][name]['sha256']
                if manifest['schema'] == 'research-storage-2' else name)

    def summary(self, archive, manifest):
        return dict(archive=str(archive), archive_sha256=digest(archive),
                    files=len(manifest['files']),
                    distinct_contents=len({r['sha256'] for r in manifest['files'].values()}),
                    original_bytes=sum(r['size'] for r in manifest['files'].values()),
                    archive_bytes=archive.stat().st_size)

    def pack(self, name):
        self.archive(name)
        source = canonical(self.root / 'analysis' / name)
        with self.lock():
            files, dirs = snapshot(source)
            check_seals(source, files)
            result = self.write(name, source, files, dirs, 'analysis')
            require(snapshot(source) == (files, dirs), 'source changed; retained original')
            return result

    def pack_finder(self, name):
        """Archive only Finder metadata absent from all ancestor checksum manifests."""
        with self.lock():
            files, skipped = {}, []
            for parent, dirs, names in os.walk(self.root, followlinks=False):
                dirs[:] = [n for n in dirs if not (Path(parent) / n).is_symlink()
                           and Path(parent) / n != self.store]
                if '.DS_Store' not in names:
                    continue
                path = Path(parent) / '.DS_Store'
                if manifest_bound(self.root, path):
                    skipped.append(str(path))
                else:
                    files[path.relative_to(self.root).as_posix()] = file_record(path)
            result = self.write(name, self.root, files, {}, 'finder')
            return dict(result, bound_metadata_preserved=skipped)

    def unpack(self, archive, destination):
        manifest = self.read(archive)
        destination = canonical(destination)
        require(not destination.exists(), 'restore destination already exists')
        require(destination.parent.is_dir(), 'restore parent missing')
        with tempfile.TemporaryDirectory(prefix='.restore-', dir=destination.parent) as tmp:
            stage = Path(tmp) / 'tree'
            stage.mkdir()
            with zipfile.ZipFile(archive) as z:
                for name in manifest['directories']:
                    (stage / relative(name)).mkdir(parents=True, exist_ok=True)
                for name, record in manifest['files'].items():
                    path = stage / relative(name)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(self.member(manifest, name)) as src, path.open('xb') as dst:
                        shutil.copyfileobj(src, dst, CHUNK)
                    os.chmod(path, record['mode'])
                    os.utime(path, ns=(record['mtime_ns'], record['mtime_ns']))
                    require(file_record(path) == record, 'restored file differs')
            for name, mode in manifest['directories'].items():
                os.chmod(stage / name, mode)
            os.chmod(stage, manifest['root_mode'])
            require(not destination.exists(), 'restore destination appeared')
            os.rename(stage, destination)
        return manifest

    def restore(self, name, destination=None):
        with self.lock():
            archive = self.archive(name)
            manifest = self.read(archive)
            if destination is None:
                require(manifest['kind'] == 'analysis', 'Finder recovery needs a separate destination')
                destination = self.root / 'analysis' / name
            self.unpack(archive, destination)
            return dict(self.summary(archive, manifest), restored_to=str(destination))

    def prune(self, name):
        with self.lock():
            archive = self.archive(name)
            manifest = self.read(archive)
            expected_source = self.root / 'analysis' / name if manifest['kind'] == 'analysis' else self.root
            require(manifest['source'] == str(expected_source), 'archive belongs to another root/name')
            source = canonical(expected_source)
            # Exercise the real restore path before removing even a single original.
            with tempfile.TemporaryDirectory(prefix='.rehearsal-', dir=self.store) as tmp:
                self.unpack(archive, Path(tmp) / 'restored')
            if manifest['kind'] == 'finder':
                for member, record in manifest['files'].items():
                    path = source / relative(member)
                    require(path.name == '.DS_Store' and self.store not in path.parents and
                            not manifest_bound(source, path), 'not disposable Finder metadata')
                    require(file_record(canonical(path)) == record, 'metadata changed; retained originals')
                for member in manifest['files']:
                    (source / member).unlink()
            else:
                require(snapshot(source) == (manifest['files'], manifest['directories']),
                        'source changed; retained original')
                # The archive is durable and fully restored/checked before this step.
                retired = source.with_name('.' + name + '.pruning')
                require(not retired.exists(), 'unfinished prune exists')
                os.rename(source, retired)
                try:
                    require(snapshot(retired) == (manifest['files'], manifest['directories']),
                            'source changed during retirement')
                except BaseException:
                    os.rename(retired, source)
                    raise
                shutil.rmtree(retired)
            return dict(self.summary(archive, manifest), pruned=True, restore_rehearsal_passed=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--private-root', type=Path, default=DEFAULT_ROOT)
    commands = parser.add_subparsers(dest='command', required=True)
    for command in ('pack', 'pack-finder', 'verify', 'prune', 'restore'):
        sub = commands.add_parser(command)
        sub.add_argument('name')
        if command == 'restore':
            sub.add_argument('--destination', type=Path)
    args = parser.parse_args()
    storage = Storage(args.private_root)
    if args.command == 'pack':
        result = storage.pack(args.name)
    elif args.command == 'pack-finder':
        result = storage.pack_finder(args.name)
    elif args.command == 'prune':
        result = storage.prune(args.name)
    elif args.command == 'restore':
        result = storage.restore(args.name, args.destination)
    else:
        archive = storage.archive(args.name)
        result = storage.summary(archive, storage.read(archive))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
