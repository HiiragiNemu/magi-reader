# Official Exedra source automation

Reader production accepts only immutable source notifications from the private
`madoka-exedra-wiki/ma-ex-data` producer repository:

- `exedra_tw_source_v1` points to a content-addressed Release ZIP and its v1
  handoff contract. The archive, contract, source revisions, provenance, and
  dynamic coverage partition are verified before import.
- `exedra_jp_source_v1` points to one full producer commit. Reader checks out
  only `gamedata/Resources/Scenarios`, selects unsuffixed official JP JSON,
  records a source receipt, and rebuilds the Exedra indexes.

Repository configuration:

1. Add Reader secret `EXEDRA_WIKI_SOURCE_TOKEN`, scoped read-only to the exact
   private producer repository.
2. Keep Reader variable `EXEDRA_READER_AUTOMATION_ENABLED=false` while testing
   both workflows through `workflow_dispatch` with immutable inputs.
3. After both manual runs pass, set the variable to `true` so verified producer
   events are accepted automatically.

Both workflows fail closed on source or coverage drift, reject generated changes
outside their explicit machine-output allowlists, commit with the verified source
receipt, and invoke the reusable production deploy workflow directly. They do
not rely on a bot-authored `push` event to deploy.
