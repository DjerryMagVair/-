#!/usr/bin/env python3
"""Collect bridge candidates from DefiLlama into STATE.md QUEUE.

Primary source: GET https://api.llama.fi/protocols (category Bridge*),
because /bridges is currently subscription-gated (HTTP 402).

Addresses from DefiLlama `address` are often tokens — only enqueue when
validate_bridge_surface(addr) is true.
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from lib.bridge_surface import validate_bridge_surface  # noqa: E402
from lib.rpc import http_get_json, load_config  # noqa: E402
from lib.state import (  # noqa: E402
    QueueRow,
    append_queue_rows,
    next_queue_num,
    parse_excluded,
    parse_excluded_addrs,
    parse_queue,
    print_queue_table,
)

TVL_MIN = 1_000_000

CHAIN_ALIASES = {
    "ethereum": "ethereum",
    "eth": "ethereum",
    "base": "base",
    "arbitrum": "arbitrum",
    "arb": "arbitrum",
    "bsc": "bsc",
    "binance": "bsc",
    "binance smart chain": "bsc",
}


def _normalize_chain(name: str) -> str | None:
    return CHAIN_ALIASES.get(name.strip().lower())


def _parse_prefixed_address(raw: str) -> tuple[str | None, str | None]:
    """Parse 'ethereum:0xabc...' or bare '0xabc...'."""
    raw = raw.strip()
    if not raw:
        return None, None
    if ":" in raw and not raw.startswith("0x"):
        chain_part, _, addr = raw.partition(":")
        chain = _normalize_chain(chain_part)
        if chain and addr.startswith("0x") and len(addr) >= 42:
            return chain, addr[:42].lower()
        return None, None
    if raw.startswith("0x") and len(raw) >= 42:
        return "ethereum", raw[:42].lower()
    return None, None


def _from_protocols(cfg: dict) -> list[dict]:
    protocols = http_get_json("https://api.llama.fi/protocols", cfg)
    if not isinstance(protocols, list):
        return []
    out = []
    allowed = set(cfg["chains"].keys())
    for p in protocols:
        if not isinstance(p, dict):
            continue
        cat = str(p.get("category") or "").lower()
        if "bridge" not in cat:
            continue
        try:
            tvl = float(p.get("tvl") or 0)
        except (TypeError, ValueError):
            continue
        if tvl < TVL_MIN:
            continue
        name = str(p.get("displayName") or p.get("name") or "").strip()
        addr_raw = p.get("address")
        chain, addr = (None, None)
        if isinstance(addr_raw, str):
            chain, addr = _parse_prefixed_address(addr_raw)
        if not chain or not addr or chain not in allowed:
            continue
        out.append({"name": name, "chain": chain, "addr": addr, "tvl": tvl})
    return out


def _from_bridges_api(cfg: dict) -> list[dict]:
    """Best-effort legacy endpoint (may 402/404)."""
    for url in (
        "https://api.llama.fi/bridges?includeChains=true",
        "https://bridges.llama.fi/bridges?includeChains=true",
    ):
        try:
            data = http_get_json(url, cfg)
        except Exception:
            continue
        bridges = data.get("bridges") if isinstance(data, dict) else data
        if not isinstance(bridges, list):
            continue
        out = []
        allowed = set(cfg["chains"].keys())
        for b in bridges:
            if not isinstance(b, dict):
                continue
            name = str(b.get("displayName") or b.get("name") or "").strip()
            try:
                tvl = float(b.get("tvl") or 0)
            except (TypeError, ValueError):
                continue
            if tvl < TVL_MIN or not name:
                continue
            addr = b.get("address")
            if not isinstance(addr, str):
                continue
            chain, parsed = _parse_prefixed_address(addr)
            if not chain:
                chain = _normalize_chain(str(b.get("destinationChain") or "ethereum"))
                parsed = addr.lower() if addr.startswith("0x") else None
            if chain in allowed and parsed:
                out.append({"name": name, "chain": chain, "addr": parsed, "tvl": tvl})
        if out:
            return out
    return []


def main() -> int:
    cfg = load_config()
    candidates = _from_bridges_api(cfg)
    source = "bridges"
    if not candidates:
        candidates = _from_protocols(cfg)
        source = "protocols"

    excluded_nc = parse_excluded()
    excluded_addrs = parse_excluded_addrs()
    existing_addrs = {r.addr for r in parse_queue()}
    next_num = next_queue_num()
    to_add: list[QueueRow] = []
    skipped_no_surface = 0
    skipped_excluded = 0

    for c in sorted(candidates, key=lambda x: -x["tvl"]):
        name = c["name"]
        chain = c["chain"]
        addr = c["addr"]
        if (name.lower(), chain.lower()) in excluded_nc:
            skipped_excluded += 1
            continue
        if addr in excluded_addrs:
            skipped_excluded += 1
            continue
        if addr in existing_addrs:
            continue

        surface = validate_bridge_surface(addr, chain)
        if not surface.get("bridge_surface"):
            skipped_no_surface += 1
            # Do not enqueue — no-bridge-surface (token/governance)
            continue

        to_add.append(
            QueueRow(
                num=next_num,
                name=name,
                chain=chain,
                addr=addr,
                tvl=f"${c['tvl']:,.0f}",
                stage="NEW",
            )
        )
        existing_addrs.add(addr)
        next_num += 1

    added = append_queue_rows(to_add)
    print(f"source: {source}")
    print(f"added: {added}")
    print(f"skipped_no_bridge_surface: {skipped_no_surface}")
    print(f"skipped_excluded: {skipped_excluded}")
    print_queue_table()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
