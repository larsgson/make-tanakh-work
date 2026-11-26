#!/usr/bin/env python3
"""The decisions' lifecycle (docs/register.md, *Lifecycle*): what a chapter was drafted and checked with, which chapters
a changed decision has gone stale for, and carrying a decision back into chapters already drafted. On the register and
on the JSON store alike.

    python3 scripts/lifecycle.py stamp <project> <code> <ch> drafted|checked   # (make_prompt and chapter_check do it)
    python3 scripts/lifecycle.py stamp <project> --all [--what checked] [--books CODE ...]   # chapters without checksums (asserted)
    python3 scripts/lifecycle.py stamp <project> --all --as-of git [--books ...]   # the store at each chapter's commit
    python3 scripts/lifecycle.py stamp <project> --all --verify [--report F] [--books ...]  # what each chapter follows
    python3 scripts/lifecycle.py stale <project> [--ids ID ...] [--books CODE ...] [--verses] [--since REV] [--stamp drafted|checked]
    python3 scripts/lifecycle.py migrate <project> --ids ID ... [--books CODE ...] [--apply] [--out DIR] [--rules FILE]
    python3 scripts/lifecycle.py migrate <project> --undo <record>

The stamp: {"drafted": {when, basis, sums, general, revision}, "checked": {...}}: the checksums (register.binding_sum) of
the decisions that apply to the chapter by their source word, the digest of the general ones (their checksums in
`.tanakh/general.jsonl`), the register revision if there is a register, and what the stamp rests on (`basis`: prompt,
chapter_check, asserted, git <commit> with `committed` and `modified`, verified with `drift` {id: {sum, verses}} and
`unverified` {id: sum}; see stamp()). stale reports a verified stamp's drift as `drift` and an untested decision only
when it changed (`changed (unverified)`). In `.tanakh/runs/<BOOK>.json` (a key per
chapter) or `.tanakh/runs/<BOOK>_<CCC>.json` (make-tanakh-grammar's place for run records), as `layout` says. stale
compares a chapter's stamp with the decisions now; --since compares by register revisions instead.

migrate is a dry run by default: a report and the edit records it would write. --apply rewrites the chapter's text
(.txt; the .tagged interim words alike), the `# text` fingerprint of its .align, and writes the edit records
(make-tanakh-review's FORMAT.md section 10, who `script:migrate`, entry = the decision id: in the `chapter` layout
`.tanakh/edits/<BOOK>/<BOOK>_<CCC>/<time>-script-migrate.jsonl`, in the `book` layout inside the migration record) and
a migration record (`.tanakh/text-migrations/<time>.json`: ids, chapters, applied or proposed, the edits, the
fingerprints before and after); `--undo <record>` reverses it.
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

DECISION_STATUS = ("decided", "proposed")       # what a chapter is drafted with (open entries are questions)
NOT_DECISIONS = ("answer", "question")
LEXICAL = ("term", "name", "formula")           # apply to a chapter where their source word is in it


def layout(pname):
    """where stamps and a migration's edit records go: 'chapter' (a file per chapter, make-tanakh-review's and
    make-tanakh-grammar's layout for language repositories) or 'book' (a stamp file per book, a migration's edit
    records inside its record: few files, for a work copy). project.yaml `lifecycle: {files: book | chapter}`; by
    default 'chapter' for a project with a register, else 'book'. Both are always read."""
    from project import project
    f = ((project(pname).get("lifecycle") or {}).get("files") or "").strip()
    if f in ("book", "chapter"):
        return f
    return "chapter" if RG.has_register(RG.profile_of(pname)) else "book"


def run_file(pname, code, ch):
    return os.path.join(project_dir(pname), ".tanakh", "runs", f"{code.upper()}_{ch:03d}.json")


def book_file(pname, code):
    return os.path.join(project_dir(pname), ".tanakh", "runs", f"{code.upper()}.json")


def _read(f):
    return json.load(open(f, encoding="utf-8")) if os.path.exists(f) else None


def _write(f, d):
    os.makedirs(os.path.dirname(f), exist_ok=True)
    with open(f, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(d, ensure_ascii=False, indent=1, sort_keys=False) + "\n")


def read_stamp(pname, code, ch):
    """a chapter's stamp {drafted: {...}, checked: {...}} from either layout ({} if none); the chapter file wins"""
    d = _read(run_file(pname, code, ch))
    if d is not None:
        return d
    b = _read(book_file(pname, code)) or {}
    return (b.get("chapters") or {}).get(str(ch)) or {}


