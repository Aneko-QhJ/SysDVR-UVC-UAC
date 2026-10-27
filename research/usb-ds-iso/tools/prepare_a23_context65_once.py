"""Preview by default; formal issuance needs explicit authorization and fresh receipts."""
import argparse
from pathlib import Path
import re
import uuid
from datetime import datetime,timezone
import context65_workflow as w
import context65_once_reservation as reservation

def destination(path):
    path=w.canonical(path)
    w.require(not path.exists() and path.parent.is_dir() and
        (path.parent==w.A or Path('/private/tmp') in path.parents) and
        re.fullmatch(r'A23-context65-once-[A-Za-z0-9_-]+\.json',path.name),'new context65 record path required')
    return path

def prepare(path,*,issue=False,deployment=None,recovery=None,ledger=reservation.LEDGER):
    w.require(type(issue) is bool,'explicit issue boolean required');path=destination(path)
    path,ledger,model=reservation.location(path,ledger);source,scope=w.materials();w.transition()
    blockers=[];saved_deployment=saved_recovery=None
    if scope['workflow_proof'] is None and not model:blockers.append('workflow proof not published')
    if deployment is None:blockers.append('saved deployment receipt required')
    else:saved_deployment=w.previous.verify_deployment(deployment,scope)
    if recovery is None:blockers.append('fresh recovery after missing boot2.flag required')
    else:
        try:saved_recovery=w.verify_recovery(recovery,scope,simulation=model)
        except (ValueError,OSError,KeyError) as error:
            if issue:raise
            blockers.append(str(error))
    burned=65 in reservation.entries(ledger)
    if burned:blockers.append('65..80 already burned')
    preview=dict(schema='A23-context65-once-preview-1',record_path=str(path),first_sequence=65,last_sequence=80,
        scope=scope,remaining=0,acquisition_enabled=False,record_written=False,sequence_reserved=burned,
        issuance_available=not blockers,blockers=blockers,simulation=model,usb_requests=0,sd_accesses=0)
    if not issue:return preview
    # Explicit issue=True is for a human-authorized future run. This module
    # never repairs a card, starts a receiver or obtains authorization itself.
    w.require(not blockers,'issuance blocked: '+', '.join(blockers));reservation.available(path,ledger)
    record={**source,'record_path':str(path),'preparation_id':str(uuid.uuid4()),'stage':'prepared','remaining':1,'acquisition_enabled':True,
        'issuance':dict(schema='A23-context65-once-issuance-1',issued_at=datetime.now(timezone.utc).isoformat(),
            scope=scope,deployment=saved_deployment,recovery=saved_recovery,reservation=None,maximum_invocations=1,automatic_retry=False)}
    record['issuance']['reservation']=reservation.burn(path,ledger,record)
    w.verify_scope(record,path);w.require(w.materials()==(source,scope),'materials changed during issuance')
    w.write(path,record) # failure leaves the burn, including partial writes
    return {**preview,'schema':'A23-context65-once-issued-1','remaining':1,'acquisition_enabled':True,'record_written':True,
        'sequence_reserved':True,'record_sha256':w.sha(w.plain(path))}

if __name__=='__main__':
    import json
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('record',type=Path);p.add_argument('--issue',action='store_true')
    p.add_argument('--deployment',type=Path);p.add_argument('--recovery',type=Path);a=p.parse_args()
    print(json.dumps(prepare(a.record,issue=a.issue,deployment=a.deployment,recovery=a.recovery),indent=2))
