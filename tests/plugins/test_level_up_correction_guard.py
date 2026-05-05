"""Tests for the fork's level-up correction guard."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _load_correction_guard():
    path = Path(__file__).resolve().parents[2] / "plugins" / "level-up" / "correction_guard.py"
    spec = importlib.util.spec_from_file_location("test_level_up_correction_guard_module", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_correction_guard_skips_simple_runtime_apt_installs(tmp_path, monkeypatch):
    guard = _load_correction_guard()
    home = tmp_path / "hermes"
    harvest = home / "level_up" / "harvest"
    harvest.mkdir(parents=True)
    (harvest / "corrections.jsonl").write_text(
        json.dumps(
            {
                "context": "Agent assumed it could not install system packages with sudo apt-get",
                "fix": "In the Hermes pod, passwordless sudo is available for apt installs.",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("HERMES_HOME", str(home))
    guard._CACHE = {"ts": 0.0, "entries": []}

    result = guard.pre_tool_call_hook(
        "terminal",
        {
            "command": (
                "bash -lc 'sudo -n apt-get update && "
                "sudo -n apt-get install -y --no-install-recommends tesseract-ocr'"
            )
        },
    )

    assert result is None


def test_correction_guard_still_blocks_non_apt_overlap(tmp_path, monkeypatch):
    guard = _load_correction_guard()
    home = tmp_path / "hermes"
    harvest = home / "level_up" / "harvest"
    harvest.mkdir(parents=True)
    (harvest / "avoid.jsonl").write_text(
        json.dumps({"avoid": "Never run dangerous cleanup with rm recursive force in workspace"}) + "\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("HERMES_HOME", str(home))
    guard._CACHE = {"ts": 0.0, "entries": []}

    result = guard.pre_tool_call_hook("terminal", {"command": "dangerous cleanup recursive force workspace"})

    assert result is not None
    assert result["action"] == "block"
