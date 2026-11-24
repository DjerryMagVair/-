"""Parse and update STATE.md — single source of truth."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE_PATH = ROOT / "STATE.md"


@dataclass
class QueueRow:
    num: int
    name: str
    chain: str
    addr: str
    tvl: str
    stage: str


def _read() -> str:
    return STATE_PATH.read_text(encoding="utf-8")


def _write(text: str) -> None:
    STATE_PATH.write_text(text, encoding="utf-8")


def _section(text: str, header: str) -> tuple[int, int, str]:
    """Return (start, end, body) for ## HEADER section."""
    pattern = re.compile(rf"^## {re.escape(header)}\s*$", re.M)
    m = pattern.search(text)
    if not m:
        raise ValueError(f"Section ## {header} not found in STATE.md")
    start = m.end()
    nxt = re.search(r"^## ", text[start:], re.M)
    end = start + nxt.start() if nxt else len(text)
    return m.start(), end, text[start:end]


def parse_queue(text: str | None = None) -> list[QueueRow]:
    text = text if text is not None else _read()
    _, _, body = _section(text, "QUEUE")
    rows: list[QueueRow] = []
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 6:
            continue
        if cells[0] in {"#", "---"} or set(cells[0]) <= {"-"}:
            continue
        try:
            num = int(cells[0])
        except ValueError:
            continue
        rows.append(
            QueueRow(
                num=num,
                name=cells[1],
                chain=cells[2],
                addr=cells[3].lower(),
                tvl=cells[4],
                stage=cells[5],
            )
        )
    return rows


def parse_excluded(text: str | None = None) -> set[tuple[str, str]]:
    text = text if text is not None else _read()
    _, _, body = _section(text, "EXCLUDED")
    out: set[tuple[str, str]] = set()
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2:
            continue
        if cells[0].lower() in {"name", "---"} or set(cells[0]) <= {"-"}:
            continue
        out.add((cells[0].lower(), cells[1].lower()))
    return out


def next_queue_num(rows: list[QueueRow] | None = None) -> int:
    rows = rows if rows is not None else parse_queue()
    return (max((r.num for r in rows), default=0) + 1)


def find_by_addr(addr: str) -> QueueRow | None:
    addr = addr.lower()
    for row in parse_queue():
        if row.addr == addr:
            return row
    return None


def append_queue_rows(new_rows: list[QueueRow]) -> int:
    """Append rows to QUEUE table. Returns count added."""
    if not new_rows:
        return 0
    text = _read()
    sec_start, sec_end, body = _section(text, "QUEUE")
    lines = body.rstrip("\n").splitlines()
    # Ensure header exists
    if not any(l.strip().startswith("| #") for l in lines):
        lines = [
            "",
            "| # | name | chain | addr | tvl | stage |",
            "|---|------|-------|------|-----|-------|",
        ]
    for row in new_rows:
        lines.append(
            f"| {row.num} | {row.name} | {row.chain} | {row.addr} | {row.tvl} | {row.stage} |"
        )
    new_body = "\n".join(lines) + "\n\n"
    _write(text[:sec_start] + "## QUEUE\n" + new_body + text[sec_end:])
    return len(new_rows)


def update_stage(addr: str, stage: str) -> QueueRow | None:
    text = _read()
    addr = addr.lower()
    sec_start, sec_end, body = _section(text, "QUEUE")
    lines = body.splitlines()
    updated: QueueRow | None = None
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("|"):
            new_lines.append(line)
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cells) >= 6 and cells[3].lower() == addr:
            try:
                num = int(cells[0])
            except ValueError:
                new_lines.append(line)
                continue
            cells[5] = stage
            new_line = "| " + " | ".join(cells) + " |"
            new_lines.append(new_line)
            updated = QueueRow(
                num=num,
                name=cells[1],
                chain=cells[2],
                addr=cells[3].lower(),
                tvl=cells[4],
                stage=stage,
            )
        else:
            new_lines.append(line)
    if updated is None:
        return None
    new_body = "\n".join(new_lines)
    if not new_body.endswith("\n"):
        new_body += "\n"
    _write(text[:sec_start] + "## QUEUE\n" + new_body + text[sec_end:])
    return updated


def set_cursor(num: int | str) -> None:
    text = _read()
    sec_start, sec_end, _ = _section(text, "CURSOR")
    body = f"\ncurrent: #{num}\n\n" if num != "none" else "\ncurrent: none\n\n"
    _write(text[:sec_start] + "## CURSOR\n" + body + text[sec_end:])


def append_excluded(name: str, chain: str, when: str | None = None) -> None:
    when = when or date.today().isoformat()
    text = _read()
    sec_start, sec_end, body = _section(text, "EXCLUDED")
    lines = body.rstrip("\n").splitlines()
    if not any(l.strip().startswith("| name") for l in lines):
        lines = ["", "| name | chain | date |", "|------|-------|------|"]
    lines.append(f"| {name} | {chain} | {when} |")
    new_body = "\n".join(lines) + "\n\n"
    _write(text[:sec_start] + "## EXCLUDED\n" + new_body + text[sec_end:])


def print_queue_table(rows: list[QueueRow] | None = None) -> None:
    rows = rows if rows is not None else parse_queue()
    print("| # | name | chain | addr | tvl | stage |")
    print("|---|------|-------|------|-----|-------|")
    for r in rows:
        print(f"| {r.num} | {r.name} | {r.chain} | {r.addr} | {r.tvl} | {r.stage} |")
