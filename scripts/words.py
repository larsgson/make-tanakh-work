#!/usr/bin/env python3
"""The corpus's words per source lexeme (export/<project>/_learn/words.db) and the word check of a draft chapter.

words.db (docs/word-db.md) indexes the style edition's own words to the Hebrew and Greek lexemes they render, from
alignment layers of exactly that text in the bcv-commons compact-alignments format. Word forms, counts, references and
token positions only, no verse text; local and git-ignored, never published (it is built from the edition). Only the
edition's own text goes in, never a draft.

    python3 scripts/words.py align <project> [--edition ID] [--out DIR] [--aligner EXE] [--data DIR] [--fetch]
        a local run of lexeme-aligner's align-text on the style edition (no LLM checking: nothing leaves the machine
        but fetch-inputs' downloads of its own pinned data); the run is recorded in OUT/words-align.json
    python3 scripts/words.py build <project> [--layer DIR ...] [--eflomal]
        words.db from the layers: --layer (a compact edition folder: <i>/<iso>/<edition>/), else project.yaml
        `words: {layers: [...]}`, else the runs of `align` (build/words-align/<project>/), else the published layer
        project.yaml names (`lexeme_aligner`, lang.py layers); --eflomal adds align.py's links_grc_pos.tsv (a
        transitional route, marked as such in every row)
    python3 scripts/words.py check <project> <code> <ch> [--respell FILE] [--all]
        the REVIEW lines of a drafted chapter (chapter_check.py calls review() when the project has a words.db):
          term      a decided store term (or formula) whose source word is in the verse and whose value isn't
          spelling  a draft form the corpus never writes, while it writes a one-rule variant of it (doubled or single
                    consonant, y/i, ä/e, long or short vowel, diphthong) at least twice, store forms included;
                    `rare` where the corpus writes the form itself at most twice and the variant ten times as often
          marks     the same letters as a corpus form, other marks
          project spelling  a draft form written as the corpus writes it where the project's respelling rules
                    (the store's `orthography.respell`) write it otherwise
          expected  a source content word whose usual form (share >= LIST_SHARE) isn't in the verse
        and the figure: source content words checkable / with one of the corpus's forms in the verse
    python3 scripts/words.py stats <project>
    python3 scripts/words.py show <project> <lexeme>        a lexeme's forms (hbo:639, H639, grc:3709, G3709)

Counts are made at read time from the occurrences (occ), leaving out the chapters being checked (the holdout): the
link table is a cache. A Hebrew lexeme the corpus has fewer than DIRECT_ENOUGH direct links for is asked through its
Septuagint equivalents (orig/heb.sqlite's lxx table): the bridges with at least BRIDGE_REL of the best one's share."""
import argparse, collections, glob, hashlib, json, os, re, sqlite3, subprocess, sys, time, unicodedata

CODE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.abspath(os.environ.get("MAKE_TANAKH_ROOT") or CODE)   # the data root (books.py)
sys.path.insert(0, os.path.join(CODE, "scripts"))
from books import BY_CODE  # noqa: E402
import register as RG  # noqa: E402

FORMAT = 1
MIN_SHARE, TOP, MIN_N = 0.05, 3, 3        # a form shown: share of its lexeme's links; forms per lexeme; links to be checkable
DIRECT_ENOUGH, BRIDGE_REL = 10, 0.5        # a Hebrew lexeme with this many direct links needs no bridge; bridges >= half the best
BRIDGE_MIN = 2                             # a bridge seen at least twice in the Septuagint (one equivalent is no evidence)
LIST_SHARE, LIST_MIN = 0.8, 10             # an expected form listed only when it is the lexeme's form this often, of this many links
VARIANT_MIN = 2                            # a spelling variant the corpus writes at least this often
RARE_MAX, RARE_RATIO, RARE_MIN = 2, 10, 20  # `rare`: the form itself at most twice, the variant >= 10x as often and >= 20x
MAX_FORMS = 6                              # a decided value of more forms is a list of a chapter's forms: not checked
FUNCTION_TOP = 60                          # a decided value's word among the corpus's commonest forms is not required
CONTENT = ("noun", "verb", "adj")
STOP_EN = set("a an the and or but of to in on at by for with from as is are was were be been his her their him them he she "
              "they it its this that these those who which what will shall not no all one i you we me my your our us".split())
DEFAULT_KEEP = ("̈", "̊", "̧", "̨")   # diaeresis, ring, cedilla, ogonek: letters, not tone
VOWELS = "aeiouyäöüåæøéèàáíóúâêîôû"
PAIRS = [("y", "i"), ("ä", "e")]           # one-rule variants beside doubling, long vowels and diphthongs
SCHEMA = """
create table lexeme(id text primary key, lang text, strong text, lemma text, cls text, n int, type text);
create table form(id integer primary key, form text unique, plain text, bare text, tokens int, n int, project text);
create table link(lexeme text, form int, n int, n_strong int, books text, share real, back real, primary key (lexeme, form));
create table occ(lexeme text, form int, ref text, src text, key text, positions text, method text, edition text,
                 layer text, level text);
create table vocab(plain text, bare text, book text, ch int, n int, edition text);
create table meta(name text primary key, value text);
"""
INDEXES = ("create index form_plain on form(plain)", "create index form_bare on form(bare)",
           "create index link_form on link(form)", "create index occ_lexeme on occ(lexeme)", "create index occ_form on occ(form)",
           "create index occ_ref on occ(ref)", "create index vocab_plain on vocab(plain)")


# --- forms -------------------------------------------------------------------

def nfc(s):
    return unicodedata.normalize("NFC", s or "")


def bare(s, keep=DEFAULT_KEEP):
    """NFD, combining marks dropped except the kept ones, NFC (lower case is the caller's)"""
    return nfc("".join(c for c in unicodedata.normalize("NFD", s) if not unicodedata.combining(c) or c in keep))


def written_tokens(text):
    """the verse's tokens as written (NFC, every mark kept), position for position the tokens of compact-alignments'
    tokenizer (full_align.tokenize, which drops the marks): the positions of a layer and of a .align count these"""
    import full_align as FA, langtools as LT
    toks, cur, lead = [], [], True
    for ch in nfc(text):
        if FA.dropped(ch):
            if cur:
                cur.append(ch)
            continue
        if unicodedata.category(ch)[0] in ("L", "M"):
            cur.append(ch)
        elif cur:
            toks += LT._segment_like_bcv("".join(cur)); cur = []
    if cur:
        toks += LT._segment_like_bcv("".join(cur))
    if len(toks) != len(FA.tokenize(text)):        # never expected; the published tokens win
        return FA.tokenize(text)
    return toks


def lex_id(lang, s):
    """an index's Strong's number -> `grc:26`, `hbo:2050b` (zeros dropped, a homonym letter kept)"""
    m = re.fullmatch(r"[HG]?0*(\d+)([a-z]?)", (s or "").strip())
    return f"{lang}:{m[1]}{m[2]}" if m else None


def heb_lexeme(strong):
    """`639`, `hbo:639`, `H639` -> orig/heb.sqlite's `0639`"""
    m = re.fullmatch(r"(?:hbo:|H)?0*(\d+)([a-z]?)", strong)
    return f"{int(m[1]):04d}{m[2]}" if m else strong


def tokens_of(form):
    return [w for w in form.replace(" … ", " ").split() if w]


def found(form, words):
    """is a lower-case form (one token or several) in a set of lower-case words?"""
    return all(w in words for w in tokens_of(form))


# --- respelling (the project's spelling of corpus forms) ----------------------

SPELLING = ("from", "to", "context", "exceptions", "order", "said")   # a spelling entry's payload
LIVE_SPELLING = ("decided",)                 # the statuses of a spelling entry that respell (open: proposed, not in force)


