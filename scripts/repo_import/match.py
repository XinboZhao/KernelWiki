"""Matching suggests relationships; external decisions select publication actions."""
import re
from .store import digest, file_hash, read


def registry(root):
    return read(root / 'data/repo-import/registry.yaml', {'version': 1, 'implementations': {}})


def existing_index(root):
    result = []
    for path in sorted((root / 'wiki/kernels').rglob('*.md')):
        match = re.match(r'^---\s*\n(.*?)\n---', path.read_text(), re.DOTALL)
        if not match:
            continue
        from _yaml_compat import yaml
        metadata = yaml.safe_load(match.group(1))
        result.append({'page_id': metadata['id'], 'path': path.relative_to(root).as_posix(),
                       'sha256': file_hash(path), 'title': metadata.get('title'),
                       'kernel_types': metadata.get('kernel_types', []),
                       'languages': metadata.get('languages', []),
                       'sources': metadata.get('sources', []),
                       'coverage': 'page-only'})
    return result


def find_matches(candidate, registered):
    matches = []
    for identity, implementation in registered.get('implementations', {}).items():
        for version_id, version in implementation.get('versions', {}).items():
            old = version['candidate']
            relation = None
            if candidate['candidate_id'] == old['candidate_id']:
                relation = 'same_snapshot'
            elif (candidate['fingerprints'] == old['fingerprints'] and
                  candidate['entry'] == old['entry'] and not candidate['unresolved_dependencies'] and
                  not old['unresolved_dependencies']):
                relation = 'exact_content'
            elif (candidate['origin']['repo_id'] == old['origin']['repo_id'] and
                  (candidate['path'], candidate['entry']) == (old['path'], old['entry'])):
                relation = 'possible_new_version'
            elif candidate['fingerprints']['entry_sha256'] == old['fingerprints']['entry_sha256']:
                relation = 'similar_body'
            if relation:
                matches.append({'implementation_id': identity, 'version_id': version_id,
                                'page_id': implementation['page_id'], 'relation': relation})
    return matches


def context_digest(index, registered):
    return digest({'pages': index, 'registry': registered})
