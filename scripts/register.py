#!/usr/bin/env python3
"""The register: a project's language knowledge (its store) as one entry per file (docs/register.md).

    python3 scripts/register.py convert <project> [--keep]      # profile/*.json -> profile/register/ (lossless)
    python3 scripts/register.py check <project>                  # the register's rules (and the round trip)
    python3 scripts/register.py show <project> [id|kind ...]     # entries
    python3 scripts/register.py add <project> --kind K --name N --value V [--status S] [--basis B] [--by W]
                                 [--set key=json ...] [--file decisions.json|observations.json]
    python3 scripts/register.py supersede <project> <id> --value V [--name N] [--set key=json ...] [--by W]
    python3 scripts/register.py retire <project> <id> [--by W] [--note T]
    python3 scripts/register.py status <project> <id> <status>   # a status change, the one edit in place
    python3 scripts/register.py bump <project> [--date D]        # a new revision: VERSION.json, REVISIONS.jsonl

The envelope and the 13 kinds are make-tanakh-grammar's register (shared/register.py, 2026-11-12) plus `spelling`; the
store's entries keep every field: what the envelope and the kind's payload have no place for (the old file, id, kind,
status and other fields) is kept in STORE.json's `round_trip`, never in the entry, so `store_file()` gives back the
old JSON exactly. Every reader of the
store reads through `store_file()` / `store_files()` (old JSON files or a register folder, whichever the project has),
every writer through `save_store()`; `entries()` gives the register's own view.

The lifecycle (stamps, stale, migrate) is scripts/lifecycle.py."""
import argparse, copy, datetime, hashlib, json, os, re, sys

CODE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(CODE, "scripts"))

FORMAT = 2                      # STORE.json `format`: 2 = the round trip in STORE.json (v0.5.0), 1 = in the entries
ROUND_TRIP = "round_trip"       # STORE.json: {entry id: its store part}, what an exact round trip needs beyond origin
FILES = ("observations.json", "decisions.json", "external.json")
KINDS = {   # kind -> (plural, payload keys): grammar's 12 + spelling
    "feature": ("features", ("parameter", "confidence", "frequency", "examples")),
    "rule": ("rules", ("table", "conditions", "do", "said", "verdict", "pattern")),
    "choice": ("choices", ("unit", "ref", "rule", "parameter", "source")),
    "term": ("terms", ("source", "renderings", "denials", "replaces", "gloss", "words", "attested")),
    "name": ("names", ("source", "renderings", "denials", "replaces", "gloss", "words", "attested", "letters")),
    "formula": ("formulas", ("source", "renderings", "gloss", "words", "attested", "pattern")),
    "word": ("words", ("form", "class", "parts", "gloss", "lexemes", "affixes", "never_split")),
    "morph": ("morphs", ("form", "slot", "host", "position", "unimorph", "written", "variants", "tone_pattern", "with",
                         "productive", "greek", "agree", "class")),
    "letter": ("letters", ("examples",)),
    "orthography": ("orthography", ("normalization", "ignore_marks", "tone", "keep_marks", "respell")),
    "answer": ("answers", ("text", "ref", "entries", "who")),
    "question": ("questions", ("text", "ref", "unit", "group", "asked", "answer")),
    "spelling": ("spellings", ("match", "replace", "context", "exceptions", "order", "said")),
}
ENVELOPE = ("id", "kind", "value", "status", "basis", "by", "when", "supersedes", "scope", "evidence", "from", "origin", "note")
REQUIRED = ("id", "kind", "value", "status", "basis", "by", "when")
STATUSES = ("proposed", "decided", "open", "superseded", "retired")
BASES = ("team", "human", "derived", "external", "model")
RENDERING_STATUS = ("preferred", "admitted", "deprecated")
EVIDENCE_WORDS = 4
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
NO_DATE = "1970-01-01"          # a store entry without a date (store.drop says so)
# store kind -> register kind (grammar's onboard/register.py new_id); the id prefixes it strips
STRIP = {"term": "term", "name": "name", "formula": "formula", "m": "morph", "w": "word", "letter": "letter",
         "gap": "choice", "claim": "rule", "gb": "feature", "spelling": "spelling"}
KIND_OF = {"gap": "choice", "claim": "rule", "cell": "rule", "feature": "rule"}
STORE_KIND = {"choice": "gap", "rule": "claim"}
MECHANICAL = {"spelling": "yes", "term": "partly", "name": "partly"}   # lifecycle.py migrate's hint per kind


# ------------------------------------------------------------------ ids and files

def file_of(eid):
    """an entry's file, relative to the register: <kind>/<slug>-<first 6 hex of sha256(id)>.json (grammar's)"""
    kind, name = eid.split(":", 1)
    slug = re.sub(r"[^a-z0-9.-]", "-", name.lower())[:40].strip("-.") or "x"
    return f"{kind}/{slug}-{hashlib.sha256(eid.encode('utf-8')).hexdigest()[:6]}.json"


def register_dir(profile):
    return os.path.join(profile, "register")


