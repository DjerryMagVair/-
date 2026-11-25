"""Explorer verification (Etherscan-style + Blockscout)."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .rpc import _headers, load_config


def is_contract_verified(chain: str, address: str) -> dict[str, Any]:
    """Check source verification via explorer API.

    Returns {verified: bool|None, contract_name: str|None, error: str|None}.
    verified=None means explorer unreachable / rate-limited (soft fail).
    """
    cfg = load_config()
    chain_cfg = cfg["chains"].get(chain)
    if not chain_cfg:
        return {"verified": None, "contract_name": None, "error": f"unknown chain {chain}"}

    api = chain_cfg.get("explorer_api")
    if not api:
        return {"verified": None, "contract_name": None, "error": "no explorer_api"}

    kind = (chain_cfg.get("explorer_kind") or "etherscan").lower()
    address = address.lower()
    params = {
        "module": "contract",
        "action": "getsourcecode",
        "address": address,
    }
    url = f"{api}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers=_headers(cfg), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {"verified": None, "contract_name": None, "error": str(exc)[:200]}

    result = data.get("result") if isinstance(data, dict) else None
    # Etherscan: result is list[dict]; Blockscout often same
    entry: dict[str, Any] | None = None
    if isinstance(result, list) and result:
        entry = result[0] if isinstance(result[0], dict) else None
    elif isinstance(result, dict):
        entry = result

    if entry is None:
        # Some Blockscout variants nest under "result"
        return {
            "verified": False,
            "contract_name": None,
            "error": f"unexpected explorer payload status={data.get('status') if isinstance(data, dict) else None}",
            "kind": kind,
        }

    source = entry.get("SourceCode") or entry.get("sourceCode") or ""
    name = entry.get("ContractName") or entry.get("contractName") or ""
    abi = entry.get("ABI") or entry.get("abi") or ""
    verified = bool(source) and source not in ("", "0") and "not verified" not in str(abi).lower()
    # ABI-only "Contract source code not verified" => false
    if isinstance(abi, str) and "not verified" in abi.lower():
        verified = False
    return {
        "verified": verified,
        "contract_name": name or None,
        "error": None,
        "kind": kind,
    }
