"""Minimal JSON-RPC helpers for the bridge audit pipeline."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config" / "rpc.json"

# EIP-1967 storage slots
EIP1967_IMPL_SLOT = (
    "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"
)
EIP1967_ADMIN_SLOT = (
    "0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103"
)

ZERO_ADDR = "0x" + "0" * 40


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def _headers(cfg: dict[str, Any] | None = None) -> dict[str, str]:
    cfg = cfg or load_config()
    return {
        "Content-Type": "application/json",
        "User-Agent": cfg.get("user_agent", "Mozilla/5.0"),
    }


def selector(signature: str) -> str:
    """Compute 4-byte selector from a canonical Solidity signature (Keccak-256)."""
    from Crypto.Hash import keccak

    k = keccak.new(digest_bits=256)
    k.update(signature.encode("ascii"))
    return "0x" + k.hexdigest()[:8]


def _post(url: str, payload: Any, cfg: dict[str, Any] | None = None) -> Any:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=_headers(cfg), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"RPC HTTP {exc.code} for {url}: {exc.read()[:200]!r}") from exc
    return body


def _rpc_urls(chain_cfg: dict[str, Any]) -> list[str]:
    urls = [chain_cfg["rpc"]]
    for u in chain_cfg.get("rpc_fallbacks") or []:
        if u not in urls:
            urls.append(u)
    return urls


def rpc_batch(chain: str, calls: list[dict[str, Any]]) -> list[Any]:
    """Send eth_* batch requests (≤ batch_limit per HTTP request)."""
    cfg = load_config()
    chain_cfg = cfg["chains"].get(chain)
    if not chain_cfg:
        raise ValueError(f"Unknown chain: {chain}")
    urls = _rpc_urls(chain_cfg)
    limit = int(cfg.get("batch_limit", 8))
    results: list[Any] = []
    for i in range(0, len(calls), limit):
        chunk = calls[i : i + limit]
        payload = []
        for j, call in enumerate(chunk):
            payload.append(
                {
                    "jsonrpc": "2.0",
                    "id": i + j + 1,
                    "method": call["method"],
                    "params": call.get("params", []),
                }
            )
        raw = None
        last_err: Exception | None = None
        for url in urls:
            try:
                raw = _post(url, payload, cfg)
                break
            except Exception as exc:  # noqa: BLE001 — try next fallback
                last_err = exc
                continue
        if raw is None:
            raise RuntimeError(f"All RPCs failed for {chain}: {last_err}")
        if not isinstance(raw, list):
            raw = [raw]
        by_id = {item.get("id"): item for item in raw}
        for j in range(len(chunk)):
            item = by_id.get(i + j + 1, {})
            if "error" in item:
                results.append({"error": item["error"]})
            else:
                results.append(item.get("result"))
    return results


def eth_get_code(chain: str, address: str) -> str:
    res = rpc_batch(chain, [{"method": "eth_getCode", "params": [address, "latest"]}])
    return res[0] or "0x"


def eth_get_storage_at(chain: str, address: str, slot: str) -> str:
    res = rpc_batch(
        chain,
        [{"method": "eth_getStorageAt", "params": [address, slot, "latest"]}],
    )
    return res[0] or "0x" + "0" * 64


def eth_call(
    chain: str,
    to: str,
    data: str,
    from_addr: str | None = None,
) -> dict[str, Any]:
    tx: dict[str, str] = {"to": to, "data": data}
    if from_addr:
        tx["from"] = from_addr
    res = rpc_batch(chain, [{"method": "eth_call", "params": [tx, "latest"]}])
    out = res[0]
    if isinstance(out, dict) and "error" in out:
        return {"ok": False, "error": out["error"]}
    if out is None:
        return {"ok": False, "error": "null result"}
    return {"ok": True, "result": out}


def eth_calls_batch(
    chain: str,
    calls: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """Batch eth_call. Each item: {to, data, from?}."""
    payload = []
    for c in calls:
        tx: dict[str, str] = {"to": c["to"], "data": c["data"]}
        if c.get("from"):
            tx["from"] = c["from"]
        payload.append({"method": "eth_call", "params": [tx, "latest"]})
    raw = rpc_batch(chain, payload)
    out: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict) and "error" in item:
            out.append({"ok": False, "error": item["error"]})
        elif item is None:
            out.append({"ok": False, "error": "null result"})
        else:
            out.append({"ok": True, "result": item})
    return out


def storage_to_address(slot_value: str) -> str | None:
    if not slot_value or slot_value == "0x":
        return None
    hexval = slot_value[2:] if slot_value.startswith("0x") else slot_value
    if int(hexval, 16) == 0:
        return None
    return "0x" + hexval[-40:].lower()


def http_get_json(url: str, cfg: dict[str, Any] | None = None) -> Any:
    cfg = cfg or load_config()
    req = urllib.request.Request(url, headers=_headers(cfg), method="GET")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))
