"""Ticket Queue: every ticket in one table. Tabs and filters narrow the same list; clicking a ticket opens it
in the Ticket Workspace. Export To Excel downloads all tickets."""
from io import BytesIO

import pandas as pd
import streamlit as st

from common import (ACTION_COLORS, ACTION_LABELS, RISK_ORDER, chip, esc, mode_chip, page_header, results, risk_pill,
                    show, ticket_href)

df = results()


@st.cache_data
def excel_export(data: pd.DataFrame) -> bytes:
    """All tickets as an xlsx with the brief's output columns."""
    out = pd.DataFrame({
        "Ticket ID": data.ticket_id,
        "Category": data.category,
        "Action": data.action.map(ACTION_LABELS),
        "Escalation Team": data.escalation_team,
        "Risk Level": data.risk_level,
        "Drafted Reply": data.drafted_reply,
    })
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        out.to_excel(xw, sheet_name="Tickets", index=False)
    return buf.getvalue()


head, exp = st.columns([4, 1], vertical_alignment="bottom")
with head:
    page_header("Ticket Queue", "Select a ticket to review the recommendation and the drafted reply.")
with exp:
    st.download_button("Export To Excel", excel_export(df), "triage_tickets.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       icon=":material/download:", use_container_width=True, type="primary")

VIEWS = {
    "All Tickets": df.index == df.index,
    "Needs Review": df.send_mode != "auto_send",
    "Escalations": df.action == "escalate",
    "Awaiting Information": df.action == "ask_info",
    "Auto-Send": df.send_mode == "auto_send",
}
labels = {f"{k}  {int(m.sum())}": k for k, m in VIEWS.items()}
preset = st.session_state.pop("queue_preset", None)   # set by the Overview's "See All ... Needing Review" button
if preset in VIEWS:
    st.session_state["queue_view"] = next(lbl for lbl, k in labels.items() if k == preset)
picked = st.segmented_control("View", list(labels), label_visibility="collapsed", key="queue_view",
                              default=None if "queue_view" in st.session_state else list(labels)[0])
view_name = labels.get(picked or list(labels)[0])

FILTER_KEYS = {"q": "", "f_cat": "All", "f_risk": "All", "f_act": "All", "f_lang": "All"}


def clear_filters() -> None:
    for k, default in FILTER_KEYS.items():
        st.session_state[k] = default


# Send Mode is not a filter here: the Needs Review and Auto-Send tabs already cover it.
c = st.columns([2.8, 1.3, 1, 1.2, 1, 0.9], vertical_alignment="bottom")
q = c[0].text_input("Search", placeholder="Ticket, merchant or words in the message", key="q")
cat = c[1].selectbox("Category", ["All"] + sorted(df.category.unique()), key="f_cat")
risk = c[2].selectbox("Risk", ["All"] + RISK_ORDER, key="f_risk")
act = c[3].selectbox("Action", ["All"] + list(ACTION_LABELS.values()), key="f_act")
lang = c[4].selectbox("Language", ["All"] + sorted(df.language.unique()), key="f_lang")
active = any(st.session_state.get(k, d) != d for k, d in FILTER_KEYS.items())
c[5].button("Clear", on_click=clear_filters, disabled=not active, use_container_width=True,
            icon=":material/filter_alt_off:")

v = df[VIEWS[view_name]]
if cat != "All":
    v = v[v.category == cat]
if risk != "All":
    v = v[v.risk_level == risk]
if act != "All":
    v = v[v.action.map(ACTION_LABELS) == act]
if lang != "All":
    v = v[v.language == lang]
if q:
    hay = (v.ticket_id + " " + v.merchant_id + " " + v.merchant_name + " " + v.merchant_message + " " + v.summary)
    v = v[hay.str.contains(q, case=False, regex=False)]
v = v.sort_values(["risk_rank", "ticket_id"])

# A styled list rather than a spreadsheet grid. Each row links to the ticket's Workspace page.
# Accents match the Overview: threat rows are tinted red, actions carry their outcome colour, teams are chips.
show(f'<p class="qcount"><b>{len(v)}</b> of {len(df)} tickets · sorted by risk, then ticket number</p>')
rows = "".join(
    f'<a href="{ticket_href(r.ticket_id)}" target="_self" class="{"crit" if r.risk_level == "Critical" else ""}">'
    f'<span class="id">{esc(r.ticket_id)}</span>'
    f'<span>{esc(r.merchant_label)}<span class="mid">{esc(r.merchant_id)}</span></span>'
    f'<span class="iss">{esc(r.summary)}</span>'
    f'<span class="mu">{esc(r.category)}</span>'
    f'<span>{risk_pill(r.risk_level)}</span>'
    f'<span class="act"><i style="background:{ACTION_COLORS[r.action]}"></i>{esc(ACTION_LABELS[r.action])}</span>'
    f'<span>{chip(r.escalation_team) if r.escalation_team else "<span class=none>None</span>"}</span>'
    f'<span>{mode_chip(r.send_mode)}</span></a>'
    for r in v.itertuples())
show('<div class="qt"><div class="in"><div class="h"><span>Ticket</span><span>Merchant</span><span>Issue</span>'
     '<span>Category</span><span>Risk</span><span>Action</span><span>Team</span><span>Send Mode</span></div>'
     + (rows or '<div class="empty">No tickets match these filters.</div>') + '</div></div>')
