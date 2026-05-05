#!/usr/bin/env bash
# check_changelog.sh — report commits in a range that lack HERMES_CHANGELOG entries.
#
# Usage:
#   scripts/check_changelog.sh <range>
#   scripts/check_changelog.sh --summary <range>
#   scripts/check_changelog.sh --strict <range>
#
# Examples:
#   scripts/check_changelog.sh upstream/main..HEAD
#   scripts/check_changelog.sh origin/main..HEAD
#
# Exit codes:
#   0 — all fork-authored commits have ledger entries (or range is empty).
#   1 — some commits lack entries (warn-level; hooks treat this as soft).
#   2 — invalid usage.
#
# --strict upgrades exit 1 into exit 2 for CI hard-fail.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LEDGER="$REPO_ROOT/HERMES_CHANGELOG.md"

SUMMARY=0
STRICT=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --summary)
      SUMMARY=1; shift ;;
    --strict)
      STRICT=1; shift ;;
    -h|--help)
      sed -n '2,16p' "$0"; exit 0 ;;
    --)
      shift; break ;;
    -*)
      echo "unknown flag: $1" >&2; exit 2 ;;
    *)
      break ;;
  esac
done

if [[ $# -lt 1 ]]; then
  echo "usage: $0 [--summary] [--strict] <git-range>" >&2
  exit 2
fi

RANGE="$1"

if [[ ! -f "$LEDGER" ]]; then
  echo "HERMES_CHANGELOG.md not found at $LEDGER" >&2
  exit 2
fi

# Commits in the range. Excludes merge commits (first-parent-only) because
# upstream merges do not need their own ledger entries.
mapfile -t COMMITS < <(git -C "$REPO_ROOT" log --no-merges --format='%H' "$RANGE" 2>/dev/null || true)

if [[ ${#COMMITS[@]} -eq 0 ]]; then
  [[ $SUMMARY -eq 1 ]] && echo "range $RANGE: no non-merge commits"
  exit 0
fi

# Pull the first 12 chars of each SHA and look for them (or the 8-char short
# form) in the ledger. Also accept a loose keyword match against the commit
# subject as a weaker signal.
missing=()
weak=()
present=()

for sha in "${COMMITS[@]}"; do
  short12="${sha:0:12}"
  short8="${sha:0:8}"
  subject="$(git -C "$REPO_ROOT" log -1 --format='%s' "$sha")"

  # Skip commits that came from upstream (authored by non-fork authors that
  # appear only on upstream). Heuristic: if the commit is reachable from
  # upstream/main, skip it.
  if git -C "$REPO_ROOT" merge-base --is-ancestor "$sha" upstream/main 2>/dev/null; then
    continue
  fi

  # Ledger-only carve-out: if the commit only touches HERMES_CHANGELOG.md
  # (a back-fill or reconciliation commit), it is self-documenting.
  # See docs/changelog-discipline.md.
  touched="$(git -C "$REPO_ROOT" diff-tree --no-commit-id --name-only -r "$sha" | sed '/^$/d')"
  if [[ "$touched" == "HERMES_CHANGELOG.md" ]]; then
    continue
  fi

  if grep -qE "(\[$short8\]|\[$short12\]|/commit/$short8|/commit/$short12)" "$LEDGER"; then
    present+=("$sha|$subject")
    continue
  fi

  # Weak match: first 4 salient words of the subject appear together in the ledger.
  key="$(echo "$subject" | tr -s '[:space:]' ' ' | cut -c1-40 | sed -E 's/[^A-Za-z0-9 ]/./g')"
  if [[ -n "$key" ]] && grep -qF "$key" "$LEDGER"; then
    weak+=("$sha|$subject")
    continue
  fi

  missing+=("$sha|$subject")
done

if [[ $SUMMARY -eq 1 ]]; then
  printf "range %s: %d ok, %d weak-match, %d missing\n" \
    "$RANGE" "${#present[@]}" "${#weak[@]}" "${#missing[@]}"
else
  if [[ ${#missing[@]} -gt 0 ]]; then
    printf '\nCommits without HERMES_CHANGELOG entries (range: %s):\n' "$RANGE"
    for row in "${missing[@]}"; do
      sha="${row%%|*}"; subj="${row#*|}"
      printf '  %s  %s\n' "${sha:0:8}" "$subj"
    done
    printf '\nAdd entries to HERMES_CHANGELOG.md in SHA-link format:\n'
    printf '  - [<short-sha>](https://github.com/example-org/hermes-agent-private/commit/<short-sha>) - Description\n'
    printf 'See docs/changelog-discipline.md for rules.\n\n'
  fi
  if [[ ${#weak[@]} -gt 0 ]]; then
    printf 'Commits with weak ledger match (verify — may need SHA link):\n'
    for row in "${weak[@]}"; do
      sha="${row%%|*}"; subj="${row#*|}"
      printf '  %s  %s\n' "${sha:0:8}" "$subj"
    done
    printf '\n'
  fi
fi

if [[ ${#missing[@]} -gt 0 ]]; then
  [[ $STRICT -eq 1 ]] && exit 2
  exit 1
fi
exit 0