def write_stamp(pname, code, ch, d):
    if layout(pname) == "chapter":
        _write(run_file(pname, code, ch), dict({"book": code.upper(), "chapter": ch}, **d))
        return
    f = book_file(pname, code)
    b = _read(f) or {"book": code.upper(), "chapters": {}}
    b.setdefault("chapters", {})[str(ch)] = {k: v for k, v in d.items() if k not in ("book", "chapter")}
    b["chapters"] = dict(sorted(b["chapters"].items(), key=lambda x: int(x[0])))
    _write(f, b)
    old = run_file(pname, code, ch)               # moved into the book's file
    if os.path.exists(old):
        os.remove(old)


class Decisions:
    """the project's decisions as a chapter is drafted with them: {id: binding_sum} of the decided and proposed
    entries, split into those that apply where their source word is (terms, names, formulas naming a source word: by
    their lexemes) and the general ones (every other kind: rules, letters, morphs, words, spelling, the orthography,
    formulas that are phrases)"""
    def __init__(self, pname, profile=None):
        import words as W
        self.pname = pname
        A = RG.entries(pname, profile=profile)                    # profile: another folder (the store at a commit)
        E = [e for e in A if e["status"] in DECISION_STATUS and e["kind"] not in NOT_DECISIONS]
        self.status = {e["id"]: e["status"] for e in A}
        lemmas = W.source_lemmas() if any(e["kind"] in LEXICAL for e in E) else {}
        self.lexical, self.general, self.by_lex = {}, {}, collections.defaultdict(set)
        self.entry = {e["id"]: e for e in E}
        for e in E:
            lx = {x for _, x in W.entry_lexemes(RG.to_store(e, {}), lemmas)} if e["kind"] in LEXICAL else set()
            if lx:
                self.lexical[e["id"]] = (RG.binding_sum(e), lx)
                for x in lx:
                    self.by_lex[x].add(e["id"])
            else:
                self.general[e["id"]] = RG.binding_sum(e)

    def of(self, code, ch):
        """({id: sum} of the lexical decisions whose source word is in the chapter, the general digest). Without the
        chapter's source index every lexical decision counts"""
        import words as W
        try:
            _, S = W.chapter_source(code, ch)
            here = {lx for toks in S.values() for _, lx, *_ in toks if lx}
            ids = {i for x in here for i in self.by_lex.get(x, ())}
        except Exception:                          # noqa: BLE001  (no orig/ index: all of them)
            ids = set(self.lexical)
        return {i: self.lexical[i][0] for i in sorted(ids)}, general_digest(self.general)


def general_digest(table):
    import hashlib
    return hashlib.sha256(json.dumps(table, sort_keys=True).encode()).hexdigest()[:RG.SUM_LEN]


def general_file(pname):
    return os.path.join(project_dir(pname), ".tanakh", "general.jsonl")


def general_tables(pname):
    """{digest: {id: sum}} of the general decisions as stamps saw them: .tanakh/general.jsonl, one line per new state,
    each a change from the line before ({digest, set: {id: sum}, drop: [id]}; the first line sets all)"""
    out, cur = {}, {}
    f = general_file(pname)
    for line in open(f, encoding="utf-8") if os.path.exists(f) else []:
        r = json.loads(line)
        cur = {k: v for k, v in cur.items() if k not in set(r.get("drop") or [])} | (r.get("set") or {})
        out[r["digest"]] = dict(cur)
    return out


