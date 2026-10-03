import tempfile
import unittest
from pathlib import Path
from repo_import_support import prepared, commit, import_repo, load_config, read
from repo_import.checkout import canonical_repo


class SnapshotTests(unittest.TestCase):
    def test_remote_identity_normalization(self):
        self.assertEqual(canonical_repo('git@github.com:owner/repo.git'), canonical_repo('https://github.com/owner/repo/'))

    def test_dirty_worktree_does_not_change_pinned_input(self):
        with tempfile.TemporaryDirectory() as directory:
            wiki, repo, _, old = prepared(Path(directory))
            (repo / 'kernel.py').write_text('uncommitted source')
            run = import_repo.prepare(wiki, str(repo), 'HEAD', load_config(wiki))
            new = read(run / 'review-request.yaml')
            self.assertTrue(new['snapshot']['ignored_worktree_changes'])
            self.assertEqual(old['candidates'], new['candidates'])

    def test_modified_cached_checkout_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            _, _, _, request = prepared(Path(directory))
            (Path(request['snapshot']['checkout']) / 'kernel.py').write_text('tampered')
            with self.assertRaisesRegex(ValueError, 'modified'):
                import_repo.check_snapshot(request)
