"""Overview: headline results, safety status, what needs a person first, and where tickets go."""
import streamlit as st

from common import (ACTION_COLORS, ACTION_LABELS, MODE_COLORS, MODE_LABELS, PAGES, card, chip, esc, js,
                    page_header, results, risk_pill, show, stacked, ticket_href)

df = results()
n = len(df)
acts = df.action.value_counts()
modes = df.send_mode.value_counts()
chan = df.channel.value_counts()
is_threat = df.threat_type != "none"
threats = int(is_threat.sum())
held = int((is_threat & (df.action == "escalate") & (df.send_mode == "do_not_send")).sum())
blocked = int((df.guardrail_status == "FAIL_NEEDS_HUMAN").sum())
safe_auto = int(((df.action == "auto_resolve") & (df.send_mode == "auto_send")).sum())
needs_person = int((df.send_mode != "auto_send").sum())
crit_errors = (js("eval_results.json") or {}).get("critical_errors")

page_header("Overview")

# 1. Four headline tiles: the hero result (blue tint) and the riskiest fact (red tint) stand out.
tiles = [
    ("", "Tickets Triaged", n, ", ".join(f"{k} {v}" for k, v in chan.items())),
    ("hero", "Safe Auto-Resolve", f"{safe_auto / n:.0%}", f"{safe_auto} tickets can go out with no agent"),
    ("", "Needs A Person", needs_person,
     f"{int(modes.get('agent_review', 0))} agent review, {int(modes.get('do_not_send', 0))} do not send"),
    ("risk", "Threats Caught", threats, "Escalated, Critical, never auto-sent"),
]
show('<div class="kpis">' + "".join(
    f'<div class="kpi {cls}"><div class="l">{esc(l)}</div><div class="v">{esc(v)}</div><div class="n">{esc(note)}</div></div>'
    for cls, l, v, note in tiles) + "</div>")

# 2. Safety status strip: green only when every safety number is clean.
ok = crit_errors == 0 and held == threats and blocked == 0
parts = [f"{crit_errors if crit_errors is not None else 'n/a'} critical errors",
         f"{held} of {threats} threats held", f"{blocked} replies blocked"]
show(f'<div class="strip {"ok" if ok else "bad"}" style="margin-top:16px"><i class="dot"></i>'
     + '<span class="sep">·</span>'.join(f"<span>{esc(p)}</span>" for p in parts) + "</div>")
st.write("")

left, right = st.columns([1.25, 1], gap="medium")

# 4. Needs Attention First, grouped so high-risk tickets show as well as threats.
with left:
    def rows_for(sub, k=4):
        return "".join(
            f'<a class="row" href="{ticket_href(r.ticket_id)}" target="_self"><div class="m"><b>{esc(r.ticket_id)}</b> '
            f'<span style="font-weight:500;color:#556070">· {esc(r.merchant_label)}</span>'
            f'<small>{esc(r.summary)}</small></div><div style="display:flex;gap:8px;align-items:center">'
            f'{chip(r.escalation_team or ACTION_LABELS[r.action])}{risk_pill(r.risk_level)}</div></a>'
            for r in sub.sort_values("ticket_id").head(k).itertuples())

    crit = df[df.risk_level == "Critical"]
    high = df[df.risk_level == "High"]
    body = (f'<p class="grp">Threats · {len(crit)}</p><div class="rows">{rows_for(crit)}</div>'
            f'<p class="grp" style="margin-top:12px">High Risk · {len(high)}</p><div class="rows">{rows_for(high)}</div>')
    show(card("Needs Attention First", body,
              foot="Critical tickets are threats. The copilot only drafts a holding reply and never sends it."))
    if st.button(f"See All {needs_person} Needing Review In The Queue", icon=":material/arrow_forward:"):
        st.session_state["queue_preset"] = "Needs Review"
        st.switch_page(PAGES["queue"])

with right:
    # 3. One card for the two-step story: what the copilot decided, then who sends the reply.
    act_bar = stacked([(ACTION_LABELS[a], int(acts.get(a, 0)), ACTION_COLORS[a]) for a in ACTION_LABELS], n)
    mode_bar = stacked([(MODE_LABELS[m], int(modes.get(m, 0)), MODE_COLORS[m][1]) for m in MODE_LABELS], n)
    show(card("What Happens To Each Ticket",
              f'<p class="grp">Action</p>{act_bar}<p class="grp" style="margin-top:8px">Who Sends</p>{mode_bar}',
              foot="Auto-Send replies passed every guardrail and are calm in tone. Everything else needs a person."))

    # 6. Category bars split by action, so it is clear where escalations come from.
    ct = df.groupby(["category", "action"]).size().unstack(fill_value=0)
    ct = ct.loc[ct.sum(axis=1).sort_values(ascending=False).index]
    top = int(ct.sum(axis=1).max())
    bars = "".join(
        f'<div class="sbar"><span style="color:#344054">{esc(cat)}</span><div class="t" style="width:{row.sum() / top * 100:.0f}%">'
        + "".join(f'<div style="flex:{int(row.get(a, 0))} 1 0;background:{ACTION_COLORS[a]}" '
                  f'title="{esc(ACTION_LABELS[a])}: {int(row.get(a, 0))}"></div>' for a in ACTION_LABELS if row.get(a, 0))
        + f'</div><b>{int(row.sum())}</b></div>' for cat, row in ct.iterrows())
    legend = "".join(f'<span style="display:inline-flex;align-items:center;gap:6px;margin-right:14px;font-size:12px;'
                     f'color:#344054"><i style="width:10px;height:10px;border-radius:2px;background:{ACTION_COLORS[a]}"></i>'
                     f'{esc(ACTION_LABELS[a])}</span>' for a in ACTION_LABELS)
    show(card("Tickets By Category", f'<div>{legend}</div><div class="bars">{bars}</div>'))