def spelling_rules(store, statuses=LIVE_SPELLING):
    """the ordered respelling rules of a store, {"entries": [...], "orthography": {"respell": [ids]}}: its `spelling`
    entries (kind spelling, not superseded, of the given statuses), in the order of `orthography.respell` (the ids),
    else by their `order`. A rule is the entry's payload, beside the envelope as in the register: {from, to, context:
    {before, after, unless: {before, after}}, exceptions: [forms], order, said}; `value` is its short form, `l → u`"""
    es = [e for e in store.get("entries", []) if e.get("kind") == "spelling"]
    gone = {e.get("supersedes") for e in store.get("entries", []) if e.get("supersedes")}
    live = {e["id"]: e for e in es if e.get("status") in statuses and e["id"] not in gone and isinstance(e.get("from"), str)}
    ids = (store.get("orthography") or {}).get("respell")
    if ids is None:
        ids = sorted(live, key=lambda i: (live[i].get("order", 0), i))
    return [{k: live[i].get(k) for k in SPELLING} | {"id": i} for i in ids if i in live]


def respell_rules(P=None, path=None, statuses=LIVE_SPELLING):
    """the project's respelling rules: from a file of the store's shape (--respell: {"entries": [spelling entries],
    "orthography": {"respell": [ids]}}), else from the store (profile/decisions.json: the rules are project
    decisions), else none"""
    if path:
        return spelling_rules(json.load(open(path, encoding="utf-8")), statuses)
    if P is None:
        return []
    store = {"entries": []}
    for fn in ("decisions.json", "observations.json"):
        f = os.path.join(P.profile, fn)
        if RG.exists(f):
            x = RG.read(f)
            store["entries"] += x.get("entries", [])
            if fn == "decisions.json" and (x.get("orthography") or {}).get("respell") is not None:
                store["orthography"] = x["orthography"]
    return spelling_rules(store, statuses)


class Respeller:
    """respell(form): a corpus form in the project's spelling (lower case in, lower case out); identity without rules.
    A rule replaces each match of `from` whose text before it ends in `context.before` and whose text after it starts
    with `context.after` (regular expressions; `$` = the word's end), unless both of `context.unless` hold; a form in
    `exceptions` is left as it is, also inside a compound (`altar` in `Brandopferaltar`), and so is a name. Matches are
    found on the form as it was before the rule."""
    def __init__(self, rules, names=()):
        def ctx(r):
            c = r.get("context") or {}; u = c.get("unless") or {}
            return dict(r, rx=re.compile(r["from"]), b=re.compile(f"(?:{c['before']})$") if c.get("before") else None,
                        a=re.compile(c["after"]) if c.get("after") else None,
                        ub=re.compile(f"(?:{u['before']})$") if u.get("before") else None,
                        ua=re.compile(u["after"]) if u.get("after") else None,
                        ex={nfc(x).lower() for x in r.get("exceptions") or ()})
        self.rules = [ctx(r) for r in rules or ()]
        self.names = {nfc(x).lower() for x in names}
        self.cache = {}

    def __bool__(self):
        return bool(self.rules)

    @staticmethod
    def apply(r, w):
        out, last = [], 0
        keep = [(i.start(), i.start() + len(x)) for x in r["ex"] for i in re.finditer(re.escape(x), w)]
        for m in r["rx"].finditer(w):
            if any(a <= m.start() and m.end() <= b for a, b in keep):
                continue
            pre, post = w[:m.start()], w[m.end():]
            ok = (not r["b"] or r["b"].search(pre)) and (not r["a"] or r["a"].match(post))
            if ok and (r["ub"] or r["ua"]):
                ok = not ((not r["ub"] or r["ub"].search(pre)) and (not r["ua"] or r["ua"].match(post)))
            if ok:
                out += [w[last:m.start()], r["to"]]; last = m.end()
        return "".join(out) + w[last:]

    def __call__(self, form):
        if not self.rules:
            return form
        if form not in self.cache:
            out = []
            for w in form.split(" "):
                if w != "…" and w not in self.names:
                    for r in self.rules:
                        if w not in r["ex"]:
                            w = self.apply(r, w)
                out.append(w)
            self.cache[form] = " ".join(out)
        return self.cache[form]

    def changes(self, form):
        return self(form) != form


def keep_marks(P):
    """the combining marks `bare` keeps: project.yaml `words: {keep_marks: [...]}`, else the store's
    `orthography.keep_marks`, else DEFAULT_KEEP (letters' marks, not tone)"""
    ch = lambda m: chr(int(m[2:], 16)) if m.upper().startswith("U+") else m
    km = (P.p.get("words") or {}).get("keep_marks")
    if km is None:
        for fn in ("decisions.json", "observations.json"):
            f = os.path.join(P.profile, fn)
            if km is None and RG.exists(f):
                km = (RG.read(f).get("orthography") or {}).get("keep_marks")
    return tuple(ch(m) for m in km) if km is not None else DEFAULT_KEEP


# --- spelling variants -------------------------------------------------------

def variants(w, pairs=PAIRS):
    """{variant: rule} of a bare lower-case form, one rule applied once: a doubled consonant single or a single one
    doubled, a pair (y/i, ä/e) swapped, a long vowel (doubled, or with h) short or a short one long, a diphthong
    (two different vowels) reduced to either vowel or a vowel made one"""
    out = {}
    put = lambda v, r: out.setdefault(v, r) if v and v != w else None
    for i, c in enumerate(w):
        if not c.isalpha():
            continue
        nxt = w[i + 1] if i + 1 < len(w) else ""
        if c not in VOWELS:
            if nxt == c:
                put(w[:i] + w[i + 1:], "double/single")
            elif (not i or w[i - 1] != c):
                put(w[:i + 1] + c + w[i + 1:], "double/single")
        else:
            if nxt == c:
                put(w[:i] + w[i + 1:], "long/short vowel")
            elif not i or w[i - 1] != c:
                put(w[:i + 1] + c + w[i + 1:], "long/short vowel")
            if nxt == "h":
                put(w[:i + 1] + w[i + 2:], "long/short vowel")
            elif nxt not in VOWELS:
                put(w[:i + 1] + "h" + w[i + 1:], "long/short vowel")
            if nxt and nxt in VOWELS and nxt != c:
                put(w[:i] + w[i + 1:], "diphthong")
                put(w[:i + 1] + w[i + 2:], "diphthong")
    for a, b in pairs:
        for x, y in ((a, b), (b, a)):
            for m in re.finditer(re.escape(x), w):
                put(w[:m.start()] + y + w[m.end():], f"{a}/{b}")
    return out


def corpus_variant(w, counts, keep=DEFAULT_KEEP, pairs=PAIRS, least=VARIANT_MIN):
    """the corpus's commonest one-rule variant of a lower-case form: (variant, rule, n) or None; counts = Counter(bare)"""
    best = None
    for v, r in variants(bare(w, keep), pairs).items():
        n = counts.get(v, 0)
        if n >= least and (best is None or n > best[2]):
            best = (v, r, n)
    return best


# --- the edition's text and its layers ---------------------------------------

def edition_verses(P):
    """{edition id: {BOOK: [(c, v, text)]}} of the style editions, each in its own numbering"""
    import langtools as LT
    out = {}
    for name, e in zip(P.p["style_from"], P.editions):
        d = os.path.join(ROOT, e["dir"], e.get("text_dir", "text")); by = collections.defaultdict(list)
        for f in sorted(glob.glob(os.path.join(d, "*.txt"))):
            b = os.path.basename(f)
            if re.fullmatch(r"[0-9a-z]{3}(\d{3})?\.txt", b) and b[:3] in BY_CODE:
                by[b[:3].upper()] += [(c, v, t) for (c, v), t in LT.verses_of(f).items()]
        out[name] = {b: sorted(r) for b, r in by.items()}
    return out


