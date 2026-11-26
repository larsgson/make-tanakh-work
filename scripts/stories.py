#!/usr/bin/env python3
"""A story's readings in a language, built from the drafts (docs/stories.md): <id>.txt and <id>.tsv, one block per
reading, in the story's order. Story files repeat the chapters, so they are rebuilt, not published.

The reading list is data, fetched at a pinned version (`setup.py --only stories`) or placed by hand:
`import/stories/<licence>/<id>/` with `story.yaml` (title, source, licence, credit, url, version) and
`<id>.readings.tsv` (n, ref, part, source_read, start, end, group; see docs/stories.md). `numbering: bsb` in
story.yaml: the Tanakh references are the BSB's (English) and are looked up in the Hebrew numbering (vrs.to_heb).

The text comes from a project (`--project`: `<code>/<code>NNN.txt` + `.align`) or from a language repository in
make-tanakh-review's FORMAT.md (`--from-repo DIR`: `<BOOK>/<BOOK>_<CCC>.md` + `.align`), or both (the repository's
text, the project's book names and editions).
- A reading of part of a verse (`from_start`, `to_end`) is cut from the whole drafted verse by the .align: the
  original words read (`source_read`) -> their MACULA tokens -> the draft words linked to them (Hebrew; a Greek
  reading is given whole, marked). A verse the project drafted only in part (draft_cache.py's drafted.tsv) is used
  as it is. The doubtful cuts are printed.
- A reading the drafts don't have comes from a style edition of the project: quoted from an open one (CC0, CC BY,
  CC BY-SA; credited in the header, not our CC0), only referenced from a non-free one. Readings found nowhere are
  listed as missing.
- Book names: project.yaml `book_titles`, else the draft's chapter heading, else English (books.tsv).

    python3 scripts/stories.py list                                       # the stories found under import/stories/
    python3 scripts/stories.py build <story> --project P [--from-repo DIR] [--out DIR]
    python3 scripts/stories.py build <story> --from-repo DIR [--out DIR]
"""
import argparse, csv, glob, os, re, sqlite3, sys, unicodedata

CODE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.abspath(os.environ.get("MAKE_TANAKH_ROOT") or CODE)
sys.path.insert(0, os.path.join(CODE, "scripts"))
from books import BY_CODE  # noqa: E402
import full_align as FA  # noqa: E402

OPEN = ("CC0", "CC-BY", "CC-BY-SA")
PARTS = ("whole", "from_start", "to_end")
ALIASES = {"film_n": "n", "hebrew_read": "source_read", "partial": "part"}


# ------------------------------------------------------------------ the reading list

def story_dirs():
    """{id: folder} of the stories under import/stories/ (any depth: <licence>/<id>/ or <id>/)"""
    out = {}
    for f in glob.glob(os.path.join(ROOT, "import", "stories", "**", "*.readings.tsv"), recursive=True):
        out[os.path.basename(f)[:-len(".readings.tsv")]] = os.path.dirname(f)
    return out


def story_meta(d):
    import yaml
    f = os.path.join(d, "story.yaml")
    m = (yaml.safe_load(open(f, encoding="utf-8")) or {}) if os.path.exists(f) else {}
    m.setdefault("licence", os.path.basename(os.path.dirname(d)) if os.path.basename(os.path.dirname(d)) != "stories" else "")
    return m


REF = re.compile(r"^\s*([1-3]?[A-Za-z]{2,3})[ .](\d+)[:.](\d+)\s*$")


