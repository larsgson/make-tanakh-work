# Changelog

Tags are `vMAJOR.MINOR.PATCH`. A work copy merges a tag; make-tanakh-grammar pins one (`docs/related-repos.md`).
Each entry has a **Format changes** section for the stable formats listed in `docs/related-repos.md`, section 4:
what changed and how existing files move over. Before 1.0 a breaking format change raises the minor version.

## v0.13.0

**Stories rebuilt, not published** (the work copy's proposal, agreed by the user 2026-11-26: story files repeat the
chapters).

- **`scripts/stories.py build <story> --project P | --from-repo DIR`**: a story's readings in its order (`.txt`,
  `.tsv`) from a project's drafts or from a language repository's chapters (make-tanakh-review FORMAT.md). Partial
  readings are cut by the `.align` (the work copy's excerpt rules); readings the drafts lack are quoted from an open
  style edition (credited) or only referenced from a non-free one; the missing ones are listed. Output in
  `export/<p>/stories/` (now git-ignored) or `--out`. `stories.py list` shows the lists found.
- **Reading lists** in `import/stories/<licence>/<id>/` (`story.yaml`, `<id>.readings.tsv`; docs/stories.md), never
  in git. `setup.py --only stories` fetches the Open Bible Stories list from bcv-commons/bible-story-builder at a
  pinned commit (1,449 verse readings, CC BY-SA; docs/sources.md). A film's list stays local in
  `import/stories/non-free/` until its makers have been asked.
- **`vrs.to_heb`**: the Hebrew verse of a BSB verse (the inverse of `to_bsb`), for lists in English numbering.

### Format changes

- **Story files** are no longer in git (`export/**/stories/`). The reading list's format is new (docs/stories.md);
  the work copy's `selection.tsv` columns are read as they are.

## v0.12.0

**Stamps with evidence** (the work copy's proposal, 2026-11-26: `stamp --all` marked every chapter as following
today's decisions, also one that writes "Darius" where the store says Dareios, and stale could never show it).

- **`basis`** in every stamp: `prompt` (make_prompt), `chapter_check`, `git <commit>`, `verified`, `asserted`.
  `stale` counts the stamps by basis and says that `asserted` ones were not tested.
- **`lifecycle.py stamp <project> --all --as-of git`**: the `drafted` stamp from the decisions in the commit that
  last changed each chapter's text (`committed`, `modified`); an upper bound for chapters committed after drafting.
  No date-based fallback for a store outside git.
- **`lifecycle.py stamp <project> --all --verify [--report F]`**: the `checked` stamp from a test of each decision on
  the chapter (terms, names, formulas with a source word through the .align; spelling rules on the text). It keeps
  what the chapter follows, `drift` (with the verses: decided entries naming their word by number, and names) and
  `unverified` (untestable kinds and phrases, verses without a link, terms found by their lemma, proposals not
  followed). Another decision on the same word (another bearer of a name) counts as followed; a name may take an
  ending of up to two letters. The drift list is the work list for `migrate --ids`. On the work copy's Danish
  project (431 chapters, read-only): 2,566 decisions followed, 20 drift verses (Ke'ila for Keila, Ma'on for Maon,
  "sydlandet" for Negev, gentilics, and one false: a name whose value is a phrase, "borgen Susa"), 27 s.
- **`words.entry_lexemes`** reads a source with a gloss or a note beside the word ("דָּרְיָוֶשׁ Darius",
  "H7270 רִגֵּל", "… (Neh 5) usury"): more decided entries are checked, by `words.py check` too.
- **`stale --stamp drafted|checked`**; from a verified stamp `drift`, `drift, changed since`, `changed (unverified)`.
- **Plain `stamp --all`** keeps its behaviour, marks its stamps `asserted` and warns.

### Format changes

- **Stamps (`.tanakh/runs/`)**: `basis` in every record; a verified record has `drift` and `unverified`, a git one
  `committed` and `modified`. Stamps without `basis` (v0.10.x) are read as before and counted as "before v0.12.0".

## v0.11.0

**Notes without whole verses** (the work copy's proposal, 2026-11-26: the whole Hebrew verses were half of its 33 MB of
notes, and every verse row also repeated the draft and the BSB).

- **The notes table** is *Verse · Hebrew (or Greek) · Comment*: the middle column a phrase the note is about (a few
  words, the WLC/BGB word for word; may be empty), never a whole verse; no copy of the draft or the BSB. A rendering
  under discussion goes into the comment. The chapter prompt says so in every project, also where `notes_structure`
  is set; the draft-chapter skill, `memory_prompt.py`, `docs/licensing.md` and CLAUDE.md follow.
- **`notes_hebrew.py`** no longer fills verses. It adds the credit line where the notes quote Hebrew or Greek (and
  removes it where they quote none), and counts the whole verses still in a table. `show` stays.
- **`notes_hebrew.py slim <project> [<code> [<ch>]] [--apply]`** moves older notes over: a whole verse in any column
  is emptied (the original's: >= 60% of the WLC/BGB verse's words; the rendering's or BSB's: that, and >= 80% of its
  words in the verse); a shorter rendering and BSB phrase move into the comment as `»rendering« (BSB phrase): comment`,
  so no choice is lost; rows left empty are dropped; a column empty in every row is dropped. Dry run by default, with
  a summary (files, cells, MB).
- **The website's verse view** shows a three-column table's phrase above its comment (it always took the verses from
  their sources).
- The demos' notes are slimmed (Danish: 86 choice rows, the phrases now in the comments; Jamaican: 93 whole-verse
  cells emptied) and the Danish `notes_structure` names the new table.

### Format changes

- **Chapter notes (`<code>NNN_notes.md`)**: the verse table has three columns (or two: Verse · Comment). Existing
  notes stay readable by every tool; to move them over, `python3 scripts/notes_hebrew.py slim <project>` (dry run),
  then `--apply`, then `python3 scripts/notes_hebrew.py <project> --all` for the credit lines.

## v0.10.1

**The work copy's "seen, not fixed" list** (its report of 2026-11-26, with cases from its projects for the last four).

- **`probe_language.py write --score`** reports familiarity by the rule that sets it (chrF verse by verse, known >= 58,
  the floors), not by the old pooled thresholds 65/30, which are gone.
- **`fetch_edition.py`:** an eBible edition needs `usfmtc`; that is said before the download, not after it.
- **`gloss.py`:** U+034F (the combining grapheme joiner some MACULA lemmas carry, Jerusalem) is ignored when lemmas
  are compared.
- **The probe's answers:** `1.`, `1)` and `1:` are item 1 (`tell` misread `1.<TAB>B`).
- **`language_profile.py check --project`:** evidence resolves against every style edition, not only the first (a
  verse two editions have may cite either).
- **`full_align.py split`:** a token both linked and dropped (`word^3 ^-3`) is linked, with a warning (it was a
  problem that stopped the split); a drop mark glued to a word (`Gott^-5.`) is read like one after a space, its
  punctuation staying with the word.
- **`notes_hebrew.py`:** a notes table's one-verse rows are filled where the table covers only some verses (a partial
  chapter, a few rows beside ranges); an empty original cell in such a table only where its BSB column is the verse,
  so a table of choices is left alone (the Danish demo's are). A table not filled says why (`--all`: counted).
- **`check_draft.py --spell`:** a decided name is spelled as decided, never a spelling question (Sarai is not Sara;
  Sin, Zin, Ai, Beeroth): all 7 spelling lines of the work copy's pilot were names.
- **`verse_pack.py --verses 1-5,8`:** only those verses (a selection run, a long chapter in parts; the header stays
  whole); a pack over 100 KB gets a note naming it.
- Built forms (`check_draft.py`'s "built from parts" and "not in the corpus" lines) no longer reach the loop's FIX or
  REVIEW since v0.9.2 (one INFO count), which was the rest of that report.
- Tests: `test_seen_fixes.py` (new).

**Format changes:** none.

## v0.10.0

**The lifecycle without revisions and without thousands of files** (make-tanakh-work's few-files request of
2026-11-12, points 1, 2, 3 and 5, with make-tanakh-grammar's answer: per-decision checksums suit it; its language
repositories keep the per-chapter layout).

- **Stale from checksums** (`lifecycle.py stale`): a chapter's stamp records the checksums of the decisions it was
  drafted and checked with (`register.binding_sum`: kind, value, status, basis, scope, supersedes and the kind's whole
  payload, renderings and denials included; not evidence or notes), the lexical ones by the source words in the
  chapter, the general ones by digest (`.tanakh/general.jsonl`). A chapter is stale for a decision that changed, was
  superseded, retired or removed, or that applies now and is not in its stamp. It works on the JSON store, across a
  history reset and outside git; `--since REV` keeps the revision route, and `bump` stays for a named state.
- **Stamps in every project** (`make_prompt.py`, `chapter_check.py`; before, only with a register), and never a
  failed prompt or check because of one. `lifecycle.py stamp <project> --all` records the chapters already drafted,
  as they are now.
- **Few files** (project.yaml `lifecycle: {files: book | chapter}`; default `chapter` with a register, else `book`):
  `book` writes one stamp file per book (`.tanakh/runs/<BOOK>.json`, a key per chapter; a chapter's old file moves into
  it) and a migration's edit records inside its record (`edit_rows`), one file per batch. `chapter` is the layout as
  it was (make-tanakh-review's). Both are read.
- **`migrate` on the JSON store:** tested (a spelling rule over the Danish demo's copy: 57 words, edit records in the
  record, undone byte for byte); with nothing to change, `--apply` writes no record.
- Point 4 (the register as JSON Lines per kind) waits until a work copy wants the register.
- Tests: `test_lifecycle.py` (checksums, the general log, stale reasons, both layouts).

**Format changes:**
- The chapter stamp gains `sums` and `general`, and `revision` is written only with a register. Stamps written before
  (a revision only) are read and compared by revision. New file: `.tanakh/general.jsonl`. New layout: `.tanakh/runs/<BOOK>.json`.
- A migration record in the `book` layout carries `edit_rows` and an empty `edits`; in the `chapter` layout nothing
  changes.

**Migration:** nothing has to move. A project on the JSON store (a work copy) gets the `book` layout by default; run
`python3 scripts/lifecycle.py stamp <project> --all` once to record the chapters already drafted, then commit
`.tanakh/`. A project with a register keeps per-chapter files unless it sets `lifecycle: {files: book}`; its old stamps
then move into the book files as chapters are stamped again.

## v0.9.2

**The checks stop pushing agents off right words; our own drafts repeated are no quotation** (from the work copy's
report of 2026-11-26: in a dialect drafted at partial familiarity, agents changed correct words four times to quiet
the spelling and English checks).

- **The spelling lines need the same word** (`words.py` review, `check_draft.py --spell` for store forms):
  `words.word_variant` passes over a one-rule variant (long/short vowel, diphthong, doubled consonant, the letter
  pairs) whose word-DB links show only other source words than the draft word renders (its `.align` link; for a store
  form, its entry's source): in a language without a standard spelling a one-letter neighbour is often another word.
  Where the links agree the line says so; with no evidence it asks "another spelling, or another word?". Passed-over
  variants are counted in the figure. Without a word DB nothing changes.
- **The English check** (`rough_check.py`): only English words the verse's own BSB has (a copied word comes from the
  verse in view); a target word spelled like an English word elsewhere is no longer flagged.
- **REVIEW lines are questions:** `chapter_check.py` prints the rule under them (a word you know to be right stays,
  with a one-line note; never change a right word to quiet a check), and the book prompt says so. `check_draft.py`'s
  spelling lines are always REVIEW (they went to FIX when the chapter had another problem, else were dropped); its
  forms not in the corpus are one INFO count.
- **`quotes.py`:** a run of 5+ words that stands in one of the project's own drafts counts nothing in any file (a story
  or selection file built from the drafts, a note citing our verse): it is our text again. Edition text copied into
  such a file is checked as before. `docs/licensing.md` says so.
- Tests: `test_quotes_own.py` (new), `test_words.py` (the same-word variant).

**Format changes:** none.

## v0.9.1

- **`CLAUDE.md`:** the command line for `scripts/draft_cache.py` (v0.9.0), in the Commands list.

**Format changes:** none.

## v0.9.0

**The drafting cache, and fixes from a many-language drafting run** (the work copy's delivery, 2026-11-26: its commit
`db69cd8`, about 60 projects onboarded and drafted with it since 2026-11-17).

- **`scripts/draft_cache.py` (new):** a project's drafting cache in `_learn/cache/` (derived, git-ignored):
  `primer.md`, the project's memory in one file (rules, book titles, quotes, formulas, terms, names, grammar and
  spelling observations, gaps, open questions); a digest per drafted chapter (its verses, the store entries its text
  uses, its open questions); `drafted.tsv`, every drafted verse with its part (whole | from_start | to_end) and
  selection. `build <project> [--selection F] [--version NAME]`; `new <project> <selection.tsv>
  [--skip-edition-chapters]` lists the verses of a selection still to add or extend. The book prompt
  (`docs/prompts/book_prompt.md`) has the agent read the primer at the start and after a compaction or resume, and
  rebuild the cache before a handover; the draft-chapter skill says so. The store and wiki stay the source. Taken with
  three changes: the store is read through the register's loader (a converted project's primer had no entries), the
  project and edition folders as the other tools find them (`export/CC-NC/` too), and a project's own rules are left
  out (Matthew skipped in a selection; chapters a style edition has: now `--skip-edition-chapters`).
