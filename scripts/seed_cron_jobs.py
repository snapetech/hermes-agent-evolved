#!/usr/bin/env python3
"""Seed sanitized Hermes cron jobs from a JSON manifest.

The manifest is public-safe: it stores prompts, schedules, skills, and delivery
mode, but not live output, private origins, channel IDs, or tokens.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "deploy/k8s/cron-seed.example.json"


def load_manifest(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    jobs = data.get("jobs")
    if not isinstance(jobs, list):
        raise ValueError(f"{path} must contain a top-level jobs list")
    return jobs


def sanitize_updates(job: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "prompt",
        "schedule",
        "skills",
        "skill",
        "model",
        "provider",
        "base_url",
        "script",
        "deliver",
        "enabled",
    }
    return {key: job[key] for key in allowed if key in job}


def seed_jobs(path: Path, *, dry_run: bool = False) -> list[dict[str, Any]]:
    from cron.jobs import create_job, load_jobs, update_job

    existing = {job.get("name"): job for job in load_jobs() if job.get("name")}
    results = []
    for spec in load_manifest(path):
        name = str(spec.get("name") or "").strip()
        if not name:
            raise ValueError("each cron seed job requires a name")
        updates = sanitize_updates(spec)
        updates.setdefault("deliver", "local")
        updates.setdefault("prompt", "")
        updates.setdefault("schedule", "0 9 * * 1")
        if name in existing:
            if dry_run:
                results.append({"name": name, "action": "update", "dry_run": True})
            else:
                updated = update_job(existing[name]["id"], updates)
                results.append({"name": name, "action": "update", "id": updated.get("id") if updated else existing[name]["id"]})
        else:
            if dry_run:
                results.append({"name": name, "action": "create", "dry_run": True})
            else:
                created = create_job(name=name, **updates)
                results.append({"name": name, "action": "create", "id": created["id"]})
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    results = seed_jobs(args.manifest, dry_run=args.dry_run)
    if args.json:
        print(json.dumps({"results": results}, indent=2))
    else:
        for item in results:
            suffix = " (dry-run)" if item.get("dry_run") else f" {item.get('id', '')}".rstrip()
            print(f"{item['action']}: {item['name']}{suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
