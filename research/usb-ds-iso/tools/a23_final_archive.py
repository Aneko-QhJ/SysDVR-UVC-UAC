"""Bounded, file-only final archives; no live roots, receiver launch or issuance."""
from pathlib import Path
import os,re,stat
import a23_sequence32_model as f
import a23_shared_sequence32 as s
from analyze_a23_shared_sequence32 import analyze as shared_analyze
from analyze_a23_two_epoch_entry import analyze as entry_analyze
FLAGS=('hardware_verified','hardware_entry_enabled','formal_issuance_available','process_origin_authenticated','callback_drain_verified','cleanup_authorized','allow_retry','sequences_allocated')
FALSE={k:False for k in FLAGS}

def canonical(path):
    p=Path(path);f.require(p.is_absolute() and p==p.resolve() and not p.is_relative_to('/Volumes'),'canonical non-volume path required');return p

def read(path,limit=64*1024*1024):
    path=canonical(path);fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        st=os.fstat(fd);f.require(stat.S_ISREG(st.st_mode) and 0<=st.st_size<=limit,'invalid file size/type');raw=bytearray()
        while len(raw)<st.st_size:
            part=os.read(fd,min(65536,st.st_size-len(raw)));f.require(part,'short read');raw.extend(part)
        f.require(not os.read(fd,1),'file grew during read');return bytes(raw)
    finally:os.close(fd)

def snapshot(root,maximum=4096,total_limit=256*1024*1024):
    root=canonical(root);f.require(root.is_dir(),'directory required');files={};dirs=[];total=0;nodes=0
    for parent,children,names in os.walk(root,followlinks=False):
        for name in sorted(children+names):
            p=Path(parent)/name;n=p.relative_to(root).as_posix();nodes+=1;f.require(nodes<=maximum and re.fullmatch(r'[A-Za-z0-9_.\-/]+',n) and len(p.relative_to(root).parts)<=18,'invalid/large input tree');st=p.lstat();f.require(not stat.S_ISLNK(st.st_mode),'symlink in tree')
            if stat.S_ISDIR(st.st_mode):dirs.append(n);continue
            f.require(stat.S_ISREG(st.st_mode),'nonregular input');raw=read(p);total+=len(raw);f.require(total<=total_limit,'input tree too large');files[n]=raw
    return dict(sorted(files.items())),sorted(dirs)

def sums(files):return ''.join(f.sha(raw)+'  '+n+'\n' for n,raw in sorted(files.items())).encode()
def inventory(files):return {n:dict(bytes=len(raw),sha256=f.sha(raw)) for n,raw in sorted(files.items())}
def prefixes(names):return sorted({str(Path(n).parent) for n in names for _ in [0] if str(Path(n).parent)!='.'}|{str(p) for n in names for p in Path(n).parents if str(p)!='.'})
def put(root,name,raw):
    p=root/name;p.parent.mkdir(parents=True,exist_ok=True);f.exclusive(p,raw)

def seal(root):
    files,_=snapshot(root);f.require('SHA256SUMS' not in files and 'COMMITTED' not in files,'already sealed');raw=sums(files);put(root,'SHA256SUMS',raw)
    for p in sorted((p for p in root.rglob('*') if p.is_dir()),key=lambda p:len(p.parts),reverse=True):f.sync(p)
    f.sync(root);put(root,'COMMITTED',(f.sha(raw)+'\n').encode());f.sync(root);f.sync(root.parent)

def sealed(root):
    files,dirs=snapshot(root);raw=files.pop('SHA256SUMS',None);commit=files.pop('COMMITTED',None);f.require(raw is not None and commit==(f.sha(raw)+'\n').encode() and raw==sums(files),'archive seal differs');return files,dirs,f.sha(raw)

