#!/usr/bin/env python3
"""The word DB (scripts/words.py, docs/word-db.md) on a synthetic fixture: tokens as written in step with the
published tokenizer, a compact layer read only for exactly its text, the holdout recount from occ, the Septuagint
bridge, the spelling variants, the respelling rules (a toy rule) and the decided-term matching. No edition text, no
network. Run: python3 scripts/tests/test_words.py (or pytest)."""
import collections, json, os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import full_align as FA  # noqa: E402
import words as W  # noqa: E402

# a toy NT: two verses of "JHN" in a made-up language
VERSES = {"JHN": [(1, 1), (1, 2), (2, 1)]}
TEXT = [(1, 1, "Am Aafang isch ds Wort gsy."), (1, 2, "Ds Wort isch bi Gott gsy, ds Wort."), (2, 1, "Ds Wort isch Gott.")]
INDEX = {"lexemes": {"JHN 1:1": ["746", "3056"], "JHN 1:2": ["3056", "2316"], "JHN 2:1": ["3056", "2316"]},
         "keys": {"JHN 1:1": ["k1", "k2"], "JHN 1:2": ["k3", "k4"], "JHN 2:1": ["k5", "k6"]}}


def fake_index(book, kind):
    return INDEX.get(kind, {})


class FakeSource:
    def book(self, lang, book):
        return {"k1": ("ἀρχή", "noun", "common"), "k2": ("λόγος", "noun", "common"), "k3": ("λόγος", "noun", "common"),
                "k4": ("θεός", "noun", "common"), "k5": ("λόγος", "noun", "common"), "k6": ("θεός", "noun", "common")}


def layer(tmp, text=TEXT):
    """a compact edition folder as align-text writes it: OUT/compact/<i>/<iso>/<edition>/ + manifest"""
    d = os.path.join(tmp, "compact", "x", "xxx", "xxx_toy")
    os.makedirs(d)
    fp = FA.text_fingerprint(text)[0][:8]
    # JHN 1:1 "Am Aafang isch ds Wort gsy": 746 -> Aafang (1), 3056 -> Wort (4); JHN 1:2: 3056 -> Wort 1 and 7 (scattered),
    # 2316 -> Gott (4); JHN 2:1: 3056 -> Wort (1), 2316 -> Gott (3)
    json.dump(["0:1 1:4", "0:1,7 1:4", "0:1 1:3"], open(os.path.join(d, f"JHN_{fp}.json"), "w"))
    json.dump({"method": ["EE", "eG", "EE"]}, open(os.path.join(d, f"JHN_{fp}.meta.json"), "w"))
    json.dump({"languages": {"xxx": {"editions": {"xxx_toy": {"versification": "eng"}}}}},
              open(os.path.join(tmp, "compact", "manifest.json"), "w"))
    return d


def test_written_tokens_follow_the_published_tokenizer():
    s = "Ndǿgo, eín-qa 12 Wält’s"
    ws = W.written_tokens(s)
    assert len(ws) == len(FA.tokenize(s)) and ws[0] == "Ndǿgo" and ws[1] == "eín"
    assert [W.bare(w.lower()) for w in ws][:2] == ["ndøgo", "ein"]           # tone marks off, ø is a letter
    assert W.bare("Härde".lower()) == "härde"                                 # the diaeresis is kept by default


def test_ids():
    assert W.lex_id("hbo", "0639") == "hbo:639" and W.lex_id("hbo", "2050b") == "hbo:2050b" and W.lex_id("grc", "26") == "grc:26"
    assert W.heb_lexeme("H639") == "0639" and W.heb_lexeme("hbo:2050b") == "2050b"


def build_fixture(tmp):
    FA.index = fake_index
    d = layer(tmp)
    occ, lex, st = W.read_layer(d, VERSES_T, "toy", FakeSource(), {"layer": "xxx_toy@test"})
    vocab = collections.Counter()
    for c, v, t in TEXT:
        for w in W.written_tokens(t):
            vocab[(w.lower(), "JHN", c, "toy")] += 1
    p = os.path.join(tmp, "words.db")
    W.write_db(p, occ, lex, vocab, {"built": "test"})
    return p, occ, st


VERSES_T = {"JHN": TEXT}


def test_layer_is_read_for_its_text_only():
    with tempfile.TemporaryDirectory() as tmp:
        p, occ, st = build_fixture(tmp)
        assert st["books"] == 1 and len(occ) == 6
        forms = collections.Counter((r[0], r[1]) for r in occ)
        assert forms[("grc:3056", "Wort")] == 2 and forms[("grc:3056", "Wort … Wort")] == 1
        assert {r[6] for r in occ} == {"E", "e", "G"} and all(r[7:] == ("toy", "xxx_toy@test", "words") for r in occ)
        other = [(1, 1, "Am Aafang isch ds Wort gsy!"), (1, 2, "Ds Wort isch bi Gott gsy."), (2, 1, "Ds Wort isch Gott.")]
        o2, _, st2 = W.read_layer(os.path.dirname(p) + "/compact/x/xxx/xxx_toy", {"JHN": other}, "toy", FakeSource(), {})
        assert o2 == [] and st2["books skipped (not this text)"] == 1       # another text: no file, nothing read


