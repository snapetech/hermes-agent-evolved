from __future__ import annotations

import json
from pathlib import Path


def test_build_packet_uses_deterministic_branch_and_paths(monkeypatch, tmp_path):
    home = tmp_path / ".hermes"
    monkeypatch.setenv("HERMES_HOME", str(home))

    from scripts import local_llm_handoff_packet as packet

    built = packet.build_packet(
        kind="promotion",
        title="Promote Qwen3.6 27B Q5_K_S",
        summary="beats retained lane",
        reasoning="repeat benches show better utility without regression",
        report_path="/tmp/latest.md",
        evidence=["benchmarks/llm/model_benchmark_scorecard.md"],
    )

    assert built["branch_name"].startswith("llm-handoff/")
    assert built["recipient"] == "keith@snape.tech"
    assert built["paths"]["pr_body_md"].endswith("/pr_body.md")


def test_write_packet_materializes_files(monkeypatch, tmp_path):
    home = tmp_path / ".hermes"
    monkeypatch.setenv("HERMES_HOME", str(home))

    from scripts import local_llm_handoff_packet as packet

    built = packet.build_packet(
        kind="remediation",
        title="Fix degraded qwen lane",
        summary="repair runtime settings",
        reasoning="nightly review found a repeatable regression and bounded fix",
        report_path="/tmp/latest.md",
    )
    packet.write_packet(built)

    packet_json = Path(built["paths"]["packet_json"])
    pr_body = Path(built["paths"]["pr_body_md"])
    email_txt = Path(built["paths"]["email_txt"])

    assert packet_json.exists()
    assert pr_body.exists()
    assert email_txt.exists()
    assert json.loads(packet_json.read_text(encoding="utf-8"))["kind"] == "remediation"
    assert "Human Approval Required" in pr_body.read_text(encoding="utf-8")
    assert "keith@snape.tech" in email_txt.read_text(encoding="utf-8")
