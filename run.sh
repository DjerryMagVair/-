#!/usr/bin/env bash
# Bridge audit pipeline runner
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

cmd="${1:-}"
arg="${2:-}"

case "$cmd" in
  collect)
    python3 scripts/collect_candidates.py
    ;;
  stage1)
    [[ -n "$arg" ]] || { echo "usage: $0 stage1 <addr>" >&2; exit 2; }
    python3 scripts/stage1_triage.py "$arg"
    ;;
  stage2)
    [[ -n "$arg" ]] || { echo "usage: $0 stage2 <addr>" >&2; exit 2; }
    python3 scripts/stage2_checklist.py "$arg"
    ;;
  stage3)
    cd scripts/stage3_fork
    if [[ -n "$arg" ]]; then
      export BRIDGE_ADDR="$arg"
      # Prefer ethereum fork; chain can be overridden via FOUNDRY_ETH_RPC_URL
      RPC_URL="${FOUNDRY_ETH_RPC_URL:-https://ethereum.publicnode.com}"
      forge test --fork-url "$RPC_URL" -vv
    else
      forge test -vv
    fi
    ;;
  *)
    echo "usage: $0 {collect|stage1 <addr>|stage2 <addr>|stage3 [addr]}" >&2
    exit 2
    ;;
esac
