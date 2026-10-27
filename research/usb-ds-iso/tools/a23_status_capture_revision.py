"""Derive an isolated STATUS fix; never mutate a frozen source or issue a job."""
from pathlib import Path
import build_a23_live_two_epoch as old
w=old.w
PARENT=w.A/'A23-live-two-epoch-first-live-closeout-20261022'
NEW=('host/a23_status_capture_revision.h','tools/a23_status_capture_revision.py',
     'tools/audit_a23_status_capture_revision.py','tests/a23_status_capture_revision_fixture.inc',
     'tests/test_a23_status_capture_revision.py')


def sources():
    w.card.seal_verify(PARENT)
    previous=w.load(PARENT/'source-hashes.json')
    w.require(len(previous)==587 and old.sources()==previous,'original587 source drift')
    out=dict(previous)
    for name in NEW:out['research/usb-ds-iso/'+name]=w.sha(w.plain(w.ROOT/name))
    return dict(sorted(out.items()))


def replace(raw,before,after):
    w.require(raw.count(before)==1,'STATUS derivation anchor differs: '+before[:70])
    return raw.replace(before,after)


CAPTURE=r'''
- (NSDictionary *)captureStatusReply:(NSDictionary *)reply phase:(NSString *)phase lower:(uint64_t)lower {
    BOOL envelope=replyValid(reply,lower,_clock.nowTicks);
    id candidate=[reply isKindOfClass:NSDictionary.class]?reply[@"data"]:nil;
    BOOL bounded=[candidate isKindOfClass:NSData.class] && [candidate length]<=2048;
    NSData *raw=bounded?[candidate copy]:[NSData data];
    NSDictionary *observation=[reply isKindOfClass:NSDictionary.class]?frozenJSON(reply[@"observation"]):nil;
    NSMutableArray *checks=[NSMutableArray new];
    if(!envelope)[checks addObject:@"sdk_observation"];
    if(!observation)[checks addObject:@"observation_json"];
    if(!bounded || raw.length!=168)[checks addObject:@"status.length"];
    else {
        IsoProbeStatus s;memcpy(&s,raw.bytes,sizeof(s));
        if([phase isEqual:@"after"]){
            uint32_t mask=A23StatusAfterFailures(&s,(uint16_t)(_first+_epoch*16));
            for(unsigned i=0;i<sizeof(A23StatusFailureNames)/sizeof(A23StatusFailureNames[0]);++i)
                if(mask&(1u<<i))[checks addObject:@(A23StatusFailureNames[i])];
            if(_epoch){IsoProbeStatus previous;memcpy(&previous,[_after[0] bytes],sizeof(previous));
                if(s.urb_id==previous.urb_id)[checks addObject:@"urb_id_reused"];}
        }else if(!_epoch){
            if(s.magic!=ISO_PROBE_STATUS_MAGIC || s.version!=1 || s.endpoint!=0x83 || s.sequence || s.state ||
                s.post_result || s.urb_id || s.report_id || s.requested || s.transferred || s.urb_status ||
                s.report_count || s.report_result || (s.speed!=0 && s.speed!=3))[checks addObject:@"initial_state"];
        }else{
            IsoProbeStatus previous;memcpy(&previous,[_after[0] bytes],sizeof(previous));
            if(!A23StatusPreservedExceptReportCount(&s,&previous))[checks addObject:@"before_preserved_state"];
        }
    }
    NSDictionary *verdict=@{@"schema":@"A23-status-capture-1",@"binding":_binding,@"epoch":@(_epoch),@"phase":phase,
        @"raw_retained":@(bounded),@"raw_bytes":@(raw.length),@"raw_sha256":sha(raw),@"sdk_envelope_valid":@(envelope),
        @"observation_json_retained":@((BOOL)(observation!=nil)),@"failed_checks":[checks copy],
        @"hardware_verified":@NO,@"physical_run_authenticated":@NO};
    NSData *o=[NSJSONSerialization dataWithJSONObject:observation?:@{} options:NSJSONWritingSortedKeys error:NULL];
    NSData *v=[NSJSONSerialization dataWithJSONObject:verdict options:NSJSONWritingSortedKeys error:NULL];
    if(!o || !v || !saveDirectory(_directory,[NSString stringWithFormat:@"status-%@-epoch-%lu",phase,(unsigned long)_epoch],
        @{@"raw.bin":raw,@"observation.json":o,@"verdict.json":v})){
        [self stop:@"status_evidence_save_failed"];return nil;
    }
    if(checks.count){[self stop:[@"status_validation_failed:" stringByAppendingString:[checks componentsJoinedByString:@","]]];return nil;}
    return @{@"data":raw,@"observation":observation};
}
'''