def readings(path):
    """[{n, code, ch, v, part, source_read, start, end, group}] of a readings file. A row names one verse: `ref`
    (`GEN 1:3`, `GEN.1.3`) or book/chapter/verse columns. part: whole (or empty), from_start, to_end; `yes` (a
    partial reading without its side) is taken as whole, marked"""
    out = []
    for i, r in enumerate(csv.DictReader(open(path, encoding="utf-8"), delimiter="\t"), 1):
        r = {ALIASES.get(k, k): (v or "").strip() for k, v in r.items() if k}
        if r.get("ref"):
            m = REF.match(r["ref"])
            if not m:
                raise SystemExit(f"{os.path.basename(path)} row {i}: ref {r['ref']!r} is not BOOK C:V")
            code, ch, v = m[1].lower(), int(m[2]), int(m[3])
        else:
            code, ch, v = r["book"].lower(), int(r["chapter"]), int(r["verse"])
        if code not in BY_CODE:
            raise SystemExit(f"{os.path.basename(path)} row {i}: no book {code!r} (books.tsv codes)")
        part = r.get("part") or "whole"
        out.append({"n": r.get("n") or str(i), "code": code, "ch": ch, "v": v,
                    "part": part if part in PARTS else "part", "source_read": r.get("source_read", ""),
                    "start": r.get("start", ""), "end": r.get("end", ""), "group": r.get("group", "")})
    return out


# ------------------------------------------------------------------ the text: a project or a language repository

class Text:
    """the drafted verses, their .align rows and the chapter headings, from a project or a FORMAT.md repository"""
    def __init__(self, project=None, repo=None):
        self.project, self.repo, self._c = project, repo, {}
        self.pd = None
        if project:
            from project import project_dir
            self.pd = project_dir(project)

    def chapter(self, code, ch):
        """-> (verses {v: text}, align rows {v: (main, fn, profile)}, align hash, heading or None)"""
        k = (code, ch)
        if k in self._c:
            return self._c[k]
        verses, rows, h, head = {}, {}, None, None
        if self.repo:
            B = code.upper()
            md = os.path.join(self.repo, B, f"{B}_{ch:03d}.md")
            al = os.path.join(self.repo, B, f"{B}_{ch:03d}.align")
            if os.path.exists(md):
                body = open(md, encoding="utf-8").read()
                if body.startswith("---"):
                    body = body.split("\n---", 1)[1] if "\n---" in body else ""
                for l in body.splitlines():
                    m = re.match(r"^(\d+):(\d+)\t(.*)$", l)
                    if m and int(m[1]) == ch and m[3].strip():
                        verses[int(m[2])] = m[3].strip()
                    elif l.startswith("# ") and head is None:
                        head = l[2:].strip()
        elif self.pd:
            base = os.path.join(self.pd, code, f"{code}{ch:03d}")
            al = base + ".align"
            if os.path.exists(base + ".txt"):
                verses = dict(FA.draft_texts(base + ".txt"))
                m = re.search(r"^===(.*?)===", open(base + ".txt", encoding="utf-8").read(), re.M)
                head = m[1].strip() if m else None
        else:
            al = ""
        if al and os.path.exists(al):
            h, rows = FA.read_chapter(al)
        self._c[k] = (verses, rows, h, head)
        return self._c[k]


# ------------------------------------------------------------------ a partial reading cut by the .align

CONS = re.compile(r"[א-ת]")


def consonants(s):
    return "".join(CONS.findall(unicodedata.normalize("NFD", s)))


def heb_words(con, code, ch, v):
    """[(consonants of the written word, [MACULA keys])] in order (orig/heb.sqlite)"""
    words = {}
    for k, w, t in con.execute("select key, word, text from tokens where book=? and ch=? and v=? order by key",
                               (code.upper(), ch, v)):
        words.setdefault(w, [[], ""])
        words[w][0].append(k)
        words[w][1] += t or ""
    return [(consonants(t), keys) for _, (keys, t) in sorted(words.items())]


