#!/usr/bin/env python3
"""A project's drafting cache: what a later agent needs to continue chapters without re-reading the whole memory
(a book agent after a handover, an agent that adds verses to drafted chapters, a resumed run).

Everything here is derived (from project.yaml, the store, the wiki, the drafts and the selection), so it can be
rebuilt at any time and is git-ignored (export/**/_learn/cache/).

  primer.md          the language in one short file: rules, book titles, quotes, divine names and formulas, the decided
                     and observed terms, names, grammar and spelling observations, gaps, open questions
  <code><nnn>.md     one per drafted chapter: the verses it has (and which part), the store entries its text uses,
                     the open questions of its notes
  drafted.tsv        every drafted verse: code, chapter, verse, part (whole | from_start | to_end), selection version(s);
                     a later build with another selection keeps what earlier ones recorded (a verse is whole once any
                     selection has it whole: its draft then has the whole verse)

A selection (optional; for drafts of chosen verses, e.g. a film's readings) is a TSV with the columns book, chapter,
verse, part (whole | from_start | to_end); verses not in it count as whole.

Usage:
  python3 scripts/draft_cache.py build <project> [--selection FILE] [--version NAME]   # all of the above
  python3 scripts/draft_cache.py new <project> <selection.tsv> [--skip-edition-chapters]
      # verses of a (new) selection not yet drafted, per chapter (add / extend); --skip-edition-chapters: leave out the
      # chapters a style edition already has (a project that drafts only what the editions lack)
"""
import csv, glob, json, os, re, sys

CODE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, CODE)
import yaml  # noqa: E402
from books import ROOT, BY_CODE  # noqa: E402
from project import edition_dir, project_dir  # noqa: E402
import register as RG  # noqa: E402
WORD = re.compile(r"[\wऀ-෿؀-ۿঀ-৿ሀ-፿'’-]+", re.U)


def load_store(pd):
    """the store's live entries, from the register if the project has one, else from the JSON files (register.py)"""
    ents = []
    for f in ("decisions.json", "observations.json"):
        d = RG.store_file(os.path.join(pd, "profile"), f)
        if d:
            ents += d.get("entries", []) if isinstance(d, dict) else d
    return [e for e in ents if e.get("status") not in ("retired", "superseded", "rejected")]


def n_of(e):
    return max([x.get("n", 0) or 0 for x in e.get("evidence", []) if isinstance(x, dict)] or [0])


def short(s, k=160):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= k else s[:k - 1] + "…"


def verses(path):
    """{verse: text} of a draft (verse ranges stand for each verse)."""
    body = [re.sub(r"^//\d\s*", "", l) for l in open(path, encoding="utf-8").read().splitlines()
            if l.strip() and not l.startswith(("!!", "=="))]
    text = re.sub(r"\{[A-Z]:[^{}]*\}", "", " ".join(body))
    parts = re.split(r"(?<![\w>.])v(\d+)(?:-(\d+))?\s", text)
    out = {}
    for i in range(1, len(parts) - 2, 3):
        for n in range(int(parts[i]), int(parts[i + 1] or parts[i]) + 1):
            out[n] = parts[i + 2].strip()
    return out


def selection(path=None):
    sel = {}
    if not path:
        return sel
    for r in csv.DictReader(open(path, encoding="utf-8"), delimiter="\t"):
        sel[(r["book"].lower(), int(r["chapter"]), int(r["verse"]))] = r["part"]
    return sel


def chapters(pd):
    for p in sorted(glob.glob(os.path.join(pd, "*", "[a-z0-9][a-z0-9][a-z0-9][0-9][0-9][0-9].txt"))):
        m = re.match(r"([a-z0-9]{3})(\d{3})\.txt$", os.path.basename(p))
        if m and os.path.basename(os.path.dirname(p)) == m[1]:
            yield m[1], int(m[2]), p


def open_questions(md, k=40):
    """The lines under an 'open question(s)' heading of a notes/wiki file (up to the next heading)."""
    if not os.path.exists(md):
        return []
    out, on = [], False
    for line in open(md, encoding="utf-8").read().splitlines():
        if line.startswith("#"):
            on = "question" in line.lower() or "open" in line.lower()
            continue
        if on and line.strip():
            out.append(short(line, 220))
    return out[:k]


