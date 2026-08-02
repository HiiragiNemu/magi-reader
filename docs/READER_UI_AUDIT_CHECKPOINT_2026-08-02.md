# Reader/editor UI audit checkpoint — 2026-08-02

Scope audited: the uncommitted reader/editor UI work under `website/` only.
`generate_story_index.py`, voice data, and portrait directories were not edited.

## Confirmed behavior

- Reader width is clamped to 640–1280 px in 32 px steps and is retained in
  local storage. The `w-full` reader container keeps that maximum width from
  overflowing narrow screens.
- The Japanese/Chinese comparison can be selected as desktop side-by-side or
  stacked; narrow screens use the stacked layout for both reading and editing.
- Newline markers are an opt-in visual layer. Reading keeps actual newlines;
  the editing overlay preserves the textarea value and is capped at 200
  markers.
- TXT exports are UTF-8 with exactly one byte-order mark and CRLF line endings
  for mobile editors. JSON exports are BOM-free UTF-8 JSON.
- JSON source selection is per Section. JP and CN originals are downloaded
  independently; an edited output is generated only after event/structure
  validation. The output validator permits only mapped string text/name fields
  (and the explicit missing `textHome` subtitle insertion), rejects playback
  structure changes, and round-trips normal Magia Record/Exedra scripts before
  download. General-voice playback fields are preserved by shape checks.
- Machine-translation lists remain collapsed behind their existing `details`
  controls; the reader format-warning list is also collapsed.

## Verification run

From `website/`:

```powershell
npm test -- lib/browser-download.test.ts lib/reader-display-preferences.test.ts lib/scenario-json-download.test.ts lib/scenario-json-selection.test.ts lib/story-json-source.test.ts tests/bilingual-layout.test.mjs tests/story-text.test.mjs tests/scenario-json-reader-ui.test.mjs
npm run type-check
```

Result: 36 targeted Node tests passed; TypeScript completed with no errors.

## Runtime catalog spot check

`website/public/story_index.json` (3,012 entries) contains no story whose JP
or CN `json_sources_*` list repeats a JSON basename. There are also no current
JP/CN basename pairs that resolve to different paths below `Scenarios_full`.
This supports the present Section selector's filename pairing for the checked
catalog snapshot.