- **`onboard.py`:** the `quotes:` line is written as a JSON string (ASCII `"` quotes broke the YAML); the answers
  list `write_priors` and `build_and_draft`; editions in a dialect's folder (`import/<licence>/<dialect id>/`) are
  found.
- **`probe_language.py`:** the write prompt always names the script; the write chrF is scored with optional pointing
  (Arabic harakat, Hebrew niqqud, Syriac vowels) removed on both sides where the edition has it
  (`pointing_removed`).
- **`align.py`:** the hbo side maps a chapter beyond the Hebrew's count (an edition numbering Joel or Malachi as the
  BSB does) through `orig/vrs` (it crashed); a scaffold that can't be fetched is skipped with a warning.
- **`fetch_edition.py`:** a DBT text's licence class comes from its copyright line, else non-free (it was always
  non-free).
- **`morphs.py`:** `hebrew_features` skips MACULA's object pronouns of person `unknown: x` (it crashed).
- **`.gitignore`:** `export/**/_learn/cache/`; a language folder's `README.md` under `import/non-free/`, `CC-ND/` and
  `CC-NC/` (a dialect folder with several editions) is kept, as an edition's is.
- **The quotation limit for an edition in all: 4% of its words (was 2%)**, in `quotes.py`, `docs/licensing.md` and
  `CLAUDE.md`; at most 10% of a book's verses per file stays. No source backed 2% (the Berne Convention's Art. 10,
  §51 UrhG and fair use name no percentage); 4% is the user's judgement. The check is looser: nothing to change in a
  project, `check_project.py` only reports fewer problems.