def save_general(pname, table):
    """append the general table to .tanakh/general.jsonl if it is a state not seen yet; its digest"""
    dg = general_digest(table)
    have = general_tables(pname)
    if dg in have:
        return dg
    last = {}
    f = general_file(pname)
    if os.path.exists(f):
        lines = open(f, encoding="utf-8").read().splitlines()
        if lines:
            last = have[json.loads(lines[-1])["digest"]]
    r = {"digest": dg, "set": {k: v for k, v in sorted(table.items()) if last.get(k) != v},
         "drop": sorted(set(last) - set(table))}
    os.makedirs(os.path.dirname(f), exist_ok=True)
    with open(f, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(r, ensure_ascii=False, sort_keys=False) + "\n")
    return dg


BASIS = {"drafted": "prompt", "checked": "chapter_check"}   # what a stamp written in the loop rests on


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def stamp(pname, code, ch, what, rev=None, D=None, basis=None, extra=None):
    """record what a chapter was drafted (make_prompt) or last checked (chapter_check) with: the checksums of the
    decisions that apply to it (`sums`, the general ones by `general` digest), with a register its revision, and its
    `basis`: prompt / chapter_check (written in the loop), asserted (stamp --all: today's decisions, not tested),
    git <commit> (stamp --as-of git: the store at the commit that last changed the chapter's text), verified (stamp
    --verify: `sums` and `general` only what the chapter follows, `drift` and `unverified` beside them). extra: fields
    that replace or add to the record (the verified and git forms)"""
    D = D or Decisions(pname)
    sums, dg = D.of(code, ch)
    save_general(pname, D.general)
    d = read_stamp(pname, code, ch) or {}
    d = {k: v for k, v in d.items() if k not in ("book", "chapter")}
    r = {"when": now_utc(), "basis": basis or BASIS.get(what, "asserted"), "sums": sums, "general": dg}
    if extra:
        if "general_table" in extra:
            r["general"] = save_general(pname, extra.pop("general_table"))
        r.update(extra)
    prof = RG.profile_of(pname)
    if rev or RG.has_register(prof):
        r["revision"] = rev or RG.revision(prof)
    d[what] = r
    write_stamp(pname, code, ch, d)
    return dict({"book": code.upper(), "chapter": ch}, **d)


# ------------------------------------------------------------------ evidence for a stamp: --verify, --as-of git

