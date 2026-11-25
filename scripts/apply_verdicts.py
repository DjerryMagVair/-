#!/usr/bin/env python3
"""Apply Strategist verdicts into STATE.md + refresh queue/current.json.

Cursor-only. Does not invent verdicts — only consumes verdicts/stageN/*.json.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from lib.state import (  # noqa: E402
    append_excluded,
    find_by_addr,
    print_queue_table,
    set_cursor,
    update_stage,
)

VERDICTS = REPO / "verdicts"
QUEUE_CURRENT = REPO / "queue" / "current.json"
DATA = REPO / "data"

STAGE_MAP = {
    1: {
        "SAFE": "SAFE",
        "EXCLUDED": "EXCLUDED",
        "STAGE2": "CHECKLIST",  # awaiting stage2 run; stage stays CHECKLIST until stage2 writes
    },
    2: {
        "SAFE": "SAFE",
        "EXCLUDED": "EXCLUDED",
        "FORK": "FORK",
    },
    3: {
        "SAFE": "SAFE",
        "HYPOTHESIS": "SAFE",  # no finding without failed invariant
        "FINDING": "FINDING",
    },
}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_current(row, awaiting: str | None, reports: dict) -> None:
    QUEUE_CURRENT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "cursor": row.num if row else None,
        "addr": row.addr if row else None,
        "name": row.name if row else None,
        "chain": row.chain if row else None,
        "stage": row.stage if row else None,
        "awaiting": awaiting,
        "reports": reports,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    QUEUE_CURRENT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _pending() -> list[tuple[int, Path, dict]]:
    out: list[tuple[int, Path, dict]] = []
    for stage in (1, 2, 3):
        d = VERDICTS / f"stage{stage}"
        if not d.is_dir():
            continue
        for path in sorted(d.glob("0x*.json")):
            v = _load(path)
            out.append((stage, path, v))
    return out


def main() -> int:
    applied = 0
    last_next: str | None = None

    for stage, path, v in _pending():
        addr = str(v.get("addr") or path.stem).lower()
        verdict = str(v.get("verdict") or "").upper()
        reason = str(v.get("reason") or "")
        next_cmd = v.get("next_cmd")
        row = find_by_addr(addr)
        if row is None:
            print(f"skip {path.name}: addr not in QUEUE", file=sys.stderr)
            continue

        mapping = STAGE_MAP.get(stage, {})
        if verdict not in mapping:
            print(f"skip {path.name}: bad verdict {verdict}", file=sys.stderr)
            continue

        # FINDING requires failed invariant evidence on disk
        if stage == 3 and verdict == "FINDING":
            s3 = DATA / addr / "stage3.json"
            ok = False
            if s3.exists():
                try:
                    ok = bool(_load(s3).get("invariant_failed"))
                except Exception:
                    ok = False
            if not ok:
                print(
                    f"reject FINDING {addr}: no invariant_failed in stage3.json → treat as HYPOTHESIS",
                    file=sys.stderr,
                )
                verdict = "HYPOTHESIS"

        new_stage = mapping[verdict]
        # STAGE2 verdict means "go run stage2" — keep CHECKLIST until stage2 script finishes
        if stage == 1 and verdict == "STAGE2":
            new_stage = "CHECKLIST"

        updated = update_stage(addr, new_stage)
        if verdict == "EXCLUDED":
            append_excluded(
                row.name,
                row.chain,
                addr=addr,
                note=reason or "strategist excluded",
            )
        if updated:
            set_cursor(updated.num)
        applied += 1
        if isinstance(next_cmd, str) and next_cmd.strip():
            last_next = next_cmd.strip()
        print(f"applied: stage{stage} {addr} → {verdict} (STATE stage={new_stage})")

    # Refresh queue/current.json from CURSOR row
    # Prefer last applied addr; else keep existing current if valid
    current_addr = None
    if last_next and "0x" in last_next:
        for part in last_next.split():
            if part.startswith("0x") and len(part) == 42:
                current_addr = part.lower()
    row = find_by_addr(current_addr) if current_addr else None
    if row is None:
        # fall back to existing queue file
        if QUEUE_CURRENT.exists():
            cur = _load(QUEUE_CURRENT)
            row = find_by_addr(str(cur.get("addr") or ""))
    reports = {}
    awaiting = None
    if row:
        for n in (1, 2, 3):
            p = DATA / row.addr / f"stage{n}.json"
            if p.exists():
                reports[f"stage{n}"] = str(p.relative_to(REPO))
        # what strategist should write next
        if "stage3" in reports and not (VERDICTS / "stage3" / f"{row.addr}.json").exists():
            awaiting = f"verdicts/stage3/{row.addr}.json"
        elif "stage2" in reports and not (VERDICTS / "stage2" / f"{row.addr}.json").exists():
            awaiting = f"verdicts/stage2/{row.addr}.json"
        elif "stage1" in reports and not (VERDICTS / "stage1" / f"{row.addr}.json").exists():
            awaiting = f"verdicts/stage1/{row.addr}.json"
        _write_current(row, awaiting, reports)

    print(f"applied_count: {applied}")
    if last_next:
        print(f"NEXT_CMD: {last_next}")
    else:
        print("NEXT_CMD: none")
    print_queue_table()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
