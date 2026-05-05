---
name: putter
description: Opportunistically find and attempt one bounded, low-risk useful task when Hermes is idle; prefer the highest-value bounded task, even when it is old or substantial, and stop cleanly when there is nothing worth doing.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [hermes, autonomy, introspection, maintenance, dogfooding, self-improvement]
    related_skills: [hermes-introspection, hermes-agent, codebase-inspection, systematic-debugging]
    compact_invocation: |
      # Putter Compact Invocation

      Do one bounded, low-risk useful task, or report that none is worth doing.

      Rules:
      - Inspect a small bounded evidence set before choosing.
      - Prefer local evidence: current repo, recent Hermes logs/sessions, durable reports, todo state, and docs.
      - Do not run indefinitely, spend money, merge, deploy, restart services, mutate live infra, or push directly to main unless the user explicitly asks.
      - If the task needs broader review, propose the exact next action instead of doing it.
      - If changing files in a git repo, validate narrowly and make a local commit only when the scope is unambiguous.
      - Do not call skill_view(name="putter") during compact invocation. If these rules are insufficient, stop with `blocked` and name the missing detail.

      Final response:
      - State `changed`, `proposed`, `blocked`, `failed usefully`, or `nothing worth doing`.
      - Include concise evidence, validation performed, and the next bounded action if any.
    cron_invocation: |
      # Scheduled Putter Compact Invocation

      Run one very small idle-maintenance pass.

      Rules:
      - Inspect at most three candidate sources before deciding.
      - If there is no clear bounded task with a concrete validation path, respond exactly `[SILENT]`.
      - Do not create, update, pause, resume, run, or remove cron jobs or scheduler state.
      - Do not continue a prior autonomous search across fresh cron sessions.
      - Do not push, deploy, restart services, mutate live infra, or change secrets.
      - If context pressure or runtime limits block a clean finish, stop and return `Putter result: failed usefully` with what was inspected and the next bounded action.

      Final response:
      - For real findings, include a concise evidence-based Decision trace.
      - For no findings, output only `[SILENT]`.
---

# Putter

Use this skill when the user wants Hermes to stop waiting for a fully specified
task and go find one bounded useful thing to do.

The intent is bounded opportunistic maintenance. It is not permission to
run indefinitely, spend money, change production, merge code, deploy services,
or rewrite live memory without review.

Putter is allowed to improve Putter. If a pass reveals a new low-risk task
category, source, validation pattern, or guardrail that should be part of this
skill, it may either patch this skill directly as its one bounded task or propose
the exact scope expansion in its final response. Patch directly only when the
new guidance is clearly conservative, locally useful, and consistent with the
guardrails below.

## Contract

When invoked, do one of three things:

1. Find one low-risk useful task, attempt it, validate what you can, and report
   the result.
2. Find one useful task but decide it needs approval or broader context, then
   report the proposed next action instead of doing it.
3. Find nothing worth doing and say so briefly.

All three outcomes are acceptable. Failed attempts are acceptable if you leave
usable evidence about what failed and what was learned.

When this skill is invoked from a scheduled cron job, be stricter than in an
interactive `/putter` session:

- inspect at most three candidate sources before choosing a task or stopping
- if there is no clear bounded task with a concrete validation path, return
  exactly `[SILENT]`
- do not continue or resume a prior autonomous search across fresh cron
  sessions just because the last run compacted or stopped mid-investigation
- do not create, update, pause, resume, run, or remove cron jobs or other
  scheduler state; leave that as a proposal only
- if context pressure, compaction, or runtime limits block a clean finish, stop
  and return `failed usefully` with what was inspected and the next bounded
  action instead of expanding the search

Do not call a task "done" just because data was collected or a ledger entry was
written. A job well done has:

- a concrete outcome: file changed, check completed, issue isolated, or proposal
  made with enough evidence for the next operator to act;
- a durable path: repo changes are in a git checkout, state changes are in the
  intended persistent store, and reports are in a known persistent location;
- a closed loop: the next consumer is named, such as a cron job, bootstrap
  script, skill, ledger, PR, or operator command;
- validation: a targeted command, read-back, or explicit blocked reason;
- honest status: use `changed`, `proposed`, `blocked`, or `failed usefully`
  according to what actually happened.