def sha256_file(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def layer_files(d):
    """{BOOK: {hash: (main file, meta file or None)}} of a compact edition folder"""
    out = collections.defaultdict(dict)
    for f in sorted(glob.glob(os.path.join(d, "*_*.json"))):
        n = os.path.basename(f)
        if n.count(".") != 1 or n.startswith("_"):
            continue
        b, h = n[:-5].split("_", 1)
        m = f[:-5] + ".meta.json"
        out[b][h] = (f, m if os.path.exists(m) else None)
    return out


def manifest_entry(d):
    """the layer's manifest entry (versification, verse_map), from a manifest.json up to three folders above it"""
    ed, iso = os.path.basename(os.path.normpath(d)), os.path.basename(os.path.dirname(os.path.normpath(d)))
    up = os.path.normpath(d)
    for _ in range(4):
        up = os.path.dirname(up)
        f = os.path.join(up, "manifest.json")
        if os.path.exists(f):
            e = (json.load(open(f, encoding="utf-8")).get("languages", {}).get(iso, {}).get("editions", {}).get(ed))
            if e:
                return e, f
    return {}, None


def verse_map(name, layer_dir):
    """{spine ref: the edition's ref} from _index/<verse_map> (beside the layer, in the index cache, or downloaded)"""
    import full_align as FA
    if not name:
        return {}
    up = os.path.normpath(layer_dir)
    for _ in range(4):
        up = os.path.dirname(up)
        f = os.path.join(up, "_index", name)
        if os.path.exists(f):
            return json.load(open(f, encoding="utf-8")).get("map", {})
    f = os.path.join(FA.INDEX, name)
    if not os.path.exists(f):
        FA._download(f"{FA.HF_INDEX}/{name}", f)
    return json.load(open(f, encoding="utf-8")).get("map", {})


class Source:
    """orig/grc.sqlite and orig/heb.sqlite by token key: (lemma, class, type)"""
    def __init__(self):
        self.g = sqlite3.connect(os.path.join(ROOT, "orig", "grc.sqlite"))
        self.h = sqlite3.connect(os.path.join(ROOT, "orig", "heb.sqlite"))
        self.cache = {}

    def book(self, lang, book):
        if (lang, book) not in self.cache:
            con = self.g if lang == "grc" else self.h
            self.cache[(lang, book)] = {k: (l, c, t) for k, l, c, t in con.execute(
                "select key, lemma, class, type from tokens where book = ?", (book,))}
        return self.cache[(lang, book)]


def read_layer(d, verses, edition, source, record):
    """occurrences [(lexeme, form, ref, src, key, positions, method, edition, layer, level)] and lexeme info from a
    compact edition folder whose book files are of exactly this text (the text fingerprint in the file name)"""
    import full_align as FA
    entry, _ = manifest_entry(d)
    vm = verse_map(entry.get("verse_map"), d) if entry.get("verse_map") else {}
    layer = record.get("layer") or os.path.basename(os.path.normpath(d))
    occ, lex, st = [], {}, collections.Counter()
    for book, by_hash in sorted(layer_files(d).items()):
        if book not in verses:
            continue
        fp = FA.text_fingerprint(verses[book])[0][:8]
        if fp not in by_hash:
            st["books skipped (not this text)"] += 1
            print(f"  {edition} {book}: no file of the layer for this text (fingerprint {fp}); skipped", file=sys.stderr)
            continue
        main_f, meta_f = by_hash[fp]
        main = json.load(open(main_f, encoding="utf-8")); meta = json.load(open(meta_f, encoding="utf-8")) if meta_f else {}
        meth, fn_s = meta.get("method") or [], meta.get("fn") or []
        lang = "grc" if BY_CODE[book.lower()][2] == "nt" else "hbo"
        L, K = FA.index(book, "lexemes"), FA.index(book, "keys")
        FL, FK = (FA.index(book, "fn"), FA.index(book, "fn_keys")) if fn_s else ({}, {})
        text = {(c, v): t for c, v, t in verses[book]}; toks = {}
        src = source.book(lang, book)
        for i, r in enumerate(L):
            tr = vm.get(r, r)
            m = re.fullmatch(r"(\w+) (\d+):(\w+)", tr)
            if not m or not m[3].isdigit():
                continue
            c, v = int(m[2]), int(m[3])
            if (c, v) not in text:
                continue
            if (c, v) not in toks:
                toks[(c, v)] = written_tokens(text[(c, v)])
            tk = toks[(c, v)]; ref = f"{book} {c}:{v}"
            for kind, s, lexs, keys, ms in (("c", main[i] if i < len(main) else "", L.get(r, []), K.get(r, []),
                                             meth[i] if i < len(meth) else ""),
                                            ("f", fn_s[i] if i < len(fn_s) else "", FL.get(r, []), FK.get(r, []), "")):
                for j, (o, ps) in enumerate(FA.parse(s).items()):
                    lx = lex_id(lang, lexs[o]) if o < len(lexs) else None
                    key = keys[o] if o < len(keys) else ""
                    ps = sorted(p for p in set(ps) if 0 <= p < len(tk))
                    if not lx or not ps:
                        continue
                    form = nfc("".join((" … " if n and p > ps[n - 1] + 1 else " " if n else "") + tk[p] for n, p in enumerate(ps)))
                    if lx not in lex:
                        t = src.get(key.split("+")[0]) or (None, None, None)
                        lex[lx] = (lang, lx.split(":")[1], t[0], t[1], t[2])
                    occ.append((lx, form, ref, f"{kind}{o}", key, json.dumps(ps), ms[j] if j < len(ms) else "", edition,
                                layer, "words"))
                    st["links"] += 1
        st["books"] += 1
    return occ, lex, st


def eflomal_links(P, verses, edition, source):
    """the transitional route: align.py's links_grc_pos.tsv (eflomal, the project's tokens <-> orig/grc), mapped to
    MACULA keys and the index's ordinals; forms in lower case (the project's exact tokens), method `x`"""
    import full_align as FA
    f = os.path.join(P.learn, "links_grc_pos.tsv")
    if not os.path.exists(f):
        raise SystemExit(f"no {os.path.relpath(f, ROOT)}: run python3 scripts/align.py {P.name} --sides grc")
    ed = {"critical": "bgb", "majority": "rp", "tr": "rp"}[P.p.get("nt_basis") or "critical"]
    g = sqlite3.connect(os.path.join(ROOT, "orig", "grc.sqlite"))
    gmap = {(b, c, v, p): k for b, c, v, p, k in g.execute("select book, ch, v, pos, key from map where edition = ?", (ed,))}
    text = {(b, c, v): t for b, rows in verses.items() for c, v, t in rows}
    by = collections.defaultdict(list)
    for l in open(f, encoding="utf-8"):
        if l.startswith(("#", "ref\t")):
            continue
        ref, tp, sp = l.rstrip("\n").split("\t")
        m = re.match(r"(\w+) (\d+):(\d+)", ref)
        k = gmap.get((m[1], int(m[2]), int(m[3]), int(sp)))
        if k:
            by[(m[1], int(m[2]), int(m[3]), k)].append(int(tp))
    occ, lex = [], {}; layer = f"align.py:links_grc_pos.tsv@{sha256_file(f)[:12]}"
    toks = {}
    for (b, c, v, k), ps in sorted(by.items()):
        if (b, c, v) not in text:
            continue
        if (b, c, v) not in toks:
            toks[(b, c, v)] = P.tok.tokens(text[(b, c, v)], exact=True)
        tk = toks[(b, c, v)]; ords = FA.ordinals(b, f"{b} {c}:{v}")
        if k not in ords:
            continue
        kind, o = ords[k]
        lexs = FA.index(b, "lexemes" if kind == "c" else "fn").get(f"{b} {c}:{v}", [])
        lx = lex_id("grc", lexs[o]) if o < len(lexs) else None
        ps = sorted(p for p in set(ps) if 0 <= p < len(tk))
        if not lx or not ps:
            continue
        form = nfc("".join((" … " if n and p > ps[n - 1] + 1 else " " if n else "") + tk[p] for n, p in enumerate(ps)))
        if lx not in lex:
            t = source.book("grc", b).get(k) or (None, None, None)
            lex[lx] = ("grc", lx.split(":")[1], t[0], t[1], t[2])
        occ.append((lx, form, f"{b} {c}:{v}", f"{kind}{o}", k, json.dumps(ps), "x", edition, layer, "words"))
    return occ, lex, {"links": len(occ)}


def find_layers(P, given):
    """[(folder, record)] of the layers to read: --layer, project.yaml words.layers, the align runs, the published one"""
    out = []
    dirs = list(given or []) or list((P.p.get("words") or {}).get("layers") or [])
    if not dirs:
        for rec in sorted(glob.glob(os.path.join(ROOT, "build", "words-align", P.name.replace("/", "_"), "*", "words-align.json"))):
            dirs += [d for d in glob.glob(os.path.join(os.path.dirname(rec), "compact", "*", "*", "*")) if os.path.isdir(d)]
    for d in dirs:
        d = d if os.path.isabs(d) else os.path.join(ROOT, d)
        if not os.path.isdir(d):
            raise SystemExit(f"no layer folder {d}")
        rec = {"route": "local run" if os.path.exists(os.path.join(d, "..", "..", "..", "..", "align-text-run.json")) else "layer",
               "dir": os.path.relpath(d, ROOT)}
        run = os.path.normpath(os.path.join(d, "..", "..", "..", "..", "align-text-run.json"))
        if os.path.exists(run):
            r = json.load(open(run, encoding="utf-8"))
            rec.update(run=os.path.relpath(run, ROOT), run_sha256=sha256_file(run),
                       aligner=f"{r.get('tool')} {r.get('version', {}).get('package')} {r.get('version', {}).get('git_commit', '')[:12]}")
            rec["layer"] = f"{os.path.basename(d)}@align-text:{sha256_file(run)[:12]}"
        out.append((d, rec))
    if not out and P.p.get("lexeme_aligner"):
        out.append(published_layer(P, P.p["lexeme_aligner"]))
    return out


def published_layer(P, layer):
    """a published layer of exactly our text (route a): its main files and, for compact-alignments, the manifest
    entry, downloaded into download/<dataset>/<i>/<iso>/<layer>/ (lang.py's cache)"""
    import lang
    iso = lang.iso3(P); ds = lang.dataset_of(layer)
    d = os.path.join(ROOT, "download", ds, iso[0], iso, layer)
    names = lang.layer_names(ds, iso, layer)
    import urllib.request
    for b, by in names.items():
        for h, path in by.items():
            f = os.path.join(d, os.path.basename(path))
            if not os.path.exists(f):
                req = urllib.request.Request(f"{lang.HF}/{ds}/resolve/main/{path}", headers={"User-Agent": "make-tanakh"})
                open(f, "wb").write(urllib.request.urlopen(req, timeout=120).read())
    return d, {"route": "published", "dataset": ds, "layer": layer, "dir": os.path.relpath(d, ROOT)}


def write_db(out, occ, lex, vocab, meta, keep=DEFAULT_KEEP, R=None):
    """words.db from occurrences [(lexeme, form, ref, src, key, positions, method, edition, layer, level)], lexeme info
    {id: (lang, strong, lemma, cls, type)}, vocab Counter((plain, BOOK, ch, edition)) and meta; written whole, then moved"""
    R = R or Respeller([])
    forms = {}
    for r in occ:
        forms.setdefault(r[1], len(forms) + 1)
    n_lex = collections.Counter(r[0] for r in occ); n_form = collections.Counter(r[1] for r in occ)
    pair = collections.defaultdict(lambda: [0, 0, set()])
    for r in occ:
        p = pair[(r[0], r[1])]; p[0] += 1; p[1] += r[6].isupper(); p[2].add(r[2].split()[0])
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    tmp = out + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)
    db = sqlite3.connect(tmp); db.executescript(SCHEMA)
    db.executemany("insert into lexeme values (?,?,?,?,?,?,?)", [(k, v[0], v[1], v[2], v[3], n_lex[k], v[4]) for k, v in lex.items()])
    db.executemany("insert into form values (?,?,?,?,?,?,?)",
                   [(i, f, f.lower(), bare(f.lower(), keep), len(tokens_of(f)), n_form[f], R(f.lower())) for f, i in forms.items()])
    db.executemany("insert into link values (?,?,?,?,?,?,?)", [(lx, forms[fm], n, s, ",".join(sorted(b)), n / n_lex[lx], n / n_form[fm])
                                                             for (lx, fm), (n, s, b) in pair.items()])
    db.executemany("insert into occ values (?,?,?,?,?,?,?,?,?,?)", [(r[0], forms[r[1]], *r[2:]) for r in occ])
    db.executemany("insert into vocab values (?,?,?,?,?,?)", [(w, bare(w, keep), b, c, n, ed) for (w, b, c, ed), n in vocab.items()])
    for ix in INDEXES:
        db.execute(ix)
    meta = dict(meta, format=str(FORMAT), lexemes=len(lex), forms=len(forms), links=len(occ), pairs=len(pair))
    db.executemany("insert into meta values (?,?)", [(k, v if isinstance(v, str) else json.dumps(v, ensure_ascii=False))
                                                     for k, v in meta.items()])
    db.commit(); db.close(); os.replace(tmp, out)
    return out


