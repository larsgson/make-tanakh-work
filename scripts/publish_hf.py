#!/usr/bin/env python3
"""Publish a project's language analysis to the publisher's Hugging Face dataset, by an allow-list, without history
(docs/publishing.md). Dry run by default; --apply uploads, and that can't be undone: the history is squashed.

    python3 scripts/publish_hf.py <project> [--config publish.yaml] [--apply]

- **What goes** (the allow-list; nothing else, whatever else the folder holds): the store (`profile/*.json`,
  `profile/*.yaml`, `profile/register/**/*.json`), the wiki (`wiki/**/*.md`), the review overviews
  (`review_overview*.md`, `<code>/<code>_review_overview.md`), the chapter notes (`<code>/<code>NNN_notes.md`) and
  `_state.md` files. Never: `_learn/` (verse packs, alignment links, words.db, the cache), `_eval/`, style reports,
  anything BHSA-based, `.tanakh/`, the drafts (they go to the language repository), and nothing of a book in
  quarantine. Generated beside them: `CREDITS.md` (every edition's credit line), `README.md` (CC0 except the
  quotations credited in CREDITS.md) and `manifest.json` (each file's SHA-256).
- **Where:** `<hf_dataset>` from publish.yaml, the folder `<code>[-<variety>]` (the project's publish.repo): the
  language repository's publisher entry points there (`analysis: hf://datasets/<owner>/<dataset>/<folder>`), and the
  review app shows `<folder>/review_overview.md` publicly.
- **Checks before anything goes:** `check_project.py` on the project, and the quotation check (`quotes.py`) on exactly
  the files to upload, review overviews included; any problem stops the run.
- **--apply** (`HF_TOKEN` from the work copy's `.env` or the environment): the folder uploaded (its old files that are
  no longer allowed deleted), the history squashed to one commit, LFS files no longer referenced deleted; then it
  checks that the dataset has exactly one commit and the folder exactly the uploaded files.

The upload folder is built in `.publish/hf/<folder>/` (git-ignored) and kept for a look after a dry run."""
import argparse, datetime, fnmatch, hashlib, json, os, re, shutil, subprocess, sys

CODE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.abspath(os.environ.get("MAKE_TANAKH_ROOT") or CODE)
sys.path.insert(0, os.path.join(CODE, "scripts"))
from books import BY_CODE  # noqa: E402
from project import project_dir  # noqa: E402
import publish_repo as PR  # noqa: E402

ALLOW = ["profile/*.json", "profile/*.yaml", "profile/register/**/*.json", "wiki/*.md", "wiki/**/*.md",
         "review_overview*.md", "*/*_review_overview.md", "*/[0-9a-z][0-9a-z][0-9a-z][0-9][0-9][0-9]_notes.md",
         "_state.md", "*/_state.md"]
NEVER = re.compile(r"(^|/)(_learn|_eval|\.tanakh|local|packs|quarantined)(/|$)|bhsa|_style\.md$|links_.*\.tsv$|words\.db$", re.I)
GENERATED = ("CREDITS.md", "README.md", "manifest.json")


def allowed(rel, quarantine):
    if NEVER.search(rel):
        return False
    top = rel.split("/")[0]
    if top in quarantine:                       # a book in quarantine: its notes stay local until it ends
        return False
    if top in BY_CODE and not re.match(rf"{top}/({top}\d{{3}}_notes|{top}_review_overview|_state)\.md$", rel):
        return False
    return any(fnmatch.fnmatchcase(rel, p) for p in ALLOW)


def selection(pname, p):
    d = project_dir(pname)
    out = []
    for dp, dns, fs in os.walk(d):
        dns[:] = [x for x in dns if not x.startswith(".")]
        for f in fs:
            rel = os.path.relpath(os.path.join(dp, f), d).replace(os.sep, "/")
            if allowed(rel, set(p.get("quarantine") or [])):
                out.append(rel)
    return sorted(out)


def token():
    t = os.environ.get("HF_TOKEN")
    f = os.path.join(ROOT, ".env")
    if not t and os.path.exists(f):
        for l in open(f, encoding="utf-8"):
            m = re.match(r"\s*HF_TOKEN\s*=\s*['\"]?([^'\"\s]+)", l)
            if m:
                t = m[1]
    if not t:
        raise SystemExit("no HF_TOKEN in the work copy's .env or the environment")
    return t


def card(cfg, folder, files, quoted):
    b, p = cfg["block"], cfg["project"]
    name = b.get("name") or p.get("language_name") or folder
    return "\n".join([
        f"# {name}: language analysis ({folder})", "",
        f"From the work copy {cfg['publisher'].get('name') or cfg['publisher']['login']}"
        + (f" ({cfg['publisher']['url']})" if cfg["publisher"].get("url") else "")
        + f", project `{os.path.basename(p.get('_name', '')) or folder}`, {datetime.date.today().isoformat()}.", "",
        "The language store (`profile/`), the wiki, the review overviews and the chapter notes that go with the drafts "
        f"in the language repository `{cfg['org']}/{b['repo']}`. Overwritten on every publish, without history.", "",
        "**Licence:** CC0 1.0, except the quotations, which stay with their owners and are credited in `CREDITS.md`"
        + (f" ({quoted} quoted words)." if quoted else " (none here)."), "",
        f"{len(files)} files of the project, and this card, `CREDITS.md` and `manifest.json` (each file's SHA-256).", ""])


def root_card(dataset):
    return "\n".join(["---", "license: cc0-1.0", "pretty_name: language analysis", "---", "",
                      f"# {dataset}", "",
                      "One folder per language repository (`<code>` or `<code>-<variety>`): the language store, wiki, review "
                      "overviews and chapter notes of make-tanakh projects. CC0 1.0, except the quotations credited in each "
                      "folder's `CREDITS.md`. Overwritten on every publish, without history.", ""])


