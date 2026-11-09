"""Shared helpers for the dashboard: data loaders and a small UI kit that follows the design mockup.

All triage logic is imported from src/triage, never reimplemented. Every number shown is read from outputs/.
"""
from __future__ import annotations

import base64
import html
import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:          # Streamlit Cloud runs without `pip install -e .`
    sys.path.insert(0, str(ROOT / "src"))

from triage.config import OUTPUTS  # noqa: E402
from triage.lookup import get_merchant  # noqa: E402

# Logo mark: a white support headset (outline, Lucide-style "headset" shape, ISC licensed).
# st.html strips inline <svg>, so the sidebar mark is embedded as an image data URI instead.
_HEADSET = ('<path d="M3 11h3a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-5Zm0 0a9 9 0 1 1 18 0m0 0v5a2 2 0 0 1-2 '
            '2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3Z"/><path d="M21 16v2a4 4 0 0 1-4 4h-5"/>')
_LOGO_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" '
             f'stroke-linecap="round" stroke-linejoin="round">{_HEADSET}</svg>')
LOGO_URI = "data:image/svg+xml;base64," + base64.b64encode(_LOGO_SVG.encode()).decode()
# Favicon: the same headset on the brand-blue rounded square, so the browser tab matches the sidebar logo.
FAVICON_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="7" '
               'fill="#2B55D9"/><g transform="translate(5 5) scale(0.9167)" fill="none" stroke="#fff" '
               f'stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">{_HEADSET}</g></svg>')

# Registry of st.Page objects, filled by streamlit_app.py before each run, so views can link to each other.
PAGES: dict = {}

# ------------------------------------------------------------------ labels and colours (from the mockup)

ACTION_LABELS = {"auto_resolve": "Auto-Resolve", "ask_info": "Ask For Info", "escalate": "Escalate"}
ACTION_COLORS = {"auto_resolve": "#2B55D9", "ask_info": "#E39A1B", "escalate": "#5B2A86"}
MODE_LABELS = {"auto_send": "Auto-Send", "agent_review": "Agent Review", "do_not_send": "Do Not Send"}
MODE_COLORS = {"auto_send": ("#DDF3EA", "#175C43"), "agent_review": ("#DCEBFB", "#1D4E89"),
               "do_not_send": ("#FDE0DD", "#8A1C13")}
RISK_ORDER = ["Critical", "High", "Medium", "Low"]
RISK_COLORS = {"Critical": ("#B42318", "#FFFFFF"), "High": ("#FFE6D5", "#9A3412"),
               "Medium": ("#FFF1C2", "#6E5200"), "Low": ("#EAEDF2", "#3F4A5A")}

