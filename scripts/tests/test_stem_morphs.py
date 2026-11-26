#!/usr/bin/env python3
"""Regression test: the stem's own morphology. An infix with `site: after_onset` (after the stem's consonants before its
first vowel; a vowel-initial stem: before it) and the reduplicated syllable (slot redup, `pattern` CV | CVC | full),
taken off the stem the prefixes and suffixes leave, only where the root is attested; every word rebuilds; a store
without them splits as before (the default site is after_prefix); the model text decodes back exactly. Synthetic store
(Tagalog verbs, Schachter & Otanes 1972, ch. 5), no project files. Run: python3 scripts/tests/test_stem_morphs.py."""
import os, sys, types
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "nllb"))
import morphs  # noqa: E402
import model_text  # noqa: E402

WORDS = ("sulat sumulat sumusulat susulat sinulat sinusulat isinulat sinulatan nagsusulat umalis inalis alis kinain "
         "kain kumain susulatin sulatan bata lumang").split()
AFFIXES = [dict(id="m:i-", slot="prefix", form="i-", host="verb"), dict(id="m:nag-", slot="prefix", form="nag-", host="verb"),
           dict(id="m:-an", slot="suffix", form="-an", host="verb"), dict(id="m:-in", slot="suffix", form="-in", host="verb")]
STEM = [dict(id="m:-um-", slot="infix", form="-um-", site="after_onset", host="verb", value="AV"),
        dict(id="m:-in-", slot="infix", form="-in-", site="after_onset", host="verb", value="PFV"),
        dict(id="m:redup.cv", slot="redup", pattern="CV", site="before_stem", host="verb", value="IPFV/CTP")]
EXPECT = {"sumulat": "s / -um- / ulat", "sumusulat": "s* / -um- / u* / sulat", "susulat": "su* / sulat",
          "sinulat": "s / -in- / ulat", "sinusulat": "s* / -in- / u* / sulat", "isinulat": "i- / s / -in- / ulat",
          "sinulatan": "s / -in- / ulat / -an", "nagsusulat": "nag- / su* / sulat", "umalis": "-um- / alis",
          "inalis": "-in- / alis", "kinain": "k / -in- / ain", "susulatin": "su* / sulat / -in",
          "sulat": "sulat", "bata": "bata", "lumang": "lumang"}   # * the copy (redup:CV); lang is not attested


def shown(S, w):
    return " / ".join(m.text + "*" if m.slot == "redup" else m.form if m.slot != "stem" else m.text for m in S.split(w))


def run():
    S = morphs.Segmenter(types.SimpleNamespace(morphs=AFFIXES + STEM, words=[]), {}, {w: 5 for w in WORDS})
    for w, want in EXPECT.items():
        assert shown(S, w) == want, (w, shown(S, w))
    for w in WORDS:
        assert S.rebuild(S.split(w)) == w, w
    ms = S.split("sumusulat")
    assert [m.form for m in ms if m.slot == "stem"] == ["sulat"] and morphs.parts(S, "sumusulat") == "s-um-u-sulat"
    assert [(m.slot, m.form) for m in S.split("sumulat")] == [("stem", "sulat"), ("infix", "-um-"), ("stem", "sulat")]
    assert S.labels("nagsusulat") == {"nag-", "redup:CV"}
    # the default site (after_prefix): the same infixes don't fire on their own, as before
    old = [dict(e, site=None) if e["slot"] == "infix" else e for e in STEM if e["slot"] != "redup"]
    D = morphs.Segmenter(types.SimpleNamespace(morphs=AFFIXES + old, words=[]), {}, {w: 5 for w in WORDS})
    assert shown(D, "sumulat") == "sumulat" and shown(D, "umalis") == "umalis" and not D.inf_onset and not D.redup
    # the model text: the infix glued on both sides, the copy before what follows; decoded back exactly
    C = model_text.Codec({"mode": "morphs", "join": "+", "tone": "~", "written": "none", "marks": [], "vowels": "aeiou",
                          "codes": {}, "tones": {}})
    line = "Sumusulat siya, nagsusulat at isinulat; umalis."
    e = C.encode(line, S)
    assert "+um+" in e and "su+" in e, e
    assert C.decode(e) == model_text.NFC(line), (e, C.decode(e))


