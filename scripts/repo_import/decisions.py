"""Read externally authored decisions. No model execution or prompt loading."""
from pathlib import Path
from .store import digest, file_hash, contained, read
from .selection import review_matches, expand_members, representative_ids

ACTIONS = {'create_page', 'extend_page', 'record_duplicate', 'attach_source', 'retain_page', 'merge_candidate'}
RELATIONS = {'distinct', 'new_version', 'variant', 'exact_duplicate'}


def validate_metadata(metadata, vocabulary):
    """Apply the wiki's field-specific vocabulary before list-only admission."""
    topical = ('hardware_features', 'techniques', 'kernel_types', 'languages')
    fields = ('tags', *topical, 'architectures', 'related', 'sources', 'prerequisites', 'aliases')
    for field in fields:
        if field not in metadata:
            continue
        values = metadata[field]
        if (not isinstance(values, list) or any(not isinstance(value, str) for value in values)
                or len(set(values)) != len(values)):
            raise ValueError('Metadata requires unique string lists: ' + field)
        allowed = (set().union(*(vocabulary.get(category, []) for category in topical))
                   if field == 'tags' else set(vocabulary.get(field, [])))
        if vocabulary and field in {'tags', *topical, 'architectures'} and set(values) - allowed:
            raise ValueError('Invalid metadata vocabulary for ' + field + ': ' + ', '.join(sorted(set(values) - allowed)))
    if 'hardware_features' in metadata and vocabulary:
        missing = (set(metadata.get('tags', [])) & set(vocabulary.get('hardware_features', []))
                   - set(metadata['hardware_features']))
        if missing:
            raise ValueError('Hardware tags missing from hardware_features: ' + ', '.join(sorted(missing)))


def decision_key(candidate):
    return candidate['content_digest']


def reuse_distinct_comparisons(previous, hints):
    """An unchanged match ID binds both candidate snapshots and the target receipt."""
    from copy import deepcopy
    current_batch = {hint['match_id'] for hint in hints if hint['kind'] == 'batch'}
    return [deepcopy(resolution) for resolution in previous.get('overlap_resolutions', [])
            if resolution['match_id'] in current_batch and resolution.get('outcome') == 'distinct']


def validate_target_evidence(decision, root):
    if not decision.get('equivalence_basis') or not decision.get('target_evidence'):
        raise ValueError('Explicit equivalence requires target evidence and a basis')
    for evidence in decision['target_evidence']:
        if not (evidence['path'].startswith('wiki/') or evidence['path'].startswith('artifacts/')):
            raise ValueError('Target evidence must be existing wiki content or code assets')
        path = contained(root, evidence['path'])
        if evidence.get('sha256') != file_hash(path) or not evidence.get('locator'):
            raise ValueError('Invalid target evidence receipt')
        if 'anchor' in evidence and (not isinstance(evidence['anchor'], str) or
                                     not evidence['anchor'].strip() or evidence['anchor'] not in path.read_text()):
            raise ValueError('Target evidence anchor must occur literally in the receipted content')


def shared_existing_page(group, hints, pages):
    """Explicitly covered branches may retain one existing page, without merging graphs."""
    scopes = []
    for _, decision in group:
        if decision.get('action') != 'retain_page' or decision.get('target_implementation_id'):
            return False
        path = pages[decision['target_page_id']]['path']
        anchors = {e['anchor'] for e in decision.get('target_evidence', [])
                   if e['path'] == path and e.get('anchor')}
        if not anchors or any(anchors & previous for previous in scopes):
            return False
        scopes.append(anchors)
        for other, _ in group:
            if other['candidate_id'] == decision['candidate_id']:
                continue
            matches = {h['match_id'] for h in hints[decision['candidate_id']]
                       if h['kind'] == 'batch' and h['candidate_id'] == other['candidate_id']}
            resolved = {r['match_id'] for r in decision.get('overlap_resolutions', [])
                        if r.get('outcome') == 'distinct'}
            if not matches or not matches <= resolved:
                return False
    return True


