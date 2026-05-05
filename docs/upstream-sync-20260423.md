# Upstream Sync Triage - 2026-04-23

Branch: `self-improve/upstream-sync-20260423`

Current fork head at triage time:
- `d5a743a5` on `origin/main`

Current upstream head at triage time:
- `f5af6520` on `upstream/main`

Merge base:
- `bc5da42b2c31136c55c55f9ef84bd156d8c90da2`

## Summary

Upstream does not contain a better replacement for the recent local work on:

- repo-first self-edits
- hot-reload of prompt/skill metadata
- live runtime reload
- deferred gateway self-restart on repo code changes
- in-pod process restart on exit code `75`
- runtime/API/hook status for reload and restart-pending state

The local design should remain the canonical path unless a future upstream
change clearly subsumes it.

What upstream *does* contain is a set of adjacent bug fixes and guardrails that
should likely be adapted on top of the local design.

## Recommendation

Keep the local reload/restart method. Selectively merge upstream fixes around
that method instead of replacing it.

## High-value upstream commits to adapt

### Gateway/session correctness

1. `b7bdf32d` `fix(gateway): guard session slot ownership after stop/reset`
   - Why it matters:
     our auto-restart and drain work touches the same end-of-turn cleanup path.
     This upstream change hardens session ownership and should be integrated
     into the local finalizer logic rather than ignored.
   - Recommendation:
     merge/adapt.

2. `d72985b7` `fix(gateway): serialize reset command handoff and heal stale session locks`
   - Why it matters:
     same control-flow neighborhood as restart/drain/session reset behavior.
   - Recommendation:
     review together with `b7bdf32d`; likely merge/adapt.

3. `36730b90` `fix(gateway): also clear session-scoped approval state on /new`
   - Why it matters:
     local work touched gateway lifecycle; this is a contained correctness fix.
   - Recommendation:
     merge/adapt.

4. `050aabe2` `fix(gateway): reset approval and yolo state on session boundary`
   - Why it matters:
     same session-boundary area; low conceptual conflict with local work.
   - Recommendation:
     merge/adapt.

### Restart/status durability

5. `b52123eb` `fix(gateway): recover stale pid and planned restart state`
   - Why it matters:
     directly overlaps local runtime status/restart work.
   - Assessment:
     upstream improves stale PID and planned-restart recovery, but does not
     supersede the local deferred auto-restart plus status/API/hook surfaces.
   - Recommendation:
     keep the local status fields and deferred restart workflow, then adapt the
     upstream recovery hardening into `gateway/status.py`, `gateway/run.py`, and
     `hermes_cli/gateway.py`.

6. `4c02e459` `fix(status): catch OSError in os.kill(pid, 0) for Windows compatibility`
   - Why it matters:
     tiny, isolated, obviously correct.
   - Recommendation:
     merge/adapt.

7. `d45c738a` `fix(gateway): preflight user D-Bus before systemctl --user start`
   - Why it matters:
     improves service-control resilience; does not conflict with local reload
     design.
   - Recommendation:
     merge/adapt.

### Skills sync

8. `24e8a6e7` `feat(skills_sync): surface collision with reset-hint`
   - Why it matters:
     complements the local stale-manifest auto-heal fix.
   - Recommendation:
     merge/adapt.

9. `3a97fb3d` `fix(skills_sync): don't poison manifest on new-skill collision`
   - Why it matters:
     directly adjacent to the local `putter`/manifest failure family.
   - Assessment:
     upstream fix is good and should be kept alongside the local stale-baseline
     auto-heal logic.
   - Recommendation:
     merge/adapt.

### Lower-priority but relevant

10. `39fcf1d1` `fix(model_switch): group custom_providers by endpoint in /model picker`
    - Why it matters:
      not directly related to reload/restart, but in adjacent CLI/gateway model
      routing surfaces.
    - Recommendation:
      merge later in the sync pass.

## Conflicts observed in dry merge

The dry merge against `upstream/main` conflicted in:

- `gateway/run.py`
- `cli.py`
- `run_agent.py`
- `agent/context_compressor.py`
- `README.md`
- `package.json`
- `pyproject.toml`
- `tests/gateway/test_unknown_command.py`
- `tests/run_agent/test_streaming.py`
- `tui_gateway/server.py`
- `ui-tui/src/app/useInputHandlers.ts`
- `uv.lock`

Only some of these are central to the recent local work.

### Core conflict assessment

#### `gateway/run.py`

This is the main real conflict. Upstream and local both changed lifecycle and
cleanup logic.

Observed overlap:
- local:
  deferred auto-restart, runtime reload, hook emission, status updates
- upstream:
  session slot ownership guard, approval/session-boundary cleanup, stale
  restart-state recovery

Decision:
- keep the local deferred restart architecture
- integrate upstream cleanup/ownership fixes into that architecture

#### `cli.py`

Conflict is minor in the inspected hunk:
- upstream adds `ignore_rules`
- local adds `/reload` and prompt-signature handling

Decision:
- take both.

#### `run_agent.py`

Conflict is broader and tied to upstream transport refactors.

Decision:
- do not blindly merge this part with the reload/restart branch.
- handle after gateway/status/skills_sync merges are settled.

## Best merge order

1. create a focused merge/adaptation pass for:
   - `b7bdf32d`
   - `d72985b7`
   - `36730b90`
   - `050aabe2`
   - `b52123eb`
   - `4c02e459`
   - `d45c738a`
   - `24e8a6e7`
   - `3a97fb3d`

2. resolve `gateway/run.py`, `gateway/status.py`, `hermes_cli/gateway.py`,
   and `tools/skills_sync.py` first.

3. run focused tests for:
   - gateway drain/restart/status
   - api health
   - skills sync

4. only then widen the upstream merge into `run_agent.py`, `cli.py`, TUI, and
   lockfiles.

## Bottom line

The local method remains better for the current pod workflow because it adds:

- safe in-process reload of low-risk changes
- deferred restart at turn boundaries
- in-pod process restart without pod replacement
- machine-facing status via API/CLI/hooks
- repo-first operational guidance

Upstream has useful fixes around that method, not a superior replacement for it.
