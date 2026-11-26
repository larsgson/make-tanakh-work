#!/usr/bin/env python3
"""The decisions' lifecycle (docs/register.md, *Lifecycle*): which register revision a chapter was drafted and checked
against, which chapters predate changed decisions, and carrying a decision back into chapters already drafted.

    python3 scripts/lifecycle.py stamp <project> <code> <ch> drafted|checked   # (make_prompt and chapter_check do it)
    python3 scripts/lifecycle.py stale <project> [--since REV] [--ids ID ...] [--books CODE ...] [--verses]
    python3 scripts/lifecycle.py migrate <project> --ids ID ... [--books CODE ...] [--apply] [--out DIR] [--rules FILE]
    python3 scripts/lifecycle.py migrate <project> --undo <record>

The stamp: `.tanakh/runs/<BOOK>_<CCC>.json` in the project folder (make-tanakh-grammar's place for run records), with
{"drafted": {revision, when}, "checked": {revision, when}}. A chapter without a stamp counts as drafted against the
register's first revision (the store as it was converted).

migrate is a dry run by default: a report and the edit records it would write. --apply rewrites the chapter's text
(.txt; the .tagged interim words alike), the `# text` fingerprint of its .align, and writes the edit records
(`.tanakh/edits/<BOOK>/<BOOK>_<CCC>/<time>-script-migrate.jsonl`, make-tanakh-review's FORMAT.md section 10, who
`script:migrate`, entry = the decision id) and a migration record (`.tanakh/text-migrations/<time>.json`: ids,
chapters, applied or proposed, the edit files, the fingerprints before and after); `--undo <record>` reverses it.
Mechanical: `spelling` entries (our own text only: verse text outside inline notes; never notes, footnotes, headings'
quotations or store evidence), and term/name swaps where the chapter's .align links the source word to exactly one
draft word that is the old value as written; anything else (an inflected form, a phrase, another kind) goes to the
review list. A change of one token never changes the token count, so the .align positions stay. Chapters the team has
published (status.py) get proposals only."""
import argparse, collections, datetime, json, os, re, sys, time

CODE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(CODE, "scripts"))
import register as RG  # noqa: E402
from books import BY_CODE  # noqa: E402
from project import project_dir  # noqa: E402

ROOT = os.path.abspath(os.environ.get("MAKE_TANAKH_ROOT") or CODE)


# ------------------------------------------------------------------ stamps

def run_file(pname, code, ch):
    return os.path.join(project_dir(pname), ".tanakh", "runs", f"{code.upper()}_{ch:03d}.json")


