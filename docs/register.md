# The register: the store as one entry per file

A project's language knowledge (its *store*: terms, names, formulas, features, morphs, words, letters, gaps, claims,
cells, spelling rules, the orthography) was two JSON files, `profile/observations.json` and `profile/decisions.json`
(`docs/language-store.md`). The **register** holds the same entries one per file, in make-tanakh-grammar's envelope, so
that decisions can be refined while drafting goes on: every change is a new entry or a status change, each file changes
alone (two branches adding entries never conflict), and a **revision** names the register as a chapter saw it
(*Lifecycle* below). `docs/language-store.md` stays the description of what the entries *mean* (kinds, fields,
methods, the brief, seeds); this page is the format they are kept in.

## Where

`export/<project>/profile/register/` (in a work copy: wherever the project folder is; `CC-NC/` projects alike). Beside
`profile/priors.yaml`, `brief.md`, `seeds.json`, which stay files of their own. The profile folder is where every tool
already looks for the store (`langtools.Project.profile`, `grammar.profile_dir`, `language_profile.py check <dir>`), so
the register moves nothing a tool or a person has to find; make-tanakh-grammar's language repositories keep theirs in
`.tanakh/register/`, the same format.

```
profile/register/
  STORE.json            the old files: per file its header (iso, edition, partition, licence, analysis; the
                        orthography as a reference to its entry) and the order of its entries
  VERSION.json          {revision, date, entries, by kind, sha256, digests}: written by `register.py bump`
  REVISIONS.jsonl       one line per revision: {revision, date, changed: {id: added | changed | removed}}
  term/h639-1a2b3c.json one entry per file: <kind>/<slug>-<first 6 hex of sha256(id)>.json
  name/…  formula/…  feature/…  rule/…  choice/…  morph/…  word/…  letter/…  orthography/…  spelling/…
```

## The entry

Every entry has the envelope (make-tanakh-grammar `shared/register.py`, agreed 2026-11-12):

| field | |
|---|---|
| `id` | `<kind>:<name>`, no white space; stable for the life of the fact |
| `kind` | one of the 13 kinds below |
| `value` | the fact (a string; an object for some) |
| `status` | `proposed` \| `decided` \| `open` \| `superseded` \| `retired` |
| `basis` | `team` \| `human` \| `derived` \| `external` \| `model` (strongest first) |
| `by`, `when` | who (a login, `team:<who>`, `script:<name>`, `agent:<name>`) and the date |
| `supersedes` | the id of the entry this one replaces, or absent |
| `scope`, `evidence`, `from`, `origin`, `note` | as in grammar's register (`origin` = `store:<file>#<store id>` for a converted entry) |

and the payload of its kind:

| kind | payload |
|---|---|
| `feature` | parameter, confidence, frequency, examples |
| `rule` | table, conditions, do, said, verdict, pattern |
| `choice` | unit, ref, rule, parameter, source |
| `term` | source, renderings, denials, replaces, gloss, words, attested |
| `name` | source, renderings, denials, replaces, gloss, words, attested, letters |
| `formula` | source, renderings, gloss, words, attested, pattern |
| `word` | form, class, parts, gloss, lexemes, affixes, never_split |
| `morph` | form, slot, host, position, unimorph, written, variants, tone_pattern, with, productive, greek, agree, class |
| `letter` | examples |
| `orthography` | normalization, ignore_marks, tone, keep_marks, respell |
| `answer` | text, ref, entries, who |
| `question` | text, ref, unit, group, asked, answer |
| `spelling` | from, to, context {before, after, unless}, exceptions, order, said (`docs/word-db.md`, *Respelling*) |

**`store`**, the one field beyond grammar's: what the old store file needs for an exact round trip: `file` (the store
file the entry was in), and only where they differ from what the envelope gives back, `id` (the store id), `kind`
(the store kind), `status` (the store status), `rest` (store fields the envelope and payload have no place for:
`method` where it isn't `team-decision`/`project-decision`/`external`, `confidence` outside features, `alternatives`
fields beyond the renderings, `stats`, `tests`, `figures`, ...), `drop` and `keys` (the field order). It is
bookkeeping for the old readers; an entry written by `register.py add` has only `file`.

### The mapping from the store

| store | register |
|---|---|
| `id` `term:…`, `name:…`, `formula:…`, `letter:…`, `spelling:…` | the same id |
| `m:…`, `w:…` | `morph:…`, `word:…` |
| `gap:…`, kind `gap` | `choice:…` |
| `claim:…`, kind `claim`; kind `cell`; a `feature` that isn't `gb:`/`gs:` | `rule:…` (store kind kept in `store.kind`) |
| `gb:…` | `feature:…`; `gs:…` → `feature:gs:…` |
| the orthography of a file | an `orthography` entry: `orthography:main` (a file whose orthography differs: `orthography:<partition>`) |
| `method` `team-decision` / `project-decision` / `external` / other | `basis` `team` / `human` / `external` / `model` (by `agent:…`) or `derived` |
| `status` `decided` (team or human) / `open` / `superseded` / `retired` / `observed` and the rest | the same / `proposed` (the store status kept) |
| `date` | `when` (none: `1970-01-01`, `store.drop`) |
| `value` + `alternatives` (term, name; formula with alternatives) | `value` + `renderings` (the value `preferred`, each alternative `admitted` or `deprecated`) |
| `supersedes` (a store id) | the register id it maps to |

