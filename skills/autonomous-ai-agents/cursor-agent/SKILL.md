---
name: cursor-agent
description: Delegate coding tasks to Cursor Agent CLI. Use for one-shot coding, model-backed reviews, worktree tasks, and Cursor subscription-backed models. Requires the cursor-agent CLI and Cursor auth.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [Coding-Agent, Cursor, Code-Review, Refactoring, PTY]
    related_skills: [codex, claude-code, hermes-agent]
---

# Cursor Agent CLI

Delegate coding tasks to Cursor Agent via the Hermes terminal. Cursor Agent can run interactively, but Hermes should prefer print mode for automation.

## Prerequisites

- Cursor Agent installed: `curl https://cursor.com/install -fsS | bash`
- Cursor auth configured: `cursor-agent login`
- Check auth: `cursor-agent whoami`
- Check models: `cursor-agent models`
- Prefer a git repository for code-changing tasks.

## One-Shot Tasks

Use print mode with an explicit workspace:

```
terminal(command="cursor-agent -p --trust --workspace /path/to/project 'Fix the failing tests and summarize the changes'", timeout=180)
```

For read-only analysis:

```
terminal(command="cursor-agent -p --mode ask --workspace /path/to/project 'Explain the auth flow and list risky edges'", timeout=120)
```

For planning without edits:

```
terminal(command="cursor-agent -p --plan --workspace /path/to/project 'Plan a safe migration from X to Y'", timeout=120)
```

## Model Selection

List available subscription models:

```
terminal(command="cursor-agent models", timeout=60)
```

Run with a specific model:

```
terminal(command="cursor-agent -p --trust --model claude-4.6-sonnet-medium --workspace /path/to/project 'Review this branch'", timeout=180)
```

## Background Work

For longer tasks, run in the background and monitor:

```
terminal(command="cursor-agent -p --trust --force --workspace /path/to/project 'Implement feature X and run tests'", background=true, timeout=600)
process(action="poll", session_id="<id>")
process(action="log", session_id="<id>")
```

## Worktrees

Cursor Agent can create isolated worktrees:

```
terminal(command="cursor-agent -p --trust --worktree issue-123 --workspace /path/to/repo 'Fix issue #123 and leave a summary'", timeout=600)
```

## Rules

1. Prefer `-p`/`--print` for Hermes automation; it exits cleanly.
2. Use `--trust` only in repositories the user controls.
3. Use `--force`/`--yolo` only when the environment is safe for command execution.
4. Use `--mode ask` or `--plan` for read-only analysis.
5. Use `cursor-agent whoami` before assuming subscription auth works.
