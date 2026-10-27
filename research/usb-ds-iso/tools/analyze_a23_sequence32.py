"""Read-only analysis of copied disposable32 model evidence; no authority granted."""
import argparse,json
from pathlib import Path
import a23_sequence32_model as m

def analyze(root,scope):
    root=Path(root);cap,materials,h,names=m.inspect(root)
    m.require(type(scope) is dict and scope.get('schema')=='A23-two-epoch-saved69-preview-1' and scope.get('formal_issuance_available') is False,'saved69 preview required')
    m.require(m.encode(materials)==m.encode(scope['model_materials']) and m.encode(h)==m.encode(scope['baseline']['history']),'model scope differs')
    m.checked_selection(root)
    expected=m.BASE|m.OPTIONAL;m.require(names==expected,'model chain inventory incomplete')
    for name in ('consume-attempt','process-attempt','selection-attempt'):m.require(m.read(root/name)==b'one attempt\n','attempt marker differs')
    m.require(m.read(root/'.lock')==b'','lock content differs')
    return dict(schema='A23-sequence32-model-analysis-1',supplied_model_chain_complete=True,first_sequence=81,last_sequence=112,
        reserved_sequences=32,reservation_files=1,maximum_model_invocations=1,remaining=0,simulation=True,model_only=True,
        baseline_manifest_sha256=materials['baseline_manifest_sha256'],materials_sha256=cap['materials_sha256'],
        process_origin_authenticated=False,formal_issuance_available=False,formal_records=0,formal_reservations=0,
        receiver_launched=False,hardware_entry_enabled=False,hardware_verified=False,usb_requests=0,sd_accesses=0)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);p.add_argument('--preview',type=Path,required=True);args=p.parse_args();print(json.dumps(analyze(args.directory,m.load(args.preview)),indent=2))
