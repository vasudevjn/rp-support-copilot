"""Merchant lookup and small date helpers used by the rules engine."""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np

from .load import load_merchants

_MERCHANTS: dict[str, dict] | None = None


def merchants() -> dict[str, dict]:
    global _MERCHANTS
    if _MERCHANTS is None:
        _MERCHANTS = load_merchants()
    return _MERCHANTS


def get_merchant(merchant_id: str | None) -> dict | None:
    if not merchant_id:
        return None
    return merchants().get(merchant_id)


def resolve_merchant_id(column_value: str | None, in_message: str | None) -> tuple[str | None, str | None]:
    """Prefer the ticket column; fall back to the ID in the message. Returns (id, note)."""
    if column_value and in_message and column_value != in_message:
        return column_value, f"Merchant ID mismatch: column {column_value}, message {in_message}; column used"
    return column_value or in_message, None


def business_days_elapsed(start: date, end: date) -> int:
    """Weekdays after `start` up to and including `end` (weekends excluded; bank holidays unknown)."""
    return int(np.busday_count(start + timedelta(days=1), end + timedelta(days=1)))


def inr(amount: float | int | None) -> str:
    """Format rupees in Indian digit grouping: 3400000 -> 'Rs 34,00,000'."""
    if amount is None:
        return ""
    n = int(round(float(amount)))
    s = str(n)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups) + "," + tail
    return f"Rs {s}"