def build_scope(root):
    root=canonical(root);files,dirs,digest=sealed(root);d=f.parse(files['descriptor.json']);f.require(files['descriptor.json']==f.encode(d) and d['schema']=='A23-verified-entry-descriptor-1','descriptor differs');expected={'descriptor.json','a23_verified_binding.h','verified-entry','binary.json','compile.log','build-command.json'}
    for group,key in (('source','source_hashes'),('baseline','baseline_files'),('history','history_files'),('recovery-index','recovery_index')):
        f.require(type(d[key]) is dict,'invalid descriptor hash table')
        for name,h in d[key].items():
            f.require(type(name) is str and re.fullmatch(r'[A-Za-z0-9_.\-/]+',name) and '..' not in name.split('/') and not name.startswith('/') and f.hex64(h),'invalid descriptor path/hash');n=group+'/'+name;f.require(f.sha(files[n])==h,'frozen '+group+' differs');expected.add(n)
    f.require(set(files)==expected and dirs==prefixes(expected),'build inventory differs')
    header=b'static const unsigned char A23VerifiedDescriptor[]={'+b','.join(str(n).encode() for n in files['descriptor.json'])+b'};\n';f.require(files['a23_verified_binding.h']==header,'binding header differs')
    record=dict(schema='A23-verified-entry-binary-1',receiver_sha256=f.sha(files['verified-entry']),descriptor_sha256=f.sha(files['descriptor.json']));f.require(files['binary.json']==f.encode(record),'binary binding differs')
    f.require(d['workflow_source_sha256']==f.sha(f.encode(d['source_hashes'])),'source inventory digest differs');base=''.join(h+'  '+n+'\n' for n,h in sorted(d['baseline_files'].items())).encode();f.require(f.sha(base)==d['baseline_manifest_sha256'],'baseline manifest differs')
    scope=dict(schema='A23-shared32-scope-1',**{k:d[k] for k in ('baseline_manifest_sha256','baseline_inventory_sha256','workflow_source_sha256','device_binding_sha256','recipe_sha256','history_sha256')},build_manifest_sha256=digest,receiver_sha256=record['receiver_sha256'],first_sequence=81,last_sequence=112,formal_issuance_available=False,acquisition_mode_implemented=False,hardware_entry_enabled=False)
    s.scope(scope)
    return scope,dict(manifest_sha256=digest,descriptor_sha256=f.sha(files['descriptor.json']),receiver_sha256=record['receiver_sha256'],frozen_source_count=len(d['source_hashes']))

def analyze_inputs(root,scope,report_raw,observation):
    result=dict(schema='A23-final-input-analysis-1',classification='incomplete_model_evidence',supplied_model_chain_complete=False,errors=[],**FALSE)
    def check(name,fn):
        try:return fn()
        except (ValueError,OSError,KeyError,TypeError,IndexError) as e:result['errors'].append(dict(component=name,reason=str(e).replace(str(root),'<inputs>')));return None
    row=check('report',lambda:f.parse(report_raw))
    def reported():
        f.require(type(row) is dict and row.get('schema')=='A23-verified-scope-fixture-1','invalid fixture report');v=row.get('verifier');f.require(type(v) is dict and v.get('schema')=='A23-readonly-scope-verifier-result-1' and v.get('failed') is False and v.get('model_roots') is True,'fresh verifier failed')
        for k in ('real_sdk_objects','usb_requests','sd_accesses'):f.require(type(row.get(k)) is int and row[k]==0,'model authority differs')
        f.require(observation['mode']=='supplied_static_model' or observation['returncode']==0,'model process failed');return True
    good=check('verifier',reported)
    info=check('job',lambda:f.load(root/'case-info.json'));job=info.get('job_id') if type(info) is dict else None
    shared=check('shared',lambda:shared_analyze(root/'namespace',job,scope,row['native']));entry=check('entry',lambda:entry_analyze(root/'host'))
    def joined():
        folder=root/'namespace/jobs'/job;context=f.load(folder/'native-context.json');host_context=f.load(root/'host/context.json');selection=f.load(folder/'native-sdk-claim.json');hs=f.load(root/'host/sdk-claim.json')
        f.require(f.encode(context)==f.encode(host_context),'native/entry context differs');f.require(selection['pid']==hs['pid'] and selection['identity']['device_id']==hs['device_id'] and selection['identity']['interface_id']==hs['interface_id'],'native/entry selected identity differs')
        expected=dict(schema='A23-two-epoch-entry-binding-1',build_manifest_sha256=scope['build_manifest_sha256'],receiver_sha256=scope['receiver_sha256'],authorization_receipt_sha256=f.sha(f.read(folder/'consumed.json')),first_sequence=81,last_sequence=112)
        for b in (row['entry']['binding'],f.load(root/'config.json')['binding'],f.load(root/'host/entry-current.json')['binding']):f.require(f.encode(b)==f.encode(expected),'entry/consumption binding differs')
        return True
    if shared and entry:check('joined',joined)
    if good and shared and entry and not result['errors']:result.update(classification='complete_model_chain',supplied_model_chain_complete=True,shared=shared,entry=entry)
    return result