def reuse_record(candidate, previous, request, hints):
    if previous.get('action') not in {'retain_page', 'attach_source', 'merge_candidate'}:
        return None
    for identity, item in request['registry']['implementations'].items():
        if previous.get('target_implementation_id') and previous['target_implementation_id'] != identity:
            continue
        if previous.get('target_page_id') and previous['target_page_id'] != item['page_id']:
            continue
        if previous.get('target_version_id') and previous['target_version_id'] != item['current_version']:
            continue
        known = any(record['content_digest'] == candidate['content_digest'] and
                    record['origin']['repo_id'] == candidate['origin']['repo_id'] and
                    record['representative'] == item['current_version'] for record in item.get('records', []))
        if not known:
            continue
        page = next(page for page in request['existing_pages'] if page['page_id'] == item['page_id'])
        if item.get('managed') is False:
            receipt = item['versions'][item['current_version']].get('page_evidence', {})
            if receipt.get('path') != page['path'] or receipt.get('sha256') != page['sha256']:
                continue
        return {**previous, 'candidate_id': candidate['candidate_id'],
                'action': 'record_duplicate' if previous['relation'] == 'exact_duplicate' else 'retain_page',
                'target_implementation_id': identity, 'target_page_id': item['page_id'],
                'target_version_id': item['current_version'],
                'equivalence_basis': previous.get('equivalence_basis', 'Unchanged previously reviewed relationship and representative.'),
                'target_evidence': [
                    {**receipt, 'sha256': page['sha256']} if receipt['path'] == page['path'] else receipt
                    for receipt in previous.get('target_evidence', [])
                ] or [{'path': page['path'], 'sha256': page['sha256'], 'locator': item['page_id']}],
                'overlap_resolutions': [
                    {'match_id': hint['match_id'], 'outcome': 'same_implementation',
                     'representative': item['page_id'], 'evidence': [hint['evidence']],
                     'rationale': 'Unchanged reviewed relationship; retain the same representative.'}
                    for hint in hints if hint.get('page_id') == item['page_id'] and hint['kind'] in {'registry', 'kernel'}]
                    + reuse_distinct_comparisons(previous, hints)}
    return None


