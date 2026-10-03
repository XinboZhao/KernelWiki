import tempfile
import unittest
from pathlib import Path
from repo_import_support import prepared, document, import_repo, write, read
from repo_import.store import contained


class StoreTests(unittest.TestCase):
    def test_rebuild_from_persisted_review_is_stable(self):
        with tempfile.TemporaryDirectory() as directory:
            wiki, _, run, request = prepared(Path(directory))
            write(run / 'decisions.yaml', document(request))
            first = import_repo.build(wiki, run)
            self.assertEqual(first, import_repo.build(wiki, run))
            self.assertEqual('built', read(run / 'result.yaml')['status'])

    def test_paths_cannot_escape_persistent_root(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                contained(Path(directory), '../../outside')
