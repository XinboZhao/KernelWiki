# External review of repository kernels

This guide is for an external agent or human reviewer. The importer never
executes this prompt, invokes a model, or requires a specific model or prompt
version. It prepares materials and validates saved decisions.

## Basis and scope

The existing `CLAUDE.md` and `references/schema.md` define wiki scope, confidence,
reproducibility and performance contracts. The archived Phase 2 plan supplies the
include/exclude/defer pattern, and current `scripts/pr_policy.py` refines positive
device evidence. Representative selection and content-bound entry allowlists
are adapted to repository input. This is an adapted guide, not a claim that all
historical prompt wording was preserved.

Review only the pinned input repository's tracked files. Submodules are listed
as skipped and are not part of its kernel inventory. A Git repo is required for
provenance. Review originals and callers; a file extension, function name or
`@triton.jit` decorator alone does not establish an actual launchable kernel.

## Suggested prompt

Read `review-request.yaml`, `matches.yaml`, the pinned source checkout and the
existing kernel/PR pages and code evidence included in the context.

1. Identify actual device implementations. Inspect host launchers, template
   dispatch, macros and helpers. Exclude host-only wrappers, support helpers,
   unrelated tests and generated material. Report unresolved dependencies rather
   than treating them as proof of equivalence.
2. Preserve worthwhile operation families and genuinely different implementations.
   Follow Blackwell-first scope, existing Hopper relevance requirements,
   controlled vocabulary and English canonical page conventions. Do not guess
   an architecture when source evidence is missing.
3. Resolve every discovered overlap before inclusion. Compare registry entries,
   existing kernel pages, PR code assets and same-batch candidates. Cite the
   matched evidence and the input source. Decide `distinct` or
   `same_implementation`; explain mathematical behavior, signatures, helper and
   dependency differences. Renaming and repo names alone do not decide identity.
4. For the same implementation, choose one representative using applicable
   evidence, reproducibility, intended scope and teaching value. Do not simply
   prefer the newest commit. Different sources, newer versions and tuning
   variants share a single canonical kernel page. Keep the existing page when
   it is the better representative. Explain the selection reason.
5. If a PR already links to a canonical kernel page, reuse it. If only PR source
   records exist, a new canonical kernel page may cite that PR and the repo.
   Do not create another PR page or copy its prose as a second implementation.
6. Choose existing confidence values with a `confidence_basis`. Review approval
   and repo existence do not imply verified confidence. Choose only snippet,
   runnable or benchmarked reproducibility. Higher levels require applicable
   content-bound evidence. Identify upstream-reported versus locally-executed
   evidence. Never transfer discarded-version metrics to the selected version.
7. Use `defer` for unresolved relationships or insufficient evidence. Explain
   the next comparison or evidence needed. Only those candidates stay pending;
   unrelated resolved candidates may publish. A simple include cannot bypass
   overlap resolution. Do not fabricate provenance, correctness or performance.
8. Save structured decisions, with current content/context hashes and IDs.
   Preserve original agent input/output under `review-attachments/` when
   available. No prompt-version change alone invalidates saved admission.

## Decision output

The document has `version: 1`, the prepared `context_digest`, optional
`review_provenance`, and `decisions`. Every row requires candidate/content IDs,
include/exclude/defer, a substantive rationale and source evidence. Evidence
receipts have path, SHA-256 and locator. Use current prepared values.

For each hint on an included candidate, add a resolution:

```yaml
overlap_resolutions:
  - match_id: <copied match-id>
    outcome: distinct
    rationale: <specific comparison explaining a different implementation>
    evidence:
      - path: <matched page or code path>
        sha256: <copied receipt>
        locator: <compared entry, source section or exact lines>
```

For `same_implementation`, also set `representative` to the selected candidate
ID or existing canonical page ID. A batch representative must be included and
must not itself merge into another candidate. Reciprocal decisions must agree;
multiple candidates cannot each create a page while declaring the same identity.
Do not edit or remove prepared hints. Build/apply checks current source and wiki
context, including PR code hashes.

## Publication actions

Existing kernel page refers here to a page already in the wiki whose body is
maintained outside this importer. It makes no assumption about the author or
the tool originally used to create it.

| Relationship | Action | Representative choice |
| --- | --- | --- |
| distinct | create_page | Incoming implementation gets its own page after all comparisons resolve. |
| exact_duplicate | record_duplicate | Existing registered page remains; add source attribution. |
| exact_duplicate of an existing kernel page | attach_source | Existing page remains; add attribution and registry identity. |
| new_version or variant | extend_page | Incoming version replaces the representative on the same managed page. |
| new_version or variant | retain_page | Existing representative remains; retain a compact incoming relation. |
| exact_duplicate, new_version or variant within a batch | merge_candidate | Another included candidate represents the implementation. |

Registered targets require `target_implementation_id`, `target_page_id` and
`target_version_id`. Batch merge requires `target_candidate_id`. Selection
through extend/retain/merge requires `selection_reason`.

For an unregistered existing kernel page, attach_source requires `target_page_id`,
`equivalence_basis` and `target_evidence` receipts in wiki or code assets. Existing
prose and reproducibility are preserved. Automatic body replacement of an existing kernel
page is not supported; such edits require a separate reviewed page edit.

An existing kernel page can also remain the representative of an incoming new_version or
variant: use retain_page with target_page_id, equivalence_basis, target_evidence,
and selection_reason, without a target implementation/version until registered.
The registry stores the selected existing kernel page's receipt and actual classification;
incoming content is only a compact relationship record. A reviewed equivalent
copy whose fingerprints differ may use record_duplicate with explicit input and
target comparison evidence, not name-based equivalence.

The selected representative is the only full version stored in the runtime
registry. Nonselected versions preserve compact origin, content digest,
relationship and reason, with full review history in run storage. The registry
is an importer bookkeeping file, not an additional user-facing kernel page.

## Confidence and execution evidence

Use the existing wiki definitions for source-reported, inferred, experimental
and verified. Verified must also satisfy the existing validator's source and
`evidence_basis` contracts. Do not equate this with a local GPU correctness run.

Runnable requires `reproducibility_evidence` build, run and environment receipts.
Benchmarked additionally requires benchmark, inputs, method and results receipts,
plus valid `performance_claims`. Each receipt names a committed snapshot file,
SHA-256, locator and basis (`upstream-reported` or `locally-executed`). Local
reports must already belong to the reviewed snapshot; the importer does not
create commits or execute programs to obtain them.

See [public example reviews](../examples/repo-import/README.md) for an included
Quack entry with an explicit forward/backward distinction and a deferred
FlashMLA candidate with unresolved existing-page overlap. These examples are
review materials only, not preinstalled wiki kernels or default presets.