**Format changes:** none.

**Migration for a work copy:** merge v0.9.0.

## v0.8.0

**Clitics in the morph view, and a root spelled like a free word** (make-tanakh-research's check of v0.7.1,
2026-11-26: the three faults mended, Tagalog verb tokens split 0.80, stores without stem morphs byte-identical on all
seven bundles; and three points, a to c).

- **Clitics** (point b: *d-um-ati-ng*, as the linker *-ng* was a suffix). The store's slot `clitic`, accepted by the
  store's description and validator but ignored by the splitter until now, is a part that attaches to a whole word:
  `=ng` or `-ng` after it, `ng=` before it. Fused, it comes off only where what remains is a word of the corpus, not
  rare beside this form (*dati=ng*; not *dumati=ng*, as *dumati* is no word, so *d-um-ating* stands); several stack,
  each leaving a word; the word under it is split as any word. Written with a hyphen (`written: hyphen | both`), it is a
  hyphen part, labelled clitic. Whether a part is a clitic or a suffix is the store's call (a linker or particle that
  follows any word: a clitic; an ending of a word class's paradigm: a suffix). The model text glues an enclitic after
  and a proclitic before (decoded back exactly); `language_profile.py check` wants a clitic's form to mark one side.
- **A root spelled like a free word** (point a: *tumayo*, *tatayo* whole, as *tayo* is also "we"; *ninais*). v0.7.1
  never took a free word as a root (for *k-in-a-in*). Now the paradigm decides, as everywhere in the splitter: a free
  word's own uses are no evidence for a root, an infix or copy on it in other words is (*t-um-ayo* beside *ta-tayo*),
  and such a root is taken only where the word has no other reading (*k-in-ain* still wins; *sina* stays whole
  beside *sa*).
