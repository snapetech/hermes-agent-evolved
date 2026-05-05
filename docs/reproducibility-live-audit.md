# Hermes Live Reproducibility Audit

## Summary

- **warn** `image`: Live image/app commit does not match local repo HEAD.
- **warn** `persistent_repo`: Persistent repo HEAD does not match local repo HEAD.

## Local Repo

- Root: `/home/<user>/Documents/code/hermes-agent`
- Branch: `main`
- HEAD: `b4d799c4e470bfbd3a20b4be9e7b4f870ad962b1`
- Config hash: `d89a41894dbfa8a31a5d836200271a2fd36b3793855368790c7366d1b3535ff5`
- Repo skill count: `133`

## Live Pod

- Images: `{'bootstrap': 'hermes-agent-sudo:git-1ac926ca8703aaf02425d74debc9a6ffeea2bcbb', 'gateway': 'hermes-agent-sudo:git-1ac926ca8703aaf02425d74debc9a6ffeea2bcbb', 'llama-admission-proxy': 'hermes-agent-sudo:git-1ac926ca8703aaf02425d74debc9a6ffeea2bcbb'}`
- App commit: ``
- Persistent repo HEAD: `b58b13b49320a371fc9274458d5e9a30fa43d292`
- Persistent repo upstream: `fork/main`
- Persistent repo ahead/behind: `0	0`
- Persistent repo dirty: `False`
- ConfigMap config hash: `d89a41894dbfa8a31a5d836200271a2fd36b3793855368790c7366d1b3535ff5`
- /opt/data config hash: `d89a41894dbfa8a31a5d836200271a2fd36b3793855368790c7366d1b3535ff5`
- Cron jobs: `12`
- Skills: `132`
