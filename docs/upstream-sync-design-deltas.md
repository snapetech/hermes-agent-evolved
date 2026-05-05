# Upstream Sync Design Deltas

This document records the durable design choices that differ from upstream,
which upstream fixes we adopted, and which gaps remain after each sync pass.

Use it together with:

- [docs/upstream-sync.md](upstream-sync.md)
- [docs/upstream-sync-20260423.md](upstream-sync-20260423.md)
- [docs/upstream-sync-report.md](upstream-sync-report.md)

## Current Position

The private deployment fork should stay close to `NousResearch/hermes-agent`,
but not at the cost of dropping working pod-specific behavior that upstream does
not provide yet.

The rule is:

- start from current upstream as the mental baseline
- ask whether we would still choose the local method if none of our prior work
  existed yet
- keep local design only when the answer is still yes
- adopt upstream when it now gets us to the same destination cleanly enough to
  make the custom path obsolete
- use a hybrid only when upstream is directionally right but still leaves a
  real SnapE gap
- document the reason either way

The invariant is:

- required Snapetech outputs, tooling, connections, operator workflows, pod
  behavior, and deployment integrations must still work
- or the newer upstream/Hermes path must replace that custom behavior fully
  enough that the local change is obsolete

Anything that fails that invariant is still a gap, not a completed sync.

## Current Baseline

As of merge commit `8126a3bb`, local `main` is aligned with
`NousResearch/hermes-agent` at upstream commit `bf196a3f` with `0` upstream-only
commits behind. The old staging branch `self-improve/upstream-sync-20260423`
has been retired; future syncs compare from merged `main`.

## Local Choices We Intentionally Keep

### Deferred runtime reload and restart

We keep the local design for:

- in-process reload of low-risk runtime changes at safe boundaries
- deferred restart for repo-backed Python code changes
- no mutation of active turns mid-run
- in-pod process restart on exit code `75`
- runtime visibility through CLI, API health, and gateway hooks

Why this still survives the fresh-upstream test:

Upstream does not currently provide a better equivalent for this pod workflow.
Our method reduces disruption without poisoning active context.

Primary files:

- `gateway/run.py`
- `gateway/status.py`
- `hermes_cli/gateway.py`
- `deploy/k8s/`

### Repo-first self-edit policy

We keep the local rule that Hermes edits the repo checkout first and treats
runtime/internal copies as exceptional.

Why this still survives the fresh-upstream test:

This avoids runtime drift and keeps durable changes reviewable and reproducible.
It directly addresses the earlier `putter` failure family.

Primary files:

- `agent/file_safety.py`
- `tools/file_operations.py`
- `tools/file_tools.py`
- `deploy/k8s/workspace-AGENTS.md`

### Skills sync safeguards

We keep the local stale-manifest auto-heal behavior in `tools/skills_sync.py`.

Why this still survives the fresh-upstream test:

It fixes the specific bundled-skill wedge where the installed skill already
matched bundled content but the manifest baseline was stale.

## Upstream Fixes We Adopted Around The Local Method

These upstream directions were adopted into the local architecture during the
2026-04-23 sync:

- `b7bdf32d` session slot ownership after stop/reset
- `d72985b7` reset handoff and stale session lock recovery
- `36730b90` clear approval state on `/new`
- `050aabe2` reset approval and yolo state on session boundary
- `b52123eb` stale PID and planned restart recovery
- `4c02e459` `os.kill(pid, 0)` `OSError` hardening
- `d45c738a` user D-Bus preflight for `systemctl --user`
- `24e8a6e7` skills sync collision reset-hint
- `3a97fb3d` skills sync manifest-poison fix

These were adapted into the local architecture, not used to replace it
wholesale.

## Adapted On This Branch

### First low-conflict slice

The merged sync adopted the following upstream ideas while keeping the local
architecture:

- `4c02e459`:
  catch `OSError` around stale PID existence checks in `gateway/status.py`
- `3a97fb3d`:
  avoid poisoning the bundled-skills manifest on a new-skill collision
- `24e8a6e7`:
  print a reset hint when a bundled skill collides with a local skill of the
  same name
- `d45c738a`:
  preflight user D-Bus reachability before `systemctl --user start/restart`
  and show a clean remediation path instead of leaving the user with a raw
  service failure

Why these were taken under the fresh-upstream test:

- they improve correctness and operator guidance
- they do not replace the local deferred reload/restart design
- they directly strengthen the `putter`/skills-sync and gateway service
  failure families we hit recently

### Session-boundary and run-generation guard slice

The merged sync also adopted the following upstream ideas in `gateway/run.py`:

- `050aabe2`:
  clear session-scoped approval and `/yolo` state on session boundaries
  such as `/resume`, `/branch`, and `/reset`
- `36730b90`:
  make sure `/new` and the shared boundary-clear helper wipe only the target
  session's security state
- `b7bdf32d`:
  guard running-agent slot promotion and release with the session run
  generation so an older unwind cannot clobber a newer turn's state

Why these were taken under the fresh-upstream test:

- they close correctness gaps around stale approvals surviving a conversation
  switch
- they reduce the chance that stale async work deletes the current session's
  running-agent slot
- they fit cleanly around the local reload/restart architecture instead of
  replacing it

## Decisions To Record For Each Sync Pass

For every upstream sync attempt, append or update notes covering:

1. Stayed local:
   which files stayed on the private method and why.
2. Re-aligned with upstream:
   which upstream commits or behaviors were adopted and why.
3. Dropped local divergence:
   where upstream became clearly better and the local method was removed.
4. Deferred gaps:
   what still differs and what evidence would justify changing it later.

5. Obsolescence test:
   if upstream now covers the old local goal, say that the local divergence is
   obsolete and remove it rather than preserving it out of habit.

## Divergences Now Obsolete

The following pre-sync states are obsolete and should not be treated as current
design:

- the retired `self-improve/upstream-sync-20260423` branch as a live staging
  baseline
- “still need to complete the current selective merge” wording from the old
  triage pass
- any assumption that being `behind upstream` is itself the target metric

## Current Open Gaps

- Upstream still does not subsume the local pod-safe reload/restart design.
- The sync workflow still depends on engineer review for design-sensitive
  overlap; that remains intentional.
- Future upstream changes in gateway restart, routing, skills sync, and pod
  workflow surfaces still need the fresh-upstream test instead of blind merges.
