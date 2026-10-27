"""Read-only saved69/two-epoch preview. No issue/acquire/reserve command exists."""
import argparse,json
from a23_two_epoch_baseline69 import adoption
from a23_sequence32_model import encode,sha

def preview():
    a=adoption();material=dict(schema='A23-sequence32-model-materials-1',baseline_manifest_sha256=a['snapshot']['manifest_sha256'],
        baseline_inventory_sha256=a['inventory_sha256'],workflow_source_sha256=sha(encode(a['source_hashes'])),build_manifest_sha256=a['build']['manifest_sha256'],
        receiver_sha256=a['receiver_sha256'],first_sequence=81,last_sequence=112,model_only=True,hardware_entry_enabled=False)
    return dict(schema='A23-two-epoch-saved69-preview-1',baseline=a,model_materials=material,first_sequence=81,last_sequence=112,sequence_count=32,
        remaining=0,record_written=False,sequence_reserved=False,acquisition_enabled=False,formal_issuance_available=False,
        production_permit_implemented=False,acquisition_mode_implemented=False,device_dual_epoch_reuse_established=False,
        blockers=['production permit and acquisition CLI not implemented','device dual-epoch package reuse not established','new hardware test not authorized'],
        usb_requests=0,sd_accesses=0,formal_records=0,formal_reservations=0,receiver_launched=False)

if __name__=='__main__':
    argparse.ArgumentParser(description=__doc__).parse_args();print(json.dumps(preview(),indent=2))