def primer(pd, cfg, store):
    L = [f"# Primer: {cfg.get('language_name', '')} ({cfg.get('language', '')}), {os.path.relpath(pd, ROOT)}", "",
         "Derived by scripts/draft_cache.py from project.yaml, the store and the wiki; rebuilt at will. "
         "Read this first; open the store or wiki only for what it doesn't settle.", ""]
    L += ["## Rules (project.yaml)", ""] + [f"- {short(r, 600)}" for r in cfg.get("rules") or []] + [""]
    if cfg.get("book_titles"):
        L += ["## Book titles", "", "; ".join(f"{k} {v}" for k, v in cfg["book_titles"].items()), ""]
    L += [f"Quotes: {cfg.get('quotes', '')}; chapter word: {cfg.get('chapter_word', '')}", ""]
    by = lambda k: sorted((e for e in store if e.get("kind") == k), key=lambda e: (-n_of(e), e["id"]))
    f = by("formula")
    if f:
        L += ["## Formulas", ""] + [f"- {e['id']}: {e.get('value')}  ({short(e.get('note'), 140)})" for e in f] + [""]
    t = by("term")
    if t:
        L += ["## Terms (source -> rendering; decided first, then by corpus frequency)", ""]
        t.sort(key=lambda e: (e.get("status") != "decided", -n_of(e), e["id"]))
        L += [f"- {e.get('source', '')} {e['id']}: {e.get('value')}" + (" (decided)" if e.get("status") == "decided" else "")
              for e in t] + [""]
    nm = by("name")
    if nm:
        L += ["## Names", "", "; ".join(f"{e.get('source', e['id'])} {e.get('value')}" for e in sorted(nm, key=lambda e: e["id"])), ""]
    for k, title in (("feature", "Grammar and style (observed)"), ("letter", "Spelling and letters"),
                     ("spelling", "Spelling rules"), ("gap", "Gaps: words the corpus lacks")):
        x = by(k)
        if x:
            L += [f"## {title}", ""] + [f"- {e['id']}: {short(e.get('value'), 260)}" for e in x] + [""]
    other = sorted({e.get("kind") for e in store} - {"formula", "term", "name", "feature", "letter", "spelling", "gap"})
    for k in other:
        L += [f"## {k}", ""] + [f"- {e['id']}: {short(e.get('value'), 200)}" for e in by(k)] + [""]
    q = open_questions(os.path.join(pd, "wiki", "questions.md"), 60)
    if not q and os.path.exists(os.path.join(pd, "wiki", "questions.md")):
        q = [short(l, 220) for l in open(os.path.join(pd, "wiki", "questions.md"), encoding="utf-8").read().splitlines()
             if re.match(r"\s*(\d+\.|-)\s", l)][:60]
    if q:
        L += ["## Open questions for a speaker (wiki/questions.md)", ""] + q + [""]
    return "\n".join(L)


def digest(pd, code, ch, path, store, sel):
    vs = verses(path)
    text = " ".join(vs.values())
    words = set(WORD.findall(text))
    used = []
    for e in store:
        v = e.get("value")
        if not isinstance(v, str) or not v.strip() or e.get("kind") in ("feature", "letter", "gap"):
            continue
        toks = WORD.findall(v)
        if toks and len(toks) <= 6 and all(t in words for t in toks) and (len(toks) > 1 or v in text):
            used.append(e)
    L = [f"# {code} {ch}: chapter digest ({os.path.relpath(path, ROOT)})", "",
         "Verses drafted: " + ", ".join(f"{v}" + ("" if sel.get((code, ch, v), "whole") == "whole" else
                                                  f" ({sel[(code, ch, v)]})") for v in sorted(vs)), ""]
    if used:
        L += ["## Store entries this chapter uses", ""]
        L += [f"- {e['id']} ({e.get('kind')}): {e.get('source', '')} {e.get('value')}" for e in
              sorted(used, key=lambda e: (e.get("kind", ""), e["id"]))] + [""]
    q = open_questions(os.path.join(os.path.dirname(path), f"{code}{ch:03d}_notes.md"))
    if q:
        L += ["## Open questions (chapter notes)", ""] + q + [""]
    st = os.path.join(os.path.dirname(path), f"{code}_state.md")
    if os.path.exists(st):
        L += [f"Book state file: {os.path.relpath(st, ROOT)}", ""]
    return "\n".join(L), vs


