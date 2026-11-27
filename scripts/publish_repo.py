#!/usr/bin/env python3
"""Publish a project's drafts into a clone of its global-tanakh language repository (make-tanakh-review's
template/FORMAT.md): gate, convert, screen, compare with the clone, plan; --apply writes and commits in the clone.
Nothing is pushed: the publisher pushes (docs/publishing.md).

    python3 scripts/publish_repo.py <project> --repo <clone> [--books gen,exo] [--report F] [--apply]

1. **Gate** (refusals end the run, or leave a chapter out):
   - the project's folder: `export/CC-NC/` and `local_output/` never publish;
   - a `publish:` block in `project.yaml` and `publish.yaml` at the work copy's root (`publish.yaml.example`);
   - `scripts/check_project.py` passes on the project;
   - per chapter: a non-free (or `quarantine_attributable`) style edition with this book's text in view and no
     quarantine recorded (the book in `quarantine:`, or, for a quarantine that has ended, in
     `publish.drafted_in_quarantine`) leaves the chapter out;
   - the clone is the configured repository (`<org>/<repo>`), its `language.json` names the same code and variety.
2. **Convert** (FORMAT.md 1-4, 8, 13): `<BOOK>_<CCC>.md` (front matter with the status in the language, the labels
   from `publish.status_labels` or the project's `header.ot` lines; `partial: "…"` for a chapter with only some of its
   verses), `.align` (rows unchanged), `.units` (cut from the .align's links on the clone's pinned
   hebrew-clause-layout, downloaded once into `download/hebrew-clause-layout/<revision>/`, checked by the dataset's
   SHA256SUMS), `.notes` (inline notes `{T|E|H|N: …}` and the reader footnotes `<code>NNN_footnotes.txt`, kind
   `publish.footnote_kind`, E by default), `.tanakh/runs/<BOOK>_<CCC>.json`, `.tanakh/glosses.json`,
   `.tanakh/publisher.json` (the list form, this publisher with its `analysis` dataset).
3. **Screen** (FORMAT.md 13): every unit against the same verse of each non-free and attributable style edition (run
   10; in a unit of more than 10 words, 0.8 of its words inside runs of 5). A failing unit holds its chapter back; the
   report gives references and figures only, never text. The mark goes into `.tanakh/runs/`: `passed`, or
   `not needed` when the project has no such edition.
4. **Compare** with the clone, chapter by chapter: `new`; `same` (nothing written, the run file kept); `changed`
   (text or sidecars differ: a re-draft, never written over the repository's text).
5. **--apply** (a clean clone on `main`): the new chapters and the derived files in one commit on `main`, the same
   commit on `approved`; the changed chapters on a branch `draft/<date>` from `main`, for a pull request. Without
   --apply nothing is written. Push yourself: the commands are printed.

Only Tanakh chapters for now (the NT needs the clone's greek-nt-clause-layout: listed as left out)."""
import argparse, collections, datetime, hashlib, json, os, re, subprocess, sys, unicodedata, urllib.request

CODE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.abspath(os.environ.get("MAKE_TANAKH_ROOT") or CODE)
sys.path.insert(0, os.path.join(CODE, "scripts"))
import full_align as FA  # noqa: E402
import bridge_align as BA  # noqa: E402
from books import BOOKS, BY_CODE  # noqa: E402
from project import project, project_dir, project_rel, edition, must_quarantine, LICENCE_CLASS, load_yaml  # noqa: E402

STATUS_KEYS = ["maturity", "translation", "exegesis", "literary", "date"]
THRESHOLD = {"run": 10, "share": 0.8, "min_run": 5, "scope": "same verse"}
HCL = "https://huggingface.co/datasets/{dataset}/resolve/{rev}/{path}"
NOTE_KINDS = "TEHN"


# ------------------------------------------------------------------ configuration

def config(pname, cfg_file=None):
    """publish.yaml (the work copy's: org, hf_dataset, publisher) and the project's publish: block -> dict, or a
    SystemExit naming what is missing"""
    f = cfg_file or os.path.join(ROOT, "publish.yaml")
    if not os.path.exists(f):
        raise SystemExit(f"no publish.yaml at {ROOT} (copy publish.yaml.example and fill it in)")
    g = load_yaml(f) or {}
    p = project(pname)
    b = p.get("publish")
    if not isinstance(b, dict) or not b.get("repo"):
        raise SystemExit(f"{pname}: no publish: block with a repo in project.yaml (docs/publishing.md)")
    for k in ("org", "publisher"):
        if not g.get(k):
            raise SystemExit(f"publish.yaml: {k} missing")
    if not (g["publisher"] or {}).get("login"):
        raise SystemExit("publish.yaml: publisher.login missing")
    code = b.get("code") or str(p.get("language", "")).split("-")[0].lower()
    if not re.fullmatch(r"[a-z]{3}", code or ""):
        raise SystemExit(f"{pname}: publish.code, the ISO 639-3 code, missing")
    want = f"{code}-{b['variety']}" if b.get("variety") else code
    if b["repo"] != want:
        raise SystemExit(f"{pname}: publish.repo is {b['repo']}, the code and variety give {want} (<code> or <code>-<variety>)")
    return dict(g, project=p, block=b, code=code)