def verify(pname, code, ch, D, ctx=None):
    """test the decisions that apply to a chapter against its text: -> {"sums", "general_table", "drift", "unverified",
    "counts"}. Terms, names and formulas naming a source word: in each verse where the source word is (in the entry's
    scope, in its sense: the entry's BSB words in the verse), the draft follows it when one of its forms (the value,
    a preferred or admitted alternative; inflected as words.same_word allows, or a form the corpus writes for the
    word) is in the verse; else the word the .align links to the source word is drift; with no link, that verse is
    untested. A broken decision is drift when it is decided and names its source word by number (H/G), or is a name (a
    name has no other sense; its scope, if any, still holds); one found by its lemma (a homonym, another sense) or a proposal only differs
    (unverified). A decision followed somewhere and broken nowhere counts as followed, one that applies in no verse
    (another sense, out of scope) too. Phrases and names without a source word can't be tested (unverified). Spelling entries: drift where the rule still changes a word of the draft.
    Every other general decision (rules, morphs, letters, the orthography) is unverified."""
    import langtools as LT, full_align as FA, words as W
    ctx = ctx if ctx is not None else {}
    if "P" not in ctx:
        P = ctx["P"] = LT.Project(pname)
        db = W.db_file(pname)
        ctx["L"] = W.Lexicon(db, keep=W.keep_marks(P)) if os.path.exists(db) else None
        ctx["common"] = ({w: i for i, (w, _) in enumerate(ctx["L"].vocab.most_common(W.FUNCTION_TOP))} if ctx["L"] else {})
        ctx["names"] = W.names_of(P, con=ctx["L"].db if ctx["L"] else None)
    P, L, keep = ctx["P"], ctx["L"], W.keep_marks(ctx["P"])
    d = os.path.join(project_dir(pname), code)
    path, al = os.path.join(d, f"{code}{ch:03d}.txt"), os.path.join(d, f"{code}{ch:03d}.align")
    rows = FA.read_chapter(al)[1] if os.path.exists(al) else {}
    verses = dict(FA.draft_texts(path))
    try:
        lang, S = W.chapter_source(code, ch)
    except Exception:                              # noqa: BLE001  (no source index: nothing lexical can be tested)
        lang, S = None, {}
    now, _ = D.of(code, ch)
    sums, drift, unv, cnt = {}, {}, {}, collections.Counter()
    bsb_has = lambda v, ws: any(re.search(rf"\b{re.escape(w.lower())}", W.bsb_verse(P, code, ch, v).lower()) for w in ws)

    def forms(e):
        vs = W.value_forms(e.get("value") or "") + [x for a in e.get("alternatives") or [] if isinstance(a, dict)
                                                   and a.get("status") in ("preferred", "admitted") and a.get("value")
                                                   for x in W.value_forms(a["value"])]
        return [x for x in (W.value_words(v, ctx["common"]) for v in vs) if x]

    def test(i, e, verse_ids, lx, siblings=()):
        """-> (followed, [[verse, draft words]], untested) over the verses where the decision applies; a verse that
        follows another decision on the same word (another bearer of the name, another sense) is not drift"""
        vals = forms(e)
        other = [x for s_ in siblings for x in forms(s_)]
        ws = [w for w in e.get("words") or [] if re.fullmatch(r"[A-Za-z][A-Za-z' -]+", w)]
        ok, bad, untested = 0, [], 0
        if not vals or not W.in_scope(e.get("scope") or W.id_scope(i), code, ch):
            return ok, bad, untested
        for v in verse_ids:
            here = [t for t in S.get(v, []) if lx and t[1] in lx]
            if v not in verses or not here:
                continue
            if ws and not bsb_has(v, ws):                  # another sense (the entry's BSB words not in the verse)
                continue
            words_ = W.written_tokens(verses[v]); low = [t.lower() for t in words_]
            same = W.same_word if D.entry[i]["kind"] != "name" else (       # a name with an ending: Elis, Asas, Ogs
                lambda w, t, k: W.same_word(w, t, k) or (t.startswith(w) and 0 < len(t) - len(w) <= 2))
            if any(all(any(same(w, t, keep) for t in low) for w in val) for val in vals):
                ok += 1; continue
            if any(all(any(same(w, t, keep) for t in low) for w in val) for val in other):
                continue
            x = L.expected(lang, here[0][1]) if L else None
            cf = {t for f in (x[0] if x else ()) for t in W.tokens_of(f)}
            if any(t in cf and any(t[:3] == w[:3] for val in vals for w in val) for t in low):
                ok += 1; continue
            main = FA.parse(rows[v][0]) if v in rows else {}
            linked = [j for o, *_ in here for j in main.get(o, []) if j < len(words_)]
            if linked:
                bad.append([v, as_written(verses[v], [words_[j] for j in sorted(set(linked))])])
            else:
                untested += 1
        return ok, bad, untested

    def record(i, sm, e, ok, bad, untested):
        sure = bool(re.search(r"\b[HG]\d+", f"{e.get('source') or ''} {i}")) or D.entry[i]["kind"] == "name"
        if bad and D.entry[i]["status"] == "decided" and sure:
            drift[i] = {"sum": sm, "verses": bad, "expected": e.get("value")}; cnt["drift"] += 1
        elif bad and D.entry[i]["status"] == "decided":  # found by its lemma: a homonym, or another sense of the word
            unv[i] = sm; cnt["differs (source word by its lemma: sense not known)"] += 1
        elif bad:                                       # a proposal the chapter doesn't follow: not drift, not followed
            unv[i] = sm; cnt["differs from a proposal"] += 1
        elif ok or not untested:
            sums[i] = sm
            cnt["followed" if ok else "not in this chapter's sense or scope"] += 1
        else:
            unv[i] = sm; cnt["unverified (no .align link)"] += 1

    for i, sm in now.items():
        e = RG.to_store(D.entry[i], {})
        sib = [j for j in now if j != i and D.lexical[j][1] & D.lexical[i][1]]   # other decisions on the word (bearers, senses)
        record(i, sm, e, *test(i, e, sorted(S), D.lexical[i][1], [RG.to_store(D.entry[j], {}) for j in sib]))
    gen = {}
    toks = sorted({t.lower() for t_ in verses.values() for t in W.written_tokens(t_)})
    for i, sm in D.general.items():
        e = D.entry[i]
        if e["kind"] in LEXICAL:                    # a phrase, or a name without a source id: no word to find it by
            unv[i] = sm; cnt["unverified (no source word)"] += 1; continue
        if e["kind"] != "spelling":
            unv[i] = sm; cnt["unverified (general)"] += 1; continue
        se = RG.to_store(e, {}); se = dict(se, status="decided")
        R = W.Respeller(W.spelling_rules({"entries": [se]}), ctx["names"])
        hit = [t for t in toks if R(t) != t] if R else []
        if hit:
            vs = [v for v, t_ in verses.items() if any(w.lower() in hit for w in W.written_tokens(t_))]
            drift[i] = {"sum": sm, "verses": [[v, ", ".join(sorted({w for w in W.written_tokens(verses[v]) if w.lower() in hit}))]
                                              for v in vs[:20]], "expected": e.get("value")}
            cnt["drift"] += 1
        else:
            gen[i] = sm; cnt["followed"] += 1
    return {"sums": sums, "general_table": gen, "drift": drift, "unverified": unv, "counts": cnt}