def build(pname, selpath=None, version=None):
    pd = project_dir(pname)
    cfg = yaml.safe_load(open(os.path.join(pd, "project.yaml"), encoding="utf-8"))
    store, sel = load_store(pd), selection(selpath)
    version = version or (os.path.splitext(os.path.basename(selpath))[0] if selpath else "-")
    out = os.path.join(pd, "_learn", "cache")
    os.makedirs(out, exist_ok=True)
    open(os.path.join(out, "primer.md"), "w", encoding="utf-8").write(primer(pd, cfg, store))
    prev = {}                                  # what earlier builds recorded (another selection's partial verses)
    dt = os.path.join(out, "drafted.tsv")
    if os.path.exists(dt):
        for r in csv.DictReader(open(dt, encoding="utf-8"), delimiter="\t"):
            prev[(r["code"], int(r["chapter"]), int(r["verse"]))] = (r["part"], r["selection"])
    rows, n = [["code", "chapter", "verse", "part", "selection"]], 0
    for code, ch, path in chapters(pd):
        text, vs = digest(pd, code, ch, path, store, sel)
        open(os.path.join(out, f"{code}{ch:03d}.md"), "w", encoding="utf-8").write(text)
        n += 1
        for v in sorted(vs):
            k = (code, ch, v)
            old_part, old_sel = prev.get(k, (None, "-"))
            if k in sel:                       # whole if any selection has it whole: the draft then has the whole verse
                # an earlier "whole" counts only if a selection said so (a build without --selection records "-")
                part = "whole" if sel[k] == "whole" or (old_part == "whole" and old_sel not in ("-", "")) else sel[k]
                sels = "+".join(dict.fromkeys(x for x in (old_sel, version) if x and x != "-")) or version
            else:
                part, sels = old_part or "whole", old_sel
            rows.append([code, ch, v, part, sels])
    with open(os.path.join(out, "drafted.tsv"), "w", encoding="utf-8", newline="") as f:
        csv.writer(f, delimiter="\t", lineterminator="\n").writerows(rows)
    size = sum(os.path.getsize(os.path.join(out, x)) for x in os.listdir(out))
    print(f"{pname}: primer {os.path.getsize(os.path.join(out, 'primer.md')) // 1024} KB, {n} chapter digests, "
          f"{len(rows) - 1} verses in drafted.tsv; cache {size // 1024} KB in {os.path.relpath(out, ROOT)}")


def new(pname, selpath, skip_edition_chapters=False):
    pd = project_dir(pname)
    done = {}
    dt = os.path.join(pd, "_learn", "cache", "drafted.tsv")
    if not os.path.exists(dt):
        raise SystemExit("no drafted.tsv: run `draft_cache.py build` first")
    for r in csv.DictReader(open(dt, encoding="utf-8"), delimiter="\t"):
        done[(r["code"], int(r["chapter"]), int(r["verse"]))] = r["part"]
    cfg = yaml.safe_load(open(os.path.join(pd, "project.yaml"), encoding="utf-8"))
    eds = [os.path.join(ROOT, edition_dir(e)) for e in cfg.get("style_from") or []] if skip_edition_chapters else []
    in_edition = lambda code, ch: any(os.path.exists(os.path.join(d, "text", f"{code}{ch:03d}.txt")) for d in eds)
    todo, skipped = {}, 0
    for (code, ch, v), part in selection(selpath).items():
        if (code, ch, v) not in done and in_edition(code, ch):
            skipped += 1                                  # a style edition has the chapter (--skip-edition-chapters)
            continue
        have = done.get((code, ch, v))
        if have is None:
            todo.setdefault((code, ch), []).append(f"{v} add ({part})")
        elif have != "whole" and part != have:
            todo.setdefault((code, ch), []).append(f"{v} extend ({have} -> {part})")
    order = {c: i for i, c in enumerate(BY_CODE)}          # Bible order (books.tsv), not alphabetical
    for (code, ch), items in sorted(todo.items(), key=lambda kv: (order.get(kv[0][0], 999), kv[0][1])):
        exists = os.path.exists(os.path.join(pd, code, f"{code}{ch:03d}.txt"))
        print(f"{code} {ch} {'(existing chapter)' if exists else '(new chapter)'}: " + ", ".join(items))
    print(f"{sum(len(x) for x in todo.values())} verses in {len(todo)} chapters"
          + (f"; {skipped} verses left out: a style edition has their chapter" if skipped else ""))


def main():
    a = sys.argv[1:]
    opt = lambda k: a[a.index(k) + 1] if k in a and a.index(k) + 1 < len(a) else None
    if len(a) >= 2 and a[0] == "build":
        build(a[1], opt("--selection"), opt("--version"))
    elif len(a) >= 3 and a[0] == "new":
        new(a[1], a[2], "--skip-edition-chapters" in a)
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