def status_labels(cfg):
    """the five status labels in the language: publish.status_labels, else the labels of the project's header.ot"""
    b, p = cfg["block"], cfg["project"]
    if b.get("status_labels"):
        labs = list(b["status_labels"])
    else:
        labs = [m[1].strip() for l in ((p.get("header") or {}).get("ot") or [])
                for m in [re.match(r"!!<([^:>]+):", l)] if m]
    if len(labs) != 5:
        raise SystemExit("the five status labels (maturity, translation, exegesis, literary, date): set publish.status_labels")
    return labs


# ------------------------------------------------------------------ gate

def gate(pname, cfg, skip_check=False):
    """project-level refusals: [reason]"""
    out = []
    rel = project_rel(pname).replace(os.sep, "/")
    if rel.startswith("export/CC-NC/") or "/CC-NC/" in f"/{rel}/":
        out.append("export/CC-NC/ never publishes (it keeps the edition's licence)")
    if not rel.startswith("export/"):
        out.append(f"{rel}: only projects in export/ publish (local_output/ never)")
    if not skip_check:
        r = subprocess.run([sys.executable, os.path.join(CODE, "scripts", "check_project.py"), pname], cwd=ROOT,
                           capture_output=True, text=True)
        if r.returncode:
            bad = [l for l in (r.stdout + r.stderr).splitlines() if l.strip() and not l.startswith(("ok", "=="))]
            out.append("check_project.py fails: " + "; ".join(bad[:5]))
    return out


def quarantine_refusal(cfg, code, ch):
    """a reason when a chapter was drafted with a non-free edition's text of its book in view, else None"""
    p, b = cfg["project"], cfg["block"]
    if code in (p.get("quarantine") or []) or code in (b.get("drafted_in_quarantine") or []):
        return None
    seen = [e for e, cls, files in must_quarantine(p, code, ch) if files]
    if seen:
        return (f"{', '.join(seen)} has this book's text in view and no quarantine is recorded (quarantine:, or "
                "publish.drafted_in_quarantine for one that has ended)")
    return None


# ------------------------------------------------------------------ the clone

def git(repo, *a, check=True):
    r = subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True)
    if check and r.returncode:
        raise SystemExit(f"git {' '.join(a)}: {r.stderr.strip()}")
    return r.stdout.strip()


def read_json(path, default=None):
    try:
        return json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return default


def clone_checks(repo, cfg):
    """-> (refusals, notes, layout revision)"""
    bad, notes = [], []
    if not os.path.isdir(os.path.join(repo, ".git")):
        return [f"{repo} is not a git clone"], notes, None
    url = git(repo, "remote", "get-url", "origin", check=False)
    want = f"{cfg['org']}/{cfg['block']['repo']}"
    if not re.search(rf"[/:]{re.escape(want)}(\.git)?/?$", url):
        bad.append(f"the clone's origin is {url or '(none)'}, not {want}")
    lay = read_json(os.path.join(repo, ".tanakh", "layout.json"), {})
    rev = (lay.get("hebrew-clause-layout") or {}).get("revision")
    if not rev:
        bad.append(".tanakh/layout.json names no hebrew-clause-layout revision")
    lang = read_json(os.path.join(repo, ".tanakh", "language.json"))
    if not lang:
        bad.append(".tanakh/language.json missing")
    else:
        if lang.get("code") != cfg["code"]:
            bad.append(f"language.json says code {lang.get('code')}, the project {cfg['code']}")
        if (lang.get("variety") or None) != (cfg["block"].get("variety") or None):
            notes.append(f"language.json: variety {lang.get('variety')!r} -> {cfg['block'].get('variety')!r}")
    return bad, notes, rev


def language_json(repo, cfg):
    lang = read_json(os.path.join(repo, ".tanakh", "language.json"), {}) or {}
    v = cfg["block"].get("variety")
    out = {"code": lang.get("code", cfg["code"])}
    if v:
        out["variety"] = v
    out.update({k: x for k, x in lang.items() if k not in ("code", "variety")})
    return out