def build(pname, layers=None, eflomal=False, out=None):
    import langtools as LT
    P = LT.Project(pname); keep = keep_marks(P)
    verses = edition_verses(P); source = Source()
    found_layers = find_layers(P, layers)
    if not found_layers and not eflomal:
        raise SystemExit(f"{pname}: no alignment layer (words.py align, --layer DIR, project.yaml lexeme_aligner) "
                         "and no --eflomal")
    occ, lex, inputs, st = [], {}, [], collections.Counter()
    for d, rec in found_layers:
        used = False
        for ed, vs in verses.items():                     # the edition whose text the layer's files fingerprint
            o, lx, s = read_layer(d, vs, ed, source, rec)
            if o:
                occ += o; lex.update(lx); st.update(s); used = True
                inputs.append(dict(rec, edition=ed, books=s.get("books", 0), links=len(o)))
        if not used:
            print(f"  {rec['dir']}: no book of it is of exactly the style editions' text", file=sys.stderr)
    if eflomal:
        ed = P.p["style_from"][0]
        o, lx, s = eflomal_links(P, verses[ed], ed, source)
        have = {(r[0], r[2], r[5]) for r in occ}
        o = [r for r in o if (r[0], r[2], r[5]) not in have]
        occ += o; lex.update({k: v for k, v in lx.items() if k not in lex})
        inputs.append({"route": "eflomal (transitional: align.py's links, until a layer exists)", "edition": ed,
                       "layer": o[0][8] if o else "", "links": len(o)})
    vocab = collections.Counter()
    for ed, vs in verses.items():
        for b, rows in vs.items():
            for c, v, t in rows:
                for w in written_tokens(t):
                    vocab[(w.lower(), b, c, ed)] += 1
    rules = respell_rules(P); R = Respeller(rules, names_of(P, lex, occ))
    out = out or os.path.join(P.learn, "words.db")
    texts = {ed: hashlib.sha256("\n".join(f"{b} {c}:{v}\t{t}" for b in sorted(vs) for c, v, t in vs[b]).encode()).hexdigest()
             for ed, vs in verses.items()}
    meta = {"built": time.strftime("%Y-%m-%d %H:%M"), "project": pname, "inputs": inputs,
            "editions": texts, "keep_marks": [f"U+{ord(c):04X}" for c in keep], "respell": rules,
            "books skipped (not this text)": st.get("books skipped (not this text)", 0)}
    write_db(out, occ, lex, vocab, meta, keep, R)
    print(f"{pname}: {len(occ)} links, {len(lex)} lexemes, {len({r[1] for r in occ})} forms from {len(inputs)} layer(s) -> "
          f"{os.path.relpath(out, ROOT)}")
    for i in inputs:
        print(f"  {i['edition']}: {i.get('route')}: {i.get('layer')} ({i.get('links')} links)")
    return out


