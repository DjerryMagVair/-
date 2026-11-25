#!/usr/bin/env python3
"""STAGE 1 — triage: bridge-surface, SpokePool markers, EIP-1967, owner, verified."""

from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from lib.bridge_surface import SPOKEPOOL_MARKERS, validate_bridge_surface  # noqa: E402
from lib.explorer import is_contract_verified  # noqa: E402
from lib.rpc import (  # noqa: E402
    EIP1967_ADMIN_SLOT,
    EIP1967_IMPL_SLOT,
    eth_calls_batch,
    rpc_batch,
    selector,
    storage_to_address,
)
from lib.state import (  # noqa: E402
    append_excluded,
    find_by_addr,
    parse_queue,
    print_queue_table,
    set_cursor,
    update_stage,
)

DATA = REPO / "data"

OWNER_SIGS = [
    "owner()",
    "getOwner()",
    "admin()",
    "getAdmin()",
    "governance()",
    "deployer()",
]


def _write_report(addr: str, report: dict) -> Path:
    out_dir = DATA / addr
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "stage1.json"
    out_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return out_path


def _advance_cursor_next_new(exclude_addr: str) -> None:
    """Point CURSOR at next NEW/CHECKLIST row after excluding current."""
    exclude_addr = exclude_addr.lower()
    for row in parse_queue():
        if row.addr == exclude_addr:
            continue
        if row.stage.upper() in {"NEW", "CHECKLIST"}:
            set_cursor(row.num)
            return
    set_cursor("none")


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
    name_l = (row.name or "").lower()
    expect_spokepool = "spokepool" in name_l or "across" in name_l

    # 1) bridge-surface gate (includes eth_getCode + ≤2 batches)
    surface = validate_bridge_surface(addr, chain)
    rpc_used += int(surface.get("rpc_batches") or 0)
    code_size = int(surface.get("code_size") or 0)
    sp_hits = list(surface.get("spokepool_hits") or [])

    if code_size == 0:
        report = {
            "addr": addr,
            "chain": chain,
            "name": row.name,
            "code_size": 0,
            "bridge_surface": False,
            "spokepool_hits": [],
            "spokepool_hit_count": 0,
            "surface": surface,
            "stage": "EXCLUDED",
            "reason": "no_code_eoa_or_empty",
            "rpc_used": rpc_used,
        }
        out_path = _write_report(addr, report)
        update_stage(addr, "EXCLUDED")
        append_excluded(row.name, chain, addr=addr, note="no code")
        _advance_cursor_next_new(addr)
        print(f"stage1: {addr} → EXCLUDED (rpc={rpc_used})")
        print(f"json: {out_path}")
        print_queue_table()
        return 0

    # SpokePool-named targets: require ≥2 SpokePool markers
    if expect_spokepool and len(sp_hits) < 2:
        report = {
            "addr": addr,
            "chain": chain,
            "name": row.name,
            "code_size": code_size,
            "bridge_surface": bool(surface.get("bridge_surface")),
            "spokepool_hits": sp_hits,
            "spokepool_hit_count": len(sp_hits),
            "spokepool_markers_checked": sorted(SPOKEPOOL_MARKERS),
            "surface": surface,
            "stage": "EXCLUDED",
            "reason": "wrong_contract_spokepool_markers_lt_2",
            "rpc_used": rpc_used,
        }
        out_path = _write_report(addr, report)
        update_stage(addr, "EXCLUDED")
        append_excluded(
            row.name,
            chain,
            addr=addr,
            note="wrong contract (SpokePool markers < 2)",
        )
        _advance_cursor_next_new(addr)
        print(f"stage1: {addr} → EXCLUDED (spokepool_hits={len(sp_hits)}, rpc={rpc_used})")
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
            "spokepool_hits": sp_hits,
            "spokepool_hit_count": len(sp_hits),
            "surface": surface,
            "stage": "EXCLUDED",
            "reason": "wrong_contract_no_bridge_surface",
            "rpc_used": rpc_used,
        }
        out_path = _write_report(addr, report)
        update_stage(addr, "EXCLUDED")
        append_excluded(
            row.name,
            chain,
            addr=addr,
            note="wrong contract (no-bridge-surface)",
        )
        _advance_cursor_next_new(addr)
        print(f"stage1: {addr} → EXCLUDED (rpc={rpc_used})")
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

    # 3) owner probes — one batch
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

    # 4) explorer verified (HTTP, not RPC)
    explorer = is_contract_verified(chain, addr)
    verified = explorer.get("verified")

    if rpc_used > 10:
        print(f"ERROR: RPC budget exceeded ({rpc_used})", file=sys.stderr)
        return 1

    stage = "CHECKLIST"
    reason = "bridge_surface_needs_invariant_checks"
    if expect_spokepool:
        reason = "spokepool_surface_needs_invariant_checks"

    report = {
        "addr": addr,
        "chain": chain,
        "name": row.name,
        "code_size": code_size,
        "bridge_surface": True,
        "spokepool_hits": sp_hits,
        "spokepool_hit_count": len(sp_hits),
        "surface": surface,
        "eip1967_impl": eip1967_impl,
        "eip1967_admin": eip1967_admin,
        "owner": owner,
        "owner_sig": owner_sig,
        "verified": verified,
        "explorer": explorer,
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

    print(f"stage1: {addr} → {stage} (spokepool_hits={len(sp_hits)}, rpc={rpc_used})")
    print(f"json: {out_path}")
    print_queue_table()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
