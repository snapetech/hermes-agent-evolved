# mission-loop

Durable Ralph-style mission loops for Hermes.

This plugin gives Hermes an outer persistence loop without changing the core
agent loop:

- mission state lives under `$HERMES_HOME/missions/<mission_id>/`
- every execution iteration starts a fresh `AIAgent`
- the next iteration reloads mission state from files instead of chat history
- verifier commands decide completion by exit code
- runs are explicit, bounded, and protected by a per-mission lock

The plugin is opt-in. Add it to `plugins.enabled`:

```yaml
plugins:
  enabled:
    - mission-loop
```

## Slash Commands

```text
/mission create --title "Name" --verifier "scripts/run_tests.sh tests/foo.py" -- <spec>
/mission list
/mission status <mission_id>
/mission record <mission_id> <note>
/mission verify <mission_id>
/mission prompt <mission_id>
/mission run <mission_id> [iterations] [--wait]
```

`/mission run` queues a background daemon thread by default so gateway command
dispatch is not blocked. Add `--wait` when using an interactive CLI and you want
the command to return only after the bounded run finishes.

## Agent Tool

When the plugin is enabled, it registers the `mission_loop` tool with actions:

- `create`
- `list`
- `status`
- `record`
- `verify`
- `render_prompt`
- `run`

Tool `run` is synchronous and intended for explicit agent-controlled use. Slash
command `run` is backgrounded by default for gateway safety.

## Files

Each mission directory contains:

- `SPEC.md` - durable mission spec and acceptance criteria
- `state.json` - status, verifier, workspace, iteration counters
- `progress.jsonl` - append-only attempt/verifier/progress ledger
- `artifacts/iteration-NNNN.prompt.md` - prompt given to the fresh agent
- `artifacts/iteration-NNNN.response.md` - agent response from that iteration

## Fit

Use this for verifier-gated tasks that benefit from context refresh. Use cron
for time-based scheduling and monitors. Cron can trigger or inspect missions,
but mission-loop owns the iterative state and verifier gate.
