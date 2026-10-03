"""Read externally authored decisions. No model execution or prompt loading."""
from pathlib import Path
from .store import digest, file_hash, contained

ACTIONS = {'create_page', 'extend_page', 'record_duplicate', 'attach_source'}
RELATIONS = {'distinct', 'new_version', 'variant', 'exact_duplicate'}


def decision_key(candidate):
    return candidate['content_digest']


def validate_decisions(document, request, root, checkout):
    if document.get('version') != 1:
        raise ValueError('Decision manifest must have version: 1')
    if document.get('context_digest') != request['context_digest']:
        raise ValueError('Decisions refer to stale wiki/registry context; review the refreshed materials')
    candidates = {item['candidate_id']: item for item in request['candidates']}
    pages = {item['page_id']: item for item in request['existing_pages']}
    implementations = request['registry'].get('implementations', {})
    selected, seen = [], set()
    for decision in document.get('decisions', []):
        identity = decision.get('candidate_id')
        if identity not in candidates or identity in seen:
            raise ValueError('Unknown or duplicate candidate decision: ' + str(identity))
        seen.add(identity)
        candidate = candidates[identity]
        if decision.get('content_digest') != decision_key(candidate):
            raise ValueError('Decision content binding mismatch: ' + identity)
        if decision.get('decision') not in {'include', 'exclude', 'defer'}:
            raise ValueError('Unknown review decision')
        if not isinstance(decision.get('rationale'), str) or not decision['rationale'].strip():
            raise ValueError('A substantive rationale is required')
        if not decision.get('evidence'):
            raise ValueError('Decisions require source evidence')
        for evidence in decision['evidence']:
            path = contained(checkout, evidence['path'])
            if evidence.get('sha256') != file_hash(path) or not evidence.get('locator'):
                raise ValueError('Invalid evidence receipt')
        if decision['decision'] != 'include':
            continue
        action, relation = decision.get('action'), decision.get('relation')
        if action not in ACTIONS or relation not in RELATIONS:
            raise ValueError('Invalid publication action or relation')
        if (action == 'create_page') != (relation == 'distinct'):
            raise ValueError('Distinct implementations must create pages; versions must target an existing implementation')
        if (action in {'record_duplicate', 'attach_source'}) != (relation == 'exact_duplicate'):
            raise ValueError('Duplicates must use record_duplicate')
        target = decision.get('target_implementation_id')
        if action == 'attach_source':
            if decision.get('target_page_id') not in pages:
                raise ValueError('Existing target page not found')
            if any(item['page_id'] == decision['target_page_id'] for item in implementations.values()):
                raise ValueError('Already registered; use record_duplicate')
            if not decision.get('equivalence_basis') or not decision.get('target_evidence'):
                raise ValueError('Existing-page attribution requires explicit equivalence evidence')
            for evidence in decision['target_evidence']:
                path = contained(root, evidence['path'])
                if not (evidence['path'].startswith('wiki/') or evidence['path'].startswith('artifacts/')):
                    raise ValueError('Target evidence must be existing wiki content or code assets')
                if evidence.get('sha256') != file_hash(path) or not evidence.get('locator'):
                    raise ValueError('Invalid target evidence receipt')
        elif action != 'create_page':
            if target not in implementations:
                raise ValueError('Target implementation is not registered')
            if implementations[target]['page_id'] != decision.get('target_page_id'):
                raise ValueError('Target implementation/page mismatch')
            if decision.get('target_version_id') not in implementations[target]['versions']:
                raise ValueError('Target version does not exist')
            if decision['target_page_id'] not in pages:
                raise ValueError('Target page does not exist')
            if relation == 'exact_duplicate':
                old = implementations[target]['versions'][decision['target_version_id']]['candidate']
                same_snapshot = old['candidate_id'] == identity
                exact = (candidate['fingerprints'] == old['fingerprints'] and candidate['entry'] == old['entry']
                         and not candidate['unresolved_dependencies'] and not old['unresolved_dependencies'])
                same_origin_content = (candidate['origin']['repo_id'] == old['origin']['repo_id']
                                       and candidate['content_digest'] == old['content_digest'])
                if not (same_snapshot or exact or same_origin_content):
                    raise ValueError('Duplicate requires complete matching receipts; use defer when uncertain')
        metadata = decision.get('metadata', {})
        for field in ('title', 'architectures', 'tags', 'kernel_types', 'languages', 'confidence', 'reproducibility'):
            if field not in metadata:
                raise ValueError('Missing metadata: ' + field)
        level = metadata['reproducibility']
        if level not in {'snippet', 'runnable', 'benchmarked'}:
            raise ValueError('Kernel reproducibility must be snippet, runnable, or benchmarked')
        if metadata['confidence'] not in {'source-reported', 'inferred', 'experimental', 'verified'}:
            raise ValueError('Invalid confidence')
        if not decision.get('confidence_basis'):
            raise ValueError('Explain confidence according to existing KernelWiki rules')
        receipts = decision.get('reproducibility_evidence', {})
        required = [] if level == 'snippet' else ['build', 'run', 'environment']
        if level == 'benchmarked':
            required += ['benchmark', 'inputs', 'method', 'results']
            if not decision.get('performance_claims'):
                raise ValueError('Benchmarked requires performance claims')
        for field in required:
            receipt = receipts.get(field, {})
            if receipt.get('basis') not in {'upstream-reported', 'locally-executed'}:
                raise ValueError('Evidence must identify upstream-reported or locally-executed basis: ' + field)
            path = contained(checkout, receipt.get('path', ''))
            if receipt.get('sha256') != file_hash(path) or not receipt.get('locator'):
                raise ValueError('Missing content-bound reproducibility receipt: ' + field)
        if metadata['confidence'] == 'verified' and not decision.get('evidence_basis'):
            raise ValueError('Verified must satisfy existing evidence_basis requirements')
        selected.append((candidate, decision))
    return selected, sorted(set(candidates) - seen) + [d['candidate_id'] for d in document.get('decisions', []) if d['decision'] == 'defer']


def rebind_manifest(manifest, request):
    """Reuse content-bound records only against exactly the saved wiki context."""
    if manifest.get('context_digest') != request['context_digest']:
        # A completed import may only reuse versions already admitted with the
        # same receipt. No new candidate is accepted against changed context.
        reused = []
        exclusions = {d['content_digest']: d for d in manifest.get('decisions', []) if d.get('decision') == 'exclude'}
        for candidate in request['candidates']:
            if candidate['content_digest'] in exclusions:
                reused.append({**exclusions[candidate['content_digest']], 'candidate_id': candidate['candidate_id']})
                continue
            for identity, implementation in request['registry']['implementations'].items():
                for version_id, version in implementation['versions'].items():
                    old = version['candidate']
                    if old['origin']['repo_id'] == candidate['origin']['repo_id'] and old['content_digest'] == candidate['content_digest']:
                        reused.append({**version['decision'], 'candidate_id': candidate['candidate_id'],
                                       'relation': 'exact_duplicate', 'action': 'record_duplicate',
                                       'target_implementation_id': identity, 'target_page_id': implementation['page_id'],
                                       'target_version_id': version_id})
                        break
        return {'version': 1, 'context_digest': request['context_digest'], 'decisions': reused}
    old = {item['content_digest']: item for item in manifest.get('decisions', [])}
    rebound = []
    for candidate in request['candidates']:
        if candidate['content_digest'] in old:
            rebound.append({**old[candidate['content_digest']], 'candidate_id': candidate['candidate_id']})
    return {'version': 1, 'context_digest': request['context_digest'], 'decisions': rebound,
            'review_provenance': manifest.get('review_provenance', {})}
