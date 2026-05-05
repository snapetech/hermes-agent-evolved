import json

from tools.runtime_installs import (
    extract_runtime_install_packages,
    promote_runtime_packages,
    promote_runtime_apt_packages,
    read_image_apt_packages,
    read_promoted_packages,
    read_runtime_installs,
    read_runtime_apt_installs,
    record_runtime_install,
    record_runtime_apt_install,
)


def test_record_runtime_apt_install_writes_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / ".hermes"))

    record_runtime_apt_install(
        command="sudo -n apt-get install -y tesseract-ocr",
        packages=["tesseract-ocr"],
        exit_code=0,
        output="ok",
        task_id="task-1",
    )

    rows = read_runtime_apt_installs()
    assert len(rows) == 1
    assert rows[0]["packages"] == ["tesseract-ocr"]
    assert rows[0]["task_id"] == "task-1"


def test_promote_runtime_apt_packages_appends_to_package_file(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / ".hermes"))
    repo = tmp_path / "repo"
    package_file = repo / "deploy" / "k8s" / "apt-packages.txt"
    package_file.parent.mkdir(parents=True)
    package_file.write_text("# packages\nffmpeg\n", encoding="utf-8")
    record_runtime_apt_install(
        command="sudo -n apt-get install -y tesseract-ocr ffmpeg",
        packages=["tesseract-ocr", "ffmpeg"],
        exit_code=0,
    )

    result = promote_runtime_apt_packages(repo_root=repo)

    assert result["added"] == ["tesseract-ocr"]
    assert "ffmpeg" in read_image_apt_packages(repo)
    assert "tesseract-ocr" in read_image_apt_packages(repo)


def test_extract_runtime_install_packages_handles_pip_and_npm():
    assert extract_runtime_install_packages(
        "bash -lc 'sudo -n apt-get update && sudo -n apt-get install -y tesseract-ocr && python -m pip install yt-dlp'"
    ) == {"apt": ["tesseract-ocr"], "pip": ["yt-dlp"]}
    assert extract_runtime_install_packages(
        "python -m pip install --upgrade yt-dlp 'openai-whisper>=20250625'"
    ) == {"pip": ["yt-dlp", "openai-whisper>=20250625"]}
    assert extract_runtime_install_packages("pip install -r requirements.txt") == {}
    assert extract_runtime_install_packages("npm install -g @mermaid-js/mermaid-cli prettier") == {
        "npm": ["@mermaid-js/mermaid-cli", "prettier"]
    }
    assert extract_runtime_install_packages("npm install prettier") == {}


def test_extract_runtime_install_packages_ignores_shell_plumbing():
    assert extract_runtime_install_packages("pip install yt-dlp 2>&1 | tail -3") == {"pip": ["yt-dlp"]}
    assert extract_runtime_install_packages(
        "python3 -m pip install pytesseract pillow --break-system-packages 2>&1 | tail -5"
    ) == {"pip": ["pytesseract", "pillow"]}


def test_promote_runtime_pip_and_npm_packages(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / ".hermes"))
    repo = tmp_path / "repo"
    package_dir = repo / "deploy" / "k8s"
    package_dir.mkdir(parents=True)
    (package_dir / "requirements-persistent.txt").write_text("requests\n", encoding="utf-8")
    (package_dir / "npm-global-packages.txt").write_text("prettier\n", encoding="utf-8")
    record_runtime_install(
        ecosystem="pip",
        command="python -m pip install yt-dlp requests",
        packages=["yt-dlp", "requests"],
        exit_code=0,
    )
    record_runtime_install(
        ecosystem="npm",
        command="npm install -g prettier @mermaid-js/mermaid-cli",
        packages=["prettier", "@mermaid-js/mermaid-cli"],
        exit_code=0,
    )

    pip_result = promote_runtime_packages("pip", repo_root=repo)
    npm_result = promote_runtime_packages("npm", repo_root=repo)

    assert pip_result["added"] == ["yt-dlp"]
    assert npm_result["added"] == ["@mermaid-js/mermaid-cli"]
    assert "yt-dlp" in read_promoted_packages("pip", repo)
    assert "@mermaid-js/mermaid-cli" in read_promoted_packages("npm", repo)


