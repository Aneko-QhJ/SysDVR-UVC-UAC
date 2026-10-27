"""Disposable file-only 32-sequence reservation model. No production writer/runner."""
from contextlib import contextmanager
from pathlib import Path
import fcntl,hashlib,json,os,stat,uuid
from a23_execution_context import validate as validate_context

def require(ok,why):
    if not ok:raise ValueError(why)
def encode(v):return (json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
def sha(raw):return hashlib.sha256(raw).hexdigest()
def pairs(rows):
    d={}
    for k,v in rows:require(k not in d,'duplicate JSON key');d[k]=v
    return d
def parse(raw):return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:require(False,'nonfinite JSON'))
def read(path):
    path=Path(path);require(path==path.resolve(),'canonical regular file required');fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        st=os.fstat(fd);require(stat.S_ISREG(st.st_mode) and 0<=st.st_size<=1024*1024,'invalid file size/type');raw=b''
        while len(raw)<st.st_size:
            part=os.read(fd,st.st_size-len(raw));require(part,'short read');raw+=part
        require(not os.read(fd,1),'file grew while reading');return raw
    finally:os.close(fd)
def load(path):return parse(read(path))
def integer(v,low=0,high=65535):return type(v) is int and low<=v<=high
def hex64(v):return type(v) is str and len(v)==64 and set(v)<=set('0123456789abcdef')
def sync(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)
def exclusive(path,raw):
    path=Path(path);fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_RDWR,0o600)
    try:
        os.fsync(fd);sync(path.parent) # the exclusive burn exists durably even if later writes fail
        at=0
        while at<len(raw):
            n=os.write(fd,raw[at:]);require(n>0,'short write');at+=n
        os.fsync(fd);require(os.pread(fd,len(raw)+1,0)==raw,'write readback differs')
    finally:os.close(fd)
    sync(path.parent)
def put(path,v):exclusive(path,encode(v))

def material(v):
    keys={'schema','baseline_manifest_sha256','baseline_inventory_sha256','workflow_source_sha256','build_manifest_sha256','receiver_sha256','first_sequence','last_sequence','model_only','hardware_entry_enabled'}
    require(type(v) is dict and set(v)==keys and v['schema']=='A23-sequence32-model-materials-1','invalid materials')
    require(v['model_only'] is True and v['hardware_entry_enabled'] is False,'model authority differs')
    for k in keys-{'schema','model_only','hardware_entry_enabled','first_sequence','last_sequence'}:require(hex64(v[k]),'invalid material digest')
    require(integer(v['first_sequence'],81,81) and integer(v['last_sequence'],112,112),'reviewed range is81..112 only')
    return v

def history(v):
    require(type(v) is list and len(v)<=4096,'invalid history');used=set()
    for r in v:
        require(type(r) is dict and set(r)=={'first','last','reservation_sha256','record_sha256'} and integer(r['first'],1,65505) and (r['first']-1)%16==0 and integer(r['last'],r['first']+15,r['first']+15),'invalid historical interval')
        require(hex64(r['reservation_sha256']) and hex64(r['record_sha256']),'history digest missing')
        values=set(range(r['first'],r['last']+1));require(not used&values,'overlapping historical intervals');used|=values
    return used

BASE={'capsule.json','history.json','materials.json'}
OPTIONAL={'.lock','reservation.json','issue.json','consume-attempt','consumed.json','process-attempt','context.json','process-claim.json','selection-attempt','sdk-claim.json'}

def inspect(root,*,writable=False):
    root=Path(root);require(root==root.resolve() and root.is_dir() and not root.is_symlink(),'canonical model root required')
    names={p.name for p in root.iterdir()};require(BASE<=names and names<=BASE|OPTIONAL and all(not p.is_symlink() and p.is_file() for p in root.iterdir()),'unknown/partial model inventory')
    cap=load(root/'capsule.json');m=material(load(root/'materials.json'));h=load(root/'history.json');history(h)
    require(type(cap) is dict and set(cap)=={'schema','root','id','materials_sha256','history_sha256','simulation','hardware_entry_enabled'} and cap['schema']=='A23-sequence32-model-capsule-1' and cap['simulation'] is True and cap['hardware_entry_enabled'] is False,'invalid model capsule')
    require(type(cap['root']) is str and Path(cap['root']).is_absolute() and Path('/private/tmp') in Path(cap['root']).parents and '..' not in Path(cap['root']).parts and str(uuid.UUID(cap['id']))==cap['id'],'invalid capsule identity')
    require(cap['materials_sha256']==sha(read(root/'materials.json')) and cap['history_sha256']==sha(read(root/'history.json')),'capsule input drift')
    if writable:require(Path('/private/tmp') in root.parents and cap['root']==str(root),'writes require original temporary model root')
    return cap,m,h,names