CSS = """
<style>
:root{--ink:#101828;--ink2:#344054;--muted:#556070;--line:#E1E5EB;--soft:#EEF1F5;--page:#F4F6F9;--blue:#2B55D9}
[data-testid="stMainBlockContainer"]{max-width:1440px;padding:4rem 2rem 3rem !important}
[data-testid="stSidebar"] [data-testid="stSidebarContent"]{padding-top:.5rem}
[data-testid="stSidebar"] [data-testid="stPageLink"] a{min-height:44px;border-radius:8px;padding:0 12px}
[data-testid="stSidebar"] [data-testid="stPageLink"] a:hover{background:#1A2440}
[data-testid="stSidebar"] [data-testid="stPageLink"] p{font-size:14px;font-weight:500;color:#C9D1E0}
[data-testid="stSidebar"] [data-testid="stPageLink"] a[aria-current="page"] p,
[data-testid="stSidebar"] [data-testid="stPageLink"] a.active p{color:#fff;font-weight:600}
[class*="st-key-card"]{background:#fff;border:1px solid var(--line) !important;border-radius:12px;padding:20px}
.ph h1{margin:0;font-family:'Space Grotesk',Inter,sans-serif;font-size:30px;font-weight:600;letter-spacing:-.01em;color:var(--ink)}
.ph p{margin:6px 0 0;font-size:14px;color:var(--muted)}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(200px,100%),1fr));gap:16px}
.kpi{background:#fff;border:1px solid var(--line);border-radius:12px;padding:18px 20px;display:flex;flex-direction:column;gap:4px}
.kpi .l{font-size:13px;font-weight:500;color:var(--muted)}
.kpi .v{font-family:'Space Grotesk',Inter,sans-serif;font-size:36px;font-weight:600;line-height:1.1;color:var(--ink);font-variant-numeric:tabular-nums}
.kpi .n{font-size:13px;color:var(--muted)}
.kpi.hero{background:#EEF3FD;border-color:#C5D2F6}.kpi.hero .v{color:#1F3FA8}
.kpi.risk{background:#FEF3F2;border-color:#FBD3CF}.kpi.risk .v{color:#B42318}
.strip{display:flex;flex-wrap:wrap;align-items:center;gap:8px 20px;padding:12px 18px;border-radius:10px;font-size:14px;font-weight:600}
.strip.ok{background:#ECF8F3;border:1px solid #BFE6D4;color:#175C43}.strip.bad{background:#FEF3F2;border:1px solid #FBD3CF;color:#8A1C13}
.strip .dot{width:10px;height:10px;border-radius:50%;background:currentColor;flex:none}
.strip span.sep{color:#9AA4B2;font-weight:400}
.sbar{display:grid;grid-template-columns:var(--lw,140px) minmax(0,1fr) 34px;align-items:center;gap:12px;font-size:13px}
.sbar .t{display:flex;height:12px;border-radius:4px;overflow:hidden;gap:1px}
.sbar b{text-align:right;font-variant-numeric:tabular-nums}
.grp{font-size:12px;font-weight:600;color:var(--muted);letter-spacing:.06em;text-transform:uppercase;margin:6px 0 2px}
.card{background:#fff;border:1px solid var(--line);border-radius:12px;padding:22px 24px;display:flex;flex-direction:column;gap:14px;color:var(--ink)}
.card h2{margin:0;font-family:Inter,sans-serif;font-size:16px;font-weight:600;color:var(--ink)}
.card .sub{margin:-8px 0 0;font-size:13px;color:var(--muted)}
.card .foot{margin:0;font-size:13px;color:var(--muted);border-top:1px solid var(--line);padding-top:12px}
.lbl{font-size:12px;font-weight:600;color:var(--muted);letter-spacing:.06em;text-transform:uppercase;margin:0}
.pill{display:inline-block;font-size:12px;font-weight:600;padding:3px 10px;border-radius:999px;white-space:nowrap}
.chip{display:inline-block;font-size:12px;font-weight:600;padding:3px 10px;border-radius:6px;white-space:nowrap}
.bars{display:flex;flex-direction:column;gap:10px}
.bar{display:grid;grid-template-columns:var(--lw,140px) minmax(0,1fr) 34px;align-items:center;gap:12px;font-size:13px}
.bar span:first-child{color:var(--ink2)}
.bar .t{height:12px;background:var(--soft);border-radius:4px}.bar .f{height:12px;border-radius:4px}
.bar b{text-align:right;font-variant-numeric:tabular-nums}
.stack{display:flex;height:28px;border-radius:6px;overflow:hidden;gap:2px}
.legend{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:12px}
.legend div{display:flex;gap:8px;align-items:flex-start}.legend i{width:10px;height:10px;border-radius:2px;margin-top:5px;flex:none}
.legend b{display:block;font-size:14px}.legend small{font-size:13px;color:var(--muted)}
.rows{display:flex;flex-direction:column}
.row{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:8px 12px;padding:12px 8px;border-top:1px solid var(--line);border-radius:6px;color:var(--ink);text-decoration:none}
a.row:hover{background:var(--page)}
.row .m{min-width:0;flex:1 1 220px}.row .m b{font-size:14px;font-variant-numeric:tabular-nums}
.row .m small{display:block;font-size:13px;color:var(--muted);margin-top:2px}
.dl{display:grid;grid-template-columns:auto 1fr;gap:8px 16px;font-size:13px;margin:0}
.dl dt{color:var(--muted)}.dl dd{margin:0;font-weight:500;color:var(--ink)}
.msg{margin:0;padding:14px 16px;background:var(--page);border-radius:8px;font-size:15px;line-height:1.55;color:var(--ink)}
.meta{margin:0;font-size:13px;color:var(--muted)}
.qt{background:#fff;border:1px solid var(--line);border-radius:12px;overflow:auto;max-height:660px}
.qt .in{min-width:1040px}
.qt .h,.qt a{display:grid;grid-template-columns:76px 1.15fr 2.3fr 1.15fr 92px 112px 1.05fr 120px;gap:14px;align-items:center;padding:0 20px}
.qt .h{position:sticky;top:0;z-index:1;background:#fff;min-height:44px;border-bottom:1px solid var(--line);font-size:12px;font-weight:600;color:var(--muted);letter-spacing:.04em;text-transform:uppercase}
.qt a{min-height:60px;padding-top:8px;padding-bottom:8px;border-bottom:1px solid var(--soft);font-size:14px;color:var(--ink);text-decoration:none}
.qt a:hover{background:var(--page)}.qt a:last-child{border-bottom:0}
.qt .id{font-weight:600;font-variant-numeric:tabular-nums}
.qt .mu{color:var(--ink2);font-size:13px}
.qt .iss{color:var(--ink2);font-size:13px;line-height:1.45;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.qt a.crit{background:#FEF7F6}.qt a.crit:hover{background:#FDEEEC}
.qt .mid{display:block;font-size:12px;color:var(--muted);font-variant-numeric:tabular-nums}
.qt .act{display:inline-flex;align-items:center;gap:7px;font-size:13px;color:var(--ink2)}
.qt .act i{width:8px;height:8px;border-radius:50%;flex:none}
.qt .none{color:#9AA4B2;font-size:13px}
.qcount{font-size:13px;color:var(--muted);margin:0}.qcount b{color:var(--ink)}
.qt .empty{padding:40px 20px;text-align:center;font-size:14px;color:var(--muted)}
.reply{margin:0;padding:14px 16px;background:#F9FAFB;border:1px solid #CBD2DC;border-radius:8px;font-size:14px;line-height:1.6;white-space:pre-wrap;color:var(--ink)}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:12px}
.tile{padding:12px 14px;border-radius:8px;background:var(--page)}.tile small{font-size:12px;color:var(--muted)}
.tile div{font-size:14px;font-weight:600;margin-top:2px}
.big{font-family:'Space Grotesk',Inter,sans-serif;font-size:26px;font-weight:600;letter-spacing:-.01em}
.alert{display:flex;gap:14px;align-items:center;padding:16px 20px;border-radius:12px;background:#B42318;color:#fff}
.alert b{font-size:16px}.alert p{margin:2px 0 0;font-size:14px}
.checks{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:6px 12px;font-size:13px;color:var(--ink2)}
.checks li{display:flex;gap:8px;align-items:center}
.checks li::before{content:"";flex:none;width:8px;height:8px;border-radius:50%;background:#175C43}
.checks li.bad{color:#B42318;font-weight:600}.checks li.bad::before{background:#B42318}
.gauge{position:relative;height:12px;border-radius:6px;background:var(--soft)}
.gauge .f{position:absolute;left:0;top:0;bottom:0;border-radius:6px}
.gauge .th{position:absolute;top:-4px;bottom:-4px;width:2px;background:var(--ink)}
.steps{list-style:none;margin:0;padding:0}.steps li{display:flex;gap:14px;padding:12px 0;border-top:1px solid var(--line)}
.steps span{flex:0 0 24px;height:24px;border-radius:50%;background:#E8EEFD;color:#1F3FA8;font-size:12px;font-weight:700;display:flex;align-items:center;justify-content:center}
.steps b{font-size:14px}.steps p{margin:2px 0 0;font-size:13px;color:var(--muted);line-height:1.5}
</style>
"""


