#!/usr/bin/env python3
"""mirror.py - tenro/core is Tengai, exactly (invariant I6 of Tengai's docs/design.md).

  mirror.py check [--hyp ID]   core/ equals the Tengai tag in core.lock (a hypothesis: that tag plus hyp/ID/core.patch), the tag has not moved, the toolchains agree
  mirror.py sync TAG           replace core/ by the tree of Tengai's TAG and write core.lock
  mirror.py dry-run            every hyp/*/core.patch still applies to Tengai's CURRENT default branch (the daily promotion dry run)

`core.lock` is {"repo": URL, "tag": NAME, "tree": git tree id of the tag}. Equality is the equality of GIT TREES: a tree id covers every byte, every path and every file mode, so
"byte-identical" is one comparison and nothing is left to a diff that could miss a mode or a rename. `git rev-parse HEAD:core` is the id of core/ as committed; for a working tree
that is not committed yet the check hashes core/ in a scratch index, so it can run before a commit.

A hypothesis (a branch `hyp/<id>` with `hyp/<id>/manifest.json`) may change core/ only through `hyp/<id>/core.patch`, a patch that applies to the tag with `git apply`. The check applies it
to the tag in a scratch directory and requires core/ to be that result exactly. Promotion to Tengai is then that same patch (a daily dry run applies it to Tengai's main).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / "core.lock"
CORE = ROOT / "core"
GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "tenro-mirror",
    "GIT_AUTHOR_EMAIL": "tenro-mirror@users.noreply.github.com",
    "GIT_COMMITTER_NAME": "tenro-mirror",
    "GIT_COMMITTER_EMAIL": "tenro-mirror@users.noreply.github.com",
}


def git(*args: str, cwd: Path | None = None, check: bool = True, input: str | None = None) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False, env=GIT_ENV, input=input)
    if check and r.returncode != 0:
        raise SystemExit(f"mirror: git {' '.join(args)} failed: {r.stderr.strip()[:300]}")
    return r.stdout.strip() if check else r.stdout


def read_lock() -> dict:
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    for k in ("repo", "tag", "tree"):
        if not isinstance(lock.get(k), str) or not lock[k]:
            raise SystemExit(f"mirror: core.lock has no {k}")
    return lock


def fetch_tag(repo: str, tag: str, into: Path) -> str:
    """clone `tag` of `repo` (a URL or a local path) shallowly into `into`; the id of its tree"""
    git("clone", "-q", "--depth", "1", "--branch", tag, repo, str(into))
    return git("rev-parse", "HEAD^{tree}", cwd=into)


def tree_of_directory(directory: Path) -> str:
    """the git tree id of a directory's files, as a commit of exactly them would record it (.gitignore and global ignores play no part)"""
    with tempfile.TemporaryDirectory() as scratch:
        env = {
            **GIT_ENV,
            "GIT_INDEX_FILE": str(Path(scratch) / "index"),
            "GIT_DIR": str(Path(scratch) / "g"),
            "GIT_WORK_TREE": str(directory),
        }
        subprocess.run(["git", "init", "-q", env["GIT_DIR"]], check=True, env=env, capture_output=True)
        subprocess.run(
            ["git", "-c", "core.excludesFile=/dev/null", "add", "-A", "-f", "."], cwd=directory, check=True, env=env, capture_output=True
        )
        out = subprocess.run(["git", "write-tree"], cwd=directory, check=True, env=env, capture_output=True, text=True)
        return out.stdout.strip()


def expected_tree(lock: dict, hyp: str | None, workdir: Path) -> tuple[str, str]:
    """(the tree core/ must have, the tag's own tree id); for a hypothesis the tag's files with the patch applied"""
    clone = workdir / "tengai"
    tag_tree = fetch_tag(lock["repo"], lock["tag"], clone)
    if not hyp:
        return tag_tree, tag_tree
    patch = ROOT / "hyp" / hyp / "core.patch"
    if not patch.is_file():
        raise SystemExit(f"mirror: hyp/{hyp}/core.patch does not exist")
    shutil.rmtree(clone / ".git")
    git("apply", "--whitespace=nowarn", str(patch), cwd=clone)
    return tree_of_directory(clone), tag_tree


