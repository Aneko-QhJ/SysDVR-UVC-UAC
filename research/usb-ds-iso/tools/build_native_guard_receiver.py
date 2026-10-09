#!/usr/bin/env python3
"""Build a serial receiver gated by exact native evidence before each resubmit."""
from pathlib import Path
import hashlib,json,shutil,subprocess
ROOT=Path(__file__).resolve().parents[1];P=ROOT/'private'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
CHANGES=[
('#include "iso_probe_protocol.h"','#include "iso_probe_protocol.h"\n#include "native_file_guard.h"'),
('    done = true;\n}', '''    unsigned native_records=0,native_payloads=0;
    bool native_pass=native_file_guard(transfer,&native_records,&native_payloads);
    fprintf(logfile,"{\\"kind\\":\\"native_serial_gate\\",\\"sequence\\":%u,\\"records\\":%u,\\"payloads\\":%u,\\"passed\\":%s,\\"raw_saved\\":%s}\\n",
            sequence,native_records,native_payloads,native_pass?"true":"false",saved?"true":"false");
    fflush(logfile);
    payload_ok = payload_ok && native_pass && saved;
    done = true;
}'''),
('n > 65535','n > 16'),('repeat must be 1..65535','repeat must be 1..16'),
('        fprintf(logfile, "{\\"kind\\":\\"result\\",\\"sequence\\":%u,\\"iso_payload_verified\\":%s,"',
'''        IsoProbeBurstContextDiagnostics burst_diag;
        memcpy(&burst_diag,&state.diagnostics,sizeof(burst_diag));
        complete = complete && burst_mode && burst_diag.magic==ISO_PROBE_BURST_INTERVAL_MAGIC &&
                   burst_diag.completed_bitmap==0xffff && burst_diag.actual_sum==3072;
        fprintf(logfile, "{\\"kind\\":\\"result\\",\\"sequence\\":%u,\\"iso_payload_verified\\":%s,"''')]
def patch(text):
    before=text
    for old,new in CHANGES:
        assert text.count(old)==1,repr(old)
        text=text.replace(old,new)
    restored=text
    for old,new in reversed(CHANGES):
        assert restored.count(new)==1
        restored=restored.replace(new,old)
    assert restored==before
    return text

def main():
    old=P/'host-A23-microframe-audit';meta=json.loads((old/'manifest.json').read_text())
    assert sha(old/'receiver-source.c')==meta['receiver_source_sha256']=='7f9ad70b3c868e86edd1e8a41bea72e2c349bad8e5073526e6d4214f93e4adc7'
    backend=old/'libusb-1.0.30/libusb';lib=backend/'.libs/libusb-1.0.a'
    assert sha(lib)==meta['static_library_sha256']=='b0824021985a1babfc289e37db75ee040583bff5e92eddc3b9e2a5e0d7b948a1'
    out=P/'host-A23-native-guard-serial';out.mkdir(exist_ok=False)
    (out/'receiver-source.c').write_text(patch((old/'receiver-source.c').read_text()))
    for f in ['iso_probe_protocol.h','summarize_run.py']:shutil.copyfile(old/f,out/f)
    shutil.copyfile(ROOT/'host/native_file_guard.h',out/'native_file_guard.h')
    cmd=['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-DISO_NATIVE_DIAGNOSTICS','-I'+str(backend),'-I'+str(out),str(out/'receiver-source.c'),str(lib),'-framework','IOKit','-framework','CoreFoundation','-framework','Security','-lobjc','-o',str(out/'iso-probe-native-diag')]
    with (out/'build.log').open('w') as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True)
    meta.update(host_revision='native-guard-serial-1',hardware_verified=False,receiver_source_sha256=sha(out/'receiver-source.c'),receiver_sha256=sha(out/'iso-probe-native-diag'),native_guard_header_sha256=sha(out/'native_file_guard.h'),repeats=16,max_repeats=16,library=str(lib),native_evidence_mandatory=True,receiver_inverse_patch_matches_reference=True,callback_reads_local_evidence=True,backend_unchanged=True,build_command=cmd)
    (out/'manifest.json').write_text(json.dumps(meta,indent=2)+'\n');print(out)
if __name__=='__main__':main()