@contextmanager
def locked(root):
    root=Path(root);inspect(root,writable=True);fd=os.open(root/'.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        require(stat.S_ISREG(os.fstat(fd).st_mode),'invalid model lock');os.fsync(fd);sync(root);fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);inspect(root,writable=True);yield root
    finally:os.close(fd)

def create(root,materials,historical):
    root=Path(root);require(root.is_absolute() and root==root.resolve() and Path('/private/tmp') in root.parents and not root.exists() and root.parent.is_dir(),'new temporary model root required')
    material(materials);history(historical);root.mkdir(mode=0o700);sync(root.parent)
    put(root/'materials.json',materials);put(root/'history.json',historical)
    put(root/'capsule.json',dict(schema='A23-sequence32-model-capsule-1',root=str(root),id=str(uuid.uuid4()),materials_sha256=sha(read(root/'materials.json')),history_sha256=sha(read(root/'history.json')),simulation=True,hardware_entry_enabled=False))
    inspect(root,writable=True);return root

def preview(root):
    cap,m,h,names=inspect(root);overlap=sorted(history(h)&set(range(81,113)))
    return dict(schema='A23-sequence32-model-preview-1',first_sequence=81,last_sequence=112,block_count=1,sequence_count=32,
        model_can_reserve=not overlap and not names&{'reservation.json','issue.json','consume-attempt','consumed.json'},
        historical_overlap=overlap,remaining=0,formal_issuance_available=False,hardware_entry_enabled=False,simulation=True)

def reserved(root):
    cap,m,h,names=inspect(root);require('reservation.json' in names,'no reservation');r=load(Path(root)/'reservation.json')
    expected=dict(schema='A23-sequence32-model-reservation-1',first=81,last=112,count=32,capsule_id=cap['id'],root=cap['root'],materials_sha256=cap['materials_sha256'],history_sha256=cap['history_sha256'],simulation=True,hardware_entry_enabled=False)
    require(encode(r)==encode(expected) and not history(h)&set(range(81,113)),'reservation binding/overlap differs');return r

def reserve(root):
    with locked(root) as root:
        cap,m,h,names=inspect(root,writable=True);require(preview(root)['model_can_reserve'],'32 sequences already burned or overlap')
        row=dict(schema='A23-sequence32-model-reservation-1',first=81,last=112,count=32,capsule_id=cap['id'],root=cap['root'],materials_sha256=cap['materials_sha256'],history_sha256=cap['history_sha256'],simulation=True,hardware_entry_enabled=False)
        put(root/'reservation.json',row);reserved(root);return row

def issue(root):
    # Single lock covers all32 burn AND issue. A write failure keeps the entire
    # reservation file, even empty/partial; there is no resume/release API.
    with locked(root) as root:
        cap,m,h,names=inspect(root,writable=True);require(preview(root)['model_can_reserve'],'32 sequences already burned or overlap')
        r=dict(schema='A23-sequence32-model-reservation-1',first=81,last=112,count=32,capsule_id=cap['id'],root=cap['root'],materials_sha256=cap['materials_sha256'],history_sha256=cap['history_sha256'],simulation=True,hardware_entry_enabled=False)
        put(root/'reservation.json',r);reserved(root)
        v=dict(schema='A23-sequence32-model-issue-1',capsule_id=cap['id'],root=cap['root'],materials_sha256=cap['materials_sha256'],reservation_sha256=sha(read(root/'reservation.json')),remaining=1,model_only=True,hardware_entry_enabled=False)
        put(root/'issue.json',v);issued(root);return v

def issued(root):
    root=Path(root);reserved(root);cap,m,h,names=inspect(root);v=load(root/'issue.json')
    expected=dict(schema='A23-sequence32-model-issue-1',capsule_id=cap['id'],root=cap['root'],materials_sha256=cap['materials_sha256'],reservation_sha256=sha(read(root/'reservation.json')),remaining=1,model_only=True,hardware_entry_enabled=False)
    require(encode(v)==encode(expected),'issue binding differs');return v

def consumed(root):
    root=Path(root);issued(root);v=load(root/'consumed.json');cap,m,h,names=inspect(root)
    expected=dict(schema='A23-sequence32-model-consumed-1',capsule_id=cap['id'],root=cap['root'],issue_sha256=sha(read(root/'issue.json')),materials_sha256=cap['materials_sha256'],remaining=0,receiver_launched=False,model_only=True,hardware_entry_enabled=False)
    require(encode(v)==encode(expected) and read(root/'consume-attempt')==b'one attempt\n','consumption binding differs');return v

def consume(root):
    with locked(root) as root:
        issued(root);exclusive(root/'consume-attempt',b'one attempt\n');cap,m,h,names=inspect(root,writable=True)
        row=dict(schema='A23-sequence32-model-consumed-1',capsule_id=cap['id'],root=cap['root'],issue_sha256=sha(read(root/'issue.json')),materials_sha256=cap['materials_sha256'],remaining=0,receiver_launched=False,model_only=True,hardware_entry_enabled=False)
        put(root/'consumed.json',row);consumed(root);return row

def process_claim(root,context):
    with locked(root) as root:
        consumed(root);exclusive(root/'process-attempt',b'one attempt\n');cap,m,h,names=inspect(root,writable=True)
        put(root/'context.json',context);validate_context(context,m['receiver_sha256'])
        row=dict(schema='A23-sequence32-model-process-1',capsule_id=cap['id'],consumed_sha256=sha(read(root/'consumed.json')),context_sha256=sha(read(root/'context.json')),pid=context['pid'],materials_sha256=cap['materials_sha256'],model_only=True,hardware_entry_enabled=False)
        put(root/'process-claim.json',row);return row

def checked_process(root):
    root=Path(root);consumed(root);cap,m,h,names=inspect(root);context=load(root/'context.json');validate_context(context,m['receiver_sha256']);row=load(root/'process-claim.json')
    expected=dict(schema='A23-sequence32-model-process-1',capsule_id=cap['id'],consumed_sha256=sha(read(root/'consumed.json')),context_sha256=sha(read(root/'context.json')),pid=context['pid'],materials_sha256=cap['materials_sha256'],model_only=True,hardware_entry_enabled=False)
    require(encode(row)==encode(expected) and read(root/'process-attempt')==b'one attempt\n','process claim differs');return row,context

def selection_claim(root,identity,context):
    with locked(root) as root:
        p,old=checked_process(root);exclusive(root/'selection-attempt',b'one attempt\n')
        require(encode(old)==encode(context),'selection process context changed')
        require(type(identity) is dict and set(identity)=={'device_id','interface_id','speed'} and integer(identity['device_id'],1,2**64-1) and integer(identity['interface_id'],1,2**64-1) and identity['device_id']!=identity['interface_id'] and integer(identity['speed'],3,3),'invalid selected HS identity')
        row=dict(schema='A23-sequence32-model-selection-1',process_sha256=sha(read(root/'process-claim.json')),context_sha256=p['context_sha256'],identity=identity,pid=old['pid'],model_only=True,hardware_entry_enabled=False)
        put(root/'sdk-claim.json',row);return row

def checked_selection(root):
    root=Path(root);p,c=checked_process(root);row=load(root/'sdk-claim.json');i=row.get('identity')
    require(type(i) is dict and set(i)=={'device_id','interface_id','speed'} and integer(i['device_id'],1,2**64-1) and integer(i['interface_id'],1,2**64-1) and i['device_id']!=i['interface_id'] and integer(i['speed'],3,3),'invalid selected HS identity')
    expected=dict(schema='A23-sequence32-model-selection-1',process_sha256=sha(read(root/'process-claim.json')),context_sha256=p['context_sha256'],identity=i,pid=c['pid'],model_only=True,hardware_entry_enabled=False)
    require(encode(row)==encode(expected) and read(root/'selection-attempt')==b'one attempt\n','selection claim differs');return row