def read_keys(con, code, ch, v, part, source_read):
    """the MACULA keys of the words read, or (None, why)"""
    words = heb_words(con, code, ch, v)
    read = [w for w in (consonants(x) for x in re.sub(r"[…«»]", " ", source_read).split()) if w]
    if not read:
        return None, "no source_read: the words read are needed to cut the verse"
    seq = words if part == "from_start" else words[::-1]
    want = read if part == "from_start" else read[::-1]
    keys, i = [], 0
    for w in want:                                  # word by word; a maqaf compound may be one word in the list
        got = ""
        while i < len(seq) and len(got) < len(w):
            got += seq[i][0]
            keys += seq[i][1]
            i += 1
        if got != w:
            return None, f"source_read doesn't match the verse at {w!r} (the verse has {got!r})"
    return keys, None


def spans(text):
    """the token spans [(start, end)] of a verse text, the same runs as FA.tokenize, with their offsets"""
    out, start = [], None
    for i, c in enumerate(text):
        if FA.dropped(c):
            continue
        if unicodedata.category(c)[0] in ("L", "M"):
            start = i if start is None else start
        elif start is not None:
            out.append((start, i)); start = None
    if start is not None:
        out.append((start, len(text)))
    return out


def excerpt(T, code, ch, v, part, source_read, con):
    """(the part of a whole drafted verse that is read, [doubts]); (None, [why]) where it can't be cut"""
    verses, rows, h, _ = T.chapter(code, ch)
    flags = []
    if not rows:
        return None, ["no .align"]
    if h != FA.text_hash(ch, sorted(verses.items())):
        flags.append("stale .align")
    if v not in verses or v not in rows:
        return None, ["verse not drafted"]
    text = verses[v]
    sp = spans(text)
    if len(sp) != len(FA.tokenize(text)):
        flags.append("tokenizer differs (a script without spaces?)")
    keys, why = read_keys(con, code, ch, v, part, source_read)
    if keys is None:
        return None, [why]
    ords = FA.ordinals(code.upper(), f"{code.upper()} {ch}:{v}")
    read = {ords[k] for k in keys if k in ords}
    main, fn, _ = rows[v]
    link = {}                                       # target position -> {("c"|"f", ordinal)}
    for kind, s in (("c", main), ("f", fn)):
        for o, ids in FA.parse(s).items():
            for p in ids:
                link.setdefault(p, set()).add((kind, o))
    for p, owner in FA.decisions(fn)["plus"]:
        if owner:
            link.setdefault(p, set()).add(owner)
    hit = sorted(p for p, ow in link.items() if ow & read)
    linked = {o for ow in link.values() for o in ow} & read
    content = {o for o in read if o[0] == "c"}
    if content - linked:
        dec = FA.decisions(main)
        none = {("c", o) for o in dec["none"]} | {("c", o) for o in dec["u"]}
        if content - linked - none:
            flags.append(f"{len(content - linked - none)} read content tokens not linked")
    if not hit:
        return None, flags + ["no draft word linked to the part read"]
    lo, hi = (0, hit[-1]) if part == "from_start" else (hit[0], len(sp) - 1)
    unread = lambda p: p in link and not (link[p] & read)
    other = [p for p in range(lo, hi + 1) if unread(p)]
    if other:
        flags.append(f"{len(other)} words inside linked only to words not read: "
                     + " ".join(text[sp[p][0]:sp[p][1]] for p in other))
    if any(not lo <= p <= hi for p in hit):
        flags.append("words read outside the cut")
    if part == "from_start":                        # words with no link (added for the grammar) go with the cut
        while hi + 1 < len(sp) and not unread(hi + 1):
            hi += 1
    else:
        while lo > 0 and not unread(lo - 1):
            lo -= 1
    start = 0 if lo == 0 else sp[lo][0]
    end = len(text) if hi == len(sp) - 1 else sp[hi][1]
    while start > 0 and not text[start - 1].isspace():      # an opening quote or bracket at the cut
        start -= 1
    while end < len(text) and not text[end].isspace():      # a closing quote or punctuation at the cut
        end += 1
    cut = re.sub(r"\s*//\d+\s*", " ", text[start:end]).strip()
    if part == "from_start" and end < len(text):
        cut = re.sub(r"[\s,;:]+$", "", cut) + " …"
    if part == "to_end" and start > 0:
        cut = "… " + cut
    return cut, flags


