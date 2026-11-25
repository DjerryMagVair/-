#!/usr/bin/env python3
"""STAGE 2 — invariant checklist (Unbacked Mint / access / spoofing surface)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from lib.rpc import ZERO_ADDR, eth_calls_batch, selector, storage_to_address  # noqa: E402
from lib.state import find_by_addr, print_queue_table, set_cursor, update_stage  # noqa: E402

DATA = REPO / "data"

VIEW_SIGS = [
    "totalMinted()",
    "totalLocked()",
    "totalBridged()",
    "lockedBalance()",
    "totalSupply()",
]

MINT_SIGS = [
    "mint(address,uint256)",
    "mint(address,uint256,bytes)",
    "mint(uint256)",
]

ANCHOR_SIGS = [
    "updateAnchor(bytes32)",
    "updateAnchor(uint256,bytes32)",
    "setLocked(uint256)",
    "setLocked(address,uint256)",
]

STARGATE_VIEW_SIGS = [
    "stargateType()",
    "token()",
    "endpoint()",
    "sharedDecimals()",
    "oftVersion()",
    "poolToken()",
    "stargate()",
    "approvalRequired()",
]

# Across SpokePool views / owner mutators (selectors via keccak)
SPOKE_VIEWS = [
    "hubPool()",
    "chainId()",
    "numberOfDeposits()",
    "getCurrentTime()",
    "paused()",
    "owner()",
    "relayer()",
    "oracle()",
    "nativeToken()",
    "poolToken()",
]

SPOKE_OWNER_MUTATORS = [
    ("setCrossDomainAdmin(address)", "address"),
    ("setHubPool(address)", "address"),
    ("pause()", "none"),
    ("unpause()", "none"),
    ("setPaused(bool)", "bool"),
    ("relayRootBundle(bytes32[],uint32)", "bundle"),
]


def _u256(hexdata: str | None) -> int | None:
    if not hexdata or not isinstance(hexdata, str):
        return None
    h = hexdata[2:] if hexdata.startswith("0x") else hexdata
    if not h or set(h) <= {"0"}:
        return 0
    try:
        return int(h, 16)
    except ValueError:
        return None


def _encode_addr(addr: str) -> str:
    return addr.lower().replace("0x", "").rjust(64, "0")


def _encode_u256(n: int) -> str:
    return f"{n:064x}"


def _encode_bool(v: bool) -> str:
    return _encode_u256(1 if v else 0)


def _load_stage1(addr: str) -> dict:
    path = DATA / addr / "stage1.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _is_spokepool(stage1: dict, row_name: str) -> bool:
    sp = stage1.get("spokepool_hit_count") or 0
    if int(sp) >= 2:
        return True
    name = (row_name or "").lower()
    return "spokepool" in name or "across" in name


def _probe_mutators(
    chain: str,
    addr: str,
    owner: str,
    specs: list[tuple[str, str]],
    *,
    limit: int = 8,
) -> tuple[list[dict], list[str], int]:
    """eth_call mutators from 0x0 and owner. Returns (rows, flags, rpc_batches)."""
    dummy = "0x0000000000000000000000000000000000000001"
    calls: list[dict] = []
    meta: list[dict] = []
    for sig, kind in specs:
        sel = selector(sig)
        if kind == "address":
            data = sel + _encode_addr(dummy)
        elif kind == "bool":
            data = sel + _encode_bool(True)
        elif kind == "bundle":
            # bytes32[] offset + length 0 + uint32 0
            data = sel + _encode_u256(64) + _encode_u256(0) + _encode_u256(0)
        elif kind == "fill":
            # Minimal fillRelay-like: all zeros — expect revert; probes ACL only
            data = sel + (_encode_u256(0) * 12)
        else:
            data = sel
        for frm in (ZERO_ADDR, owner):
            calls.append({"to": addr, "data": data, "from": frm})
            meta.append({"sig": sig, "from": frm})
    calls = calls[:limit]
    meta = meta[:limit]
    res = eth_calls_batch(chain, calls)
    flags: list[str] = []
    rows = []
    for m, r in zip(meta, res):
        ok = bool(r.get("ok"))
        rows.append({**m, "eth_call_ok": ok})
        if ok and m["from"] == ZERO_ADDR:
            flags.append(f"CALLABLE_FROM_ZERO:{m['sig']}")
    return rows, flags, 1


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: stage2_checklist.py <addr>", file=sys.stderr)
        return 2
    addr = sys.argv[1].lower()
    row = find_by_addr(addr)
    if row is None:
        print(f"ERROR: {addr} not in QUEUE", file=sys.stderr)
        return 1
    chain = row.chain
    stage1 = _load_stage1(addr)
    owner = stage1.get("owner") or ZERO_ADDR
    surface_hits = set((stage1.get("surface") or {}).get("hits") or [])
    is_stargate = "stargateType()" in surface_hits
    is_spoke = _is_spokepool(stage1, row.name)

    rpc_batches = 0
    flags: list[str] = []
    details: dict = {}
    dummy = "0x0000000000000000000000000000000000000001"

    if is_spoke:
        # --- Across SpokePool path (≤4 batches) ---
        view_calls = [{"to": addr, "data": selector(sig)} for sig in SPOKE_VIEWS]
        view_res = eth_calls_batch(chain, view_calls[:8])
        rpc_batches += 1
        spoke_views: dict[str, object] = {}
        for sig, res in zip(SPOKE_VIEWS[:8], view_res):
            if not res.get("ok"):
                continue
            raw = res.get("result")
            if sig in (
                "hubPool()",
                "owner()",
                "relayer()",
                "oracle()",
                "nativeToken()",
                "poolToken()",
            ):
                spoke_views[sig] = storage_to_address(raw if isinstance(raw, str) else "0x0")
            else:
                spoke_views[sig] = _u256(raw if isinstance(raw, str) else None)
        details["spokepool_views"] = spoke_views

        # Unbacked/infinite mint proxies: totalMinted vs locked if present
        mint_views = eth_calls_batch(
            chain,
            [{"to": addr, "data": selector(s)} for s in ("totalMinted()", "totalLocked()", "numberOfDeposits()")],
        )
        rpc_batches += 1
        tm = _u256(mint_views[0].get("result") if mint_views[0].get("ok") else None)
        tl = _u256(mint_views[1].get("result") if mint_views[1].get("ok") else None)
        deposits = _u256(mint_views[2].get("result") if mint_views[2].get("ok") else None)
        details["totalMinted"] = tm
        details["totalLocked"] = tl
        details["numberOfDeposits"] = deposits
        unbacked = None
        if tm is not None and tl is not None:
            unbacked = tm > tl
            if unbacked:
                flags.append("UNBACKED_MINT_INVARIANT")
        details["unbacked_mint"] = unbacked

        # fillRelay ACL: who can fill? Probe from 0x0 (expect revert)
        # Signature is complex; use a short selector probe with zeroed args.
        fill_sig = "fillRelay(bytes)"
        fill_data = (
            selector(fill_sig)
            + _encode_u256(32)
            + _encode_u256(0)
        )
        # fillV3Relay with truncated args → expect revert (ACL probe only)
        fill_calls = [
            {"to": addr, "data": fill_data, "from": ZERO_ADDR},
            {"to": addr, "data": fill_data, "from": owner},
            {"to": addr, "data": selector("fillV3Relay(bytes,uint256)") + _encode_u256(32) + _encode_u256(0) + _encode_u256(0), "from": ZERO_ADDR},
            {"to": addr, "data": selector("fillV3Relay(bytes,uint256)") + _encode_u256(32) + _encode_u256(0) + _encode_u256(0), "from": owner},
            {"to": addr, "data": selector("requestSlowFill(bytes)") + _encode_u256(32) + _encode_u256(0), "from": ZERO_ADDR},
            {"to": addr, "data": selector("executeRelayerRefundLeaf(uint32,bytes,(uint256,address[],uint256[]))"), "from": ZERO_ADDR},
        ]
        # Cap to 6 + pad with owner mutators in next batch
        fill_res = eth_calls_batch(chain, fill_calls)
        rpc_batches += 1
        fill_rows = []
        fill_meta = [
            {"sig": "fillRelay(bytes)", "from": ZERO_ADDR},
            {"sig": "fillRelay(bytes)", "from": owner},
            {"sig": "fillV3Relay(bytes,uint256)", "from": ZERO_ADDR},
            {"sig": "fillV3Relay(bytes,uint256)", "from": owner},
            {"sig": "requestSlowFill(bytes)", "from": ZERO_ADDR},
            {"sig": "executeRelayerRefundLeaf(...)", "from": ZERO_ADDR},
        ]
        for m, r in zip(fill_meta, fill_res):
            ok = bool(r.get("ok"))
            fill_rows.append({**m, "eth_call_ok": ok})
            if ok and m["from"] == ZERO_ADDR:
                flags.append(f"FILL_CALLABLE_FROM_ZERO:{m['sig']}")
        details["fill_access"] = fill_rows
        details["message_spoofing"] = {
            "note": (
                "fill amount/price/chainId must be validated against deposit + "
                "relayer bond; public fill is expected but forged deposit root is not"
            ),
            "public_fill_expected": True,
            "verified_source": stage1.get("verified"),
            "needs_manual": True,
        }

        # Owner powers / stale root injection
        owner_rows, owner_flags, b = _probe_mutators(
            chain, addr, owner, SPOKE_OWNER_MUTATORS, limit=8
        )
        rpc_batches += b
        flags.extend(owner_flags)
        details["owner_mutators"] = owner_rows
        details["owner_powers"] = {
            "note": "setHubPool/setCrossDomainAdmin/pause = centralization risk, not finding",
            "owner": owner,
            "callable_from_zero": [f for f in owner_flags],
        }
        details["stale_state"] = {
            "note": "nonce/sequence / rootBundle replay needs source or fork test",
            "needs_manual": True,
        }
        details["public_relayer"] = {
            "relayer": spoke_views.get("relayer()"),
            "oracle": spoke_views.get("oracle()"),
            "hubPool": spoke_views.get("hubPool()"),
            "note": "who injects roots/batches — HubPool vs open relayer",
        }

    elif is_stargate:
        view_calls = [{"to": addr, "data": selector(sig)} for sig in STARGATE_VIEW_SIGS]
        view_res = eth_calls_batch(chain, view_calls)
        rpc_batches += 1
        sg_views: dict[str, object] = {}
        for sig, res in zip(STARGATE_VIEW_SIGS, view_res):
            if not res.get("ok"):
                continue
            raw = res.get("result")
            if sig in ("token()", "endpoint()", "poolToken()", "stargate()"):
                sg_views[sig] = storage_to_address(raw if isinstance(raw, str) else "0x0")
            else:
                sg_views[sig] = _u256(raw if isinstance(raw, str) else None)
        details["stargate_views"] = sg_views
        if sg_views.get("stargateType()") is not None:
            details["stargateType"] = sg_views.get("stargateType()")

        access_sigs = [
            ("transferOwnership(address)", selector("transferOwnership(address)") + _encode_addr(dummy)),
            ("renounceOwnership()", selector("renounceOwnership()")),
            ("setDelegate(address)", selector("setDelegate(address)") + _encode_addr(dummy)),
            ("mint(address,uint256)", selector("mint(address,uint256)") + _encode_addr(dummy) + _encode_u256(1)),
        ]
        access_calls = []
        access_meta = []
        for sig, data in access_sigs:
            for frm in (ZERO_ADDR, owner):
                access_calls.append({"to": addr, "data": data, "from": frm})
                access_meta.append({"sig": sig, "from": frm})
        access_calls = access_calls[:8]
        access_meta = access_meta[:8]
        access_res = eth_calls_batch(chain, access_calls)
        rpc_batches += 1
        access_rows = []
        for meta, res in zip(access_meta, access_res):
            ok = bool(res.get("ok"))
            access_rows.append({**meta, "eth_call_ok": ok})
            if ok and meta["from"] == ZERO_ADDR:
                flags.append(f"STARGATE_CALLABLE_FROM_ZERO:{meta['sig']}")
        details["stargate_access"] = access_rows

        meaningful = [
            k
            for k, v in sg_views.items()
            if k != "stargateType()" and v not in (None, 0, "0x0000000000000000000000000000000000000000")
        ]
        if not meaningful and not flags:
            flags.append("THIN_STARGATE_SURFACE")
            details["thin_surface_note"] = (
                "stargateType present but no token/endpoint/poolToken — likely not a live pool"
            )

        details["totalMinted"] = None
        details["totalLocked"] = None
        details["unbacked_mint"] = None
        details["message_spoofing"] = {
            "note": "requires source review: chainId binding, signature, nonce",
            "verified_source": stage1.get("verified"),
            "needs_manual": True,
        }
    else:
        view_calls = [{"to": addr, "data": selector(sig)} for sig in VIEW_SIGS]
        view_res = eth_calls_batch(chain, view_calls)
        rpc_batches += 1
        views: dict[str, int | None] = {}
        for sig, res in zip(VIEW_SIGS, view_res):
            views[sig] = _u256(res.get("result") if res.get("ok") else None)
        details["views"] = {k: v for k, v in views.items() if v is not None}

        total_minted = views.get("totalMinted()")
        total_locked = views.get("totalLocked()")
        if total_minted is None:
            total_minted = views.get("totalSupply()")
        if total_locked is None:
            total_locked = views.get("totalBridged()") or views.get("lockedBalance()")

        unbacked = None
        if total_minted is not None and total_locked is not None:
            unbacked = total_minted > total_locked
            if unbacked:
                flags.append("UNBACKED_MINT_INVARIANT")
        details["totalMinted"] = total_minted
        details["totalLocked"] = total_locked
        details["unbacked_mint"] = unbacked

        mint_calls = []
        mint_meta = []
        for sig in MINT_SIGS:
            sel = selector(sig)
            if sig == "mint(address,uint256)":
                data = sel + _encode_addr(dummy) + _encode_u256(1)
            elif sig == "mint(address,uint256,bytes)":
                data = (
                    sel
                    + _encode_addr(dummy)
                    + _encode_u256(1)
                    + _encode_u256(96)
                    + _encode_u256(0)
                )
            else:
                data = sel + _encode_u256(1)
            for frm in (ZERO_ADDR, owner):
                mint_calls.append({"to": addr, "data": data, "from": frm})
                mint_meta.append({"sig": sig, "from": frm})
        mint_calls = mint_calls[:8]
        mint_meta = mint_meta[:8]
        mint_res = eth_calls_batch(chain, mint_calls)
        rpc_batches += 1
        mint_access = []
        for meta, res in zip(mint_meta, mint_res):
            ok = bool(res.get("ok"))
            entry = {"sig": meta["sig"], "from": meta["from"], "eth_call_ok": ok}
            if ok and meta["from"] == ZERO_ADDR:
                flags.append("MINT_CALLABLE_FROM_ZERO")
            mint_access.append(entry)
        details["mint_access"] = mint_access

        anchor_calls = []
        anchor_meta = []
        for sig in ANCHOR_SIGS:
            sel = selector(sig)
            if sig.startswith("updateAnchor(bytes32)"):
                data = sel + _encode_u256(0)
            elif sig == "updateAnchor(uint256,bytes32)":
                data = sel + _encode_u256(1) + _encode_u256(0)
            elif sig == "setLocked(uint256)":
                data = sel + _encode_u256(1)
            else:
                data = sel + _encode_addr(dummy) + _encode_u256(1)
            for frm in (ZERO_ADDR, owner):
                anchor_calls.append({"to": addr, "data": data, "from": frm})
                anchor_meta.append({"sig": sig, "from": frm})
        anchor_calls = anchor_calls[:8]
        anchor_meta = anchor_meta[:8]
        if rpc_batches < 10:
            anchor_res = eth_calls_batch(chain, anchor_calls)
            rpc_batches += 1
            anchor_access = []
            for meta, res in zip(anchor_meta, anchor_res):
                ok = bool(res.get("ok"))
                entry = {"sig": meta["sig"], "from": meta["from"], "eth_call_ok": ok}
                if ok and meta["from"] == ZERO_ADDR:
                    flags.append("ANCHOR_CALLABLE_FROM_ZERO")
                anchor_access.append(entry)
            details["anchor_access"] = anchor_access

        details["message_spoofing"] = {
            "note": "requires source review: chainId binding, signature, nonce",
            "verified_source": stage1.get("verified"),
            "needs_manual": True,
        }

    details["owner"] = owner
    details["eip1967_admin"] = stage1.get("eip1967_admin")
    details["eip1967_impl"] = stage1.get("eip1967_impl")
    details["upgrade_surface"] = bool(stage1.get("eip1967_admin") or stage1.get("eip1967_impl"))

    if stage1.get("verified") is False:
        flags.append("UNVERIFIED_SOURCE_SPOOFING_REVIEW")

    dangerous = [
        f
        for f in flags
        if f.startswith("MINT_CALLABLE")
        or f.startswith("ANCHOR_CALLABLE")
        or f.startswith("STARGATE_CALLABLE")
        or f.startswith("FILL_CALLABLE")
        or f.startswith("CALLABLE_FROM_ZERO")
        or f == "UNBACKED_MINT_INVARIANT"
    ]
    if dangerous:
        stage = "FORK"
        reason = "invariant_or_access_flags:" + ",".join(sorted(set(flags)))
    elif "THIN_STARGATE_SURFACE" in flags:
        stage = "SAFE"
        reason = "thin_stargate_surface_likely_wrong_contract"
    elif flags:
        stage = "FORK"
        reason = "invariant_or_access_flags:" + ",".join(sorted(set(flags)))
    else:
        stage = "SAFE"
        reason = "no_invariant_flags"

    # Stage2 auto-stage is a hint for strategist — CURSOR stays; do not FORK-run stage3 here
    report = {
        "addr": addr,
        "chain": chain,
        "name": row.name,
        "rpc_batches": rpc_batches,
        "flags": sorted(set(flags)),
        "details": details,
        "stage": stage,
        "reason": reason,
        "stage1_ref": str(DATA / addr / "stage1.json"),
        "path": "spokepool" if is_spoke else ("stargate" if is_stargate else "generic"),
    }

    out_dir = DATA / addr
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "stage2.json"
    out_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    # Keep CHECKLIST until strategist verdict; only update if SAFE/FORK hint for visibility
    updated = update_stage(addr, stage)
    if updated:
        set_cursor(updated.num)

    print(f"stage2: {addr} → {stage} (rpc_batches={rpc_batches})")
    print(f"json: {out_path}")
    print_queue_table()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
