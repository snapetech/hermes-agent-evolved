# Upstream Sync Report

- generated_at: `2026-04-23T23:10:00Z`
- private_ref: `HEAD`
- private_sha: `8126a3bbd8e9d2ee63747d03fc0e39e61cbf3081`
- upstream_ref: `refs/remotes/upstream/main`
- upstream_sha: `bf196a3fb7a0c6b79f4ac88f458381c0eb801f0e`
- merge_base: `bf196a3fb7a0c6b79f4ac88f458381c0eb801f0e`
- private_only_commits: 223
- upstream_only_commits: 0

## Selective Merge Policy

- Do not blind-merge upstream into the private deployment fork.
- Assume a fresh start from current upstream and ask whether the local method is still what we would choose today.
- Keep local deployment design only where it is still intentional, required, and better than upstream for the Snapetech target.
- Prefer selective adaptation for gateway restart/reload behavior, pod deployment workflow, repo-first self-edit rules, and skills sync safeguards.
- Treat design-sensitive overlap as mandatory human review, even when the textual merge is clean.
- The invariant is that all required Snapetech outputs/tooling/connections still work, or newer Hermes behavior makes the custom path obsolete.

## Current Status

- `main` is now `0` behind `upstream/main`
- sync landed in merge commit `8126a3bb`
- `origin/main` and `gitlab/main` match local `main`
- the old upstream-sync staging branch has been deleted
- this report is now a post-merge baseline marker, not an open triage queue

## Post-Merge Notes

- Merge regressions fixed during validation:
  - duplicated `skip_context_files` / `skip_memory` wiring in `cli.py`
  - duplicated `--ignore-user-config` / `--ignore-rules` parser entries in
    `hermes_cli/main.py`
- Focused post-merge validation passed:
  - `470 passed`
- Remaining branch-only commits are the intentional private-fork overlay on top
  of the merged upstream baseline, not unsynced upstream debt

## Private-only Commits

