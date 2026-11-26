#!/usr/bin/env python3
"""Regression test: clitics (a morph of slot clitic: a part that attaches to a whole word; its side by its form, =ng or
-ng after the word, ng= before it). Fused, it comes off only where what remains is a word of the corpus, not rare beside
this one (dati=ng; not dumati=ng, so the infix reading d-um-ating stands); several stack; the word before it is split as
any word; written with a hyphen it is a hyphen part, labelled clitic; a protected word keeps it; every word rebuilds; the
model text decodes back exactly; a store without clitics splits as before; the validator wants one side marked.
Synthetic store, no project files. Run: python3 scripts/tests/test_clitics.py (or with pytest)."""
import json, os, subprocess, sys, tempfile, types
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "nllb"))
import morphs  # noqa: E402
import model_text  # noqa: E402

M = lambda slot, form, **k: dict(id="m:" + form, slot=slot, form=form, host=k.pop("host", "any"), **k)
BASE = [M("infix", "-um-", site="after_onset", host="verb"), M("prefix", "pag-", host="verb"), M("suffix", "-an", host="verb")]
CLITICS = [M("clitic", "=ng"), M("clitic", "=que"), M("clitic", "ka="), M("clitic", "-ko", written="hyphen")]
VOCAB = {w: 5 for w in ("dati dating dumating darating pagdating bahay bahayng populus populusque populusqueng tao katao "
                        "lame lame-ko kanino uging ugi pagdatingan").split()}
WORDS = [{"id": "w:uging", "kind": "word", "form": "uging"}]


def shown(S, w):
    return " / ".join(m.form if m.slot not in ("stem",) else m.text for m in S.split(w))


def run():
    S = morphs.Segmenter(types.SimpleNamespace(morphs=BASE + CLITICS, words=WORDS), {}, VOCAB)
    want = {"dating": "dati / =ng", "dumating": "d / -um- / ating", "bahayng": "bahay / =ng",
            "populusque": "populus / =que", "populusqueng": "populus / =que / =ng", "katao": "ka= / tao",
            "lame-ko": "lame / -ko", "kanino": "kanino", "uging": "uging", "pagdatingan": "pag- / dating / -an"}
    for w, x in want.items():
        assert shown(S, w) == x, (w, shown(S, w))
    assert [m.slot for m in S.split("lame-ko")] == ["stem", "clitic"]
    assert S.labels("populusqueng") == {"=que", "=ng"}
    for w in VOCAB:
        assert S.rebuild(S.split(w)) == w, w
    # a store without clitics: as before
    D = morphs.Segmenter(types.SimpleNamespace(morphs=BASE, words=WORDS), {}, VOCAB)
    assert shown(D, "dating") == "dating" and not D.encl and not D.procl
    # the model text: an enclitic glued after, a proclitic before; decoded back exactly
    C = model_text.Codec({"mode": "morphs", "join": "+", "tone": "~", "written": "none", "marks": [], "vowels": "aeiou",
                          "codes": {}, "tones": {}})
    line = "Dating bahayng populusque katao, dumating."
    e = C.encode(line, S)
    assert "+ng" in e and "ka+" in e and "+que" in e, e
    assert C.decode(e) == model_text.NFC(line), (e, C.decode(e))


def validator():
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "text"))
    open(os.path.join(d, "text", "mrk001.txt"), "w").write("v1 Dating bahayng katao.\n")
    base = dict(kind="morph", value="LNK", confidence="low", method="corpus-derived", by="agent:x", date="2026-11-26",
                status="observed", evidence=[{"ref": "MRK 1:1"}])
    es = [dict(base, **CLITICS[0]), dict(base, **CLITICS[2]), dict(base, **{**CLITICS[0], "id": "m:ng", "form": "ng"})]
    json.dump({"iso": "tgl", "edition": "test", "partition": "observations", "entries": es},
              open(os.path.join(d, "observations.json"), "w"))
    r = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "language_profile.py"),
                        "check", d, "--text-dir", os.path.join(d, "text")], capture_output=True, text=True)
    out = r.stdout + r.stderr
    assert "m:ng: a clitic's form 'ng' marks one side" in out, out
    assert "m:=ng:" not in out and "m:ka=:" not in out, out


def test_clitics():
    run()
    validator()


if __name__ == "__main__":
    run()
    validator()
    print("ok")
