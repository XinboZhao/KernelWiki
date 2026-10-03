# Optional repository kernel import

The ordinary KernelWiki installation remains offline and needs no imported
repository. The optional importer is deterministic; external review is a
separate activity. It does not invoke a model or require model credentials.

Run from the wiki root:

```bash
python3 scripts/import_repo.py prepare --repo /path/to/repo --revision HEAD
# Read the printed run directory. An external agent follows
# references/repo-import-review.md and edits decisions.yaml there.
python3 scripts/import_repo.py build --run <run-id>
python3 scripts/import_repo.py apply --run <run-id>
python3 scripts/import_repo.py status --run <run-id>
```

Git URLs are also accepted. Local inputs must be repository roots. Only the
chosen commit is imported; uncommitted changes are reported and excluded.
Nested submodules are not initialized automatically. Modify the scan include
and exclude patterns through a YAML configuration, passed as `--config PATH`
before the subcommand. No NDA or DVT input is configured.

## Persistence and recovery

`data/repo-import.yaml` specifies `state_dir` and `checkout_dir`, defaulting to
ignored `.cache/repo-import/`. These directories persist until explicitly
removed. Absolute storage directories are supported. A run holds the snapshot,
inventory, matching suggestions, a snapshot of the review guide, external
decisions, staging files, validation
output and publication plan. Original agent conversations may be saved in
`review-attachments/`; only structured decisions are mandatory.

Re-run build after correcting decisions. Apply is repeatable for a committed
run. Interrupted apply has a backup journal; the importer recovers it before
retrying. Concurrent target changes stop publication. A changed wiki context
requires a new preparation; previously admitted unchanged implementations in
the same repo reuse their decisions, while changed candidates remain pending.
Review excludes and deferrals are retained in decision manifests. No prompt
version change alone invalidates prior admission.

## Presets

Add a public repository and its externally reviewed manifest to
`data/repo-import-presets.yaml`:

```yaml
version: 1
presets:
  example:
    repo: https://github.com/owner/example.git
    revision: <full-commit>
    decision_manifest: data/repo-import/decisions/<repo-id>/<review-run>.yaml
```

Then run `python3 scripts/import_repo.py import --preset example`. The repository
snapshot, decision receipts and referenced wiki context must match. Unknown or
changed candidates stop the command at external review. No unconditional
skip-review option exists. The shipped manifest intentionally has no enabled
presets: existing private-source decisions are not imported into this public
feature. Create public presets by reviewing the chosen snapshots first.

## Publication

Formal output consists of `sources/repos/` provenance pages,
`wiki/kernels/imported/` implementation pages, a compact registry and decisions
under `data/repo-import/`, and generated query indices. The registry preserves
version branches and source origins. Identical versions extend attribution;
new versions have separately bound reproducibility evidence. No execution
levels are added. Only explicitly selected definitions appear in code fences; full defining
files and dependencies remain bound by review receipts and are available in
the pinned source snapshot. Large snapshots may exceed the wiki size budget and
must be narrowed or left unpublished.

Apply first generates indices and runs the existing validator and size check
in an isolated workspace. Formal source validation remains offline and does
not need the checkout cache. Imported contents must satisfy existing scope,
evidence, vocabulary and performance rules. Existing manual pages can receive reviewed duplicate-source attribution via
`attach_source`; their prose and reproducibility are preserved. Their later
implementation updates require manual editing and are never replaced wholesale.