def as_written(text, toks):
    """the linked draft words as the verse writes them: tokens next to each other with what stands between them (Ke'ila,
    not Ke ila), others joined by ' … '"""
    out, k = [], 0
    for t in toks:
        m = re.compile(re.escape(t)).search(text, k)
        if not m:
            return " ".join(toks)
        if out and re.fullmatch(r"\W{0,2}", text[out[-1][1]:m.start()]) and "  " not in text[out[-1][1]:m.start()]:
            out[-1] = (out[-1][0], m.end())
        else:
            out.append((m.start(), m.end()))
        k = m.end()
    return " … ".join(text[a:b] for a, b in out)


def git_basis(pname, code, ch, cache):
    """the commit that last changed a chapter's text and the project's decisions in it: -> (commit, date, modified,
    Decisions) or None where the text was never committed. The profile folder at the commit is read from git (git
    archive into a temporary folder), whichever form the store had then"""
    import subprocess, tempfile, tarfile, io
    pd = project_dir(pname)
    f = os.path.join(pd, code, f"{code}{ch:03d}.txt")
    g = lambda *a: subprocess.run(["git", "-C", pd, *a], capture_output=True, text=True)
    top = g("rev-parse", "--show-toplevel").stdout.strip()
    if not top:
        return None
    out = g("log", "-1", "--format=%H %cI", "--", f).stdout.split()
    if not out:
        return None
    commit, date = out
    modified = bool(g("status", "--porcelain", "--", f).stdout.strip())
    if (pname, commit) not in cache:
        rel = os.path.relpath(os.path.join(pd, "profile"), top)
        tmp = tempfile.mkdtemp(prefix="stamp-")
        r = subprocess.run(["git", "-C", top, "archive", "--format=tar", commit, "--", rel], capture_output=True)
        if r.returncode == 0:
            with tarfile.open(fileobj=io.BytesIO(r.stdout)) as t:
                t.extractall(tmp, filter="data")
        prof = os.path.join(tmp, rel)
        os.makedirs(prof, exist_ok=True)              # no profile at that commit: no decisions then
        cache[(pname, commit)] = Decisions(pname, profile=prof)
    return commit, date, modified, cache[(pname, commit)]


def drafted_rev(pname, code, ch):
    d = read_stamp(pname, code, ch)
    return RG.rev_n((d.get("drafted") or {}).get("revision")) or 1