# ------------------------------------------------------------------ editions for readings not drafted

def style_editions(project):
    """[(text folder, credit, open?)] of the project's style editions"""
    if not project:
        return []
    from project import project as proj_cfg, edition as ed_cfg
    out = []
    for e in proj_cfg(project).get("style_from") or []:
        try:
            ed = ed_cfg(e) if isinstance(e, str) else e
        except Exception:                            # noqa: BLE001  (an edition not fetched here)
            continue
        d = os.path.join(ROOT, ed["dir"], ed.get("text_dir", "text"))
        out.append((d, ed.get("credit") or ed.get("name") or os.path.basename(ed["dir"]), ed["licence_folder"] in OPEN))
    return out


def edition_verse(eds, code, ch, v, cache):
    """-> (text or None for a non-free edition, credit, open?, the chapter's heading) of the first edition that has it"""
    import langtools as LT
    for d, credit, is_open in eds:
        f = os.path.join(d, f"{code}{ch:03d}.txt")
        if f not in cache:
            cache[f] = {vv: t for (c, vv), t in LT.verses_of(f).items()} if os.path.exists(f) else {}
        t = cache[f].get(v)
        if t:
            m = re.search(r"^===(.*?)===", open(f, encoding="utf-8").read(), re.M)
            return (t if is_open else None), credit, is_open, (m[1].strip() if m else None)
    return None, None, None, None


# ------------------------------------------------------------------ build

def book_name(cfg, code, head):
    t = (cfg.get("book_titles") or {}).get(code)
    if t:
        return t
    if head:                                        # "Første Mosebog, kapitel 20" / "Ds Buech, Kapitel 1"
        return re.split(r",", head)[0].strip()
    return BY_CODE[code][1]