def faults():
    """make-tanakh-research's check of v0.7.0, with and without positions (a chain store, as theirs): (1) a prefix before
    a copy whose core is rare on its own (nag-sa-sabi beside one magsasabi); (2) no infix or copy off words the NT links
    to another class (lalaki, tinig, sino), still off an unlinked verb whose root a linked verb has; no infix before a
    consonant (in-yong); (3) no free word as root (k-in-a-in), the infix reading over a productive suffix (k-in-ain)"""
    import collections
    vocab = {"nagsasabi": 200, "magsasabi": 1, "sabi": 50, "nagsabi": 50, "sinabi": 40, "kinain": 60, "kain": 20,
             "kainin": 10, "kumain": 250, "kakain": 15, "kina": 300, "ka": 900, "lalaki": 2000, "laki": 40, "tinig": 250,
             "tig": 5, "sino": 500, "so": 3, "inyong": 3000, "yong": 3, "kumakain": 80}
    vocab |= {w + "in": 3 for w in ("bas", "sul", "tak", "lak", "big", "dal", "kit", "tan", "luk", "sak", "sab", "ip")}
    vocab |= {w: 3 for w in ("bas", "sul", "tak", "lak", "big", "dal", "kit", "tan", "luk", "sak", "sab", "ip")}   # -in productive
    free = [dict(id="m:ka", slot="free", form="ka", host="any")]
    na = [dict(id="m:na-", slot="prefix", form="na-", host="verb"), dict(id="m:mag-", slot="prefix", form="mag-", host="verb")]
    C = lambda c: collections.Counter({c: 10, "": 10})
    classes = {"lalaki": C("noun"), "tinig": C("noun"), "sino": C("pron"), "kumain": C("verb"), "kinain": C("verb"),
               "nagsasabi": C("verb")}
    for pos in (0, 1):
        ms = [dict(e, position=pos) if pos and e["slot"] in ("prefix", "suffix") else e for e in AFFIXES + na] + STEM + free
        S = morphs.Segmenter(types.SimpleNamespace(morphs=ms, words=[]), {}, vocab, classes)
        got = {w: shown(S, w) for w in ("nagsasabi", "kinain", "kumain", "kumakain", "lalaki", "tinig", "sino", "inyong")}
        assert got["nagsasabi"] == "nag- / sa* / sabi", (pos, got)
        assert got["kinain"] == "k / -in- / ain" and got["kumain"] == "k / -um- / ain", (pos, got)
        assert got["kumakain"] == "k* / -um- / a* / kain", (pos, got)       # not linked: kain is a linked verb's root
        assert got["lalaki"] == "lalaki" and got["tinig"] == "tinig" and got["sino"] == "sino", (pos, got)
        assert "-in-" not in got["inyong"], (pos, got)
        assert all(S.rebuild(S.split(w)) == w for w in vocab)


def validator():
    """language_profile.py check: site and pattern; an after_onset infix may begin a word; a copy is not matched"""
    import json, subprocess, tempfile
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "text"))
    open(os.path.join(d, "text", "mrk001.txt"), "w").write("v1 Umalis siya at sinulat ang susulat.\n")
    base = dict(kind="morph", confidence="low", method="corpus-derived", by="agent:x", date="2026-11-14",
                status="observed", evidence=[{"ref": "MRK 1:1"}])
    es = [dict(base, **e) for e in STEM] + [dict(base, **{**STEM[2], "id": "m:redup.x", "pattern": "CCV"}),
                                           dict(base, **{**STEM[0], "id": "m:-x-", "site": "before_stem"})]
    json.dump({"iso": "tgl", "edition": "test", "partition": "observations", "entries": es},
              open(os.path.join(d, "observations.json"), "w"))
    r = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "language_profile.py"),
                        "check", d, "--text-dir", os.path.join(d, "text")], capture_output=True, text=True)
    out = r.stdout + r.stderr
    assert "m:redup.x: a redup morph needs pattern" in out and "m:-x-: site 'before_stem'" in out, out
    assert not any(f"m:{x}:" in out for x in ("-um-", "-in-", "redup.cv")), out


def test_stem_morphs():
    run()
    faults()
    validator()


if __name__ == "__main__":
    run()
    faults()
    validator()
    print("ok")
