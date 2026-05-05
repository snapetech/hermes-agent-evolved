#!/usr/bin/env python3
"""Review Hermes K3s resource usage and emit bounded recommendations.

This helper is intentionally report-first. It reads Kubernetes metrics and
resource declarations, then writes a Markdown report with suggested request or
limit changes. It does not patch live workloads or edit manifests.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except Exception:  # pragma: no cover - production image includes PyYAML
    yaml = None


NAMESPACE = os.getenv("HERMES_NAMESPACE", "hermes")
HERMES_HOME = Path(os.getenv("HERMES_HOME", "/opt/data")).expanduser()
STATE_DIR = Path(
    os.getenv(
        "HERMES_RESOURCE_REVIEW_STATE_DIR",
        str(HERMES_HOME / "self-improvement" / "resource-review"),
    )
)
REPORTS_DIR = Path(os.getenv("HERMES_RESOURCE_REVIEW_REPORTS_DIR", str(STATE_DIR / "reports")))
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_MANIFEST_ROOT = Path("/app/deploy/k8s") if Path("/app/deploy/k8s").exists() else SCRIPT_DIR
MANIFEST_ROOT = Path(os.getenv("HERMES_RESOURCE_REVIEW_MANIFEST_ROOT", str(DEFAULT_MANIFEST_ROOT)))
DEFAULT_FILES = ("deployment.yaml", "self-improvement-cron.yaml", "profile-workers.yaml", "hindsight.yaml")


CPU_RE = re.compile(r"^([0-9.]+)(n|u|m)?$")
MEM_RE = re.compile(r"^([0-9.]+)(Ki|Mi|Gi|Ti|K|M|G|T)?$")


@dataclass(frozen=True)
class ContainerResources:
    workload_kind: str
    workload_name: str
    container_name: str
    cpu_request_m: int | None
    cpu_limit_m: int | None
    mem_request_mi: int | None
    mem_limit_mi: int | None


@dataclass(frozen=True)
class ContainerUsage:
    pod_name: str
    container_name: str
    cpu_m: int
    mem_mi: int


@dataclass(frozen=True)
class RestartSignal:
    pod_name: str
    container_name: str
    restart_count: int
    reason: str


@dataclass(frozen=True)
class Recommendation:
    severity: str
    workload: str
    container: str
    metric: str
    current: str
    observed: str
    suggestion: str
    rationale: str


def parse_cpu_m(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    match = CPU_RE.match(text)
    if not match:
        return None
    number = float(match.group(1))
    suffix = match.group(2) or ""
    if suffix == "n":
        return max(1, math.ceil(number / 1_000_000))
    if suffix == "u":
        return max(1, math.ceil(number / 1_000))
    if suffix == "m":
        return max(1, math.ceil(number))
    return max(1, math.ceil(number * 1000))


def parse_mem_mi(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    match = MEM_RE.match(text)
    if not match:
        return None
    number = float(match.group(1))
    suffix = match.group(2) or "Mi"
    factors = {
        "Ki": 1 / 1024,
        "Mi": 1,
        "Gi": 1024,
        "Ti": 1024 * 1024,
        "K": 1 / 1000,
        "M": 1,
        "G": 1000,
        "T": 1000 * 1000,
    }
    return max(1, math.ceil(number * factors.get(suffix, 1)))


def fmt_cpu(value_m: int | None) -> str:
    if value_m is None:
        return "unset"
    if value_m >= 1000 and value_m % 1000 == 0:
        return str(value_m // 1000)
    return f"{value_m}m"


def fmt_mem(value_mi: int | None) -> str:
    if value_mi is None:
        return "unset"
    if value_mi >= 1024 and value_mi % 1024 == 0:
        return f"{value_mi // 1024}Gi"
    return f"{value_mi}Mi"


def _run(args: list[str], timeout: int = 20) -> str:
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, timeout=timeout)


def load_yaml_documents(paths: list[Path]) -> list[dict[str, Any]]:
    if yaml is None:
        return []
    docs: list[dict[str, Any]] = []
    for path in paths:
        if not path.exists():
            continue
        for doc in yaml.safe_load_all(path.read_text(encoding="utf-8")):
            if isinstance(doc, dict):
                docs.append(doc)
    return docs


def get_path(doc: dict[str, Any], path: list[str], default: Any = None) -> Any:
    current: Any = doc
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def resources_from_docs(docs: list[dict[str, Any]]) -> list[ContainerResources]:
    out: list[ContainerResources] = []
    for doc in docs:
        kind = str(doc.get("kind") or "")
        name = str(get_path(doc, ["metadata", "name"], "unknown"))
        if kind == "CronJob":
            containers = get_path(doc, ["spec", "jobTemplate", "spec", "template", "spec", "containers"], [])
        else:
            containers = get_path(doc, ["spec", "template", "spec", "containers"], [])
        if not isinstance(containers, list):
            continue
        for container in containers:
            if not isinstance(container, dict):
                continue
            resources = container.get("resources") if isinstance(container.get("resources"), dict) else {}
            requests = resources.get("requests") if isinstance(resources.get("requests"), dict) else {}
            limits = resources.get("limits") if isinstance(resources.get("limits"), dict) else {}
            out.append(
                ContainerResources(
                    workload_kind=kind or "Unknown",
                    workload_name=name,
                    container_name=str(container.get("name") or "unknown"),
                    cpu_request_m=parse_cpu_m(requests.get("cpu")),
                    cpu_limit_m=parse_cpu_m(limits.get("cpu")),
                    mem_request_mi=parse_mem_mi(requests.get("memory")),
                    mem_limit_mi=parse_mem_mi(limits.get("memory")),
                )
            )
    return out


def load_live_resource_docs(namespace: str) -> list[dict[str, Any]]:
    if yaml is None:
        return []
    docs: list[dict[str, Any]] = []
    for resource in ("deployments", "cronjobs"):
        try:
            text = _run(["kubectl", "-n", namespace, "get", resource, "-o", "yaml"])
        except Exception:
            continue
        parsed = yaml.safe_load(text)
        for item in parsed.get("items", []) if isinstance(parsed, dict) else []:
            if isinstance(item, dict):
                docs.append(item)
    return docs


def parse_top_pod_containers(text: str) -> list[ContainerUsage]:
    usages: list[ContainerUsage] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.lower().startswith("pod "):
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        cpu = parse_cpu_m(parts[2])
        mem = parse_mem_mi(parts[3])
        if cpu is None or mem is None:
            continue
        usages.append(ContainerUsage(pod_name=parts[0], container_name=parts[1], cpu_m=cpu, mem_mi=mem))
    return usages


def collect_live_usage(namespace: str) -> tuple[list[ContainerUsage], str | None]:
    try:
        text = _run(["kubectl", "-n", namespace, "top", "pod", "--containers", "--no-headers"])
    except Exception as exc:
        return [], str(exc)
    return parse_top_pod_containers(text), None


def collect_restart_signals(namespace: str) -> tuple[list[RestartSignal], str | None]:
    try:
        text = _run(["kubectl", "-n", namespace, "get", "pods", "-o", "json"])
    except Exception as exc:
        return [], str(exc)
    try:
        parsed = json.loads(text)
    except Exception as exc:
        return [], str(exc)
    signals: list[RestartSignal] = []
    for pod in parsed.get("items", []):
        pod_name = str(get_path(pod, ["metadata", "name"], "unknown"))
        statuses = get_path(pod, ["status", "containerStatuses"], [])
        if not isinstance(statuses, list):
            continue
        for status in statuses:
            if not isinstance(status, dict):
                continue
            restarts = int(status.get("restartCount") or 0)
            last_state = status.get("lastState") if isinstance(status.get("lastState"), dict) else {}
            terminated = last_state.get("terminated") if isinstance(last_state.get("terminated"), dict) else {}
            reason = str(terminated.get("reason") or "")
            if restarts or reason:
                signals.append(
                    RestartSignal(
                        pod_name=pod_name,
                        container_name=str(status.get("name") or "unknown"),
                        restart_count=restarts,
                        reason=reason or "restart",
                    )
                )
    return signals, None


def _usage_by_container(usages: list[ContainerUsage]) -> dict[str, ContainerUsage]:
    latest: dict[str, ContainerUsage] = {}
    for usage in usages:
        latest[usage.container_name] = usage
    return latest


def _ceil_step(value: int, step: int) -> int:
    return int(math.ceil(value / step) * step)


def recommend(resources: list[ContainerResources], usages: list[ContainerUsage], restarts: list[RestartSignal]) -> list[Recommendation]:
    by_container = _usage_by_container(usages)
    restart_by_container: dict[str, list[RestartSignal]] = {}
    for signal in restarts:
        restart_by_container.setdefault(signal.container_name, []).append(signal)

    recs: list[Recommendation] = []
    for resource in resources:
        usage = by_container.get(resource.container_name)
        workload = f"{resource.workload_kind}/{resource.workload_name}"
        if usage:
            if resource.cpu_request_m and usage.cpu_m >= resource.cpu_request_m * 0.80:
                suggested = min(resource.cpu_limit_m or max(usage.cpu_m * 2, resource.cpu_request_m), _ceil_step(max(usage.cpu_m * 2, 100), 50))
                recs.append(
                    Recommendation(
                        severity="medium",
                        workload=workload,
                        container=resource.container_name,
                        metric="cpu_request",
                        current=fmt_cpu(resource.cpu_request_m),
                        observed=fmt_cpu(usage.cpu_m),
                        suggestion=f"raise request toward {fmt_cpu(suggested)} after confirming this is sustained",
                        rationale="observed CPU is at least 80% of the current request in the latest metrics snapshot",
                    )
                )
            elif resource.cpu_request_m and usage.cpu_m <= resource.cpu_request_m * 0.20 and resource.cpu_request_m >= 250:
                recs.append(
                    Recommendation(
                        severity="low",
                        workload=workload,
                        container=resource.container_name,
                        metric="cpu_request",
                        current=fmt_cpu(resource.cpu_request_m),
                        observed=fmt_cpu(usage.cpu_m),
                        suggestion="consider lowering only after repeated low-usage snapshots",
                        rationale="single snapshot is far below request, but down-sizing needs repeated evidence",
                    )
                )
            if resource.cpu_limit_m and usage.cpu_m >= resource.cpu_limit_m * 0.90:
                recs.append(
                    Recommendation(
                        severity="high",
                        workload=workload,
                        container=resource.container_name,
                        metric="cpu_limit",
                        current=fmt_cpu(resource.cpu_limit_m),
                        observed=fmt_cpu(usage.cpu_m),
                        suggestion="raise CPU limit or investigate runaway work before increasing",
                        rationale="observed CPU is near the current limit",
                    )
                )
            if resource.mem_request_mi and usage.mem_mi >= resource.mem_request_mi * 0.80:
                target = _ceil_step(max(int(usage.mem_mi * 1.5), resource.mem_request_mi + 128), 128)
                if resource.mem_limit_mi:
                    target = min(target, resource.mem_limit_mi)
                recs.append(
                    Recommendation(
                        severity="medium",
                        workload=workload,
                        container=resource.container_name,
                        metric="memory_request",
                        current=fmt_mem(resource.mem_request_mi),
                        observed=fmt_mem(usage.mem_mi),
                        suggestion=f"raise request toward {fmt_mem(target)} after confirming this is sustained",
                        rationale="observed memory is at least 80% of the current request in the latest metrics snapshot",
                    )
                )
            if resource.mem_limit_mi and usage.mem_mi >= resource.mem_limit_mi * 0.90:
                recs.append(
                    Recommendation(
                        severity="high",
                        workload=workload,
                        container=resource.container_name,
                        metric="memory_limit",
                        current=fmt_mem(resource.mem_limit_mi),
                        observed=fmt_mem(usage.mem_mi),
                        suggestion="raise memory limit or reduce memory use before OOM risk becomes acute",
                        rationale="observed memory is near the current limit",
                    )
                )
        for signal in restart_by_container.get(resource.container_name, []):
            if signal.reason == "OOMKilled":
                recs.append(
                    Recommendation(
                        severity="high",
                        workload=workload,
                        container=resource.container_name,
                        metric="restart",
                        current=f"{signal.restart_count} restart(s)",
                        observed="OOMKilled",
                        suggestion="raise memory limit/request or reduce workload memory before restarting again",
                        rationale=f"{signal.pod_name} last terminated with OOMKilled",
                    )
                )
    return recs


def render_report(
    resources: list[ContainerResources],
    usages: list[ContainerUsage],
    restarts: list[RestartSignal],
    recs: list[Recommendation],
    *,
    namespace: str,
    usage_error: str | None = None,
    restart_error: str | None = None,
    source: str = "live",
) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    lines = [
        "# Hermes K3s Resource Review",
        "",
        f"- generated_at: {now}",
        f"- namespace: `{namespace}`",
        f"- resource_source: {source}",
        f"- containers_with_declared_resources: {len(resources)}",
        f"- live_usage_rows: {len(usages)}",
        f"- restart_signals: {len(restarts)}",
        "",
        "This report is advisory. It does not patch Kubernetes resources or edit manifests.",
        "Apply changes only through an explicit operator-approved manifest or deployment change.",
        "",
    ]
    if usage_error:
        lines.extend(["## Metrics Availability", "", f"- `kubectl top pod --containers` failed or was unavailable: `{usage_error}`", ""])
    if restart_error:
        lines.extend(["## Restart Signal Availability", "", f"- pod restart inspection failed or was unavailable: `{restart_error}`", ""])

    lines.extend(["## Recommendations", ""])
    if not recs:
        lines.append("- No resource changes recommended from the available evidence.")
    else:
        for rec in recs:
            lines.extend(
                [
                    f"- **{rec.severity}** `{rec.workload}` container `{rec.container}` `{rec.metric}`",
                    f"  - current: {rec.current}",
                    f"  - observed: {rec.observed}",
                    f"  - suggestion: {rec.suggestion}",
                    f"  - rationale: {rec.rationale}",
                ]
            )
    lines.append("")

    lines.extend(["## Declared Resources", ""])
    for resource in resources:
        lines.append(
            "- "
            f"`{resource.workload_kind}/{resource.workload_name}` "
            f"container `{resource.container_name}`: "
            f"requests cpu={fmt_cpu(resource.cpu_request_m)} memory={fmt_mem(resource.mem_request_mi)}; "
            f"limits cpu={fmt_cpu(resource.cpu_limit_m)} memory={fmt_mem(resource.mem_limit_mi)}"
        )
    if not resources:
        lines.append("- No resource declarations found.")
    lines.append("")

    lines.extend(["## Latest Usage Snapshot", ""])
    for usage in usages:
        lines.append(f"- `{usage.pod_name}` container `{usage.container_name}`: cpu={fmt_cpu(usage.cpu_m)} memory={fmt_mem(usage.mem_mi)}")
    if not usages:
        lines.append("- No live usage snapshot available.")
    lines.append("")

    if restarts:
        lines.extend(["## Restart Signals", ""])
        for signal in restarts:
            lines.append(
                f"- `{signal.pod_name}` container `{signal.container_name}`: "
                f"restarts={signal.restart_count} reason={signal.reason}"
            )
        lines.append("")

    lines.extend(
        [
            "## Guardrails",
            "",
            "- Prefer repeated metrics snapshots before lowering requests.",
            "- Treat OOMKilled, near-limit memory, and sustained CPU saturation as higher-confidence signals.",
            "- Do not change live Deployment, CronJob, Secret, PVC, ingress, or node policy from this report alone.",
            "- If a change is warranted, patch manifests in git, run targeted tests/checks, then deploy with explicit approval.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_report(text: str) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = REPORTS_DIR / f"resource-review-{stamp}.md"
    path.write_text(text, encoding="utf-8")
    latest = REPORTS_DIR / "latest.md"
    latest.write_text(text, encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Review Hermes K3s resource requests/limits and live usage.")
    parser.add_argument("--namespace", default=NAMESPACE)
    parser.add_argument("--manifest-root", type=Path, default=MANIFEST_ROOT)
    parser.add_argument("--manifest", action="append", default=[], help="Additional manifest file to inspect")
    parser.add_argument("--local-only", action="store_true", help="Skip kubectl and inspect local manifests only")
    parser.add_argument("--write-report", action="store_true", help="Write report under the resource-review state directory")
    args = parser.parse_args(argv)

    source = "local"
    docs: list[dict[str, Any]] = []
    usage: list[ContainerUsage] = []
    restarts: list[RestartSignal] = []
    usage_error = None
    restart_error = None

    if not args.local_only:
        docs = load_live_resource_docs(args.namespace)
        usage, usage_error = collect_live_usage(args.namespace)
        restarts, restart_error = collect_restart_signals(args.namespace)
        if docs:
            source = "live"

    if not docs:
        manifest_paths = [args.manifest_root / name for name in DEFAULT_FILES]
        manifest_paths.extend(Path(p) for p in args.manifest)
        docs = load_yaml_documents(manifest_paths)
        source = "local"

    resources = resources_from_docs(docs)
    recs = recommend(resources, usage, restarts)
    report = render_report(
        resources,
        usage,
        restarts,
        recs,
        namespace=args.namespace,
        usage_error=usage_error,
        restart_error=restart_error,
        source=source,
    )
    if args.write_report:
        path = write_report(report)
        print(f"wrote {path}")
        print(f"updated {REPORTS_DIR / 'latest.md'}")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
