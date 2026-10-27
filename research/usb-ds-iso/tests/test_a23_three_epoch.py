"""Fixed48 model authority, historical coverage and one-use refusal behavior."""
from pathlib import Path
import sys
import tempfile
import types
import unittest
import uuid

TOOLS=Path(__file__).resolve().parents[1]/'tools'
sys.path.insert(0,str(TOOLS))
import a23_three_epoch_candidate as c

class Fixed48(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir='/private/tmp',prefix='a23-fixed48-unit-')
        self.root=Path(self.tmp.name);self.m=types.ModuleType('fixed48_test');self.m.__file__=str(self.root/'engine.py')
        exec(compile(c.engine((TOOLS/'a23_shared_sequence32.py').read_text()),self.m.__file__,'exec'),self.m.__dict__)
        self.h=[dict(first=n,last=n+15,reservation_sha256='1'*64,record_sha256='2'*64) for n in range(49,177,16)]
        self.scope={k:'3'*64 for k in self.m.SCOPE_HASHES}
        self.scope.update({k:False for k in self.m.SCOPE_FLAGS})
        self.scope.update(schema='A23-shared48-scope-1',first_sequence=177,last_sequence=224,history_sha256=self.m.f.sha(self.m.f.encode(self.h)))
    def tearDown(self):self.tmp.cleanup()
    def store(self):return self.m.SharedSequence48(self.root/'ns',simulation=True,fresh_scope=lambda:self.scope)
    def prepare(self,s):
        job=str(uuid.uuid4());ns=s.validate();s.prepare(job,dict(schema='A23-shared48-authorization-1',job_id=job,scope_sha256=ns['scope_sha256'],maximum_invocations=1,simulation=True,hardware_test_authorized=False));return job
    def test_formal_refused_without_creating_directory(self):
        with self.assertRaises(ValueError):self.m.SharedSequence48(self.root/'formal',simulation=False,fresh_scope=lambda:self.scope)
        self.assertFalse((self.root/'formal').exists())
    def test_old32_and_wrong_width_refused(self):
        for override in [dict(schema='A23-shared32-scope-1'),dict(last_sequence=208),dict(first_sequence=True)]:
            with self.assertRaises(ValueError):self.m.scope(self.scope|override)
    def test_history_digest_mismatch_refused_before_creation(self):
        with self.assertRaises(ValueError):self.store().initialize(self.h[:-1])
        self.assertFalse((self.root/'ns').exists())
    def test_rehashed_missing_history_still_refused(self):
        self.h=self.h[:-1];self.scope['history_sha256']=self.m.f.sha(self.m.f.encode(self.h))
        with self.assertRaises(ValueError):self.store().initialize(self.h)
        self.assertFalse((self.root/'ns').exists())
    def test_freshness_change_refused(self):
        s=self.store();s.initialize(self.h);self.scope['receiver_sha256']='4'*64
        with self.assertRaises(ValueError):s.validate()
    def test_one_job_burns_all48_and_no_takeover(self):
        s=self.store();s.initialize(self.h);first=self.prepare(s);second=self.prepare(s);s.issue(first);s.consume(first)
        b=self.m.check_burn(s.root,first);self.assertEqual((b['first'],b['last'],b['count']),(177,224,48))
        for call in [lambda:s.issue(second),lambda:s.consume(first)]:
            with self.assertRaises((ValueError,OSError)):call()

if __name__=='__main__':unittest.main()