def publisher_json(repo, cfg):
    """the clone's publisher list with this publisher in it (the first form, one object, read as a list of one)"""
    j = read_json(os.path.join(repo, ".tanakh", "publisher.json"), {}) or {}
    pubs = j["publishers"] if isinstance(j.get("publishers"), list) else ([j] if j.get("login") else [])
    me = {k: cfg["publisher"][k] for k in ("login", "name", "url") if cfg["publisher"].get(k)}
    if cfg.get("hf_dataset"):
        me["analysis"] = f"hf://datasets/{cfg['hf_dataset']}/{cfg['block']['repo']}"
    keep = [{k: x for k, x in q.items() if k in ("login", "name", "url", "analysis")} for q in pubs
            if q.get("login") != me["login"]]
    old = next((q for q in pubs if q.get("login") == me["login"]), None)
    if old:                                   # this publisher's place in the list is kept
        i = pubs.index(old)
        keep.insert(i, me)
    else:
        keep.append(me)
    return {"publishers": keep}


# ------------------------------------------------------------------ the clause layout

_layout = {}


def layout_file(rev, book, dataset="bcv-commons/hebrew-clause-layout"):
    d = os.path.join(ROOT, "download", "hebrew-clause-layout", rev)
    f = os.path.join(d, f"clauses-{book}.parquet")
    if os.path.exists(f):
        return f
    os.makedirs(d, exist_ok=True)
    sums_f = os.path.join(d, "SHA256SUMS")
    if not os.path.exists(sums_f):
        urllib.request.urlretrieve(HCL.format(dataset=dataset, rev=rev, path="SHA256SUMS"), sums_f)
    sums = {x[1].strip(): x[0] for x in (l.split(None, 1) for l in open(sums_f, encoding="utf-8").read().splitlines()) if len(x) == 2}
    want = sums.get(f"data/clauses-{book}.parquet")
    data = urllib.request.urlopen(urllib.request.Request(HCL.format(dataset=dataset, rev=rev, path=f"data/clauses-{book}.parquet"),
                                                         headers={"User-Agent": "make-tanakh"})).read()
    if not want or hashlib.sha256(data).hexdigest() != want:
        raise SystemExit(f"hebrew-clause-layout@{rev[:12]} clauses-{book}.parquet: SHA-256 does not match SHA256SUMS")
    open(f, "wb").write(data)
    return f


def layout(book, rev):
    """{(c, v): [(unit key, set of word ids)]} in the layout's order; keys `first-last`, `/n` for later segments"""
    if (book, rev) in _layout:
        return _layout[(book, rev)]
    import pyarrow.parquet as pq
    rows = pq.read_table(layout_file(rev, book), columns=["chapter", "verse", "seg", "clause_key", "last", "words"]).to_pylist()
    last = collections.defaultdict(str)
    for r in rows:
        last[r["clause_key"]] = max(last[r["clause_key"]], r["last"])
    out, seen = collections.defaultdict(list), collections.Counter()
    for r in sorted(rows, key=lambda r: (r["chapter"], r["verse"], r["seg"])):
        k = r["clause_key"]; seen[k] += 1
        out[(r["chapter"], r["verse"])].append((f"{k}-{last[k]}" + (f"/{seen[k]}" if seen[k] > 1 else ""), set(r["words"] or [])))
    _layout[(book, rev)] = out
    return out


def cut(votes, n):
    """votes: per token the unit it is linked to, or None -> the units' start positions (n contiguous groups in order,
    possibly empty) with the fewest tokens outside their unit"""
    m = len(votes); INF = 10 ** 9
    pre = [[0] * (m + 1) for _ in range(n)]
    for i in range(n):
        for j, v in enumerate(votes):
            pre[i][j + 1] = pre[i][j] + (v is not None and v != i)
    cost = [[INF] * (m + 1) for _ in range(n + 1)]; back = [[0] * (m + 1) for _ in range(n + 1)]
    cost[0][0] = 0
    for i in range(1, n + 1):
        for j in range(m + 1):
            for k in range(j + 1):
                c = cost[i - 1][k] + pre[i - 1][j] - pre[i - 1][k]
                if c < cost[i][j]:
                    cost[i][j], back[i][j] = c, k
    starts, j = [], m
    for i in range(n, 0, -1):
        k = back[i][j]; starts.append(k); j = k
    return starts[::-1]


def units_line(clauses, ntok, links):
    """clauses [(key, words)], links {word id: [token positions]} -> 'key:a-b key:= …'"""
    if not clauses:
        return ""
    votes, w2c = [None] * ntok, {}
    for i, (_, ws) in enumerate(clauses):
        for w in ws:
            w2c.setdefault(w, i)
    for w, ps in links.items():
        ci = w2c.get(w)
        for q in ps if ci is not None else ():
            if 0 <= q < ntok:
                votes[q] = ci
    starts, parts = cut(votes, len(clauses)), []
    for i, (key, _) in enumerate(clauses):
        s = starts[i]; e = starts[i + 1] if i + 1 < len(clauses) else ntok
        parts.append(f"{key}:=" if s == e else f"{key}:{s}-{e - 1}" if e - 1 > s else f"{key}:{s}")
    return " ".join(parts)


