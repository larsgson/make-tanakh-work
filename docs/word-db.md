# The word DB (`words.db`)

Which words the style edition uses for each Hebrew and Greek lexeme, counted from an alignment of exactly its text,
and the check of a draft chapter against them. One file per project, `export/<project>/_learn/words.db`, built by
`scripts/words.py build`; local and git-ignored, never published: it is derived from the edition's text, and
`docs/licensing.md` keeps bulk derived data of an edition local. It holds word forms, counts, references and token
positions, no verse text.

The same format serves make-tanakh-grammar (its `onboard/lexicon.py` wrote the first version of it; its readers
`drafting/prompt.py`, `alternatives/shape.py` and `alternatives/rules.py` go through `drafting/lexicon.Lexicon`, which
`words.Lexicon` replaces with the same methods).

**Hard rule: only the edition's own text goes in, never draft output.** A draft that passes the check must not
become the evidence of the next check.

## Format (version 1)

| table | columns | holds |
|---|---|---|
| `lexeme` | `id, lang, strong, lemma, cls, n, type` | a source lexeme: `grc:26`, `hbo:2050b` (Strong's number as the public index writes it, zeros dropped, a Hebrew homonym letter kept); MACULA's lemma, class (`noun`, `verb`, ...) and type (`proper`, ...) of its first token; `n` its links |
| `form` | `id, form, plain, bare, tokens, n, project` | a target form as written (NFC); `plain` lower case; `bare` = NFD, combining marks dropped except the kept marks, NFC; a link to several tokens is one form, its tokens joined by a space, or by ` … ` where words of the verse stand between them; `project` = `plain` in the project's spelling (respelling, below) when the DB was built |
| `link` | `lexeme, form, n, n_strong, books, share, back` | one row per pair, a cache: `n_strong` = links the aligner rated high (method letter in upper case), `share` = of the lexeme's links, `back` = of the form's. Readers recount from `occ` |
| `occ` | `lexeme, form, ref, src, key, positions, method, edition, layer, level` | every link: the verse in the edition's numbering (Hebrew in the Tanakh), the source word (`c3` = content ordinal 3 of the verse in the public index, `f0` a function word), its MACULA key, the target token positions (JSON), the method letter (compact-alignments' `method` channel: `E`/`e` eflomal, `G`/`g` gloss, `f` gapfill, `r` residual; `x` the transitional route), the edition id, the layer id with its revision, `words` or `parts` |
| `vocab` | `plain, bare, book, ch, n, edition` | every token of the edition's text per chapter (the spelling check's corpus; per chapter for the holdout) |
| `meta` | `name, value` | `format`, `built`, `project`, `inputs` (route, layer, edition, run record and its SHA-256, links), `editions` (SHA-256 of each edition's verse texts), `keep_marks`, `respell`, figures |

Target positions count the tokens of compact-alignments' tokenizer (`full_align.tokenize`, tokenizer v2); a form is
taken from the same tokens with their marks (`words.written_tokens`). Adding a column or a table is not a breaking
change; renaming, removing or changing one is (`docs/related-repos.md`, section 4).

## Routes (where the links come from)

Every route reads the bcv-commons compact-alignments format with the template's own readers (`full_align.index`,
`.parse`, `.text_fingerprint`). A layer's book file is used only when its file name carries the fingerprint of our
copy of the edition's book: another copy or another version of the text is skipped, never read onto the wrong words.
A layer's spine verses are moved to the edition's numbering by its manifest's `verse_map`.

1. **A published layer of exactly this text** (`lang.py layers <project>`; `lexeme_aligner:` in `project.yaml`).
2. **A local run of lexeme-aligner** (`words.py align <project>`): its `align-text` on the style edition, writing only
   into OUT (default `build/words-align/<project>/<edition>/`), the run recorded in `OUT/words-align.json` beside the
   aligner's own `align-text-run.json`. Never with `--jev`: nothing of the text leaves the machine (only
   `fetch-inputs` downloads its pinned data, with `--fetch`). The aligner is `--aligner`, `$LEXEME_ALIGNER`, `words:
   {aligner: ...}` in `project.yaml`, or `tools/lexeme-aligner/.venv/bin/lexeme-aligner`. An NT of 8,000 verses takes
   about two minutes on a laptop CPU.