def profile_of(pname):
    from project import project_dir
    return os.path.join(project_dir(pname), "profile")


def basis_of(e):
    m, by = e.get("method"), str(e.get("by", ""))
    if m == "team-decision":
        return "team"
    if m == "project-decision":
        return "human"
    if m == "external":
        return "external"
    return "model" if by.startswith("agent:") else "derived"


METHOD_OF = {"team": "team-decision", "human": "project-decision", "external": "external"}


def status_of(e, basis):
    s = e.get("status")
    if s in ("superseded", "retired", "open"):
        return s
    if s == "decided" and basis in ("team", "human"):
        return "decided"
    return "proposed"


def new_id(e):
    """(register kind, register id) of a store entry (grammar's mapping; cells and alternation cues are rules here,
    since the register keeps everything)"""
    sid, k = str(e.get("id")), e.get("kind")
    if sid.startswith("gs:"):
        kind, name = "feature", sid
    else:
        pre = sid.split(":", 1)[0] if ":" in sid else None
        kind = STRIP.get(pre) or KIND_OF.get(k, k)
        if k == "feature" and pre == "gb":
            kind = "feature"
        if kind not in KINDS:
            kind = "rule"
        name = sid.split(":", 1)[1] if pre in STRIP else sid
    return kind, f"{kind}:{re.sub(r'\s', '_', name) or 'x'}"


# ------------------------------------------------------------------ store entry <-> register entry

def _renderings(e):
    if not isinstance(e.get("value"), str):
        return None
    out = [{"form": e["value"], "status": "preferred"}]
    for x in e.get("alternatives") or []:
        if isinstance(x, dict) and isinstance(x.get("value"), str):
            r = {"form": x["value"], **{k: v for k, v in x.items() if k != "value"}}
            if r.get("status") not in ("admitted", "deprecated"):
                r["status"] = "admitted"
            out.append(r)
    return out


def _forward(e, fn, rid, kind, ids):
    """the register entry of a store entry, without its `store` part"""
    b = basis_of(e)
    r = {"id": rid, "kind": kind, "value": e.get("value"), "status": status_of(e, b), "basis": b,
         "by": e.get("by") or "unknown", "when": e.get("date") if DATE.match(str(e.get("date") or "")) else NO_DATE}
    if e.get("supersedes") in ids:
        r["supersedes"] = ids[e["supersedes"]]
    for k in ("scope", "evidence", "note"):
        if e.get(k) not in (None, [], ""):
            r[k] = e[k]
    r["origin"] = f"store:{fn}#{e.get('id')}"
    for k in KINDS[kind][1]:
        if k in e and k != "renderings":
            r[k] = e[k]
    if kind in ("term", "name", "formula"):
        rs = _renderings(e)
        if rs and (len(rs) > 1 or kind != "formula"):
            r["renderings"] = rs
    return r


def sid_of(r):
    """the store id of a register entry"""
    st = r.get("store") or {}
    if st.get("id"):
        return st["id"]
    o = str(r.get("origin") or "")
    return o.split("#", 1)[1] if o.startswith("store:") and "#" in o else r["id"]


def _inverse(r, sids):
    """the store entry a register entry stands for (before its `store` part is applied)"""
    st = r.get("store") or {}
    e = {"id": sid_of(r),
         "kind": st.get("kind") or STORE_KIND.get(r["kind"], r["kind"]), "value": r.get("value")}
    e["status"] = st.get("status") or {"proposed": "observed"}.get(r["status"], r["status"])
    if r["basis"] in METHOD_OF:
        e["method"] = METHOD_OF[r["basis"]]
    e["by"] = r.get("by"); e["date"] = r.get("when")
    if r.get("supersedes"):
        e["supersedes"] = sids.get(r["supersedes"], r["supersedes"])
    for k in ("scope", "evidence", "note"):
        if k in r:
            e[k] = r[k]
    for k in KINDS[r["kind"]][1]:
        if k in r and k != "renderings":
            e[k] = r[k]
    if r.get("renderings") and len(r["renderings"]) > 1:
        e["alternatives"] = [{"value": x["form"], **{k: v for k, v in x.items() if k != "form"}} for x in r["renderings"][1:]]
    for k, v in (st.get("rest") or {}).items():
        e[k] = v
    for k in st.get("drop") or []:
        e.pop(k, None)
    if st.get("keys"):
        e = {k: e[k] for k in st["keys"] if k in e} | {k: v for k, v in e.items() if k not in st["keys"]}
    return e