def stale_ids(stamp_d, now, general_now, tables, status):
    """{id: why} of the decisions that changed for a chapter since its stamp (the checked one, else the drafted one):
    changed (another checksum), superseded / retired / removed, or new (applies now, not in the stamp); None where
    the stamp has no checksums (written before v0.10.0)"""
    s = stamp_d.get("checked") or stamp_d.get("drafted") or {}
    if "sums" not in s:
        return None
    known = s.get("general") in tables             # a general state the log doesn't have: only the lexical ones compared
    then = dict(s["sums"]) | (tables[s["general"]] if known else {})
    cur = dict(now) | (general_now if known else {})
    drift, unv = s.get("drift") or {}, s.get("unverified") or {}   # a verified stamp: broken, and not testable
    out = {}
    for i, v in then.items():
        if i not in cur:
            out[i] = status.get(i) or "removed"     # superseded, retired, open again, or gone
        elif cur[i] != v:
            out[i] = "changed"
    for i in cur:
        if i in then:
            continue
        if i in drift:
            out[i] = "drift" if drift[i].get("sum") == cur[i] else "drift, changed since"
        elif i in unv:
            if unv[i] != cur[i]:
                out[i] = "changed (unverified)"     # an unchanged untested one is silent: stale says nothing new
        else:
            out[i] = "new"
    for i in drift:
        if i not in cur:
            out[i] = status.get(i) or "removed"
    return out


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
    inline = layout(pname) == "book"              # few files: the batch's edit records inside its record
    for (code, c), rs in rows.items() if not inline else ():
        f = os.path.join(d, ".tanakh", "edits", code.upper(), f"{code.upper()}_{c:03d}", f"{stamp_s}-script-migrate.jsonl")
        os.makedirs(os.path.dirname(f), exist_ok=True)
        with open(f, "w", encoding="utf-8") as fh:
            fh.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rs)
        files.append(os.path.relpath(f, d))
    rec = {"when": stamp_s, "ids": ids, "applied": True, "undo_of": undo_of, "commit": commit,
           "chapters": sorted({f"{x['code']}{x['ch']:03d}" for x in changes}), "edits": files, "fingerprints": fps,
           "changes": [{k: x[k] for k in ("code", "ch", "v", "pos", "start", "old", "new", "entry", "cat")} for x in changes]}
    if inline:
        rec["edit_rows"] = {f"{code.upper()}_{c:03d}": rs for (code, c), rs in sorted(rows.items())}
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