def stamp(pname, code, ch, what, rev=None):
    """record the register revision a chapter was drafted (make_prompt) or last checked (chapter_check) against"""
    f = run_file(pname, code, ch)
    d = json.load(open(f, encoding="utf-8")) if os.path.exists(f) else {"book": code.upper(), "chapter": ch}
    d[what] = {"revision": rev or RG.revision(RG.profile_of(pname)),
               "when": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    os.makedirs(os.path.dirname(f), exist_ok=True)
    with open(f, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(d, ensure_ascii=False, indent=1) + "\n")
    return d


def drafted_rev(pname, code, ch):
    f = run_file(pname, code, ch)
    d = json.load(open(f, encoding="utf-8")) if os.path.exists(f) else {}
    return RG.rev_n((d.get("drafted") or {}).get("revision")) or 1


def chapters(pname, books=None):
    d = project_dir(pname)
    for code in BY_CODE:
        if books and code not in books:
            continue
        for f in sorted(os.listdir(os.path.join(d, code))) if os.path.isdir(os.path.join(d, code)) else []:
            m = re.fullmatch(rf"{code}(\d{{3}})\.txt", f)
            if m:
                yield code, int(m[1]), os.path.join(d, code, f)


def published(pname, code, ch):
    """has the team approved the chapter? status.py's published state. Hook: the review project's approval signal is
    not settled (make-tanakh-review); when it is, read it here as well"""
    import status
    return (status.load(project_dir(pname)).get(f"{code}{ch:03d}") or {}).get("status") == "published"


# ------------------------------------------------------------------ the draft's tokens with their places in the file

def verse_tokens(text):
    """[(verse, position in the verse, start, end)] of a draft file's text: the tokens of each verse's translatable text
    (bridge_align's reading: no head lines, title or headings, no verse markers, no inline notes), with their offsets
    in the file. Positions are those of words.written_tokens and of the .align"""
    import full_align as FA, bridge_align as BA, langtools as LT, unicodedata
    skip = []
    for m in re.finditer(r"^(!!<.*|===.*===\s*|==.*==\s*)$", text, re.M):
        skip.append((m.start(), m.end()))
    for m in BA.NOTE.finditer(text):
        skip.append((m.start(), m.end()))
    marks = [(m.start(), m.end(), int(m[1])) for m in BA.MARK.finditer(text)]
    skip += [(a, b) for a, b, _ in marks]
    skip.sort()
    out, v, pos, i, n = [], None, collections.Counter(), 0, len(text)
    mi, si = 0, 0
    while i < n:
        while si < len(skip) and skip[si][1] <= i:
            si += 1
        if si < len(skip) and skip[si][0] <= i < skip[si][1]:
            while mi < len(marks) and marks[mi][0] < skip[si][1]:
                if marks[mi][0] >= skip[si][0]:
                    v = marks[mi][2]
                mi += 1
            i = skip[si][1]; continue
        ch = text[i]
        if unicodedata.category(ch)[0] in ("L", "M"):
            j = i
            while j < n and (unicodedata.category(text[j])[0] in ("L", "M") or FA.dropped(text[j])) and \
                    not (si < len(skip) and skip[si][0] <= j < skip[si][1]):
                j += 1
            w = text[i:j]
            parts = LT._segment_like_bcv(w)
            if v is not None:
                k = i
                for p in parts:
                    out.append((v, pos[v], k, k + len(p), len(parts) > 1)); pos[v] += 1; k += len(p)
            i = j
        else:
            i += 1
    return out


def case_like(old, new):
    if old.isupper() and len(old) > 1:
        return new.upper()
    if old[:1].isupper():
        return new[:1].upper() + new[1:]
    return new


# ------------------------------------------------------------------ what changed, and where

def changed_entries(pname, since=None, ids=None):
    prof = RG.profile_of(pname)
    E = {e["id"]: e for e in RG.entries(profile=prof)}
    if ids:
        ch = {i: "named" for i in ids}
    else:
        ch = RG.changed_since(prof, since or 1)
    return E, ch


def spelling_rules(E, ids):
    import words as W
    rules = [{k: E[i].get(k) for k in W.SPELLING} | {"id": i} for i in ids if i in E and E[i]["kind"] == "spelling"
             and E[i]["status"] == "decided"]
    resp = []                                # the orthography's order (orthography.respell), then each rule's `order`
    for e in E.values():
        if e["kind"] == "orthography" and e["status"] not in ("superseded", "retired"):
            resp += [x for x in e.get("respell") or [] if x not in resp]
    rank = {x: n for n, x in enumerate(resp)}
    return sorted(rules, key=lambda r: (rank.get(r["id"], len(rank)), r.get("order") or 0))


def term_swaps(E, ids):
    """[(entry id, lexemes, old forms, new value)] for term/name entries that supersede another"""
    import words as W
    lemmas = W.source_lemmas(); out = []
    for i in ids:
        e = E.get(i)
        if not e or e["kind"] not in ("term", "name") or not e.get("supersedes") or e["status"] in ("superseded", "retired"):
            continue
        o = E.get(e["supersedes"]) or {}
        store_e = RG.to_store(e, {})
        lx = {x for _, x in W.entry_lexemes(store_e, lemmas)}
        old = set(W.value_forms(str(o.get("value") or ""))) | {x for x in e.get("replaces") or [] if isinstance(x, str)}
        out.append((i, lx, {x.strip() for x in old if x.strip()} - {e["value"]}, e["value"]))
    return out


def plan(pname, ids, books=None, rules_file=None, since=None):
    """(changes, review): changes = [{code, ch, path, v, pos, start, end, old, new, entry, cat, published}], review =
    [(entry, code, ch, verse or None, why)]"""
    import words as W, langtools as LT, full_align as FA
    E, ch = changed_entries(pname, since, ids)
    ids = list(ch)
    P = LT.Project(pname)
    sp = spelling_rules(E, ids)
    if rules_file:
        sp += [dict(r, id=r.get("id") or f"spelling:{n}") for n, r in enumerate(W.respell_rules(path=rules_file))]
    swaps = term_swaps(E, ids)
    mech = {r["id"] for r in sp} | {s[0] for s in swaps}
    review = [(i, None, None, None, f"{E[i]['kind'] if i in E else '?'}: not mechanical ({ch[i]})") for i in ids
              if i not in mech and (i not in E or E[i]["kind"] != "spelling")]
    import sqlite3
    db = W.db_file(pname)                    # names: the store's, and forms the corpus links mostly to proper nouns
    names = W.names_of(P, con=sqlite3.connect(db) if os.path.exists(db) else None)
    Rs = [(r["id"], W.Respeller([r], names)) for r in sp]
    changes = []
    for code, c, path in chapters(pname, books):
        if since is None and not ids:
            continue
        text = open(path, encoding="utf-8").read()
        toks = verse_tokens(text)
        pub = published(pname, code, c)
        verses = dict(FA.draft_texts(path))
        by_v = collections.defaultdict(list)
        for t in toks:
            by_v[t[0]].append(t)
        bad = {v for v, ts in by_v.items() if [text[a:b] for _, _, a, b, _ in ts] != W.written_tokens(verses.get(v, ""))}
        for v in sorted(bad):
            review.append(("*", code, c, v, "the verse's tokens could not be placed in the file"))
        proper = set()                       # and the draft words the .align links to a proper noun
        al = path[:-4] + ".align"
        if Rs and os.path.exists(al):
            rows_ = FA.read_chapter(al)[1]; _, S_ = W.chapter_source(code, c)
            for v, r_ in rows_.items():
                m_ = FA.parse(r_[0])
                for o, lx, lem, cls, typ, key in S_.get(v, []):
                    if typ == "proper":
                        proper |= {(v, q) for q in m_.get(o) or []}
        for v, p, a, b, cut in toks:
            if v in bad or cut or (v, p) in proper:
                continue
            w = text[a:b]; low = w.lower(); new = low; ent = None
            for rid, R in Rs:
                x = R(new)
                if x != new:
                    new, ent = x, (ent + "+" + rid if ent else rid)
            if ent:
                changes.append(dict(code=code, ch=c, path=path, v=v, pos=p, start=a, end=b, old=w, new=case_like(w, new),
                                    entry=ent, cat="SPELL", published=pub))
        if swaps:
            al = path[:-4] + ".align"
            if not os.path.exists(al):
                for s in swaps:
                    review.append((s[0], code, c, None, "no .align: the swap can't be located"))
                continue
            rows = FA.read_chapter(al)[1]
            lang, S = W.chapter_source(code, c)
            for v, ts in by_v.items():
                if v in bad or v not in rows:
                    continue
                main = FA.parse(rows[v][0])
                for o, lx, *_ in S.get(v, []):
                    for i, lxs, old, nv in swaps:
                        if lx not in lxs:
                            continue
                        pos = main.get(o) or []
                        words = [ts[q] for q in pos if q < len(ts)]
                        forms = [text[a:b] for _, _, a, b, _ in words]
                        hit = [k for k, f in enumerate(forms) if f.lower() in {x.lower() for x in old}]
                        if len(words) == 1 and hit and " " not in nv:
                            _, q, a, b, _ = words[0]
                            changes.append(dict(code=code, ch=c, path=path, v=v, pos=q, start=a, end=b, old=forms[0],
                                                new=case_like(forms[0], nv), entry=i, cat="WORD", published=pub))
                        elif any(any(W.same_word(f.lower(), x.lower()) for x in old) for f in forms):
                            review.append((i, code, c, v, f"linked words »{' '.join(forms)}« for an old form "
                                           f"{sorted(old)} -> »{nv}«: case, inflection or phrase"))
    return changes, review


# ------------------------------------------------------------------ edit records and applying

def edit_rows(changes, commit):
    """make-tanakh-review FORMAT.md section 10 rows, one per changed token; `quote` from the verse as the file has it
    now (after an applied batch: the new verse, as the format says; in a dry run the old one)"""
    import words as W, full_align as FA
    rows = collections.defaultdict(list)
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    vts = {}
    for x in changes:
        if x["path"] not in vts:
            vts[x["path"]] = dict(FA.draft_texts(x["path"]))
        vt = vts[x["path"]].get(x["v"], "")
        toks = W.written_tokens(vt)
        rows[(x["code"], x["ch"])].append({
            "ref": f"{x['ch']}:{x['v']}", "unit": None, "who": "script:migrate", "when": now, "scope": "this",
            "entry": x["entry"], "draft": None, "why": None, "commit": commit, "op": "R", "cat": x["cat"],
            "span": {"old": [x["pos"], x["pos"] + 1], "new": [x["pos"], x["pos"] + 1]}, "old": x["old"], "new": x["new"],
            "quote": {"prefix": " ".join(toks[max(0, x["pos"] - 3):x["pos"]]), "suffix": " ".join(toks[x["pos"] + 1:x["pos"] + 4])},
            "from_alt": None})
    return rows


def git_head():
    import subprocess
    try:
        return subprocess.run(["git", "-C", ROOT, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip() or None
    except OSError:
        return None


def apply_changes(pname, changes, ids, stamp_s, undo_of=None):
    """write the texts, the .tagged words, the .align fingerprints, the edit records and the migration record"""
    import full_align as FA
    by_file = collections.defaultdict(list)
    for x in changes:
        by_file[x["path"]].append(x)
    fps, files = {}, []
    commit = git_head()
    for path, xs in by_file.items():
        text = open(path, encoding="utf-8").read()
        for x in sorted(xs, key=lambda x: -x["start"]):
            assert text[x["start"]:x["end"]] == x["old"], (path, x)
            text = text[:x["start"]] + x["new"] + text[x["end"]:]
        open(path, "w", encoding="utf-8").write(text)
        tg = path[:-4] + ".tagged"
        if os.path.exists(tg):
            t = open(tg, encoding="utf-8").read()
            for x in xs:      # the tagged interim: the same word before its tag, in the same verse (first not yet changed)
                t = _tagged_swap(t, x)
            open(tg, "w", encoding="utf-8").write(t)
        al = path[:-4] + ".align"
        if os.path.exists(al):
            a = open(al, encoding="utf-8").read()
            c = xs[0]["ch"]
            old = re.search(r"^# text (\S+)", a, re.M)
            new = FA.text_hash(c, FA.draft_texts(path))
            if old:
                a = a.replace(old.group(0), f"# text {new}", 1)
                open(al, "w", encoding="utf-8").write(a)
                fps[os.path.relpath(al, ROOT)] = [old[1], new]
    d = project_dir(pname)
    rows = edit_rows(changes, commit)
    for (code, c), rs in rows.items():
        f = os.path.join(d, ".tanakh", "edits", code.upper(), f"{code.upper()}_{c:03d}", f"{stamp_s}-script-migrate.jsonl")
        os.makedirs(os.path.dirname(f), exist_ok=True)
        with open(f, "w", encoding="utf-8") as fh:
            fh.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rs)
        files.append(os.path.relpath(f, d))
    rec = {"when": stamp_s, "ids": ids, "applied": True, "undo_of": undo_of, "commit": commit,
           "chapters": sorted({f"{x['code']}{x['ch']:03d}" for x in changes}), "edits": files, "fingerprints": fps,
           "changes": [{k: x[k] for k in ("code", "ch", "v", "pos", "start", "old", "new", "entry", "cat")} for x in changes]}
    f = os.path.join(d, ".tanakh", "text-migrations", f"{stamp_s}.json")
    os.makedirs(os.path.dirname(f), exist_ok=True)
    json.dump(rec, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return f, rec


def _tagged_swap(t, x):
    m = re.search(rf"(?m)^v{x['v']}\b", t)
    if not m:
        return t
    nxt = re.search(r"(?m)^v\d+\b", t[m.end():])
    seg_end = m.end() + nxt.start() if nxt else len(t)
    seg = t[m.start():seg_end]
    seg2 = re.sub(rf"(?<![\w]){re.escape(x['old'])}(?=\^|[^\w])", x["new"], seg, count=1)
    return t[:m.start()] + seg2 + t[seg_end:]


def undo(pname, recf):
    """reverse a migration batch: the same tokens back, new edit records, a record of the undo"""
    rec = json.load(open(recf, encoding="utf-8"))
    d = project_dir(pname); changes = []
    for x in rec["changes"]:
        path = os.path.join(d, x["code"], f"{x['code']}{x['ch']:03d}.txt")
        text = open(path, encoding="utf-8").read()
        toks = [t for t in verse_tokens(text) if t[0] == x["v"] and t[1] == x["pos"]]
        if not toks or text[toks[0][2]:toks[0][3]] != x["new"]:
            print(f"{x['code']} {x['ch']}:{x['v']} #{x['pos']}: »{x['new']}« not there any more: left as it is")
            continue
        _, _, a, b, _ = toks[0]
        changes.append(dict(x, path=path, start=a, end=b, old=x["new"], new=x["old"], published=False))
    s = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return apply_changes(pname, changes, rec["ids"], s, undo_of=os.path.basename(recf))


# ------------------------------------------------------------------ commands

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("stamp"); c.add_argument("project"); c.add_argument("code"); c.add_argument("ch", type=int)
    c.add_argument("what", choices=("drafted", "checked"))
    c = sub.add_parser("stale"); c.add_argument("project"); c.add_argument("--since"); c.add_argument("--ids", nargs="*")
    c.add_argument("--books", nargs="*"); c.add_argument("--verses", action="store_true"); c.add_argument("--rules")
    c = sub.add_parser("migrate"); c.add_argument("project"); c.add_argument("--ids", nargs="*", default=[])
    c.add_argument("--books", nargs="*"); c.add_argument("--apply", action="store_true"); c.add_argument("--out")
    c.add_argument("--undo"); c.add_argument("--rules", help="spelling rules from a file as well (words.py --respell's form)")
    c.add_argument("--sample", type=int, default=0)
    a = ap.parse_args()
    if a.cmd == "stamp":
        print(json.dumps(stamp(a.project, a.code, a.ch, a.what), ensure_ascii=False))
    elif a.cmd == "stale":
        prof = RG.profile_of(a.project)
        E, ch = changed_entries(a.project, a.since, a.ids)
        per = collections.defaultdict(list)
        for code, c_, path in chapters(a.project, a.books):
            rev = a.since or drafted_rev(a.project, code, c_)
            later = set(a.ids or RG.changed_since(prof, rev))
            for i in later:
                per[i].append((code, c_))
        changes, review = plan(a.project, list(ch), a.books, a.rules, a.since) if a.verses else ([], [])
        where = collections.defaultdict(lambda: collections.defaultdict(set))
        for x in changes:
            for i in x["entry"].split("+"):
                where[i][(x["code"], x["ch"])].add(x["v"])
        for i in sorted(per):
            k = E.get(i, {}).get("kind", "?")
            print(f"{i} ({k}, {ch.get(i, 'changed')}, mechanical: {RG.MECHANICAL.get(k, 'no')}): {len(per[i])} chapters predate it")
            if a.verses and where.get(i):
                print("   verses: " + "; ".join(f"{c.upper()} {n}:{','.join(map(str, sorted(vs)))}"
                                           for (c, n), vs in sorted(where[i].items())[:30]))
        if a.verses:
            print(f"review list: {len(review)}")
    elif a.cmd == "migrate":
        if a.undo:
            f, rec = undo(a.project, a.undo)
            print(f"undone: {len(rec['changes'])} changes; record {os.path.relpath(f, ROOT)}"); return
        t0 = time.time()
        changes, review = plan(a.project, a.ids, a.books, a.rules)
        pub = [x for x in changes if x["published"]]
        do = [x for x in changes if not x["published"]]
        per = collections.Counter(x["code"] for x in do)
        print(f"{a.project}: {len(do)} words would change in {len({(x['code'], x['ch']) for x in do})} chapters"
              f" ({', '.join(f'{k} {n}' for k, n in per.items())}); {len(pub)} in published chapters (proposals only);"
              f" review list {len(review)}; {time.time() - t0:.0f} s")
        if a.out:
            os.makedirs(a.out, exist_ok=True)
            rows = edit_rows(changes, git_head())
            for (code, c), rs in rows.items():
                with open(os.path.join(a.out, f"{code.upper()}_{c:03d}.jsonl"), "w", encoding="utf-8") as fh:
                    fh.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rs)
            with open(os.path.join(a.out, "review.tsv"), "w", encoding="utf-8") as fh:
                fh.write("entry\tbook\tchapter\tverse\twhy\n")
                fh.writelines(f"{i}\t{c or ''}\t{n or ''}\t{v or ''}\t{w}\n" for i, c, n, v, w in review)
            json.dump({"ids": a.ids, "applied": False, "changes": len(do), "published": len(pub), "review": len(review),
                       "per book": dict(per)}, open(os.path.join(a.out, "summary.json"), "w"), indent=1)
            print("dry run written to", a.out)
        if a.apply:
            s = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
            f, rec = apply_changes(a.project, do, a.ids, s)
            print(f"applied: {len(do)} changes; record {os.path.relpath(f, ROOT)}")


if __name__ == "__main__":
    main()