def from_store(e, fn, rid, kind, ids):
    """the register entry of a store entry, with a `store` part that makes the round trip exact"""
    r = _forward(e, fn, rid, kind, ids)
    sids = {v: k for k, v in ids.items()}
    st = {"file": fn}
    r["store"] = st
    if r["origin"].split("#", 1)[1] != e.get("id"):
        st["id"] = e.get("id")
    if STORE_KIND.get(kind, kind) != e.get("kind"):
        st["kind"] = e.get("kind")
    back = _inverse(r, sids)
    if back.get("status") != e.get("status"):
        st["status"] = e.get("status")
    back = _inverse(r, sids)
    rest = {k: v for k, v in e.items() if k not in back or back[k] != v or type(back[k]) is not type(v)}
    drop = [k for k in back if k not in e]
    if rest:
        st["rest"] = rest
    if drop:
        st["drop"] = drop
    if list(_inverse(r, sids)) != list(e):
        st["keys"] = list(e)
    assert _inverse(r, sids) == e and list(_inverse(r, sids)) == list(e), e.get("id")
    return r


def to_store(r, sids):
    return _inverse(r, sids)


# ------------------------------------------------------------------ the register folder

def load(d, store=True):
    """all entries of a register folder, kind by kind, by file name; store: each with its `store` part (the round trip
    to the old JSON files, kept in STORE.json's `round_trip`, never in the entry file), else exactly as the files hold
    them. An entry file written by v0.4.0 holds its `store` part itself: read as before, moved out at the next write"""
    rt = _layout(d).get(ROUND_TRIP) or {} if store else {}
    out = []
    for kind in KINDS:
        k = os.path.join(d, kind)
        for f in sorted(os.listdir(k)) if os.path.isdir(k) else []:
            if f.endswith(".json"):
                e = json.load(open(os.path.join(k, f), encoding="utf-8"))
                if store:
                    st = _full_store(e, e.pop("store", None) or rt.get(e.get("id")))
                    if st:
                        e["store"] = st
                out.append(e)
    return out


def _origin_file(e):
    o = str(e.get("origin") or "")
    return o[6:].split("#", 1)[0] if o.startswith("store:") else None


def _full_store(e, st):
    """an entry's `store` part, its file filled in from `origin`"""
    st = dict(st or {})
    if "file" not in st and _origin_file(e):
        st["file"] = _origin_file(e)
    return st


def _small_store(e, st):
    """what of an entry's `store` part STORE.json keeps: the file and id only where `origin` doesn't give them"""
    st = dict(st or {})
    if st.get("file") and st["file"] == _origin_file(e):
        del st["file"]
    if st.get("id") and st["id"] == sid_of(e):
        o = str(e.get("origin") or "")
        if o.startswith("store:") and o.split("#", 1)[-1] == st["id"]:
            del st["id"]
    return st


def _dump(e):
    return json.dumps(e, ensure_ascii=False, indent=1) + "\n"


def write_entry(d, e, lay=None, write=True):
    """an entry's file, without its `store` part, which goes into the layout's `round_trip` (lay: the layout being built,
    written by the caller; None: STORE.json read and written here); write=False: the round trip only"""
    e = dict(e); small = _small_store(e, e.pop("store", None))
    if write:
        p = os.path.join(d, file_of(e["id"])); os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(_dump(e))
    own = lay is None
    lay = _layout(d) if own else lay
    rt = lay.setdefault(ROUND_TRIP, {})
    if small:
        rt[e["id"]] = small
    else:
        rt.pop(e["id"], None)
    if own:
        _write_layout(d, lay)
    _CACHE.clear(); _STAMP.clear()


