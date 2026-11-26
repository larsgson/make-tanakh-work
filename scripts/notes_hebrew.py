#!/usr/bin/env python3
"""The original text in a chapter's notes: from the open text, never from orig/heb/; and notes without whole verses.

orig/heb/ is our BHSA copy (the BHS text, CC BY-NC): agents consult its clause layout but never copy its text. The
original that the notes quote comes from the open texts: the Westminster Leningrad Codex (public domain) via MACULA
Hebrew in orig/heb.sqlite, and for the NT the Berean Greek Bible (orig/grc/, CC0).

The notes table (v0.11.0): *Verse · <Hebrew|Greek> · Comment*, the middle column a phrase the note is about (a few
words, the open text word for word; optional), never a whole verse: not the original's, not the BSB's, not a copy of
the draft. A reader gets the verses from their sources (the website's verse view does). quotes.py checks that a phrase
is the WLC / BGB word for word.

- `<project> <code> <ch>` / `--all`: the credit line for the original text where the notes quote it (replaced, not
  repeated, on a second run; removed where they quote none), and a count of the whole verses still in a table.
- `slim <project> [<code> [<ch>]] [--apply]`: the older tables (a row per verse with the whole verse, or the
  rendering and BSB columns) in the new form: a whole verse in any column is emptied; a short rendering or BSB phrase
  goes into the comment (»rendering« (BSB phrase): comment), so no choice is lost; an original phrase stays. A dry
  run by default, with a summary; tables that are not verse tables are left alone.
- `show <code> <ch>:<v>`: one verse of the open original (for an agent).

    python3 scripts/notes_hebrew.py <project> <code> <ch>
    python3 scripts/notes_hebrew.py <project> --all
    python3 scripts/notes_hebrew.py slim <project> [<code> [<ch>]] [--apply]
    python3 scripts/notes_hebrew.py show <code> <ch>:<v>
"""
import glob, os, re, sqlite3, sys

CODE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.abspath(os.environ.get("MAKE_TANAKH_ROOT") or CODE)   # the data root (books.py)
sys.path.insert(0, os.path.join(CODE, "scripts"))
from books import BY_CODE  # noqa: E402
from project import project_dir  # noqa: E402

CREDIT_MARK = "Original text in these notes:"
CREDIT = {"ot": f"*{CREDIT_MARK} Hebrew from the Westminster Leningrad Codex (public domain), via MACULA Hebrew "
                f"(CC BY 4.0, Clear Bible).*",
          "nt": f"*{CREDIT_MARK} Greek from the Berean Greek Bible (public domain, CC0).*"}
ORIGINAL = re.compile(r"[\u0590-\u05FF\uFB1D-\uFB4F\u0370-\u03FF\u1F00-\u1FFF]")   # Hebrew or Greek letters
VERSE_HEAD = re.compile(r"^(verse|vers|v\.?|vers\.?)$", re.I)
SEP = re.compile(r"^\s*\|[\s:|-]+\|\s*$")


def original_verses(code, ch):
    """{verse: text} of the open original: WLC (MACULA Hebrew, orig/heb.sqlite) or BGB (orig/grc)."""
    if BY_CODE[code][2] == "nt":
        import langtools as LT
        f = os.path.join(ROOT, "orig", "grc", f"{code}{ch:03d}.txt")
        return {v: t for (c, v), t in LT.verses_of(f).items()} if os.path.exists(f) else {}
    db = os.path.join(ROOT, "orig", "heb.sqlite")
    if not os.path.exists(db):
        raise SystemExit("orig/heb.sqlite is missing: python3 scripts/setup.py --only src")
    out = {}
    for v, t, a in sqlite3.connect(db).execute("select v, text, after from tokens where book=? and ch=? order by key",
                                              (code.upper(), ch)):
        out[v] = out.get(v, "") + (t or "") + (a or "")
    return {v: re.sub(r"\s+", " ", t).strip() for v, t in out.items()}


