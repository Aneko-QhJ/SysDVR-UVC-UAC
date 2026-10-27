#!/usr/bin/env python3
"""Memory-only startup/EP0 correlation prototype; no firmware/FS integration."""
import argparse,hashlib,json
from pathlib import Path
import build_a23_startup_candidate as startup
from analyze_ep0_session import decode_session
from analyze_ep0_startup import decode_startup
from workflows.artifacts import verify
base=startup.base;ROOT=startup.ROOT
SEALED=base.ep0.PRIVATE/'analysis/A23-startup-candidate-review-20261014'
BOUNDED=base.ep0.PRIVATE/'analysis/A23-bounded-candidate-review-20261014'
INPUTS=('device/ep0_session_capture.h','tools/analyze_ep0_session.py','tools/build_a23_session_correlation.py','tests/ep0_session_policy_test.c')
r=base.trace.replace

def native_source(label,recipe):
    s=(BOUNDED/(label+'-session.c')).read_text()
    old=(BOUNDED/label/'source/uvc/ep0_candidate_recipe.h').read_text()
    s=r(s,old,startup.journal.startup.sink.bounded.recipe_header(recipe))
    setup='''#include "research/usb-ds-iso/device/ep0_session_capture.h"
static Ep0StartupJournal startup_journal;static Ep0SessionContext context;
static Ep0SessionWork work;static uint8_t envelope[EP0_REL_MAX];static Ep0SaveReceipt receipt;
'''
    s=r(s,'static void VideoStreamThread(void* arg)',setup+'static void VideoStreamThread(void* arg)')
    s=r(s,'    Ep0CandidateWindow window={0};',
        '    assert(ep0_session_publish(&context,22,writer,boot_nonce,session_nonce,ep0CandidateRecipe));\n    Ep0CandidateWindow window={0};')
    s=r(s,'    VideoStreamThread(NULL);',
        '    /* Synthetic minimal startup journal in this native correlation model. */\n'
        '    assert(ep0_startup_init(&startup_journal,22,ep0CandidateRecipe));\n'
        '    assert(ep0_startup_record(&startup_journal,22,EP0_I_SM_INIT,EP0_I_CALL,0));\n'
        '    assert(ep0_startup_record(&startup_journal,22,EP0_I_SM_INIT,EP0_I_RESULT,0));\n'
        '    assert(ep0_startup_seal(&startup_journal,22));\n    VideoStreamThread(NULL);')
    s=r(s,'    printf("{\\"case\\":',
        '''    Ep0SinkState saved={0};
    if(diagnostic) {
        /* Save outcome is injected here; the envelope does not perform FS IO. */
        saved=(Ep0SinkState){.phase=EP0_SINK_ACKNOWLEDGED,.attempted=true,.file_may_exist=true,.content_verified=true,.commit_acknowledged=true,.verified_bytes=diagnostic};
        assert(ep0_save_receipt_publish(&receipt,true,&saved,bytes,diagnostic));
    }
    const Ep0TraceOwner *capture_owner=(v || a) ? (void*)1:o;
    const Ep0GuardObservation *capture_guard=(v || a) ? (void*)1:g;
    const Ep0AdmissionObservation *capture_admission=(v || a) ? (void*)1:admission;
    const Ep0SaveReceipt *capture_receipt=(v || a) ? (void*)1:&receipt;
    size_t correlated=ep0_session_capture(&startup_journal,&context,2,0,ep0CandidateRecipe,true,v,a,22,
        capture_owner,capture_guard,capture_admission,true,capture_receipt,&work,envelope,sizeof(envelope));assert(correlated);
    assert(!memcmp(o,&before,sizeof(before)) && !memcmp(g,&guard_before,sizeof(guard_before)));
    char path[1024];assert(strlen(argv[2])+5<sizeof(path));snprintf(path,sizeof(path),"%s.rel",argv[2]);
    FILE *file=fopen(path,"wb");assert(file);assert(fwrite(envelope,1,correlated,file)==correlated);assert(!fclose(file));
    printf("{\\"case\\":''')
    # Replacement above preserves the rest of the exact old printf format.
    return s

