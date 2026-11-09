"""Payment-failure spike detection across tickets (stretch goal).

Two signals, thresholds in config:
1. Days with many Payment Failure tickets.
2. Merchants raising repeat Payment Failure tickets within a short window.
"""
from __future__ import annotations

import pandas as pd

from .config import OUTPUTS, load_config
from .lookup import get_merchant


def payment_failure_tickets(df: pd.DataFrame) -> pd.DataFrame:
    pf = df[df.category == "Payment Failure"].copy()
    pf["created_dt"] = pd.to_datetime(pf["created_at"], format="%d %b %Y %H:%M")
    pf["day"] = pf["created_dt"].dt.date
    return pf


def daily_counts(df: pd.DataFrame) -> pd.DataFrame:
    """Payment Failure tickets per day for every day in the ticket range (zeros included)."""
    all_days = pd.to_datetime(df["created_at"], format="%d %b %Y %H:%M").dt.date
    days = pd.date_range(min(all_days), max(all_days)).date
    pf = payment_failure_tickets(df)
    counts = pf.groupby("day").size().reindex(days, fill_value=0)
    thr = load_config()["spikes"]["daily_min_payment_failure_tickets"]
    out = pd.DataFrame({"day": days, "payment_failure_tickets": counts.values})
    out["flagged"] = out.payment_failure_tickets >= thr
    out["ticket_ids"] = [" ".join(pf[pf.day == d].ticket_id) for d in days]
    out["low_success_merchants"] = [
        " ".join(sorted({m for m in pf[pf.day == d].merchant_id
                         if (get_merchant(m) or {}).get("payment_success_rate_7d_pct", 100)
                         < load_config()["thresholds"]["success_rate_degradation_pct"]}))
        for d in days]
    return out


def repeat_merchants(df: pd.DataFrame) -> pd.DataFrame:
    cfg = load_config()["spikes"]
    pf = payment_failure_tickets(df)
    pf = pf[pf.merchant_id != ""].sort_values("created_dt")
    rows = []
    for mid, g in pf.groupby("merchant_id"):
        times = list(g.created_dt)
        best = 1
        for i in range(len(times)):
            n = sum(1 for t in times[i:] if (t - times[i]).days <= cfg["repeat_window_days"])
            best = max(best, n)
        if best >= cfg["repeat_min_tickets"]:
            m = get_merchant(mid) or {}
            rows.append({"merchant_id": mid, "tickets_in_window": best, "total_pf_tickets": len(g),
                         "ticket_ids": " ".join(g.ticket_id),
                         "first": g.created_at.iloc[0], "last": g.created_at.iloc[-1],
                         "success_rate_7d_pct": m.get("payment_success_rate_7d_pct")})
    return pd.DataFrame(rows, columns=["merchant_id", "tickets_in_window", "total_pf_tickets", "ticket_ids",
                                       "first", "last", "success_rate_7d_pct"]) \
        .sort_values(["tickets_in_window", "merchant_id"], ascending=[False, True])


def write(df: pd.DataFrame) -> None:
    daily = daily_counts(df).assign(signal="daily_count")
    rep = repeat_merchants(df).assign(signal="repeat_merchant")
    daily.to_csv(OUTPUTS / "spikes_daily.csv", index=False)
    rep.to_csv(OUTPUTS / "spikes_repeat_merchants.csv", index=False)
    flagged = daily[daily.flagged][["signal", "day", "payment_failure_tickets", "ticket_ids", "low_success_merchants"]]
    flagged = flagged.rename(columns={"day": "key", "payment_failure_tickets": "count"})
    rep2 = rep.rename(columns={"merchant_id": "key", "tickets_in_window": "count"})[
        ["signal", "key", "count", "ticket_ids", "success_rate_7d_pct"]]
    pd.concat([flagged, rep2], ignore_index=True).to_csv(OUTPUTS / "spikes.csv", index=False)
