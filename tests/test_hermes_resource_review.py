"""Tests for the Hermes K3s resource review helper."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parent.parent / "deploy/k8s/hermes-resource-review.py"


def load_module():
    spec = importlib.util.spec_from_file_location("hermes_resource_review", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_quantity_parsers_handle_kubernetes_units():
    review = load_module()

    assert review.parse_cpu_m("250m") == 250
    assert review.parse_cpu_m("2") == 2000
    assert review.parse_cpu_m("1000000n") == 1
    assert review.parse_mem_mi("256Mi") == 256
    assert review.parse_mem_mi("1Gi") == 1024
    assert review.parse_mem_mi("1024Ki") == 1


def test_parse_top_pod_containers_extracts_usage_rows():
    review = load_module()

    rows = review.parse_top_pod_containers(
        "hermes-gateway-abc gateway 850m 900Mi\n"
        "hermes-gateway-abc llama-admission-proxy 10m 64Mi\n"
    )

    assert rows == [
        review.ContainerUsage("hermes-gateway-abc", "gateway", 850, 900),
        review.ContainerUsage("hermes-gateway-abc", "llama-admission-proxy", 10, 64),
    ]


def test_recommend_flags_high_usage_and_oomkill():
    review = load_module()

    resources = [
        review.ContainerResources(
            workload_kind="Deployment",
            workload_name="hermes-gateway",
            container_name="gateway",
            cpu_request_m=250,
            cpu_limit_m=2000,
            mem_request_mi=1024,
            mem_limit_mi=4096,
        )
    ]
    usage = [review.ContainerUsage("hermes-gateway-abc", "gateway", 900, 3900)]
    restarts = [review.RestartSignal("hermes-gateway-abc", "gateway", 1, "OOMKilled")]

    recs = review.recommend(resources, usage, restarts)

    assert any(rec.metric == "cpu_request" for rec in recs)
    assert any(rec.metric == "memory_request" for rec in recs)
    assert any(rec.metric == "memory_limit" for rec in recs)
    assert any(rec.metric == "restart" and rec.severity == "high" for rec in recs)


def test_local_manifest_defaults_find_gateway_resources():
    review = load_module()

    docs = review.load_yaml_documents([review.SCRIPT_DIR / "deployment.yaml"])
    resources = review.resources_from_docs(docs)

    gateway = next(item for item in resources if item.workload_name == "hermes-gateway" and item.container_name == "gateway")
    assert gateway.cpu_request_m == 250
    assert gateway.mem_request_mi == 1024


def test_render_report_is_advisory_not_mutating():
    review = load_module()

    report = review.render_report(
        resources=[],
        usages=[],
        restarts=[],
        recs=[],
        namespace="hermes",
        source="local",
    )

    assert "This report is advisory" in report
    assert "does not patch Kubernetes resources or edit manifests" in report
    assert "No resource changes recommended" in report
