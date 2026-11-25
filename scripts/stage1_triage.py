#!/usr/bin/env python3
"""STAGE 1 — triage: bridge-surface, code size, EIP-1967, owner, verified."""

from __future__ import annotations

import json
import sys
import urllib.parse
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from lib.bridge_surface import validate_bridge_surface  # noqa: E402
from lib.rpc import (  # noqa: E402
    EIP1967_ADMIN_SLOT,
    EIP1967_IMPL_SLOT,
    eth_calls_batch,
    http_get_json,
    load_config,
    rpc_batch,
    selector,
    storage_to_address,
)
from lib.state import find_by_addr, print_queue_table, set_cursor, update_stage  # noqa: E402

DATA = REPO / "data"

OWNER_SIGS = [
    "owner()",
    "getOwner()",
    "admin()",
    "getAdmin()",
    "governance()",
]


def _check_verified(chain: str, addr: str) -> bool | None:
    cfg = load_config()
    chain_cfg = cfg["chains"].get(chain)
    if not chain_cfg or not chain_cfg.get("explorer_api"):
        return None
    base = chain_cfg["explorer_api"]
    qs = urllib.parse.urlencode(
        {
            "module": "contract",
            "action": "getsourcecode",
            "address": addr,
        }
    )
    try:
        data = http_get_json(f"{base}?{qs}", cfg)
    except Exception:
        return None
    results = data.get("result") if isinstance(data, dict) else None
    if not results:
        return None
    first = results[0] if isinstance(results, list) else results
    if not isinstance(first, dict):
        return None
    src = first.get("SourceCode") or ""
    return bool(src and src not in ("", "0"))


def _write_report(addr: str, report: dict) -> Path:
    out_dir = DATA / addr
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "stage1.json"
    out_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return out_path


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: stage1_triage.py <addr>", file=sys.stderr)
        return 2
    addr = sys.argv[1].lower()
    if not addr.startswith("0x") or len(addr) != 42:
        print("ERROR: invalid address", file=sys.stderr)
        return 2

    row = find_by_addr(addr)
    if row is None:
        print(f"ERROR: {addr} not in QUEUE", file=sys.stderr)
        return 1
    chain = row.chain
    rpc_used = 0

    # 1) bridge-surface gate (includes eth_getCode + ≤2 batches)
    surface = validate_bridge_surface(addr, chain)
    rpc_used += int(surface.get("rpc_batches") or 0)
    code_size = int(surface.get("code_size") or 0)

    if code_size == 0:
        report = {
            "addr": addr,
            "chain": chain,
            "name": row.name,
            "code_size": 0,
            "bridge_surface": False,
            "surface": surface,
            "stage": "SAFE",
            "reason": "no_code_eoa_or_empty",
            "rpc_used": rpc_used,
        }
        out_path = _write_report(addr, report)
        updated = update_stage(addr, "SAFE")
        if updated:
            set_cursor(updated.num)
        print(f"stage1: {addr} → SAFE (rpc={rpc_used})")
        print(f"json: {out_path}")
        print_queue_table()
        return 0

    if not surface.get("bridge_surface"):
        report = {
            "addr": addr,
            "chain": chain,
            "name": row.name,
            "code_size": code_size,
            "bridge_surface": False,
            "surface": surface,
            "stage": "SAFE",
            "reason": "wrong_contract_no_bridge_surface",
            "rpc_used": rpc_used,
        }
        out_path = _write_report(addr, report)
        updated = update_stage(addr, "SAFE")
        if updated:
            set_cursor(updated.num)
        print(f"stage1: {addr} → SAFE (rpc={rpc_used})")
        print(f"json: {out_path}")
        print_queue_table()
        return 0

    # 2) EIP-1967 slots (batch)
    slots = rpc_batch(
        chain,
        [
            {"method": "eth_getStorageAt", "params": [addr, EIP1967_IMPL_SLOT, "latest"]},
            {"method": "eth_getStorageAt", "params": [addr, EIP1967_ADMIN_SLOT, "latest"]},
        ],
    )
    rpc_used += 1
    eip1967_impl = storage_to_address(slots[0] if isinstance(slots[0], str) else "0x0")
    eip1967_admin = storage_to_address(slots[1] if isinstance(slots[1], str) else "0x0")

    # 5) owner probes — one batch
    calls = [{"to": addr, "data": selector(sig)} for sig in OWNER_SIGS]
    owner_results = eth_calls_batch(chain, calls)
    rpc_used += 1

    owner = None
    owner_sig = None
    for sig, res in zip(OWNER_SIGS, owner_results):
        if res.get("ok") and isinstance(res.get("result"), str):
            parsed = storage_to_address(res["result"])
            if parsed:
                owner = parsed
                owner_sig = sig
                break

    verified = _check_verified(chain, addr)

    if rpc_used > 10:
        print(f"ERROR: RPC budget exceeded ({rpc_used})", file=sys.stderr)
        return 1

    stage = "CHECKLIST"
    reason = "bridge_surface_needs_invariant_checks"

    report = {
        "addr": addr,
        "chain": chain,
        "name": row.name,
        "code_size": code_size,
        "bridge_surface": True,
        "surface": surface,
        "eip1967_impl": eip1967_impl,
        "eip1967_admin": eip1967_admin,
        "owner": owner,
        "owner_sig": owner_sig,
        "verified": verified,
        "rpc_used": rpc_used,
        "stage": stage,
        "reason": reason,
    }

    out_path = _write_report(addr, report)
    updated = update_stage(addr, stage)
    if updated:
        set_cursor(updated.num)
    else:
        set_cursor("none")

    print(f"stage1: {addr} → {stage} (rpc={rpc_used})")
    print(f"json: {out_path}")
    print_queue_table()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