def unresolved_overlaps(decision, hints, decisions, root, checkout, all_hints):
    resolutions = {item['match_id']: item for item in decision.get('overlap_resolutions', [])}
    if len(resolutions) != len(decision.get('overlap_resolutions', [])):
        raise ValueError('Duplicate overlap resolution')
    if set(resolutions) - {hint['match_id'] for hint in hints}:
        raise ValueError('Unknown overlap resolution; prepare current materials')
    blocked = False
    for hint in hints:
        resolution = resolutions.get(hint['match_id'])
        if not resolution or resolution.get('outcome') not in {'distinct', 'same_implementation'}:
            blocked = True
            continue
        if not resolution.get('rationale') or not resolution.get('evidence'):
            blocked = True
            continue
        expected = hint['evidence']
        evidence = resolution['evidence']
        if not any(item.get('path') == expected['path'] and item.get('sha256') == expected['sha256'] for item in evidence):
            raise ValueError('Overlap resolution must cite the matched evidence')
        for receipt in evidence:
            path = contained(checkout if hint['kind'] == 'batch' else root, receipt['path'])
            if receipt.get('sha256') != file_hash(path) or not receipt.get('locator'):
                raise ValueError('Invalid overlap evidence receipt')
        if hint['kind'] == 'batch':
            other = decisions.get(hint['candidate_id'], {})
            reciprocal_ids = {item['match_id'] for item in all_hints[hint['candidate_id']]
                              if item['kind'] == 'batch' and item['candidate_id'] == decision['candidate_id']}
            for reciprocal in other.get('overlap_resolutions', []):
                if other.get('decision') == 'include' and reciprocal['match_id'] in reciprocal_ids and (
                        reciprocal.get('outcome') != resolution['outcome'] or
                        (resolution['outcome'] == 'same_implementation' and
                         reciprocal.get('representative') != resolution.get('representative'))):
                    blocked = True
        if resolution['outcome'] == 'distinct':
            if hint['kind'] == 'batch':
                other = decisions.get(hint['candidate_id'], {})
                if other.get('action') == 'merge_candidate' and other.get('target_candidate_id') == decision['candidate_id']:
                    blocked = True
            continue
        representative = resolution.get('representative')
        if hint['kind'] == 'batch':
            other = decisions.get(hint['candidate_id'], {})
            chosen = decisions.get(representative, {})
            if chosen.get('decision') != 'include' or chosen.get('action') not in {
                    'create_page', 'extend_page', 'attach_source', 'retain_page', 'record_duplicate'}:
                blocked = True
            for member in (decision, other):
                if member.get('decision') == 'include' and member.get('candidate_id') != representative:
                    if member.get('action') != 'merge_candidate' or member.get('target_candidate_id') != representative:
                        blocked = True
        elif hint['kind'] == 'pr':
            linked = hint.get('kernel_pages', [])
            if linked:
                if decision.get('action') == 'create_page':
                    distinct_pages = {h['page_id'] for h in hints if h['kind'] in {'kernel', 'registry'}
                                      and resolutions.get(h['match_id'], {}).get('outcome') == 'distinct'}
                    if representative != decision['candidate_id'] or not set(linked) <= distinct_pages:
                        blocked = True
                elif decision.get('target_page_id') not in linked:
                    blocked = True
            elif decision.get('action') == 'create_page' and representative != decision['candidate_id']:
                blocked = True
        else:
            if decision.get('target_page_id') != hint['page_id'] or decision.get('action') == 'create_page':
                blocked = True
            expected_representative = decision['candidate_id'] if decision.get('action') == 'extend_page' else hint['page_id']
            if representative != expected_representative:
                blocked = True
    return blocked