- Not changed: *in-ilagay* (point c).
- Tests: `scripts/tests/test_clitics.py` (new), `scripts/tests/test_stem_morphs.py`. Stores without clitics or stem
  morphs split byte-identically (Zinza, Kuni).

**Format changes:**
- The language store and the register's `morph` kind: slot `clitic` now takes effect in the morph view (it was accepted
  and ignored); `written` applies to it as to prefixes and suffixes. A store with clitic entries now splits them off
  (none known). A morph view consumer outside this repo may now see the slot `clitic`.

**Migration for a work copy:** merge v0.8.0. A store that writes a word-level linker or particle as a `suffix` may move
it to `clitic` (make-tanakh-research: Tagalog's *-ng*).

## v0.7.1

**The stem's infix and copy, mended after make-tanakh-research's check of v0.7.0** (2026-11-26, the Tagalog ULB: verb
tokens split 26.6 % → 62.4 %, 0 rebuild failures, and three faults). With a store that has neither, nothing changes:
the Zinza and Kuni stores split byte-identically again; research found the same for Indonesian, Swahili, Tok Pisin,
Danish, Kuni and Tagalog's old store on v0.7.0.

- **A prefix before a copy** (fault 1: *nagsasabi* whole beside *mag-sa-sabi*): the prefixes and suffixes, the infix
  and the copy are chosen together (in `chain_parse` and without positions alike), and the root's evidence is enough
  for the affixes around it, so *nag-sa-sabi* and *na-su-sulat* split where *sasabi* is rare on its own.
- **Non-verbs** (fault 2: *la-laki*, *bi-big*, *t-in-ig*, *s-in-o*, *in-yo-ng*): where the NT is aligned to the Greek
  (`lang.py build`), an infix or copy comes off only words linked to its host (`verb`) in at least half their tokens,
  or unlinked words whose root is the root of such a word (`host_ok`); this now holds without positions as well. And
  the infix stands right before the stem's first vowel, so *inyong* is not *in-yong*.
- **The suffix over the infix** (fault 3: *kina-in*, *kuma-in*): a free word (`ka`) is never a root, and of two
  readings with as many letters off in as many pieces, the one whose stem or root is attested in more forms wins
  (*k-in-ain*, *k-um-ain*, *k-um-a-kain*).
- Test: `scripts/tests/test_stem_morphs.py` adds the three faults, with and without positions.

**Format changes:** none.

**Migration for a work copy:** merge v0.7.1.

## v0.7.0

**Infixes after the stem's onset and reduplication in the morph view** (make-tanakh-research's request, 2026-11-14,
found on Tagalog: the verb is focus affix x aspect over a root). Both are store entries a team writes from a grammar
sketch, with no code of its own (`docs/language-store.md`, *Morphs* and *The morph view*):