This is grammar's `onboard/register.py seed` mapping, with two differences: nothing is left out (cells, alternation
cues and superseded entries are kept: `seed` drops them as statistics), and every store field survives (`store`).

## Reading and writing: one loader

- `register.store_file(profile, "decisions.json")` / `register.read(path)`: a store file's dict, exactly as the JSON
  was, from the register if the profile has one, else from the file. Every reader of the store reads through it
  (verse_pack, make_prompt, wiki.py, quotes.py through langtools, check_project, words.py, grammar.py, morphs.py,
  gloss.py, alternations.py, cell_check, concord, package, lang.py, rough_check, decide_text, onboard, language_profile,
  score_store, align.py, nllb/model_text).
- `register.write(path, data, …)`: a writer's whole-file write goes into the register (entries changed, added or
  removed as the data says) when the profile has one, else to the JSON as before.
- `register.entries(project, kinds, status)`: the register's own view (envelope and payload), from the register or from
  an old store converted in memory.
- Agents and people add and change entries with `register.py add | supersede | retire | status`; an edit in place is
  only a status change. For a project with a register, `register.agent_wording` rewrites the prompts' store
  instructions (modes.md's `[store]` lines, the chapter prompt, `team_input.py prompt`, `memory_prompt.py`): "add to
  `profile/decisions.json`" becomes a `register.py add` call. A project with the old store gets the old text, byte for
  byte.

**The questionnaire:** `docs/register/parameters.tsv` (from make-tanakh-grammar's `register/parameters.tsv`, 1,161
questions): a `feature` entry's `parameter` must be one of its ids. Its rows keep their sources' licences, named per row
in the `source` column: Grambank v1.0.2, WALS Online, APiCS Online and AUTOTYP are CC BY 4.0 (credit the source when
you reuse a row), make-tanakh's own rows CC0.

## Commands

```
python3 scripts/register.py convert <project> [--keep]   # the store -> profile/register/ (round trip checked; the JSON files removed)
python3 scripts/register.py check <project>               # the envelope's rules, file names, team decisions binding
python3 scripts/register.py show <project> [id|kind ...]
python3 scripts/register.py add <project> --kind term --name H639 --value vrede [--status decided --basis human --by agent:num022]
                                [--set source='"H639"' --set gloss='[...]']
python3 scripts/register.py supersede <project> term:H639 --value harme [--set replaces='["vrede"]']
python3 scripts/register.py retire <project> <id> [--note why]
python3 scripts/register.py status <project> <id> decided
python3 scripts/register.py bump <project>                # a new revision (also a git tag name to suggest; no tag is made)
```

**The rules** (`check`): an id is `<kind>:<name>`, unique; status, basis, `when` valid; no field outside the envelope,
the payload and `store`; a rendering's status is preferred/admitted/deprecated, the value is the preferred one;
`supersedes` names an entry of the register; **only the team supersedes the team's decided entry**; a spelling entry
has `from`, `to`, `said` and patterns that compile; `orthography.respell` names spelling entries; each file's name is
`file_of(its id)`.

## Lifecycle

`register.py stale | migrate | stamp` run `scripts/lifecycle.py`'s commands of the same name (the code lives there).

- **Revisions:** `register.py bump` writes `VERSION.json` (`register-<n>`, the entries' digests) and a line of
  `REVISIONS.jsonl` with the ids changed since the last revision. `convert` makes `register-1`, the store as it was.
- **Stamps:** `make_prompt.py` records the revision a chapter is drafted against, `chapter_check.py` the one its checks
  last ran against: `.tanakh/runs/<BOOK>_<CCC>.json` in the project folder, `{"drafted": {revision, when}, "checked":
  {...}}` (make-tanakh-grammar's run record place). A chapter without a stamp counts as drafted against `register-1`.
- **Stale:** `lifecycle.py stale <project> [--since REV] [--ids …] [--verses]`: per changed decision the chapters that
  predate it, with the verses it touches (spelling rules on the text; terms and names through the .align).
- **Migrate:** `lifecycle.py migrate <project> --ids … [--books …] [--apply]`, a dry run by default. Whether a decision
  is carried back is a choice per batch, recorded in the migration record (`.tanakh/text-migrations/<time>.json`: ids,
  chapters, applied or proposed, edit files, fingerprints before and after); there is no `applies` field. Mechanical:
  `spelling` (our own text only, never notes, footnotes or store evidence) and term/name swaps the .align locates (one
  linked draft word that is the old value as written; case kept); the rest goes to a review list. Each change is an
  edit record in make-tanakh-review's format (FORMAT.md section 10: `who: script:migrate`, `entry` the decision id, op
  `R`, cat `SPELL` or `WORD`) under `.tanakh/edits/<BOOK>/<BOOK>_<CCC>/`; the `# text` fingerprint of the chapter's
  .align is rewritten (one token for one token: positions stay). `migrate --undo <record>` reverses a batch with new
  edit records. Chapters the team has published (`status.py`) get proposals only; the review project's approval signal
  is not settled yet (a hook in `lifecycle.published`).
