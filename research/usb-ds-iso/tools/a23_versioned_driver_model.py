"""Isolated versioned driver derivation; original production sources stay pinned."""
import difflib
import a23_driver_fault_model as old_model
import a23_quiet_driver_copy as patch
f=old_model.f
BASE=old_model.BASE
DRIVER=BASE+'host/a23_two_epoch_sdk_driver.m'
PINS={'research/usb-ds-iso/tests/a23_driver_fault_clock.inc': '6c5d65530808e0e3e866b7ca5e66b3d028f9d622290d238547f5b8609ef2c593', 'research/usb-ds-iso/tests/a23_driver_fault_main.inc': 'd0f34c3a725e96f4ebe3891a4625e0224e74d4ab8c037fb6e06770708c5028b9'}


def once(text,old,new):
    f.require(text.count(old)==1,'versioned driver anchor missing or repeated');return text.replace(old,new,1)


def driver(raw):
    text=patch.render(raw).decode()
    text=once(text,'#import "a23_quiet_driver_clock_candidate.h"','#import "a23_versioned_driver_bridge.h"')
    text=text.replace('A23QuietDriverClockSample','A23VersionedDriverSample').replace('A23QuietDriverReadProfile','A23VersionedDriverReadProfile').replace('A23QuietDriverCapture','A23VersionedDriverCapture').replace('A23QuietDriverEvaluate','A23VersionedDriverEvaluate')
    for name in ('_quietClockStart','start','now'):text=text.replace(name+'.stamp',name+'.version.stamp')
    text=once(text,'A23VersionedDriverSample _quietClockStart;','A23VersionedDriverSample _quietClockStart;\n    id _versionedClockOwner;uint64_t _quietVersionLive,_quietVersionStart,_quietVersionEnd,_quietVersionReleased;')
    text=once(text,'if((self=[super init])){','if((self=[super init])){\n        _versionedClockOwner=clock;')
    text=once(text,'- (BOOL)guard {','- (BOOL)guard {\n    if(_versionedClockOwner && _clock!=_versionedClockOwner)[self stop:@"observation_clock"];\n    if(_quietVersionLive && !A23VersionedDriverMatches(_clock,_quietVersionLive))[self stop:@"observation_version"];')
    old='            if(duration.minimum_met && [self emit:@"observation_complete" details:@{@"quiet_start_ticks":@(_quietSince),@"quiet_end_ticks":@(now.version.stamp.ticks),@"minimum_ns":@250000000}] && [self guard]){_settled=YES;_settledAt=now.version.stamp.ticks;}'
    new='            _quietVersionEnd=now.version.generation;\n            if(duration.minimum_met){\n                if(!A23VersionedDriverBeginCommit(_versionedClockOwner,&now)){[self stop:@"observation_version"];return;}\n                BOOL accepted=[self emit:@"observation_complete" details:@{@"quiet_start_ticks":@(_quietSince),@"quiet_end_ticks":@(now.version.stamp.ticks),@"minimum_ns":@250000000}] && [self guard];\n                if(accepted){_settled=YES;_settledAt=now.version.stamp.ticks;}\n                uint64_t released=0;\n                if(!A23VersionedDriverEndCommit(_versionedClockOwner,&released)){[self stop:@"observation_version"];return;}\n                _quietVersionLive=released;_quietVersionReleased=released;[self guard];\n            }'
    text=once(text,old,new)
    text=once(text,'_quietClockStart=start;_quietSince=start.version.stamp.ticks;','_quietClockStart=start;_quietSince=start.version.stamp.ticks;_quietVersionLive=start.version.generation;_quietVersionStart=start.version.generation;')
    return text.encode()


def protected(raw):
    text=raw.decode();out=patch.protected_slices(raw);out.pop('emit-stop-guard')
    out['emit-stop']=text[text.index('- (BOOL)emit:'):text.index('- (BOOL)guard {')].encode();return out


def diff(raw,candidate):
    return ''.join(difflib.unified_diff(patch.render(raw).decode().splitlines(True),candidate.decode().splitlines(True),fromfile='prior-isolated/driver.m',tofile='versioned-isolated/driver.m')).encode()


def render(source):
    for name,h in PINS.items():f.require(f.sha((source/name).read_bytes())==h,'old fault fixture pin differs')
    out=old_model.render(source);out[DRIVER]=driver((source/DRIVER).read_bytes())
    f.require(protected((source/DRIVER).read_bytes())==protected(out[DRIVER]),'unrelated driver methods changed')
    for name in ('host/a23_versioned_clock_candidate.h','host/a23_versioned_clock_candidate.c','host/a23_versioned_driver_bridge.h','host/a23_versioned_driver_bridge.m'):
        out[BASE+name]=(source/BASE/name).read_bytes()
    key=BASE+'tests/model_main.m';text=out[key].decode()
    oldclock=(source/BASE/'tests/a23_isolated_driver_clock.inc').read_text();newclock=(source/BASE/'tests/a23_versioned_driver_clock.inc').read_text()
    text=once(text,oldclock,newclock)
    fault=(source/BASE/'tests/a23_driver_fault_clock.inc').read_text()
    fault=once(fault,'@property NSUInteger mutations;','@property NSUInteger mutations;\n@property BOOL afterCaptureABA;')
    fault=once(fault,'if([_mutation isEqual:@"aba"])','if([_mutation isEqual:@"bypass"]){\n            A23VersionedClockSample p;assert([self versionedProfile:&p]==A23VersionedClockOK);\n            A23VersionedClockStore *store=(A23VersionedClockStore *)p.store_identity;\n            atomic_store(&store->numerator,2);atomic_store(&store->numerator,1);\n        }\n        if([_mutation isEqual:@"aba"])')
    marker='    }return ticks;\n}\n@end'
    fault=once(fault,marker,'    }return ticks;\n}\n- (A23VersionedClockStatus)versionedCapture:(A23VersionedClockSample *)out {\n    A23VersionedClockStatus status=[super versionedCapture:out];\n    if(_afterCaptureABA && status==A23VersionedClockOK){_afterCaptureABA=NO;++_mutations;self.n=2;self.n=1;}\n    return status;\n}\n@end')
    text=once(text,(source/BASE/'tests/a23_driver_fault_clock.inc').read_text(),fault)
    text=once(text,(source/BASE/'tests/a23_driver_fault_main.inc').read_text(),(source/BASE/'tests/a23_versioned_driver_main.inc').read_text())
    out[key]=text.encode()
    for name,raw in out.items():
        if name.endswith(('.m','.c')):
            for token in ('mach_absolute_time','mach_timebase_info','initWithIOService:','A23ReadExecutionContext'):
                f.require(token.encode() not in raw,'versioned implementation crossed scope')
    return out
