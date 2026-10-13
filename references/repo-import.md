# Optional repository kernel import

The importer is optional. It accepts a Git URL or a local Git repository root,
pins a commit, prepares review materials, and consumes decisions from an external
reviewer. It never invokes an AI model, executes downloaded kernels, or creates a
Git commit. An ordinary non-Git folder is rejected because it has no pinned
repository provenance.

Only files tracked by the input repository are scanned, including normal
subdirectories. Gitlinks are recorded in `snapshot.yaml.skipped_submodules` and
never initialized, fetched or scanned. There is no submodule expansion option.
Uncommitted worktree changes are excluded and recorded.

## Commands

Run from the wiki root:

```bash
python3 scripts/import_repo.py prepare --repo /path/to/repo --revision HEAD
# Review the printed run directory independently and edit decisions.yaml.
python3 scripts/import_repo.py build --run <run-id>
python3 scripts/import_repo.py apply --run <run-id>
python3 scripts/import_repo.py status --run <run-id>
```

Use `--config PATH` or `--wiki-root PATH` before the subcommand. Scan include and
exclude patterns use fnmatch; configure nested exclusion patterns explicitly
when required. Local input must be the repository root, not an arbitrary folder
inside it. A run ID or a full run-directory path is accepted by `--run`.

## Review and unresolved overlap

The run saves candidate entries, source/dependency hashes, unresolved imports,
parse failures, existing kernel and PR pages, code-asset receipts, matching hints,
and a snapshot of `references/repo-import-review.md`.

Hints cover registered implementations, existing kernel pages and PR assets,
and same-batch candidates. They are conservative comparisons, not proofs of
semantic equivalence. They may include false positives and cannot guarantee that
all duplicate implementations are detected.

Every hint for an included candidate needs an `overlap_resolutions` record:
`match_id`, `outcome` (`distinct` or `same_implementation`), rationale, and
content-bound evidence citing the matched page/file. For the same implementation,
choose a `representative` (candidate ID or canonical page ID). Missing or
unresolved relationships keep that candidate pending; unrelated reviewed
candidates may still publish. Deleting hints from saved materials cannot bypass
validation: current matching context is checked again.

For an existing PR with a linked kernel page, reuse that page. If the PR only
records the implementation and no canonical kernel page exists, create one and
cite the PR as well as the repository snapshot. An existing PR is a source,
not a separate canonical kernel implementation.

## One representative per implementation

Here, an existing kernel page means a page already in the wiki whose body is
maintained outside this importer. The term describes importer ownership,
independent of who authored the page. Importer-generated pages can be updated
through `extend_page`; existing-page attribution preserves the original body.

- `create_page` / `distinct`: create a canonical page for a genuinely different
  implementation, with resolved comparisons.
- `attach_source` / `exact_duplicate`: retain an unregistered existing kernel page,
  cite explicit equivalence evidence, and add repository attribution.
- `record_duplicate` / `exact_duplicate`: reuse a registered representative and
  add source attribution.
- `extend_page` / `new_version` or `variant`: select the incoming implementation
  as the new representative of the existing page.
- `retain_page` / `new_version` or `variant`: retain the existing representative;
  save only the incoming relationship and selection reason.
- `merge_candidate`: select another included candidate in the same batch as the
  representative; no additional canonical page is created for the merged entry.

Selection actions require `selection_reason`. Choose based on applicable
evidence, reproducibility, scope and teaching value, not commit recency alone.
Existing kernel page prose is never automatically replaced; body changes to such pages
require a separate reviewed page edit rather than `extend_page`.

The runtime registry stores one full representative version per implementation.
Other versions/variants retain compact origin, digest, relationship and reason
records; full scan and review history remains in persistent run storage. The
page shows only the representative. Its confidence, reproducibility and metrics
come from that representative's own evidence, not a discarded variant.

## Persistence and publication

`data/repo-import.yaml` defines `state_dir` and `checkout_dir`, defaulting to
ignored `.cache/repo-import/`. Absolute paths are supported. Run history persists
until explicitly removed; retention and backups are user-managed. A run includes
snapshot, inventory, matching, guide, decisions, optional `review-attachments/`,
staging, validation results, publication plan and backup/transaction journal.

Formal outputs are created only after a user executes import into a target wiki:
`sources/repos/`, `wiki/kernels/imported/`, registry and compact decisions under
`data/repo-import/`, license notices and query indices. Unedited pending templates
remain in run storage. The distributed feature has no populated registry,
imported kernel/source pages, or default enabled preset.

Apply first generates indices and runs page/registry and size validation in an
isolated copy. Publication uses a lock, before/after file hashes, backups and a
recoverable journal. Interrupted writes recover before context checks; concurrent
edits stop publication/recovery. A repeated successful apply does not write again.
Transaction status `committed` means file publication completed, not a Git commit.

Content changes invalidate old decisions. Changed wiki pages or PR code assets
require a new preparation. Previously admitted unchanged representatives may
reuse decisions if all current overlaps are resolved. Guide-version changes alone
do not invalidate prior decisions. Higher execution levels require committed,
content-bound evidence, and the importer performs no GPU validation.

## Examples and presets

[Public review examples](../examples/repo-import/README.md) include Quack and
FlashMLA decisions and explanations without publication outputs. Adapt them to
fresh materials rather than blindly copying stale context or IDs.

The default `data/repo-import-presets.yaml` is empty. A user can explicitly add a
preset pinning `repo`, `revision`, `decision_manifest`, and optional scan config,
then run `python3 scripts/import_repo.py import --preset <name>`. Preset import
reuses valid saved review; changed candidates or unresolved overlaps stop it at
pending. There is no unconditional skip-review option.
