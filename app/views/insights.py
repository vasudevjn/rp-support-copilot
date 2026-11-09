"""Insights & Quality: what the queue says (spikes, KB gaps, churn) and whether the copilot stayed safe
(spec cases, safety checks, guardrail retries, replies not sent)."""
import re

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from common import card, csv, esc, hbars, js, kpi_row, page_header, results, show, ticket_href
from triage.config import load_config
from triage.lookup import get_merchant

df = results()
n = len(df)
page_header("Insights & Quality")
tab_i, tab_d, tab_q = st.tabs(["Insights", "Decision Logic", "Quality"])

# ------------------------------------------------------------------ insights
with tab_i:

    # Payment-failure spikes: one bar per September day (zero days included), spike days in amber,
    # the config threshold as a dashed line. Data from spikes_daily.csv and spikes_repeat_merchants.csv.
    daily = csv("spikes_daily.csv")
    if daily is not None:
        thr = load_config()["spikes"]["daily_min_payment_failure_tickets"]
        created = pd.to_datetime(df.created_at, format="%d %b %Y %H:%M").dt.normalize()
        all_days = pd.date_range(created.min(), created.max(), freq="D")
        d = daily.assign(day=pd.to_datetime(daily.day)).set_index("day").reindex(all_days)
        d["n"] = d.payment_failure_tickets.fillna(0).astype(int)
        d["spike"] = d.n >= thr
        d["tickets"] = d.ticket_ids.fillna("").str.replace(" ", ", ")
        d["low"] = d.low_success_merchants.fillna("")
        fig = go.Figure(go.Bar(
            x=d.index.day, y=d.n, marker_color=["#E39A1B" if s else "#9DB2EE" for s in d.spike],
            text=[str(v) if v else "" for v in d.n], textposition="outside", cliponaxis=False,
            textfont=dict(size=12, color="#344054"),
            customdata=list(zip(d.tickets, d.low)),
            hovertemplate="%{x} Sep: %{y} payment-failure tickets<br>%{customdata[0]}"
                          "<br>Low-success merchants: %{customdata[1]}<extra></extra>"))
        fig.add_hline(y=thr, line_dash="dash", line_color="#B42318", line_width=1.5,
                      annotation_text=f"Spike threshold: {thr} a day", annotation_position="top right",
                      annotation_font=dict(size=12, color="#B42318"))
        fig.update_layout(height=380, margin=dict(l=10, r=10, t=30, b=10), plot_bgcolor="#fff", paper_bgcolor="#fff",
                          font=dict(family="Inter", color="#344054"), showlegend=False, bargap=0.25,
                          xaxis=dict(title="Day of September 2026", tickmode="linear", dtick=1, showgrid=False),
                          yaxis=dict(title="Tickets", dtick=1, gridcolor="#EEF1F5", rangemode="tozero",
                                     range=[0, max(int(d.n.max()), thr) + 1]))
        spikes = d[d.spike].sort_values("n", ascending=False)
        rep = csv("spikes_repeat_merchants.csv")
        left, right = st.columns([2, 1], gap="medium")
        with left:
            with st.container(border=True, key="card_pf"):
                show(f'<h2 style="margin:0;font-size:16px;font-weight:600">Payment Failure Tickets Per Day</h2>'
                     f'<p style="margin:4px 0 0;font-size:13px;color:#556070">{int(d.n.sum())} payment-failure tickets in September. '
                     f'Amber days reach the spike threshold of {thr} or more.</p>')
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
            if rep is not None and len(rep):
                rate_thr = load_config()["thresholds"]["success_rate_degradation_pct"]
                rows = "".join(
                    f'<div class="row"><div class="m"><b>{esc(r.merchant_id)}</b> '
                    f'<span style="color:#556070">· {esc((get_merchant(r.merchant_id) or {}).get("business_name", ""))}</span>'
                    f'<small>{r.total_pf_tickets} payment-failure tickets</small></div>'
                    f'<span class="pill" style="background:{"#FFE6D5" if float(r.success_rate_7d_pct) < rate_thr else "#DDF3EA"};'
                    f'color:{"#9A3412" if float(r.success_rate_7d_pct) < rate_thr else "#175C43"}">'
                    f'{float(r.success_rate_7d_pct):g}% success</span></div>' for r in rep.itertuples())
                show(card("Repeat Merchants", f'<div class="rows">{rows}</div>',
                          sub=f"Two or more payment-failure tickets within "
                              f"{load_config()['spikes']['repeat_window_days']} days. Below {rate_thr}% goes to Payments Ops."))
        with right:
            rows = "".join(
                f'<div class="row"><div class="m"><b>{day:%d %b}</b><small>{esc(r.tickets)}'
                + (f"<br>Low success: {esc(r.low)}" if r.low else "") + f'</small></div>'
                f'<span class="pill" style="background:#FFF1C2;color:#6E5200">{r.n} tickets</span></div>'
                for day, r in spikes.iterrows())
            show(card("Spike Days", f'<div class="rows">{rows}</div>' if rows else "<p>None this month.</p>"))

    a, b = st.columns(2, gap="medium")
    with a:
        kb = csv("kb_insights.csv")
        if kb is not None:
            rows = "".join(
                f'<div style="display:grid;grid-template-columns:64px minmax(0,1fr);gap:12px;padding:12px 0;'
                f'border-top:1px solid #E1E5EB"><b style="font-size:13px;color:#1F3FA8">{esc(r.kb_id)}</b>'
                f'<div><div style="font-size:14px;font-weight:600">{esc(r.topic)}</div><div style="font-size:13px;'
                f'color:#556070;line-height:1.5">{esc(r.notes or "Tickets needed a missing detail before acting.")}</div></div>'
                f'</div>'
                for r in kb[kb.improvement_score > 0].itertuples())
            show(card("KB Articles To Improve", rows))
        churn = df[df.churn_signal.astype(str) == "True"]
        rows = "".join(f'<a class="row" href="{ticket_href(r.ticket_id)}" target="_self"><div class="m"><b>'
                       f'{esc(r.ticket_id)}</b> <span style="color:#556070">· {esc(r.merchant_label)}</span>'
                       f'<small>{esc(r.summary)}</small></div></a>' for r in churn.itertuples())
        show(card("Churn Signals", f'<div class="rows">{rows}</div>'))
    with b:
        gaps = csv("kb_gaps.csv")
        if gaps is not None:
            rows = "".join(f'<a class="row" href="{ticket_href(r.ticket_id)}" target="_self"><div class="m"><b>'
                           f'{esc(r.ticket_id)}</b><small>{esc(r.merchant_message)}</small></div></a>'
                           for r in gaps.itertuples())
            show(card("Unsupported Queries", f'<div class="rows">{rows}</div>'))
        miss = df[df.action == "ask_info"].missing_fields.str.replace("_", " ").str.replace("details", "details")
        show(card("Why The Copilot Asked For More Information",
                  hbars([(k.capitalize(), int(v)) for k, v in miss.value_counts().items()], "#E39A1B", 200)))