def build(pname, cfg, skip_check=False):
    """-> (folder, stage dir, files, problems)"""
    import quotes as QT
    p, folder = cfg["project"], cfg["block"]["repo"]
    problems = []
    if not cfg.get("hf_dataset"):
        problems.append("publish.yaml: hf_dataset missing")
    problems += PR.gate(pname, cfg, skip_check)
    d = project_dir(pname)
    files = selection(pname, p)
    stage = os.path.join(ROOT, ".publish", "hf", folder)
    shutil.rmtree(stage, ignore_errors=True)
    for rel in files:
        os.makedirs(os.path.dirname(os.path.join(stage, rel)), exist_ok=True)
        shutil.copy2(os.path.join(d, rel), os.path.join(stage, rel))
    Q = QT.Quotes(pname)
    QT.write_credits(Q, os.path.join(stage, "CREDITS.md"))
    probs, warns, quoted = Q.check_files([os.path.join(stage, r) for r in files], os.path.join(stage, "CREDITS.md"))
    problems += [re.sub(re.escape(os.path.relpath(stage, ROOT)) + "/", "", x) for x in probs]
    open(os.path.join(stage, "README.md"), "w", encoding="utf-8").write(card(dict(cfg, project=dict(p, _name=pname)), folder, files, quoted))
    allf = files + list(GENERATED[:2])
    man = {"format": "make-tanakh-analysis/1", "folder": folder, "project": os.path.basename(pname),
           "repository": f"{cfg['org']}/{cfg['block']['repo']}", "made": datetime.date.today().isoformat(),
           "code": subprocess.run(["git", "-C", ROOT, "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip(),
           "licence": "CC0-1.0, except the quotations credited in CREDITS.md",
           "files": {r: hashlib.sha256(open(os.path.join(stage, r), "rb").read()).hexdigest() for r in sorted(allf)}}
    open(os.path.join(stage, "manifest.json"), "w", encoding="utf-8").write(json.dumps(man, ensure_ascii=False, indent=1) + "\n")
    return folder, stage, sorted(allf + ["manifest.json"]), problems, warns, quoted


def upload(cfg, folder, stage, files):
    from huggingface_hub import HfApi
    api, rid = HfApi(token=token()), cfg["hf_dataset"]
    api.create_repo(rid, repo_type="dataset", exist_ok=True, private=bool(cfg.get("hf_private")))
    if not api.file_exists(rid, "README.md", repo_type="dataset"):
        api.upload_file(path_or_fileobj=root_card(rid).encode(), path_in_repo="README.md", repo_id=rid, repo_type="dataset",
                        commit_message="The dataset card")
    api.upload_folder(repo_id=rid, repo_type="dataset", folder_path=stage, path_in_repo=folder, delete_patterns="**",
                      commit_message=f"{folder}: the language analysis of {datetime.date.today().isoformat()}")
    api.super_squash_history(rid, repo_type="dataset", commit_message=f"language analysis ({datetime.date.today().isoformat()})")
    live = {e.lfs.sha256 for e in api.list_repo_tree(rid, repo_type="dataset", recursive=True, expand=True)
            if getattr(e, "lfs", None)}
    stale = [f for f in api.list_lfs_files(rid, repo_type="dataset") if f.file_oid not in live]
    if stale:
        api.permanently_delete_lfs_files(rid, stale, repo_type="dataset")
    commits = api.list_repo_commits(rid, repo_type="dataset")
    there = sorted(f[len(folder) + 1:] for f in api.list_repo_files(rid, repo_type="dataset") if f.startswith(folder + "/"))
    bad = []
    if len(commits) != 1:
        bad.append(f"{len(commits)} commits after the squash, not one")
    if there != sorted(files):
        bad.append(f"the folder holds {len(there)} files, {len(files)} were uploaded: "
                   f"extra {sorted(set(there) - set(files))[:5]}, missing {sorted(set(files) - set(there))[:5]}")
    return bad, len(stale)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("project")
    ap.add_argument("--config", help="publish.yaml to use (default: the work copy's root)")
    ap.add_argument("--apply", action="store_true", help="upload, squash the history (irreversible)")
    ap.add_argument("--skip-check", action="store_true", help=argparse.SUPPRESS)   # tests only
    a = ap.parse_args()
    cfg = PR.config(a.project, a.config)
    folder, stage, files, problems, warns, quoted = build(a.project, cfg, a.skip_check)
    size = sum(os.path.getsize(os.path.join(stage, f)) for f in files)
    groups = {}
    for f in files:
        k = f.split("/")[0] if "/" in f else "(top)"
        k = "chapters" if k in BY_CODE else k
        groups[k] = groups.get(k, 0) + 1
    print(f"{a.project} -> hf://datasets/{cfg.get('hf_dataset')}/{folder}: {len(files)} files, {size / 1e6:.1f} MB "
          f"({', '.join(f'{k} {n}' for k, n in sorted(groups.items()))}); {quoted} quoted words; built in "
          f"{os.path.relpath(stage, ROOT)}")
    for w in warns[:10]:
        print("  warning:", w)
    if problems:
        print("refused, nothing uploaded:")
        for x in problems[:30]:
            print("  -", x)
        sys.exit(1)
    if not a.apply:
        print("dry run: nothing uploaded (--apply uploads and squashes the dataset's history: irreversible)")
        return
    bad, n = upload(cfg, folder, stage, files)
    print(f"uploaded; history squashed to one commit; {n} unreferenced LFS files deleted")
    for b in bad:
        print("  check failed:", b)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
