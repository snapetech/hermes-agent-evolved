---
name: research-best-practices
description: General research workflow for Hermes: plan questions, choose primary sources, use Firecrawl/web tools, Edge-Watch, GitHub, arXiv, session/compaction recall, local evidence, and Hindsight without overclaiming. Use when asked to research a topic, find best practices, compare options, verify current facts, produce a sourced brief, investigate ecosystem movement, or turn research into safe follow-up actions.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [research, best-practices, evidence, sources, synthesis, verification, hermes-stack]
    category: research
    related_skills: [arxiv, blogwatcher, llm-wiki, research-paper-writing, putter]
---

# Research Best Practices

Use this skill for research tasks that need evidence quality, source choice,
current facts, or careful synthesis. It is the general research router for this
Hermes deployment; use narrower skills such as `arxiv`, `blogwatcher`,
`llm-wiki`, or `research-paper-writing` when the task clearly fits them.

## Research Contract

Answer the actual question, not a bigger one. Start with a short research plan
when the task is ambiguous or high stakes. Separate facts from inference, and
label uncertainty instead of smoothing it over.

For any changing fact, browse or query a current source. For any technical,
legal, medical, financial, security, or deployment-impacting claim, prefer
primary sources and local evidence over summaries.

Do not mutate production, push to `main`, merge, deploy, rotate secrets, or
change live resources as a result of research alone. Research may produce
recommendations, PR branches, issues, docs, or local commits according to the
repository policy.

## Source Priority

Use the least noisy source that can answer the question:

1. **Local truth:** repo files, tests, configs, logs, Kubernetes state, session
   search, compaction artifacts, Hindsight memory, Edge-Watch findings.
2. **Primary upstream truth:** official docs, release notes, source repos,
   issues, PRs, commits, standards, papers, vendor docs.
3. **Direct community evidence:** maintainer comments, reproducible bug reports,
   forum/Discord/Reddit posts with logs or configs.
4. **Secondary synthesis:** blog posts, videos, social posts, summaries. Use
   these for leads, not as final authority unless no better source exists.

If sources conflict, report the conflict and prefer the most direct, recent,
and reproducible source.

## Hermes Stack Workflow

For Hermes, Nous, or this deployment:

- Query Edge-Watch before re-browsing broad public surfaces:
  `/opt/data/scripts/hermes_edge_watch_query.py recent`, `search`, `alerts`,
  `digest`, or the `edge_watch.*` MCP tools.
- Use local repo search with `rg` for docs, code paths, and prior decisions.
- Use `session_search` for older conversations and `compaction_search` for
  details that may have been compacted out of the current session.
- Use Hindsight/shared memory for durable facts and decisions, but verify stale
  facts before acting.
- Use GitHub issues, PRs, releases, and commits for live project movement.
- Use `kubectl`, pod logs, and checked-in manifests for runtime claims about
  this cluster.

## Web And Paper Workflow

Use Firecrawl or web tools for web search and extraction when browsing is
needed. Prefer exact queries with entity names, versions, file paths, error
strings, or paper titles.

For papers:

- Start with arXiv/Semantic Scholar/official publisher pages where available.
- Capture title, authors, year, URL, and the specific claim the paper supports.
- Do not rely on abstracts alone when the answer depends on methods, metrics,
  limitations, or results.
- Distinguish "paper claims" from "field consensus" and from "our deployment
  should do this."

For software:

- Prefer official docs, source, releases, changelogs, issues/PRs, and tests.
- Verify commands against the installed version when local execution is safe.
- For recommendations, include compatibility, risk, migration cost, and how to
  validate.

## Synthesis Shape

Use this structure unless the user asks for something else:

- **Answer:** direct conclusion or current best option.
- **Evidence:** short bullets with source links or local file references.
- **Caveats:** what is uncertain, stale, disputed, or unverified.
- **Action:** smallest safe next step, test, PR, config change, or follow-up.

When giving recommendations, rank options by fit to the user's actual
constraints. Avoid generic "best practice" lists that ignore the local system.

## Quality Bar

- Cite or link every non-obvious external claim.
- Use absolute dates for current/latest claims.
- Do not quote long copyrighted passages.
- Do not present a single community post as established fact.
- Do not use screenshots, snippets, or model memory as sole evidence when a
  primary source is available.
- If the search failed, say what was searched and why it was insufficient.

## Durable Output

If the research creates a reusable workflow, update the relevant skill or docs.
If it creates a file change, follow the git policy: commit locally, update
`HERMES_CHANGELOG.md`, and use a PR branch for review-worthy changes.
