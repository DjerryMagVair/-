"""Bridge-surface validation via eth_call getter probes (from 0x0)."""

from __future__ import annotations

from typing import Any

from .rpc import ZERO_ADDR, eth_calls_batch, eth_get_code, selector

# Probe signatures — selectors computed via Keccak, never hard-coded as magic.
# Known expected 4-bytes (self-check): owner=0x8da5cb5b, wormhole=0x84acd1bb, …
VIEW_SIGS: list[str] = [
    "owner()",
    "tokenImplementation()",
    "wormhole()",
    "chainId()",
    "tokenBridge()",
    "getChainId()",
    "totalMinted()",
    "totalLocked()",
    # Stargate pool marker (OFT tokens like ZRO do not expose this)
    "stargateType()",
]

ARG_PROBES: list[tuple[str, str]] = [
    ("mint(address,uint256)", "address,uint256"),
    ("burn(uint256)", "uint256"),
    ("lock(address,uint256)", "address,uint256"),
    ("unlock(address,uint256)", "address,uint256"),
    ("verifyMessage(bytes)", "bytes"),
    ("processMessage(bytes)", "bytes"),
    ("updateAnchor(uint256)", "uint256"),
    ("setLockedAmount(uint256)", "uint256"),
    ("relayer(address)", "address"),
    ("oracle(address)", "address"),
]


def _enc_addr(addr: str = ZERO_ADDR) -> str:
    return addr.lower().replace("0x", "").rjust(64, "0")


def _enc_u256(n: int = 0) -> str:
    return f"{n:064x}"


def _encode_probe(sig: str, kind: str) -> str:
    sel = selector(sig)
    if kind == "address,uint256":
        return sel + _enc_addr(ZERO_ADDR) + _enc_u256(0)
    if kind == "uint256":
        return sel + _enc_u256(0)
    if kind == "address":
        return sel + _enc_addr(ZERO_ADDR)
    if kind == "bytes":
        return sel + _enc_u256(32) + _enc_u256(0)
    return sel


def _is_hit(res: dict[str, Any]) -> bool:
    """Non-revert with non-empty returndata (EOA eth_call returns empty 0x)."""
    if not res.get("ok"):
        return False
    result = res.get("result")
    if not isinstance(result, str):
        return False
    if result in ("0x", "0X", "", "0x0"):
        return False
    return len(result) > 2


def validate_bridge_surface(
    addr: str,
    chain: str,
    *,
    from_addr: str = ZERO_ADDR,
) -> dict[str, Any]:
    """Return bridge-surface verdict.

    ≥2 non-reverting probes with non-empty returndata → bridge-surface: true
    0–1 → false (token/governance / EOA / wrong contract)

    RPC: 1 eth_getCode + at most 2 batches (≤8) = ≤3 HTTP RPC requests.
    """
    addr = addr.lower()

    code = eth_get_code(chain, addr)
    code_hex = code[2:] if code.startswith("0x") else code
    code_size = len(code_hex) // 2
    rpc_batches = 1  # eth_getCode counts toward budget

    if code_size == 0:
        return {
            "bridge_surface": False,
            "hits": [],
            "hit_count": 0,
            "rpc_batches": rpc_batches,
            "code_size": 0,
            "details": [],
            "label": "no-bridge-surface",
            "reason": "no_code",
        }

    probes: list[dict[str, str]] = []
    meta: list[str] = []

    for sig in VIEW_SIGS:
        probes.append({"to": addr, "data": selector(sig), "from": from_addr})
        meta.append(sig)

    for sig, kind in ARG_PROBES:
        probes.append({"to": addr, "data": _encode_probe(sig, kind), "from": from_addr})
        meta.append(sig)

    # Cap remaining probes to 16 → 2 batches of 8
    probes = probes[:16]
    meta = meta[:16]

    hits: list[str] = []
    details: list[dict[str, Any]] = []

    batch1, meta1 = probes[:8], meta[:8]
    res1 = eth_calls_batch(chain, batch1)
    rpc_batches += 1
    for sig, res in zip(meta1, res1):
        ok = _is_hit(res)
        details.append({"sig": sig, "ok": ok, "raw_ok": bool(res.get("ok"))})
        if ok:
            hits.append(sig)

    if len(hits) < 2:
        batch2, meta2 = probes[8:16], meta[8:16]
        if batch2:
            res2 = eth_calls_batch(chain, batch2)
            rpc_batches += 1
            for sig, res in zip(meta2, res2):
                ok = _is_hit(res)
                details.append({"sig": sig, "ok": ok, "raw_ok": bool(res.get("ok"))})
                if ok:
                    hits.append(sig)

    # owner/mint/burn alone are common on tokens — require ≥1 strong probe.
    strong_set = {
        "tokenImplementation()",
        "wormhole()",
        "chainId()",
        "tokenBridge()",
        "getChainId()",
        "totalMinted()",
        "totalLocked()",
        "stargateType()",
        "verifyMessage(bytes)",
        "processMessage(bytes)",
        "updateAnchor(uint256)",
        "setLockedAmount(uint256)",
        "lock(address,uint256)",
        "unlock(address,uint256)",
        "relayer(address)",
        "oracle(address)",
    }
    strong_hits = [h for h in hits if h in strong_set]
    surface = len(hits) >= 2 and len(strong_hits) >= 1
    return {
        "bridge_surface": surface,
        "hits": hits,
        "strong_hits": strong_hits,
        "hit_count": len(hits),
        "rpc_batches": rpc_batches,
        "code_size": code_size,
        "details": details,
        "label": "bridge-surface: true" if surface else "no-bridge-surface",
    }