def analyze(root,build):
    root=canonical(root);files,dirs,_=sealed(root);meta=f.parse(files['collection.json']);scope,reference=build_scope(build)
    expected_keys={'schema','origin','build_reference','raw_files','directories','report_sha256','observation',*FLAGS};f.require(type(meta) is dict and set(meta)==expected_keys and meta['schema']=='A23-final-collection-1','collection metadata differs')
    f.require(all(meta[k] is False for k in FLAGS),'collection authority differs');f.require(meta['origin'] in ('supplied_static_model','observed_model_child_exit'),'invalid collection origin');f.require(f.encode(meta['build_reference'])==f.encode(reference),'external build differs')
    observation=meta['observation'];f.require(type(observation) is dict and set(observation)=={'mode','child_exited','returncode','binary_sha256'},'observation inventory differs');f.require(observation['mode']==meta['origin'],'observation mode differs')
    if meta['origin']=='supplied_static_model':f.require(f.encode(observation)==f.encode(dict(mode='supplied_static_model',child_exited=False,returncode=None,binary_sha256=None)),'static observation claims process exit')
    else:f.require(observation['child_exited'] is True and type(observation['returncode']) is int and -255<=observation['returncode']<=255 and f.hex64(observation['binary_sha256']),'model exit observation differs')
    raw={n[7:]:r for n,r in files.items() if n.startswith('inputs/')};f.require(f.encode(inventory(raw))==f.encode(meta['raw_files']),'raw inventory differs');f.require(files['ATTEMPT']==b'one final collection attempt\n' and f.sha(files['report.json'])==meta['report_sha256'],'attempt/report differs')
    expected={'ATTEMPT','collection.json','analysis.json','report.json','process.stdout','process.stderr'}|{'inputs/'+n for n in raw};f.require(set(files)==expected,'collection inventory differs')
    f.require(type(meta['directories']) is list and meta['directories']==sorted(set(meta['directories'])) and all(type(n) is str and re.fullmatch(r'[A-Za-z0-9_.\-/]+',n) and '..' not in n.split('/') and not n.startswith('/') for n in meta['directories']),'directory inventory differs')
    wanted=sorted(set(prefixes(expected))|{'inputs'}|{'inputs/'+n for n in meta['directories']});f.require(dirs==wanted,'collection directories differ')
    if observation['mode']=='observed_model_child_exit':f.require(files['process.stdout']==files['report.json'],'observed report/stdout differs')
    recomputed=analyze_inputs(root/'inputs',scope,files['report.json'],observation);f.require(files['analysis.json']==f.encode(recomputed),'saved analysis differs');return dict(schema='A23-final-archive-analysis-1',archive_integrity_valid=True,build_consistent=True,origin=meta['origin'],producer_exit_reported=observation['child_exited'],analysis=recomputed,**FALSE)
