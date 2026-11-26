#!/usr/bin/env python3
"""register.py on a synthetic store: the round trip is exact (every field, the order), the envelope's rules, add /
supersede / retire / status, revisions and what changed, the loader for old and new stores. No project data."""
import json, os, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import register as RG  # noqa: E402

OBS = {"iso": "toy", "edition": "toy_BSB", "partition": "observations", "licence": "CC0-1.0",
       "orthography": {"normalization": "NFC", "ignore_marks": ["U+0300"], "tone": {"written": "none"}},
       "analysis": {"match": "strings"},
       "entries": [
           {"id": "gb:GB020", "kind": "feature", "value": "yes", "confidence": "medium", "method": "corpus-derived",
            "by": "agent:x", "date": "2026-10-01", "status": "observed", "codes": ["GB020"]},
           {"id": "m:ta-:verb", "kind": "morph", "value": "PST", "form": "ta-", "slot": "prefix", "host": "verb",
            "position": 1, "confidence": "low", "method": "corpus-derived", "by": "script:morphs.py", "date": "2026-10-02",
            "status": "observed", "stats": {"count": 12}},
           {"id": "c:verb:pst", "kind": "cell", "value": "ta-", "alternatives": [{"value": "Ø", "n": 3}], "status": "observed"},
           {"id": "gap:fish", "kind": "gap", "value": "searched: fish", "status": "open", "by": "agent:y", "date": "2026-10-03"},
           {"id": "claim:x y", "kind": "claim", "value": "a claim with a space", "basis": "corpus", "status": "observed"},
       ]}
DEC = {"iso": "toy", "edition": "toy_BSB", "partition": "decisions", "licence": "CC0-1.0",
       "orthography": {"normalization": "NFC"},
       "entries": [
           {"id": "term:H639", "kind": "term", "value": "wrath", "source": "H639", "gloss": [{"lang": "hbo", "form": "אַף"}],
            "words": ["anger"], "alternatives": [{"value": "fury", "status": "admitted"}], "method": "team-decision",
            "by": "team:t", "date": "2026-10-04", "status": "decided"},
           {"id": "term:old", "kind": "term", "value": "aa", "method": "project-decision", "by": "agent:z", "date": "2026-10-05",
            "status": "superseded"},
           {"id": "term:new", "kind": "term", "value": "bb", "supersedes": "term:old", "method": "project-decision",
            "by": "agent:z", "date": "2026-10-06", "status": "decided", "evidence": [{"ref": "GEN 1:1", "form": "bb"}]},
           {"id": "spelling:ph", "kind": "spelling", "value": "ph → f", "match": "ph", "replace": "f", "said": "ph is written f",
            "method": "project-decision", "by": "agent:z", "date": "2026-10-07", "status": "decided"},
       ]}