def check(hyp: str | None) -> int:
    lock = read_lock()
    problems = []
    with tempfile.TemporaryDirectory() as d:
        want, tag_tree = expected_tree(lock, hyp, Path(d))
    if tag_tree != lock["tree"]:
        problems.append(
            f"the tag {lock['tag']} of {lock['repo']} is now tree {tag_tree}, core.lock says {lock['tree']} (a moved tag: nothing is mirrored from it until a person re-syncs)"
        )
    if not CORE.is_dir():
        problems.append("core/ does not exist")
    else:
        have = tree_of_directory(CORE)
        if have != want:
            problems.append(
                f"core/ is tree {have}, it must be {want} ({'the tag with hyp/' + hyp + '/core.patch' if hyp else 'the tag ' + lock['tag']}): `mirror.py sync {lock['tag']}` rewrites it"
            )
        tc_root, tc_core = ROOT / "lean-toolchain", CORE / "lean-toolchain"
        if tc_root.is_file() and tc_core.is_file() and tc_root.read_text().strip() != tc_core.read_text().strip():
            problems.append(f"lean-toolchain differs: tenro {tc_root.read_text().strip()}, core {tc_core.read_text().strip()}")
    if problems:
        for p in problems:
            print(f"::error::mirror: {p}")
        return 1
    print(f"mirror ok: core/ is Tengai {lock['tag']} (tree {lock['tree'][:12]}){' + hyp/' + hyp if hyp else ''}")
    return 0


def dry_run() -> int:
    """each registered hypothesis patch must apply cleanly to Tengai's default branch as it is now: a promotion is that patch, so one that no longer applies is found here, daily, and not on the day of the promotion"""
    lock = read_lock()
    patches = sorted((ROOT / "hyp").glob("*/core.patch")) if (ROOT / "hyp").is_dir() else []
    failed = []
    with tempfile.TemporaryDirectory() as d:
        clone = Path(d) / "tengai"
        git("clone", "-q", "--depth", "1", lock["repo"], str(clone))
        head = git("rev-parse", "HEAD", cwd=clone)
        for patch in patches:
            r = subprocess.run(
                ["git", "apply", "--check", "--whitespace=nowarn", str(patch)], cwd=clone, capture_output=True, text=True, env=GIT_ENV
            )
            if r.returncode != 0:
                failed.append(f"hyp/{patch.parent.name}: {r.stderr.strip()[:200]}")
    for f in failed:
        print(f"::error::mirror dry-run: {f}")
    print(f"dry run: {len(patches) - len(failed)} of {len(patches)} hypothesis patch(es) apply to Tengai {head[:12]}")
    return 1 if failed else 0


def sync(tag: str) -> int:
    old = json.loads(LOCK.read_text(encoding="utf-8")) if LOCK.is_file() else {"repo": "https://github.com/competemath/tengai"}
    with tempfile.TemporaryDirectory() as d:
        clone = Path(d) / "tengai"
        tree = fetch_tag(old["repo"], tag, clone)
        shutil.rmtree(clone / ".git")
        if CORE.exists():
            shutil.rmtree(CORE)
        shutil.copytree(clone, CORE, symlinks=True)
    if tree_of_directory(CORE) != tree:
        raise SystemExit("mirror: the copy is not the tag's tree (a file mode or a symlink was lost)")
    LOCK.write_text(json.dumps({"repo": old["repo"], "tag": tag, "tree": tree}, indent=2) + "\n", encoding="utf-8")
    print(f"core/ is now Tengai {tag} (tree {tree[:12]})")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--hyp")
    s = sub.add_parser("sync")
    s.add_argument("tag")
    sub.add_parser("dry-run")
    a = ap.parse_args(argv)
    if a.cmd == "dry-run":
        return dry_run()
    return check(a.hyp) if a.cmd == "check" else sync(a.tag)


if __name__ == "__main__":
    sys.exit(main())