def _layout(d):
    p = os.path.join(d, "STORE.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {"format": FORMAT, "files": {}}


def _write_layout(d, lay):
    with open(os.path.join(d, "STORE.json"), "w", encoding="utf-8") as fh:
        fh.write(json.dumps(lay, ensure_ascii=False, indent=1) + "\n")
    _CACHE.clear(); _STAMP.clear()


def write_store(d, files, when=None):
    """{file: store dict} -> the register folder d (entries no longer given are removed); STORE.json keeps each file's
    header and order. The orthography becomes an entry, `orthography:main` (a file whose orthography differs gets
    `orthography:<partition>`)"""
    os.makedirs(d, exist_ok=True)
    old = {e["id"]: e for e in load(d, store=False)}      # the files as they are, to rewrite only what changes
    taken, keep, lay, ids = set(), set(), {"format": FORMAT, "files": {}}, {}
    plan = []
    for fn, data in files.items():
        for e in data.get("entries", []):
            kind, rid = new_id(e)
            n, base = 2, rid
            while rid in taken:
                rid, n = f"{base}.{n}", n + 1
            taken.add(rid); plan.append((fn, e, rid, kind))
            ids.setdefault(e.get("id"), rid)
    orth = {}
    for fn, data in files.items():
        head = {k: v for k, v in data.items() if k != "entries"}
        if "orthography" in head and isinstance(head["orthography"], dict):
            same = next((oid for oid, o in orth.items() if o == head["orthography"]), None)
            if not same:
                same = "orthography:main" if not orth else f"orthography:{data.get('partition') or fn.split('.')[0]}"
                orth[same] = head["orthography"]
                o = head["orthography"]
                x = dict(old.get(same) or {}) or {"id": same, "kind": "orthography", "value": "the language's writing", "status": "proposed",
                                      "basis": "derived", "by": "script:register.py", "when": when or datetime.date.today().isoformat()}
                x = {k: v for k, v in x.items() if k not in KINDS["orthography"][1] and k != "store"}
                extra = {k: v for k, v in o.items() if k not in KINDS["orthography"][1]}
                x.update({k: o[k] for k in o if k in KINDS["orthography"][1]})
                st = {"file": fn, "keys": list(o)}
                if extra:
                    st["rest"] = extra
                x["store"] = st
                write_entry(d, x, lay); keep.add(file_of(same))
            head["orthography"] = {"$entry": same}
        lay["files"][fn] = {"header": head, "keys": list(data), "entries": [rid for f, e, rid, k in plan if f == fn]}
    for fn, e, rid, kind in plan:
        r = from_store(e, fn, rid, kind, ids)
        write_entry(d, r, lay, write=old.get(rid) != {k: v for k, v in r.items() if k != "store"})
        keep.add(file_of(rid))
    for kind in KINDS:
        k = os.path.join(d, kind)
        for f in os.listdir(k) if os.path.isdir(k) else []:
            if f.endswith(".json") and f"{kind}/{f}" not in keep:
                os.remove(os.path.join(k, f))
    _write_layout(d, lay)


def read_store(d):
    """the register folder -> {file: store dict}, exactly the JSON the store files held"""
    E = {e["id"]: e for e in load(d)}
    lay = _layout(d); out = {}
    sids = {rid: sid_of(e) for rid, e in E.items()}
    for fn, f in lay["files"].items():
        data = {}
        for k in f["keys"]:
            if k == "entries":
                data["entries"] = [to_store(E[rid], sids) for rid in f["entries"] if rid in E]
            elif k == "orthography" and isinstance(f["header"].get(k), dict) and "$entry" in f["header"][k]:
                o = E.get(f["header"][k]["$entry"]) or {}
                st = o.get("store") or {}
                vals = {**{x: o[x] for x in KINDS["orthography"][1] if x in o}, **(st.get("rest") or {})}
                data[k] = {x: vals[x] for x in st.get("keys") or vals if x in vals}
            else:
                data[k] = f["header"][k]
        out[fn] = data
    return out


# ------------------------------------------------------------------ the loader: every reader and writer of the store

def has_register(profile):
    return os.path.exists(os.path.join(register_dir(profile), "STORE.json"))


def store_files(profile):
    """{file: store dict} of a profile folder: from its register if it has one, else from the JSON files"""
    if has_register(profile):
        return read_store(register_dir(profile))
    out = {}
    for fn in FILES:
        p = os.path.join(profile, fn)
        if os.path.exists(p):
            out[fn] = json.load(open(p, encoding="utf-8"))
    return out


_CACHE = {}


def store_file(profile, fn, default=None):
    """one store file's dict (observations.json, decisions.json, external.json), or default when the store has none"""
    if has_register(profile):
        d = register_dir(profile)
        key = (d, _stamp(d))
        if key not in _CACHE:                # each file kept as JSON text: a fresh copy per read, faster than deepcopy
            _CACHE.clear(); _CACHE[key] = {f: json.dumps(x, ensure_ascii=False) for f, x in read_store(d).items()}
        x = _CACHE[key].get(fn)
        return json.loads(x) if x is not None else default
    p = os.path.join(profile, fn)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else default


def store_exists(profile, fn):
    if not has_register(profile):
        return os.path.exists(os.path.join(profile, fn))
    store_file(profile, fn)                  # fills the cache
    d = register_dir(profile)
    return any(fn in v for k, v in _CACHE.items() if k[0] == d)


_STAMP = {}


def _stamp(d):
    """the newest mtime in the register folder; walked at most once a second (this process's own writes clear the cache)"""
    import time
    now = time.monotonic()
    if d in _STAMP and now - _STAMP[d][0] < 1 and _CACHE:
        return _STAMP[d][1]
    t = _walk_stamp(d)
    _STAMP[d] = (now, t)
    return t


def _walk_stamp(d):
    t = 0
    for root, _, fs in os.walk(d):
        for f in fs:
            t = max(t, os.stat(os.path.join(root, f)).st_mtime_ns)
    return t


def save_store(profile, fn, data):
    """write one store file into the register when the project has one (True); False: the project has the old JSON
    files, and the writer writes its file as before

        if not register.save_store(P.profile, "observations.json", d):
            json.dump(d, open(f, "w"), ...)"""
    if not has_register(profile):
        return False
    files = read_store(register_dir(profile)); files[fn] = data
    write_store(register_dir(profile), files); _CACHE.clear(); _STAMP.clear()
    return True


def is_store_path(f):
    return os.path.basename(f) in FILES


def read(f, default=None):
    """a store file by its old path (<profile>/observations.json, ...): the register's reconstruction when the profile
    has a register, else the JSON file; default when neither has it. Readers replace json.load(open(f)) with this"""
    if is_store_path(f):
        return store_file(os.path.dirname(f), os.path.basename(f), default)
    return json.load(open(f, encoding="utf-8")) if os.path.exists(f) else default


def exists(f):
    """os.path.exists for a store file's old path"""
    return store_exists(os.path.dirname(f), os.path.basename(f)) if is_store_path(f) else os.path.exists(f)


def write(f, data, newline=False, **dump):
    """write a store file by its old path: into the register when the profile has one, else json.dump(data, f, **dump)
    (plus a final newline when newline) exactly as the writer did before"""
    if is_store_path(f) and save_store(os.path.dirname(f), os.path.basename(f), data):
        return
    with open(f, "w", encoding="utf-8") as fh:
        json.dump(data, fh, **dump)
        if newline:
            fh.write("\n")


def mtime(f):
    """the newest change of a store file (its register folder when there is one)"""
    if is_store_path(f) and has_register(os.path.dirname(f)):
        return _stamp(register_dir(os.path.dirname(f))) / 1e9
    return os.path.getmtime(f) if os.path.exists(f) else 0


def entries(project=None, kinds=None, status=None, profile=None):
    """the register's entries of a project (its register folder, or its old store converted in memory), filtered by
    kind and status (a status or a tuple of them)"""
    profile = profile or profile_of(project)
    if has_register(profile):
        E = load(register_dir(profile))
    else:
        files = store_files(profile); ids, taken, plan = {}, set(), []
        for fn, data in files.items():
            for e in data.get("entries", []):
                kind, rid = new_id(e); n, base = 2, rid
                while rid in taken:
                    rid, n = f"{base}.{n}", n + 1
                taken.add(rid); plan.append((fn, e, rid, kind)); ids.setdefault(e.get("id"), rid)
        E = [from_store(e, fn, rid, kind, ids) for fn, e, rid, kind in plan]
    if kinds:
        E = [e for e in E if e["kind"] in kinds]
    if status:
        st = (status,) if isinstance(status, str) else tuple(status)
        E = [e for e in E if e["status"] in st]
    return E


def live(E):
    return [e for e in E if e["status"] not in ("superseded", "retired")]


# ------------------------------------------------------------------ what agents are told

ADD = ("with `python3 scripts/register.py add {project} --kind <kind> --name <name> --value <value> --basis human "
       "--by agent:<code><NNN> --set evidence='[{{\"ref\": \"BOOK C:V\"}}]' --set gloss=…` (one call per entry; "
       "`register.py supersede {project} <id> --value …` to change one; never edit `profile/register/` itself)")


def agent_wording(text, pname, long=False):
    """a prompt's store instructions for a project whose store is a register: entries go in through register.py, not
    into the JSON files (unchanged text for a project with the old store); long: a whole prompt, which gets a closing
    paragraph when it still names the old files"""
    if not has_register(profile_of(pname)):
        return text
    add = ADD.format(project=pname)
    text = re.sub(r"(?:add|append) to `(?:[^`]*/)?profile/(?:observations|decisions)\.json`(?: and `(?:[^`]*/)?profile/"
                  r"(?:observations|decisions)\.json`)?", "add " + add, text)
    text = re.sub(r"as a store entry in `[^`]*profile/decisions\.json`(?: \([^)]*\))? or `observations\.json`",
                  "as a register entry " + add, text)
    text = text.replace("`method: project-decision`", "`--basis human`")          # idempotent: the store's terms
    text = text.replace('`method: "team-decision"`', "`--basis team`")
    if long and re.search(r"(observations|decisions)\.json", text):
        text += ("\n\nThis project's store is a register (`docs/register.md`): `" + "profile/register/" + "`, one entry per "
                 "file. Where this prompt names `observations.json` or `decisions.json`, read the entries with "
                 f"`python3 scripts/register.py show {pname}` or `concord.py {pname} store`, and write each one {add}.")
    return text


# ------------------------------------------------------------------ the check (grammar's rules, plus spelling)

PARAMETERS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "register", "parameters.tsv")


