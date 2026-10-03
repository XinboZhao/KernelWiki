import copy
import tempfile
import unittest
from pathlib import Path
from repo_import_support import prepared, registered
from repo_import.match import find_matches


class MatchTests(unittest.TestCase):
    def test_same_snapshot_and_dependency_difference(self):
        with tempfile.TemporaryDirectory() as directory:
            _, _, _, request = prepared(Path(directory))
            candidate = copy.deepcopy(request['candidates'][0])
            self.assertEqual('same_snapshot', find_matches(candidate, registered(request))[0]['relation'])
            candidate['candidate_id'] = 'new'
            candidate['origin']['repo_id'] = 'fork'
            candidate['unresolved_dependencies'] = []
            candidate['fingerprints']['dependencies_sha256'] = 'different'
            self.assertEqual('similar_body', find_matches(candidate, registered(request))[0]['relation'])

    def test_same_name_different_body_not_cross_repo_duplicate(self):
        with tempfile.TemporaryDirectory() as directory:
            _, _, _, request = prepared(Path(directory))
            candidate = copy.deepcopy(request['candidates'][0])
            candidate['candidate_id'] = 'new'
            candidate['origin']['repo_id'] = 'fork'
            candidate['fingerprints']['entry_sha256'] = 'different'
            self.assertEqual([], find_matches(candidate, registered(request)))
