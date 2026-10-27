#!/usr/bin/env python3
"""Preview one quiet diagnostic; --issue creates a new record after user authorization.

No device access, card access, receiver launch, ticket refill, or implicit retry.
The original offline record and all sealed review trees remain unchanged.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import uuid

import build_a23_quiet_deployment as package
import build_a23_quiet_receiver as build
from workflows import capture_a23_quiet_receiver as gate

ANALYSIS = package.ANALYSIS
OFFLINE = ANALYSIS/'A23-quiet-receiver-review-20261015/offline-record.json'
VALIDATION = ANALYSIS/'A23-quiet-receiver-validation-20261015'
PACKAGE = ANALYSIS/'A23-quiet-deployment-review-20261016'


def destination(path):
    path = Path(path)
    build.require(path.is_absolute() and path == path.resolve() and not path.exists(), 'new canonical record required')
    build.require(path.parent == ANALYSIS or Path('/private/tmp') in path.parents, 'record must be outside sealed review trees')
    build.require(path.parent.is_dir() and re.fullmatch(r'A23-quiet-once-[A-Za-z0-9_-]+\.json', path.name),
                  'new A23-quiet-once record name required')
    return path


def materials():
    source = build.load(OFFLINE)
    build.require(source.get('stage') == 'offline_build_ready' and type(source.get('remaining')) is int and
                  source['remaining'] == 0 and source.get('acquisition_enabled') is False, 'offline source is not dormant')
    build.verify_build(source)
    checked = package.verify_review(PACKAGE)
    report = build.load(PACKAGE/'package-report.json')
    build.require(report['device_binding'] == source['device_binding'] and
                  report['device_binding_sha256'] == source['device_binding_sha256'], 'package/receiver mismatch')
    validation_hash = build.sha(build.plain(VALIDATION/'SHA256SUMS'))
    candidate = {**source, 'validation_directory': str(VALIDATION), 'validation_manifest_sha256': validation_hash}
    gate.verify_validation(candidate)
    return source, dict(package_directory=str(PACKAGE), package_manifest_sha256=checked['manifest_sha256'],
        exefs_nsp_sha256=report['exefs_nsp_sha256'], device_binding_sha256=source['device_binding_sha256'],
        runtime_recipe_sha256=source['recipe_sha256'], receiver_sha256=source['receiver_sha256'],
        build_manifest_sha256=source['build_manifest_sha256'], validation_directory=str(VALIDATION),
        validation_manifest_sha256=validation_hash, offline_source_sha256=build.sha(build.plain(OFFLINE)),
        deployment_files=report['deployment_files'], plan=source['plan'])


def prepare(path, *, issue=False):
    """The caller must obtain human authorization before selecting issue=True."""
    path = destination(path)
    source, scope = materials()
    preview = dict(schema='A23-quiet-once-preview-1', record_path=str(path), scope=scope,
        remaining=0, acquisition_enabled=False, attempt_issued=False, record_written=False,
        receiver_launched=False, hardware_verified=False, device_requests=0, sd_accesses=0,
        maximum_invocations=1, automatic_retry=False,
        site_conditions='fresh CFW start after host WAITING; controlled shutdown before read-only recovery',
        physical_site_verified=False)
    if not issue:
        return preview
    build.require(type(issue) is bool, 'issue must be explicit boolean')
    record = {**source, 'stage': 'prepared', 'remaining': 1, 'acquisition_enabled': True,
        'preparation_id': str(uuid.uuid4()), 'validation_directory': scope['validation_directory'],
        'validation_manifest_sha256': scope['validation_manifest_sha256'],
        'issuance': dict(schema='A23-quiet-once-issuance-1', issued_at=datetime.now(timezone.utc).isoformat(),
            scope=scope, maximum_invocations=1, automatic_retry=False)}
    gate.prepared(record, build.REPO)
    build.require(materials() == (source, scope), 'materials changed before issuance')
    build.write(path, record)  # O_EXCL/O_NOFOLLOW: never overwrite or refill, including after partial failures.
    return {**preview, 'schema': 'A23-quiet-once-issued-1', 'remaining': 1, 'acquisition_enabled': True,
        'attempt_issued': True, 'record_written': True, 'record_sha256': build.sha(build.plain(path))}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('record', type=Path)
    parser.add_argument('--issue', action='store_true', help='create exactly one new record; only after explicit user authorization')
    args = parser.parse_args()
    print(json.dumps(prepare(args.record, issue=args.issue), indent=2))
