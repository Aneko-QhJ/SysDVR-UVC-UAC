"""Isolated fixed-three derivations. No issuer, live CLI or hardware launch."""
import re


def change(raw, before, after, count=1):
    if raw.count(before) != count:
        raise ValueError('three-epoch anchor differs: '+before[:90])
    return raw.replace(before, after)


def names(raw):
    return (raw.replace('A23Paired', 'A23Triple').replace('A23PairLease', 'A23TripleLease')
            .replace('a23_paired_sdk_adapter.h', 'a23_triple_sdk_adapter.h')
            .replace('A23TwoEpochSDKDriver', 'A23ThreeEpochSDKDriver')
            .replace('a23_two_epoch_sdk_driver.h', 'a23_three_epoch_sdk_driver.h')
            .replace('A23-paired-resource-', 'A23-triple-resource-')
            .replace('A23-two-epoch-sdk-', 'A23-three-epoch-sdk-'))


def arrays(raw):
    # Declaration names only; descriptor bytes, SHA256 and array indexing stay intact.
    return re.sub(r'(_(?:dataAddress|rowAddress|saveAttempted|controlObserved|submittedAt|triggerAt|isoCount|controlCount|isoAt|controlAt|triggerEntered|isoOK|controlOK|accepted))\[2\]', r'\1[3]', raw)


def driver(raw):
    raw = names(arrays(raw))
    for a,b,n in [
        ('unsignedIntegerValue]!=4','unsignedIntegerValue]!=6',1),
        ('@"iso_attempts":@2,@"trigger_attempts":@2,@"status_reads":@4,@"frame_reads":@2', '@"iso_attempts":@3,@"trigger_attempts":@3,@"status_reads":@6,@"frame_reads":@3',1),
        ('rows.count!=2','rows.count!=3',1),
        ('first<81 || first>65504 || first%16!=1','first!=177',1),
        ('data.count==2 && rows.count==2','data.count==3 && rows.count==3',1),
        ('@[data[0],rows[0],data[1],rows[1]]','@[data[0],rows[0],data[1],rows[1],data[2],rows[2]]',1),
        ('i<4;++i','i<6;++i',1),
        ('@[NSNull.null,NSNull.null]','@[NSNull.null,NSNull.null,NSNull.null]',1),
        ('n<2;++n','n<3;++n',2), ('_epoch>=2','_epoch>=3',2), ('_epoch<2','_epoch<3',2),
        ('n>=2','n>=3',1),
        ('_epoch==2','_epoch==3',1), ('@"max_epochs":@2','@"max_epochs":@3',1),
        ('@"saved_epochs":@2','@"saved_epochs":@3',1),
        ('if(_epoch){IsoProbeStatus previous;memcpy(&previous,[_after[0] bytes],sizeof(previous));\n                if(s.urb_id==previous.urb_id)[checks addObject:@"urb_id_reused"];}',
         'for(NSUInteger prior=0;prior<_epoch;++prior){IsoProbeStatus previous;memcpy(&previous,[_after[prior] bytes],sizeof(previous));\n                if(s.urb_id==previous.urb_id)[checks addObject:@"urb_id_reused"];}',1),
        ('[_after[0] bytes]','[_after[_epoch-1] bytes]',1),
    ]: raw=change(raw,a,b,n)
    return raw