def names_of(P, lex=None, occ=None, con=None):
    """forms names are written with (left as they are by respelling): the store's name values and the corpus forms
    linked mostly to proper nouns"""
    import langtools as LT
    out = set()
    for fn in ("decisions.json", "observations.json"):
        f = os.path.join(P.profile, fn)
        if RG.exists(f):
            for e in RG.read(f).get("entries", []):
                if e.get("kind") == "name" and isinstance(e.get("value"), str):
                    out.update(w.lower() for w in written_tokens(e["value"]))
    c = collections.defaultdict(lambda: [0, 0])
    if con is not None:
        rows = con.execute("select f.plain, l.type from occ o join form f on f.id = o.form join lexeme l on l.id = o.lexeme")
    else:
        rows = ((r[1].lower(), (lex.get(r[0]) or (0, 0, 0, 0, None))[4]) for r in occ or ())
    for form, typ in rows:
        for w in tokens_of(form):
            c[w][0] += 1; c[w][1] += typ == "proper"
    out.update(w for w, (n, p) in c.items() if p * 2 > n)
    return out


# --- reading -----------------------------------------------------------------

def db_file(pname):
    from project import project_dir
    return os.path.join(project_dir(pname), "_learn", "words.db")


class Lexicon:
    """The corpus's forms per source lexeme, recounted from occ without the chapters skipped ({(BOOK, ch)}) and the
    books left out: .ok, .built, of(lang, strong), bridges(strong, direct), renderings(lang, strong), expected(lang,
    strong), .vocab (lower-case forms, Counter), .vocab_bare. Strong's numbers as the index writes them, with or without
    zeros; one without a homonym letter (grammar's tokens) takes every homonym of the number."""
    def __init__(self, path, skip=(), leave_out=(), keep=DEFAULT_KEEP):
        self.ok = os.path.exists(path); self.path = path
        self.n = collections.defaultdict(collections.Counter)          # lexeme id -> Counter(lower-case form)
        self.written = collections.defaultdict(collections.Counter)    # lower-case form -> Counter(form as written)
        self.digits = collections.defaultdict(set); self.lemma = {}; self.typ = {}; self.built = None
        self.vocab = collections.Counter(); self.vocab_bare = collections.Counter(); self.keep = keep
        self._bridge = None
        if not self.ok:
            return
        skip = {(b.upper(), int(c)) for b, c in skip}; leave_out = {b.upper() for b in leave_out}
        db = sqlite3.connect(path); self.db = db
        self.meta = dict(db.execute("select name, value from meta"))
        self.built = self.meta.get("built")
        forms = dict(db.execute("select id, form from form"))
        for lx, lem, typ in db.execute("select id, lemma, type from lexeme"):
            self.lemma[lx] = lem; self.typ[lx] = typ
            self.digits[re.sub(r"[a-z]$", "", lx)].add(lx)
        for lx, fm, ref in db.execute("select lexeme, form, ref from occ"):
            b, cv = ref.split(); ch = int(cv.split(":")[0])
            if b in leave_out or (b, ch) in skip:
                continue
            f = forms[fm]; pl = f.lower(); self.n[lx][pl] += 1; self.written[pl][f] += 1
        for pl, bb, b, ch, n in db.execute("select plain, bare, book, ch, n from vocab"):
            if b in leave_out or (b, ch) in skip:
                continue
            self.vocab[pl] += n; self.vocab_bare[bb] += n

    def ids(self, lang, strong):
        x = lex_id(lang, str(strong).split(":")[-1])
        if not x:
            return []
        return [x] if x[-1].isalpha() else sorted(self.digits.get(x) or {x})

    def counts(self, lang, strong):
        c = collections.Counter()
        for x in self.ids(lang, strong):
            c.update(self.n.get(x, {}))
        return c

    def shown(self, pl):
        return self.written[pl].most_common(1)[0][0] if self.written.get(pl) else pl

    def of(self, lang, strong):
        """([(form as written, share, n)] the TOP commonest with share >= MIN_SHARE, total links) or None"""
        c = self.counts(lang, strong)
        if not c:
            return None
        tot = sum(c.values())
        return [(self.shown(f), n / tot, n) for f, n in c.most_common(TOP) if n / tot >= MIN_SHARE], tot

    def bridge(self):
        """Hebrew lexeme id -> [(Greek lexeme id, share)] from orig/heb.sqlite's lxx table, best first"""
        if self._bridge is None:
            agg = collections.defaultdict(collections.Counter)
            p = os.path.join(ROOT, "orig", "heb.sqlite")
            if os.path.exists(p):
                for lx, g, n in sqlite3.connect(p).execute("select lexeme, greekstrong, n from lxx"):
                    a, b = lex_id("hbo", lx), lex_id("grc", g)
                    if a and b:
                        agg[a][b] += n
            self._bridge = {}
            for a, c in agg.items():
                tot = sum(c.values())
                self._bridge[a] = [(g, n / tot) for g, n in c.most_common() if n / tot >= MIN_SHARE and n >= BRIDGE_MIN][:TOP]
        return self._bridge

    def bridges(self, strong, direct):
        """the Greek equivalents of a Hebrew lexeme worth asking, given its number of direct links"""
        bs = []
        for x in self.ids("hbo", strong):
            bs += self.bridge().get(x, [])
        bs.sort(key=lambda r: -r[1])
        if direct >= DIRECT_ENOUGH or not bs:
            return []
        return [(g, p) for g, p in bs if p >= BRIDGE_REL * bs[0][1]]

    def renderings(self, lang, strong):
        """[(label, rows, total, weight)]: the lexeme's own forms (label None), then for a Hebrew lexeme its usual Greek
        equivalents (label = the Greek lemma, weight = the bridge's share)"""
        out = []; own = self.of(lang, strong)
        if own:
            out.append((None, own[0], own[1], 1.0))
        if lang == "hbo":
            for g, share in self.bridges(strong, own[1] if own else 0):
                x = self.of("grc", g)
                if x:
                    out.append((self.lemma.get(g) or g, x[0], x[1], share))
        return out

    def expected(self, lang, strong):
        """(every lower-case form the corpus uses for the lexeme and, for a Hebrew one, its usual Greek equivalents,
        Counter of those forms) or None when none of these lexemes has MIN_N links"""
        own = self.counts(lang, strong)
        cs = [own] + ([self.counts("grc", g) for g, _ in self.bridges(strong, sum(own.values()))] if lang == "hbo" else [])
        cs = [c for c in cs if sum(c.values()) >= MIN_N]
        if not cs:
            return None
        tot = collections.Counter()
        for c in cs:
            tot.update(c)
        return set(tot), tot


# --- the check ---------------------------------------------------------------

def store_entries(P):
    """decided term and formula entries (not superseded) of the store"""
    es = []
    for fn in ("decisions.json", "observations.json"):
        f = os.path.join(P.profile, fn)
        if RG.exists(f):
            es += RG.read(f).get("entries", [])
    gone = {e.get("supersedes") for e in es if e.get("supersedes")}
    return [e for e in es if e.get("kind") in ("term", "formula") and e.get("status") == "decided" and e["id"] not in gone
            and isinstance(e.get("value"), str)]


