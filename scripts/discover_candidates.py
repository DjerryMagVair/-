#!/usr/bin/env python3
"""Discovery feed: DefiLlama age+TVL → ranked hunt list (no Llama addresses).

Writes data/discovery.json. Does NOT touch QUEUE.
Address resolution only from config/bridge_allowlist.json.
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

from collect_candidates import (  # noqa: E402
    _age_months,
    _llama_tvl_index,
    _match_llama,
    _parse_listed_at,
    attack_surface_score,
    load_allowlist,
)
from lib.rpc import eth_get_code, load_config  # noqa: E402
from lib.state import parse_excluded_rows  # noqa: E402

OUT = ROOT / "data" / "discovery.json"
TVL_MIN = 500_000
TVL_MAX = 80_000_000
AGE_MAX_MONTHS = 30


def main() -> int:
    cfg = load_config()
    now = datetime.now(timezone.utc)
    allowlist = load_allowlist()
    excluded = {e.addr for e in parse_excluded_rows() if e.addr}

    try:
        llama = _llama_tvl_index(cfg)
    except Exception as exc:  # noqa: BLE001
        print(f"llama failed: {exc}", file=sys.stderr)
        llama = {}

    # Layer A: Llama hunt pool (metadata only)
    llama_pool: list[dict[str, Any]] = []
    seen_slugs: set[str] = set()
    for slug, hit in llama.items():
        if slug in seen_slugs:
            continue
        tvl = float(hit.get("tvl") or 0)
        listed = hit.get("listed_at")
        months = _age_months(listed, now)
        if tvl < TVL_MIN or tvl > TVL_MAX:
            continue
        if months is None or months > AGE_MAX_MONTHS:
            continue
        seen_slugs.add(slug)
        llama_pool.append(
            {
                "slug": slug,
                "name": hit.get("name"),
                "tvl": tvl,
                "listed_at": listed.isoformat() if listed else None,
                "age_months": round(months, 1),
                "status": "needs-address",
                "note": "Llama address ignored — resolve from docs into allowlist",
            }
        )
    llama_pool.sort(key=lambda x: (x["age_months"], x["tvl"]))

    # Layer B: allowlist primary assessment
    assessed: list[dict[str, Any]] = []
    for protocol, meta in allowlist.items():
        llama_hit = _match_llama(meta, llama)
        tvl = float(llama_hit.get("tvl") or 0)
        listed = llama_hit.get("listed_at") or _parse_listed_at(meta.get("listed_at"))
        is_custom = bool(meta.get("custom", True))
        is_audited = bool(meta.get("audited", False))
        is_vanilla = bool(meta.get("vanilla", False))
        score = attack_surface_score(
            tvl=tvl,
            listed_at=listed,
            is_custom=is_custom and not is_vanilla,
            chain="ethereum",  # base factor; per-chain adjusted below
            is_audited=is_audited,
            is_vanilla=is_vanilla,
            now=now,
        )
        for chain, raw in (meta.get("chains") or {}).items():
            if chain not in cfg["chains"]:
                continue
            addr = str(raw).lower()
            if addr in excluded:
                status = "excluded"
                code_size = None
            else:
                try:
                    code = eth_get_code(chain, addr)
                    code_size = (len(code) - 2) // 2 if code.startswith("0x") else 0
                except Exception as exc:  # noqa: BLE001
                    code_size = None
                    status = f"rpc_error:{exc}"
                    assessed.append(
                        {
                            "protocol": protocol,
                            "name": meta.get("display_name"),
                            "chain": chain,
                            "addr": addr,
                            "tvl": tvl,
                            "score": score,
                            "status": status,
                            "why": meta.get("why"),
                        }
                    )
                    continue
                status = "ok" if code_size and code_size > 0 else "no_code"
            chain_score = attack_surface_score(
                tvl=tvl,
                listed_at=listed,
                is_custom=is_custom and not is_vanilla,
                chain=chain,
                is_audited=is_audited,
                is_vanilla=is_vanilla,
                now=now,
            )
            assessed.append(
                {
                    "protocol": protocol,
                    "name": meta.get("display_name"),
                    "role": meta.get("role"),
                    "chain": chain,
                    "addr": addr,
                    "tvl": tvl,
                    "tvl_fmt": f"${tvl:,.0f}" if tvl else "manual",
                    "score": chain_score,
                    "age_months": round(_age_months(listed, now) or 0, 1),
                    "custom": is_custom,
                    "audited": is_audited,
                    "vanilla": is_vanilla,
                    "code_size": code_size,
                    "status": status,
                    "why": meta.get("why"),
                    "listed_at": listed.isoformat() if listed else meta.get("listed_at"),
                }
            )

    assessed_ok = [a for a in assessed if a.get("status") == "ok"]
    assessed_ok.sort(key=lambda x: (-float(x["score"]), x["name"] or ""))
    top10 = assessed_ok[:10]

    payload = {
        "generated_at": now.isoformat(),
        "policy": {
            "tvl_min": TVL_MIN,
            "tvl_max": TVL_MAX,
            "age_max_months": AGE_MAX_MONTHS,
            "score": "tvl×age×custom×chain×audit×vanilla",
            "address_source": "allowlist only",
        },
        "top10": top10,
        "allowlist_assessed": assessed,
        "llama_needs_address": llama_pool[:40],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    print("| # | name | chain | addr | tvl | score | code | why |")
    print("|---|------|-------|------|-----|-------|------|-----|")
    for i, r in enumerate(top10, 1):
        why = (r.get("why") or "")[:48]
        print(
            f"| {i} | {r['name']} | {r['chain']} | {r['addr']} | "
            f"{r['tvl_fmt']} | {r['score']} | {r['code_size']} | {why} |"
        )
    print(f"\njson: {OUT}", file=sys.stderr)
    print(f"llama needs-address: {len(llama_pool)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
