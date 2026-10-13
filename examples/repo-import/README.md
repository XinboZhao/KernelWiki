# Public repository review examples

These are external review materials, not imported wiki contents. They do not
create pages, populate a registry, enable a preset, or appear in kernel queries.
No source implementation is embedded in the examples. Each example pins a public
repository commit and records candidate fingerprints, evidence and a decision.

- `quack-softmax-review.yaml`: review selects Softmax backward as an independent
  implementation and explicitly distinguishes its forward entry. The forward
  candidate has no admission decision and remains pending in this example.
- `flashmla-pending-review.yaml`: review identifies sparse decode device code,
  but defers publication until its relationship to existing FlashMLA/sparse-MLA
  pages is established. Finding device code does not bypass overlap review.

Example IDs, comparison hints and wiki-context digests belong to their recorded
snapshots. Run `prepare` for your chosen repository and scope, inspect current
matches, then adapt the decisions using current candidate/match IDs and evidence.
Do not treat `example_only` as a runtime permission switch: the examples are
outside the active decision directory and the default preset file is empty.

A build may publish a reviewed subset while keeping unresolved candidates
pending. Actual publication generates kernel/source pages, selected-version
registry records and indices only in the explicitly chosen target wiki. The
feature itself ships none of those import outputs.