def validate_decisions(document, request, root, checkout, *, _matches=None):
    from .discovery import validate_discoveries
    validate_discoveries(request.get('discovered_overlaps'), request['candidates'],
                         request['existing_pages'], root, checkout)
    if document.get('version') != 1:
        raise ValueError('Decision manifest must have version: 1')
    if document.get('context_digest') != request['context_digest']:
        raise ValueError('Decisions refer to stale wiki/registry context; review the refreshed materials')
    if 'selection' in request and document.get('selection_digest') != digest(request['selection']):
        raise ValueError('Decisions refer to stale selection; review refreshed groups')
    document = expand_members(document, request)
    candidates = {item['candidate_id']: item for item in request['candidates']}
    pages = {item['page_id']: item for item in request['existing_pages']}
    implementations = request['registry'].get('implementations', {})
    # A selection refresh validates several trial documents against the same
    # immutable request. Its caller may share one freshly computed hint index.
    hints = review_matches(request) if _matches is None else _matches
    decisions = {item.get('candidate_id'): item for item in document.get('decisions', [])}
    blocked = set()
    selected, seen = [], set()
    vocabulary = read(root / 'data/tags.yaml')
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
        if unresolved_overlaps(decision, hints[identity], decisions, root, checkout, hints):
            blocked.add(identity)
            continue
        action, relation = decision.get('action'), decision.get('relation')
        if action not in ACTIONS or relation not in RELATIONS:
            raise ValueError('Invalid publication action or relation')
        if (action == 'create_page') != (relation == 'distinct'):
            raise ValueError('Distinct implementations must create pages; versions must target an existing implementation')
        if action != 'merge_candidate' and (action in {'record_duplicate', 'attach_source'}) != (relation == 'exact_duplicate'):
            raise ValueError('Duplicates must use record_duplicate')
        target = decision.get('target_implementation_id')
        if action == 'merge_candidate':
            other = decisions.get(decision.get('target_candidate_id'), {})
            if other.get('decision') != 'include' or other.get('action') not in {'create_page', 'extend_page', 'attach_source', 'retain_page', 'record_duplicate'}:
                raise ValueError('Batch merge must target an included representative, not another merge')
            if other['candidate_id'] == identity:
                raise ValueError('A candidate cannot merge into itself')
        elif action == 'attach_source' or (action == 'retain_page' and target not in implementations):
            if target is not None:
                raise ValueError('Unregistered existing-page attribution must not specify a target implementation')
            if decision.get('target_page_id') not in pages:
                raise ValueError('Existing target page not found')
            if pages[decision['target_page_id']].get('kind', 'kernel') != 'kernel':
                raise ValueError('Canonical target must be a kernel page, not a PR page')
            if any(item['page_id'] == decision['target_page_id'] for item in implementations.values()):
                raise ValueError('Already registered; use record_duplicate')
            validate_target_evidence(decision, root)
        elif action != 'create_page':
            if target not in implementations:
                raise ValueError('Target implementation is not registered')
            if action == 'extend_page' and implementations[target].get('managed') is False:
                raise ValueError('Existing kernel page replacement requires a separate reviewed page edit')
            if implementations[target]['page_id'] != decision.get('target_page_id'):
                raise ValueError('Target implementation/page mismatch')
            if decision.get('target_version_id') not in implementations[target]['versions']:
                raise ValueError('Target version does not exist')
            if decision['target_page_id'] not in pages:
                raise ValueError('Target page does not exist')
            if pages[decision['target_page_id']].get('kind', 'kernel') != 'kernel':
                raise ValueError('Canonical target must be a kernel page')
            if not any(hint.get('page_id') == decision['target_page_id'] and
                       any(resolution['match_id'] == hint['match_id'] and resolution['outcome'] == 'same_implementation'
                           for resolution in decision.get('overlap_resolutions', [])) for hint in hints[identity]):
                validate_target_evidence(decision, root)
            if relation == 'exact_duplicate':
                old = implementations[target]['versions'][decision['target_version_id']].get('candidate', {})
                same_snapshot = old.get('candidate_id') == identity
                exact = (candidate['fingerprints'] == old.get('fingerprints') and candidate['entry'] == old.get('entry')
                         and not candidate['unresolved_dependencies'] and not old['unresolved_dependencies'])
                same_origin_content = (candidate['origin']['repo_id'] == old.get('origin', {}).get('repo_id')
                                       and candidate['content_digest'] == old.get('content_digest'))
                if not (same_snapshot or exact or same_origin_content):
                    validate_target_evidence(decision, root)
        if action in {'extend_page', 'retain_page', 'merge_candidate'} and not decision.get('selection_reason'):
            raise ValueError('Representative selection requires a selection_reason')
        if any('anchor' in evidence for evidence in decision.get('target_evidence', [])):
            validate_target_evidence(decision, root)
        metadata = decision.get('metadata', {})
        for field in ('title', 'architectures', 'tags', 'kernel_types', 'languages', 'confidence', 'reproducibility'):
            if field not in metadata:
                raise ValueError('Missing metadata: ' + field)
        validate_metadata(metadata, vocabulary)
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
    targets = {}
    for identity, decision in decisions.items():
        if decision.get('decision') != 'include':
            continue
        candidate = candidates[identity]
        if decision.get('target_page_id') and decision.get('action') != 'merge_candidate':
            targets.setdefault(decision['target_page_id'], []).append((candidate, decision))
    for group in targets.values():
        existing_targets = [d for _, d in group if d.get('action') in {'attach_source', 'retain_page'} and not d.get('target_implementation_id')]
        if ((len(existing_targets) > 1 and (any(c['candidate_id'] in blocked for c, _ in group) or
                                           not shared_existing_page(group, hints, pages))) or
                (len(group) > 1 and any(d.get('action') == 'extend_page' for _, d in group))):
            blocked.update(c['candidate_id'] for c, _ in group)
    while True:
        newly_blocked = {c['candidate_id'] for c, d in selected if d['action'] == 'merge_candidate' and
                         d['target_candidate_id'] in blocked}
        if newly_blocked <= blocked:
            break
        blocked.update(newly_blocked)
    selected = [(c, d) for c, d in selected if c['candidate_id'] not in blocked]
    pending = (set(candidates) - seen) | blocked | {d['candidate_id'] for d in document.get('decisions', []) if d['decision'] == 'defer'}
    pending.update(r['candidate_id'] for r in request.get('selection', {}).get('entries', []) if r['role'] == 'pending')
    return selected, sorted(pending)