def split_row(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def notes_table(md):
    """The notes' verse table (the first Markdown table whose first column is Verse/Vers):
    -> (rows, header cells, the notes without it, (first line, last line) of the table or None)."""
    lines, rows, head, out, i, span = md.splitlines(), [], None, [], 0, None
    while i < len(lines):
        l = lines[i]
        if head is None and l.lstrip().startswith("|") and VERSE_HEAD.match(split_row(l)[0]) and i + 1 < len(lines) \
                and SEP.match(lines[i + 1]):
            head, start, i = split_row(l), i, i + 2
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                rows.append(split_row(lines[i]))
                i += 1
            span = (start, i)
            k = len(out) - 1                       # the table's own heading, when nothing else is under it
            while k >= 0 and not out[k].strip():
                k -= 1
            nxt = next((x for x in lines[i:] if x.strip()), "")
            if k >= 0 and re.match(r"^#{1,6} ", out[k]) and (not nxt or re.match(r"^#{1,6} ", nxt)):
                del out[k:]
            continue
        out.append(l)
        i += 1
    return rows, head, "\n".join(l for l in out if CREDIT_MARK not in l), span


def verse_numbers(cell):
    """'1' '1.2.6.22' '1–3' '3,5' '16a' 'v3' -> [1, 2, …]"""
    out = []
    for part in re.split(r"[.,;/ ]+", re.sub(r"^v", "", cell.strip(), flags=re.I)):
        m = re.match(r"^(\d+)[a-z]?(?:\s*[-–]\s*(\d+))?", part)
        if m:
            a, b = int(m[1]), int(m[2] or m[1])
            out += list(range(a, min(b, a + 200) + 1))
    return out


def whole(cell, verse, cut=0.4):
    """is a table cell a whole verse (or the verse cut with …)? ≥ 60% of its words, or ending with … and ≥ cut of them"""
    cell = (cell or "").strip()
    n, full = len(cell.split()), len((verse or "").split())
    return bool(cell and full and (n >= 0.6 * full or (cell.endswith("…") and n >= cut * full)))


def is_verse(cell, verse):
    """a rendering or BSB cell that is the verse itself (whole(), and ≥ 80% of its words are the verse's words), not a
    long phrase with a note around it"""
    if not whole(cell, verse):
        return False
    w = lambda t: re.findall(r"\w+", t.lower())
    cw, vw = w(cell), set(w(verse))
    return bool(cw) and sum(x in vw for x in cw) >= 0.8 * len(cw)


def credit(md, code):
    """the notes with the credit line where they quote the original (Hebrew or Greek letters outside it), without it
    where they quote none"""
    body = "\n".join(l for l in md.splitlines() if CREDIT_MARK not in l).rstrip()
    if ORIGINAL.search(body):
        return body + "\n\n" + CREDIT["nt" if BY_CODE[code][2] == "nt" else "ot"] + "\n"
    return body + "\n"


def fill(path, code, ch):
    """One notes file: the credit line as credit() says. -> (whole verses left in its table, changed)"""
    md = open(path, encoding="utf-8").read()
    rows, head, _, span = notes_table(md)
    orig = original_verses(code, ch)
    left = sum(1 for r in rows for vs in [verse_numbers(r[0])] if head and len(head) >= 3 and len(r) > 1 and len(vs) == 1
               and whole(r[1], orig.get(vs[0])))      # the original column (a Verse · Comment table has none)
    new = credit(md, code)
    if new != md:
        open(path, "w", encoding="utf-8").write(new)
    return left, new != md


def slim_text(md, code, ch, draft, bsb):
    """the notes with their verse table in the new form (Verse · original phrase · Comment) -> (new md, stats).
    draft, bsb: {verse: text}, to tell a whole verse in the rendering and BSB columns"""
    rows, head, _, span = notes_table(md)
    st = {"rows": len(rows), "emptied": 0, "folded": 0, "dropped": 0}
    if not span or not head or len(head) < 3:
        return md, st
    orig = original_verses(code, ch)
    out = []
    for r in rows:
        r = r + [""] * (len(head) - len(r))
        vs = verse_numbers(r[0]); v = vs[0] if len(vs) == 1 else None
        o, mids, cm = r[1], r[2:len(head) - 1], r[len(head) - 1]
        if v and whole(o, orig.get(v)):
            o = ""; st["emptied"] += 1
        phr = []
        for x in mids:
            x = x.strip()
            if not x or x in ("–", "-", "—"):
                continue
            if v and (is_verse(x, draft.get(v)) or is_verse(x, bsb.get(v))):
                st["emptied"] += 1; continue
            phr.append(x)
        if phr:
            st["folded"] += 1
            lead = f"»{phr[0]}«" + (f" ({' / '.join(phr[1:])})" if phr[1:] else "")
            cm = lead + (f": {cm}" if cm.strip() else "")
        if not (o.strip() or cm.strip()):
            st["dropped"] += 1; continue
        out.append((r[0], o, cm))
    keep_o = any(o.strip() for _, o, _ in out)
    hd = [head[0], head[1], head[-1]] if keep_o else [head[0], head[-1]]
    tab = ["| " + " | ".join(hd) + " |", "|" + "---|" * len(hd)]
    tab += ["| " + " | ".join([a_, o, c_] if keep_o else [a_, c_]) + " |" for a_, o, c_ in out]
    lines = md.splitlines()
    new = "\n".join(lines[:span[0]] + tab + lines[span[1]:]) + ("\n" if md.endswith("\n") else "")
    return credit(new, code), st


def project_notes(pname):
    pdir = project_dir(pname)
    out = []
    for f in sorted(glob.glob(os.path.join(pdir, "**", "*_notes.md"), recursive=True)):
        if "/_eval/local/" in f.replace(os.sep, "/"):
            continue
        m = re.fullmatch(r"([0-9a-z]{3})(\d{3})_notes\.md", os.path.basename(f))
        if m and m[1] in BY_CODE:
            out.append((f, m[1], int(m[2])))
    return out


def slim(pname, code=None, ch=None, apply=False):
    """slim_text over a project's notes (or one book or chapter); a dry run unless apply. -> summary dict"""
    import collections, langtools as LT, words as W
    P = LT.Project(pname)
    tot = collections.Counter()
    for f, c, n in project_notes(pname):
        if (code and c != code) or (ch and n != ch):
            continue
        md = open(f, encoding="utf-8").read()
        dr = os.path.join(os.path.dirname(f), f"{c}{n:03d}.txt")
        draft = {v: t for (_, v), t in LT.verses_of(dr).items()} if os.path.exists(dr) else {}
        bsb = {v: W.bsb_verse(P, c, n, v) for v in set(draft) | set(original_verses(c, n))}
        new, st = slim_text(md, c, n, draft, bsb)
        tot.update({k: v for k, v in st.items() if k != "rows"})
        if new != md:
            tot["files"] += 1; tot["bytes before"] += len(md.encode()); tot["bytes after"] += len(new.encode())
            if apply:
                open(f, "w", encoding="utf-8").write(new)
    return tot


def main():
    a = sys.argv[1:]
    if a[:1] == ["show"] and len(a) == 3:
        ch, v = map(int, a[2].split(":"))
        print(original_verses(a[1], ch).get(v, ""))
        return
    if a[:1] == ["slim"] and len(a) >= 2:
        rest = [x for x in a[2:] if x != "--apply"]
        t = slim(a[1], rest[0] if rest else None, int(rest[1]) if len(rest) > 1 else None, "--apply" in a)
        saved = t["bytes before"] - t["bytes after"]
        print(f"{a[1]}: {t['files']} notes files {'changed' if '--apply' in a else 'would change'}; "
              f"{t['emptied']} whole-verse cells emptied, {t['folded']} rows with a rendering or BSB phrase moved into "
              f"the comment, {t['dropped']} empty rows dropped; {saved / 1e6:.2f} MB of {t['bytes before'] / 1e6:.2f} MB"
              + ("" if "--apply" in a else " (dry run: --apply writes)"))
        return
    if len(a) == 2 and a[1] == "--all":
        todo = project_notes(a[0])
    elif len(a) == 3:
        f = os.path.join(project_dir(a[0]), a[1], f"{a[1]}{int(a[2]):03d}_notes.md")
        if not os.path.exists(f):
            raise SystemExit(f"no notes {os.path.relpath(f, ROOT)}")
        todo = [(f, a[1], int(a[2]))]
    else:
        raise SystemExit(__doc__)
    left = changed = 0
    for f, code, ch in todo:
        n, c = fill(f, code, ch)
        left += n; changed += c
    print(f"{a[0]}: {len(todo)} notes files, {changed} changed (credit line)"
          + (f"; {left} whole verses in their tables: the notes quote a phrase, not the verse "
             f"(`python3 scripts/notes_hebrew.py slim {a[0]}`)" if left else ""))


if __name__ == "__main__":
    main()
