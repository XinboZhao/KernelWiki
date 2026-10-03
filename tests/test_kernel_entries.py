import tempfile
import unittest
from pathlib import Path
from repo_import_support import ROOT, CODE
from kernel_entries import python_kernel_entries, cuda_kernel_entries


class EntryTests(unittest.TestCase):
    def test_python_multiple_entries_and_comment(self):
        entries = python_kernel_entries(CODE + '\n# @triton.jit\n@cute.kernel\ndef second(x):\n    return x\n')
        self.assertEqual(['reduce_kernel', 'second'], [e.name for e in entries])

    def test_invalid_python_is_not_a_silent_success(self):
        from repo_import_support import prepared, commit, import_repo, load_config, read
        with tempfile.TemporaryDirectory() as directory:
            wiki, repo, _, _ = prepared(Path(directory))
            (repo / 'broken.py').write_text('def invalid(:')
            commit(repo)
            run = import_repo.prepare(wiki, str(repo), 'HEAD', load_config(wiki))
            self.assertEqual('broken.py', read(run / 'inventory.yaml')['failures'][0]['path'])

    def test_cuda_definition_not_declaration_or_comment(self):
        entries = cuda_kernel_entries('// __global__ void fake() {}\n__global__ void declared();\n__global__ void real(int* x) { x[0] = 1; }')
        self.assertEqual(['real'], [e.name for e in entries])

    def test_selected_snippet_never_publishes_unreviewed_definition(self):
        from kernel_entries import kernel_snippet
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'kernel.py'
            path.write_text(CODE + '\n@triton.jit\ndef unreviewed(x):\n    return x * 2\n')
            entry = python_kernel_entries(path.read_text())[0]
            snippet = kernel_snippet(path, entry.name, entry.line)
            self.assertIn('reduce_kernel', snippet)
            self.assertNotIn('unreviewed', snippet)

    def test_cuda_strings_cannot_create_entries_or_close_bodies(self):
        from kernel_entries import kernel_snippet
        source = 'const char* fake = "__global__ void fake() {}";\n__global__ void real(int* x) { const char* s = "}"; x[0] = 1; }\n'
        entries = cuda_kernel_entries(source)
        self.assertEqual(['real'], [e.name for e in entries])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'kernel.cu'
            path.write_text(source)
            self.assertIn('x[0] = 1;', kernel_snippet(path, entries[0].name, entries[0].line))