# ------------------------------------------------------------------ conversion

def clean(text):
    """translatable text only: no inline notes, no poetry marks (//n), single spaces"""
    text = FA.NOTE.sub(" ", text)
    text = re.sub(r"(?<!\S)//\d+(?!\S)", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def inline_notes(raw):
    """[(kind, anchor, text)] of a verse's inline notes {K: …}: the anchor is the number of tokens before the note"""
    raw = FA.MARK.sub("", raw.strip())
    out = []
    for m in FA.NOTE.finditer(raw):
        k = m[0][1]
        body = re.sub(r"\s+", " ", m[0][3:-1]).strip()
        out.append((k if k in NOTE_KINDS else "N", len(FA.tokenize(clean(raw[:m.start()]))), body))
    return out


def footnotes(path):
    """{verse: [text]} of a reader footnote file (`vN text` lines after the head)"""
    out = collections.defaultdict(list)
    if os.path.exists(path):
        for l in open(path, encoding="utf-8").read().splitlines():
            m = re.match(r"v(\d+)\s+(.*\S)", l)
            if m:
                out[int(m[1])].append(re.sub(r"\s+", " ", m[2]))
    return out


def anchor_of(note, toks):
    """a footnote `Eva: …` follows the word it names (its first place in the verse), else the verse's end"""
    m = re.match(r"([^:]{1,60}):\s", note)
    if m:
        want = [t.lower() for t in FA.tokenize(m[1])]
        low = [t.lower() for t in toks]
        for i in range(len(low) - len(want) + 1):
            if want and low[i:i + len(want)] == want:
                return i + len(want)
    return len(toks)


def ranges(vs):
    """[1, 2, 3, 26] -> '1-3, 26'"""
    out, vs = [], sorted(vs)
    i = 0
    while i < len(vs):
        j = i
        while j + 1 < len(vs) and vs[j + 1] == vs[j] + 1:
            j += 1
        out.append(f"{vs[i]}-{vs[j]}" if j > i else str(vs[i])); i = j + 1
    return ", ".join(out)


def iso(d):
    m = re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", d or "")
    return f"{m[3]}-{int(m[2]):02d}-{int(m[1]):02d}" if m else (d or "")


def front_matter(book, ch, status, labels, partial=None):
    y = [f"book: {book}", f"chapter: {ch}"] + ([f"partial: {json.dumps(partial)}"] if partial else []) + ["status:"]
    y += [f"  {k}: {json.dumps(status.get(k, ''), ensure_ascii=False)}" for k in STATUS_KEYS]
    y.append("status_labels: " + json.dumps(labels, ensure_ascii=False))
    return "---\n" + "\n".join(y) + "\n---\n"


def repo_status(md_text):
    """the status block of a chapter already in the repository (people's, after publishing): {key: value} or None"""
    m = re.match(r"---\n(.*?)\n---\n", md_text or "", re.S)
    if not m:
        return None
    out = {}
    for k in STATUS_KEYS:
        x = re.search(rf"^  {k}: (.*)$", m[1], re.M)
        if x:
            try:
                out[k] = json.loads(x[1])
            except ValueError:
                out[k] = x[1]
    return out or None


def convert(pname, cfg, code, ch, rev, labels, forms, existing_md=None):
    """one chapter -> ({relpath: text}, info) ; info: verses, partial, problems"""
    d = os.path.join(project_dir(pname), code)
    path = os.path.join(d, f"{code}{ch:03d}.txt")
    BOOK = code.upper()
    head, title, verses = BA.draft_verses(path)
    lab = {}
    for l in head:
        for m in re.finditer(r"!!<([^:>]+):\s*(.*?)>!!", l):
            lab[m[1].strip()] = m[2].strip()
    status = {k: lab.get(labels[i], "") for i, k in enumerate(STATUS_KEYS)}
    if existing_md is not None:                    # people's status on a chapter already published stays
        status = repo_status(existing_md) or status
    title = re.sub(r"^===\s*|\s*===\s*$", "", title or "").strip()
    problems, by_v, heads, notes, raw_v = [], collections.OrderedDict(), {}, collections.defaultdict(list), {}
    for v, raw, pend in verses:
        if v in by_v:
            problems.append(f"{BOOK} {ch}:{v}: verse twice"); continue
        raw_v[v] = FA.verse_text(raw)               # the .align's text (no marker, no notes)
        by_v[v] = clean(raw_v[v])                   # the .md's (no poetry marks either)
        if FA.tokenize(by_v[v]) != FA.tokenize(raw_v[v]):
            problems.append(f"{BOOK} {ch}:{v}: cleaning the text changed its tokens")
        heads[v] = [clean(re.sub(r"^==\s*|\s*==\s*$", "", h)) for h in pend if h]
        notes[v] += inline_notes(raw)
    for v, ts in footnotes(os.path.join(d, f"{code}{ch:03d}_footnotes.txt")).items():
        if v in by_v:
            toks = FA.tokenize(by_v[v])
            notes[v] += [(cfg["block"].get("footnote_kind", "E"), anchor_of(t, toks), t) for t in ts]
        else:
            problems.append(f"{BOOK} {ch}:{v}: a footnote for a verse not in the draft")
    if not title:
        problems.append(f"{BOOK} {ch}: no title line")
    h = FA.text_hash(ch, sorted(by_v.items()))
    apath = path[:-4] + ".align"
    ah, rows = FA.read_chapter(apath) if os.path.exists(apath) else (None, {})
    if ah is None:
        problems.append(f"{BOOK} {ch}: no .align")
    elif ah != FA.text_hash(ch, sorted(raw_v.items())) and ah != h:
        problems.append(f"{BOOK} {ch}: the .align is stale (its text hash differs from the draft)")
    all_v = sorted({int(r.split(":")[1]) for r in FA.index(BOOK, "keys") if r.startswith(f"{BOOK} {ch}:")})
    partial = ranges(sorted(by_v)) if all_v and sorted(by_v) != all_v else None
    md = [front_matter(BOOK, ch, status, labels, partial), f"# {title}\n", "\n"]
    for v in sorted(by_v):
        md += [f"## {x}\n" for x in heads.get(v, [])] + [f"{ch}:{v}\t{by_v[v]}\n"]
    L = layout(BOOK, rev)
    arows, urows, nrows = [], [], []
    for v in sorted(by_v):
        toks = FA.tokenize(by_v[v]); n = len(toks); ref = f"{BOOK} {ch}:{v}"
        keys, fnk = FA.index(BOOK, "keys").get(ref, []), FA.index(BOOK, "fn_keys").get(ref, [])
        lx, fx = FA.index(BOOK, "lexemes").get(ref, []), FA.index(BOOK, "fn").get(ref, [])
        links = collections.defaultdict(list)
        if v in rows:
            mn, fn, prof = rows[v]
            for field, kk, ll in ((mn, keys, lx), (fn, fnk, fx)):
                for o, ps in FA.parse(field).items():
                    if any(q >= n for q in ps) or o >= len(kk):
                        problems.append(f"{ref}: link {o}:{ps} outside the verse ({n} tokens) or the index"); continue
                    for w in (kk[o].split("+") if kk[o] else []):
                        links[w] += ps
                    if ps and o < len(ll):
                        forms["hbo:" + ll[o]][" ".join(toks[q] for q in sorted(set(ps))).lower()] += 1
            arows.append(f"{v}\t{mn}\t{fn}\t{prof or 'b'}\n")
        urows.append(f"{ch}:{v}\t{units_line(L.get((ch, v), []), n, links)}\n")
        nrows += [f"{ch}:{v}\t{k}\t{min(a, n)}\t{t}\n" for k, a, t in notes.get(v, [])]
    stem = f"{BOOK}/{BOOK}_{ch:03d}"
    files = {stem + ".md": "".join(md),
             stem + ".align": f"{FA.HEAD}\n# text {h}\n" + "".join(arows),
             stem + ".units": f"# units: aligned; layout bcv-commons/hebrew-clause-layout@{rev}; token ranges of the standard tokeniser\n# text {h}\n" + "".join(urows),
             stem + ".notes": f"# notes: verse, kind, anchor token, text\n# text {h}\n" + "".join(nrows)}
    return files, {"verses": by_v, "partial": partial, "problems": problems, "status": status, "units": urows}


def run_file(cfg, BOOK, ch, status, screen, code_rev, register):
    built = iso(status.get("date", ""))
    return {"book": BOOK, "chapter": ch, "main": "main", "drafts": {"main": {
        "run": f"main@{built}", "label": "main", "model": cfg["block"].get("model", "claude (model not recorded)"),
        "code": code_rev, "register": register, "built": built, "kind of draft": "main", "screen": screen,
        "publisher": cfg["publisher"]["login"]}}}


# ------------------------------------------------------------------ the verbatim screen (FORMAT.md 13)

def norm(text):
    """exact words: lower-cased, NFC, split at spaces and hyphens, punctuation stripped, tone and length marks kept"""
    out = []
    for w in re.split(r"[\s\-‐‑‒–—]+", unicodedata.normalize("NFC", text.lower())):
        w = "".join(c for c in w if unicodedata.category(c)[0] in "LMN")
        if w:
            out.append(w)
    return out


def common_runs(d, g):
    """(longest common run of words, [(start, end) in d of every common run])"""
    best, runs = 0, []
    prev = [0] * (len(g) + 1)
    for i in range(1, len(d) + 1):
        cur = [0] * (len(g) + 1)
        for j in range(1, len(g) + 1):
            if d[i - 1] == g[j - 1]:
                cur[j] = prev[j - 1] + 1
                best = max(best, cur[j])
                runs.append((i - cur[j], i))
        prev = cur
    return best, runs


def covered(d, runs, min_run):
    mark = [False] * len(d)
    for a, b in runs:
        if b - a >= min_run:
            for i in range(a, b):
                mark[i] = True
    return sum(mark) / max(len(d), 1)


def fails(unit_text, team_text):
    d, g = norm(unit_text), norm(team_text)
    if not d or not g:
        return None
    L, runs = common_runs(d, g)
    sh = covered(d, runs, THRESHOLD["min_run"])
    if L >= THRESHOLD["run"] or (len(d) > THRESHOLD["run"] and sh >= THRESHOLD["share"]):
        return {"run": L, "share": round(sh, 3)}
    return None


def screen_editions(cfg):
    """the style editions the screen compares with: non-free, CC-ND/NC and attributable ones -> [(id, {(BOOK, c, v): text})]"""
    import glob
    import langtools as LT
    import vrs
    out = []
    for e in cfg["project"].get("style_from") or []:
        ed = edition(e)
        if LICENCE_CLASS.get(ed["licence_folder"], "non-free") == "public-domain":
            continue
        base = os.path.join(ROOT, ed["dir"])
        texts = {}
        for f in sorted(glob.glob(os.path.join(base, "text", "**", "*.txt"), recursive=True)
                        + glob.glob(os.path.join(base, "quarantined", "**", "*.txt"), recursive=True)):
            b = os.path.basename(f)[:3].lower()
            if b not in BY_CODE:
                continue
            try:
                vs = LT.verses_of(f)
            except Exception:                         # noqa: BLE001  (a file in another shape: not a verse file)
                continue
            for (c, v), t in vs.items():
                for key in {(b.upper(), c, v), (b.upper(), *vrs_heb(vrs, b, c, v))}:
                    texts[key] = (texts[key] + " " + t) if key in texts and t not in texts[key] else t
        out.append((e, texts))
    return out


def vrs_heb(vrs, code, c, v):
    try:
        return vrs.to_heb(code, c, v) if BY_CODE[code][2] == "ot" else (c, v)
    except Exception:                                 # noqa: BLE001  (no verse map here: the same number)
        return c, v


def screen_chapter(eds, BOOK, ch, verses, urows):
    """-> (failures [{ref, edition, range, run, share}], comparisons)"""
    fail, n = [], 0
    units = {}
    for l in urows:
        ref, _, items = l.rstrip("\n").partition("\t")
        units[int(ref.split(":")[1])] = [it.rpartition(":")[2] for it in items.split()]
    for v, text in verses.items():
        toks = FA.tokenize(text)
        rngs = [r for r in units.get(v, []) if r != "="] or [f"0-{len(toks) - 1}"] if toks else []
        for e, texts in eds:
            team = texts.get((BOOK, ch, v))
            if not team:
                continue
            for r in rngs:
                n += 1
                f = fails(" ".join(toks[i] for i in FA.ids_of(r) if i < len(toks)), team)
                if f:
                    fail.append(dict(ref=f"{BOOK} {ch}:{v}", edition=e, range=r, **f))
    return fail, n


# ------------------------------------------------------------------ the run

def chapters_of(pname, books):
    d = project_dir(pname)
    for b in BOOKS:
        code = b[0]
        if books and code not in books:
            continue
        if not os.path.isdir(os.path.join(d, code)):
            continue
        for f in sorted(os.listdir(os.path.join(d, code))):
            m = re.fullmatch(rf"{code}(\d{{3}})\.txt", f)
            if m:
                yield code, int(m[1])


def register_sum(pname):
    pd = os.path.join(project_dir(pname), "profile")
    h = hashlib.sha256()
    for dp, _, fs in sorted(os.walk(pd)):
        for f in sorted(fs):
            if f.endswith((".json", ".yaml")):
                h.update(os.path.relpath(os.path.join(dp, f), pd).encode()); h.update(open(os.path.join(dp, f), "rb").read())
    return h.hexdigest()[:12]


def plan(pname, repo, books=None, skip_check=False, cfg_file=None):
    cfg = config(pname, cfg_file)
    labels = status_labels(cfg)
    refuse = gate(pname, cfg, skip_check)
    bad, notes, rev = clone_checks(repo, cfg)
    refuse += bad
    res = {"project": pname, "repo": f"{cfg['org']}/{cfg['block']['repo']}", "refused": refuse, "notes": notes,
           "new": [], "same": [], "changed": [], "left out": [], "held back by the screen": [], "problems": []}
    if refuse:
        return res, cfg, {}
    eds = screen_editions(cfg)
    today = datetime.date.today().isoformat()
    screen = (dict(verbatim="passed", threshold=THRESHOLD, against="the team's text", checked=today) if eds
              else dict(verbatim="not needed", checked=today))
    code_rev = git(ROOT, "rev-parse", "--short", "HEAD", check=False) or "unknown"
    register = register_sum(pname)
    forms = collections.defaultdict(collections.Counter)
    out, comparisons, in_repo_elsewhere = {}, 0, [0]
    for code, ch in chapters_of(pname, None):
        BOOK, ref = code.upper(), f"{code.upper()} {ch}"
        if BY_CODE[code][2] != "ot":
            if not books or code in books:
                res["left out"].append(f"{ref}: the NT (not yet: greek-nt-clause-layout)")
            continue
        if books and code not in books:            # outside --books: only counted for the glosses, if in the repository
            stem = os.path.join(repo, BOOK, f"{BOOK}_{ch:03d}")
            if os.path.exists(stem + ".md"):
                f0 = collections.defaultdict(collections.Counter)
                try:
                    convert(pname, cfg, code, ch, rev, labels, f0, open(stem + ".md", encoding="utf-8").read())
                except Exception:                  # noqa: BLE001  (a chapter that doesn't convert counts nothing)
                    continue
                for k, c in f0.items():
                    forms[k].update(c)
                in_repo_elsewhere[0] += 1
            continue
        q = quarantine_refusal(cfg, code, ch)
        if q:
            res["left out"].append(f"{ref}: {q}"); continue
        stem = os.path.join(repo, BOOK, f"{BOOK}_{ch:03d}")
        old = {x: open(stem + x, encoding="utf-8").read() for x in (".md", ".align", ".units", ".notes") if os.path.exists(stem + x)}
        f0 = collections.defaultdict(collections.Counter)
        files, info = convert(pname, cfg, code, ch, rev, labels, f0, old.get(".md"))
        if info["problems"]:
            res["problems"] += info["problems"]
            if any("no .align" in x or "stale" in x or "outside" in x for x in info["problems"]):
                res["left out"].append(f"{ref}: {info['problems'][0]}"); continue
        fail, n = screen_chapter(eds, BOOK, ch, info["verses"], info["units"])
        comparisons += n
        if fail:
            res["held back by the screen"].append({"chapter": ref, "units": fail}); continue
        for k, c in f0.items():
            forms[k].update(c)
        if not old:
            files[f".tanakh/runs/{BOOK}_{ch:03d}.json"] = json.dumps(
                run_file(cfg, BOOK, ch, info["status"], screen, code_rev, register), indent=1, ensure_ascii=False) + "\n"
            res["new"].append(ref); out[ref] = ("new", files)
        elif all(old.get(x[len(f"{BOOK}/{BOOK}_{ch:03d}"):]) == t for x, t in files.items()):
            res["same"].append(ref)
        else:
            what = [x.rpartition(".")[2] for x, t in files.items() if old.get(x[len(f"{BOOK}/{BOOK}_{ch:03d}"):]) != t]
            text_changed = ".md" in [f".{w}" for w in what] and verse_lines(old.get(".md")) != verse_lines(files[f"{BOOK}/{BOOK}_{ch:03d}.md"])
            if text_changed or not os.path.exists(os.path.join(repo, ".tanakh", "runs", f"{BOOK}_{ch:03d}.json")):
                files[f".tanakh/runs/{BOOK}_{ch:03d}.json"] = json.dumps(   # a re-draft: a new run; sidecars only: the run stays
                    run_file(cfg, BOOK, ch, info["status"], screen, code_rev, register), indent=1, ensure_ascii=False) + "\n"
            res["changed"].append({"chapter": ref, "files": what, "text": text_changed}); out[ref] = ("changed", files)
    res["screen"] = {"editions": [e for e, _ in eds], "comparisons": comparisons, "mark": screen["verbatim"]}
    published = len(res["new"]) + len(res["same"]) + len(res["changed"]) + in_repo_elsewhere[0]
    derived = {}
    if published:
        src = cfg["publisher"].get("url", "")
        g = {"format": "make-tanakh-glosses/1", "language": cfg["code"],
             "source": {"repo": re.sub(r"^https?://[^/]+/", "", src).rstrip("/") or cfg["publisher"]["login"],
                        "commit": code_rev, "editions": [os.path.basename(pname)], "chapters": published},
             "licence": "CC0-1.0 (counts from our drafts); lexemes: MACULA Hebrew (WLC) via lexeme-spine-macula, CC BY 4.0",
             "lexemes": {k: [[f, n] for f, n in c.most_common(8)] for k, c in sorted(forms.items())}}
        derived[".tanakh/glosses.json"] = json.dumps(g, ensure_ascii=False, indent=0) + "\n"
        derived[".tanakh/publisher.json"] = json.dumps(publisher_json(repo, cfg), ensure_ascii=False, indent=1) + "\n"
        derived[".tanakh/language.json"] = json.dumps(language_json(repo, cfg), ensure_ascii=False, indent=2) + "\n"
        for k in list(derived):
            if open(os.path.join(repo, k), encoding="utf-8").read() == derived[k] if os.path.exists(os.path.join(repo, k)) else False:
                del derived[k]
        res["derived"] = sorted(derived)
    return res, cfg, {"chapters": out, "derived": derived}


def verse_lines(md):
    return [l for l in (md or "").splitlines() if re.match(r"\d+:\d+\t", l)]


def write(repo, files):
    for rel, text in files.items():
        f = os.path.join(repo, rel)
        os.makedirs(os.path.dirname(f), exist_ok=True)
        open(f, "w", encoding="utf-8").write(text)


def apply(repo, res, cfg, todo):
    if git(repo, "status", "--porcelain"):
        raise SystemExit(f"{repo}: the clone has uncommitted changes; nothing written")
    if git(repo, "rev-parse", "--abbrev-ref", "HEAD") != "main":
        raise SystemExit(f"{repo}: check out main first")
    who = cfg["publisher"].get("name") or cfg["publisher"]["login"]
    new = {k: v for ref, (kind, fs) in todo["chapters"].items() if kind == "new" for k, v in fs.items()}
    msgs = []
    if new or todo["derived"]:
        write(repo, dict(new, **todo["derived"]))
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", f"Publish: {len(res['new'])} new chapter(s) from {who}" if new else f"Publish: derived files from {who}")
        head = git(repo, "rev-parse", "HEAD")
        if git(repo, "rev-parse", "--verify", "-q", "approved", check=False):
            git(repo, "checkout", "-q", "approved")
            r = subprocess.run(["git", "-C", repo, "cherry-pick", head], capture_output=True, text=True)
            if r.returncode:
                git(repo, "cherry-pick", "--abort", check=False)
                msgs.append("approved: the commit does not apply cleanly; bring it over by hand")
            git(repo, "checkout", "-q", "main")
        msgs.append(f"main: {head[:12]}")
    changed = {k: v for ref, (kind, fs) in todo["chapters"].items() if kind == "changed" for k, v in fs.items()}
    if changed:
        br = f"draft/{datetime.date.today().isoformat()}"
        git(repo, "checkout", "-q", "-B", br, "main")
        write(repo, changed)
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", f"Re-draft: {len(res['changed'])} chapter(s) from {who}")
        git(repo, "checkout", "-q", "main")
        msgs.append(f"{br}: {len(res['changed'])} chapter(s), for a pull request")
    return msgs


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("project"); ap.add_argument("--repo", required=True, help="a clone of the language repository")
    ap.add_argument("--books", help="book codes, comma-separated")
    ap.add_argument("--report", help="write the plan here (JSON; references and figures, no text)")
    ap.add_argument("--apply", action="store_true", help="write and commit in the clone (never pushed)")
    ap.add_argument("--config", help="publish.yaml to use (default: the work copy's root)")
    ap.add_argument("--skip-check", action="store_true", help=argparse.SUPPRESS)   # tests only
    a = ap.parse_args()
    repo = os.path.abspath(os.path.expanduser(a.repo))
    res, cfg, todo = plan(a.project, repo, set(a.books.split(",")) if a.books else None, a.skip_check, a.config)
    if a.report:
        json.dump(res, open(a.report, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if res["refused"]:
        print(f"{a.project}: refused, nothing to publish:")
        for r in res["refused"]:
            print("  -", r)
        sys.exit(1)
    for n in res["notes"]:
        print("note:", n)
    ch = res["changed"]
    print(f"{a.project} -> {res['repo']}: {len(res['new'])} new, {len(res['same'])} same, {len(ch)} changed "
          f"({sum(c['text'] for c in ch)} with new text), {len(res['left out'])} left out, "
          f"{len(res['held back by the screen'])} held back by the screen; screen: {res['screen']['mark']}, "
          f"{res['screen']['comparisons']} unit comparisons against {', '.join(res['screen']['editions']) or 'no edition'}")
    for x in res["left out"][:20]:
        print("  left out:", x)
    for x in res["held back by the screen"][:20]:
        print("  held back:", x["chapter"], ", ".join(f"{u['range']} run {u['run']} share {u['share']}" for u in x["units"][:3]))
    for x in res["problems"][:10]:
        print("  problem:", x)
    if res.get("derived"):
        print("  derived files:", ", ".join(res["derived"]))
    if not a.apply:
        print("dry run: nothing written (--apply writes and commits in the clone)")
        return
    for m in apply(repo, res, cfg, todo):
        print(" ", m)
    print(f"pushed by you: git -C {repo} push origin main approved" + (f" draft/{datetime.date.today().isoformat()}" if ch else ""))


if __name__ == "__main__":
    main()
