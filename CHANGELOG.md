# Changelog

Tags are `vMAJOR.MINOR.PATCH`. A work copy merges a tag; make-tanakh-grammar pins one (`docs/related-repos.md`).
Each entry has a **Format changes** section for the stable formats listed in `docs/related-repos.md`, section 4:
what changed and how existing files move over. Before 1.0 a breaking format change raises the minor version.

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
