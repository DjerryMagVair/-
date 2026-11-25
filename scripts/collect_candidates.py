#!/usr/bin/env python3
"""Collect bridge candidates into STATE.md QUEUE.

Layer 1: curated allowlist addresses (real bridge contracts, NOT Llama tokens).
Layer 2: DefiLlama /protocols for TVL + listedAt only (never for address).
Layer 3: verify code + explorer + bridge_surface before enqueue.

Priority: attack-surface score (not raw TVL).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from lib.bridge_surface import validate_bridge_surface  # noqa: E402
from lib.explorer import is_contract_verified  # noqa: E402
from lib.rpc import eth_get_code, http_get_json, load_config  # noqa: E402
from lib.state import (  # noqa: E402
    QueueRow,
    parse_excluded_rows,
    parse_queue,
    print_queue_table,
    replace_queue,
    set_cursor,
)

ALLOWLIST_PATH = ROOT / "config" / "bridge_allowlist.json"
DATA_DIR = ROOT / "data"

NEW_CHAINS = {"base", "ink", "robinhood", "bsc"}
# Protocols with public audits/bounties — down-rank attack-surface score
AUDITED_DEFAULT = {"across", "stargate", "wormhole"}


def load_allowlist() -> dict[str, Any]:
    raw = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    return {k: v for k, v in raw.items() if not k.startswith("_") and isinstance(v, dict)}


def _llama_tvl_index(cfg: dict) -> dict[str, dict[str, Any]]:
    """slug/name.lower() → {tvl, listed_at} from DefiLlama protocols (bridge*)."""
    protocols = http_get_json("https://api.llama.fi/protocols", cfg)
    if not isinstance(protocols, list):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for p in protocols:
        if not isinstance(p, dict):
            continue
        cat = str(p.get("category") or "").lower()
        if "bridge" not in cat:
            continue
        try:
            tvl = float(p.get("tvl") or 0)
        except (TypeError, ValueError):
            tvl = 0.0
        listed = p.get("listedAt")
        listed_at: datetime | None = None
        if isinstance(listed, (int, float)) and listed > 0:
            listed_at = datetime.fromtimestamp(int(listed), tz=timezone.utc)
        entry = {"tvl": tvl, "listed_at": listed_at, "name": p.get("name")}
        slug = str(p.get("slug") or "").lower()
        name = str(p.get("name") or "").lower()
        if slug:
            out[slug] = entry
        if name:
            out[name] = entry
    return out


def _parse_listed_at(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.strptime(raw[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _age_months(when: datetime | None, now: datetime) -> float | None:
    if when is None:
        return None
    return max(0.0, (now - when).days / 30.44)


def tvl_factor(tvl: float) -> float:
    """Prefer mid-tier; crush mega-TVL."""
    if tvl <= 0:
        return 3.0  # unknown / manual allowlist
    if 500_000 <= tvl <= 30_000_000:
        return 4.0
    if tvl <= 80_000_000:
        return 2.0
    if tvl <= 500_000_000:
        return 0.5
    return 0.25  # mega — almost never worth hunter time


def age_factor(months: float | None) -> float:
    if months is None:
        return 2.0
    if months < 6:
        return 4.0
    if months < 12:
        return 3.0
    if months <= 24:
        return 2.0
    return 1.0


def custom_factor(is_custom: bool) -> float:
    return 2.0 if is_custom else 1.0


def vanilla_factor(is_vanilla: bool) -> float:
    """OP-stack / Arb standard gateway re-deploys — low hunt value."""
    return 0.35 if is_vanilla else 1.0


def chain_factor(chain: str) -> float:
    return 2.0 if chain.lower() in NEW_CHAINS else 1.0


def audit_factor(is_audited: bool) -> float:
    """Public audits/bounty (Across/Stargate/Wormhole/Linea…) → 0.35."""
    return 0.35 if is_audited else 1.0


def attack_surface_score(
    *,
    tvl: float,
    listed_at: datetime | None,
    is_custom: bool,
    chain: str,
    is_audited: bool = False,
    is_vanilla: bool = False,
    now: datetime | None = None,
) -> float:
    now = now or datetime.now(timezone.utc)
    raw = (
        tvl_factor(tvl)
        * age_factor(_age_months(listed_at, now))
        * custom_factor(is_custom)
        * chain_factor(chain)
        * audit_factor(is_audited)
        * vanilla_factor(is_vanilla)
    )
    return round(float(raw), 2)


def _match_llama(meta: dict[str, Any], index: dict[str, dict[str, Any]]) -> dict[str, Any]:
    for slug in meta.get("llama_slugs") or []:
        hit = index.get(str(slug).lower())
        if hit:
            return hit
    name = str(meta.get("display_name") or "").lower()
    if name and name in index:
        return index[name]
    return {"tvl": 0.0, "listed_at": None}


def verify_candidate(addr: str, chain: str, *, allowlisted: bool = True) -> dict[str, Any]:
    """code + explorer + bridge_surface. RPC ≤ ~4 HTTP requests.

    Allowlisted contracts: accept strong_hits≥1 (curated addr already trusted)
    when full ≥2-hit surface heuristic misses custom L1/L2 ABIs.
    """
    code = eth_get_code(chain, addr)
    code_hex = code[2:] if isinstance(code, str) and code.startswith("0x") else ""
    code_size = len(code_hex) // 2
    if code_size == 0:
        return {
            "ok": False,
            "reason": "no_code",
            "code_size": 0,
            "verified": None,
            "bridge_surface": False,
            "rpc_calls": 1,
        }

    explorer = is_contract_verified(chain, addr)
    surface = validate_bridge_surface(addr, chain)
    # validate_bridge_surface does getCode + ≤2 batches → count ≈ surface.rpc_batches
    # (re-getCode inside surface); budget still ≤ 1+3.
    rpc_calls = int(surface.get("rpc_batches") or 0)

    verified = explorer.get("verified")
    # Explorer soft-fail: None (API down/key) OK.
    # Allowlisted addrs come from official docs — verified=False is a warning, not a hard block.
    explorer_ok = verified is not False or allowlisted
    surface_ok = bool(surface.get("bridge_surface"))
    strong = list(surface.get("strong_hits") or [])
    if allowlisted and not surface_ok and strong:
        surface_ok = True  # curated bridge addr + ≥1 strong marker
    # Last resort for curated proxies (EIP-1967 shells can be <500B): allowlist + code
    if allowlisted and not surface_ok and code_size >= 100:
        surface_ok = True

    ok = explorer_ok and surface_ok
    reason = "ok"
    if not surface_ok:
        reason = "no_bridge_surface"
    elif verified is False and not allowlisted:
        reason = "not_verified_on_explorer"
        ok = False

    return {
        "ok": ok,
        "reason": reason,
        "code_size": code_size,
        "verified": verified,
        "explorer": explorer,
        "bridge_surface": bool(surface.get("bridge_surface")),
        "surface_accepted": surface_ok,
        "surface": surface,
        "rpc_calls": rpc_calls,
    }


def main() -> int:
    force = "--force" in sys.argv
    cfg = load_config()
    allowlist = load_allowlist()
    now = datetime.now(timezone.utc)

    try:
        llama = _llama_tvl_index(cfg)
        llama_ok = True
    except Exception as exc:  # noqa: BLE001
        print(f"warn: llama fetch failed: {exc}", file=sys.stderr)
        llama = {}
        llama_ok = False

    existing = {r.addr: r for r in parse_queue()}
    excluded_by_addr = {
        e.addr: e for e in parse_excluded_rows() if e.addr
    }

    verified_rows: list[QueueRow] = []
    needs_address: list[str] = []
    skipped: list[dict[str, Any]] = []
    reports: list[dict[str, Any]] = []

    for protocol, meta in allowlist.items():
        chains = meta.get("chains") or {}
        if not isinstance(chains, dict) or not chains:
            needs_address.append(protocol)
            continue
        llama_hit = _match_llama(meta, llama)
        tvl = float(llama_hit.get("tvl") or 0)
        listed = llama_hit.get("listed_at") or _parse_listed_at(meta.get("listed_at"))
        is_custom = bool(meta.get("custom", True))
        is_audited = bool(meta.get("audited", protocol in AUDITED_DEFAULT))
        is_vanilla = bool(meta.get("vanilla", False))
        display = str(meta.get("display_name") or protocol)
        role = str(meta.get("role") or "")

        for chain, raw_addr in chains.items():
            if chain not in cfg["chains"]:
                skipped.append(
                    {
                        "protocol": protocol,
                        "chain": chain,
                        "reason": "chain_not_in_rpc_config",
                    }
                )
                continue
            if not isinstance(raw_addr, str) or not raw_addr.startswith("0x"):
                needs_address.append(f"{protocol}:{chain}")
                continue
            addr = raw_addr.lower()
            prior = existing.get(addr)
            excl = excluded_by_addr.get(addr)

            # EXCLUDED → skip unless --force (explicit re-audit)
            if excl and not force:
                skipped.append(
                    {
                        "protocol": protocol,
                        "chain": chain,
                        "addr": addr,
                        "reason": "excluded",
                    }
                )
                continue
            if prior and prior.stage.upper() == "EXCLUDED" and not force:
                skipped.append(
                    {
                        "protocol": protocol,
                        "chain": chain,
                        "addr": addr,
                        "reason": "queue_excluded",
                    }
                )
                continue

            score = attack_surface_score(
                tvl=tvl,
                listed_at=listed,
                is_custom=is_custom and not is_vanilla,
                chain=chain,
                is_audited=is_audited,
                is_vanilla=is_vanilla,
                now=now,
            )
            tvl_str = f"${tvl:,.0f}" if tvl > 0 else "manual"

            # Preserve prior stage (SAFE stays SAFE; do not resurrect from EXCLUDED)
            if prior:
                stage = prior.stage
            else:
                stage = "NEW"

            try:
                verdict = verify_candidate(addr, chain)
            except Exception as exc:  # noqa: BLE001
                skipped.append(
                    {
                        "protocol": protocol,
                        "chain": chain,
                        "addr": addr,
                        "reason": f"verify_error:{exc}",
                    }
                )
                continue

            report = {
                "protocol": protocol,
                "role": role,
                "name": display,
                "chain": chain,
                "addr": addr,
                "tvl": tvl,
                "score": score,
                "factors": {
                    "tvl_factor": tvl_factor(tvl),
                    "age_factor": age_factor(_age_months(listed, now)),
                    "custom_factor": custom_factor(is_custom and not is_vanilla),
                    "chain_factor": chain_factor(chain),
                    "audit_factor": audit_factor(is_audited),
                    "vanilla_factor": vanilla_factor(is_vanilla),
                },
                "why": meta.get("why"),
                "vanilla": is_vanilla,
                "listed_at": listed.isoformat() if isinstance(listed, datetime) else None,
                "verify": {
                    "ok": verdict["ok"],
                    "reason": verdict["reason"],
                    "code_size": verdict["code_size"],
                    "verified": verdict["verified"],
                    "bridge_surface": verdict["bridge_surface"],
                    "rpc_calls": verdict["rpc_calls"],
                },
                "llama_ok": llama_ok,
                "force": force,
            }
            reports.append(report)
            out_dir = DATA_DIR / addr
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "collect.json").write_text(
                json.dumps(report, indent=2) + "\n", encoding="utf-8"
            )

            if not verdict["ok"]:
                skipped.append(
                    {
                        "protocol": protocol,
                        "chain": chain,
                        "addr": addr,
                        "reason": verdict["reason"],
                    }
                )
                continue

            verified_rows.append(
                QueueRow(
                    num=0,  # renumber after sort
                    name=display,
                    chain=chain,
                    addr=addr,
                    tvl=tvl_str,
                    stage=stage,
                    score=str(score),
                )
            )

    # Dedup by address (keep highest score)
    by_addr: dict[str, QueueRow] = {}
    for row in verified_rows:
        prev = by_addr.get(row.addr)
        if prev is None or float(row.score or 0) > float(prev.score or 0):
            by_addr[row.addr] = row

    ranked = sorted(
        by_addr.values(),
        key=lambda r: (-float(r.score or 0), r.name.lower()),
    )
    for i, row in enumerate(ranked, start=1):
        row.num = i

    replace_queue(
        ranked,
        comment=(
            "hunt score = tvl×age×custom×chain×audit×vanilla; "
            "EXCLUDED skipped unless --force; "
            "addrs from config/bridge_allowlist.json"
        ),
    )

    # CURSOR → highest-score NEW (or first row)
    cursor_target = next((r for r in ranked if r.stage.upper() == "NEW"), None)
    if cursor_target is None and ranked:
        cursor_target = ranked[0]
    if cursor_target:
        set_cursor(cursor_target.num)
    else:
        set_cursor("none")

    # stderr diagnostics; stdout = table only
    print(
        f"allowlist_protocols: {len(allowlist)} "
        f"queued: {len(ranked)} skipped: {len(skipped)} "
        f"needs_address: {len(needs_address)}",
        file=sys.stderr,
    )
    if needs_address:
        print(f"needs_address: {needs_address}", file=sys.stderr)
    for s in skipped[:30]:
        print(f"skip: {s}", file=sys.stderr)

    print_queue_table(ranked)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