def entry_lexemes(e, lemmas):
    """{(lang, lexeme id)} a decided entry names: H639 / G3709 in `source` or the id, else a single Hebrew or Greek
    source word looked up as a lemma (content words only); a phrase names none"""
    for s in (e.get("source") or "", e["id"].split(":", 1)[-1]):
        m = re.fullmatch(r"([HG])0*(\d+)([a-z]?)", s.strip())
        if m:
            lang = "hbo" if m[1] == "H" else "grc"
            return {(lang, f"{lang}:{m[2]}{m[3]}")}
    s = nfc(e.get("source") or "").strip()
    if e.get("kind") == "formula" or not s or re.search(r"[\s\u05BE]", s):   # a formula is a phrase: only a number names its word
        return set()
    return lemmas.get(s, set())


def source_lemmas():
    """{lemma: {(lang, lexeme id)}} of the content words of orig/heb.sqlite and orig/grc.sqlite"""
    out = collections.defaultdict(set)
    h = os.path.join(ROOT, "orig", "heb.sqlite"); g = os.path.join(ROOT, "orig", "grc.sqlite")
    if os.path.exists(h):
        for lem, lx in sqlite3.connect(h).execute("select distinct lemma, lexeme from tokens where class in ('noun','verb','adj')"):
            if lex_id("hbo", lx):
                out[nfc(lem)].add(("hbo", lex_id("hbo", lx)))
    if os.path.exists(g):
        for lem, s in sqlite3.connect(g).execute("select distinct lemma, strong from tokens where class in ('noun','verb','adj')"):
            if lex_id("grc", s):
                out[nfc(lem)].add(("grc", lex_id("grc", s)))
    return out


def same_word(w, d, keep=DEFAULT_KEEP):
    """a decided value's word and a draft word: equal, equal without marks, or one stem (an inflected form; compared
    without any marks, so that an umlaut plural, Magd / Mägd, is the same word)"""
    if w == d or bare(w, keep) == bare(d, keep):
        return True
    w, d = bare(w, ()), bare(d, ())
    k = 0
    while k < min(len(w), len(d)) and w[k] == d[k]:
        k += 1
    if min(len(w), len(d)) >= 4 and k >= max(4, max(len(w), len(d)) - 2):
        return True
    if len(w) >= 4 and w in d:                                       # a compound: Onyxsteine for Stei, Alltagsarbeit
        return True
    stem = w[:max(4, len(w) - 2)]
    return len(w) >= 5 and stem in d and len(d) - len(stem) <= 4     # a prefixed form: gsägnet for sägne


def value_words(value, common, drop_script=None):
    """the words of a value form a verse must have: those not among the corpus's commonest (common: {form: rank}),
    else its rarest one (der HERR -> herr); drop_script: leave out words in that script (a Hebrew word in a value)"""
    toks = [w.lower() for w in written_tokens(re.sub(r"<[^<>]*>|\([^()]*\)", " ", value))
            if not (drop_script and any(drop_script in unicodedata.name(c, "") for c in w))]
    return [w for w in toks if w not in common] or sorted(toks, key=lambda w: -common.get(w, 0))[:1]


def value_forms(value):
    """a value's accepted forms: a list written `a; b`, `a / b` or `a, b` is one form each"""
    return [x.strip() for x in re.split(r"\s*[;/,:]\s*", value) if x.strip()]


def in_scope(scope, code, ch):
    """does an entry's scope hold for a chapter? None or "ALL": everywhere; a book ("EXO"), a chapter ("EXO 21") or a
    chapter range ("EXO 21-23"), or a list of them; a feature bundle (a dict) is not a place: it holds"""
    if scope in (None, "", "ALL") or isinstance(scope, dict):
        return True
    for s in scope if isinstance(scope, list) else [scope]:
        m = re.fullmatch(r"([1-3A-Za-z]{3})(?:\s+(\d+)(?:-(\d+))?)?", str(s).strip())
        if m and m[1].lower() == code and (not m[2] or int(m[2]) <= ch <= int(m[3] or m[2])):
            return True
    return False


def id_scope(eid):
    """the book an entry's id names at its end (`term:alah_deu`, `term:ets-est`): drafting agents name a decision
    made for one book so; taken as its scope until the entry has a `scope` of its own"""
    m = re.search(r"[_-]([0-9a-z]{3})$", eid)
    return m[1].upper() if m and m[1] in BY_CODE else None


def chapter_source(code, ch):
    """{verse: [(ordinal, lexeme id, lemma, class, type, key)]} of the chapter's content tokens (the index's numbering:
    Hebrew in the Tanakh)"""
    import full_align as FA
    B = code.upper(); lang = "grc" if BY_CODE[code][2] == "nt" else "hbo"
    L, K = FA.index(B, "lexemes"), FA.index(B, "keys")
    src = Source().book(lang, B); out = collections.defaultdict(list)
    for r, lexs in L.items():
        c, v = (int(x) for x in r.split()[1].split(":"))
        if c != ch:
            continue
        for o, s in enumerate(lexs):
            k = (K.get(r) or [""] * len(lexs))[o] if o < len(K.get(r) or []) else ""
            lem, cls, typ = src.get(k.split("+")[0]) or (None, None, None)
            out[v].append((o, lex_id(lang, s), lem, cls, typ, k))
    return lang, out


def bsb_verse(P, code, ch, v):
    import langtools as LT, vrs
    c, vv = vrs.to_bsb(code, ch, v) if BY_CODE[code][2] == "ot" else (ch, v)
    if vv == "title":
        c, vv = ch, v
    f = os.path.join(ROOT, P.assist_dir(code), f"{code}{c:03d}.txt")
    if not os.path.exists(f):
        return ""
    if f not in _BSB:
        _BSB[f] = LT.verses_of(f)
    return _BSB[f].get((c, vv), "")


_BSB = {}


