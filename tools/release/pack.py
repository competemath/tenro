#!/usr/bin/env python3
"""pack.py - the tengai data snapshot as one verifiable file, and the way back. Standard library only.

  pack.py pack --olean-dir DIR --manifest MANIFEST.json --out SNAPSHOT.tar        DIR/TengaiData/*.olean + manifest.json -> a deterministic tar (sorted, mtime 0, owner 0): the same inputs give the same bytes
       [--indexes DIR] [--legal DIR]                                                the retrieval indexes go under indexes/, the licence texts and notices (tools/release/licences.py) under legal/: each is listed in the manifest with its sha256 and verified
  pack.py verify SNAPSHOT.tar[.zst|.gz] [--sha256 H] --into DIR                    unpack, check every .olean against the manifest's sha256, print the LEAN_PATH entry that makes `import TengaiData.X` work

A snapshot (manifest schema 1: one module; schema 2: a promotion in layers, `manifest.py layers`) is what a prover environment (Leak) puts on its LEAN_PATH next to Lean core: `LEAN_PATH=DIR:$LEAN_PATH`. Compression is the caller's (`zstd -T0 -19 --long SNAPSHOT.tar`); verify reads .tar, .tar.zst (the `zstd`
binary) and .tar.gz. What is checked on the way in: the sha256 of the file when one is given, that no member escapes DIR, and that every module's .olean has the hash and the size the manifest recorded for the module it was built from.
The trust is in the hashes, not in where the file came from: an untrusted mirror can serve it.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
import sys
import tarfile
from pathlib import Path


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def collect(olean_dir: Path) -> list[tuple[str, Path]]:
    """every .olean under DIR/TengaiData, as (member name, file), sorted"""
    base = olean_dir / "TengaiData"
    if not base.is_dir():
        raise SystemExit(f"pack: {base} is not a directory")
    out = [(p.relative_to(olean_dir).as_posix(), p) for p in sorted(base.rglob("*.olean"))]
    if not out:
        raise SystemExit(f"pack: no .olean under {base}")
    return out


def pack(olean_dir: Path, manifest: Path, out: Path, indexes: Path | None = None, legal: Path | None = None) -> dict:
    files = collect(olean_dir)
    m = json.loads(manifest.read_text(encoding="utf-8"))
    extra = [(f"indexes/{p.name}", p.read_bytes()) for p in sorted(indexes.iterdir()) if p.is_file()] if indexes is not None else []
    # the licence texts and notices (tools/release/licences.py) travel inside the archive: a copy of the snapshot is a copy with them
    extra += (
        [(f"legal/{p.relative_to(legal).as_posix()}", p.read_bytes()) for p in sorted(legal.rglob("*")) if p.is_file()]
        if legal is not None
        else []
    )
    entries = [("manifest.json", manifest.read_bytes()), *[(name, p.read_bytes()) for name, p in files], *extra]
    with tarfile.open(out, "w", format=tarfile.PAX_FORMAT) as tar:
        for name, data in entries:
            info = tarfile.TarInfo(name)
            info.size, info.mtime, info.mode, info.uid, info.gid, info.uname, info.gname = len(data), 0, 0o644, 0, 0, "", ""
            tar.addfile(info, io.BytesIO(data))
    return {
        "members": [n for n, _ in entries],
        "sha256": sha256_file(out),
        "modules": len(files),
        "manifest_theorems": len(m.get("theorems", [])),
    }


def open_tar(path: Path) -> tarfile.TarFile:
    if path.suffix == ".zst":
        data = subprocess.run(["zstd", "-d", "-c", str(path)], capture_output=True, check=True).stdout
        return tarfile.open(fileobj=io.BytesIO(data), mode="r:")
    return tarfile.open(path, "r:*")


def verify_layers(manifest: dict, into: Path, oleans: list[Path]) -> None:
    """manifest schema 2 (a promotion in layers): the snapshot holds exactly the layers the manifest lists, each with the size and the sha256 it recorded, and every layer imports only layers of the manifest"""
    layers = manifest.get("layers") or []
    if not layers:
        raise SystemExit("verify: the manifest (schema 2) lists no layers")
    modules = {x["module"] for x in layers}
    want = {x["module"]: x["olean"] for x in layers}
    have = {p.relative_to(into).with_suffix("").as_posix().replace("/", "."): p for p in oleans}
    if set(have) != modules:
        raise SystemExit(
            f"verify: the snapshot and the manifest list other layers: missing {sorted(modules - set(have))}, not in the manifest {sorted(set(have) - modules)}"
        )
    for module, rec in want.items():
        got = {"bytes": have[module].stat().st_size, "sha256": sha256_file(have[module])}
        if got["bytes"] != rec["bytes"] or got["sha256"] != rec["sha256"]:
            raise SystemExit(f"verify: {module} differs from the manifest ({got['sha256'][:12]} vs {rec['sha256'][:12]})")
    for x in layers:
        unknown = [m for m in x["imports"] if m not in modules]
        if unknown:
            raise SystemExit(f"verify: {x['module']} imports {unknown}, which the manifest does not list")


def verify_indexes(manifest: dict, into: Path) -> None:
    """the indexes the manifest lists (schema 2, `indexes`): exactly those files are in `indexes/`, each with the size and the sha256 the manifest recorded; files there that the manifest does not list are refused"""
    listed = (manifest.get("indexes") or {}).get("files") or {}
    folder = into / "indexes"
    have = {p.name: p for p in sorted(folder.iterdir()) if p.is_file()} if folder.is_dir() else {}
    if set(have) != set(listed):
        raise SystemExit(
            f"verify: the snapshot and the manifest list other indexes: missing {sorted(set(listed) - set(have))}, not in the manifest {sorted(set(have) - set(listed))}"
        )
    for name, rec in listed.items():
        got = {"bytes": have[name].stat().st_size, "sha256": sha256_file(have[name])}
        if got["bytes"] != rec["bytes"] or got["sha256"] != rec["sha256"]:
            raise SystemExit(f"verify: the index {name} differs from the manifest ({got['sha256'][:12]} vs {rec['sha256'][:12]})")


def verify_legal(manifest: dict, into: Path) -> None:
    """the licence texts the manifest lists (`legal`): exactly those files are under `legal/`, each with the size and the sha256 the manifest recorded; a manifest without `legal` has none"""
    listed = (manifest.get("legal") or {}).get("files") or {}
    folder = into / "legal"
    have = {p.relative_to(folder).as_posix(): p for p in sorted(folder.rglob("*")) if p.is_file()} if folder.is_dir() else {}
    if set(have) != set(listed):
        raise SystemExit(
            f"verify: the snapshot and the manifest list other legal files: missing {sorted(set(listed) - set(have))}, not in the manifest {sorted(set(have) - set(listed))}"
        )
    for name, rec in listed.items():
        got = {"bytes": have[name].stat().st_size, "sha256": sha256_file(have[name])}
        if got["bytes"] != rec["bytes"] or got["sha256"] != rec["sha256"]:
            raise SystemExit(f"verify: the legal file {name} differs from the manifest ({got['sha256'][:12]} vs {rec['sha256'][:12]})")


def verify(snapshot: Path, into: Path, sha256: str | None = None) -> dict:
    if sha256 is not None and sha256_file(snapshot) != sha256:
        raise SystemExit(f"verify: {snapshot.name} does not have the sha256 {sha256}")
    into = into.resolve()
    into.mkdir(parents=True, exist_ok=True)
    with open_tar(snapshot) as tar:
        for m in tar.getmembers():
            target = (into / m.name).resolve()
            if not m.isfile() or into not in target.parents:
                raise SystemExit(f"verify: refusing member {m.name!r} (not a plain file inside the target)")
        tar.extractall(into, filter="data")
    manifest = json.loads((into / "manifest.json").read_text(encoding="utf-8"))
    oleans = sorted((into / "TengaiData").rglob("*.olean"))
    if not oleans:
        raise SystemExit("verify: the snapshot holds no .olean")
    if manifest.get("schema") == 2:
        verify_layers(manifest, into, oleans)
        verify_indexes(manifest, into)
        verify_legal(manifest, into)
    else:
        recorded = (manifest.get("artifact") or {}).get("olean")
        if recorded is None:
            raise SystemExit("verify: the manifest records no olean (a transplant that did not finish)")
        if len(oleans) != 1:
            raise SystemExit(f"verify: manifest schema 1 records one module, the snapshot holds {len(oleans)}")
        got = {"bytes": oleans[0].stat().st_size, "sha256": sha256_file(oleans[0])}
        if got["bytes"] != recorded["bytes"] or got["sha256"] != recorded["sha256"]:
            raise SystemExit(f"verify: {oleans[0].name} differs from the manifest ({got['sha256'][:12]} vs {recorded['sha256'][:12]})")
    checks = manifest.get("checks", {})
    return {
        "into": str(into),
        "lean_path": str(into),
        "modules": [p.relative_to(into).as_posix() for p in oleans],
        "checks": {k: (v if not isinstance(v, dict) else v.get("status", v.get("ok", "recorded"))) for k, v in checks.items()},
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pack")
    p.add_argument("--olean-dir", required=True)
    p.add_argument("--manifest", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--indexes", help="a directory of retrieval indexes: its files go into the archive under indexes/")
    p.add_argument(
        "--legal", help="a directory of licence texts and notices (tools/release/licences.py): its files go into the archive under legal/"
    )
    v = sub.add_parser("verify")
    v.add_argument("snapshot")
    v.add_argument("--sha256")
    v.add_argument("--into", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "pack":
        print(
            json.dumps(
                pack(
                    Path(a.olean_dir),
                    Path(a.manifest),
                    Path(a.out),
                    Path(a.indexes) if a.indexes else None,
                    Path(a.legal) if a.legal else None,
                ),
                sort_keys=True,
            )
        )
    else:
        print(json.dumps(verify(Path(a.snapshot), Path(a.into), a.sha256), sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
