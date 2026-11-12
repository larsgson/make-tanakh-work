#!/usr/bin/env python3
"""lifecycle.py on a synthetic chapter: the draft's tokens found in the file in step with the .align's positions (no
head lines, headings, markers or inline notes), a migration batch applied (text, .tagged, the .align's fingerprint,
the edit records in make-tanakh-review's format, the migration record) and undone byte for byte; stamps. No project
data."""
import json, os, sys, tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import full_align as FA  # noqa: E402
import lifecycle as LC  # noqa: E402
import words as W  # noqa: E402

DRAFT = """!!<Reifegrad: Entwurf>!!

===Ds Buech, Kapitel 1===

==D Wält==

v1 Der Herr het d Wält gmacht, {F: ds Wort »Wält« isch alt} und alls
isch voll gsi.
v2 Der Volk het gseit: Wält!
"""
d = tempfile.mkdtemp(); pdir = os.path.join(d, "toy"); os.makedirs(os.path.join(pdir, "gen"))
txt = os.path.join(pdir, "gen", "gen001.txt"); open(txt, "w", encoding="utf-8").write(DRAFT)
open(txt[:-4] + ".tagged", "w", encoding="utf-8").write("v1 Der^1 Herr^2 het^3 d^+ Wält^4 gmacht^5 und^6 alls^7 isch^8 voll^9 gsi^+.\nv2 Der^1 Volk^2 het^3 gseit^4: Wält^5!\n")
verses = FA.draft_texts(txt)
FA.write_chapter(txt[:-4] + ".align", 1, [(1, "0:0", "", "b"), (2, "0:0", "", "b")], verses)
before = {f: open(os.path.join(pdir, "gen", f), "rb").read() for f in os.listdir(os.path.join(pdir, "gen"))}

# the tokens in the file, position for position the verse's written tokens; the note's words are not among them
toks = LC.verse_tokens(DRAFT)
for v, t in verses:
    assert [DRAFT[a:b] for vv, _, a, b, _ in toks if vv == v] == W.written_tokens(t), v
assert not any(DRAFT[a:b] == "alt" for _, _, a, b, _ in toks) and not any(DRAFT[a:b] == "Kapitel" for _, _, a, b, _ in toks)
assert LC.case_like("Wält", "wäut") == "Wäut" and LC.case_like("HERR", "herr") == "HERR" and LC.case_like("voll", "vou") == "vou"

# a batch: Wält -> Wäut (both verses), voll -> vou
LC.project_dir = lambda p: pdir
LC.ROOT = d
R = W.Respeller([{"match": "l", "replace": "u", "context": {"before": "[äo]", "after": "t"}}, {"match": "ll$", "replace": "u"}])
changes = []
for v, p, a, b, cut in toks:
    w = DRAFT[a:b]; new = R(w.lower())
    if new != w.lower():
        changes.append(dict(code="gen", ch=1, path=txt, v=v, pos=p, start=a, end=b, old=w, new=LC.case_like(w, new),
                            entry="spelling:toy", cat="SPELL", published=False))
assert [(x["v"], x["old"], x["new"]) for x in changes] == [(1, "Wält", "Wäut"), (1, "voll", "vou"), (2, "Wält", "Wäut")], changes
rec_f, rec = LC.apply_changes("toy", changes, ["spelling:toy"], "20261112T000000Z")
t = open(txt, encoding="utf-8").read()
assert "d Wäut gmacht" in t and "isch vou gsi" in t and "»Wält« isch alt" in t and "==D Wält==" in t   # note and heading kept
assert "Wäut^4" in open(txt[:-4] + ".tagged", encoding="utf-8").read()
h, _ = FA.read_chapter(txt[:-4] + ".align")
assert h == FA.text_hash(1, FA.draft_texts(txt)) and rec["fingerprints"]
ed = os.path.join(pdir, ".tanakh", "edits", "GEN", "GEN_001", "20261112T000000Z-script-migrate.jsonl")
rows = [json.loads(x) for x in open(ed, encoding="utf-8")]
assert len(rows) == 3 and rows[0]["who"] == "script:migrate" and rows[0]["entry"] == "spelling:toy"
assert rows[0]["op"] == "R" and rows[0]["cat"] == "SPELL" and rows[0]["span"] == {"old": [4, 5], "new": [4, 5]}
assert rows[0]["ref"] == "1:1" and rows[0]["quote"]["prefix"] == "Herr het d" and rows[0]["old"] == "Wält"

# undo: the files as they were, byte for byte; new edit records of the undo
LC.time.strftime = lambda *a: "20261112T000001Z"
f2, rec2 = LC.undo("toy", rec_f)
after = {f: open(os.path.join(pdir, "gen", f), "rb").read() for f in os.listdir(os.path.join(pdir, "gen"))}
assert after == before, [f for f in before if before[f] != after.get(f)]
assert rec2["undo_of"] == os.path.basename(rec_f) and len(rec2["changes"]) == 3

# stamps
LC.RG.revision = lambda prof: "register-3"
LC.RG.profile_of = lambda p: pdir
s = LC.stamp("toy", "gen", 1, "drafted")
assert s["drafted"]["revision"] == "register-3" and LC.drafted_rev("toy", "gen", 1) == "register-3"
assert LC.drafted_rev("toy", "gen", 2) == "register-1"
print("ok")