def parameters(p=PARAMETERS):
    """{id: {question, codes, group, type, source}}: the shared questionnaire (Grambank, WALS, APiCS, AUTOTYP: CC BY 4.0,
    credited per row; make-tanakh's own: CC0), from make-tanakh-grammar's register/parameters.tsv"""
    import csv
    if not os.path.exists(p):
        return {}
    return {r["id"]: r for r in csv.DictReader(open(p, encoding="utf-8"), delimiter="\t")}


def check(E, protected=False, params=None):
    """(errors, warnings)"""
    err, warn, ids = [], [], {}
    params = parameters() if params is None else params
    for i, e in enumerate(E):
        where = e.get("id") or f"entry {i + 1}"
        miss = [k for k in REQUIRED if k not in e]
        if miss:
            err.append(f"{where}: missing {miss}"); continue
        k = e["kind"]
        if k not in KINDS:
            err.append(f"{where}: unknown kind {k}"); continue
        if k == "feature" and e.get("parameter") and params and e["parameter"] not in params:
            err.append(f"{where}: parameter {e['parameter']} is not in the questionnaire (docs/register/parameters.tsv)")
        if not e["id"].startswith(k + ":") or re.search(r"\s", e["id"]):
            err.append(f"{where}: an id is <kind>:<name> without white space")
        if e["id"] in ids:
            err.append(f"{where}: id used twice")
        ids[e["id"]] = e
        if e["status"] not in STATUSES:
            err.append(f"{where}: status {e['status']}")
        if e["basis"] not in BASES:
            err.append(f"{where}: basis {e['basis']}")
        if not DATE.match(str(e["when"])):
            err.append(f"{where}: when {e['when']}")
        extra = set(e) - set(ENVELOPE) - set(KINDS[k][1])
        if extra:
            err.append(f"{where}: unknown keys {sorted(extra)}")
        for ev in e.get("evidence") or []:
            if protected and isinstance(ev, dict) and len(str(ev.get("form") or "").split()) > EVIDENCE_WORDS:
                err.append(f"{where}: an evidence form of more than {EVIDENCE_WORDS} words")
        for r in e.get("renderings") or []:
            if r.get("status") not in RENDERING_STATUS:
                err.append(f"{where}: a rendering's status {r.get('status')}")
        pref = [r.get("form") for r in e.get("renderings") or [] if r.get("status") == "preferred"]
        if pref and e["value"] not in pref:
            err.append(f"{where}: the value is the preferred rendering ({pref[0]}), not {e['value']}")
        if k == "spelling":
            if not isinstance(e.get("match"), str) or not isinstance(e.get("replace"), str) or not e.get("said"):
                err.append(f"{where}: a spelling entry needs match, replace and said")
            else:
                c = e.get("context") or {}
                for x in [e["match"], c.get("before"), c.get("after"), (c.get("unless") or {}).get("before"),
                          (c.get("unless") or {}).get("after")]:
                    try:
                        re.compile(x or "")
                    except re.error as x_:
                        err.append(f"{where}: pattern {x!r}: {x_}")
    for e in ids.values():
        s = e.get("supersedes")
        if s and s not in ids:
            err.append(f"{e['id']}: supersedes {s}, which is not in the register")
        elif s and ids[s]["basis"] == "team" and ids[s]["status"] in ("decided", "superseded") and e["basis"] != "team" \
                and ids[s].get("status") == "decided":
            err.append(f"{e['id']}: only the team may supersede the team's decision {s}")
        for f in e.get("from") or []:
            if f not in ids or ids[f]["kind"] not in ("answer", "question"):
                warn.append(f"{e['id']}: from {f}, which is no answer or question of the register")
        if e["kind"] == "orthography":
            for x in e.get("respell") or []:
                if x not in ids or ids[x]["kind"] != "spelling":
                    err.append(f"{e['id']}: respell names {x}, which is no spelling entry")
    return err, warn


