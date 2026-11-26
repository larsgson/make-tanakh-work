#!/usr/bin/env python3
"""Regression test: small fixes from the work copy's "seen, not fixed" list (v0.10.1). The probe's answer keys (1. 1)
1:), U+034F in a lemma, a drop mark glued to a word in the tagged format, the notes' per-verse tables (a partial
chapter's one-verse rows filled; a table of choices left alone), evidence resolved against every style edition.
Synthetic data, no project files. Run: python3 scripts/tests/test_seen_fixes.py (or with pytest)."""
import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import full_align as FA  # noqa: E402
import gloss  # noqa: E402
import language_profile as LPR  # noqa: E402
import notes_hebrew as NH  # noqa: E402
import probe_language as PL  # noqa: E402


def test_answer_keys():
    f = os.path.join(tempfile.mkdtemp(), "a.tsv")
    open(f, "w", encoding="utf-8").write("1.\tB\n2)\tA\n3:\tA\n4\tB\nGEN 1:1\tIn the beginning\n")
    assert PL.answers(f) == {"1": "B", "2": "A", "3": "A", "4": "B", "GEN 1:1": "In the beginning"}


def test_grapheme_joiner():
    assert gloss.bare("יְרוּשָׁלִַ͏ם") == gloss.bare("יְרוּשָׁלִַם")


def test_drop_glued_to_a_word():
    assert FA.strip_tags("v1 Und^1 Gott^2^-5. Dann^3 ^-4 ging^6.") == "v1 Und Gott. Dann ging."


def test_notes_per_verse():
    orig = {v: "a b c d e f g h" for v in range(1, 33)}
    head = ["Verse", "Hebrew", "Target", "BSB", "Comment"]
    few = [["3", "", "x y z", "one two three four five six seven", ""], ["7", "", "x y", "one two three … ", ""],
           ["12-14", "", "x", "a range", ""]]
    assert NH.per_verse(few, orig, head)[0]                      # a few verses and a range: the one-verse rows count
    choice = [["3", "", "borgen", "palace / temple", ""], ["7", "", "karneol", "onyx … marble x", ""],
              ["9", "", "hus", "house", ""]]
    ok, why = NH.per_verse(choice, orig, head)
    assert not ok and "choice" in why                            # phrases: a row per choice, left alone
    twice = [["3", "", "a", "b", ""], ["3", "", "c", "d", ""]]
    assert "more than one row" in NH.per_verse(twice, orig, head)[1]


def test_evidence_in_every_style_edition():
    d = tempfile.mkdtemp()
    a, b = os.path.join(d, "a"), os.path.join(d, "b")
    os.makedirs(a); os.makedirs(b)
    open(os.path.join(a, "gen001.txt"), "w", encoding="utf-8").write("v1 alpha\nv2 beta\n")
    open(os.path.join(b, "gen001.txt"), "w", encoding="utf-8").write("v2 gamma\nv3 delta\n")
    t = LPR.load_texts([a, b])
    assert t[("GEN", 1, 1)] == "alpha" and t[("GEN", 1, 3)] == "delta" and "beta" in t[("GEN", 1, 2)] and "gamma" in t[("GEN", 1, 2)]


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
    print("ok")