def render_driver(base):
    raw=old.render_driver(base)
    raw='#include "a23_status_capture_revision.h"\n'+raw
    raw=replace(raw,'- (BOOL)arm {',CAPTURE+'\n- (BOOL)arm {')
    begin=raw.index('    if(!replyValid(reply,lower,_clock.nowTicks)){[self stop:@"invalid_before_reply"]')
    end=raw.index('    _before[_epoch]=raw;_beforeObservation[_epoch]=beforeObservation;',begin)
    raw=raw[:begin]+'''    reply=[self captureStatusReply:reply phase:@"before" lower:lower];if(!reply)return NO;
    NSData *raw=reply[@"data"];NSDictionary *beforeObservation=reply[@"observation"];
'''+raw[end:]
    begin=raw.index('    if(!replyValid(reply,lower,_clock.nowTicks)){[self stop:@"invalid_after_reply"]')
    end=raw.index('    if(![self emit:@"save_intent"',begin)
    raw=raw[:begin]+'''    reply=[self captureStatusReply:reply phase:@"after" lower:lower];if(!reply)return;
    NSData *raw=reply[@"data"];_after[_epoch]=raw;NSDictionary *afterObservation=reply[@"observation"];
'''+raw[end:]
    return raw


def render_analyzer(base):
    raw=replace(base,'v[12]==1 and not v[13]','v[12] in (0,1) and not v[13]')
    raw=replace(raw,"else:require(files['before.bin']==old,'second before differs from first after')",
        "else:\n            status(files['before.bin'],first+(epoch-1)*16)\n            require(files['before.bin'][:48]+files['before.bin'][52:]==old[:48]+old[52:],'second before differs beyond report_count')")
    raw=replace(raw,'def analyze(root):',ANALYZE_CAPTURE+'\n\ndef analyze(root):')
    raw=replace(raw,"    return dict(input_origin='injected_sdk_model'", "    validate_status_captures(root,binding)\n    return dict(status_captures_verified=True,report_count_policy='latest_query_0_or_1',input_origin='injected_sdk_model'")
    return raw


ANALYZE_CAPTURE=r'''
def validate_status_captures(root,binding):
    keys={'schema','binding','epoch','phase','raw_retained','raw_bytes','raw_sha256',
          'sdk_envelope_valid','observation_json_retained','failed_checks','hardware_verified','physical_run_authenticated'}
    typed=lambda x:json.dumps(x,sort_keys=True,separators=(',',':'))
    for epoch in (0,1):
        metadata=load(read(root/('epoch-'+str(epoch))/'metadata.json'))
        for phase in ('before','after'):
            folder=root/('status-'+phase+'-epoch-'+str(epoch));names={'raw.bin','observation.json','verdict.json'}
            require(folder.is_dir() and not folder.is_symlink() and {p.name for p in folder.iterdir()}==names|{'SHA256SUMS','COMMITTED'},'STATUS capture missing/extra files')
            files={n:read(folder/n,32768) for n in names}
            sums=''.join(sha(files[n])+'  '+n+'\n' for n in sorted(names)).encode()
            require(read(folder/'SHA256SUMS')==sums and read(folder/'COMMITTED',65)==(sha(sums)+'\n').encode(),'STATUS capture hash differs')
            v=load(files['verdict.json']);o=load(files['observation.json'])
            require(type(v) is dict and set(v)==keys and v.get('schema')=='A23-status-capture-1' and
                typed(v.get('binding'))==typed(binding) and integer(v.get('epoch'),epoch,epoch) and v.get('phase')==phase and
                v.get('raw_retained') is True and integer(v.get('raw_bytes'),168,168) and
                v.get('raw_sha256')==sha(files['raw.bin']) and len(files['raw.bin'])==168 and
                v.get('sdk_envelope_valid') is True and v.get('observation_json_retained') is True and
                v.get('failed_checks')==[] and v.get('hardware_verified') is False and v.get('physical_run_authenticated') is False,'STATUS capture verdict differs')
            require(files['raw.bin']==read(root/('epoch-'+str(epoch))/(phase+'.bin')) and
                typed(o)==typed(metadata.get(phase+'_observation')),'STATUS capture byte/observation binding differs')
'''
