"""Read the P1 tabs of the Data Pack."""
from __future__ import annotations

import hashlib
from datetime import datetime

import pandas as pd

from .config import ROOT, load_config

DATE_FMT = "%d %b %Y"


def data_path():
    return ROOT / load_config()["data"]["path"]


def _clean(v):
    """Turn pandas NaN into None so downstream code sees plain Python values."""
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


def load_tickets() -> pd.DataFrame:
    cfg = load_config()["data"]
    df = pd.read_excel(data_path(), sheet_name=cfg["tickets_sheet"], dtype=str)
    df["merchant_id"] = pd.Series([v if isinstance(v, str) and v.strip() else None
                                   for v in df["merchant_id"]], dtype=object, index=df.index)
    df["created_dt"] = pd.to_datetime(df["created_at"], format="%d %b %Y %H:%M")
    return df


def load_merchants() -> dict[str, dict]:
    """Return merchants keyed by merchant_id, NaN cleaned to None."""
    cfg = load_config()["data"]
    df = pd.read_excel(data_path(), sheet_name=cfg["merchants_sheet"])
    out = {}
    for rec in df.to_dict(orient="records"):
        rec = {k: _clean(v) for k, v in rec.items()}
        out[rec["merchant_id"]] = rec
    return out


def load_kb() -> dict[str, dict]:
    cfg = load_config()["data"]
    df = pd.read_excel(data_path(), sheet_name=cfg["kb_sheet"], dtype=str)
    return {r["kb_id"]: r for r in df.to_dict(orient="records")}


def data_hash() -> str:
    return hashlib.sha256(data_path().read_bytes()).hexdigest()


def parse_date(s: str | None) -> datetime | None:
    return datetime.strptime(s, DATE_FMT) if s else None
