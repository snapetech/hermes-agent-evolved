from __future__ import annotations

from scripts.upstream_sync_triage import TriageData, render_report


def test_render_report_includes_selective_policy_and_overlap_sections():
    data = TriageData(
        private_ref="refs/remotes/origin/main",
        upstream_ref="refs/remotes/upstream-sync/main",
        private_sha="a" * 40,
        upstream_sha="b" * 40,
        merge_base="c" * 40,
        private_only_count=2,
        upstream_only_count=3,
        private_only_commits=["1111111 local: keep repo-first"],
        upstream_only_commits=["2222222 upstream: fix gateway cleanup"],
        upstream_diff_stat=[" gateway/run.py | 10 +++++-----"],
        overlap_files=["gateway/run.py", "tools/skills_sync.py"],
        design_sensitive_overlap=["gateway/run.py"],
        keep_local_overlap=["gateway/run.py", "tools/skills_sync.py"],
    )

    report = render_report(data)

    assert "Selective Merge Policy" in report
    assert "Do not blind-merge upstream into the private deployment fork." in report
    assert "Design-Sensitive Overlap" in report
    assert "Keep-Local-Method Overlap" in report
    assert "gateway/run.py" in report
    assert "tools/skills_sync.py" in report
    assert "Adapt upstream bug fixes around the local method instead of replacing it wholesale." in report