def stale_by_sums(a):
    """stale from the stamps' checksums (either store form; no revisions needed): per decision the chapters it changed
    for since they were stamped. A stamp without checksums (before v0.10.0) falls back to the register's revisions"""
    prof = RG.profile_of(a.project)
    D, tables = Decisions(a.project), general_tables(a.project)
    per, why, none, old = collections.defaultdict(list), collections.defaultdict(collections.Counter), [], []
    basis, unknown = collections.Counter(), 0
    for code, c_, path in chapters(a.project, a.books):
        st = read_stamp(a.project, code, c_)
        if st and getattr(a, "stamp", None):
            st = {a.stamp: st.get(a.stamp)} if st.get(a.stamp) else {}
        s_ = (st or {}).get("checked") or (st or {}).get("drafted") or {}
        basis[s_.get("basis") or "before v0.12.0"] += bool(s_)
        unknown += len(s_.get("unverified") or {})
        now, _ = D.of(code, c_)
        ids = stale_ids(st, now, D.general, tables, D.status) if st else None
        if ids is None:
            if st and RG.has_register(prof):
                ids = {i: w for i, w in RG.changed_since(prof, drafted_rev(a.project, code, c_)).items()}
            else:
                (old if st else none).append(f"{code.upper()} {c_}"); continue
        for i, w in ids.items():
            if not a.ids or i in a.ids:
                per[i].append((code, c_)); why[i][w] += 1
    E = {e["id"]: e for e in RG.entries(a.project)}
    changes, review = plan(a.project, sorted(per), a.books) if a.verses and per else ([], [])
    where = collections.defaultdict(lambda: collections.defaultdict(set))
    for x in changes:
        for i in x["entry"].split("+"):
            where[i][(x["code"], x["ch"])].add(x["v"])
    for i in sorted(per):
        k = E.get(i, {}).get("kind", "?")
        print(f"{i} ({k}, {', '.join(f'{w} {n}' for w, n in why[i].most_common())}; mechanical: "
              f"{RG.MECHANICAL.get(k, 'no')}): {len(per[i])} chapters stamped before it")
        if a.verses and where.get(i):
            print("   verses: " + "; ".join(f"{c.upper()} {n}:{','.join(map(str, sorted(vs)))}"
                                       for (c, n), vs in sorted(where[i].items())[:30]))
    if a.verses:
        print(f"review list: {len(review)}")
    if none or old:
        print(f"{len(none) + len(old)} chapters without a stamp to compare ({', '.join((none + old)[:8])}"
              f"{' …' if len(none) + len(old) > 8 else ''}): `python3 scripts/lifecycle.py stamp {a.project} --all` "
              "records them as they are now")
    print(f"{a.project}: {len(per)} decisions changed for {len({x for v in per.values() for x in v})} chapters; "
          "stamps by basis: " + ", ".join(f"{k} {v}" for k, v in sorted(collections.Counter(
              ("git" if k.startswith("git ") else k) for k in basis.elements()).items()))
          + (f"; {unknown} decision-chapter pairs untested (verified stamps' `unverified`, unchanged ones not listed)" if unknown else "")
          + ("; `asserted` stamps were not tested: --verify for evidence" if basis.get("asserted") else ""))


def stamp_verified(a):
    """stamp --all --verify: each chapter's `checked` stamp from verify(); the drift list printed (and --report)"""
    what = a.what or "checked"
    D, ctx, tot, out = Decisions(a.project), {}, collections.Counter(), []
    rep = open(a.report, "w", encoding="utf-8") if a.report else None
    n = 0
    for code, c_, _ in chapters(a.project, a.books):
        r = verify(a.project, code, c_, D, ctx)
        tot.update(r["counts"]); n += 1
        for i, x in sorted(r["drift"].items()):
            for v, w in x["verses"]:
                out.append(f"{code.upper()} {c_}:{v}  {i}: the draft has “{w}”, the decision “{(x['expected'] or '')[:60]}”")
                if rep:
                    rep.write(json.dumps({"book": code.upper(), "chapter": c_, "id": i, "verse": v, "draft": w,
                                          "expected": x["expected"]}, ensure_ascii=False) + "\n")
        stamp(a.project, code, c_, what, D=D, basis="verified",
              extra={"sums": r["sums"], "general_table": r["general_table"],
                     "drift": {i: {"sum": x["sum"], "verses": [v for v, _ in x["verses"]]} for i, x in r["drift"].items()},
                     "unverified": r["unverified"]})
    if rep:
        rep.close()
    for l in out[:200]:
        print(l)
    if len(out) > 200:
        print(f"… {len(out) - 200} more" + (f" (all in {a.report})" if a.report else " (--report FILE for all)"))
    print(f"{a.project}: {n} chapters verified ({what}); decisions per chapter: "
          + ", ".join(f"{k} {v}" for k, v in tot.most_common()) + f"; {len(out)} drift verses"
          + (f"; the mechanical ones: `python3 scripts/lifecycle.py migrate {a.project} --ids …`" if out else ""))