def build(story, project=None, repo=None, out=None, quiet=False):
    """-> (txt lines, tsv rows, missing, cuts); writes <out>/<story>.txt and .tsv"""
    dirs = story_dirs()
    if story not in dirs:
        raise SystemExit(f"no story {story!r} under import/stories/ (found: {', '.join(sorted(dirs)) or 'none'}); "
                         "python3 scripts/setup.py --only stories, or docs/stories.md for your own")
    meta, R = story_meta(dirs[story]), readings(os.path.join(dirs[story], f"{story}.readings.tsv"))
    cfg = {}
    if project:
        from project import project as proj_cfg
        cfg = proj_cfg(project)
    T, eds, ecache = Text(project, repo), style_editions(project), {}
    db = os.path.join(ROOT, "orig", "heb.sqlite")
    con = sqlite3.connect(db) if os.path.exists(db) else None
    whole = {}                                      # draft_cache.py: which verses the project drafted whole
    if T.pd and not repo:
        dt = os.path.join(T.pd, "_learn", "cache", "drafted.tsv")
        if os.path.exists(dt):
            whole = {(x["code"], int(x["chapter"]), int(x["verse"])): x["part"]
                     for x in csv.DictReader(open(dt, encoding="utf-8"), delimiter="\t")}
    lang = cfg.get("language_name") or project or os.path.basename(os.path.normpath(repo or "")) or "?"
    txt = [f"# {meta.get('title') or story}: the readings in {lang} (draft, CC0), in the story's order",
           "# »…« = only part of the verse is read." + (f" The reading list: {meta['credit']}." if meta.get("credit") else "")]
    tsv = [["n", "start", "end", "group", "ref", "part", "text"]]
    missing, cuts, used = [], [], {}
    bsb = str(meta.get("numbering", "heb")).lower() == "bsb"
    import vrs
    for r in R:
        code, part = r["code"], r["part"]
        shown = (r["ch"], r["v"])                   # the list's own numbering, in the reference shown
        ch, v = vrs.to_heb(code, r["ch"], r["v"]) if bsb and BY_CODE[code][2] == "ot" else shown
        verses, _, _, head = T.chapter(code, ch)
        text, note = verses.get(v), ""
        if text is None:
            et, credit, is_open, ehead = edition_verse(eds, code, ch, v, ecache)
            head = head or ehead                    # the book's name as the edition writes it
            if credit:
                used[credit] = is_open
                text = et if is_open else f"[in {credit}; not quoted: non-free]"
                if is_open and part != "whole":
                    note = " [whole verse; only part is read]"
        elif part in ("from_start", "to_end") and whole.get((code, ch, v), "whole") == "whole":
            cut, flags = (excerpt(T, code, ch, v, part, r["source_read"], con) if con and BY_CODE[code][2] == "ot"
                          else (None, ["a Greek reading: not cut" if con else "no orig/heb.sqlite (setup.py --only src)"]))
            if cut:
                text = cut
                if flags:
                    cuts.append(f"{code.upper()} {ch}:{v} ({part}): {'; '.join(flags)}")
            else:
                cuts.append(f"{code.upper()} {ch}:{v} ({part}): not cut: {'; '.join(flags)}")
                note = " [whole verse; only part is read]"
        elif part in ("from_start", "to_end"):     # drafted in part: the part read, as the draft has it
            text = text.strip().strip("…").strip()
            text = text + " …" if part == "from_start" else "… " + text
        elif part == "part":
            note = " [only part is read]"
        ref = f"{book_name(cfg, code, head)} {shown[0]}:{shown[1]}"
        if text is None:
            missing.append(f"{code.upper()} {ch}:{v}")
            text = "[not drafted yet]"
        text += note
        when = f"[{r['start'][:8]}–{r['end'][:8]}] " if r["start"] else ""
        txt += [f"{when}{ref}", text, ""]
        tsv.append([r["n"], r["start"], r["end"], r["group"], ref, part, text])
    if used:
        txt.insert(2, "# Readings the drafts don't have come from: " + "; ".join(
            f"{c} ({'quoted, not our CC0' if o else 'referenced only: non-free'})" for c, o in sorted(used.items())) + ".")
    out = out or (os.path.join(T.pd, "stories") if T.pd else os.path.join(os.path.normpath(repo), ".stories"))
    os.makedirs(out, exist_ok=True)
    open(os.path.join(out, f"{story}.txt"), "w", encoding="utf-8").write("\n".join(txt))
    with open(os.path.join(out, f"{story}.tsv"), "w", encoding="utf-8", newline="") as f:
        csv.writer(f, delimiter="\t", lineterminator="\n").writerows(tsv)
    if not quiet:
        if cuts:
            print("cuts to look at:\n  " + "\n  ".join(cuts))
        print(f"{story}: {len(R)} readings, {len(R) - len(missing)} with text, {len(missing)} missing"
              + (f" ({', '.join(missing[:8])}{' …' if len(missing) > 8 else ''})" if missing else "")
              + f"; {os.path.join(out, story + '.txt')}")
    return txt, tsv, missing, cuts


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    b = sub.add_parser("build"); b.add_argument("story"); b.add_argument("--project"); b.add_argument("--from-repo", dest="repo")
    b.add_argument("--out")
    a = ap.parse_args()
    if a.cmd == "list":
        for k, d in sorted(story_dirs().items()):
            m = story_meta(d)
            n = sum(1 for _ in open(os.path.join(d, f"{k}.readings.tsv"), encoding="utf-8")) - 1
            print(f"{k}\t{n} readings\t{m.get('licence', '?')}\t{m.get('title', '')}\t{os.path.relpath(d, ROOT)}")
        return
    if not (a.project or a.repo):
        ap.error("build needs --project, --from-repo, or both")
    build(a.story, a.project, a.repo, a.out)


if __name__ == "__main__":
    main()