def review(pname, code, ch, path=None, respell=None, figure=None, every=False, records=None, respell_open=False):
    """REVIEW lines for chapter_check.py (never FIX in this version); figure: a dict that gets the counts;
    respell: a rules file in place of the store's; every: list expected forms of any share; records: a list that gets
    one dict per line (class, verses, draft form, expected form, counts)"""
    rec = (lambda **k: records.append(dict(k, book=code, ch=ch))) if records is not None else (lambda **k: None)
    import langtools as LT, full_align as FA
    from project import project_dir
    p = db_file(pname)
    if not os.path.exists(p):
        return []
    P = LT.Project(pname); keep = keep_marks(P)
    L = Lexicon(p, skip={(code, ch)}, keep=keep)
    R = Respeller(respell_rules(P, respell, LIVE_SPELLING + (("open",) if respell_open else ())), names_of(P, con=L.db))
    d = os.path.join(project_dir(pname), code); path = path or os.path.join(d, f"{code}{ch:03d}.txt")
    al = os.path.join(d, f"{code}{ch:03d}.align")
    rows = FA.read_chapter(al)[1] if os.path.exists(al) and os.path.abspath(path) == os.path.join(os.path.abspath(d), f"{code}{ch:03d}.txt") else {}
    verses = FA.draft_texts(path)
    lang, S = chapter_source(code, ch)
    common = {w: i for i, (w, _) in enumerate(L.vocab.most_common(FUNCTION_TOP))}
    lemmas = source_lemmas(); entries = []; st = collections.Counter()
    script = None if (P.p.get("language") or "").split("-")[0] in ("he", "heb", "hbo") else "HEBREW"
    for e in store_entries(P):
        lx = {x for l, x in entry_lexemes(e, lemmas) if l == lang}
        if lx:
            vals = value_forms(e["value"]) + [x for a in e.get("alternatives") or [] if isinstance(a, dict)
                                              and a.get("status") in ("preferred", "admitted") and a.get("value")
                                              for x in value_forms(a["value"])]
            if len(vals) > MAX_FORMS:              # a list of a chapter's forms, not a decided rendering
                st["term: entries with more than MAX_FORMS forms (not checked)"] += 1; continue
            vals = [x for x in (value_words(v, common, script) for v in vals) if x]
            if vals:
                entries.append((e, lx, vals))
    by_lex = collections.defaultdict(list)
    for e, lx, vals in entries:
        for x in lx:
            by_lex[x].append((e, vals))
    # the corpus in the project's spelling
    proj = collections.Counter(); proj_bare = collections.Counter(); changed = {}
    for w, n in L.vocab.items():
        r = R(w); proj[r] += n; proj_bare[bare(r, keep)] += n
        if r != w:
            changed[w] = r
    vp = (P.p.get("words") or {}).get("variant_pairs")       # the project's letter pairs replace the default ones
    pairs = PAIRS if vp is None else [tuple(x) for x in vp]
    out_term, out_exp, sp, listed = [], [], collections.defaultdict(list), set()
    term_groups = collections.defaultdict(list)    # one line per decided entry and draft form, its verses
    proper = set(R.names)                          # names: never a spelling finding (the names check has them)
    for v, text in verses:
        toks = written_tokens(text); low = [t.lower() for t in toks]; words = set(low)
        main = FA.parse(rows[v][0]) if v in rows else {}
        terms_here = set()
        for o, lx, lem, cls, typ, key in S.get(v, []):
            live = []                              # the entries on this word whose sense the BSB verse shows
            for e, vals in by_lex.get(lx, []):
                if not in_scope(e.get("scope") or id_scope(e["id"]), code, ch):
                    st["term: out of the entry's scope"] += 1
                    continue
                ws = [w for w in e.get("words") or [] if re.fullmatch(r"[A-Za-z][A-Za-z' -]+", w) and w.lower() not in STOP_EN]
                bsb = bsb_verse(P, code, ch, v).lower() if ws else ""
                if ws and not any(re.search(rf"\b{re.escape(w.lower())}", bsb) for w in ws):
                    st["term: other sense (the entry's BSB words not in the verse)"] += 1
                    continue
                live.append((e, vals))
            if not live or lx in terms_here:
                continue
            st["term checked"] += 1; terms_here.add(lx)
            if any(all(any(same_word(w, t, keep) for t in low) for w in val) for e, vals in live for val in vals):
                continue
            x = L.expected(lang, lx)                 # an inflected form the corpus writes for the word: lost for lose
            cf = {t for f in (x[0] if x else ()) for t in tokens_of(f)}
            if any(t in cf and any(t[:3] == w[:3] for e, vals in live for val in vals for w in val) for t in low):
                continue
            st["term missed"] += 1
            if v in rows and not main.get(o) and not every:   # the .align links no draft word to it: counted, not listed
                st["term: not linked in the .align (not listed)"] += 1; continue
            here = " ".join(toks[i] for i in main.get(o, []) if i < len(toks)) or "-"
            exp = L.of(lang, lx)
            cor = f"; corpus: {', '.join(f'{f} {n}x' for f, _, n in exp[0])}" if exp else ""
            dec = "; ".join(f"{e['id']} “{e['value'][:60]}{'…' if len(e['value']) > 60 else ''}”" for e, _ in live)
            term_groups[(lem, here, dec, cor)].append(v)
            rec(cls="term", verses=[v], draft=here, expected=" / ".join(e["value"] for e, _ in live), ids=[e["id"] for e, _ in live],
                lemma=lem, corpus=[(f, n) for f, _, n in exp[0]] if exp else [])
        for o, lx, lem, cls, typ, key in S.get(v, []):
            if cls not in CONTENT or typ == "proper" or not lx or lx in terms_here:
                continue
            x = L.expected(lang, lx)
            if not x:
                continue
            forms, cnt = x; st["checkable"] += 1
            if any(found(R(f), words) or found(f, words) for f in forms) or any(
                    all(any(same_word(w, d, keep) for d in low) for w in tokens_of(R(f))) for f in forms):
                st["found"] += 1; continue
            top, n = cnt.most_common(1)[0]; tot = sum(cnt.values())
            if (lem, v) in listed:
                continue
            if v in rows and not main.get(o) and not every:
                st["expected: not linked in the .align (not listed)"] += 1; continue
            direct = sum(L.counts(lang, lx).values())   # a line needs the lexeme's own links; bridged ones give the figure only
            if every or n / tot >= LIST_SHARE and tot >= LIST_MIN and direct >= LIST_MIN:
                listed.add((lem, v))
                here = " ".join(toks[i] for i in main.get(o, []) if i < len(toks)) or "-"
                rec(cls="expected", verses=[v], draft=here, expected=L.shown(top) if R(top) == top else R(top), n=n, total=tot, lemma=lem)
                out_exp.append(f"expected {ch}:{v}: {lem} usually “{L.shown(top) if R(top) == top else R(top)}” "
                               f"({n}/{tot}); the draft has “{here}”")
        for o, lx, lem, cls, typ, key in S.get(v, []):
            if typ in ("proper", "gentilic"):
                proper.update(low[i] for i in main.get(o, []) if i < len(low))
        for t in low:
            sp[t].append(v)
    out_sp = []
    import modes
    spelling = (P.p.get("words") or {}).get("spelling", modes.mode(P.p)["spell_check"])
    for w, vs in sorted(sp.items(), key=lambda x: (-len(x[1]), x[0])):
        if w.isdigit() or len(w) < 2 or w in proper:
            continue
        where = ", ".join(f"{ch}:{v}" for v in sorted(set(vs))[:4]) + (" …" if len(set(vs)) > 4 else "")
        k = f"{len(vs)}x " if len(vs) > 1 else ""
        if w in changed and w not in proj:
            st["project spelling"] += 1
            rec(cls="project spelling", verses=sorted(set(vs)), draft=w, expected=changed[w], n=len(vs), corpus_n=L.vocab[w])
            out_sp.append(f"project spelling {where}: {k}“{w}” is the corpus's spelling; the project writes “{changed[w]}”")
            continue
        if not spelling:                         # a known language: the corpus's other spellings are mostly other words
            continue
        if w in proj:
            c = proj[w]
            if c <= RARE_MAX:
                var = corpus_variant(w, proj_bare, keep, pairs, max(RARE_MIN, RARE_RATIO * c))
                if var and var[1] == "diphthong":    # Böim (1x) is not Bim: a rare form's diphthong is the word's
                    var = None
                if var:
                    st["spelling (rare)"] += 1
                    rec(cls="spelling (rare)", verses=sorted(set(vs)), draft=w, expected=var[0], n=len(vs), corpus_n=c, variant_n=var[2], rule=var[1])
                    out_sp.append(f"spelling {where}: {k}“{w}” ({c}x in the corpus) — the corpus writes “{var[0]}” "
                                  f"{var[2]}x ({var[1]}, rare)")
            continue
        b = bare(w, keep)
        if proj_bare.get(b):
            alts = [x for x in proj if bare(x, keep) == b][:3]
            st["marks"] += 1
            rec(cls="marks", verses=sorted(set(vs)), draft=w, expected=alts[0] if alts else "", n=len(vs), corpus_n=0, variant_n=proj[alts[0]] if alts else 0)
            out_sp.append(f"marks {where}: {k}“{w}” — the corpus writes {', '.join(f'“{a}” {proj[a]}x' for a in alts)}")
            continue
        var = corpus_variant(w, proj_bare, keep, pairs)
        if var:
            st["spelling"] += 1
            rec(cls="spelling", verses=sorted(set(vs)), draft=w, expected=var[0], n=len(vs), corpus_n=0, variant_n=var[2], rule=var[1])
            out_sp.append(f"spelling {where}: {k}“{w}” (0x in the corpus) — the corpus writes “{var[0]}” {var[2]}x ({var[1]})")
    for (lem, here, dec, cor), vs in term_groups.items():
        where = ", ".join(f"{ch}:{v}" for v in vs[:6]) + (" …" if len(vs) > 6 else "")
        out_term.append(f"term {where}: {f'{len(vs)}x ' if len(vs) > 1 else ''}“{here}” for {lem} (decided: {dec}{cor})")
    if figure is not None:
        figure.update(st); figure["term lines"] = len(out_term); figure["expected lines"] = len(out_exp)
    return out_term + out_sp + out_exp