def test_recount_leaves_out_the_checked_chapters():
    with tempfile.TemporaryDirectory() as tmp:
        p, _, _ = build_fixture(tmp)
        L = W.Lexicon(p)
        assert L.of("grc", "3056")[1] == 3 and L.of("grc", "2316")[0][0][0] == "Gott"
        H = W.Lexicon(p, skip={("JHN", 2)})
        assert H.of("grc", "3056")[1] == 2 and H.vocab["gott"] == 1 and L.vocab["gott"] == 2
        assert W.Lexicon(p, leave_out={"JHN"}).of("grc", "3056") is None
        assert L.expected("grc", "3056")[0] == {"wort", "wort … wort"}
        assert L.expected("grc", "746") is None                              # one link: not checkable (MIN_N)


def test_bridge_tiers():
    with tempfile.TemporaryDirectory() as tmp:
        p, _, _ = build_fixture(tmp)
        L = W.Lexicon(p)
        L._bridge = {"hbo:1697": [("grc:3056", 0.6), ("grc:4487", 0.25)], "hbo:430": [("grc:2316", 0.9)]}
        assert L.bridges("1697", 0) == [("grc:3056", 0.6)]                    # under half the best's share: dropped
        assert L.bridges("1697", W.DIRECT_ENOUGH) == []                       # enough direct links: no bridge
        assert L.expected("hbo", "1697")[0] == {"wort", "wort … wort"}
        assert [r[0] for r in L.renderings("hbo", "430")] == [None] or L.renderings("hbo", "430")[0][0] in ("θεός", "grc:2316")


def test_spelling_variants():
    counts = collections.Counter({"useggange": 19, "ga": 211, "blybe": 60, "härde": 5, "darbbracht": 3})
    assert W.corpus_variant("usegange", counts)[:2] == ("useggange", "double/single")
    assert W.corpus_variant("gah", counts)[:2] == ("ga", "long/short vowel")
    assert W.corpus_variant("blibe", counts)[:2] == ("blybe", "y/i")
    assert W.corpus_variant("herde", counts)[:2] == ("härde", "ä/e")
    assert W.corpus_variant("darbracht", counts)[0] == "darbbracht"
    assert W.corpus_variant("darbracht", collections.Counter({"darbbracht": 1})) is None    # once is not enough
    assert W.corpus_variant("zeche", counts) is None


def spelling(i, frm, to, status="decided", order=1, **ctx):
    return {"id": f"spelling:{i}", "kind": "spelling", "status": status, "value": f"{frm} → {to}", "from": frm, "to": to,
            "context": ctx, "exceptions": ["phalanx"], "order": order, "said": f"{frm} is written {to}"}


def test_respelling_toy_rule():
    store = {"entries": [spelling("ph", "ph", "f"), spelling("old", "x", "y", status="superseded"),
                         spelling("open", "th", "t", status="open", order=2),
                         spelling("final-e", "e", "", order=3, before="[^aeiou]", after="$", unless={"before": "^.", "after": "$"})]}
    rules = W.spelling_rules(store)
    assert [r["id"] for r in rules] == ["spelling:ph", "spelling:final-e"]               # decided only, in order
    assert [r["id"] for r in W.spelling_rules(store, ("decided", "open"))][1] == "spelling:open"
    assert [r["id"] for r in W.spelling_rules(dict(store, orthography={"respell": ["spelling:final-e", "spelling:ph"]}))] == \
        ["spelling:final-e", "spelling:ph"]                                                # orthography.respell orders them
    R = W.Respeller(rules, names=["philippe"])
    assert R("prophete") == "profet" and R("phalanx") == "phalanx" and R("philippe") == "philippe"
    assert R("me") == "me"                                       # unless: a two-letter word keeps its e
    assert R("prophete … phalanx") == "profet … phalanx" and not W.Respeller([])
    assert W.Respeller([])("prophet") == "prophet"


def test_decided_terms():
    assert W.same_word("töubi", "töubi") and W.same_word("sägne", "gsägnet") and W.same_word("gott", "gottes")
    assert not W.same_word("töubi", "zorn")
    assert W.value_forms("Sklav / Sklavin / Sklave") == ["Sklav", "Sklavin", "Sklave"]
    lem = {"אַף": {("hbo", "hbo:639"), ("hbo", "hbo:637")}}
    assert W.entry_lexemes({"id": "term:H639", "source": "אַף"}, lem) == {("hbo", "hbo:639")}
    assert W.entry_lexemes({"id": "term:anger", "source": "אַף"}, lem) == lem["אַף"]
    assert W.entry_lexemes({"id": "formula:x", "source": "נשׂא קול"}, lem) == set()
    assert W.value_words("der HERR", {"der": 0}) == ["herr"]
    assert W.value_words("der HERR", {"der": 0, "herr": 30}) == ["herr"]          # all common: the rarest word
    assert W.value_forms("Guld, Silber und Bronze; Öl") == ["Guld", "Silber und Bronze", "Öl"]


if __name__ == "__main__":
    for name, f in list(globals().items()):
        if name.startswith("test_"):
            f()
    assert W.in_scope(None, "exo", 21) and W.in_scope("ALL", "gen", 1) and W.in_scope(["EXO 21-23", "LEV"], "exo", 22)
assert W.in_scope("LEV", "lev", 5) and not W.in_scope(["EXO 21-23"], "exo", 24) and not W.in_scope("EXO", "gen", 1)
R = W.Respeller([{"from": "l", "to": "u", "context": {"after": "[^aeiou]|$"}, "exceptions": ["altar"]}])
assert R("altar") == "altar" and R("brandopferaltar") == "brandopferaltar" and R("wält") == "wäut" and R("altarwält") == "altarwäut"
assert W.id_scope("term:alah_deu") == "DEU" and W.id_scope("term:ets-est") == "EST" and W.id_scope("term:H639") is None
assert W.id_scope("term:H5650_slave_law") is None
print("ok")