def adapter(raw):
    raw=names(arrays(raw))
    for a,b,n in [
        ('i<2;++i','i<3;++i',1),('n<2;++n','n<3;++n',2),
        ('_dataStores.count==2 && _transactionStores.count==2','_dataStores.count==3 && _transactionStores.count==3',1),
        ('- (NSDictionary *)readStatus {\n    if(![self check])return @{};',
         '- (BOOL)priorTerminal:(NSUInteger)count {\n    for(NSUInteger n=0;n<count;++n)if(![self terminal:n])return NO;return YES;\n}\n- (NSDictionary *)readStatus {\n    if(![self check])return @{};',1),
        ('BOOL order=(_statusReads==0 && _isoAttempts==0) ||\n        ((_statusReads==1 || _statusReads==2) && _isoAttempts==1 && [self terminal:0]) ||\n        (_statusReads==3 && _isoAttempts==2 && [self terminal:1]);',
         'NSUInteger epoch=_statusReads/2;BOOL after=(_statusReads%2)!=0;\n    BOOL order=_statusReads<6 && _isoAttempts==epoch+(after?1:0) && [self priorTerminal:epoch+(after?1:0)];',1),
        ('_frameReads>=2','_frameReads>=3',1),
        ('(_frameReads && ![self terminal:0])','![self priorTerminal:_frameReads]',1),
        ('n<2 &&','n<3 &&',1),('(!n || [self terminal:0])','[self priorTerminal:n]',1),('n>=2','n>=3',1),
        ('first<81 || first>65504 || first%16!=1','first!=177',1),
        ('i<4;++i','i<6;++i',1),
        ('lease.dataStores=@[all[0],all[2]];lease.transactionStores=@[all[1],all[3]];',
         'lease.dataStores=@[all[0],all[2],all[4]];lease.transactionStores=@[all[1],all[3],all[5]];',1),
        ('@(atomic_load(&_isoCount[1]))]','@(atomic_load(&_isoCount[1])),@(atomic_load(&_isoCount[2]))]',1),
        ('@(atomic_load(&_controlCount[1]))]','@(atomic_load(&_controlCount[1])),@(atomic_load(&_controlCount[2]))]',1),
    ]:raw=change(raw,a,b,n)
    return raw


def analyzer(raw):
    raw=names(raw)
    for a,b,n in [
        ('iso_attempts=2,trigger_attempts=2,status_reads=4,frame_reads=2,aborts=0,store_count=4',
         'iso_attempts=3,trigger_attempts=3,status_reads=6,frame_reads=3,aborts=0,store_count=6',1),
        ('len(r)==2','len(r)==3',1),('for epoch in (0,1):','for epoch in (0,1,2):',2),
        ('iso_attempts=2,trigger_attempts=2,saved_epochs=2','iso_attempts=3,trigger_attempts=3,saved_epochs=3',1),
        ('integer(first,81,65504)','integer(first,177,177)',1),('len(lines)==25','len(lines)==36',1),
        ('integer(epoch,0,1)','integer(epoch,0,2)',1),
        ("integer(prepared.get('max_epochs'),2,2)","integer(prepared.get('max_epochs'),3,3)",1),
        ('for e in (0,1)','for e in (0,1,2)',1),
        ("saved['index']==24","saved['index']==35",1),
        ("integer(saved['details'].get('saved_epochs'),2,2)","integer(saved['details'].get('saved_epochs'),3,3)",1),
        ('out=[];old=None;old_id=None;origins=[]','out=[];old=None;old_ids=set();origins=[]',1),
        ("by['saved',0]['index']","by['saved',epoch-1]['index']",1),
        ("require(state[5]!=old_id,'URB ID reused');old_id=state[5]", "require(state[5] not in old_ids,'URB ID reused');old_ids.add(state[5])",1),
        ('total_bytes=6144','total_bytes=9216',1),
    ]:raw=change(raw,a,b,n)
    # A fully rebound extra fourth directory must not be ignored.
    raw=change(raw,"    result=load(read(root/'result.json',16384))", "    require({p.name for p in root.glob('epoch-*')}=={'epoch-0','epoch-1','epoch-2'},'fixed three epoch inventory differs')\n    result=load(read(root/'result.json',16384))")
    return raw


def engine(raw):
    raw=raw.replace('SharedSequence32','SharedSequence48').replace('shared32','shared48').replace('block-00081','block-00177')
    raw=re.sub(r'\b(81|112|113|32)\b',lambda m:{'81':'177','112':'224','113':'225','32':'48'}[m[0]],raw)
    raw=change(raw,"        self.root=Path(root);self.simulation=simulation;self.fresh_scope=fresh_scope",
        "        f.require(simulation is True,'fixed48 is model-only; no formal issuer')\n        self.root=Path(root);self.simulation=simulation;self.fresh_scope=fresh_scope")
    raw=change(raw,'f.history(historical)',"f.require(f.history(historical)==set(range(49,177)),'complete 49..176 history required')",2)
    raw=raw.replace('A23-two-epoch-entry-binding-1','A23-three-epoch-entry-binding-1')
    return raw
