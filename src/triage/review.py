"""Human review: drafts Vasudev rejected, read from docs/replies_rejected.md.

The file is a markdown table with columns: Tickets | Rejected draft (excerpt) | Reason | Status.
- Status "open": the current draft is still rejected, so the pipeline sets send_mode = do_not_send.
- Status "fixed": the cause was fixed (template, prompt or rule); the row is kept as a record only.

This is review data written by a person, not decision logic: no rule reads ticket IDs from here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .config import ROOT

REVIEW_FILE = ROOT / "docs" / "replies_rejected.md"
TICKET_RE = re.compile(r"T-\d{4}")


@dataclass
class Rejection:
    tickets: list[str]
    excerpt: str
    reason: str
    status: str          # "open" or "fixed"


def load_rejections() -> list[Rejection]:
    """Parse every table row whose first cell names at least one ticket ID."""
    if not REVIEW_FILE.exists():
        return []
    out = []
    for line in REVIEW_FILE.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4:
            continue
        tickets = TICKET_RE.findall(cells[0])
        if not tickets:
            continue
        out.append(Rejection(tickets, cells[1], cells[2], cells[3].lower()))
    return out


def open_rejections() -> dict[str, str]:
    """ticket_id -> reason, for rejections still open."""
    return {t: r.reason for r in load_rejections() if r.status == "open" for t in r.tickets}