def check_files(d):
    err = []
    for kind in KINDS:
        k = os.path.join(d, kind)
        for f in sorted(os.listdir(k)) if os.path.isdir(k) else []:
            e = json.load(open(os.path.join(k, f), encoding="utf-8"))
            if file_of(e.get("id", "x:x")) != f"{kind}/{f}":
                err.append(f"{kind}/{f}: the name does not match the id {e.get('id')}")
    return err


# ------------------------------------------------------------------ revisions

def digest(e):
    return hashlib.sha256(_dump(e).encode("utf-8")).hexdigest()[:12]


def version(d):
    p = os.path.join(d, "VERSION.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {"revision": "register-0", "digests": {}}


def revision(profile):
    """the project's register revision (register-<n>; register-0 before the first bump or without a register)"""
    return version(register_dir(profile)).get("revision", "register-0") if has_register(profile) else "register-0"


def rev_n(rev):
    m = re.match(r"register-(\d+)$", str(rev or ""))
    return int(m[1]) if m else 0


def revisions(profile):
    """[{revision, date, changed: {id: added|changed|removed}}] in order"""
    p = os.path.join(register_dir(profile), "REVISIONS.jsonl")
    return [json.loads(x) for x in open(p, encoding="utf-8")] if os.path.exists(p) else []


def bump(profile, date=None):
    """a new revision: VERSION.json {revision, date, entries, sha256, digests}, a REVISIONS.jsonl line of the ids changed
    since the last one. The revision is also a suggested git tag name; no tag is made"""
    d = register_dir(profile); v = version(d); E = load(d, store=False)
    dig = {e["id"]: digest(e) for e in E}
    old = v.get("digests") or {}
    changed = {i: "added" for i in dig if i not in old} | {i: "changed" for i in dig if i in old and old[i] != dig[i]} \
        | {i: "removed" for i in old if i not in dig}
    n = rev_n(v.get("revision")) + 1
    rev = f"register-{n}"; date = date or datetime.date.today().isoformat()
    whole = hashlib.sha256("".join(f"{i}\t{dig[i]}\n" for i in sorted(dig)).encode()).hexdigest()
    by = {}
    for e in E:
        by[e["kind"]] = by.get(e["kind"], 0) + 1
    json.dump({"revision": rev, "date": date, "entries": len(E), "by kind": by, "sha256": whole, "digests": dig},
              open(os.path.join(d, "VERSION.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    with open(os.path.join(d, "REVISIONS.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"revision": rev, "date": date, "changed": changed}, ensure_ascii=False) + "\n")
    return rev, changed


def changed_since(profile, rev):
    """{id: change} of the revisions after rev, plus what is changed and not yet bumped (as 'unreleased')"""
    out = {}
    for r in revisions(profile):
        if rev_n(r["revision"]) > rev_n(rev):
            out.update(r["changed"])
    if has_register(profile):
        d = register_dir(profile); dig = version(d).get("digests") or {}
        for e in load(d, store=False):
            if dig.get(e["id"]) != digest(e):
                out.setdefault(e["id"], "unreleased")
    return out


# ------------------------------------------------------------------ edits: add, supersede, retire, status

FILE_OF_KIND = {"term": "decisions.json", "name": "decisions.json", "formula": "decisions.json", "spelling": "decisions.json"}


def _need(profile):
    if not has_register(profile):
        sys.exit(f"no register in {profile} (python3 scripts/register.py convert <project>)")
    return register_dir(profile)


def add(profile, e, fn=None):
    """a new entry (the envelope's defaults filled in) appended to its store file's order"""
    d = _need(profile); E = {x["id"]: x for x in load(d)}
    if e["id"] in E:
        sys.exit(f"{e['id']} is in the register already (supersede it)")
    e = {"status": "proposed", "basis": "model", "by": "unknown", "when": datetime.date.today().isoformat(), **e}
    e = {k: e[k] for k in ENVELOPE if k in e} | {k: v for k, v in e.items() if k not in ENVELOPE}
    fn = fn or FILE_OF_KIND.get(e["kind"], "observations.json")
    e.setdefault("origin", f"store:{fn}#{e['id']}")
    e["store"] = {"file": fn, **({"id": e["id"]} if e["origin"] == f"store:{fn}#{e['id']}" else {})}
    if e["kind"] in ("term", "name") and isinstance(e.get("value"), str) and not e.get("renderings"):
        e["renderings"] = [{"form": e["value"], "status": "preferred"}]
    err, _ = check([{k: v for k, v in x.items() if k != "store"} for x in list(E.values()) + [e]])
    err = [x for x in err if x.startswith(e["id"] + ":")]
    if err:
        sys.exit("\n".join(err))
    write_entry(d, e)
    lay = _layout(d); f = lay["files"].setdefault(fn, {"header": {}, "keys": ["entries"], "entries": []})
    f["entries"].append(e["id"]); _write_layout(d, lay); _CACHE.clear(); _STAMP.clear()
    return e


def supersede(profile, old_id, new):
    """a new entry replacing old_id (never an edit in place); the old one's status becomes superseded"""
    d = _need(profile); E = {x["id"]: x for x in load(d)}; old_id = resolve(d, old_id)
    if old_id not in E:
        sys.exit(f"no entry {old_id}")
    o = E[old_id]
    if o["basis"] == "team" and o["status"] == "decided" and new.get("basis", o["basis"]) != "team":
        sys.exit(f"{old_id} is the team's decision: only the team may supersede it")
    n = {k: v for k, v in o.items() if k not in ("store", "origin", "renderings") or k == "renderings" and "value" not in new}
    n.update(new); n["supersedes"] = old_id; n.setdefault("when", datetime.date.today().isoformat())
    if "id" not in new:
        base, i = old_id, 2
        while f"{base}.{i}" in E:
            i += 1
        n["id"] = f"{base}.{i}"
    fn = (o.get("store") or {}).get("file") or FILE_OF_KIND.get(o["kind"], "observations.json")
    e = add(profile, n, fn)
    set_status(profile, old_id, "superseded")
    return e


def resolve(d, eid):
    """a register id, or the store id an entry was converted from"""
    if ":" in eid and os.path.exists(os.path.join(d, file_of(eid))):
        return eid
    return next((e["id"] for e in load(d) if sid_of(e) == eid), eid)


def set_status(profile, eid, status, note=None, by=None):
    d = _need(profile); eid = resolve(d, eid); p = os.path.join(d, file_of(eid))
    if not os.path.exists(p):
        sys.exit(f"no entry {eid}")
    if status not in STATUSES:
        sys.exit(f"status {status}: one of {STATUSES}")
    e = next(x for x in load(d) if x["id"] == eid); e["status"] = status
    st = e.get("store") or {}
    st.pop("status", None)
    if note:
        e["note"] = ((e.get("note") or "") + ("; " if e.get("note") else "") + note)
    write_entry(d, e); _CACHE.clear(); _STAMP.clear()
    return e


# ------------------------------------------------------------------ commands

def convert(profile, keep=False, when=None):
    """the JSON store -> the register (round trip checked); on a project that has a register already, its entries are
    written again in the current format (a v0.4.0 register's store parts move to STORE.json), with no new revision"""
    first = not has_register(profile)
    files = store_files(profile)
    if not files:
        sys.exit(f"no store in {profile}")
    d = register_dir(profile)
    write_store(d, files, when=when)
    back = read_store(d)
    for fn, data in files.items():
        if json.dumps(back[fn], ensure_ascii=False) != json.dumps(data, ensure_ascii=False):
            sys.exit(f"round trip failed for {fn}: the register is in {d}, the JSON files are kept")
    if first:
        bump(profile, when)                  # register-1: the store as it was converted
    if not keep:
        for fn in files:
            if os.path.exists(os.path.join(profile, fn)):
                os.remove(os.path.join(profile, fn))
    return files, d


def _parse_set(xs):
    out = {}
    for x in xs or []:
        k, _, v = x.partition("=")
        try:
            out[k] = json.loads(v)
        except json.JSONDecodeError:
            out[k] = v
    return out


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ("stale", "migrate", "stamp"):   # the lifecycle's commands (lifecycle.py)
        import lifecycle
        sys.argv[0] = "register.py"
        return lifecycle.main()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("convert"); c.add_argument("project"); c.add_argument("--keep", action="store_true")
    c.add_argument("--profile", help="a profile folder instead of the project's")
    c = sub.add_parser("check"); c.add_argument("project"); c.add_argument("--profile")
    c = sub.add_parser("show"); c.add_argument("project"); c.add_argument("what", nargs="*"); c.add_argument("--profile")
    c = sub.add_parser("add"); c.add_argument("project"); c.add_argument("--kind", required=True)
    c.add_argument("--name", required=True); c.add_argument("--value", required=True); c.add_argument("--status", default="proposed")
    c.add_argument("--basis", default="model"); c.add_argument("--by", default="unknown"); c.add_argument("--note")
    c.add_argument("--set", action="append"); c.add_argument("--file"); c.add_argument("--profile")
    c = sub.add_parser("supersede"); c.add_argument("project"); c.add_argument("id"); c.add_argument("--value", required=True)
    c.add_argument("--name"); c.add_argument("--by"); c.add_argument("--basis"); c.add_argument("--status"); c.add_argument("--note")
    c.add_argument("--set", action="append"); c.add_argument("--profile")
    c = sub.add_parser("retire"); c.add_argument("project"); c.add_argument("id"); c.add_argument("--by"); c.add_argument("--note")
    c.add_argument("--profile")
    c = sub.add_parser("status"); c.add_argument("project"); c.add_argument("id"); c.add_argument("status"); c.add_argument("--profile")
    c = sub.add_parser("bump"); c.add_argument("project"); c.add_argument("--date"); c.add_argument("--profile")
    a = ap.parse_args()
    prof = a.profile or profile_of(a.project)
    if a.cmd == "convert":
        files, d = convert(prof, a.keep)
        print(f"{sum(len(x.get('entries', [])) for x in files.values())} entries of {', '.join(files)} -> {d}"
              f" (round trip exact{'; JSON files kept' if a.keep else '; JSON files removed'})")
    elif a.cmd == "check":
        E = load(register_dir(prof), store=False) if has_register(prof) else \
            [{k: v for k, v in e.items() if k != "store"} for e in entries(profile=prof)]
        err, warn = check(E)
        if has_register(prof):
            err += check_files(register_dir(prof))
        for x in err:
            print("ERROR  ", x)
        for x in warn[:20]:
            print("WARN   ", x)
        print(f"{len(E)} entries, {len(err)} errors, {len(warn)} warnings; revision {revision(prof)}")
        sys.exit(1 if err else 0)
    elif a.cmd == "show":
        E = entries(profile=prof)
        for e in E:
            if not a.what or e["id"] in a.what or e["kind"] in a.what:
                print(json.dumps({k: v for k, v in e.items() if k != "store"}, ensure_ascii=False))
    elif a.cmd == "add":
        e = {"id": f"{a.kind}:{a.name}", "kind": a.kind, "value": a.value, "status": a.status, "basis": a.basis, "by": a.by,
             **({"note": a.note} if a.note else {}), **_parse_set(a.set)}
        print("added", add(prof, e, a.file)["id"])
    elif a.cmd == "supersede":
        n = {"value": a.value, **{k: getattr(a, k) for k in ("by", "basis", "status", "note") if getattr(a, k)}, **_parse_set(a.set)}
        if a.name:
            n["id"] = f"{a.id.split(':')[0]}:{a.name}"
        print("added", supersede(prof, a.id, n)["id"], "; superseded", a.id)
    elif a.cmd == "retire":
        set_status(prof, a.id, "retired", a.note, a.by); print("retired", a.id)
    elif a.cmd == "status":
        set_status(prof, a.id, a.status); print(a.id, "->", a.status)
    elif a.cmd == "bump":
        rev, ch = bump(prof, a.date)
        print(f"{rev}: {len(ch)} entries changed (suggested tag name: {rev}; no tag made)")


if __name__ == "__main__":
    main()
