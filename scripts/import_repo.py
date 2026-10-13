#!/usr/bin/env python3
"""Prepare repo candidates; consume external decisions; publish validated pages."""
import argparse
import datetime
import json
import subprocess
import sys
import uuid
from pathlib import Path

from repo_import.checkout import git, resolve_snapshot
from repo_import.config import load_config, load_preset, merge
from repo_import.decisions import rebind_manifest, reuse_distinct_comparisons, reuse_record, validate_decisions
from repo_import.match import context_digest, existing_index, overlap_index, registry
from repo_import.publish import apply_plan, build_plan, validate_plan, recover_transaction
from repo_import.scan import scan_snapshot
from repo_import.store import contained, digest, file_hash, read, write, atomic_write

ROOT = Path(__file__).resolve().parents[1]


def storage(root, configured):
    path = Path(configured).expanduser()
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def prepare(root, repo, revision, config):
    run_id = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + uuid.uuid4().hex[:8]
    run = storage(root, config['state_dir']) / run_id
    run.mkdir(parents=True)
    write(run / 'result.yaml', {'run_id': run_id, 'status': 'preparing'})
    try:
        snapshot = resolve_snapshot(repo, revision, storage(root, config['checkout_dir']))
        inventory = scan_snapshot(snapshot, config['scan'])
        registered, pages = registry(root), existing_index(root)
        request = {'version': 1, 'run_id': run_id, 'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                   'snapshot': snapshot, 'scan_config': config['scan'], **inventory,
                   'registry': registered, 'existing_pages': pages,
                   'context_digest': context_digest(pages, registered)}
        matches = overlap_index(inventory['candidates'], registered, pages)
        request['matches'] = matches
        write(run / 'request.yaml', {'repo': repo, 'revision': revision, 'config': config})
        write(run / 'snapshot.yaml', snapshot)
        write(run / 'inventory.yaml', inventory)
        write(run / 'review-request.yaml', request)
        write(run / 'matches.yaml', matches)
        guide = root / 'references/repo-import-review.md'
        if guide.exists():
            atomic_write(run / 'review-guide.md', guide.read_text())
        decisions = []
        prior_exclusions = {}
        prior_includes = {}
        prior_dir = root / 'data/repo-import/decisions' / snapshot['repo_id']
        if prior_dir.exists():
            for path in sorted(prior_dir.glob('*.yaml')):
                for decision in read(path).get('decisions', []):
                    if decision.get('decision') == 'exclude':
                        prior_exclusions[decision['content_digest']] = decision
                    elif decision.get('decision') == 'include':
                        prior_includes[decision['content_digest']] = decision
        for candidate in inventory['candidates']:
            # A previously admitted unchanged same-repository version can be reused.
            reused = None
            for identity, implementation in registered['implementations'].items():
                for version_id, version in implementation['versions'].items():
                    old = version.get('candidate')
                    if old is None:
                        continue
                    if (old['origin']['repo_id'] == candidate['origin']['repo_id'] and
                            old['content_digest'] == candidate['content_digest']):
                        reused = {**version['decision'], 'candidate_id': candidate['candidate_id'],
                                  'relation': 'exact_duplicate', 'action': 'record_duplicate',
                                  'target_implementation_id': identity, 'target_page_id': implementation['page_id'],
                                  'target_version_id': version_id}
                        reused['overlap_resolutions'] = [
                            {'match_id': hint['match_id'], 'outcome': 'same_implementation',
                             'representative': implementation['page_id'],
                             'rationale': 'Unchanged previously admitted content; retain its canonical page.',
                             'evidence': [hint['evidence']]}
                            for hint in matches[candidate['candidate_id']]
                            if hint['kind'] == 'registry' and hint['implementation_id'] == identity]
                        reused['overlap_resolutions'] += reuse_distinct_comparisons(version['decision'], matches[candidate['candidate_id']])
                        break
            if not reused and candidate['content_digest'] in prior_exclusions:
                reused = {**prior_exclusions[candidate['content_digest']], 'candidate_id': candidate['candidate_id']}
            if not reused:
                reused = reuse_record(candidate, prior_includes.get(candidate['content_digest'], {}),
                                      request, matches[candidate['candidate_id']])
            if reused:
                try:
                    _, pending = validate_decisions({'version': 1, 'context_digest': request['context_digest'],
                                        'decisions': [reused]}, request, root, Path(snapshot['checkout']))
                    if candidate['candidate_id'] in pending:
                        reused = None
                except ValueError:
                    reused = None
            if reused:
                decisions.append(reused)
            else:
                decisions.append({'candidate_id': candidate['candidate_id'], 'content_digest': candidate['content_digest'],
                                  'decision': 'defer', 'rationale': 'Pending external review',
                                  'evidence': [{'path': candidate['path'], 'sha256': candidate['fingerprints']['source_sha256'],
                                                'locator': candidate['entry']}]})
        write(run / 'decisions.yaml', {'version': 1, 'context_digest': request['context_digest'], 'decisions': decisions})
        atomic_write(run / 'review.md', '# External kernel review\n\nRead references/repo-import-review.md in KernelWiki.\n'
                     'Inspect review-request.yaml, matches.yaml and the pinned checkout.\n'
                     'Edit decisions.yaml; do not change the source snapshot.\n'
                     'Save original agent input/output under review-attachments/ if available.\n')
        write(run / 'result.yaml', {'run_id': run_id, 'status': 'pending', 'candidates': len(inventory['candidates']),
                                   'parse_failures': len(inventory['failures'])})
        return run
    except Exception as error:
        write(run / 'result.yaml', {'run_id': run_id, 'status': 'failed', 'error': str(error)})
        raise