def run(output):
    output=Path(output);sealed=verify(SEALED);bounded=verify(BOUNDED);old=json.loads((SEALED/'audit.json').read_text())
    source_audit=base.owner.source_audit();assert source_audit==old['source_audit']
    tickets={n:base.ep0.sha(base.ep0.PRIVATE/'analysis'/n) for n in base.owner.TICKETS};assert tickets==old['tickets_sha256']
    names=list(dict.fromkeys([*old['source_hashes'],*INPUTS]));inputs={n:base.ep0.sha(ROOT/n) for n in names}
    for n,h in old['source_hashes'].items():
        if inputs[n]!=h:raise ValueError('Dependency drift: '+n)
    production={n:base.ep0.sha(startup.startup.REPO/n) for n in startup.startup.PRODUCTION};assert production==old['production_sources_sha256']
    info=dict(source_sha256=inputs,startup_candidate_manifest_sha256=base.ep0.sha(SEALED/'SHA256SUMS'),bounded_manifest_sha256=base.ep0.sha(BOUNDED/'SHA256SUMS'),memory_only=True)
    digest=hashlib.sha256(json.dumps(info,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    (output/'recipe.json').write_text(json.dumps(dict(input_digest=digest,inputs=info),indent=2)+'\n')
    commands=[]
    flags=['-DISO_PROBE','-DISO_PROBE_BURST_MODE','-DISO_PROBE_EVENT_AUDIT','-DISO_PROBE_CONTEXT_AUDIT','-DISO_PROBE_FOLLOWUP_SIA']
    for label in ('dormant','window-30s'):
        file=output/(label+'.c');file.write_text(native_source(label,digest));commands.append(base.trace.compile_native(file,output/label,flags))
    rows=[];previous={r['case']:r for r in json.loads((BOUNDED/'audit.json').read_text())['cases']}
    for case in startup.journal.startup.sink.bounded.session.CASES:
        label='window-30s' if case=='window-wait' else 'dormant'
        path=output/(case+'.diagnostic.bin');normal=output/(case+'.ownership.bin')
        row=json.loads(base.owner.command([str(output/label),case,str(path),str(normal)]))
        expected={k:v for k,v in previous[case].items() if k not in ('candidate_recipe_digest','diagnostic','ownership')};assert row==expected
        rel=Path(str(path)+'.rel');decoded=decode_session(rel.read_bytes(),digest)
        (output/(case+'.session.json')).write_text(json.dumps(decoded,indent=2)+'\n');row['session']=decoded;rows.append(row)
    policy=output/'session-policy';commands.append(base.trace.compile_native(ROOT/'tests/ep0_session_policy_test.c',policy,[]))
    policies=json.loads(base.owner.command([str(policy),str(output/'policy')]))
    for path in sorted(output.glob('policy-*.bin')):
        decoded=decode_session(path.read_bytes());path.with_suffix('.json').write_text(json.dumps(decoded,indent=2)+'\n')
    arm=output/'session-arm.c';arm.write_text('#include "ep0_session_capture.h"\nsize_t session_copy(const Ep0StartupJournal *j,const Ep0SessionContext *c,unsigned st,uint32_t rc,const uint8_t r[32],bool want,uint32_t v,uint32_t a,uint64_t e,const Ep0TraceOwner *o,const Ep0GuardObservation *g,const Ep0AdmissionObservation *ad,bool done,const Ep0SaveReceipt *s,Ep0SessionWork *w,uint8_t *b,size_t n) { return ep0_session_capture(j,c,st,rc,r,want,v,a,e,o,g,ad,done,s,w,b,n); }\n')
    cmd=['/opt/devkitpro/devkitA64/bin/aarch64-none-elf-gcc','-std=gnu11','-Wall','-Wextra','-Werror','-O3','-D__SWITCH__',
         '-I'+str(ROOT/'device'),'-I/opt/devkitpro/libnx/include','-c',str(arm),'-o',str(output/'session-arm.o')]
    base.owner.command(cmd);commands.append(cmd)
    assert inputs=={n:base.ep0.sha(ROOT/n) for n in names};assert production=={n:base.ep0.sha(startup.startup.REPO/n) for n in startup.startup.PRODUCTION}
    assert tickets=={n:base.ep0.sha(base.ep0.PRIVATE/'analysis'/n) for n in base.owner.TICKETS};verify(SEALED);verify(BOUNDED)
    result=dict(schema='A23-session-correlation-1',source_audit=source_audit,source_hashes=inputs,production_sources_sha256=production,
        tickets_sha256=tickets,sealed_input=sealed,sealed_bounded=bounded,recipe_digest=digest,compiler_commands=commands,
        cases=rows,case_count=len(rows),policy=policies,arm_object_sha256=base.ep0.sha(output/'session-arm.o'),
        native_session_results_unchanged=True,startup_transcript_synthetic=True,save_outcome_injected=True,
        startup_and_ep0_shared_context_prototype=True,save_receipt_input_crc_checked=True,
        full_arm_candidate_integrated=False,device_filesystem_envelope_integrated=False,old_wire_modified=False,
        production_modified=False,prior_runtime_modified=False,usb_accessed=False,sd_accessed=False,arm_executed=False,
        firmware_packaged=False,actual_switch_threads_executed=False,actual_dma_executed=False,
        hardware_verified=False,root_cause_confirmed=False,source_authenticated=False,cleanup_authorized=False)
    (output/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    (output/'SHA256SUMS').write_text(''.join(base.ep0.sha(p)+'  '+str(p.relative_to(output))+'\n' for p in sorted(output.rglob('*')) if p.is_file()))
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False);s=run(a.output);print(json.dumps(dict(output=str(a.output),cases=s['case_count'],policy=s['policy']),indent=2))
if __name__=='__main__':main()