3. **Transitional:** `--eflomal` adds `align.py`'s `_learn/links_grc_pos.tsv` (NT only, lower-case forms, method `x`,
   layer `align.py:links_grc_pos.tsv@<sha>`), until a layer exists. `align.py` is to be retired.

`build` takes `--layer DIR` (a compact edition folder, `<i>/<iso>/<edition>/`), else `words: {layers: [...]}` in
`project.yaml`, else the runs of `align`, else the published layer.

**Hebrew words through the Greek.** For an NT-only corpus, a Hebrew lexeme reaches the corpus's words through its
Septuagint equivalents (`orig/heb.sqlite`'s `lxx` table, MACULA Hebrew's per-word Greek): only when it has fewer than
`DIRECT_ENOUGH` = 10 direct links; the equivalents with share >= `MIN_SHARE` 0.05 and at least `BRIDGE_MIN` 2
occurrences, the best `TOP` 3, those with at least `BRIDGE_REL` 0.5 of the best one's share. `expected()` uses every
form of these lexemes, not the commonest few; a lexeme is checkable with `MIN_N` 3 links.

## The check

`words.py check <project> <code> <ch>` prints the lines; `chapter_check.py` adds them as REVIEW lines (never FIX in
this version) when the project has a `words.db`, and an INFO line with the figure.

**Holdout.** Counts are made at read time from `occ` and `vocab`, leaving out the chapter being checked: a draft of
an NT chapter the edition has never sees the edition's own text of it.

- **term**: a decided store term or formula (`profile/*.json`, kind `term`/`formula`, status `decided`, not
  superseded) names a source lexeme (`H639`/`G3709` in `source` or the id, else a single Hebrew or Greek source word
  looked up as a content lemma; a formula needs the number, and a phrase names none), the lexeme occurs in the verse,
  the entry's English BSB `words` (if any; function words aside) are in the BSB verse (the sense the entry is for),
  and no accepted form of the value is in the verse. The value's forms: the value, split at `;`, `,`, `:` and ` / `,
  and alternatives with `status: preferred | admitted`; a form is there when each of its words that isn't among the
  corpus's commonest 60 is (all common: its rarest word; Hebrew words in a value left out), inflected or not (same
  word, same letters without marks, one stem: `sägne` / `gsägnet`, `Magd` / `Mägd`; inside a compound: `Stei` in
  `Onyxsteine`; or a form the corpus writes for the lexeme with the same first three letters: `lost` for `lose`). A
  value of more than `MAX_FORMS` 6 forms is a list of a chapter's forms, not a rendering: not checked. One line per
  entry and draft form, with its verses. An entry with a `scope` (a book `EXO`, a chapter `EXO 21`, a range `EXO
  21-23`, or a list of them; `ALL` or none: everywhere) is checked only there; without one, a book code at the end of
  the id (`term:alah_deu`, `term:ets-est`: Danish has 170 such decided entries) is taken as its scope. With a
  `.align`, a source word it links to no draft word is counted ("term missed"), not listed: in a judged sample
  1 of 7 such lines was a finding. Several decided entries on one lexeme are alternatives (senses): the verse passes
  when one is there. The `.align` names the draft words that render it.
- The spelling classes (spelling, rare, marks) run where the project checks spelling (`spell_check`, on for `partial` and
  `unknown`; project.yaml `words: {spelling: true|false}` overrides): in Danish (`known`) 5 of 6 sampled spelling lines
  were other words (`øerne`/`ørne`, `fyre`/`fire`). `project spelling` runs always.
