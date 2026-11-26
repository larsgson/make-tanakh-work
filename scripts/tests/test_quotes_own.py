#!/usr/bin/env python3
"""Regression test: a file that repeats the project's own drafts (a story or selection file built from them) quotes
nothing, even where a draft shares a phrase with the non-free edition; edition text copied into the same file is still
a quotation; a run only partly in a draft still counts. Synthetic edition and drafts, no project files.
Run: python3 scripts/tests/test_quotes_own.py (or with pytest)."""
import os, sys, types
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import langtools as LT  # noqa: E402
import quotes  # noqa: E402

EDITION = {(1, 1): "and the man went up to the city of the king and he sat down there",
           (1, 2): "the woman took the bread from the table and gave it to her son at night"}
DRAFT = "then the man went up to the city of the king and stayed"       # shares a 9-word run with 1:1


def make():
    Q = quotes.Quotes.__new__(quotes.Quotes)
    tok = LT.Tokeniser({}, ())
    Q.P = types.SimpleNamespace(tok=tok)
    Q.w = lambda t, s: quotes.merged(t.tokens(s))
    Q.written_tok = tok
    Q.rows = [(f"MAT {c}:{v}", "mat", (c, v), "", t, "ed", True) for (c, v), t in EDITION.items()]
    Q.grams = {}
    for i, r in enumerate(Q.rows):
        ts = Q.w(tok, r[4])
        for j in range(len(ts) - quotes.N + 1):
            Q.grams.setdefault(tuple(ts[j:j + quotes.N]), set()).add(i)
    Q.published, Q.has_published = set(), False
    ts = Q.w(tok, DRAFT)
    Q.own = {tuple(ts[j:j + quotes.N]) for j in range(len(ts) - quotes.N + 1)}
    return Q


def test_quotes_own():
    Q = make()
    story = "00:01:10\tMAT 1:1\twhole\t" + DRAFT + "\n"
    assert Q.check_text(story)[0] == 0                                   # our draft again: nothing quoted
    assert Q.check_text(story + "00:02:00\tMAT 1:2\twhole\t" + EDITION[(1, 2)] + "\n")[0] == 16   # the edition's verse
    assert Q.check_text("the man went up to the city of the king and he sat down")[0] == 14      # partly ours: counts
    Q.own = set()
    assert Q.check_text(story)[0] == 11                                  # without the drafts: the shared run counts


if __name__ == "__main__":
    test_quotes_own()
    print("ok")