If the pass changes files inside any git repository, finish by creating an
informative local commit for those changes before reporting success. Also update
`HERMES_CHANGELOG.md` with a short review entry and commit link. If unrelated
dirty changes make a safe commit ambiguous, stop and report that ambiguity
instead of papering over it.

For Hermes self-edits inside the cluster pod, the only durable writable repo is
`/opt/data/workspace/hermes-agent-private`. Before changing Hermes code, deployment
manifests, skills, tests, or docs, verify the working directory is that checkout
or a child of it. If the current directory is `/opt/data/hermes-agent`, stop and
report the mismatch; that path is a compatibility alias or archived reference,
not a place to create new work. Start code/deploy changes with
`/opt/data/scripts/hermes_self_edit.py start <slug>` from the canonical checkout
so the branch, tests, and PR path are tracked.
Do not "fix" Hermes by editing installed/internal copies under `~/.hermes`,
`/opt/hermes`, `/app`, or `/opt/data/hermes-agent` when the same change can be
made in the repo. Repo edits are the default durable path; internal/runtime
paths are exceptional recovery-only targets when no repo-backed alternative
exists, and the reason must be stated explicitly.

When Putter is running inside the cluster pod and a bounded task changes Hermes
runtime/config/deploy behavior, validate activation using the pod-native reload
signals before declaring success:

- for config, prompt, or skill changes, check the gateway runtime state or API
  health fields for `last_runtime_reload_at`
- for repo-backed Python code changes, check for `auto_restart_pending` and then
  verify it clears after the deferred in-pod gateway self-restart
- prefer `http://127.0.0.1:8642/health`, `http://127.0.0.1:8642/health/detailed`,
  or `$HERMES_HOME/gateway_state.json` over guessing whether the change is live
- if an automation path depends on lifecycle transitions, use the gateway hooks
  `gateway:runtime_reload` and `gateway:restart_pending` as the authoritative
  machine-facing workflow signals

Putter may keep low-risk maintenance as local commits. Escalate to a PR in
`example-org/hermes-agent-private` for runtime code, deployment manifests,
auth/approval/RBAC/sudo/secret handling, MCP exposure, model routing,
memory/session persistence, context compression, public mirror behavior,
multi-file refactors, failed/untested changes, or any change that needs review.
If opening a PR, pushing a non-`main` branch is allowed. Never push directly to
`main`, merge PRs, deploy, or mutate live services unless the user explicitly
asks.

## Budget

Keep the pass small unless the user gives a larger budget.

- Default search budget: 5 to 10 minutes.
- Default execution budget: one focused change or one focused investigation.
- Default scope: current repo, current Hermes profile, recent sessions,
  improvement reports, todo state, and local docs.
- Stop after the first meaningful completed task, blocked task, or clear "no
  worthwhile task found" result.

Bounded does not mean trivial. A task may still be a good putter candidate when
it is older, never done before, or somewhat substantial, if all of these are
true:

- the pass can name a clear finish line
- the work fits one coherent objective instead of sprawling into many threads
- the validation path is concrete
- doing it now would retire recurring debt or unblock later maintenance

Do not skip a candidate merely because it is old, stale, unfamiliar, or larger
than a typo fix. Skip it only when the stop condition, risk, or validation path
is unclear.

If the user supplies a target after `/putter`, treat it as the focus. Examples:

- `/putter docs`
- `/putter tests`
- `/putter introspection`
- `/putter find a bounded cleanup`
- `/putter cache cleanup`
- `/putter sync docs with deploy`
- `/putter research anything stale`
- `/putter compact noisy context notes`
- `/putter review k3s resources`
- `/putter review cluster SIEM`

## Candidate Sources

Prefer local evidence before browsing.

Look for candidate work in this order:

1. Current user instruction after `/putter`.
2. Current temporal context injected with the skill invocation. Treat it as the
   anchor for "today", "latest", "recent", "stale", "overdue", and schedule
   comparisons.
3. Maintenance freshness ledger, when the tool is available:
   - call `maintenance_freshness(action="seed")` once per profile/session if
     the ledger may not exist yet
   - call `maintenance_freshness(action="due", limit=10)` to see stale
     maintenance candidates before browsing or broad searching
   - prefer due items with concrete local validation paths, but keep the pass
     bounded and low-risk
