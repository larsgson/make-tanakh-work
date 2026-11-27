# Publishing: the drafts to a language repository, the analysis to Hugging Face

A project's drafts are published to its global-tanakh language repository (one CC0 repository per language or
dialect, in make-tanakh-review's `template/FORMAT.md`); its language analysis (store, wiki, review overviews, chapter
notes) to the publisher's own Hugging Face dataset. Everything built from an edition's text stays on our machines
(`docs/licensing.md`). Two tools, both a dry run unless `--apply`:

    python3 scripts/publish_repo.py <project> --repo <clone of the language repository> [--books gen,exo] [--report F] [--apply]
    python3 scripts/publish_hf.py <project> [--apply]

## Configuration

Every name of an owner comes from the work copy, never from the template:

- **`publish.yaml`** at the work copy's root (`publish.yaml.example`): `org` (the GitHub organisation of the language
  repositories), `hf_dataset` (`<owner>/<name>`, the publisher's dataset), `hf_private` (default `false`), and
  `publisher` (`login`: the GitHub account that publishes, `name`, `url`).
- **`publish:`** in each `project.yaml`:

  ```yaml
  publish:
    repo: gsw-be              # <code> or <code>-<variety>, the repository's name
    code: gsw                 # ISO 639-3 (default: the first part of `language`)
    variety: be               # a dialect's place tag, 2 to 8 lower-case letters or digits; never in bcp47
    status_labels: [...]      # the five status labels in the language (default: the labels of header.ot)
    footnote_kind: E          # the .notes kind of reader footnotes (T, E, H, N; default E)
    model: claude-opus-5-5    # recorded in .tanakh/runs/ for new chapters (default "claude (model not recorded)")
    drafted_in_quarantine: [] # books drafted in a quarantine that has since ended (the gate's record)
  ```

- **Tokens** only from the work copy's `.env` (`HF_TOKEN`; git-ignored). `publish_repo.py` needs none: it never pushes.

## publish_repo.py

1. **Gate.** Refused: a project in `export/CC-NC/` or `local_output/`; one without `publish.yaml` or `publish:`; one
   that fails `check_project.py`; a clone that isn't `<org>/<repo>` or whose `language.json` names another code. Left
   out, chapter by chapter: a chapter drafted with a non-free (or `quarantine_attributable`) style edition's text of
   its book in view and no quarantine recorded; a chapter without `.align` or with a stale one; the NT for now (the
   repository's greek-nt-clause-layout is not used yet).
2. **Convert** to FORMAT.md 1-4, 8 and 13:
   - `.md`: the status from the draft's head lines (by the five labels), the title, `## headings`, the verse lines;
     `partial: "1-3, 26"` when only some of the chapter's verses are drafted. A chapter already in the repository
     keeps the status there (people's).
   - `.align` (the rows unchanged), `.units` (cut from the links on the clone's pinned hebrew-clause-layout, fetched
     once into `download/hebrew-clause-layout/<revision>/` and checked by the dataset's SHA256SUMS), `.notes` (inline
     notes `{T|E|H|N: …}` at their place, reader footnotes after the word they name, else at the verse's end).
   - `.tanakh/runs/<BOOK>_<CCC>.json` (run, model, code, register, built, screen mark, publisher),
     `.tanakh/glosses.json` (over every chapter in the repository), `.tanakh/publisher.json` (the list form, this
     publisher with `analysis: hf://datasets/<hf_dataset>/<repo>`), `.tanakh/language.json` (the variety added).
3. **Screen** (FORMAT.md 13): each unit against the same verse of every non-free and attributable style edition (the
   edition's numbering read both as it is and mapped to the Hebrew). A failing unit holds its chapter back; the report
   has references and figures, no text. Mark: `passed`, or `not needed` without such an edition.
4. **Compare** with the clone: `new`, `same` (nothing written), `changed` (a re-draft, or sidecars only; a run file
   changes only with the text).
5. **--apply** (a clean clone on `main`): new chapters and derived files in one commit on `main`, the same commit on
   `approved`; changed chapters on `draft/<date>` for a pull request, so reviewers' edits are never written over. The
   push is yours: the command is printed.

Once a chapter is in the language repository, its text there is the master: reviewers' edits come back before any
re-draft (the return path, still to be built; until then no published chapter is re-drafted).

## publish_hf.py

- **The allow-list** (nothing else goes, whatever the folder holds): `profile/*.json`, `profile/*.yaml`,
  `profile/register/**/*.json`, `wiki/**/*.md`, `review_overview*.md`, `<code>/<code>_review_overview.md`,
  `<code>/<code>NNN_notes.md`, `_state.md`. Never `_learn/`, `_eval/`, style reports, BHSA-based files, `.tanakh/`, the
  drafts, or a book in quarantine. Generated: `CREDITS.md`, `README.md` (CC0 except the quotations credited in
  CREDITS.md), `manifest.json` (each file's SHA-256).
- **Checks:** `check_project.py`, and `quotes.py` on exactly the files to upload; a problem stops the run. The review
  app shows `<folder>/review_overview.md` publicly, so it is checked like the rest: a team whose texts are not free
  gets counts there, not quotations.
- **Where:** `<hf_dataset>/<repo>/` (the language repository's name). The upload folder is built in
  `.publish/hf/<repo>/` (git-ignored) for a look after the dry run.
- **--apply** (irreversible): upload (old files no longer allowed deleted), `super_squash_history` to one commit,
  unreferenced LFS files deleted; then the dataset must have exactly one commit and the folder exactly the uploaded
  files. Every publish overwrites; there is no history to recover from.
