import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from repo_import_support import prepared, document, write, import_repo, read
from repo_import.store import digest, file_hash
from repo_import.publish import apply_plan, recover_transaction


class PublishTests(unittest.TestCase):
    def plan(self, directory):
        wiki, _, run, request = prepared(directory)
        write(run / 'decisions.yaml', document(request))
        plan = import_repo.build(wiki, run)
        plan['validated_digest'] = digest(plan['files'])
        return wiki, run, plan

    def test_concurrent_target_edit_prevents_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            wiki, run, plan = self.plan(Path(directory))
            target = wiki / plan['files'][0]['path']
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('concurrent edit')
            with self.assertRaisesRegex(ValueError, 'Concurrent'):
                apply_plan(wiki, run, plan)
            self.assertEqual('concurrent edit', target.read_text())

    def test_partial_write_failure_restores_all_targets(self):
        with tempfile.TemporaryDirectory() as directory:
            wiki, run, plan = self.plan(Path(directory))
            from repo_import import publish
            original = publish.atomic_write
            calls = 0
            def fail_once(path, text):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError('injected write failure')
                original(path, text)
            with patch.object(publish, 'atomic_write', side_effect=fail_once), self.assertRaises(OSError):
                apply_plan(wiki, run, plan)
            for record in plan['files']:
                self.assertEqual(record['before'], file_hash(wiki / record['path']))
            self.assertEqual('rolled_back', read(run / 'transaction.yaml')['status'])

    def test_interrupted_apply_recovers_before_context_check(self):
        with tempfile.TemporaryDirectory() as directory:
            wiki, run, plan = self.plan(Path(directory))
            write(run / 'publication-plan.yaml', plan)
            from repo_import import publish
            original = publish.atomic_write
            calls = 0
            def crash(path, text):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise SystemExit('simulated process interruption')
                original(path, text)
            with patch.object(publish, 'atomic_write', side_effect=crash), self.assertRaises(SystemExit):
                apply_plan(wiki, run, plan)
            self.assertEqual('applying', read(run / 'transaction.yaml')['status'])
            import_repo.apply(wiki, run)
            self.assertEqual('committed', read(run / 'transaction.yaml')['status'])

    def test_manual_page_duplicate_adds_source_without_replacing_prose(self):
        with tempfile.TemporaryDirectory() as directory:
            wiki, repo, _, _ = prepared(Path(directory))
            from repo_import.publish import markdown
            from repo_import_support import admission, load_config
            text = markdown({'id': 'kernel-manual', 'title': 'Manual', 'type': 'kernel',
                             'sources': [], 'reproducibility': 'benchmarked'}, '# Hand-maintained content\n')
            page = wiki / 'wiki/kernels/manual.md'
            page.write_text(text)
            run = import_repo.prepare(wiki, str(repo), 'HEAD', load_config(wiki))
            request = read(run / 'review-request.yaml')
            decision = admission(request)
            decision.update(action='attach_source', relation='exact_duplicate', target_page_id='kernel-manual',
                            equivalence_basis='Fixture source corresponds to this manually maintained example.',
                            target_evidence=[{'path': 'wiki/kernels/manual.md', 'sha256': file_hash(page), 'locator': 'Hand-maintained content'}])
            write(run / 'decisions.yaml', document(request, decision))
            plan = import_repo.build(wiki, run)
            staged = (run / 'staging/wiki/kernels/manual.md').read_text()
            self.assertIn('# Hand-maintained content', staged)
            self.assertIn('reproducibility: benchmarked', staged)
            self.assertNotIn('Fixture reduction', staged)

    def test_changed_decision_after_build_cannot_be_applied(self):
        with tempfile.TemporaryDirectory() as directory:
            wiki, run, plan = self.plan(Path(directory))
            write(run / 'publication-plan.yaml', plan)
            doc = read(run / 'decisions.yaml')
            doc['decisions'][0]['rationale'] = 'changed after build'
            write(run / 'decisions.yaml', doc)
            with self.assertRaisesRegex(ValueError, 'changed after build'):
                import_repo.apply(wiki, run)