4. Active todo state, if a todo tool is available.
5. Current git status and obvious unfinished local work.
   In the Hermes pod, check `/opt/data/workspace/hermes-agent-private` first. Treat
   dirty state under `/opt/data/hermes-agent` as orphaned legacy state to report
   or triage, not as the primary worktree.
6. Latest introspection report:
   `$HERMES_HOME/self-improvement/introspection/reports/latest.md`.
7. Latest edge-watch or self-improvement report:
   `$HERMES_HOME/self-improvement/reports/` or
   `$HERMES_HOME/cron/output/edge-watch/`.
8. Recent session search for repeated corrections, failed tests, tool errors,
   "TODO", "follow up", "broken", "needs docs", or similar.
9. Repo-local docs and tests around recently changed files.
10. Existing skills that are stale, missing validation steps, or missing a
   troubleshooting note.

Use web or external sources only when the chosen candidate explicitly depends
on current outside facts.

## Good Putter Tasks

Prefer tasks that are useful even if modest:

### Repo Cleanup

- remove obsolete generated files when the generating source is present and the
  deletion is clearly safe
- delete empty temporary directories under repo-local scratch paths
- normalize stale comments that contradict nearby code
- fix broken local Markdown links
- fix typos in docs, command examples, comments, and skill instructions
- update a docs map or index after a new doc or script was added
- tighten overly broad TODOs into concrete follow-up items
- remove duplicate documentation paragraphs when the canonical location is
  obvious
- add missing `bash -n`, link-check, or targeted test notes to docs
- make examples match current filenames, command names, or config keys
- check whether checked-in generated embeds are synced with source scripts and
  run the existing sync/check command if one exists
- inspect recently changed files for missing nearby tests or docs
- verify executable bits on shell scripts that are meant to be run directly

### Low-Risk Updates

- refresh generated indexes or manifests using existing repo scripts
- update copied or embedded configmap/script content with existing sync tooling
- run a package manager's metadata-only audit when it does not mutate lockfiles
  unless the user asked for lockfile updates
- when promoting captured runtime installs, verify the package list changed in
  the durable repo checkout or explicitly pass `repo_root`; do not treat edits
  to image-copy paths such as `/opt/hermes` as durable unless a bootstrap or
  ConfigMap path will actually consume them
- update a stale internal reference to a renamed command, file, skill, or doc
- add a short compatibility note when code already supports a newer path but
  docs still describe the old one
- inspect dependency notices or lockfile drift and report a proposed update
  rather than upgrading by default
- run formatters only on files already changed in the current task, unless the
  repo has an explicit narrow formatting command
- verify current branch/repo remote state and report drift without pushing

### Research And Inspection

- inspect the latest introspection report and pick one actionable finding
- inspect the latest edge-watch digest and summarize one candidate follow-up
- search recent sessions for repeated user corrections that should become a
  skill or memory proposal
- search for recurring tool failures and identify the smallest preflight or doc
  improvement
- review failed trajectories and extract one reproducible test idea
- check issue/PR references already present in local reports and summarize the
  likely next action
- browse only when the candidate depends on current external facts, and cite the
  source in the final report
- compare repo docs against current local scripts or manifests for drift
- inspect logs for one recurring warning and propose a bounded fix

### Sync Tasks

- compare README, deployment docs, and decision docs for inconsistent wording
- ensure public mirror publisher allowlists include newly linked public docs
- check whether new docs linked from README are included in publication scripts
- verify Kubernetes configmap embeds are in sync with source files
- check whether CronJob docs match actual schedule names and output paths
- confirm skills mentioned in docs exist and have matching frontmatter names
- sync a skill's validation instructions with current AGENTS.md testing policy
- ensure generated examples still match the template or source manifests
- verify command aliases in docs match `hermes_cli/commands.py`
- check that gateway and CLI help surfaces still describe the same command

### K3s Resource Review

- run `hermes_resource_review.py --write-report` inside the pod when available
- run `python3 deploy/k8s/hermes-resource-review.py --local-only` from the repo
  when only manifests are available
- inspect gateway, proxy, profile-worker, Hindsight, and maintenance CronJob
  requests/limits for drift against observed usage
- look for `OOMKilled`, high restart counts, near-limit memory, or sustained CPU
  saturation before recommending increases
- treat a single low-usage snapshot as weak evidence; recommend decreases only
  after repeated low-usage observations