def figure_line(f):
    k = f.get("checkable", 0)
    return (f"words: {f.get('found', 0)}/{k} source content words with one of the corpus's forms in the verse"
            f" ({100 * f.get('found', 0) / max(k, 1):.0f}%); decided terms {f.get('term checked', 0) - f.get('term missed', 0)}"
            f"/{f.get('term checked', 0)}")


# --- align (route b) ---------------------------------------------------------

def align(pname, edition=None, out=None, aligner=None, data=None, fetch=False, force=False):
    """lexeme-aligner's align-text on a style edition's text, here: no --jev, so nothing of the text leaves the
    machine; writes only into OUT (default build/words-align/<project>/<edition>/) and records the run"""
    import langtools as LT
    P = LT.Project(pname); verses = edition_verses(P)
    edition = edition or P.p["style_from"][0]
    if edition not in verses:
        raise SystemExit(f"{edition} is not a style edition of {pname}")
    exe = aligner or os.environ.get("LEXEME_ALIGNER") or (P.p.get("words") or {}).get("aligner") or \
        os.path.join(ROOT, "tools", "lexeme-aligner", ".venv", "bin", "lexeme-aligner")
    exe = os.path.abspath(exe)                      # it runs from the aligner's checkout below
    if not os.path.exists(exe):
        raise SystemExit(f"no lexeme-aligner at {exe} (--aligner, $LEXEME_ALIGNER or project.yaml words.aligner)")
    import lang
    iso = lang.iso3(P)
    out = os.path.abspath(out or os.path.join(ROOT, "build", "words-align", pname.replace("/", "_"), edition))
    data = os.path.abspath(data or os.path.join(os.path.dirname(out), "aligner-data"))
    inp = os.path.join(os.path.dirname(out), f"input-{edition}"); os.makedirs(inp, exist_ok=True)
    txt = os.path.join(inp, f"{iso}_{edition}.txt")
    with open(txt, "w", encoding="utf-8") as w:
        for b in sorted(verses[edition], key=lambda b: list(BY_CODE).index(b.lower())):
            for c, v, t in verses[edition][b]:
                if t.strip():
                    w.write(f"{b} {c}:{v} {t}\n")
    cwd = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(exe))))   # the checkout: settings are read from it
    steps = []
    if fetch:
        cmd = [exe, "fetch-inputs", "--iso", iso, "--data", data]
        steps.append({"cmd": cmd, "rc": subprocess.run(cmd, cwd=cwd).returncode})
    ed_id = re.sub(r"[^a-z0-9_]", "_", f"{iso}_{edition}".lower())
    cmd = [exe, "align-text", "--text", txt, "--edition", ed_id, "--iso", iso, "--out", out, "--data", data] + (["--force"] if force else [])
    t0 = time.time(); rc = subprocess.run(cmd, cwd=cwd).returncode
    steps.append({"cmd": cmd, "rc": rc, "seconds": round(time.time() - t0)})
    rec = {"project": pname, "edition": edition, "text": os.path.relpath(txt, ROOT), "text_sha256": sha256_file(txt),
           "steps": steps, "jev": False, "date": time.strftime("%Y-%m-%d %H:%M")}
    os.makedirs(out, exist_ok=True)
    json.dump(rec, open(os.path.join(out, "words-align.json"), "w", encoding="utf-8"), indent=1)
    print(f"align-text {'ok' if rc == 0 else f'failed ({rc})'} in {steps[-1]['seconds']} s -> {os.path.relpath(out, ROOT)}")
    if rc == 0:
        print(f"  then: python3 scripts/words.py build {pname}" + ("" if out.startswith(os.path.join(ROOT, "build", "words-align"))
                                                                     else f" --layer {glob.glob(os.path.join(out, 'compact', '*', '*', '*'))[0]}"))
    return rc


def stats(pname):
    con = sqlite3.connect(db_file(pname)); q = lambda s: con.execute(s).fetchone()[0]
    res = {"lexemes": q("select count(*) from lexeme"), "forms": q("select count(*) from form"),
           "links": q("select count(*) from occ"), "rated high": round(q("select sum(n_strong)*1.0/sum(n) from link") or 0, 3)}
    for lang in ("grc", "hbo"):
        n = q(f"select count(*) from lexeme where lang='{lang}' and n>=3")
        if n:
            res[f"{lang}: lexemes with 3+ links, top form's share (median)"] = round(q(
                f"select share from (select max(l.share) share from link l join lexeme x on x.id=l.lexeme where x.lang='{lang}'"
                f" and x.n>=3 group by l.lexeme) order by share limit 1 offset {n // 2}"), 3)
    res.update({k: json.loads(v) if v[:1] in "[{" else v for k, v in con.execute("select name, value from meta")
                if k in ("format", "built", "inputs", "keep_marks")})
    print(json.dumps(res, ensure_ascii=False, indent=1))


def show(pname, lexeme):
    m = re.fullmatch(r"(hbo:|grc:|H|G)?0*(\d+[a-z]?)", lexeme)
    lang = "grc" if (m[1] or "").startswith(("G", "grc")) else "hbo"
    L = Lexicon(db_file(pname))
    for label, rows, tot, w in L.renderings(lang, m[2]):
        print(f"{label or f'{lang}:{m[2]}'} ({tot} links{'' if label is None else f', bridge {w:.2f}'}): "
              + ", ".join(f"{f} {n}x ({s:.0%})" for f, s, n in rows))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("align", "build", "check", "stats", "show"))
    ap.add_argument("project"); ap.add_argument("rest", nargs="*")
    ap.add_argument("--layer", action="append"); ap.add_argument("--eflomal", action="store_true")
    ap.add_argument("--out"); ap.add_argument("--edition"); ap.add_argument("--aligner"); ap.add_argument("--data")
    ap.add_argument("--fetch", action="store_true"); ap.add_argument("--force", action="store_true")
    ap.add_argument("--respell", help="a JSON file of spelling entries (the store's shape) in place of the store's, to try rules")
    ap.add_argument("--respell-open", action="store_true", help="also apply the open (proposed) spelling entries")
    ap.add_argument("--all", action="store_true", help="check: list expected forms of any share")
    a = ap.parse_args()
    if a.cmd == "align":
        sys.exit(align(a.project, a.edition, a.out, a.aligner, a.data, a.fetch, a.force))
    if a.cmd == "build":
        build(a.project, a.layer, a.eflomal, a.out)
    elif a.cmd == "stats":
        stats(a.project)
    elif a.cmd == "show":
        show(a.project, a.rest[0])
    else:
        code, ch = a.rest[0], int(a.rest[1])
        if not os.path.exists(db_file(a.project)):
            sys.exit(f"{a.project}: no words.db (python3 scripts/words.py build {a.project})")
        f = {}
        lines = review(a.project, code, ch, respell=a.respell, figure=f, every=a.all, respell_open=a.respell_open)
        print(f"{a.project} {code} {ch}: {len(lines)} to review; {figure_line(f)}")
        for l in lines:
            print(f"  REVIEW  {l}")


if __name__ == "__main__":
    main()