# ------------------------------------------------------------------ decision logic
RULE_RE = re.compile(r"^(Rule \d+)(?: \(([^)]*)\))?:\s*(.*)")


def rule_rows(sub: pd.DataFrame) -> str:
    """One row per sub-case: the rule that fired, what triggered it, the team(s), the count and an example ticket.
    Everything is read from decision_trace in the outputs, so it shows what the rules actually did."""
    items = []
    for sc, g in sub.groupby("sub_case"):
        m = RULE_RE.match(g.decision_trace.iloc[0])
        rule, kb, text = (m.group(1), m.group(2) or "", m.group(3)) if m else ("", "", g.decision_trace.iloc[0])
        trigger = text.rstrip(".")
        if sc == "threat":
            types = sorted(t.replace("_", " ") for t in g.threat_type.unique())
            trigger = "threat detected: " + ", ".join(types)
        elif len(g) > 1:
            trigger = "e.g. " + trigger   # the example ticket's own trace; other tickets differ in the details
        teams = ", ".join(sorted(t for t in g.escalation_team.unique() if t)) or "Merchant"
        items.append((int(rule.split()[-1]) if rule else 99, rule, kb, trigger, teams, len(g), g.ticket_id.iloc[0]))
    return "".join(
        f'<div style="display:grid;grid-template-columns:72px minmax(0,1fr) 150px 44px;gap:14px;align-items:start;'
        f'padding:12px 0;border-top:1px solid #E1E5EB"><div><b style="font-size:13px">{esc(rule)}</b>'
        f'<div style="font-size:12px;color:#1F3FA8;font-weight:600">{esc(kb)}</div></div>'
        f'<div style="font-size:13px;color:#344054;line-height:1.5">{esc(trigger)}. '
        f'<a href="{ticket_href(ex)}" target="_self" style="color:#2B55D9;font-weight:600">Example {esc(ex)}</a></div>'
        f'<div style="font-size:13px;font-weight:600">{esc(teams)}</div>'
        f'<b style="text-align:right;font-variant-numeric:tabular-nums">{n}</b></div>'
        for _, rule, kb, trigger, teams, n, ex in sorted(items))


with tab_d:
    st.info("Rules run in priority order and the first match decides; the threat rule is always checked first. "
            "The model only reads the message and words the reply. Every row below is read from the decision "
            "trace of the 150-ticket run.")
    esc_t = df[df.action == "escalate"]
    show(card("When It Escalates", rule_rows(esc_t),
              sub=f"{len(esc_t)} tickets. Each gets a holding reply with no timeline; threats are never sent."))
    ask_t = df[df.action == "ask_info"]
    show(card("When Information Is Missing", rule_rows(ask_t),
              sub=f"{len(ask_t)} tickets. The reply asks for every missing field, and the checker confirms it does."))
    tones = df.tone.value_counts()
    upset = df[df.tone.isin(["frustrated", "angry"])]
    show(card("Angry Or Frustrated Merchants",
              hbars([(t.title(), int(tones.get(t, 0))) for t in ["calm", "frustrated", "angry"]], "#E39A1B", 120),
              sub=f"{len(upset)} upset merchants. {int((upset.send_mode == 'auto_send').sum())} of them were "
                  f"auto-sent; the rest go to an agent or are threats. Tone adds a short acknowledgement and "
                  f"raises risk by one level, but never changes the facts or the action."))

