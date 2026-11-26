#!/usr/bin/env python3
"""Regression test: small fixes from the work copy's "seen, not fixed" list (v0.10.1). The probe's answer keys (1. 1)
1:), U+034F in a lemma, a drop mark glued to a word in the tagged format, evidence resolved against every style
edition; and the notes slimmed to phrases (v0.11.0).
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


def test_notes_slim():
    """v0.11.0: notes without whole verses. A per-verse table loses its whole verses (original, rendering, BSB) and
    keeps the comment; a table of choices keeps its original phrase and moves the rendering and BSB phrase into the
    comment; the credit line stays only where the original is quoted"""
    NH.original_verses = lambda code, ch: {1: "א ב ג ד ה ו", 2: "ז ח ט י כ ל"}
    draft = {1: "one two three four five six", 2: "seven eight nine ten eleven twelve"}
    bsb = {1: "a b c d e f g", 2: "h i j k l m n"}
    md = ("# Notes\n\n| Verse | Hebrew | Target | BSB | Comment |\n|---|---|---|---|---|\n"
          "| 1 | א ב ג ד ה ו | one two three four five six | a b c d e f g | why v1 |\n"
          "| 2 | ז ח ט י כ ל | seven eight nine ten eleven twelve | h i j k l m n | |\n\n" + NH.CREDIT["ot"] + "\n")
    new, st = NH.slim_text(md, "gen", 1, draft, bsb)
    assert "| Verse | Comment |" in new and "| 1 | why v1 |" in new and "| 2 |" not in new, new
    assert NH.CREDIT_MARK not in new and st["emptied"] == 6 and st["dropped"] == 1
    md = ("| Vers | Hebraisk | Dansk | BSB | Kommentar |\n|---|---|---|---|---|\n"
          "| 1 | ב ג | borgen | palace / temple | why |\n| 1 | ד | hus | house | |\n")
    new, st = NH.slim_text(md, "gen", 1, draft, bsb)
    assert "| Vers | Hebraisk | Kommentar |" in new and "| 1 | ב ג | »borgen« (palace / temple): why |" in new, new
    assert "| 1 | ד | »hus« (house) |" in new and NH.CREDIT_MARK in new and st["folded"] == 2


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
