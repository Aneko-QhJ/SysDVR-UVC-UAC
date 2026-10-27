from pathlib import Path
import ast,copy,os,sys,tempfile,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_supervisor_job_link as audit
m=audit.model


class SupervisorJobLinkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        saved=os.environ.get('A23_SUPERVISOR_JOB_LINK_REVIEW')
        if saved:cls.root=Path(saved)
        else:cls.root=Path(tempfile.mkdtemp(prefix='a23-job-link-test-'))/'review';audit.run(cls.root)
        cls.pin=audit.f.sha(audit.a.read(cls.root/'SHA256SUMS'));cls.report=audit.verify(cls.root,cls.pin)
    def args(self,label):
        p=self.root/'work/cases'/label;expected=audit.a.read(p/'expected.json')
        return [expected,m.sha(expected),audit.cache(p/'job'),audit.f.load(p/'observation.json'),audit.a.read(p/'stdout.bin'),audit.a.read(p/'stderr.bin'),audit.cache(p/'materials'),audit.a.read(p/'link.json')]
    def reanchor(self,args):
        old=m.parse(args[0]);args[0]=m.encode(m.anchor(old['supervisor_case'],*args[2:7],old['job_review_sha256'],old['supervisor_review_sha256']));args[1]=m.sha(args[0]);return args
    def test_fifty_seven_cases_and_twenty_semantic_mutants(self):self.assertEqual(len(self.report['semantic']),57);self.assertEqual(len(audit.VARIANTS),20)
    def test_only_two_linked_model_completions_no_authority(self):
        self.assertEqual({n for n,v in self.report['semantic'].items() if v['result']['linked_model_completion']},audit.previous.GOOD)
        for v in self.report['semantic'].values():
            for k in m.FALSE:self.assertIs(v['result'][k],False)
    def test_entry_and_sdk_bindings_are_distinct(self):
        args=self.args('normal');link=m.parse(args[-1]);self.assertEqual(link['entry_binding']['schema'],'A23-two-epoch-entry-binding-1');self.assertIn('authorization_receipt_sha256',link['entry_binding']);self.assertIn('session_id',link['sdk_binding']);self.assertNotIn('job_id',link['sdk_binding']);self.assertEqual(link['relation_kind'],m.RELATION)
    def test_job_semantic_failures_rejected_after_new_anchor(self):
        for n in audit.VARIANTS[:7]:self.assertIn('job',self.report['semantic'][n]['result']['errors'])
    def test_selection_and_all_declaration_failures_rejected(self):
        for n in audit.VARIANTS[7:]:self.assertIn('correspondence',self.report['semantic'][n]['result']['errors'])
    def test_consumed_zero_is_not_reopened(self):
        args=self.args('normal');self.assertEqual(m.job_view(args[2])['consumed_sha256'],m.sha(args[2]['consumed.json']));self.assertEqual(self.report['semantic']['normal']['result']['consumed_remaining'],0)
    def test_existing_job_uuid_reused_without_new_namespace(self):
        original=m.parse(audit.a.read(self.root/'inputs/job/job.json'))
        for n in audit.previous.materials.CASES:self.assertEqual(self.report['semantic'][n]['result']['job_id'],original['job_id'])
    def test_supervisor_failure_stays_failure_despite_valid_job(self):
        for n in ('worker-failure','driver-failure','stdout-close-error','timeout-after-output'):
            r=self.report['semantic'][n]['result'];self.assertTrue(r['job_scope_consistent']);self.assertFalse(r['linked_model_completion'])
    def test_external_anchor_pin_required(self):
        args=self.args('normal');args[1]='0'*64
        with self.assertRaisesRegex(ValueError,'external job anchor'):m.assess(*args)
    def test_anchored_byte_change_without_new_anchor_rejected(self):
        args=self.args('normal');args[2]['consume-commit']=b'changed'
        self.assertIn('anchor',m.assess(*args)['errors'])
    def test_pure_consumers_open_no_files(self):
        saved={n:self.args(n) for n in self.report['semantic']}
        with patch('builtins.open',side_effect=AssertionError('filesystem')),patch('io.open',side_effect=AssertionError('filesystem')):
            for args in saved.values():self.assertEqual(m.assess(*args)['consumer_filesystem_calls'],0)
    def test_all_eighteen_job_members_required_even_with_new_anchor(self):
        self.assertEqual(len(m.JOB_FILES),18)
        for path in m.JOB_FILES:
            args=self.args('normal');del args[2][path];self.reanchor(args);self.assertIn('job',m.assess(*args)['errors'])
    def test_all_declaration_fields_mutation_rejected(self):
        original=self.args('normal');link=m.parse(original[-1])
        for k,v in link.items():
            args=self.args('normal');bad=copy.deepcopy(link);bad[k]=v+'-bad' if type(v) is str else {};args[-1]=m.encode(bad)
            self.assertIn('correspondence',m.assess(*args)['errors'])
    def test_bool_remaining_is_not_integer_zero(self):
        args=self.args('normal');v=m.parse(args[2]['consumed.json']);v['remaining']=False;args[2]['consumed.json']=m.encode(v);self.reanchor(args)
        self.assertIn('job',m.assess(*args)['errors'])
    def test_sdk_session_splice_after_resealing_cannot_link(self):
        args=self.args('normal');c=args[6];receipt=m.parse(c['sdk-receipt/receipt.json']);receipt['binding']['session_id']='other-session';c['sdk-receipt/receipt.json']=m.encode(receipt)
        sums=''.join(m.sha(c['sdk-receipt/'+n])+'  '+n+'\n' for n in ('receipt.json','snapshot.json')).encode();c['sdk-receipt/SHA256SUMS']=sums;c['sdk-receipt/COMMITTED']=(m.sha(sums)+'\n').encode()
        args[4]=m.encode(m.supervisor.old.stdout_report('normal','normal',c));args[3]['stdout_bytes']=len(args[4]);args[7]=m.encode(m.declaration(args[2],args[3],c));self.reanchor(args)
        self.assertIn('correspondence',m.assess(*args)['errors'])
    def test_generated_adapter_is_unapplied_readonly(self):
        static=self.report['static_plan'];self.assertFalse(static['patch_applied']);self.assertFalse(static['production_entry_changed'])
        tree=ast.parse(audit.a.read(self.root/'work/generated'/audit.plan.TARGET))
        for n in ast.walk(tree):
            if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute):self.assertNotIn(n.func.attr,('issue','consume','claimProcess','claimSelection','Popen'))
    def test_static_integration_evidence_nine_sources_pinned(self):
        evidence=self.report['static_plan']['source_evidence'];self.assertEqual(len(evidence),9)
        for name,row in evidence.items():self.assertEqual(m.sha(audit.a.read(self.root/'source'/name)),row['sha256']);self.assertTrue(row['anchors'])
    def test_forged_outer_observation_is_only_model_correspondence(self):
        args=self.args('stdout-close-error');args[3]['close_errors']=[];args[3]['close_completed']=m.supervisor.CLOSE_ORDER.copy();args[7]=m.encode(m.declaration(args[2],args[3],args[6]));self.reanchor(args)
        result=m.assess(*args);self.assertTrue(result['linked_model_completion']);self.assertFalse(result['same_physical_run_verified']);self.assertFalse(result['production_execution_authorized'])
    def test_readonly_verify_has_no_worker_process(self):
        with patch.object(audit.previous.supervisor.subprocess,'Popen',side_effect=AssertionError('process')):audit.verify(self.root,self.pin)
        with self.assertRaises(ValueError):audit.verify(self.root,'0'*64)
    def test_source507_and_formal_namespace_absent(self):
        v=audit.f.load(self.root/'audit.json');self.assertEqual((v['source_count'],v['prior_sources_unchanged']),(507,503));self.assertFalse(self.report['new_job_created'])
        self.assertFalse((ROOT/'private/sequence-reservations32').exists())


if __name__=='__main__':unittest.main()