def esc(v) -> str:
    """HTML-escape any value from the data before it goes into markup."""
    return html.escape("" if v is None else str(v))


def inject_css() -> None:
    st.html(CSS)


def sidebar() -> None:
    """Dark sidebar: brand and nav links. Ticket Workspace opens from the queue, so it is not listed."""
    with st.sidebar:
        st.html(f"""<div style="display:flex;align-items:center;gap:12px;padding:8px 8px 20px">
<div style="width:32px;height:32px;border-radius:8px;background:#2B55D9;display:flex;align-items:center;justify-content:center">
<img src="{LOGO_URI}" width="20" height="20" alt=""></div>
<div style="font-family:'Space Grotesk',Inter,sans-serif;font-weight:600;font-size:15px;line-height:1.25;color:#fff">Support<br>Copilot</div></div>""")
        for key, label, icon in [("overview", "Overview", ":material/dashboard:"),
                                 ("queue", "Ticket Queue", ":material/inbox:"),
                                 ("insights", "Insights & Quality", ":material/insights:"),
                                 ("try_it", "Try It", ":material/science:")]:
            st.page_link(PAGES[key], label=label, icon=icon)


def page_header(title: str, subtitle: str = "") -> None:
    st.html(f'<div class="ph"><h1>{esc(title)}</h1>' + (f"<p>{esc(subtitle)}</p>" if subtitle else "") + "</div>")


