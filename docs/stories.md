# Stories: a story's readings, rebuilt from the drafts

A story file gives the verses a story reads (a film's narration, the Open Bible Stories), in the story's order, in a
project's language: `export/<project>/stories/<id>.txt` (a block per reading) and `<id>.tsv`. It repeats the
chapters, so it is **rebuilt, not published**: `export/**/stories/` is git-ignored, and so is the reading list.

    python3 scripts/stories.py list
    python3 scripts/stories.py build <id> --project <project> [--out DIR]
    python3 scripts/stories.py build <id> --from-repo <clone of a language repository> [--project <project>] [--out DIR]

## The reading list

`import/stories/<licence>/<id>/`, filed by licence like the editions (`CC0`, `CC-BY`, `CC-BY-SA`, `non-free`):

- `story.yaml`: `title`, `licence`, `credit` (printed in the file's header), `source`, `url`, `version`, and
  `numbering: bsb` when the Tanakh references are the BSB's (English) rather than the Hebrew (the default); they are
  then looked up in the Hebrew numbering the drafts use (`vrs.to_heb`), and shown as the list writes them.
- `<id>.readings.tsv`, a header and one row per verse:

| Column | |
|---|---|
| `n` | the reading's number (default: the row) |
| `ref` | `GEN 1:3` or `GEN.1.3`; or the columns `book`, `chapter`, `verse` (books.tsv codes) |
| `part` | `whole` (or empty), `from_start` (the verse's first words), `to_end` (its last words) |
| `source_read` | the Hebrew words read, for a partial reading (the verse's own words, from the WLC) |
| `start`, `end` | time codes (a film's), optional |
| `group` | a frame or passage id, optional (OBS: `story-frame`) |

The work copy's older column names are read too: `film_n` (n), `hebrew_read` (source_read), `partial` (part).

`setup.py --only stories` fetches the Open Bible Stories list at a pinned version (docs/sources.md). A list whose
rights are not settled (a film's selection and order are the film's own) stays in `import/stories/non-free/` and
is not shared until its makers have been asked.

## What goes into the file

- **The text:** the project's drafts (`<code>/<code>NNN.txt`), or a language repository's chapters in
  make-tanakh-review's FORMAT.md (`<BOOK>/<BOOK>_<CCC>.md`), each with its `.align`.
- **A partial reading** of a verse drafted whole is cut by the `.align`: the words read -> their MACULA tokens
  (`orig/heb.sqlite`) -> the draft words linked to them; words with no link go with the cut, a word inside it linked
  only to words not read is reported. Doubtful cuts are printed; a verse that can't be cut is given whole, marked. A
  verse the project drafted only in part (`_learn/cache/drafted.tsv`, draft_cache.py) is used as it is. Greek
  readings are given whole.
- **A reading the drafts don't have** comes from a style edition of the project: quoted unchanged from an open one
  (CC0, CC BY, CC BY-SA), credited in the header and not under our CC0; only referenced from a non-free one. Readings
  found nowhere are listed as missing.
- **Book names:** project.yaml `book_titles`, else the chapter heading, else the English name (books.tsv).