```json
{"kind": "morph", "slot": "infix", "form": "-um-", "site": "after_onset", "host": "verb"}
{"kind": "morph", "slot": "redup", "pattern": "CV", "site": "before_stem", "value": "IPFV/CTP", "host": "verb"}
```

- An infix's `site`: `after_prefix` (the default, as before) or `after_onset`: after the stem's consonants before its
  first vowel, before a vowel-initial stem, with or without a prefix or suffix (*s-um-ulat*, *um-alis*, *i-s-in-ulat*,
  *s-in-ulat-an*).
- Slot `redup`, `pattern` `CV` | `CVC` | `full`: a copy of the root's first syllable or of the whole root before it,
  after any prefix and infix (*su-sulat*, *nag-su-sulat*, *s-um-u-sulat*).
- The splitter's rules hold: a piece comes off only where the root is attested (a stem of its own, or with another
  infix or copy); the parts rebuild the token exactly; the label is the store form (`-um-`, `redup:CV`). An infix cuts
  the stem (or the copy) into two pieces of one form: `s` / `-um-` / `ulat` are stem `sulat`, infix, stem `sulat`.
- The callers: `align.py --by parts` takes a cut stem as one part (the root), the model text
  (`nllb/model_text.py`) glues a copy to what follows and an infix that begins the word like a prefix (decoded back
  exactly), `stem_forms` joins the pieces; `language_profile.py check` validates `site` and `pattern`; `grammar.basis`
  includes them where an entry has them (existing fingerprints unchanged). Test: `scripts/tests/test_stem_morphs.py`,
  the request's twelve Tagalog words.
- A store without them splits byte-identically: checked on every corpus token of the Zinza and Kuni stores here.

**Format changes:**
- The language store and the register's `morph` kind: two optional fields, `site` and `pattern`, and the slot
  `redup` (whose `form` is optional). Additive: existing stores and registers are unchanged. A morph view consumer
  outside this repo may now see the slot `redup` and a word with two stem morphs (of one form).

**Migration for a work copy:** merge v0.7.0; nothing to rewrite.

## v0.6.0

**The register's revision is a plain number in the files** (make-tanakh-grammar's request, 2026-11-12). The prefix
`register-` earns its place only in the git tag, where a language repository has other tags beside it; inside the
files the field is already called `revision`. `register.py`: `revision()` returns the number (0 before the first
bump), `bump` writes it, `tag_of` gives the tag name it suggests; `rev_n` takes `3`, `"3"` and `"register-3"` alike.
`lifecycle.py`: an unstamped chapter counts as drafted against 1; `stale --since` takes both forms.

**Format changes:**
- The register: `VERSION.json` and `REVISIONS.jsonl` `revision` is an integer (`"revision": 3`), the chapter stamp
  `.tanakh/runs/<BOOK>_<CCC>.json` (`drafted.revision`, `checked.revision`) likewise. The git tag stays
  `register-<n>`. Files written before (`"register-<n>"`) are still read, for this version at least, and compare with
  the new ones; the next `bump` writes the number. A reader of these files outside this repo reads an integer now.

**Migration for a work copy:** merge v0.6.0. Nothing has to be rewritten: a register at `register-1` reads as 1 and
the next `bump` writes 2. To have the files in the new form at once, set `"revision": 1` in `VERSION.json` and on the
line of `REVISIONS.jsonl` (the digests are untouched); `register.py check` reports `revision 1`. Stamps already
written may stay as they are.

## v0.5.0

**Two field names in the register, as make-tanakh-grammar decided** (the work copy's follow-up to v0.4.0,
2026-11-12). With both, a converted entry passes grammar's check as it is.

