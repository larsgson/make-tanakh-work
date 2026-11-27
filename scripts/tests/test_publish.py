#!/usr/bin/env python3
"""publish_repo.py and publish_hf.py without project data: the verbatim screen (FORMAT.md 13), partial chapters, notes
and their anchors, the clause cut, the publisher list, the HF allow-list. Run: python3 scripts/tests/test_publish.py"""
import os, sys, tempfile, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import publish_repo as PR  # noqa: E402
import publish_hf as HF  # noqa: E402


def test_screen():
    team = "und Gott het gseit es söll Liecht wärde und es isch Liecht worde am erschte Tag"
    assert PR.fails("Gott het gseit, es söll Liecht wärde, und es isch Liecht worde", team)["run"] == 12   # a run of 10+
    assert PR.fails("Da het Gott gredt: Liecht söll sy!", team) is None
    # a unit of more than 10 words, 80% inside runs of 5 (no single run of 10)
    f = PR.fails("Gott het gseit es söll X und es isch Liecht worde", "Gott het gseit es söll A und es isch Liecht worde B")
    assert f == {"run": 5, "share": 0.909}, f
    assert PR.fails("Gott het gseit es söll X Y und es isch Liecht worde Z", "Gott het gseit es söll A B und es isch Liecht worde C") is None
    assert PR.norm("Gott-Vater, „Läbe“!") == ["gott", "vater", "läbe"]
    assert PR.norm("nø̀qa᷄v") == PR.norm("nø̀qa᷄v") and PR.norm("nø̀qa᷄v") != PR.norm("nøqav")   # tone kept


def test_ranges_and_notes():
    assert PR.ranges([1, 2, 3, 26]) == "1-3, 26" and PR.ranges([4]) == "4"
    toks = ["Und", "Noomi", "het", "gseit"]
    assert PR.anchor_of("Noomi: heisst di Liebi", toks) == 2 and PR.anchor_of("Allgemein", toks) == 4
    assert PR.inline_notes("v3 Er isch cho {T: Ordret: gange} und het gseh.") == [("T", 3, "Ordret: gange")]
    fm = PR.front_matter("RUT", 1, {"maturity": "Entwurf"}, ["a", "b", "c", "d", "e"], "1-3, 26")
    assert 'partial: "1-3, 26"' in fm.splitlines()[3] and PR.repo_status(fm)["maturity"] == "Entwurf"


def test_cut():
    # two clauses, tokens 0-2 linked to the first, 3-4 to the second; a third without words is `=`
    line = PR.units_line([("k1-k1", {"w1"}), ("k2-k2", {"w2"}), ("k3-k3", {"w3"})], 5, {"w1": [0, 2], "w2": [3, 4]})
    assert line == "k1-k1:0-2 k2-k2:3-4 k3-k3:=", line
    assert PR.units_line([], 3, {}) == ""


def test_publisher_list():
    d = tempfile.mkdtemp(); os.makedirs(os.path.join(d, ".tanakh"))
    open(os.path.join(d, ".tanakh", "publisher.json"), "w").write(json.dumps({"login": "me", "publisher": "x", "named": "2026-11-17"}))
    cfg = {"publisher": {"login": "me", "name": "work", "url": "https://example.org/w"}, "hf_dataset": "o/la", "block": {"repo": "gsw-be"}}
    assert PR.publisher_json(d, cfg) == {"publishers": [{"login": "me", "name": "work", "url": "https://example.org/w",
                                                         "analysis": "hf://datasets/o/la/gsw-be"}]}
    open(os.path.join(d, ".tanakh", "publisher.json"), "w").write(json.dumps({"publishers": [{"login": "other"}, {"login": "me"}]}))
    assert [p["login"] for p in PR.publisher_json(d, cfg)["publishers"]] == ["other", "me"]   # its place kept
    open(os.path.join(d, ".tanakh", "language.json"), "w").write(json.dumps({"code": "gsw", "name": "Bernese German", "bcp47": "gsw"}))
    assert PR.language_json(d, dict(cfg, code="gsw", block={"repo": "gsw-be", "variety": "be"})) == {
        "code": "gsw", "variety": "be", "name": "Bernese German", "bcp47": "gsw"}             # never the place tag in bcp47


def test_allow_list():
    ok = ["profile/decisions.json", "profile/register/terms/x.json", "wiki/index.md", "wiki/grammar/a.md",
          "review_overview.md", "gen/gen_review_overview.md", "gen/gen001_notes.md", "_state.md"]
    no = ["gen/gen001.txt", "gen/gen001.align", "gen/gen001_footnotes.txt", "gen/gen_style_guide.md", "gen/gen001_style.md",
          "_learn/packs/gen001.md", "_learn/words.db", "_learn/links_eng.tsv", "_eval/local/x.md", "profile/bhsa_layer.json",
          ".tanakh/runs/GEN.json", "project.yaml", "STATUS.md", "CREDITS.md", "wiki-view.html", "rut/rut001_notes.md"]
    assert all(HF.allowed(r, {"rut"}) for r in ok), [r for r in ok if not HF.allowed(r, {"rut"})]
    assert not any(HF.allowed(r, {"rut"}) for r in no), [r for r in no if HF.allowed(r, {"rut"})]


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
    print("ok")