def rebind_manifest(manifest, request):
    """Reuse content-bound records only against exactly the saved wiki context."""
    rebind_candidates = request['candidates']
    if 'selection' in request:
        if 'selection' not in manifest:
            raise ValueError('Compact publication records require a separate full audit pack for preset reuse')
        if manifest.get('selection') != request['selection']:
            raise ValueError('Saved selection does not match current content')
        rebind_candidates = [c for c in request['candidates']
                             if c['candidate_id'] in representative_ids(request['selection'])]
    binding = {'selection_digest': digest(request['selection'])} if 'selection' in request else {}
    if manifest.get('context_digest') != request['context_digest']:
        hints = review_matches(request)
        # A completed import may only reuse versions already admitted with the
        # same receipt. No new candidate is accepted against changed context.
        reused = []
        includes = {d['content_digest']: d for d in manifest.get('decisions', []) if d.get('decision') == 'include'}
        exclusions = {d['content_digest']: d for d in manifest.get('decisions', []) if d.get('decision') == 'exclude'}
        for candidate in rebind_candidates:
            if candidate['content_digest'] in exclusions:
                reused.append({**exclusions[candidate['content_digest']], 'candidate_id': candidate['candidate_id']})
                continue
            for identity, implementation in request['registry']['implementations'].items():
                for version_id, version in implementation['versions'].items():
                    old = version.get('candidate')
                    if old is None:
                        continue
                    if old['origin']['repo_id'] == candidate['origin']['repo_id'] and old['content_digest'] == candidate['content_digest']:
                        reused.append({**version['decision'], 'candidate_id': candidate['candidate_id'],
                                       'relation': 'exact_duplicate', 'action': 'record_duplicate',
                                       'target_implementation_id': identity, 'target_page_id': implementation['page_id'],
                                       'target_version_id': version_id,
                                       'overlap_resolutions': [
                                           {'match_id': hint['match_id'], 'outcome': 'same_implementation',
                                            'representative': implementation['page_id'], 'evidence': [hint['evidence']],
                                            'rationale': 'Retain the previously admitted unchanged representative.'}
                                           for hint in hints[candidate['candidate_id']]
                                           if hint['kind'] == 'registry' and hint['implementation_id'] == identity]
                                       + reuse_distinct_comparisons(version['decision'], hints[candidate['candidate_id']])})
                        break
            if not any(row['candidate_id'] == candidate['candidate_id'] for row in reused):
                retained = reuse_record(candidate, includes.get(candidate['content_digest'], {}), request, hints[candidate['candidate_id']])
                if retained:
                    reused.append(retained)
        return {'version': 1, 'context_digest': request['context_digest'], 'decisions': reused, **binding}
    old = {item['content_digest']: item for item in manifest.get('decisions', [])}
    rebound = []
    for candidate in rebind_candidates:
        if candidate['content_digest'] in old:
            rebound.append({**old[candidate['content_digest']], 'candidate_id': candidate['candidate_id']})
    return {'version': 1, 'context_digest': request['context_digest'], 'decisions': rebound,
            'review_provenance': manifest.get('review_provenance', {}), **binding}
