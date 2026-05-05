---
name: hermes-local-llm-promotion-handoff
description: Turn a nightly local-LLM promotion or remediation candidate into a human-review handoff: create a deterministic approval packet, branch, commit, and draft PR, then send an approval email to keith@snape.tech with the reasoning and evidence.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [hermes, nightly, local-models, promotion, remediation, github, email, approvals]
    category: autonomy
    related_skills: [hermes-local-llm-nightly, hermes-upstream-sync, github-pr-workflow]
---

# Hermes Local LLM Promotion Handoff

Use this skill when the nightly local-LLM review found a real promotion or
remediation candidate that crosses into human-gated territory.

Read [references/workflow-map.md](references/workflow-map.md) before acting.

## Goal

Convert a qualified nightly finding into a reviewable handoff:

- deterministic packet on disk
- dedicated git branch
- draft PR against `main`
- approval email to `keith@snape.tech`

This skill exists so the nightly benchmark loop can stay bounded while still
producing operator-ready proposals.

## When To Use It

Use this skill only when the nightly pass found something that should change
Hermes behavior after human review, for example:

- a new retained candidate should replace an existing default
- a runtime/config/service change is needed to unlock a validated model win
- a benchmark-backed remediation is needed to correct a degraded local lane

Do not use it for:

- ordinary rejects or deletions
- speculative ideas without repeatable evidence
- noisy "maybe later" follow-ups

## Workflow

1. Start from the latest nightly report and state:
   - `$HERMES_HOME/self-improvement/local-llm-nightly/reports/latest.md`
   - `$HERMES_HOME/self-improvement/local-llm-nightly/state.json`
2. Confirm the finding really needs human approval.
3. Write a deterministic handoff packet with:
   - `python scripts/local_llm_handoff_packet.py ...`
4. Create or update a dedicated branch named like:
   - `llm-handoff/YYYY-MM-DD-<slug>`
5. Commit only the files needed for the proposal:
   - benchmark docs
   - scorecards
   - service/config patches if the remediation is concrete and validated
   - the handoff packet artifacts
6. Push the branch and open or update a draft PR against `main`.
7. Send the reasoning summary to `keith@snape.tech`.
8. In the final response, either:
   - output `[SILENT]` if no approval-worthy candidate exists
   - or provide a terse structured summary suitable for the email body

## Branch And PR Rules

- one branch per distinct promotion/remediation proposal
- prefer draft PRs
- keep PR scope narrow and evidence-backed
- include rollback/operational risk when the proposal touches live serving
- do not merge
- do not restart the live primary service
- do not switch production routing

## Email Rules

The email must explain:

- what changed
- why Hermes thinks the promotion/remediation is worth approval
- what evidence was used
- what the operational risks or caveats are
- where the draft PR and packet live

Default recipient:

- `keith@snape.tech`

Use cron auto-delivery to `email:keith@snape.tech` when available. If direct
email delivery is unavailable, still write the rendered email body to the
handoff packet directory so the operator has the exact message content.

## Guardrails

- do not open a PR without a deterministic on-disk handoff packet
- do not send a "promotion" email for a candidate that has unresolved
  regressions
- do not hide uncertainty; name open questions directly
- do not treat self-authored PR approval as possible; GitHub blocks it