def check_snapshot(request):
    snapshot = request['snapshot']
    checkout = Path(snapshot['checkout'])
    if git(checkout, 'rev-parse', 'HEAD') != snapshot['commit'] or git(checkout, 'status', '--porcelain'):
        raise ValueError('Pinned checkout was modified; prepare a new run')
    current = scan_snapshot(snapshot, request['scan_config'])
    if current != {k: request[k] for k in ('candidates', 'failures')}:
        raise ValueError('Snapshot receipts changed')


def check_context(root, request):
    pages, registered = existing_index(root), registry(root)
    if (request['context_digest'] != context_digest(pages, registered) or
            request['existing_pages'] != pages or request['registry'] != registered or
            request['matches'] != overlap_index(request['candidates'], registered, pages)):
        raise ValueError('Wiki or matching materials changed; prepare again')


def build(root, run):
    request = read(run / 'review-request.yaml')
    check_snapshot(request)
    check_context(root, request)
    document = read(run / 'decisions.yaml')
    selected, pending = validate_decisions(document, request, root, Path(request['snapshot']['checkout']))
    plan = build_plan(root, run, request, document, selected)
    write(run / 'result.yaml', {'run_id': request['run_id'], 'status': 'built',
                               'included': len(selected), 'pending': pending})
    return plan


def apply(root, run):
    # Restore interrupted writes before comparing the saved wiki context.
    if read(run / 'transaction.yaml').get('status') == 'applying':
        import fcntl
        lock = root / '.cache/repo-import/publish.lock'
        lock.parent.mkdir(parents=True, exist_ok=True)
        with lock.open('a') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            recover_transaction(root, run)
    if read(run / 'transaction.yaml').get('status') == 'committed':
        write(run / 'result.yaml', {**read(run / 'result.yaml'), 'status': 'applied'})
        print('Already applied; no changes')
        return
    request = read(run / 'review-request.yaml')
    check_snapshot(request)
    plan = read(run / 'publication-plan.yaml')
    if plan.get('run_id') != request['run_id']:
        raise ValueError('Build this run before applying it')
    if plan.get('request_digest') != digest(request) or plan.get('decisions_digest') != digest(read(run / 'decisions.yaml')):
        raise ValueError('Review materials changed after build; rebuild required')
    check_context(root, request)
    if not plan.get('validated_digest'):
        validate_plan(root, run, plan)
    apply_plan(root, run, plan)
    write(run / 'result.yaml', {**read(run / 'result.yaml'), 'status': 'applied'})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wiki-root', type=Path, default=ROOT)
    parser.add_argument('--config', type=Path)
    sub = parser.add_subparsers(dest='command', required=True)
    prepare_parser = sub.add_parser('prepare')
    prepare_parser.add_argument('--repo', required=True)
    prepare_parser.add_argument('--revision')
    for command in ('build', 'apply', 'status'):
        child = sub.add_parser(command)
        child.add_argument('--run', required=True, help='Run ID or full persistent run directory')
    preset_parser = sub.add_parser('import')
    preset_parser.add_argument('--preset', required=True)
    args = parser.parse_args()
    root = args.wiki_root.resolve()
    config = load_config(root, args.config)
    run = None
    try:
        if args.command == 'prepare':
            run = prepare(root, args.repo, args.revision, config)
        elif args.command == 'import':
            preset = load_preset(root, args.preset, config)
            run = prepare(root, preset['repo'], preset['revision'], merge(config, preset.get('config', {})))
            request = read(run / 'review-request.yaml')
            manifest = read(contained(root, preset['decision_manifest']))
            document = rebind_manifest(manifest, request)
            write(run / 'decisions.yaml', document)
            selected, pending = validate_decisions(document, request, root, Path(request['snapshot']['checkout']))
            if pending:
                raise ValueError(f'{len(pending)} candidates need external review; materials: {run}')
            build(root, run)
            apply(root, run)
        else:
            path = Path(args.run).expanduser()
            run = path.resolve() if path.is_dir() else contained(storage(root, config['state_dir']), args.run)
            if args.command == 'build':
                build(root, run)
            elif args.command == 'apply':
                apply(root, run)
            else:
                print(json.dumps(read(run / 'result.yaml'), indent=2))
        if args.command != 'status':
            print(f'Run directory: {run}')
        return 0
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as error:
        if run and run.exists():
            write(run / 'last-error.yaml', {'command': args.command, 'error': str(error)})
        print(f'ERROR: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