d = tempfile.mkdtemp()
for fn, x in (("observations.json", OBS), ("decisions.json", DEC)):
    json.dump(x, open(os.path.join(d, fn), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# the loader before the conversion: the files as they are
assert RG.store_file(d, "decisions.json") == DEC and not RG.has_register(d)
E0 = RG.entries(profile=d)
assert {e["id"] for e in E0} >= {"feature:GB020", "morph:ta-:verb", "rule:c:verb:pst", "choice:fish", "rule:x_y",
                                 "term:H639", "spelling:ph"}, sorted(e["id"] for e in E0)

# convert: lossless, every field and the order
RG.convert(d)
assert RG.has_register(d) and not os.path.exists(os.path.join(d, "decisions.json"))
for fn, x in (("observations.json", OBS), ("decisions.json", DEC)):
    back = RG.store_file(d, fn)
    assert json.dumps(back, ensure_ascii=False) == json.dumps(x, ensure_ascii=False), fn
    assert RG.read(os.path.join(d, fn)) == x and RG.exists(os.path.join(d, fn))
E = {e["id"]: e for e in RG.entries(profile=d)}
t = E["term:H639"]
assert t["basis"] == "team" and t["status"] == "decided" and t["renderings"][1] == {"form": "fury", "status": "admitted"}
assert E["term:new"]["supersedes"] == "term:old" and E["orthography:main"]["ignore_marks"] == ["U+0300"]
assert E["orthography:decisions"]["normalization"] == "NFC"
assert RG.sid_of(E["rule:x_y"]) == "claim:x y"
err, warn = RG.check(RG.load(RG.register_dir(d), store=False))     # the files as they are: no `store` in them
assert not err, err
assert all("store" not in x for x in RG.load(RG.register_dir(d), store=False))
assert json.load(open(os.path.join(RG.register_dir(d), "STORE.json"), encoding="utf-8"))["round_trip"]
assert not RG.check_files(RG.register_dir(d))
assert RG.revision(d) == 1 and RG.version(RG.register_dir(d))["revision"] == 1

# a writer's whole-file write goes into the register
x = RG.read(os.path.join(d, "observations.json")); x["entries"].append({"id": "gap:bird", "kind": "gap", "value": "b", "status": "open"})
RG.write(os.path.join(d, "observations.json"), x, ensure_ascii=False, indent=1)
assert RG.store_file(d, "observations.json")["entries"][-1]["id"] == "gap:bird"
assert not os.path.exists(os.path.join(d, "observations.json"))

# add, supersede (the team's decision only by the team), retire, status; revisions
RG.add(d, {"id": "term:H1288", "kind": "term", "value": "bless", "status": "decided", "basis": "human", "by": "agent:q",
           "source": "H1288"})
assert RG.store_file(d, "decisions.json")["entries"][-1]["id"] == "term:H1288"
try:
    RG.supersede(d, "term:H639", {"value": "rage", "basis": "model"})
    raise AssertionError("a model entry superseded the team's decision")
except SystemExit:
    pass
n = RG.supersede(d, "term:H1288", {"value": "praise", "by": "agent:q"})
E = {e["id"]: e for e in RG.entries(profile=d)}
assert n["id"] == "term:H1288.2" and E["term:H1288"]["status"] == "superseded" and E["term:H1288.2"]["supersedes"] == "term:H1288"
dec = RG.store_file(d, "decisions.json")["entries"]
assert [e["status"] for e in dec if e["id"] == "term:H1288"] == ["superseded"]
assert dec[-1]["supersedes"] == "term:H1288" and dec[-1]["value"] == "praise"
RG.set_status(d, "gap:fish", "retired")
ch = RG.changed_since(d, 1)
assert set(ch) == {"choice:bird", "term:H1288", "term:H1288.2", "choice:fish"} and set(ch.values()) == {"unreleased"}, ch
rev, changed = RG.bump(d, "2026-11-12")
assert rev == 2 and RG.tag_of(rev) == "register-2" and changed["term:H1288.2"] == "added" and changed["term:H1288"] == "added" and changed["choice:fish"] == "changed"
assert RG.changed_since(d, 2) == {} and set(RG.changed_since(d, 1)) == set(ch)
assert RG.rev_n("register-3") == RG.rev_n(3) == RG.rev_n("3") == 3 and RG.changed_since(d, "register-1") == RG.changed_since(d, 1)
assert not RG.check(RG.load(RG.register_dir(d), store=False))[0]

# the rules catch what they should
bad = [dict(E["term:new"], id="term:new x"), dict(E["term:H639"], value="other"), {**E["spelling:ph"], "match": "("},
       dict(E["term:new"], id="term:z", supersedes="term:none")]
err = RG.check(bad)[0]
assert any("white space" in x for x in err) and any("preferred rendering" in x for x in err)
assert any("pattern" in x for x in err) and any("not in the register" in x for x in err), err
assert RG.file_of("term:H639").startswith("term/h639-") and RG.file_of("term:H639").endswith(".json")

# the agents' wording: register.py add for a register, the text unchanged for the old store
rule = "- [store] **Extend the memory at the end:** add to `profile/decisions.json` the decisions (`method: project-decision`)"
keep = RG.profile_of
RG.profile_of = lambda p: d
w = RG.agent_wording(rule, "x/y")
assert "register.py add x/y --kind" in w and "decisions.json" not in w and "--basis human" in w, w
assert RG.agent_wording(w, "x/y") == w
assert "register.py show x/y" in RG.agent_wording("read observations.json", "x/y", long=True)
RG.profile_of = lambda p: os.path.join(d, "none")
assert RG.agent_wording(rule, "x/y") == rule
RG.profile_of = keep
print("ok")
