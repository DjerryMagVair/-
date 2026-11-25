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


@dataclass
class ExcludedRow:
    name: str
    chain: str
    addr: str
    date: str
    note: str


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
    """Return set of (name.lower(), chain.lower()) for name/chain dedup."""
    return {(e.name.lower(), e.chain.lower()) for e in parse_excluded_rows(text)}


def parse_excluded_rows(text: str | None = None) -> list[ExcludedRow]:
    text = text if text is not None else _read()
    _, _, body = _section(text, "EXCLUDED")
    out: list[ExcludedRow] = []
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2:
            continue
        if cells[0].lower() in {"name", "---"} or set(cells[0]) <= {"-"}:
            continue
        # Formats:
        # | name | chain | date |
        # | name | chain | date | note |
        # | name | chain | addr | date | note |
        name = cells[0]
        chain = cells[1]
        addr = ""
        when = ""
        note = ""
        if len(cells) >= 5 and cells[2].startswith("0x"):
            addr = cells[2].lower()
            when = cells[3]
            note = cells[4]
        elif len(cells) >= 4:
            # name | chain | date | note  OR name | chain | addr | date
            if cells[2].startswith("0x"):
                addr = cells[2].lower()
                when = cells[3]
            else:
                when = cells[2]
                note = cells[3]
        elif len(cells) >= 3:
            when = cells[2]
        out.append(ExcludedRow(name=name, chain=chain, addr=addr, date=when, note=note))
    return out


def parse_excluded_addrs(text: str | None = None) -> set[str]:
    """Addresses listed in EXCLUDED (and QUEUE rows already EXCLUDED)."""
    addrs = {e.addr for e in parse_excluded_rows(text) if e.addr}
    for r in parse_queue(text):
        if r.stage.upper() == "EXCLUDED" or r.stage.upper().startswith("SAFE"):
            # SAFE-excluded wrong contracts still block re-add by addr
            if r.stage.upper() == "EXCLUDED":
                addrs.add(r.addr)
    return addrs


def next_queue_num(rows: list[QueueRow] | None = None) -> int:
    rows = rows if rows is not None else parse_queue()
    return max((r.num for r in rows), default=0) + 1


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


def update_queue_row(
    num: int,
    *,
    name: str | None = None,
    chain: str | None = None,
    addr: str | None = None,
    tvl: str | None = None,
    stage: str | None = None,
) -> QueueRow | None:
    text = _read()
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
        if len(cells) >= 6:
            try:
                n = int(cells[0])
            except ValueError:
                new_lines.append(line)
                continue
            if n == num:
                if name is not None:
                    cells[1] = name
                if chain is not None:
                    cells[2] = chain
                if addr is not None:
                    cells[3] = addr.lower()
                if tvl is not None:
                    cells[4] = tvl
                if stage is not None:
                    cells[5] = stage
                new_lines.append("| " + " | ".join(cells) + " |")
                updated = QueueRow(
                    num=n,
                    name=cells[1],
                    chain=cells[2],
                    addr=cells[3].lower(),
                    tvl=cells[4],
                    stage=cells[5],
                )
                continue
        new_lines.append(line)
    if updated is None:
        return None
    new_body = "\n".join(new_lines)
    if not new_body.endswith("\n"):
        new_body += "\n"
    _write(text[:sec_start] + "## QUEUE\n" + new_body + text[sec_end:])
    return updated


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
            new_lines.append("| " + " | ".join(cells) + " |")
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


def set_queue_comment(comment: str) -> None:
    """Insert/replace HTML comment under QUEUE header."""
    text = _read()
    sec_start, sec_end, body = _section(text, "QUEUE")
    lines = body.splitlines()
    # Drop existing HTML comments at top
    while lines and (not lines[0].strip() or lines[0].strip().startswith("<!--")):
        if lines[0].strip().startswith("<!--"):
            lines.pop(0)
        elif not lines[0].strip():
            lines.pop(0)
        else:
            break
    lines.insert(0, "")
    lines.insert(1, f"<!-- {comment} -->")
    lines.insert(2, "")
    new_body = "\n".join(lines)
    if not new_body.endswith("\n"):
        new_body += "\n"
    _write(text[:sec_start] + "## QUEUE\n" + new_body + text[sec_end:])


def append_excluded(
    name: str,
    chain: str,
    when: str | None = None,
    *,
    addr: str = "",
    note: str = "",
) -> None:
    when = when or date.today().isoformat()
    addr = addr.lower() if addr else ""
    text = _read()
    sec_start, sec_end, body = _section(text, "EXCLUDED")
    lines = body.rstrip("\n").splitlines()
    # Normalize header to 5-column form
    header = "| name | chain | addr | date | note |"
    sep = "|------|-------|------|------|------|"
    new_lines: list[str] = [""]
    new_lines.append(header)
    new_lines.append(sep)
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if not cells or cells[0].lower() in {"name", "---"} or set(cells[0]) <= {"-"}:
            continue
        # rewrite old rows into 5-col
        if len(cells) >= 5 and cells[2].startswith("0x"):
            new_lines.append(
                f"| {cells[0]} | {cells[1]} | {cells[2].lower()} | {cells[3]} | {cells[4]} |"
            )
        elif len(cells) >= 4 and not cells[2].startswith("0x"):
            new_lines.append(
                f"| {cells[0]} | {cells[1]} |  | {cells[2]} | {cells[3]} |"
            )
        elif len(cells) >= 3:
            new_lines.append(f"| {cells[0]} | {cells[1]} |  | {cells[2]} |  |")
        else:
            new_lines.append(f"| {cells[0]} | {cells[1]} |  |  |  |")
    new_lines.append(f"| {name} | {chain} | {addr} | {when} | {note} |")
    new_body = "\n".join(new_lines) + "\n\n"
    _write(text[:sec_start] + "## EXCLUDED\n" + new_body + text[sec_end:])


def print_queue_table(rows: list[QueueRow] | None = None) -> None:
    rows = rows if rows is not None else parse_queue()
    print("| # | name | chain | addr | tvl | stage |")
    print("|---|------|-------|------|-----|-------|")
    for r in rows:
        print(f"| {r.num} | {r.name} | {r.chain} | {r.addr} | {r.tvl} | {r.stage} |")