- **spelling**: a draft form (not a name: the store's names, the words the `.align` links to a proper noun) the corpus
  never writes while it writes a one-rule variant at least `VARIANT_MIN` 2 times, compared on `bare`, **store forms
  included**: a doubled or single consonant, `y`/`i`, `ä`/`e`, a long or short vowel (doubled, or with `h`), a
  diphthong reduced to one of its vowels (the letter pairs `y`/`i` and `ä`/`e` by default; a project's `words:
  {variant_pairs: [[a, b], ...]}` replaces them, `[]` for none: in Danish `y`/`i` makes only noise, `tyde`/`tide`,
  `sindet`/`syndet`). **rare**: the corpus writes the form itself at most twice and the variant ten times as often
  (and at least 20 times; not by the diphthong rule: `Böim` is not `Bim`).
- **marks**: the corpus writes the same letters with other marks only (a tone or accent mark).
- **project spelling**: the draft writes a form as the corpus does where the project's respelling rules write it
  otherwise.
- **expected**: a source content word (noun, verb, adjective; not a name, not a word a decided term covers) whose
  lexeme is checkable and none of whose corpus forms (respelled, inflected) is in the verse; listed only when its
  commonest form has share >= `LIST_SHARE` 0.8 of at least `LIST_MIN` 10 links, the lexeme itself (not only its
  Septuagint bridge) has `LIST_MIN` links in the corpus, and, with a `.align`, the `.align` links the word to draft
  words (an unlinked one is counted, not listed). A bridged word gives the figure, not a line: on a project with an NT
  corpus for Tanakh drafts, 1 of 12 sampled bridged lines was a real finding. The figure: found / checkable.

`check_draft.py --spell` does the same for its spelling list: a store form no longer counts as attested when the corpus
writes a one-rule variant of it, and the corpus is compared in the project's spelling.

## Keep-marks rule

`bare` drops combining marks except the kept ones: `words: {keep_marks: [U+0308, ...]}` in `project.yaml`, else the
store's `orthography.keep_marks`, else the default: diaeresis U+0308, ring U+030A, cedilla U+0327, ogonek U+0328 (marks
that make letters, `ä`, `å`, `ç`; tone and accent marks are dropped). A tone language keeps none of its tone marks
here: forms differing only in them fall into `marks`.

## Respelling: the project's spelling of the corpus's words

A project may spell differently from its style corpus, while the corpus still decides the word: a Danish project drafting
with the 1871 text as its corpus writes `å` where the corpus writes `aa` (`Aand` -> `Ånd`); a team may revise its
orthography against its own published text (a letter dropped from names, say). Each rule is a store entry of its own, kind
`spelling`, in `profile/decisions.json` (a project decision), so that each has its own status and `supersedes`, a
team can decide the rules one at a time, and a migration can name the rule it applied:

```json
{"id": "spelling:aa", "kind": "spelling", "value": "aa → å", "status": "decided", "method": "project-decision",
 "confidence": "medium", "by": "...", "date": "2026-11-12", "note": "...",
 "from": "aa", "to": "å",
 "exceptions": ["baal"], "order": 1,
 "said": "aa is written å: Aand → Ånd, gaa → gå."}
```

The payload (`from, to, context, exceptions, order, said`) stands beside the envelope, as in make-tanakh-grammar's
register; `value` is its short form. `orthography.respell` in the same file holds only the ordered list of the spelling
entries' ids (without it, they apply by `order`). `from` is a regular expression on the lower-case form;
`context.before` must match the text before it (at its end), `context.after` the text after it (at its start; `$` = the
word's end); `context.unless` (both parts) keeps a match; `exceptions` are forms left as they are (loanwords), also
inside a compound (`baal` keeps `Baalspræst`). Names (the store's name values, and forms the corpus links mostly
to proper nouns) are never respelled. `said` is the one-sentence rule a drafter's prompt shows. Only entries with status
`decided` apply; `open` is a proposal. `words.Respeller(rules)(form)` applies them; `words.py check --respell FILE`
tries entries from a file of the store's shape (`{"entries": [...], "orthography": {"respell": [...]}}`) without
changing the store, `--respell-open` with the open ones too.

- `words.db` keeps the corpus's forms exactly as written; `form.project` is the respelled form.
- Decided store terms are compared as stored: their values are in the project's spelling.
- The spelling check: a draft form is right when it equals a respelled corpus form; one that equals the corpus's
  unrespelled form where a rule applies is `project spelling`; the variant classes are judged on respelled forms.
- **Quotations are never respelled:** a quotation of the edition in notes, footnotes or store evidence stays as the
  edition writes it (`docs/licensing.md`); only our own text follows the project's spelling.
- **make-tanakh-grammar:** its register (`shared/register.py`, `KINDS`) needs the same kind `spelling`, taken from the
  template, so that a team's orthography revision is one entry per rule there as here.
