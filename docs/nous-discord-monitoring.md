# Nous Discord Monitoring Plan

Assessment date: 2026-04-24.

Hermes cannot use a bot account in the Nous Research Discord. For this guild,
use the authenticated browser-DOM monitor (`discord-wayland-monitor.py`) and
extract structured DOM messages, anchors, GitHub links, PR links, and message
URLs. Do not use OCR for routine monitoring.

Discord virtualizes chat history. There is no reliable "capture all" command:
`Ctrl+A`, page text extraction, and full-page screenshots only see currently
loaded rows. The correct monitor shape is:

1. Navigate to a specific channel URL.
2. Run `scrape --since <last-capture-date-or-timestamp> --pages N --direction up`.
3. Page upward from the latest loaded messages until the lower-bound date is
   reached, then filter and sort messages oldest-to-newest so processing works
   forward from the last capture point.
4. Require `delta_complete: true`. If the result stops with
   `stop_reason: max_pages`, the capture is partial and the job must continue
   with a larger page budget or mark the channel incomplete.
5. Deduplicate by Discord message ID or message text/link fingerprint.
6. Persist a per-channel watermark/fingerprint set.
7. Record only findings that meet the channel's extraction policy.

## Recommended Channels

| Channel | ID | Cadence | Extract | Action |
| --- | --- | --- | --- | --- |
| `hermes-announcements` | `1490858802726043759` | quick, every 1-2h | release notes, feature announcements, docs links, GitHub PRs, media links | Treat as official/high-confidence Hermes signal; include in daily digest and immediate alerts for releases, breaking changes, or new capabilities. |
| `announcements` | `1145143867818119272` | daily | Nous-wide releases, model/platform announcements, Hermes mentions, external links | Include only Hermes-relevant or model/provider-routing-relevant items; avoid duplicating `hermes-announcements`. |
| `developers` | `1491258766648283238` | daily, plus quick when active/unread | bug reports, implementation discussion, GitHub issues/PRs, maintainer notes, reproducible workflows | Create candidate findings with medium confidence; require corroboration before action unless a maintainer gives concrete instructions. |
| `research-papers` | `1104063238934626386` | daily | arXiv links, GitHub repos, model/eval/training papers, agent-relevant methods | Enrich existing arXiv/HF lanes; only promote papers tied to Hermes agent capabilities, local inference, evaluation, or tool use. |
| `interesting-links` | `1132352574750728192` | daily | external articles, agent-framework links, security/privacy posts, repos | Route through web extraction and classify; alert only for security, install risk, provider/runtime changes, or notable agent tooling. |
| `support-threads` | `1485307775444844625` | daily | thread titles, log/debug guidance, repeated user failures, install/runtime issues | Cluster pain points; convert repeated failures into docs, tests, or issue candidates. Do not ingest private logs unless explicitly shared for that purpose. |
| `plugins-skills-and-skins` | `1485392832154832906` | daily | skill/plugin repos, PRs/issues, new skins, user workflows | Feed skill/plugin review backlog; consider repo links for ecosystem-watch and optional-skill candidates. |
| `community-projects-showcase` | `1316137596535177246` | weekly | showcase repos, dashboards, proxies, integrations, PR links | Track ecosystem projects and possible integration ideas; low urgency unless a repo is directly useful to deployment. |
| `creative-hackathon-submissions` | `1494773540711432394` | weekly while active | project links, demos, repos, workflows | Harvest examples and creative workflow ideas; stop or reduce cadence after the event quiets down. |

## Opportunistic Channels

| Channel | ID | Cadence | Notes |
| --- | --- | --- | --- |
| `github-tracker` | `1478591073629765744` | fallback/cross-check only | Mostly duplicates GitHub webhook/API data. Prefer direct GitHub PR/issue/release/commit/org-event collection; sample this only to validate Discord webhook health or recover if GitHub auth/search is unavailable. |
| `getting-started` | `1487849039696236857` | weekly or on docs changes | Mostly stable docs/onboarding links. Useful as docs baseline, not a frequent feed. |
| `hermes-agent` | `1476316988992258300` | daily sample only | High chatter. Extract support-like questions and maintainer answers, but avoid treating every conversation as signal. |
| `hermes-agent-cn` | `1492442153383628850` | weekly sample | Useful for international support patterns. Translate summaries only; do not alert unless a clear bug or docs gap appears. |
| `ask-about-llms` | `1154120232051408927` | weekly | Provider/model pricing and quality chatter. Promote only concrete provider/runtime implications. |
| `ai-general` | `1149866623109439599` | weekly | Broad AI discussion. Use as weak signal for model/provider trends, not as Hermes operations input. |
| `creative-hackathon-info` | `1494775370090545192` | event-bound weekly | Event metadata only. Disable after hackathon window ends. |

## Do Not Monitor Routinely

| Channel | ID | Reason |
| --- | --- | --- |
| `rules` | `1151297754992234496` | Static server policy; check only when channel text changes. |
| `memes` | `1365353718924709958` | Mostly images/social content; low operational value. |
| `off-topic` | `1109649177689980928` | High noise and weak actionability. |

## Finding Rules

Use channel-specific confidence:

- Official/high confidence: `hermes-announcements`, `announcements`.
- Structured/high confidence: direct GitHub API/CLI for PR, issue, release, commit, and org-event metadata.
- Fallback structured signal: `github-tracker` only when GitHub collection is degraded or when validating Discord webhook health.
- Community/medium confidence: `developers`, `support-threads`, `plugins-skills-and-skins`, `community-projects-showcase`.
- Weak/context signal: `ai-general`, `ask-about-llms`, `interesting-links`, `hermes-agent`, `hermes-agent-cn`.

Immediate alerts are appropriate for:

- Hermes release or breaking-change announcements.
- Security/privacy issues affecting Hermes install, agent auth, browser control, MCP, gateway, or provider routing.
- Repeated support failures with clear reproduction.
- Maintainer-confirmed bugs or roadmap changes.
- GitHub PRs touching gateway, auth, MCP exposure, tool execution, memory/session persistence, context compression, deployment, or runtime routing.

Daily digests should include:

- New official announcements.
- New or updated PRs from GitHub grouped by subsystem.
- Developer/support themes with evidence counts.
- New ecosystem repos/tools from showcase or plugin/skill channels.
- Research links only after dedupe against existing arXiv/HuggingFace lanes.

Weekly rollups should include:

- Slow-burn community projects.
- Plugin/skill candidates.
- Repeated support/documentation gaps.
- Low-confidence model/provider chatter worth watching but not acting on yet.

## Implementation Notes

Prefer MCP calls when Hermes has the monitor server enabled:

```text
discord_monitor_start(url="https://discord.com/channels/@me")
discord_monitor_goto(href="https://discord.com/channels/1053877538025386074/<channel_id>")
discord_monitor_scrape(pages=30, direction="up", since="yesterday")
discord_monitor_stop()
```

For Cron-style jobs, call `/opt/data/discord-wayland-monitor.py` directly from
the pod and write raw outputs under `/opt/data/self-improvement/raw/discord-web/`.
Only promote normalized findings into the Edge Watch database. Raw Discord
transcripts should not be committed to the repo.

Example CLI delta scrape:

```bash
/opt/data/discord-wayland-monitor.py goto \
  --href https://discord.com/channels/1053877538025386074/1478591073629765744 \
  --wait 8
/opt/data/discord-wayland-monitor.py scrape \
  --since yesterday \
  --pages 40 \
  --direction up \
  --output /opt/data/self-improvement/raw/discord-web/github-tracker.json
```
