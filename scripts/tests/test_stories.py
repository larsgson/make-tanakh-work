#!/usr/bin/env python3
"""stories.py on synthetic data: a readings list (the work copy's column names too), a language repository in
make-tanakh-review's FORMAT.md, a reading not drafted listed as missing, a partial reading drafted in part kept as it
is. No project data, no source database. Run: python3 scripts/tests/test_stories.py (or with pytest)."""
import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import stories as ST  # noqa: E402


def setup():
    d = tempfile.mkdtemp()
    sd = os.path.join(d, "import", "stories", "CC0", "toy")
    os.makedirs(sd)
    open(os.path.join(sd, "story.yaml"), "w").write("title: Toy\nlicence: CC0\ncredit: a toy list\n")
    open(os.path.join(sd, "toy.readings.tsv"), "w").write(
        "film_n\tbook\tchapter\tverse\tpart\thebrew_read\tstart\tend\n"
        "1\tgen\t1\t1\twhole\t\t00:00:01.000\t00:00:05.000\n"
        "2\tgen\t1\t2\tto_end\tx\t00:00:05.000\t00:00:09.000\n"
        "3\tgen\t1\t3\twhole\t\t\t\n")
    repo = os.path.join(d, "repo"); os.makedirs(os.path.join(repo, "GEN"))
    open(os.path.join(repo, "GEN", "GEN_001.md"), "w").write(
        "---\nbook: GEN\nchapter: 1\n---\n# Ds Buech, Kapitel 1\n\n## Am Aafang\n1:1\tAm Aafang het Gott gmacht.\n"
        "1:2\tD Ärde isch läär gsi.\n1:3\t\n")
    return d, repo


def test_readings_and_repo():
    d, repo = setup()
    ST.ROOT = d
    R = ST.readings(os.path.join(d, "import", "stories", "CC0", "toy", "toy.readings.tsv"))
    assert [(r["n"], r["code"], r["ch"], r["v"], r["part"]) for r in R] == \
        [("1", "gen", 1, 1, "whole"), ("2", "gen", 1, 2, "to_end"), ("3", "gen", 1, 3, "whole")]
    assert R[1]["source_read"] == "x" and R[0]["start"] == "00:00:01.000"
    T = ST.Text(repo=repo)
    verses, rows, h, head = T.chapter("gen", 1)
    assert verses == {1: "Am Aafang het Gott gmacht.", 2: "D Ärde isch läär gsi."} and head == "Ds Buech, Kapitel 1"
    assert ST.story_dirs() == {"toy": os.path.join(d, "import", "stories", "CC0", "toy")}
    txt, tsv, missing, cuts = ST.build("toy", repo=repo, out=os.path.join(d, "out"), quiet=True)
    assert missing == ["GEN 1:3"] and tsv[1][4] == "Ds Buech 1:1" and tsv[3][6] == "[not drafted yet]"
    assert "[00:00:01–00:00:05] Ds Buech 1:1" in txt and "a toy list" in txt[1]
    assert tsv[2][6].endswith("[whole verse; only part is read]") and cuts and "heb.sqlite" in cuts[0]
    assert os.path.exists(os.path.join(d, "out", "toy.txt")) and os.path.exists(os.path.join(d, "out", "toy.tsv"))
    assert ST.REF.match("GEN.1.3") and ST.REF.match("1SA 17:45")


if __name__ == "__main__":
    test_readings_and_repo()
    print("ok")