# ------------------------------------------------------------------ quality
with tab_q:
    res = js("eval_results.json")
    if res is None:
        st.warning("No evaluation yet. Run `python -m triage.evaluate`.")
        st.stop()
    st.info("Spec cases are expected outcomes written in the project spec before the build. They cover the risky "
            "paths on purpose, so they are not a random-sample accuracy estimate for the full queue. Safety checks "
            "run over all 150 tickets and count the brief's critical errors.")
    kpi_row([
        ("Spec Cases Passed", f"{res['spec_cases_all_pass']} / {res['spec_cases']}",
         f"{res['spec_checks_passed']} of {res['spec_checks']} checks"),
        ("Critical Errors", res["critical_errors"], "Across all 150 tickets"),
    ])
    st.write("")
    kpi_row([(f"{t} Checks", res[f"{k}_checks_passed"], "") for k, t in
             [("action", "Action"), ("team", "Team"), ("category", "Category"), ("risk", "Risk"), ("reply", "Reply")]])

    a, b = st.columns(2, gap="medium")
    with a:
        sc = csv("eval_safety_checks.csv")
        if sc is not None:
            rows = "".join(f'<div class="row"><div class="m" style="font-size:13px">{esc(r.check)}</div>'
                           f'<b style="color:{"#175C43" if str(r.failures) == "0" else "#B42318"}">{r.failures}</b></div>'
                           for r in sc.itertuples())
            show(card("Safety Checks", f'<div class="rows">{rows}</div>', sub="Target is zero failures on every check."))
        crit = df[df.risk_level == "Critical"].sort_values("ticket_id")
        rows = "".join(f'<a class="row" href="{ticket_href(r.ticket_id)}" target="_self"><div class="m"><b>{esc(r.ticket_id)}'
                       f'</b><small>{esc(r.summary)}</small></div><b style="font-size:13px">{esc(r.escalation_team)}</b></a>'
                       for r in crit.itertuples())
        show(card("Critical Tickets", f'<div class="rows">{rows}</div>',
                  sub=f"All {len(crit)} are escalated, marked do not send, and have a holding draft only."))
    with b:
        g = csv("guardrail_log.csv")
        retried = df[df.guardrail_status == "PASS_AFTER_RETRY"]
        rows = ""
        if g is not None:
            for r in retried.itertuples():
                first = g[(g.ticket_id == r.ticket_id) & (g.attempt == 1)]
                why = "; ".join(f"{c}: {v[6:]}" for c, v in first.iloc[0].items()
                                if isinstance(v, str) and v.startswith("FAIL")) if len(first) else ""
                rows += (f'<div class="row"><div class="m"><b>{esc(r.ticket_id)}</b><small>{esc(why)}</small></div>'
                         f'<b style="font-size:13px;color:#175C43">Passed on retry</b></div>')
        blocked = int((df.guardrail_status == "FAIL_NEEDS_HUMAN").sum())
        show(card("Guardrail Retries", f'<div class="rows">{rows}</div>' if rows else "<p>None on this run.</p>",
                  sub=f"{len(retried)} first drafts failed a check and were rewritten once. {blocked} are waiting "
                      f"for a human fix."))
        cases = csv("eval_spec_cases.csv")
        if cases is not None:
            rows = "".join(f'<div class="row"><div class="m"><b>{esc(r.ticket_id)}</b><small>{esc(r.note)}</small></div>'
                           f'<b style="font-size:13px;color:{"#175C43" if str(r.all_pass) == "True" else "#B42318"}">'
                           f'{r.passed}/{r.checks}</b></div>' for r in cases.itertuples())
            show(card("Spec Cases", f'<div class="rows">{rows}</div>'))

    misses = csv("eval_misses.csv")
    if misses is not None and not misses.empty:
        show('<p class="lbl" style="margin-top:16px">Failed Checks</p>')
        st.dataframe(misses, use_container_width=True, hide_index=True)

    show('<section class="card" style="margin-top:16px"><h2>Replies I Would Not Send</h2><p class="sub">Automatic blocks '
         'are threat drafts and replies that failed the checker twice. Human review rows are drafts rejected after '
         'reading them, with the reason; fixed ones stay listed as a record.</p></section>')
    ns = csv("replies_not_sent.csv")
    if ns is not None:
        for src, title in [("human review", "Human Review"), ("automatic", "Automatic Blocks")]:
            part = ns[ns.source == src]
            st.markdown(f"**{title}** · {len(part)}")
            st.dataframe(part.drop(columns=["source"]), use_container_width=True, hide_index=True,
                         column_config={"rejected_draft": st.column_config.TextColumn("Rejected draft", width="large"),
                                        "reason_not_sent": st.column_config.TextColumn("Reason", width="large"),
                                        "current_reply": st.column_config.TextColumn("Current reply", width="large")})
