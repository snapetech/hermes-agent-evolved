"""Regression tests for Snapetech deployment customizations."""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parent.parent
K8S = ROOT / "deploy" / "k8s"


def _load_yaml_docs(path: Path) -> list[dict]:
    return [doc for doc in yaml.safe_load_all(path.read_text(encoding="utf-8")) if isinstance(doc, dict)]


def _cronjob_container(cronjob: dict) -> dict:
    containers = cronjob["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"]
    assert len(containers) == 1
    return containers[0]


def _env_map(container: dict) -> dict:
    return {item["name"]: item for item in container.get("env", [])}


def test_embedded_configmap_sources_are_byte_for_byte_synced():
    spec = importlib.util.spec_from_file_location(
        "sync_configmap_embeds", ROOT / "scripts" / "sync_configmap_embeds.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    configmap = yaml.safe_load((K8S / "configmap.yaml").read_text(encoding="utf-8"))
    data = configmap["data"]

    for key, source_path in module.EMBEDS:
        assert key in data, f"{key} missing from hermes-bootstrap ConfigMap"
        expected = source_path.read_text(encoding="utf-8").rstrip("\n")
        actual = data[key].rstrip("\n")
        assert actual == expected, f"{key} is out of sync with {source_path}"


def test_all_custom_cronjobs_have_resource_bounds_and_safe_policy():
    cronjobs = {
        doc["metadata"]["name"]: doc
        for doc in _load_yaml_docs(K8S / "self-improvement-cron.yaml")
        if doc.get("kind") == "CronJob"
    }

    expected = {
        "hermes-edge-watch-quick",
        "hermes-edge-watch-daily",
        "hermes-edge-watch-weekly",
        "hermes-internal-introspection",
        "hermes-repo-sync",
        "hermes-node-image-prune",
        "hermes-resource-review",
    }
    assert expected <= set(cronjobs)

    for name in expected:
        cronjob = cronjobs[name]
        assert cronjob["spec"]["concurrencyPolicy"] == "Forbid"
        assert cronjob["spec"]["timeZone"] == "America/Winnipeg"
        assert cronjob["spec"]["jobTemplate"]["spec"]["backoffLimit"] == 1
        assert cronjob["spec"]["jobTemplate"]["spec"]["activeDeadlineSeconds"] <= 3600

        resources = _cronjob_container(cronjob).get("resources", {})
        assert resources.get("requests") == {"cpu": "100m", "memory": "256Mi"}
        assert resources.get("limits") == {"cpu": "1", "memory": "1Gi"}


def test_base_manifests_use_stable_local_image_not_commit_pins():
    manifest_paths = [
        K8S / "deployment.yaml",
        K8S / "self-improvement-cron.yaml",
        K8S / "profile-workers.yaml",
        K8S / "hindsight.yaml",
    ]

    for path in manifest_paths:
        text = path.read_text(encoding="utf-8")
        assert "hermes-agent-sudo:local" in text
        assert not re.search(r"hermes-agent-sudo:git-[0-9a-f]{40}", text), path

    deploy_script = (K8S / "github-main-deploy.sh").read_text(encoding="utf-8")
    assert 'STABLE_IMAGE_REF="${IMAGE_NAME}:local"' in deploy_script
    assert '-t "$STABLE_IMAGE_REF"' in deploy_script
    assert '"$DOCKER_BIN" save "$STABLE_IMAGE_REF" | ${CTR_IMPORT}' in deploy_script


def test_deploy_script_skips_docs_only_and_already_running_commits():
    deploy_script = (K8S / "github-main-deploy.sh").read_text(encoding="utf-8")

    assert "should_skip_deploy()" in deploy_script
    assert "HERMES_FORCE_DEPLOY" in deploy_script
    assert 'running_image=$(${KUBECTL} -n "$NAMESPACE" get deploy "$DEPLOYMENT"' in deploy_script
    assert 'if [ "$running_sha" = "$current_sha" ]' in deploy_script
    assert "only docs/meta files changed" in deploy_script
    for safe_path in (
        ":!docs/",
        ":!.github/",
        ":!HERMES_CHANGELOG.md",
        ":!README.md",
        ":!AGENTS.md",
    ):
        assert safe_path in deploy_script


def test_deployments_cap_revision_history_to_limit_rollout_churn():
    docs = []
    for path in (K8S / "deployment.yaml", K8S / "hindsight.yaml", K8S / "profile-workers.yaml"):
        docs.extend(_load_yaml_docs(path))
    deployments = {
        doc["metadata"]["name"]: doc
        for doc in docs
        if doc.get("kind") == "Deployment"
    }

    assert deployments["hermes-gateway"]["spec"]["revisionHistoryLimit"] == 3
    assert deployments["hindsight"]["spec"]["revisionHistoryLimit"] == 2
    assert deployments["hindsight-postgres"]["spec"]["revisionHistoryLimit"] == 2
    for name in ("hermes-worker-ops", "hermes-worker-coder", "hermes-worker-research"):
        assert deployments[name]["spec"]["replicas"] == 0
        assert deployments[name]["spec"]["revisionHistoryLimit"] == 1
        assert deployments[name]["spec"]["template"]["spec"]["nodeSelector"] == {
            "kubernetes.io/hostname": "node-a"
        }


def test_resource_review_cron_runs_weekly_and_writes_reports():
    cronjob = next(
        doc
        for doc in _load_yaml_docs(K8S / "self-improvement-cron.yaml")
        if doc.get("metadata", {}).get("name") == "hermes-resource-review"
    )
    pod_spec = cronjob["spec"]["jobTemplate"]["spec"]["template"]["spec"]
    container = _cronjob_container(cronjob)
    command = "\n".join(container["command"])

    assert cronjob["spec"]["schedule"] == "15 9 * * 5"
    assert cronjob["spec"]["timeZone"] == "America/Winnipeg"
    assert cronjob["spec"]["concurrencyPolicy"] == "Forbid"
    assert cronjob["spec"]["jobTemplate"]["spec"]["activeDeadlineSeconds"] == 900
    assert pod_spec["nodeSelector"] == {"kubernetes.io/hostname": "node-a"}
    assert "hermes-resource-review.py" in command
    assert "hermes_resource_review.py" in command
    assert "--write-report" in command
    assert "/opt/data/cron/output/resource-review" in command


def test_htui_wrapper_starts_blank_and_recovers_only_interrupted_turns():
    text = (K8S / "htui.sh").read_text(encoding="utf-8")

    assert "HERMES_TUI_CLIENT_ID=$tui_client_id /app/.venv/bin/hermes --tui\"" in text
    assert "HERMES_TUI_RECOVER_INTERRUPTED_ONLY=1" in text
    assert "HERMES_TUI_RECOVER_INTERRUPTED_ONLY=1 /app/.venv/bin/hermes --tui --continue" in text
    assert "remote_command=\"cd /app && HERMES_HOME=/opt/data /app/.venv/bin/hermes --tui --continue\"" not in text


def test_node_image_prune_cron_cleans_failed_work_and_prunes_k3s_images_safely():
    cronjob = next(
        doc
        for doc in _load_yaml_docs(K8S / "self-improvement-cron.yaml")
        if doc.get("metadata", {}).get("name") == "hermes-node-image-prune"
    )
    pod_spec = cronjob["spec"]["jobTemplate"]["spec"]["template"]["spec"]
    container = _cronjob_container(cronjob)
    command = "\n".join(container["command"])
    env = _env_map(container)

    assert cronjob["spec"]["schedule"] == "5 */6 * * *"
    assert cronjob["spec"]["concurrencyPolicy"] == "Forbid"
    assert cronjob["spec"]["jobTemplate"]["spec"]["activeDeadlineSeconds"] == 900
    assert pod_spec["nodeSelector"] == {"kubernetes.io/hostname": "node-a"}
    assert pod_spec["volumes"] == [
        {"name": "host-root", "hostPath": {"path": "/", "type": "Directory"}}
    ]
    assert container["securityContext"]["privileged"] is True
    assert container["volumeMounts"] == [{"name": "host-root", "mountPath": "/host"}]
    assert "kubectl delete pod -n hermes --field-selector=status.phase=Failed" in command
    assert 'awk \'$2 == "Failed" {print $1}\'' in command
    assert 'df -P /host' in command
    assert 'chroot /host k3s crictl --timeout "$timeout" rmi --prune' in command
    assert env["HERMES_PRUNE_MIN_USED_PERCENT"]["value"] == "75"
    assert env["HERMES_PRUNE_TIMEOUT"]["value"] == "120s"

    sudoers = (K8S / "host-wrappers" / "sudoers-node-a").read_text(encoding="utf-8")
    wrapper = (K8S / "host-wrappers" / "hermes-k3s-image-prune").read_text(encoding="utf-8")
    assert "/usr/local/sbin/hermes-k3s-image-prune" in sudoers
    assert 'k3s crictl --timeout "$timeout" rmi --prune' in wrapper


def test_edge_watch_cronjobs_have_expected_secret_and_pass_wiring():
    docs = _load_yaml_docs(K8S / "self-improvement-cron.yaml")
    edge_jobs = [doc for doc in docs if doc.get("metadata", {}).get("labels", {}).get("app.kubernetes.io/name") == "hermes-edge-watch"]
    assert {job["metadata"]["name"] for job in edge_jobs} == {
        "hermes-edge-watch-quick",
        "hermes-edge-watch-daily",
        "hermes-edge-watch-weekly",
    }

    for job in edge_jobs:
        pass_name = job["metadata"]["labels"]["hermes.snapetech/pass"]
        container = _cronjob_container(job)
        env = _env_map(container)
        assert env["HERMES_EDGE_WATCH_PASS"]["value"] == pass_name
        assert env["HERMES_FORK_REPO"]["value"] == "example-org/hermes-agent-private"
        assert env["HERMES_UPSTREAM_REPO"]["value"] == "NousResearch/hermes-agent"
        assert env["DISCORD_BOT_TOKEN"]["valueFrom"]["secretKeyRef"] == {
            "name": "hermes-discord",
            "key": "DISCORD_BOT_TOKEN",
        }
        assert env["GH_TOKEN"]["valueFrom"]["secretKeyRef"] == {"name": "hermes-github", "key": "token"}
        assert env["GITHUB_TOKEN"]["valueFrom"]["secretKeyRef"] == {"name": "hermes-github", "key": "token"}
        command = "\n".join(container["command"])
        assert "hermes-self-improvement-scan.py" in command
        assert "tee \"$log\"" in command


def test_introspection_cron_uses_report_first_runtime_and_persistent_state():
    cronjob = next(
        doc
        for doc in _load_yaml_docs(K8S / "self-improvement-cron.yaml")
        if doc.get("metadata", {}).get("name") == "hermes-internal-introspection"
    )
    container = _cronjob_container(cronjob)
    env = _env_map(container)
    assert env["HERMES_HOME"]["value"] == "/opt/data"
    assert env["HERMES_INTROSPECTION_STATE_DIR"]["value"] == "/opt/data/self-improvement/introspection"
    assert env["HERMES_INTROSPECTION_SESSION_DB"]["value"] == "/opt/data/state.db"
    command = "\n".join(container["command"])
    assert "hermes-introspection-scan.py" in command
    assert "--window-days 7 --session-limit 120" in command
    assert "/opt/data/cron/output/introspection" in command


def test_bootstrap_installs_agent_mcp_and_self_improvement_runtime_files():
    text = (K8S / "bootstrap-runtime.sh").read_text(encoding="utf-8")

    for expected in (
        "local-models.manifest.yaml",
        "shared-memory-mcp.py",
        "edge-watch-mcp.py",
        "desktop-bridge-mcp.py",
        "discord-wayland-monitor.py",
        '"hermes-memory"',
        '"hermes-edge-watch"',
        "[mcp_servers.hermes_memory]",
        "[mcp_servers.hermes_edge_watch]",
        "hermes-self-edit.py",
        "hermes_self_edit.py",
        "hermes-repo-sync.py",
        "hermes_repo_sync.py",
        "hermes-self-improvement-scan.py",
        "hermes_self_improvement_scan.py",
        "hermes-introspection-scan.py",
        "hermes_introspection_scan.py",
        "hermes-resource-review.py",
        "hermes_resource_review.py",
        "ensure_legacy_repo_alias",
        "orphaned-repos",
    ):
        assert expected in text
    assert "[ ! -s /opt/data/SOUL.md ]" in text
    assert "[ ! -s /opt/data/BOOT.md ]" in text


def test_deploy_config_explicitly_enables_required_runtime_plugins():
    config = yaml.safe_load((K8S / "configmap.yaml").read_text(encoding="utf-8"))["data"]["config.yaml"]
    parsed = yaml.safe_load(config)
    bootstrap = (K8S / "bootstrap-runtime.sh").read_text(encoding="utf-8")
    deployment = (K8S / "deployment.yaml").read_text(encoding="utf-8")

    assert parsed["plugins"]["enabled"] == ["runtime-control", "level-up", "mission-loop"]
    assert "mission_loop" in parsed["platform_toolsets"]["discord"]
    assert "mission_loop" in parsed["platform_toolsets"]["api_server"]
    assert "cp -R /app/plugins/mission-loop /opt/data/plugins/mission-loop" in bootstrap
    assert "cp -R /app/plugins/mission-loop /opt/data/plugins/mission-loop" in deployment


def test_repo_sync_cron_mirrors_pod_local_checkouts_to_self_pr_branch():
    cronjob = next(
        doc
        for doc in _load_yaml_docs(K8S / "self-improvement-cron.yaml")
        if doc.get("metadata", {}).get("name") == "hermes-repo-sync"
    )
    container = _cronjob_container(cronjob)
    env = _env_map(container)
    command = "\n".join(container["command"])

    assert cronjob["spec"]["schedule"] == "*/30 * * * *"
    assert cronjob["spec"]["concurrencyPolicy"] == "Forbid"
    assert "hermes-repo-sync.py" in command
    assert "hermes_repo_sync.py" in command
    assert "/opt/data/cron/output/repo-sync" in command
    assert env["HERMES_REPO_SYNC_TARGET"]["value"] == "/opt/data/workspace/hermes-agent-private"
    assert env["HERMES_REPO_SYNC_SOURCES"]["value"] == (
        "/opt/data/hermes-agent,/opt/data/home/hermes-agent-private,/opt/data/home/hermes-agent"
    )
    assert env["HERMES_REPO_SYNC_READ_ONLY_SOURCES"]["value"] == "/opt/data/hermes-agent"
    assert env["HERMES_REPO_SYNC_BRANCH"]["value"] == "self-improve/pod-repo-sync"
    assert env["HERMES_REPO_SYNC_MAX_CHANGED_PATHS"]["value"] == "80"
    assert env["HERMES_REPO_SYNC_MAX_REMOVED_PATHS"]["value"] == "8"
    assert env["HERMES_REPO_SYNC_MAX_SOURCE_BEHIND_COMMITS"]["value"] == "5"
    assert env["HERMES_FORK_REPO"]["value"] == "example-org/hermes-agent-private"
    assert env["GH_TOKEN"]["valueFrom"]["secretKeyRef"] == {"name": "hermes-github", "key": "token"}

    script = (K8S / "hermes-repo-sync.py").read_text(encoding="utf-8")
    assert "example-org/hermes-agent-private" in script
    assert "NousResearch/hermes-agent" in script
    assert "snapetech/hermes-agent-evolved" in script
    assert "gh" in script
    assert "pr" in script
    assert "READ_ONLY_SOURCE_REPOS" in script
    assert "ORPHAN_REPORT_DIR" in script
    assert "write_orphan_report" in script
    assert "orphaned_read_only_sources" in script
    assert "MAX_CHANGED_PATHS" in script
    assert "MAX_REMOVED_PATHS" in script
    assert "MAX_SOURCE_BEHIND_COMMITS" in script
    assert 'git(["checkout", "-B", BRANCH, BASE_REF], check=True)' in script
    assert "refusing large repo-sync" in script


def test_desktop_and_discord_monitor_mcps_are_packaged_but_disabled_by_default():
    dockerfile = (K8S / "Dockerfile.sudo").read_text(encoding="utf-8")
    config = yaml.safe_load((K8S / "configmap.yaml").read_text(encoding="utf-8"))["data"]["config.yaml"]
    parsed = yaml.safe_load(config)

    assert "desktop-bridge-mcp.py" in dockerfile
    assert "discord-wayland-monitor.py" in dockerfile
    assert "desktop-bridge-mcp.py" in (K8S / "bootstrap-runtime.sh").read_text(encoding="utf-8")
    assert "discord-wayland-monitor.py" in (K8S / "bootstrap-runtime.sh").read_text(encoding="utf-8")

    desktop_bridge = parsed["mcp_servers"]["desktop_bridge"]
    assert desktop_bridge["enabled"] is False
    assert desktop_bridge["command"] == "python3"
    assert desktop_bridge["args"] == ["/opt/data/desktop-bridge-mcp.py"]
    assert desktop_bridge["env"] == {
        "DESKTOP_BRIDGE_URL": "${DESKTOP_BRIDGE_URL}",
        "DESKTOP_BRIDGE_TOKEN": "${DESKTOP_BRIDGE_TOKEN}",
    }

    discord_monitor = parsed["mcp_servers"]["discord_wayland_monitor"]
    assert discord_monitor["enabled"] is False
    assert discord_monitor["command"] == "python3"
    assert discord_monitor["args"] == ["/opt/data/discord-wayland-monitor.py", "mcp"]
    assert discord_monitor["env"] == {
        "HERMES_DISCORD_MONITOR_PROFILE": "/opt/data/discord-monitor/chromium-profile",
        "HERMES_DISCORD_MONITOR_RUNTIME": "/tmp/hermes-discord-wayland",
    }


def test_local_glm_validator_route_is_declared_but_not_primary():
    dockerfile = (K8S / "Dockerfile.sudo").read_text(encoding="utf-8")
    manifest = yaml.safe_load((K8S / "local-models.manifest.yaml").read_text(encoding="utf-8"))
    config = yaml.safe_load((K8S / "configmap.yaml").read_text(encoding="utf-8"))["data"]["config.yaml"]
    parsed = yaml.safe_load(config)

    assert "local-models.manifest.yaml" in dockerfile
    assert "local-models.manifest.yaml" in (K8S / "bootstrap-runtime.sh").read_text(encoding="utf-8")

    assert parsed["model"]["default"] == "qwen3.6-35b-a3b:iq4xs"
    assert parsed["model"]["base_url"] == "http://127.0.0.1:8002/v1"
    assert parsed["auxiliary"]["validation"] == {
        "provider": "kilocode",
        "model": "kilo-auto/free",
        "timeout": 60,
    }

    providers = {entry["name"]: entry for entry in parsed["custom_providers"]}
    assert providers["llama-cpp-7900-primary"]["models"]["qwen3.6-35b-a3b:iq4xs"]["context_length"] == 65536
    assert providers["llama-cpp-7900-strong"]["base_url"] == "http://10.0.0.10:8034/v1"
    assert providers["llama-cpp-7900-strong"]["models"]["qwen3.6-27b:q5ks-7900"]["context_length"] == 4096
    assert providers["llama-cpp-9070-backup"]["base_url"] == "http://10.0.0.10:8035/v1"
    assert providers["llama-cpp-9070-backup"]["models"]["qwen3.6-27b:q5ks-9070"]["context_length"] == 4096
    assert providers["llama-cpp-glm-validator"]["base_url"] == "http://10.0.0.10:8028/v1"
    assert providers["llama-cpp-glm-validator"]["models"]["glm-4.7-flash:q6kl"]["context_length"] == 8192
    assert providers["llama-cpp-a380-backup"]["base_url"] == "http://127.0.0.1:8030/v1"
    assert set(providers["llama-cpp-a380-backup"]["models"]) == {
        "ministral3-3b-instruct:q4km",
        "smollm3:q4km",
        "qwen3-4b-instruct-2507:q4km",
    }
    for model in providers["llama-cpp-a380-backup"]["models"].values():
        assert model["context_length"] == 8192

    models = {entry["id"]: entry for entry in manifest["models"]}
    assert models["gemma4-26b-a4b-it:q4km"]["role"] == "primary_workhorse"
    assert models["gemma4-26b-a4b-it:q4km"]["required"] is True
    assert models["gemma4-26b-a4b-it:q4km"]["route_policy"]["tier"] == 100
    assert models["qwen3.6-35b-a3b:iq4xs"]["role"] == "fast_utility_fallback"
    assert models["qwen3.6-35b-a3b:iq4xs"]["required"] is False
    assert models["qwen3.6-35b-a3b:iq4xs"]["route_policy"]["tier"] == 90
    assert models["qwen3.6-27b:q5ks-7900"]["role"] == "qwen_dense_single_card_fallback"
    assert models["qwen3.6-27b:q5ks-7900"]["benchmark_summary"]["utility_score"] == "21/24"
    assert "quality" in models["qwen3.6-27b:q5ks-7900"]["route_policy"]["tags"]
    assert models["qwen3.6-27b:q5ks-9070"]["role"] == "guarded_backup_same_family"
    assert models["qwen3.6-27b:q5ks-9070"]["host_guard_profile"] == "amd-node-a"
    assert models["glm-4.7-flash:q6kl"]["role"] == "secondary_validator"
    assert models["glm-4.7-flash:q6kl"]["required"] is False
    assert models["glm-4.7-flash:q6kl"]["in_pod_base_url"] == "http://10.0.0.10:8028/v1"
    assert models["glm-4.7-flash:q6kl"]["context_length"] == 8192
    assert models["ministral3-3b-instruct:q4km"]["role"] == "a380_backup_utility"
    assert models["ministral3-3b-instruct:q4km"]["required"] is False
    assert models["ministral3-3b-instruct:q4km"]["custom_provider"] == "llama-cpp-a380-backup"
    assert models["ministral3-3b-instruct:q4km"]["in_pod_base_url"] == "http://127.0.0.1:8030/v1"
    assert models["ministral3-3b-instruct:q4km"]["host_guard_profile"] == "intel-node-b"
    assert models["ministral3-3b-instruct:q4km"]["benchmark_summary"]["raw_utility_slm_score"] == "6/8"
    assert models["ministral3-3b-instruct:q4km"]["benchmark_summary"]["routed_score_with_policy_post_rules"] == "8/8"
    assert models["smollm3:q4km"]["role"] == "a380_backup_utility"
    assert models["smollm3:q4km"]["benchmark_summary"]["raw_utility_slm_score"] == "5/8"
    assert models["qwen3-4b-instruct-2507:q4km"]["role"] == "a380_backup_tunable"
    assert models["qwen3-4b-instruct-2507:q4km"]["benchmark_summary"]["tuned_prompt_score"] == "6/8"
    assert parsed["adaptive_fallback_routing"]["enabled"] is False
    assert parsed["model_aliases"] == {
        "manifest": {
            "provider": "manifest",
            "model": "manifest/auto",
            "base_url": "http://127.0.0.1:3001/v1",
        },
        "manifest-auto": {
            "provider": "manifest",
            "model": "manifest/auto",
            "base_url": "http://127.0.0.1:3001/v1",
        },
    }
    assert parsed["fallback_providers"] == [
        {
            "provider": "kilocode",
            "model": "kilo-auto/free",
            "base_url": "https://api.kilo.ai/api/gateway",
        },
    ]
    qar = parsed["queue_aware_routing"]
    assert qar["enabled"] is True
    assert qar["default_request_class"] == "general"
    validator_followup = qar["validator_followup"]
    assert validator_followup["enabled"] is True
    assert validator_followup["ttl_seconds"] == 900
    assert "retry" in validator_followup["repair_keywords"]
    assert validator_followup["short_followup_keywords"] == ["again", "continue", "that", "it", "this"]
    assert validator_followup["short_followup_max_words"] == 6
    routes = {entry["id"]: entry for entry in qar["routes"]}
    assert routes["qwen35_7900_primary"]["model"] == "qwen3.6-35b-a3b:iq4xs"
    assert routes["qwen35_7900_primary"]["fallback_route_ids"] == ["kilo_cloud_backup"]
    assert "qwen27_7900_strong" not in routes
    assert "qwen27_9070_backup" not in routes
    assert "glm47_validator" not in routes
    assert "ministral_a380" not in routes
    assert "smollm3_a380" not in routes
    assert "qwen3_4b_a380" not in routes
    assert "claude_cloud_strong" not in routes
    assert "codex_cloud_strong" not in routes
    assert "copilot_cloud_backup" not in routes
    assert routes["kilo_cloud_backup"]["provider"] == "kilocode"
    assert routes["kilo_cloud_backup"]["fallback_route_ids"] == ["qwen35_7900_primary"]
    assert "claude-subscription" not in providers
    assert "codex-subscription" not in providers
    assert "copilot-subscription" not in providers
    assert providers["kilo-subscription"]["base_url"] == "https://api.kilo.ai/api/gateway"


def test_self_improvement_repo_policy_targets_private_package_repo_only():
    self_edit = (K8S / "hermes-self-edit.py").read_text(encoding="utf-8")
    scan = (K8S / "hermes-self-improvement-scan.py").read_text(encoding="utf-8")
    intel = (K8S / "hermes-intel-sources.yaml").read_text(encoding="utf-8")
    workspace_agents = (K8S / "workspace-AGENTS.md").read_text(encoding="utf-8")

    for text in (self_edit, scan, intel, workspace_agents):
        assert "example-org/hermes-agent-private" in text
        assert "NousResearch/hermes-agent" in text
        assert "snapetech/hermes-agent-evolved" in text

    assert "must open self PRs\n    and self issues only in example-org/hermes-agent-private" in intel
    assert "PUBLIC_MIRROR_REPO" in self_edit
    assert "publication output only" in self_edit
    assert "ensure_canonical_cwd" in self_edit
    assert "compatibility alias" in workspace_agents
    assert "orphaned-repos" in workspace_agents
    assert "refuses start/test/submit from any other working directory" in workspace_agents

    upstream_sync_skill = (ROOT / "skills" / "autonomous-ai-agents" / "hermes-upstream-sync" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "example-org/hermes-agent-private" in upstream_sync_skill
    assert "NousResearch/hermes-agent" in upstream_sync_skill
    assert "snapetech/hermes-agent-evolved" in upstream_sync_skill
    assert "Do not push to `main`, merge PRs, or mutate the live deployment without explicit" in upstream_sync_skill
    assert "Do not default to a blind merge." in upstream_sync_skill
    assert "keep the local deferred reload/restart workflow" in upstream_sync_skill

    upstream_sync_doc = (ROOT / "docs" / "upstream-sync.md").read_text(encoding="utf-8")
    assert "This workflow is upstream-first." in upstream_sync_doc
    assert "upstream supersedes" in upstream_sync_doc
    assert "back-build any deployment gaps" in upstream_sync_doc

    design_deltas = (ROOT / "docs" / "upstream-sync-design-deltas.md").read_text(encoding="utf-8")
    assert "Deferred runtime reload and restart" in design_deltas
    assert "Repo-first self-edit policy" in design_deltas


def test_gateway_init_repairs_empty_boot_and_soul_without_overwriting_nonempty_files():
    docs = _load_yaml_docs(K8S / "deployment.yaml")
    deploy = next(doc for doc in docs if doc.get("kind") == "Deployment" and doc["metadata"]["name"] == "hermes-gateway")
    init_command = "\n".join(deploy["spec"]["template"]["spec"]["initContainers"][0]["command"])

    assert "if [ ! -s /opt/data/SOUL.md ]; then" in init_command
    assert "if [ ! -s /opt/data/BOOT.md ]; then" in init_command
    assert "cp /bootstrap/SOUL.md /opt/data/SOUL.md" in init_command
    assert "cp /bootstrap/BOOT.md /opt/data/BOOT.md" in init_command


def test_gateway_uses_noninteractive_sudo_and_does_not_reserve_gpu():
    docs = _load_yaml_docs(K8S / "deployment.yaml")
    deploy = next(doc for doc in docs if doc.get("kind") == "Deployment" and doc["metadata"]["name"] == "hermes-gateway")
    gateway = next(container for container in deploy["spec"]["template"]["spec"]["containers"] if container["name"] == "gateway")
    env = _env_map(gateway)
    resources = gateway["resources"]

    assert env["HERMES_PASSWORDLESS_SUDO"]["value"] == "1"
    assert env["HERMES_UPDATE_COMMAND"]["value"] == "hermes-upstream-sync skill"
    assert env["HERMES_UPDATE_ACTION_PREFIX"]["value"] == "use"
    assert env["HERMES_UPDATE_BEHIND_CONTEXT"]["value"] == "behind upstream"
    assert env["HERMES_UPDATE_ACTION_SUFFIX"]["value"] == "to plan and land an upstream sync"
    assert env["HERMES_UPDATE_CHECK_CACHE_SECONDS"]["value"] == "900"
    assert "amd.com/gpu" not in resources.get("requests", {})
    assert "amd.com/gpu" not in resources.get("limits", {})
    assert "gpu.intel.com/i915" not in resources.get("requests", {})
    assert "gpu.intel.com/i915" not in resources.get("limits", {})


def test_opportunistic_gpu_runner_is_packaged():
    dockerfile = (K8S / "Dockerfile.sudo").read_text(encoding="utf-8")
    runner = (K8S / "hermes-gpu-opportunistic-runner.py").read_text(encoding="utf-8")
    watchdog = (K8S / "hermes-gpu-telemetry-watchdog.py").read_text(encoding="utf-8")

    assert "hermes-gpu-opportunistic-runner.py" in dockerfile
    assert "hermes-gpu-telemetry-watchdog.py" in dockerfile
    assert "amd-node-a" in runner
    assert "intel-node-b" in runner
    assert "Plex Transcoder" in runner
    assert "gamescope" in runner
    assert '"nice", "-n"' in runner
    assert '"ionice", "-c", "3"' in runner
    assert "rocm-smi" in watchdog
    assert "display_max_vram_pct" in watchdog
    assert "max_memory_temp_c" in watchdog
    assert "SIGTERM" in watchdog
    assert "SIGKILL" in watchdog
    assert "os.killpg" in watchdog


def test_configmap_shell_helper_is_not_embedded_in_python_heredoc():
    configmap = (K8S / "configmap.yaml").read_text(encoding="utf-8")
    start = configmap.index("python3 - <<'PY'")
    end = configmap.index("\n    PY", start)
    python_block = configmap[start:end]

    assert "install_managed_executable()" in configmap
    assert "install_managed_executable()" not in python_block
    assert "def _write_json(path: Path, payload: dict) -> None:" in python_block


def test_gpu_telemetry_watchdog_dry_run_with_fake_rocm_smi(tmp_path):
    fake_rocm_smi = tmp_path / "rocm-smi"
    fake_rocm_smi.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "print(json.dumps({\n"
        "  'card0': {\n"
        "    'Temperature (Sensor edge) (C)': '45.0',\n"
        "    'Temperature (Sensor junction) (C)': '50.0',\n"
        "    'Temperature (Sensor memory) (C)': '60.0',\n"
        "    'GPU use (%)': '3',\n"
        "    'GPU Memory Allocated (VRAM%)': '10'\n"
        "  }\n"
        "}))\n",
        encoding="utf-8",
    )
    fake_rocm_smi.chmod(0o755)
    log_path = tmp_path / "watchdog.jsonl"

    proc = subprocess.run(
        [
            sys.executable,
            str(K8S / "hermes-gpu-telemetry-watchdog.py"),
            "--profile",
            "amd-node-a",
            "--cards",
            "card0",
            "--display-cards",
            "card0",
            "--rocm-smi",
            str(fake_rocm_smi),
            "--block-re",
            "pattern-that-will-not-match",
            "--log",
            str(log_path),
            "--dry-run",
        ],
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert events[-1]["event"] == "preflight"
    assert events[-1]["violations"] == []
    assert events[-1]["samples"]["card0"]["vram_pct"] == 10.0


def test_gpu_telemetry_watchdog_aborts_on_fake_vram_violation(tmp_path):
    fake_rocm_smi = tmp_path / "rocm-smi"
    fake_rocm_smi.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "print(json.dumps({\n"
        "  'card0': {\n"
        "    'Temperature (Sensor edge) (C)': '45.0',\n"
        "    'Temperature (Sensor junction) (C)': '50.0',\n"
        "    'Temperature (Sensor memory) (C)': '60.0',\n"
        "    'GPU use (%)': '3',\n"
        "    'GPU Memory Allocated (VRAM%)': '95'\n"
        "  }\n"
        "}))\n",
        encoding="utf-8",
    )
    fake_rocm_smi.chmod(0o755)
    log_path = tmp_path / "watchdog.jsonl"

    proc = subprocess.run(
        [
            sys.executable,
            str(K8S / "hermes-gpu-telemetry-watchdog.py"),
            "--profile",
            "amd-node-a",
            "--cards",
            "card0",
            "--display-cards",
            "card0",
            "--display-max-vram-pct",
            "82",
            "--rocm-smi",
            str(fake_rocm_smi),
            "--block-re",
            "pattern-that-will-not-match",
            "--log",
            str(log_path),
            "--dry-run",
        ],
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 76
    events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert events[-1]["event"] == "preflight"
    assert any("display VRAM" in item for item in events[-1]["violations"])


def test_hermes_model_benchmark_skill_tracks_local_lineup_and_script():
    script = ROOT / "scripts" / "hermes_model_benchmark.py"
    source = script.read_text(encoding="utf-8")
    compile(source, str(script), "exec")

    skill = (ROOT / "skills" / "mlops" / "evaluation" / "hermes-model-benchmark" / "SKILL.md").read_text(encoding="utf-8")
    lineup = (
        ROOT
        / "skills"
        / "mlops"
        / "evaluation"
        / "hermes-model-benchmark"
        / "references"
        / "model-lineup.md"
    ).read_text(encoding="utf-8")

    for expected in (
        "scripts/hermes_model_benchmark.py",
        "deploy/k8s/hermes-llama-qwen36-service.sh",
        "google_gemma-4-E4B-it-Q8_0.gguf",
        "google_gemma-4-26B-A4B-it-Q4_K_M.gguf",
        "Qwen_Qwen3.6-35B-A3B-IQ4_XS.gguf",
        "Kimi / Moonshot Watch Lane",
        "hermes-llama-gemma4-26b-9070.service",
        "smoke result 2/3",
        "GPU_GUARD_PROFILE=amd-node-a",
        "guard-check",
        "Never run wildcard stops",
        "hermes-llama-qwen36.service",
    ):
        assert expected in skill or expected in lineup

    assert "--list-tasks" in source
    assert "qwen3.6-35b-a3b:iq4xs" in source
    assert "gemma4-26b-a4b-it:q4km" in source


def test_evolved_publish_includes_public_safe_slm_capability_artifacts():
    script = (ROOT / "scripts" / "publish_evolved_repo.sh").read_text(encoding="utf-8")

    assert 'git -C "$repo_root" ls-tree -r --name-only "$private_sha"' in script
    assert "public_overlay_excluded_path" in script
    assert ".github/workflows/*" in script
    assert "benchmark_runs/*" in script
    assert "benchmarks/llm/results/*" in script
    assert "rsync -a --delete" in script

    for expected in (
        "benchmarks/llm/local_llm_benchmark_report_20260421.md",
        "benchmarks/llm/model_benchmark_scorecard.md",
        "benchmarks/llm/model_capability_cards.md",
        "benchmarks/llm/model_capability_cards.generated.md",
        "benchmarks/llm/nous_edge_watch_local_results_20260422.md",
        "benchmarks/llm/run_slm_utility_bench.sh",
        "benchmarks/llm/slm_candidates.tsv",
        "benchmarks/llm/split_card_test_plan_20260422.md",
        "scripts/hermes_model_benchmark.py",
        "scripts/llama_throughput_compare.py",
        "scripts/model_capability_cards.py",
        "tests/scripts/test_model_capability_cards.py",
    ):
        assert expected in script

    assert "benchmark_runs/hermes_model_benchmark_slm_utility" not in script
    assert "benchmark_runs/llama_throughput_slm" not in script
    assert "skills/security|skills/security/*|tools/siem_tool.py" in script
    assert "s#/opt/models/hermes-bench#/opt/models/hermes-bench#g" in script
    assert "s#10\\.42\\.0\\.1#10.0.0.10#g" in script
    assert "s#192\\.168\\.50\\.([0-9]{1,3})#10.0.50.$1#g" in script
    assert "s/security-lab/security-lab/g" in script
    assert "s/SECURITY-PLATFORM-SETUP/SECURITY-PLATFORM-SETUP/g" in script
    assert "private_pattern='node-a|node-b|gitlab\\.home|hermes\\.home|10\\.42\\.0\\.1|192\\.168\\.50\\." in script
    assert "security-lab|SECURITY-PLATFORM-SETUP" in script


def test_llama_service_helper_supports_explicit_9070_gpu_selection():
    text = (K8S / "hermes-llama-qwen36-service.sh").read_text(encoding="utf-8")

    for expected in (
        "SERVICE_DESCRIPTION",
        "GPU_DEVICE_ORDINAL_VALUE",
        "GGML_VK_VISIBLE_DEVICES_VALUE",
        "Environment=GPU_DEVICE_ORDINAL=",
        "Environment=GGML_VK_VISIBLE_DEVICES=",
        "HSA_OVERRIDE_GFX_VERSION_VALUE=12.0.1",
        "GPU_GUARD_PROFILE",
        "guard-check",
        "ExecStartPre=",
        "/usr/bin/nice",
        "/usr/bin/ionice",
        "stop_service",
        "refusing to stop primary service",
        "ALLOW_PRIMARY_STOP=1",
    ):
        assert expected in text


def test_evolved_publisher_overlays_private_readme_before_publication_metadata():
    text = (ROOT / "scripts" / "publish_evolved_repo.sh").read_text(encoding="utf-8")

    assert 'rsync -a --delete --exclude=\'.git\' "$overlay"/ "$upstream"/' in text
    assert 'cp "$overlay/README.md" "$upstream/README.md"' in text
    assert text.index('rsync -a --delete') < text.index('cat >"$upstream/PUBLICATION.md"')
    assert text.index('cp "$overlay/README.md" "$upstream/README.md"') < text.index('cat >"$upstream/PUBLICATION.md"')
    assert "private infrastructure marker scan" in text
    assert "inline Kubernetes/private secret scan" in text
    assert "high-confidence secret pattern scan" in text
    assert "example-org/hermes-agent-private#example-org/hermes-agent-private" in text
