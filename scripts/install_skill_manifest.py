#!/usr/bin/env python3
"""Install repo-backed Hermes skills from a sanitized manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "deploy/k8s/skills.lock.example.json"


def hermes_home() -> Path:
    return Path(os.getenv("HERMES_HOME", Path.home() / ".hermes")).expanduser()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    skills = data.get("skills")
    if not isinstance(skills, list):
        raise ValueError(f"{path} must contain a top-level skills list")
    return skills


def install_manifest(path: Path, *, dest_home: Path | None = None, dry_run: bool = False) -> list[dict[str, Any]]:
    dest_home = dest_home or hermes_home()
    results = []
    for spec in load_manifest(path):
        name = str(spec.get("name") or "").strip()
        rel = str(spec.get("repo_path") or "").strip()
        if not name or not rel:
            raise ValueError("each skill entry requires name and repo_path")
        source = (ROOT / rel).resolve()
        if not source.is_file():
            results.append({"name": name, "action": "missing_source", "source": str(source)})
            continue
        expected = spec.get("sha256")
        actual = sha256_file(source)
        if expected and expected != actual:
            results.append({"name": name, "action": "hash_mismatch", "expected": expected, "actual": actual})
            continue
        dest_rel = Path(rel)
        if dest_rel.parts and dest_rel.parts[0] in {"skills", "optional-skills"}:
            dest_rel = Path(*dest_rel.parts[1:])
        dest = dest_home / "skills" / dest_rel
        if dry_run:
            results.append({"name": name, "action": "install", "dry_run": True, "dest": str(dest)})
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        results.append({"name": name, "action": "install", "dest": str(dest), "sha256": actual})
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--hermes-home", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    results = install_manifest(args.manifest, dest_home=args.hermes_home, dry_run=args.dry_run)
    if args.json:
        print(json.dumps({"results": results}, indent=2))
    else:
        for item in results:
            print(f"{item['action']}: {item['name']} {item.get('dest', item.get('source', ''))}".rstrip())
    return 1 if any(item["action"] in {"missing_source", "hash_mismatch"} for item in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