def kpi_row(items: list[tuple]) -> None:
    """items: (label, value, note)."""
    st.html('<div class="kpis">' + "".join(
        f'<div class="kpi"><div class="l">{esc(l)}</div><div class="v">{esc(v)}</div><div class="n">{esc(n)}</div></div>'
        for l, v, n in items) + "</div>")


def card(title: str, body: str, sub: str = "", foot: str = "") -> str:
    """A white card. body is trusted HTML built by these helpers; title, sub and foot are escaped."""
    return (f'<section class="card"><h2>{esc(title)}</h2>' + (f'<p class="sub">{esc(sub)}</p>' if sub else "")
            + body + (f'<p class="foot">{esc(foot)}</p>' if foot else "") + "</section>")


def show(markup: str) -> None:
    st.html(markup)


def risk_pill(level: str) -> str:
    bg, fg = RISK_COLORS.get(level, ("#EAEDF2", "#3F4A5A"))
    return f'<span class="pill" style="background:{bg};color:{fg}">{esc(level)}</span>'


def mode_chip(mode: str) -> str:
    bg, fg = MODE_COLORS.get(mode, ("#EAEDF2", "#3F4A5A"))
    return f'<span class="chip" style="background:{bg};color:{fg}">{esc(MODE_LABELS.get(mode, mode))}</span>'


def chip(text: str) -> str:
    return f'<span class="chip" style="background:#EAEDF2;color:#3F4A5A">{esc(text)}</span>'


def hbars(rows: list[tuple], color: str = "#2B55D9", label_w: int = 140) -> str:
    """Labelled horizontal bars: rows of (label, count)."""
    top = max([n for _, n in rows] or [1]) or 1
    return f'<div class="bars" style="--lw:{label_w}px">' + "".join(
        f'<div class="bar"><span>{esc(l)}</span><div class="t"><div class="f" style="width:{n / top * 100:.0f}%;'
        f'background:{color}"></div></div><b>{n}</b></div>' for l, n in rows) + "</div>"


def stacked(parts: list[tuple], total: int) -> str:
    """One stacked bar plus legend: parts of (label, count, colour)."""
    aria = ", ".join(f"{n} {l}" for l, n, _ in parts)
    bar = "".join(f'<div style="flex:{n} 1 0;background:{c}"></div>' for _, n, c in parts if n)
    leg = "".join(f'<div><i style="background:{c}"></i><span><b>{esc(l)}</b><small>{n} tickets, '
                  f'{n / total:.0%}</small></span></div>' for l, n, c in parts)
    return f'<div class="stack" role="img" aria-label="{esc(aria)}">{bar}</div><div class="legend">{leg}</div>'


def dl(pairs: list[tuple]) -> str:
    return '<dl class="dl">' + "".join(f"<dt>{esc(k)}</dt><dd>{esc(v)}</dd>" for k, v in pairs) + "</dl>"


def ticket_href(tid: str) -> str:
    return f"workspace?t={esc(tid)}"


def open_ticket(tid: str) -> None:
    """Jump to the Ticket Workspace for one ticket."""
    st.session_state["ticket"] = tid
    st.switch_page(PAGES["workspace"])


# ------------------------------------------------------------------ data

@st.cache_data
def results() -> pd.DataFrame:
    p = OUTPUTS / "triage_results.csv"
    if not p.exists():
        st.error("No outputs yet. Run `python -m triage.pipeline` first.")
        st.stop()
    df = pd.read_csv(p, keep_default_na=False, dtype=str)
    df["merchant_name"] = df.merchant_id.map(lambda m: (get_merchant(m) or {}).get("business_name", "") if m else "")
    df["merchant_label"] = df.apply(lambda r: r.merchant_name or "No merchant ID", axis=1)
    df["risk_rank"] = df.risk_level.map({r: i for i, r in enumerate(RISK_ORDER)})
    return df


@st.cache_data
def csv(name: str) -> pd.DataFrame | None:
    p = OUTPUTS / name
    return pd.read_csv(p, keep_default_na=False) if p.exists() else None


@st.cache_data
def js(name: str) -> dict | None:
    p = OUTPUTS / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