def stamp_git(a):
    """stamp --all --as-of git: each chapter's `drafted` stamp with the decisions at the commit that last changed its
    text (basis `git <commit>`); chapters never committed, and stamps written in the loop (basis prompt), are left"""
    what = a.what or "drafted"
    cache, n, skip, mod = {}, 0, collections.Counter(), 0
    for code, c_, _ in chapters(a.project, a.books):
        st = read_stamp(a.project, code, c_).get(what) or {}
        if "sums" in st and st.get("basis") not in (None, "asserted"):
            skip[f"already stamped ({st.get('basis')})"] += 1; continue
        g = git_basis(a.project, code, c_, cache)
        if not g:
            skip["text not in git (stamp --all --verify instead)"] += 1; continue
        commit, date, modified, D = g
        stamp(a.project, code, c_, what, D=D, basis=f"git {commit[:12]}",
              extra={"committed": date} | ({"modified": True} if modified else {}))
        n += 1; mod += modified
    print(f"{a.project}: {n} chapters stamped ({what}) with the decisions of {len(cache)} commits"
          + (f"; {mod} have changes not committed (marked `modified`: the stamp is the committed text's)" if mod else "")
          + "".join(f"; {v} {k}" for k, v in skip.items())
          + ". A chapter committed after it was drafted is stamped with decisions it may not have had: the commit is "
            "an upper bound")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("stamp"); c.add_argument("project"); c.add_argument("rest", nargs="*", help="<code> <ch> drafted|checked")
    c.add_argument("--all", action="store_true", help="every drafted chapter without a stamp (or without checksums), as it is now")
    c.add_argument("--verify", action="store_true", help="with --all: stamp what each chapter follows, its drift and what can't be tested")
    c.add_argument("--as-of", dest="as_of", choices=("git",), help="with --all: the decisions at the commit that last changed each chapter")
    c.add_argument("--what", choices=("drafted", "checked")); c.add_argument("--books", nargs="*")
    c.add_argument("--report", help="with --verify: write the drift list here (JSON Lines: book, chapter, id, verse, draft, expected)")
    c = sub.add_parser("stale"); c.add_argument("project"); c.add_argument("--since"); c.add_argument("--ids", nargs="*")
    c.add_argument("--stamp", choices=("drafted", "checked"), help="compare with this stamp (default: checked, else drafted)")
    c.add_argument("--books", nargs="*"); c.add_argument("--verses", action="store_true"); c.add_argument("--rules")
    c = sub.add_parser("migrate"); c.add_argument("project"); c.add_argument("--ids", nargs="*", default=[])
    c.add_argument("--books", nargs="*"); c.add_argument("--apply", action="store_true"); c.add_argument("--out")
    c.add_argument("--undo"); c.add_argument("--rules", help="spelling rules from a file as well (words.py --respell's form)")
    c.add_argument("--sample", type=int, default=0)
    a = ap.parse_args()
    if a.cmd == "stamp":
        if a.all and a.verify:
            stamp_verified(a); return
        if a.all and a.as_of:
            stamp_git(a); return
        if a.all:
            what = a.what or "checked"
            D, n = Decisions(a.project), 0
            for code, c_, _ in chapters(a.project, a.books):
                st = read_stamp(a.project, code, c_).get(what) or {}
                if "sums" not in st:
                    stamp(a.project, code, c_, what, D=D, basis="asserted"); n += 1
            print(f"{a.project}: {n} chapters stamped ({what}), as they are now; layout: {layout(a.project)}")
            if n:
                print("warning: these stamps assert that each chapter follows today's decisions, untested (basis "
                      "`asserted`). For stamps with evidence: --as-of git (the store when the chapter was committed) "
                      "or --verify (each decision tested on the chapter)")
            return
        if len(a.rest) != 3 or a.rest[2] not in ("drafted", "checked"):
            ap.error("stamp <project> <code> <ch> drafted|checked, or stamp <project> --all [--what checked]")
        print(json.dumps(stamp(a.project, a.rest[0], int(a.rest[1]), a.rest[2]), ensure_ascii=False))
    elif a.cmd == "stale" and not a.since:
        stale_by_sums(a)
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
        if a.apply and not do:
            print("nothing to apply")
        elif a.apply:
            s = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
            f, rec = apply_changes(a.project, do, a.ids, s)
            print(f"applied: {len(do)} changes; record {os.path.relpath(f, ROOT)}")


if __name__ == "__main__":
    main()