- 590a0ef7 Improve gateway service restart recovery
- fc348eae Add idle-boundary gateway restart command
- dedb18bd Harden gateway pid checks and skills sync hints
- 3c2b4db2 Adapt model picker routing and cron putter flow
- e4d5511a Add split-brain regressions and refresh pod routing docs
- ba170329 Add cloud fallbacks and route cooldown telemetry
- cfd58d65 Adapt adapter session recovery and route failover state
- 540d3a7a Integrate queue-aware local routing and upstream sync fixes
- ad2707d5 Adapt low-conflict upstream gateway and skills fixes
- 7bb42032 Codify selective upstream sync workflow
- ce6ccbf3 Add upstream sync triage report
- d5a743a5 Capture remaining qwen27 benchmark artifacts
- b98b9005 Capture remaining local workspace changes
- cf62cb81 Document in-pod reload and restart workflow
- 25b9e904 Expose reload state via api health and hooks
- 7ad3d194 Expose gateway reload and restart pending state
- 10792e95 Restart gateway in-place inside k8s pods
- 5bc1b390 Auto-restart gateway on safe code changes
- 9550149b Add live runtime reload command
- 4ca857ec Hot-reload prompt and skill metadata on next turn
- 4e6c357e Enforce repo-first Hermes self-edits
- aab32a4d Fix deploy bootstrap and package watchdog helper (#3)
- 9a4bde59 Commit full dirty workspace state
- c2708c5e Fix evolved mirror sanitizer and benchmark allowlist
- ee6fa7ee Add split-card local model test plan
- 0607edc0 Document Proton Bridge email setup
- 0323f39a Document email IMAP security modes
- 198c0735 Document expanded local model wave2 results
- 505b927e Harden web content handling and record benchmark artifacts
- e86b050c Add expanded wave2 benchmark run marker
- 8c7556d8 Make shared memory bootstrap idempotent
- 0c6ff247 Expire stale TUI pending turns
- b3884b33 Clean up failed Discord startup tasks
- 04b8e731 Bound TUI pending turn recovery retries
- 973eb4f4 Document Nous edge watch local model results
- 50d03eb1 Add NousCoder no-think smoke output
- 9a44026e Add NousCoder edge-watch benchmark outputs
- 62ad6dde Improve cron putter diagnostics
- c4766c76 Add expanded local model benchmark notes
- cdaeebb6 Harden evolved mirror SIEM exclusions
- e295254f Add local model benchmark scorecard
- feeb0948 Restore main after no-op pod repo sync
- 0217af51 Canonicalize pod self-edit checkout
- bcc73f70 Expand 7900 XT local model benchmark matrix
- 9d302bc6 Merge remote-tracking branch 'upstream/main'
- 7969a5b9 Merge remote-tracking branch 'upstream/main'
- 00f3c6e6 Retry Hindsight client install in deploy image
- 2d0dc279 Apply upstream Hermes edge fixes
- d6db8070 Correct GLM validator context metadata
- 3b55954f Harden local deploy Cursor install
- b627e065 Regenerate uv lock for dev deps
- e7ff72f3 Add missing full-suite dev dependencies
- 1394daa4 Fix hermes_cli test package imports
- b27615d1 Cache WhatsApp bridge npm install in Docker build
- 30cea07f Add optional smart model routing
- 171b2637 Merge origin main after upstream sync
- d7f61c9d Merge upstream NousResearch main
- 645033b7 Merge GitLab main before repo sync guard mirror
- b26b9b00 Test pod repo sync safety guards
- 0abfcf6f Harden pod repo sync source policy
- 764233b9 Expand evolved repo publisher overlay
- 44d05044 Expand evolved repo publisher overlay
- d559b577 Retry deploy tool downloads
- 77debdc2 Fix repo sync submission metadata
- 725f958a Sync repo sync deletion handling
- 1c80575b Document local LLM benchmark results
- 89609bdd Fix restart recovery tool-call compatibility
- 37c428a5 Improve gateway restart recovery breadcrumbs
- 31829c6e Merge upstream main with local updates
- 3014f545 Preserve benchmark and retry hardening before upstream merge
- 75000b03 Improve putter runtime install durability
- 00f935c9 Fix evolved mirror SLM artifact publishing
- 50b30829 Add Discord channel history retrieval
- 9e061331 Track SLM capability benchmarks and harden TUI resume
- 6cc9062a Add expanded 9070 benchmark result
- 0828fb47 Cache pod dependency install layers
- 6621a230 Cache Hermes deploy dependency layers
- 27fb9d3e Add maintenance freshness tracking
- 78638bc4 Add Hermes upstream sync skill
- 6b520143 Clarify Hermes pod repository roles
- eb22a1c5 Document Hermes pod incident operations
- f6a4c60d Document external model candidates
- fef2e182 Test persistent repo drift audit
- b4d799c4 Flag persistent repo head drift
- b8b37770 Document small utility model benchmark results
- 1ac926ca Record utility model benchmark tasks
- b58b13b4 Improve live reproducibility checks
- 4eddec61 Prevent wildcard model service stops
- bfd96236 Record llama throughput comparisons
- f384076d Guard local model benchmark services
- 9df167fe Record 9070 model benchmark services
- b6a82b6b Update stack audit durability checks
- 3a120edc Carry forward benchmark helper updates
- 21b719ba Add Hermes model benchmark lineup references
- baf2b405 Add stack audit and benchmark skills
- 27a1fc86 Finish hostname fallback hardening
- 36bfa351 Carry forward reliability hardening
- 95580c82 Use opportunistic GPU jobs for Hermes
- 33119fa8 Expose pod GPU and harden sudo handling
- 2b13df5b Log server-side deploy apply change
- 78e8f5a9 Use server-side apply for Hermes deploy
- 909908b5 Log desktop bridge MCP change
- 80331f71 Add desktop bridge MCP
- e9d22af8 Log recovery carry-forward changes
- 0f76bc14 Improve runtime install promotion and turn recovery
- 3fba6f76 Log Pulse row tightening
- 3cb9f8fc Tighten Pulse event rows
- a30e6b4f Allow trusted pod runtime apt installs
- 7cbaa717 Log startup noise fixes
- b39f9fbf Add TUI interrupted turn recovery
- a3d6d6ba Log local model admission tuning
- 0b7c27c0 Tune local model admission defaults
- 8678ddde Log Pulse stream spacing fix
- b68a1de5 Preserve Pulse stream spacing
- 338df494 Log auxiliary routing documentation update
- 9f28096d Document auxiliary model routing
- 27de6736 Log reproducibility documentation update
- 27346c11 Document public reproducibility boundaries
- 81d2fe98 Log research best practices skill
- c4ab0a96 Add Hermes research best practices skill
- 618399a0 Log compaction recall tools update
- 95eb79ba Expose compaction artifact recall tools
- 8da5ce3e Log HTUI Pulse display update
- 2ae07d20 Tighten HTUI Pulse signal display
- 1512ea32 Define Hermes PR and changelog policy
- bf6b44e9 Add compaction artifacts and calibrated estimates
- 7376dc4e Keep yolo opt-in and require git commits
- fe2ee8fd Make yolo approval mode explicit
- 262aa3ca Collapse expanded skill pending turns
- c9ad37c0 Document evolved operations and recovery
- 2bd3e16d Recover interrupted TUI turns
- 8ded5a6f Persist client Pulse gateway events
- d1b94ed6 Improve Pulse panel responsive layout
- 83bbffe7 Publish Pulse overlay to evolved mirror
- c7a42199 Add TUI Pulse observer panel
- 5939a2f1 Clarify evolved mirror publication policy
- 33cda418 Fix evolved publisher sanitization loop
- 37e91c73 strip workflows from evolved mirror
- d26d8798 Expand resource review guidance
- 0a0cf9a0 Document resource review paths
- 23b165b3 Add resource review helper
- 7537f836 Add putter improvement skill
- d236fd3b Document custom deployment runtime contracts
- a1024ab0 document hermes improvement system
- df70ed1d Harden custom deployment runtime tests
- 897a924b rewrite evolved readme
- 010a88a5 add hermes introspection scan
- 214cf662 Publish evolved README from private overlay
- 326d39d5 Expose edge-watch findings to agents
- 3036bd8a Close evolved reproducibility gaps
- 4020c805 Avoid realistic fake secrets in edge-watch tests
- aab41f6f Expand public evolved mirror documentation
- 2c793719 Expand edge-watch scout into scheduled multi-source intel pipeline
- 6553e3c9 Use existing tools on evolved publisher runner
- 7836bb57 Run evolved publisher on private runner
- c7bc68af Add sanitized evolved repo publisher
- 1e359aba Wire self-improvement scout and scope deployment access
- 12a98a78 Add root-owned host sudo wrappers
- 18ee388b Add dedicated Hermes host access
- c6f41df0 Clarify proxy-backed local runtime identity
- 9f879c70 Anchor fresh sessions to live runtime
- ffedcc5d Stabilize pod coding-agent auth checks
- ee21f6cb Add agent modes and harden local upstream recovery
- 7086b504 Prefer ready pod for htui reconnect
- 3c48097f Enable warm-standby gateway rollouts
- 0eaf0e84 Drain gateway cleanly during pod replacement
- 69d90617 Escalate empty Kilo free auxiliary responses
- 2e1f8921 Use Kilo free auto for explicit remote routes
- 0818faa5 Add adaptive local-free-paid fallback routing
- 6a1c5e30 Prefer Kilo Kimi for remote auxiliary routing
- 41973a68 Surface compaction metrics in TUI
- b131f810 Expand compaction reporting surfaces
- ebe86708 Document live compaction policy check
- 7118861d Add session compaction visibility command
- 93a476e4 Disable automatic docker publish workflow
- 39b45885 Trim inherited CI workflows
- 83f81cda Slim Hindsight runtime install
- d790f948 Fix Hindsight deploy path
- 20453485 Add closed-loop level-up self review
- f9dc4abd Clean stale deployment context sources
- 9e7b989b Repair bundled TUI ink runtime
- 0a2275a2 Build ink bundle before source TUI fallback
- c3bdc8dc Stage clean TUI runtime workspace
- e0bc1aaf Fallback to source TUI when bundle build fails
- e98659ec Fix TUI startup on immutable pod image
- 0ee56b8f Tighten Hermes preflight compaction policy
- f528aa01 Track benchmark artifacts
- 370c3f7e Add local deploy pipeline and admission proxy
- 21033c5d docs: add context serving strategy notes
- 279d9950 docs: document Hermes cluster bundle changes
- 76b3b266 Add Manifest provider integration
- f7f2a32f docs: document pod sudo access
- dfbff1ca test: fix merged streaming provider fixture
- 44ea698b Merge remote-tracking branch 'origin/main'
- 0a76fb41 chore: checkpoint local Hermes deployment state
- 934c7bff Add Hermes level-up runtime surfaces
- b2d8416d docs: clarify upstream install vs packaged deployment
- acc3fc95 docs: explain fork packaging and deployment goals
- d6a096f6 docs(k8s): make Hermes deployment reproducible
- 9404e4d2 Merge upstream main into upstream-sync
- c1aa01cb Tighten Hermes runtime and memory ops
- de1ce755 chore: snapshot local changes
- 8a63c6a4 chore: snapshot local changes
- 9126721d chore(k8s): add remaining private deployment files
- 51039640 chore(k8s): add hermes gitlab credentials
- a40bf696 chore: initialize GitLab mirror

## Upstream-only Commits

- f5af6520 fix: add extra_content property to ToolCall for Gemini thought_signature (#14488)
- e91be4d7 fix: resolve_alias prefers highest version + merges static catalog
- 82a0ed1a feat: add Xiaomi MiMo v2.5-pro and v2.5 model support (#14635)
- ce089169 feat(skills-guard): gate agent-created scanner on config.skills.guard_agent_created (default off)
- e3c00841 fix(skills-guard): allow agent-created dangerous verdicts without confirmation
- 5651a733 fix(gateway): guard-match the finally-block _active_sessions delete
- 81d925f2 chore(release): map dyxushuai and etcircle in AUTHOR_MAP
- ec02d905 test(gateway): regressions for issue #11016 split-brain session locks
- b7bdf32d fix(gateway): guard session slot ownership after stop/reset
- d72985b7 fix(gateway): serialize reset command handoff and heal stale session locks
- 5a26938a fix(terminal): auto-source ~/.profile and ~/.bash_profile so n/nvm PATH survives (#14534)
- d45c738a fix(gateway): preflight user D-Bus before systemctl --user start (#14531)
- d50be05b chore(release): map j0sephz in AUTHOR_MAP
- 24e8a6e7 feat(skills_sync): surface collision with reset-hint
- 3a97fb3d fix(skills_sync): don't poison manifest on new-skill collision
- 91d6ea07 chore(dev): add ruff linter to dev deps and configure in pyproject.toml (#14527)
- fdcb3e9a chore(dev): add ty type checker to dev deps and configure in pyproject.toml (#14525)
- 627abbb1 chore(release): map davidvv in AUTHOR_MAP
- 39fcf1d1 fix(model_switch): group custom_providers by endpoint in /model picker (#9210)
- 6172f959 chore(release): map GuyCui in AUTHOR_MAP
- b24d239c Update permissions for config.yaml
- cd9cd1b1 chore(release): map MikeFac in AUTHOR_MAP
- 78e21371 fix: guard against None tirith path in security scanner
- 4f4fd211 chore(release): map vivganes in AUTHOR_MAP
- 7ca2f700 fix(docs): Add links to Atropos and wandb in user guide
- dab36d95 chore(release): map phpoh in AUTHOR_MAP
- 4c02e459 fix(status): catch OSError in os.kill(pid, 0) for Windows compatibility
- 51c1d2de fix(profiles): stage profile imports to prevent directory clobbering
- 08cb345e chore(release): map Lind3ey in AUTHOR_MAP
- 9dba75bc fix(feishu): issue where streaming edits in Feishu show extra leading newlines
- 8f50f283 chore(release): add Wysie to AUTHOR_MAP
- be99feff fix(image-gen): force-refresh plugin providers in long-lived sessions
- 911f57ad chore(release): map TaroballzChen in AUTHOR_MAP
- 5d094743 fix(tools): enforce ACP transport overrides in delegate_task child agents
- 33773ed5 chore(release): map DrStrangerUJN in AUTHOR_MAP
- a5b0c7e2 fix(config): preserve list-format models in custom_providers normalize
- c80cc855 chore(release): map RyanLee-Dev in AUTHOR_MAP
- 1df0c812 feat(skills): add MiniMax-AI/cli as default skill tap
- b5ec6e8d chore(release): map sharziki in AUTHOR_MAP
- d7452af2 fix(pairing): handle null user_name in pairing list display
- 48923e5a chore(release): map azhengbot in AUTHOR_MAP
- f77da7de Rename _api_call_with_interrupt to _interruptible_api_call
- 36adcebe Rename API call function to _interruptible_api_call
- 43de1ca8 refactor: remove _nr_to_assistant_message shim + fix flush_memories guard
- f4612785 refactor: collapse normalize_anthropic_response to return NormalizedResponse directly
- 738d0900 refactor: migrate auxiliary_client Anthropic path to use transport
- 1c532278 chore(release): map lvnilesh in AUTHOR_MAP
- 22afa066 fix(cron): guard against non-dict result from run_conversation
- 5e76c650 chore(release): map yzx9 in AUTHOR_MAP
- 15efb410 fix(nix): make working directory writable
- e8cba18f chore(release): map wenhao7 in AUTHOR_MAP
- 48dc8ef1 docs(cron): clarify default model/provider setup for scheduled jobs
- 156b3583 docs(cron): explain runtime resolution for null model/provider
- fa47cbd4 chore(release): map minorgod in AUTHOR_MAP
- 92e4bbc2 Update Docker guide with terminal command
- 85cc12e2 chore(release): map roytian1217 in AUTHOR_MAP
- 8b1ff55f fix(wecom): strip @mention prefix in group chats for slash command recognition
- 77f99c4f chore(release): map zhouxiaoya12 in AUTHOR_MAP
- 3d90292e fix: normalize provider in list_provider_models to support aliases
- d8cc85dc review(stt-xai): address cetej's nits
- 18b29b12 test(stt): add unit tests for xAI Grok STT provider
- a6ffa994 feat(stt): add xAI Grok STT provider
- bace220d fix(image-gen): persist plugin provider on reconfigure
- d1ce3586 feat(agent): add PLATFORM_HINTS for matrix, mattermost, and feishu (#14428)
- 88b6eb9a chore(release): map Nan93 in AUTHOR_MAP
- 2f48c58b fix: normalize iOS unicode dashes in slash command args
- e25c319f chore(release): map hsy5571616 in AUTHOR_MAP
- 9357db28 docs: fix fallback behavior description — it is per-turn, not per-session
- 400b5235 chore(release): map isaachuangGMICLOUD in AUTHOR_MAP
- 73533fc7 docs: add GMI Cloud to compatible providers list
- 74520392 chore(release): map WadydX in AUTHOR_MAP
- dcb8c5c6 docs(contributing): align Node requirement in repo + docs site
- 2c53a334 docs(contributing): align Node prerequisite with package engines
- 7f1c1aa4 chore(release): map mikewaters in AUTHOR_MAP
- ed5f1632 Update Git requirement to include git-lfs extension
- d6d9f106 Update Git requirement to include git-lfs extension
- fa8f0c6f chore(release): map xinpengdr in AUTHOR_MAP
- 5eefdd9c fix: skip non-API-key auth providers in env-var credential detection
- 268a4aa1 chore(release): map fatinghenji in AUTHOR_MAP
- 99af222e fix(tirith): detect Android/Termux as Linux ABI-compatible
- f347315e chore(release): map lmoncany in AUTHOR_MAP
- b80b4001 fix(mcp): respect ssl_verify config for StreamableHTTP servers
- bf039a92 chore(release): map fengtianyu88 in AUTHOR_MAP
- ec7e9208 fix(qqbot): add backoff upper-bound check for QQCloseError reconnect path
- a4877faf chore(release): map Llugaes in AUTHOR_MAP
- 85caa5d4 fix(docker): exclude runtime data/ from build context
- eda5ae5a feat(image_gen): add openai-codex plugin (gpt-image-2 via Codex OAuth) (#14317)
- 563ed0e6 chore(release): map fuleinist in AUTHOR_MAP
- e371af1d Add config option to disable Discord slash commands
- ee54e20c chore(release): map zhang9w0v5 in AUTHOR_MAP
- 82fbd477 Update .gitignore
- 30ad507a chore(release): map christopherwoodall in AUTHOR_MAP
- dce2b0df Add exclude-newer option for UV tool in pyproject.toml
- f9487ee8 chore(release): map 10ishq in AUTHOR_MAP
- e038677e docs: add Exa web search backend setup guide and details
- effcbc8a chore(release): map huangke19 in AUTHOR_MAP
- 6209e85e feat: support document/archive extensions in MEDIA: tag extraction
- a2a8092e feat(cli): add --ignore-user-config and --ignore-rules flags
- 520b8d90 chore(release): map A-afflatus in AUTHOR_MAP
- 9c5c8268 fix(skills): remove invalid llm-wiki related skill
- 463fbf14 chore(release): map iborazzi in AUTHOR_MAP
- f41031af fix: increase max_tokens for GLM 5.1 reasoning headroom
- c78a188d refactor: invalidate transport cache when api_mode auto-upgrades to codex_responses
- d30ee2e5 refactor: unify transport dispatch + collapse normalize shims
- 36730b90 fix(gateway): also clear session-scoped approval state on /new
- 050aabe2 fix(gateway): reset approval and yolo state on session boundary
- 64c38cc4 chore(release): map shushuzn in AUTHOR_MAP
- fa2dbd1b fix: use utf-8 encoding when reading .env file in load_env()
- 6ad2fab8 chore(release): map Dev-Mriganka in AUTHOR_MAP
- a14fb3ab fix(cli): guard fallback_model list format in save_config_value
- 2c26a808 chore(release): map projectadmin-dev in AUTHOR_MAP
- d67d12b5 Update whatsapp-bridge package-lock.json
- 86510477 chore(release): map NIDNASSER-Abdelmajid in AUTHOR_MAP
- ce4214ec Normalize claw workspace paths for Windows
- 50387d71 chore(release): map haimu0x in AUTHOR_MAP
- aa75d0a9 fix(web): remove duplicate skill count in dashboard badge (#12372)
- 15906183 chore(release): map @akhater's Azure VM commit email in AUTHOR_MAP
- d70f0f1d fix(docker): allow entrypoint to pass-through non-hermes commands
- a3014a44 fix(docker): add SETUID/SETGID caps so gosu drop in entrypoint succeeds
- c345ec9a fix(display): strip standalone tool-call XML tags from visible text

## Files Changed On Both Sides

- .gitignore
- Dockerfile
- README.md
- agent/auxiliary_client.py
- agent/context_compressor.py
- agent/model_metadata.py
- agent/prompt_builder.py
- agent/skill_utils.py
- cli-config.yaml.example
- cli.py
- cron/scheduler.py
- gateway/platforms/base.py
- gateway/platforms/discord.py
- gateway/platforms/email.py
- gateway/run.py
- gateway/session.py
- gateway/status.py
- hermes_cli/auth.py
- hermes_cli/commands.py
- hermes_cli/config.py
- hermes_cli/gateway.py
- hermes_cli/main.py
- hermes_cli/model_switch.py
- hermes_cli/models.py
- hermes_cli/setup.py
- model_tools.py
- package-lock.json
- package.json
- pyproject.toml
- run_agent.py
- tests/agent/test_context_compressor.py
- tests/agent/test_prompt_builder.py
- tests/gateway/test_session_boundary_security_state.py
- tests/gateway/test_session_split_brain_11016.py
- tests/gateway/test_status.py
- tests/gateway/test_unknown_command.py
- tests/hermes_cli/test_gateway_service.py
- tests/hermes_cli/test_model_switch_custom_providers.py
- tests/run_agent/test_run_agent.py
- tests/run_agent/test_streaming.py
- tests/test_tui_gateway_server.py
- tests/tools/test_local_shell_init.py
- tests/tools/test_skills_sync.py
- tools/delegate_tool.py
- tools/environments/local.py
- tools/skills_sync.py
- tools/terminal_tool.py
- tools/web_tools.py
- tui_gateway/server.py
- ui-tui/src/app/interfaces.ts
- ui-tui/src/app/uiStore.ts
- ui-tui/src/app/useInputHandlers.ts
- ui-tui/src/app/useMainApp.ts
- ui-tui/src/components/appChrome.tsx
- ui-tui/src/components/appLayout.tsx
- ui-tui/src/gatewayTypes.ts
- uv.lock
- website/docs/user-guide/docker.md

## Design-Sensitive Overlap

- agent/prompt_builder.py
- cli.py
- gateway/run.py
- gateway/status.py
- hermes_cli/commands.py
- hermes_cli/config.py
- hermes_cli/gateway.py
- model_tools.py
- run_agent.py
- tools/skills_sync.py

## Keep-Local-Method Overlap

- agent/prompt_builder.py
- gateway/run.py
- gateway/status.py
- hermes_cli/gateway.py
- tools/skills_sync.py

## Upstream File Impact

.dockerignore                                      |    3 +
 .gitignore                                         |    1 +
 CONTRIBUTING.md                                    |    6 +-
 Dockerfile                                         |    3 +-
 README.md                                          |    1 -
 agent/anthropic_adapter.py                         |  170 +-
 agent/auxiliary_client.py                          |   19 +-
 agent/context_compressor.py                        |   61 +-
 agent/error_classifier.py                          |   71 +-
 agent/model_metadata.py                            |   43 +-
 agent/models_dev.py                                |    3 +
 agent/prompt_builder.py                            |   26 +
 agent/skill_utils.py                               |    2 +-
 agent/title_generator.py                           |    2 +-
 agent/transports/anthropic.py                      |   60 +-
 agent/transports/types.py                          |   56 +
 agent/usage_pricing.py                             |   12 +
 cli-config.yaml.example                            |    1 +
 cli.py                                             |   53 +-
 cron/scheduler.py                                  |    6 +
 docker/entrypoint.sh                               |   22 +
 gateway/hooks.py                                   |   55 +-
 gateway/platforms/base.py                          |  291 +-
 gateway/platforms/discord.py                       |  103 +-
 gateway/platforms/email.py                         |    1 +
 gateway/platforms/feishu.py                        |  429 ++-
 gateway/platforms/qqbot/adapter.py                 |    3 +
 gateway/platforms/wecom.py                         |    5 +
 gateway/run.py                                     |  181 +-
 gateway/session.py                                 |    2 +-
 gateway/status.py                                  |  201 +-
 hermes_cli/auth.py                                 |    1 +
 hermes_cli/claw.py                                 |    2 +-
 hermes_cli/commands.py                             |   65 +
 hermes_cli/config.py                               |   50 +-
 hermes_cli/debug.py                                |  176 +-
 hermes_cli/gateway.py                              |  409 ++-
 hermes_cli/main.py                                 |   59 +-
 hermes_cli/model_switch.py                         |  287 +-
 hermes_cli/models.py                               |   92 +-
 hermes_cli/pairing.py                              |    6 +-
 hermes_cli/plugins.py                              |   47 +-
 hermes_cli/profiles.py                             |   56 +-
 hermes_cli/setup.py                                |   15 +-
 hermes_cli/skin_engine.py                          |   78 +-
 hermes_cli/tools_config.py                         |   83 +-
 model_tools.py                                     |   10 +-
 nix/nixosModules.nix                               |    7 +-
 package-lock.json                                  | 3515 +-------------------
 package.json                                       |    4 +-
 plugins/image_gen/openai-codex/__init__.py         |  378 +++
 plugins/image_gen/openai-codex/plugin.yaml         |    5 +
 pyproject.toml                                     |   27 +-
 run_agent.py                                       |  452 ++-
 scripts/discord-voice-doctor.py                    |    2 +-
 scripts/release.py                                 |   68 +
 scripts/whatsapp-bridge/package-lock.json          |    2 +-
 skills/research/llm-wiki/SKILL.md                  |    2 +-
 tests/agent/test_anthropic_adapter.py              |  150 +-
 tests/agent/test_anthropic_normalize_v2.py         |  238 --
 tests/agent/test_auxiliary_main_first.py           |    8 +-
 tests/agent/test_context_compressor.py             |   64 +
 tests/agent/test_error_classifier.py               |   91 +
 tests/agent/test_local_stream_timeout.py           |   22 +
 tests/agent/test_prompt_builder.py                 |   18 +
 tests/agent/test_usage_pricing.py                  |   67 +
 tests/agent/transports/test_transport.py           |    8 +
 tests/agent/transports/test_types.py               |  121 +
 tests/gateway/test_debug_command.py                |   60 +
 tests/gateway/test_discord_slash_commands.py       |   83 +
 tests/gateway/test_feishu.py                       | 1104 +++++-
 tests/gateway/test_hooks.py                        |   96 +
 .../test_session_boundary_security_state.py        |  201 ++
 tests/gateway/test_session_split_brain_11016.py    |  399 +++
 tests/gateway/test_status.py                       |  119 +-
 tests/gateway/test_unknown_command.py              |  209 +-
 tests/hermes_cli/test_commands.py                  |  116 +
 tests/hermes_cli/test_debug.py                     |  202 +-
 tests/hermes_cli/test_gateway.py                   |   27 +
 tests/hermes_cli/test_gateway_service.py           |  287 +-
 tests/hermes_cli/test_ignore_user_config_flags.py  |  245 ++
 tests/hermes_cli/test_image_gen_picker.py          |   77 +
 .../test_model_switch_custom_providers.py          |  145 +
 .../hermes_cli/test_models_dev_preferred_merge.py  |  124 +
 tests/hermes_cli/test_opencode_go_in_model_list.py |   37 +-
 tests/hermes_cli/test_plugins.py                   |   27 +
 tests/hermes_cli/test_profiles.py                  |   41 +
 .../hermes_cli/test_provider_config_validation.py  |   45 +
 tests/hermes_cli/test_skin_engine.py               |   17 +-
 tests/hermes_cli/test_xiaomi_provider.py           |    4 +-
 .../image_gen/test_openai_codex_provider.py        |  299 ++
 .../test_anthropic_truncation_continuation.py      |   30 +-
 tests/run_agent/test_provider_fallback.py          |   26 +
 tests/run_agent/test_run_agent.py                  |   85 +
 .../test_run_agent_multimodal_prologue.py          |    3 +-
 tests/run_agent/test_streaming.py                  |  222 ++
 tests/run_agent/test_strip_reasoning_tags_cli.py   |   69 +
 tests/test_cli_skin_integration.py                 |    3 +
 tests/test_model_tools_async_bridge.py             |   62 +
 tests/test_tui_gateway_server.py                   |  538 ++-
 tests/tools/test_delegate.py                       |   53 +
 tests/tools/test_docker_environment.py             |   28 +
 .../tools/test_image_generation_plugin_dispatch.py |   99 +
 tests/tools/test_local_shell_init.py               |  110 +-
 tests/tools/test_parse_env_var.py                  |   21 +
 tests/tools/test_skill_manager_tool.py             |   82 +
 tests/tools/test_skills_guard.py                   |    6 +-
 tests/tools/test_skills_sync.py                    |   80 +
 tests/tools/test_transcription_tools.py            |  259 ++
 tests/tools/test_url_safety.py                     |  193 +-
 tests/tui_gateway/test_make_agent_provider.py      |   48 +
 tools/browser_cdp_tool.py                          |    2 +-
 tools/browser_tool.py                              |    9 +
 tools/code_execution_tool.py                       |    1 +
 tools/delegate_tool.py                             |   52 +-
 tools/environments/base.py                         |    2 +-
 tools/environments/docker.py                       |    6 +
 tools/environments/local.py                        |   21 +-
 tools/image_generation_tool.py                     |   10 +
 tools/mcp_tool.py                                  |    3 +
 tools/skill_manager_tool.py                        |   30 +-
 tools/skills_guard.py                              |    4 +
 tools/skills_hub.py                                |    1 +
 tools/skills_sync.py                               |   20 +-
 tools/skills_tool.py                               |    2 +-
 tools/terminal_tool.py                             |   43 +-
 tools/tirith_security.py                           |    9 +-
 tools/transcription_tools.py                       |  126 +-
 tools/url_safety.py                                |  113 +-
 tools/web_tools.py                                 |    2 +-
 tui_gateway/server.py                              |  104 +-
 .../src/ink/components/AlternateScreen.tsx         |    5 +-
 .../hermes-ink/src/ink/components/Text.tsx         |    6 +
 .../hermes-ink/src/ink/render-node-to-output.ts    |    2 +-
 ui-tui/packages/hermes-ink/src/ink/styles.ts       |    1 +
 ui-tui/packages/hermes-ink/src/ink/wrap-text.ts    |    4 +
 ui-tui/src/__tests__/platform.test.ts              |   19 +
 ui-tui/src/__tests__/subagentTree.test.ts          |    5 +-
 ui-tui/src/__tests__/textInputWrap.test.ts         |   60 +
 ui-tui/src/__tests__/useConfigSync.test.ts         |   54 +-
 ui-tui/src/app/interfaces.ts                       |    4 +-
 ui-tui/src/app/slash/commands/core.ts              |   25 +-
 ui-tui/src/app/uiStore.ts                          |    2 +-
 ui-tui/src/app/useConfigSync.ts                    |   13 +-
 ui-tui/src/app/useInputHandlers.ts                 |   24 +
 ui-tui/src/app/useMainApp.ts                       |   16 +-
 ui-tui/src/bootBanner.ts                           |   26 -
 ui-tui/src/components/appChrome.tsx                |    8 +-
 ui-tui/src/components/appLayout.tsx                |   95 +-
 ui-tui/src/components/textInput.tsx                |   24 +-
 ui-tui/src/content/hotkeys.ts                      |    4 +-
 ui-tui/src/entry.tsx                               |    3 -
 ui-tui/src/gatewayTypes.ts                         |    2 +-
 ui-tui/src/lib/platform.ts                         |   13 +-
 uv.lock                                            |   71 +-
 web/src/pages/SkillsPage.tsx                       |    1 -
 website/docs/developer-guide/adding-providers.md   |    2 +-
 website/docs/developer-guide/agent-loop.md         |    4 +-
 website/docs/developer-guide/contributing.md       |    4 +-
 website/docs/guides/daily-briefing-bot.md          |    2 +
 website/docs/integrations/providers.md             |    1 +
 website/docs/reference/cli-commands.md             |    5 +
 website/docs/user-guide/configuration.md           |    2 +
 website/docs/user-guide/docker.md                  |    6 +
 website/docs/user-guide/features/cron.md           |    2 +
 .../docs/user-guide/features/fallback-providers.md |    6 +-
 website/docs/user-guide/features/rl-training.md    |    6 +-
 167 files changed, 10824 insertions(+), 4821 deletions(-)

## Recommended Next Step

- Create or refresh an upstream-sync branch from the private fork main.
- Resolve design-sensitive overlap first.
- For each overlap, classify it as upstream-first, local-first, or hybrid using the fresh-upstream test.
- Keep the local method in keep-local files only when we would still choose it today on fresh upstream.
- Adapt upstream bug fixes around the local method instead of replacing it wholesale.
- Delete obsolete local divergence when upstream now covers the same goal cleanly.
- Run focused tests on touched gateway/status/skills_sync paths before widening the merge.
