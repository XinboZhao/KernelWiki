# External review of repository kernels

This guide is for an external agent or reviewer. The importer never invokes a
model, executes this prompt, or requires a particular model or prompt version.

## Origin of the rules

KernelWiki's `CLAUDE.md` and `references/schema.md` define scope, confidence,
reproducibility and performance contracts. The archived Phase 2 plan
(`data/plan-supersession-baselines/plan-phase2.body.md`) supplies the historical
include/exclude/defer pattern. Current `scripts/pr_policy.py` tests refine the
positive device-evidence requirement. These are source rules, not a claim that
a complete original review prompt was preserved. Representative selection and
explicit content-bound entry allowlists have also been adapted from the existing
extension importer; this guide introduces no private source content.

## Suggested review prompt

Review the candidates in `review-request.yaml` against the pinned checkout,
`matches.yaml`, existing kernel pages and their source evidence. The input is a
repository snapshot, not a PR. Do not assume that every function in a kernel
file or every `@triton.jit` function is a launchable kernel.

1. Identify actual device implementations and their entry points. Exclude host
   wrappers, support helpers, tests and unrelated generated material. A file
   extension, tuning variable, kernel-like name or host launch syntax alone is
   insufficient. Inspect callers where needed.
2. Preserve worthwhile operation families and implementations, including
   architecture/language differences. Collapse redundant dtype/tile/launch
   variants only when their behavior and teaching value are genuinely shared.
   Do not merge implementations solely by operation name.
3. Compare signatures, full defining files, helpers, macros, templates and
   configuration. Unresolved dependencies are uncertainty, not proof of
   equivalence. Use `exact_duplicate`, `new_version`, `variant`, or `distinct`.
   Renamed/moved implementations and diverged forks require evidence. Do not
   invent a linear version order across independent repositories.
4. Select existing `confidence` values according to KernelWiki's definitions;
   repository existence and review approval do not establish `verified`.
   Select only `snippet`, `runnable` or `benchmarked` for publication. runnable
   requires a complete build/run example; benchmarked also requires input,
   environment, method and result evidence. Distinguish upstream reports from
   locally executed evidence. Never transfer old measurements to changed code
   without evidence that they apply.
5. Keep Blackwell-first scope, explicit Hopper relevance where required,
   controlled architecture/language vocabulary and English canonical pages.
   Unknown architecture remains unknown. Do not fabricate performance numbers,
   dependencies, provenance or correctness results.
6. For uncertainty, use `defer` with an actionable rationale. Otherwise explain
   include/exclude using exact source locators. Fill `decisions.yaml`; retain
   its candidate IDs, content digests and wiki context digest. Preserve raw
   agent input/output in `review-attachments/` when available.

## Output contract

```yaml
version: 1
context_digest: <copied from review-request.yaml>
review_provenance:
  reviewer: <agent or person>
  guide: repo-import-review-v1  # informational; not an invalidation switch
decisions: []                 # see complete example below
```

A complete snippet-level decision:

```yaml
version: 1
context_digest: <copied value>
decisions:
  - candidate_id: <copied value>
    content_digest: <copied value>
    decision: include
    rationale: <specific reason and uncertainty limits>
    evidence:
      - path: kernels/example.py
        sha256: <file receipt from inventory>
        locator: <function name or exact section>
    relation: distinct
    action: create_page
    confidence_basis: <explain the existing confidence choice>
    metadata:
      title: Example kernel
      architectures: []
      tags: [reduction]
      kernel_types: [reduction]
      languages: [triton]
      confidence: experimental
      reproducibility: snippet
```

For `new_version` or `variant`, use `extend_page`, and specify
`target_implementation_id`, `target_page_id`, and `target_version_id` from the
registry. For `exact_duplicate`, use `record_duplicate` with the same target
fields. For a duplicate of an existing unregistered/manual page, use `attach_source`
and `target_page_id`, plus `equivalence_basis` and `target_evidence` receipts
(path, sha256, locator of the existing wiki page or code asset). The external
reviewer must justify equivalence; a title match is insufficient. This adds
attribution and an implementation identity while preserving the existing prose
and reproducibility. Future body changes to manual pages remain deferred for
manual editing; the importer never replaces their prose.

For runnable, add `reproducibility_evidence` entries `build`, `run`, and
`environment`. For benchmarked also add `benchmark`, `inputs`, `method`, and
`results`, plus `performance_claims` in the existing schema. Each receipt has
`path`, `sha256`, `locator`, and `basis` (`upstream-reported` or
`locally-executed`). Receipts reference committed files in the pinned input
repository; local execution reports must be committed to a reviewed snapshot
before they can support a higher reproducibility level. The importer does not
execute downloaded programs.