- propose manifest patches or `kubectl set resources` commands with rationale,
  but do not apply them without explicit user approval
- prefer durable manifest changes in git over one-off live patches
- include the observed usage, current request/limit, suggested target, and
  validation command in the final report

### Security And SIEM Review

- run the `siem-review` skill for a bounded read-only review of cluster SIEM
  health, recent alert-like events, detection gaps, and noisy sources
- inspect `../k3s/docs/SECURITY-PLATFORM-SETUP.md`, `../k3s/siem/`, and
  `../security-lab/` docs only as supporting context; prefer live SIEM data when
  available
- classify findings as incident, misconfiguration, operational, benign/noise,
  or gap, and propose conservative next steps
- do not delete indices, teardown namespaces, disable alerting, rotate secrets,
  or apply live cluster changes unless the user explicitly asks
- if the review suggests a recurring task, update the repo cron seed manifest
  and live cron state rather than only leaving a one-off note

### Cache, State, And Compaction

- identify obviously stale repo-local caches such as `.pytest_cache`, coverage
  output, build output, or tool scratch directories and ask before deleting if
  they are outside ignored/generated paths
- clear only safe local caches when they are known-regenerable and not needed
  for current debugging
- compact or summarize noisy investigation notes into a shorter local report
- move useful scratch findings into `.hermes/putter/` and remove redundant
  scratch notes when safe
- propose memory compaction when prompt-visible memory contains task progress
  instead of durable facts
- propose session/context compression when the active conversation has become
  long and repetitive
- inspect level-up harvest proposals and identify one safe promotion candidate
  without promoting it automatically
- inspect recovery recipes for repeated failures and suggest one recipe/doc
  update

### Skills And Memory

- add a missing "when to use this skill" sentence to a skill
- add a missing validation or troubleshooting section to a skill
- split a bloated skill by moving deep reference material into `references/`
- update related skill metadata when a companion skill was added
- turn a repeated operator preference into a memory proposal, not a blind write
- turn a repeated workflow correction into a skill patch
- check whether a disabled or missing skill explains repeated task friction
- add examples to a skill when invocation syntax is ambiguous
- remove stale setup instructions that no longer match code

### Tests And Validation

- run a narrow test selector for recently changed code
- add a small regression test for a deterministic bug found in reports
- add a shell syntax check for a touched script
- add or update a fixture when the expected behavior is already clear
- reproduce one reported failure and record the exact command/result
- improve a test name or assertion message when it hides the behavior being
  protected
- inspect skipped or xfailed tests and report whether one can be made active
- verify docs-only changes with link checks and syntax checks

### General Improvement

- add or improve docs for a recently added feature
- add a missing validation command to a skill
- turn a repeated correction into a skill note or memory proposal
- write a small regression test for a clearly reproducible issue
- tighten an error message or preflight check
- clean up a stale TODO when the intended fix is obvious
- summarize a fresh introspection or edge-watch finding into an actionable
  proposal
- run a targeted test or script and record the result
- inspect a suspicious failure report and identify the smallest next fix
- improve an error message that currently sends the operator to the wrong place
- add a preflight check for a common missing file, env var, or tool
- reduce duplicate operator steps in docs or scripts
- identify one likely flaky test and document the suspected cause
- make a local command example copy-pasteable
- propose a safer default when evidence shows repeated confusion
- create a tiny follow-up issue draft or todo entry when implementation is not
  safe in the current pass

### Putter Self-Improvement

- add a newly discovered low-risk task category to this skill
- add a missing candidate source that helped find useful idle work
- add a validation pattern that made a putter task safer or faster
- add a guardrail after finding an operation that looked tempting but was too
  risky for idle autonomy
- refine the selection heuristic when a pass chose poorly or stopped too late
- add examples for common focus strings such as docs, cache, sync, tests,
  introspection, research, memory, or deploy-docs
- move overly long putter guidance into a reference file if the skill becomes
  too large for routine loading
- propose a new scheduled job only as a proposal; do not create or enable it
  from a putter pass unless the user explicitly asked for scheduling

## Bad Putter Tasks

Do not choose tasks that require broad authority or high blast radius:

- deploy, restart, or mutate live infrastructure
- push, merge, tag, publish, or open PRs unless the user explicitly asks
- edit secrets, credentials, auth tokens, or private endpoints
- make large refactors
- upgrade dependency stacks speculatively
- rewrite memory wholesale
- alter scheduler cadence or production CronJobs without a clear request
- create, update, pause, resume, run, or remove scheduled jobs from a
  scheduled putter pass
- change live Kubernetes resource requests/limits, restart workloads, or patch
  deployments/CronJobs without explicit user approval
- continue working after the first substantial task is complete
- delete logs, reports, caches, or generated output when they may be evidence
  for an active investigation. Preserve evidence first; if cleanup still looks
  worthwhile, summarize the safe deletion candidate and ask or leave it as a
  proposal.
- run broad destructive cleanup commands such as `git clean`, `rm -rf`, or
  package-manager prune commands without explicit user approval
- change lockfiles, dependency versions, model routing, or provider defaults
  without evidence and a validation path
- rewrite public documentation with private operational details
- change Kubernetes resource limits, secrets, ingress, storage, or restart
  policy without a specific operational request
- mutate shared memory, Hindsight, harvest proposals, or correction rules
  directly unless the user explicitly asks for that promotion/change
- background a long-running process without a clear stop condition
- browse broadly or scrape noisy sources without a targeted research question
- expand Putter into high-risk work just because a task is common. New putter
  categories must remain low-risk, bounded, inspectable, and locally
  validatable.

Do not reject a task only because it looks "big" at first glance. If the work
can be reduced to one bounded objective with a clear validation step, it is
still eligible.

## Selection Heuristic

Score candidates informally:

- impact: will this remove recurring friction or preserve useful knowledge?
- confidence: is the right action obvious from evidence?
- risk: can this be undone and tested locally?
- boundedness: can it fit inside one coherent pass with a named stop condition?
- validation: is there a targeted command or review check?

Age, backlog status, or novelty are not negative factors by themselves. A stale
or never-before-attempted task can be the right pick if it now has a clear,
bounded path.

Pick the highest-impact candidate that is low risk, high confidence, bounded,
and validatable. Do not automatically prefer the tiniest task when a somewhat
larger bounded task would retire more recurring debt. If none meet that bar,
stop.

## Execution Pattern

1. Announce the bounded search scope.
2. Inspect bounded evidence.
3. Pick one candidate or stop.
4. State the intended action before editing.
5. Make the smallest useful change that fully resolves the chosen bounded task,
   or perform the focused investigation.
6. Validate with the narrowest relevant check.
7. If you collected data, identify the next consumer before calling the task
   complete. If no code, docs, config, cron, memory, skill, PR, or operator
   action will use it, report the result as `proposed` or `blocked`.
8. If the task corresponds to a freshness ledger item, record the result with
   `maintenance_freshness(action="record", key="<item-key>", status="ok|blocked|failed|proposed", evidence="<short path/commit/command/result>", actor="putter")`.
   Do this after validation so the ledger reflects what actually happened.
9. Report:
   - what was inspected
   - what was chosen
   - what changed or why nothing changed
   - validation result
   - what will consume or act on the collected data
   - any learning worth preserving

For Hermes repo tests, activate the environment and use the wrapper:

```bash
source venv/bin/activate
scripts/run_tests.sh <selector>
```

If this checkout uses `.venv` instead of `venv`, use:

```bash
source .venv/bin/activate
scripts/run_tests.sh <selector>
```

Do not call `pytest` directly unless the wrapper is impossible to use.

## Learning From Failure

If the attempt fails, do not treat that as wasted work.

Leave one of these behind when appropriate:

- a short final note with the failed command and likely next step
- a todo item, if the todo tool is available and the next step is concrete
- a skill patch proposal when a reusable procedure was missing
- a memory proposal when the lesson is a stable user/environment preference
- a small report under `.hermes/putter/` in the active workspace when there is
  useful evidence but no code/docs change

Do not create noisy state for every idle pass. Only write a report when it will
help the next agent avoid repeating the same investigation.

## Final Response Shape

Keep the final response compact:

```md
Putter result: <changed|blocked|nothing worth doing|failed usefully>

Decision trace: <2-4 bullets naming the evidence checked, chosen task, and why
broader/riskier options were skipped; summarize rationale without exposing
hidden chain-of-thought>
Inspected: ...
Chose: ...
Changed: ...
Validation: ...
Learning: ...
```

If nothing was found, say that directly and stop.