def test_promote_runtime_packages_prefers_hermes_home_checkout_when_cwd_is_image_copy(
    tmp_path,
    monkeypatch,
):
    hermes_home = tmp_path / ".hermes"
    durable_repo = hermes_home / "hermes-agent"
    image_copy = tmp_path / "opt-hermes"
    for root in (durable_repo, image_copy):
        package_dir = root / "deploy" / "k8s"
        package_dir.mkdir(parents=True)
        (package_dir / "requirements-persistent.txt").write_text("requests\n", encoding="utf-8")

    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.chdir(image_copy)
    record_runtime_install(
        ecosystem="pip",
        command="python -m pip install yt-dlp",
        packages=["yt-dlp"],
        exit_code=0,
    )

    result = promote_runtime_packages("pip")

    assert result["package_file"] == str(durable_repo / "deploy" / "k8s" / "requirements-persistent.txt")
    assert "yt-dlp" in read_promoted_packages("pip", durable_repo)
    assert "yt-dlp" not in read_promoted_packages("pip", image_copy)


def test_promote_runtime_packages_reparses_historical_shell_plumbing_records(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / ".hermes"))
    repo = tmp_path / "repo"
    package_dir = repo / "deploy" / "k8s"
    package_dir.mkdir(parents=True)
    (package_dir / "requirements-persistent.txt").write_text("requests\n", encoding="utf-8")
    record_runtime_install(
        ecosystem="pip",
        command="pip install yt-dlp 2>&1 | tail -3",
        packages=["2>&1", "tail", "yt-dlp", "|"],
        exit_code=0,
    )

    result = promote_runtime_packages("pip", repo_root=repo)

    assert result["added"] == ["yt-dlp"]
    assert "tail" not in read_promoted_packages("pip", repo)
    assert "|" not in read_promoted_packages("pip", repo)


def test_terminal_tool_records_successful_runtime_apt_install(tmp_path, monkeypatch):
    import tools.terminal_tool as terminal_tool

    class FakeEnv:
        def execute(self, command, **kwargs):
            return {"output": "installed", "returncode": 0}

    monkeypatch.setenv("HERMES_HOME", str(tmp_path / ".hermes"))
    monkeypatch.setattr(
        terminal_tool,
        "_get_env_config",
        lambda: {
            "env_type": "local",
            "cwd": str(tmp_path),
            "timeout": 30,
            "local_persistent": False,
        },
    )
    monkeypatch.setattr(terminal_tool, "_start_cleanup_thread", lambda: None)
    terminal_tool._active_environments["apt-test"] = FakeEnv()
    try:
        result = json.loads(
            terminal_tool.terminal_tool(
                "sudo -n apt-get update && sudo -n apt-get install -y tesseract-ocr",
                task_id="apt-test",
                force=True,
            )
        )
    finally:
        terminal_tool._active_environments.pop("apt-test", None)

    assert result["exit_code"] == 0
    rows = read_runtime_apt_installs()
    assert rows[0]["packages"] == ["tesseract-ocr"]


def test_terminal_tool_records_successful_runtime_pip_install(tmp_path, monkeypatch):
    import tools.terminal_tool as terminal_tool

    class FakeEnv:
        def execute(self, command, **kwargs):
            return {"output": "installed", "returncode": 0}

    monkeypatch.setenv("HERMES_HOME", str(tmp_path / ".hermes"))
    monkeypatch.setattr(
        terminal_tool,
        "_get_env_config",
        lambda: {
            "env_type": "local",
            "cwd": str(tmp_path),
            "timeout": 30,
            "local_persistent": False,
        },
    )
    monkeypatch.setattr(terminal_tool, "_start_cleanup_thread", lambda: None)
    terminal_tool._active_environments["pip-test"] = FakeEnv()
    try:
        result = json.loads(
            terminal_tool.terminal_tool(
                "python -m pip install yt-dlp",
                task_id="pip-test",
                force=True,
            )
        )
    finally:
        terminal_tool._active_environments.pop("pip-test", None)

    assert result["exit_code"] == 0
    rows = read_runtime_installs("pip")
    assert rows[0]["packages"] == ["yt-dlp"]