- **The spelling payload is `match, replace, context, exceptions, order, said`.** It was `from, to, …`, and that
  `from` clashed with the envelope's `from` (the answers and questions an entry was made from). `register.py check`
  no longer treats a spelling entry's `from` as a special case. Changed in `register.py`, `words.py`,
  `language_profile.py`, `wiki.py`, the docs and the tests.
- **The round trip to the old JSON store is out of the entries.** The pointer is the envelope's `origin`
  (`store:<file>#<store id>`). What an exact round trip needs beyond it is kept in STORE.json's `round_trip`, by entry
  id. The `store` field and `check`'s exemption for it are gone (`docs/register.md`, *The round trip*).

**Format changes:**
- The `spelling` kind: `from` → `match`, `to` → `replace`, in the JSON store and in the register. No reader accepts
  the old names. A store with spelling entries renames the two keys by hand (none are known: the work copy has
  none).
- The register: STORE.json `format` 2, with `round_trip`. A v0.4.0 register (`format` 1, the `store` part inside each
  entry) is still read exactly; `register.py convert` run again moves all its store parts to STORE.json (a single `add`,
  `supersede` or `status` moves that entry's). Until then, `register.py check` reports `unknown keys ['store']`.

**Migration for a work copy:** merge v0.5.0, then convert as v0.4.0's note says
(`python3 scripts/register.py convert <project>`, then `check`). A project converted on v0.4.0: run `convert` again. It
rewrites the entries in format 2 (round trip checked, no new revision); commit the changed entry files and STORE.json.

## v0.4.0

Three deliveries from the work copy (2026-11-12), built on each other: the word DB, the register, the decisions'
lifecycle. New tools are now coordinated with the template: one built in a work copy or in make-tanakh-grammar comes
here as a delivery (`docs/related-repos.md`, *How a change travels*; `CLAUDE.md`, `README.md`, `docs/workflow.md`).

**The word DB and its check.** `words.db` holds the style edition's words per Hebrew and Greek lexeme, from an
alignment layer of exactly its text (`docs/word-db.md`). make-tanakh and make-tanakh-grammar share the format (grammar's
`onboard/lexicon.py` schema, extended).

- `scripts/words.py align | build | check | stats | show`:
  - `align` runs lexeme-aligner's `align-text` on the style edition here, without LLM checking: the text stays on the
    machine.
  - `build` reads compact-alignments layers: a local run, `--layer`, or the published layer of `lang.py layers`.
    `--eflomal` reads the old `align.py` links, as a marked transitional route.
  - `check` reviews a chapter: decided store terms the verse lacks, spellings the corpus writes otherwise (one-rule
    variants, store forms included; marks; the project's respelling), expected corpus forms that are missing, and the
    figure found / checkable. Counts are recounted from the occurrences without the chapter checked. A decided entry
    is checked in its `scope` (a book, chapter or range), or in the book its id ends in (`term:alah_deu`).
- `chapter_check.py` adds the word check's REVIEW lines and an INFO figure when the project has a `words.db`.
- `check_draft.py --spell`: a store form no longer counts as attested when the corpus writes a one-rule variant of it,
  and the corpus is compared in the project's spelling.
- A new store kind, `spelling`: one respelling rule per entry (`from, to, context, exceptions, order, said`), with
  `orthography.respell` (their ordered ids) and `orthography.keep_marks`. The validator, its schema and `wiki.py`
  accept it (`docs/language-store.md`).
- `lang.py hbo <project> 639` finds H0639: the Strong's number is zero-padded as orig/heb.sqlite writes it.

**The register.** A project's store can be `profile/register/`: one JSON file per entry (`<kind>/<slug>-<hex6>.json`),
with `VERSION.json` and `REVISIONS.jsonl`, in make-tanakh-grammar's envelope with its 12 kinds plus `spelling`
(`docs/register.md`).

- `scripts/register.py convert | check | show | add | supersede | retire | status | bump`. A team's decision is binding:
  only the team supersedes it.
- Every store reader and writer goes through one loader (`register.read`, `write`, `exists`, `mtime`; `entries` for the
  envelope view). It reads the old JSON store unchanged where a project has no register.
- For a register project, the prompts tell agents to write with `register.py add` / `supersede` instead of editing
  `profile/decisions.json`.
- The questionnaire `docs/register/parameters.tsv` (1,161 questions; the Grambank, WALS, APiCS and AUTOTYP rows are
  CC BY 4.0, credited per row and in `docs/sources.md`).

**The decisions' lifecycle.** `scripts/lifecycle.py` (also `register.py stamp | stale | migrate`), for register
projects only:

- The chapter stamp `.tanakh/runs/<BOOK>_<CCC>.json`: `make_prompt.py` writes `drafted`, and `chapter_check.py` writes
  `checked` when nothing is left to fix. Each records the register's revision.
- `stale` lists the chapters older than a changed decision, with `--verses` the verses it touches.
- `migrate` is a dry run by default. `--apply` rewrites the drafts for spelling rules and for term swaps the `.align`
  locates, one token for one token, so the `.align` keeps its positions and only its `# text` fingerprint changes.
  Every change goes to an edit record (make-tanakh-review's FORMAT.md section 10) under `.tanakh/edits/`, and the batch
  to a migration record. `--undo` reverses a batch. Published chapters get proposals only.

**Format changes:**
- New: `words.db` format 1 (`meta.format`); the register (`VERSION.json` `format` 1); the chapter stamp and the
  migration and edit records under `.tanakh/`. All are listed in `docs/related-repos.md`, section 4.
- The store: a new kind `spelling`, and the optional fields `orthography.respell` and `orthography.keep_marks`.
- `project.yaml`: an optional `words:` block (`keep_marks`, `variant_pairs`, `aligner`).
- The register replaces `profile/decisions.json` and `profile/observations.json` once a project is converted. Until
  then nothing changes: the JSON store is read as before, and outputs are byte-identical (tested on five projects).
  The demos keep their JSON stores.

**Migration for a work copy:**
1. Merge the tag: `git fetch template && git merge v0.4.0`.
2. Per project, when you choose to: `python3 scripts/register.py convert <project>`. It checks the round trip entry by
   entry before it removes the two JSON files (`--keep` keeps them). Then `python3 scripts/register.py check <project>`
   should report 0 errors.
3. Commit the new `profile/register/` folder and the removal of the JSON files. The `.tanakh/` files that
   `make_prompt.py` and `chapter_check.py` write from then on belong to the project too.
4. Optional, per project: `python3 scripts/words.py align <project>` (needs a lexeme-aligner checkout) and
   `python3 scripts/words.py build <project>`. `_learn/words.db` is git-ignored.

## v0.3.1

**"Tanakh", not "OT", in the prose** (the work copy's request of 2026-10-30). "Old" is often heard as derogatory, so
the docs, skills, prompt templates, `CLAUDE.md` and the editions' descriptions say "Tanakh" (the books), the
language ("Hebrew") where the source language is the point, and "Septuagint" or "LXX" for its Greek translation.
"NT" stays.

- Script output that people and agents read says "Tanakh" too: the chapter and memory prompts, the clause
  packages' `had:` line (`Tanakh:` for the style edition's own renderings), the audit's route names (`Tanakh Hebrew`,
  `Tanakh LXX`, `Tanakh Vamvas`), and the reports of `onboard.py`, `setup.py`, `project.py`, `lang.py`,
  `cell_check.py`, `gloss.py`, `judge.py` and `fetch_edition.py`.
- Identifiers stay: the testament code `ot` (`books.py`), `ot_routes.py`, `--route ot`, the verdict `ot-only`, and
  field names. Comments and docstrings are left for later.
- `docs/related-repos.md`: the work copy is larsgson/make-tanakh-work.
- The Jamaican demo's wiki and store are its own notes, copied from the work copy: they change there.

**Format changes:** none.

## v0.3.0

**Tagged drafting for the NT** (the work copy's request of 2026-10-29). An NT chapter is now drafted as a chapter of the Tanakh is:
clause packages first, a tagged draft, `full_align.py split` into the draft and its `.align`, the checks in the loop.

- `package.py <project> <code> <ch>` builds NT packages: one block per line of the Greek NT clause layout
  (`orig/grc-gntl`), with the words of the project's own Greek text (BGB for `nt_basis: critical`, RP otherwise), each
  numbered as `full_align.numbering` numbers its MACULA Greek word; gloss, morphology for verbs, referents, speech
  marks and clause rules (greek-nt-clause-layout v0.5, needs pyarrow), named participants (`who:`), BSB words, and
  `had:` (earlier `.align` files, the store's `G` terms; for an unknown language the style edition's renderings in the
  other NT books, never in the book being drafted).
- **Which Greek the numbers count:** MACULA Greek (the compact-alignments index). A word of the project's text that
  MACULA lacks is shown as `* word`, without a number: the agent renders it and leaves it untagged. A MACULA word the
  project's text lacks isn't shown, and `split` doesn't ask for it (`full_align.absent`); it stays undecided in the
  `.align`.
- `make_prompt.py` drafts the NT tagged by default, in Greek wording; `--end-align` gives the earlier NT prompt (the
  draft alone; `full_align.py prompt` aligns it later). The book agent builds the NT packages too.
- `chapter_check.py` runs the alignment check and the names-across-the-book check on NT chapters, and `rough_check.py`
  counts the negations an NT `.align` links.

New test: `scripts/tests/test_nt_tagged.py` (package numbers, `*` words and absent ones, the split/tag round trip;
skipped without the Greek sources).

**Format changes:** none (an NT `.align` was already in the compact-alignments format).

## v0.2.1

**The speaker layer v0.15** (bcv-commons/hebrew-speaker-layer; `setup.py --only spk` fetches it). Its `speaker_id` now
agrees with each quotation's inquit; a difference left between the id's name and the inquit is one person under two
names (Jacob/Israel). A quotation spoken by several people has a group id, no `speaker_name`, and the new
`speaker_members`. The clause packages mark a group with each named member's participant (`= p5+p6`, Rachel and Leah
in GEN 31:14) instead of one member's, or with none where not all are named.

**Format changes:** `orig/heb.sqlite`: `speaker_quotations` gains `speaker_members` (additive; `setup.py --only spk`
rebuilds the table).

## v0.2.0

**The Tanakh order by default.** A project's reading order is now its own setting, `book_order` in `project.yaml`:
`tanakh` (the default: Torah, Prophets, Writings, as in BHS), `protestant` (Genesis … Malachi, the BSB's order and
the one every list followed before) or `septuagint` (the Greek order of Orthodox Bibles). The setup wizard asks for it.
It orders `STATUS.md`, the site's book lists and the wizard's book ranges. Book codes, file names and the book numbers
for Paratext and MACULA keep the BSB's numbering order (`books.BOOKS`); the NT order is the same in all three.

**For an existing project:** without `book_order` it now lists its books in the Tanakh order. To keep the earlier
order, add `book_order: protestant` to `project.yaml`; run `scripts/status.py <project>` to rewrite `STATUS.md`.

**Format changes:** `project.yaml` gains the optional `book_order` (additive).

## v0.1.1

A fix: in v0.1.0 a store entry's `basis` had two meanings. `grammar.py run --write` put a Grambank answer's
team/derived/labelled there, and the validator accepted only those three values, but `basis` is also the settings
fingerprint that `morphs.py try --write` and `cell_check.py try` write on a measured claim and `grammar.py retest`
compares. Every store with measured claims failed validation.

**Format changes:**

- language store: a Grambank answer's (`gb:GBnnn`) team/derived/labelled moves from `basis` to **`answer_basis`**.
  `basis` is only the settings fingerprint (16 hex digits, `grammar.basis`), and the validator now checks that shape.
  **Migration:** `python3 scripts/grammar.py run <project> --write` rewrites the script's `gb:` entries with the new
  field; the validator names any old one left (`a Grambank answer's basis is answer_basis`). A `gb:` entry an agent or
  team wrote by hand needs the field renamed by hand. Measured claims need nothing.

New test: `scripts/tests/test_store_basis.py` (a measured claim and a Grambank answer side by side, a claim going
stale, the migration message).

## v0.1.0

The first tagged version: the baseline the work copy and make-tanakh-grammar start from.

**Formats at this version:**

- language store: `docs/language-store.md`, schema `docs/language-store/schema/language_profile.schema.json`;
- clause sidecars: `docs/clause-sidecar.md`;
- `.align` working format: `scripts/full_align.py`, on compact-alignments' `tokenizer_version` 2 and
  `text_fp_version` 1;
- compact-alignments layer: `_layer.json` `version` 3, layer id `<edition>+auto+make-tanakh`;
- `orig/heb.sqlite`, `orig/grc.sqlite`: the tables in `scripts/src.py`, from the source structure `v1`.

**In this version, from the work copy's reconciliation delivery:** NT word alignment (`bridge_align.py`,
`full_align.py`, Greek tokens from `orig/grc.sqlite`) and the site's Greek NT clause view (greek-nt-clause-layout
v0.5, `build_grc_gntl.py`); the speaker layer v0.14; alternations (`alternations.py`); store fields for hyphen
chains, harmony variants, word parts and tone `with`; `nllb/train.py --src-chars`.

**New here:** the data root setting `MAKE_TANAKH_ROOT` (`docs/configuration.md`): data from that folder, code from the
toolkit's own; without it, everything as before.

**Format changes:** none against earlier states, all additive:

- language store: optional `with`, `variants` and `parts` fields, and `feature` entries with an `alternation` block;
- `orig/heb.sqlite`: `speaker_quotations` gains `speaker_ref`, `speaker_basis`, `alt_eng`, `speaker_id`,
  `speaker_name`, `speaker_name_ref` (`setup.py --only spk` rebuilds it);
- `.align`: now also for NT chapters, in the same format, on the Greek of compact-alignments' index;
- the layer id was `<edition>+auto+bsb-add-books` before the rename; no layer with the old id was published.
