# Hermes Agent Evolved

This repository is built from upstream Hermes Agent with a public-safe Snapetech
overlay.

Base:

- upstream: `NousResearch/hermes-agent`
- upstream_ref: `main`
- upstream_sha: `de9238d37e778da3654595a49cc7ae5b8a10fa60`

Overlay:

- private_source_ref: `HEAD`
- private_source_sha: `1a37fb53e14bc6ba7b1c976ff929c4ccd535a078`
- private deployment history is not published here

Publication rules:

- Keep live Kubernetes manifests, host-specific runbooks, self-hosted runner
  labels, internal hostnames, private service IPs, Discord IDs, SSH key names,
  and GitLab topology in the private package repository.
- Remove inherited upstream GitHub Actions workflows from the public mirror.
  Public automation should be added only when it is purpose-built for this
  sanitized overlay and does not require private infrastructure or secrets.
- Mirror all tracked private-fork files by default, except paths blocked by the
  publication denylist. The sanitizer and leak scans are the publication gate.
- Publish generalized deployment examples and reusable deployment utilities;
  keep live manifests, host wrappers, runtime ConfigMaps, and operator runbooks
  private unless they have a dedicated public-safe form.
- Raw benchmark run artifacts are not published. Publish derived summaries,
  benchmark scripts, candidate manifests, and capability cards only after
  hostnames, local paths, service IPs, and runner-specific labels are scrubbed.
- Runtime credentials belong in environment variables, Kubernetes Secrets, or
  GitHub repository secrets. They must never be committed.

Start here:

- `docs/evolved-decisions.md`
- `docs/evolved-tooling.md`
- `docs/improvement-system.md`
- `docs/research-update-cycles.md`
- `docs/reproducibility-audit.md`
- `docs/evolved-model-matrix.md`
- `docs/upstream-sync.md`
- `skills/autonomous-ai-agents/hermes-introspection/SKILL.md`
- `skills/autonomous-ai-agents/putter/SKILL.md`
- `deploy/k8s/README.md`
- `deploy/k8s/hermes-resource-review.py`
- `deploy/k8s/public-examples/README.md`
- `benchmarks/llm/model_capability_cards.md`
- `benchmarks/llm/slm_candidates.tsv`
