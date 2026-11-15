"""
Fraud detection command center.

Every visual on this page is computed from the fraud log and the ledger:
the threat gauge, the accepted / flagged / rejected split, the activity
timeline, and the ranking of wallets by accumulated risk.
"""

import time
from datetime import datetime

import streamlit as st

import config
from security import Severity
from ui import viz
from ui.components import (
    alert_feed,
    bars,
    chart,
    fmt_amount,
    fmt_time,
    gauge,
    page_header,
    party_label,
    party_name,
    section,
    short,
    stat_row,
    table,
)
from ui.theme import ACCENT, BAD, OK, SEVERITY_COLORS, WARN

THREAT_WINDOW_MINUTES = 60


def _threat(alerts: list[dict]) -> tuple[int, str, str, str]:
    """Threat score (0-100) from the alerts of the last hour, with a label, text and colour."""
    cutoff = time.time() - THREAT_WINDOW_MINUTES * 60
    recent = [a for a in alerts if a["created_at"] >= cutoff]
    score = min(100, sum(Severity.SCORES.get(a["severity"], 0) for a in recent))
    if score >= 80:
        label, color = "CRITICAL", BAD
    elif score >= 50:
        label, color = "ELEVATED", "#fb923c"
    elif score >= 20:
        label, color = "GUARDED", WARN
    else:
        label, color = "NORMAL", OK
    text = (f"{len(recent)} alert(s) in the last {THREAT_WINDOW_MINUTES} minutes. Score = sum of severity "
            f"weights (LOW 10, MEDIUM 30, HIGH 50, CRITICAL 100), capped at 100.")
    return score, label, text, color


def _suspicious_wallets(alerts: list[dict], book: dict[str, str]) -> list[dict]:
    """Wallets ranked by the total severity weight of the alerts naming them as sender."""
    totals: dict[str, dict] = {}
    for alert in alerts:
        if not alert["sender"]:
            continue
        entry = totals.setdefault(alert["sender"], {"score": 0, "count": 0, "worst": Severity.LOW})
        entry["score"] += Severity.SCORES.get(alert["severity"], 0)
        entry["count"] += 1
        if Severity.ORDER.index(alert["severity"]) > Severity.ORDER.index(entry["worst"]):
            entry["worst"] = alert["severity"]
    ranked = sorted(totals.items(), key=lambda item: item[1]["score"], reverse=True)[:6]
    top = ranked[0][1]["score"] if ranked else 1
    return [
        {
            "label": f"{party_name(address, book)} · worst {entry['worst']}",
            "value": f"{entry['count']} alert(s) · risk {entry['score']}",
            "fraction": entry["score"] / top,
            "tone": SEVERITY_COLORS.get(entry["worst"], ACCENT),
        }
        for address, entry in ranked
    ]


def render(node) -> None:
    page_header(
        "Fraud Detection Command Center",
        "Suspicious behaviour and rejected attacks, monitored continuously and recorded permanently in the fraud log.",
        eyebrow="Security operations",
    )

    alerts = node.get_alerts()
    book = node.address_book()
    counts = {level: sum(1 for a in alerts if a["severity"] == level) for level in Severity.ORDER}
    flagged, rejected = viz.classify_transactions(node)
    payments = [h for h in node.get_history() if not h["tx"].is_coinbase]
    clean = sum(1 for h in payments if h["tx"].tx_id not in flagged)

    tab_center, tab_feed, tab_log, tab_rules = st.tabs(["Command center", "Alert feed", "Full log", "Detection rules"])

    # ----- command center ---------------------------------------------------------
    with tab_center:
        score, label, text, color = _threat(alerts)
        left, right = st.columns([2, 3])
        with left:
            gauge(score, f"Threat level: {label}", text, tone=color)
        with right:
            stat_row([
                {"label": "Accepted", "value": clean, "hint": "Payments with no medium+ alert", "tone": "ok"},
                {"label": "Flagged", "value": len(flagged), "hint": "Accepted but suspicious",
                 "tone": "warn" if flagged else ""},
                {"label": "Rejected", "value": len(rejected), "hint": "Blocked by the node",
                 "tone": "bad" if rejected else ""},
            ])

        stat_row([
            {"label": "Critical", "value": counts[Severity.CRITICAL], "hint": "Forged signatures, chain tampering",
             "tone": "bad" if counts[Severity.CRITICAL] else ""},
            {"label": "High", "value": counts[Severity.HIGH], "hint": "Large transfers, velocity, double spends",
             "tone": "warn" if counts[Severity.HIGH] else ""},
            {"label": "Medium", "value": counts[Severity.MEDIUM], "hint": "Balance drains, overspending"},
            {"label": "Low", "value": counts[Severity.LOW], "hint": "First-time recipients"},
        ])

        if not alerts:
            st.caption("The fraud log is empty. Use the Attack Lab or send a large payment to trigger alerts.")
        else:
            left, right = st.columns([3, 2])
            with left:
                section("Fraud activity timeline")
                rows = [
                    {"Time": datetime.fromtimestamp(a["created_at"]).strftime("%Y-%m-%dT%H:%M:%S"),
                     "Severity": a["severity"], "Rule": a["rule"].replace("_", " ").title(), "Alerts": 1}
                    for a in alerts
                ]
                chart(
                    rows,
                    {
                        "mark": {"type": "bar", "size": 14},
                        "encoding": {
                            "x": {"field": "Time", "type": "temporal", "timeUnit": "yearmonthdatehoursminutes",
                                  "axis": {"title": "Time (per minute)", "format": "%H:%M", "labelAngle": 0}},
                            "y": {"aggregate": "sum", "field": "Alerts", "type": "quantitative",
                                  "axis": {"title": "Alerts", "tickMinStep": 1}},
                            "color": {"field": "Severity", "type": "nominal",
                                      "scale": {"domain": Severity.ORDER,
                                                "range": [SEVERITY_COLORS[level] for level in Severity.ORDER]},
                                      "legend": {"title": None}},
                            "order": {"field": "Severity"},
                            "tooltip": [
                                {"field": "Time", "type": "temporal", "timeUnit": "yearmonthdatehoursminutes",
                                 "title": "Minute", "format": "%Y-%m-%d %H:%M"},
                                {"field": "Severity", "title": "Severity"},
                                {"aggregate": "sum", "field": "Alerts", "title": "Alerts"},
                            ],
                        },
                    },
                    height=230,
                )
                section("Alerts by rule")
                rule_counts: dict[str, int] = {}
                for a in alerts:
                    name = a["rule"].replace("REJECTED_", "Rejected: ").replace("_", " ").title()
                    rule_counts[name] = rule_counts.get(name, 0) + 1
                chart(
                    [{"Rule": name, "Alerts": count} for name, count in rule_counts.items()],
                    {
                        "mark": {"type": "bar", "cornerRadiusEnd": 5, "height": 14,
                                 "color": {"x1": 0, "y1": 0, "x2": 1, "y2": 0, "gradient": "linear",
                                           "stops": [{"offset": 0, "color": "#3b82f6"}, {"offset": 1, "color": "#22d3ee"}]}},
                        "encoding": {
                            "y": {"field": "Rule", "type": "nominal", "sort": "-x",
                                  "axis": {"title": None, "labelLimit": 220}},
                            "x": {"field": "Alerts", "type": "quantitative", "axis": {"title": "Alerts", "tickMinStep": 1}},
                            "tooltip": [{"field": "Rule"}, {"field": "Alerts"}],
                        },
                    },
                    height=max(120, 30 * len(rule_counts)),
                )
            with right:
                section("Wallets by accumulated risk")
                ranking = _suspicious_wallets(alerts, book)
                if ranking:
                    bars(ranking)
                else:
                    st.caption("No wallet is named in the fraud log.")
                section("Latest alerts")
                alert_feed(alerts[:4], book)

    # ----- alert feed -------------------------------------------------------------
    with tab_feed:
        col1, col2 = st.columns(2)
        # An empty filter means "show everything".
        levels = col1.multiselect("Severity", Severity.ORDER, key="fraud_levels", placeholder="All severities")
        rule_names = sorted({a["rule"] for a in alerts})
        chosen_rules = col2.multiselect("Rule", rule_names, key="fraud_rules", placeholder="All rules",
                                        format_func=lambda r: r.replace("_", " ").title())
        visible = [
            a for a in alerts
            if (not levels or a["severity"] in levels) and (not chosen_rules or a["rule"] in chosen_rules)
        ]
        if not alerts:
            st.caption("The fraud log is empty. Try the Attack Lab to trigger some alerts.")
        elif not visible:
            st.caption("No alerts match these filters.")
        else:
            alert_feed(visible[:50], book)
        if len(visible) > 50:
            st.caption(f"Showing the 50 most recent of {len(visible)} alerts. See 'Full log' for all.")

    # ----- full log -----------------------------------------------------------------
    with tab_log:
        table(
            [
                {
                    "ID": a["id"],
                    "Time": fmt_time(a["created_at"]),
                    "Severity": a["severity"],
                    "Rule": a["rule"],
                    "Message": a["message"],
                    "Sender": party_label(a["sender"], book) if a["sender"] else "-",
                    "Amount": fmt_amount(a["amount"]) if a["amount"] else "-",
                    "Transaction": short(a["tx_id"], 10, 6) if a["tx_id"] else "-",
                }
                for a in alerts
            ],
            empty_message="The fraud log is empty.",
            height=420 if len(alerts) > 10 else None,
        )

    # ----- rules ----------------------------------------------------------------------
    with tab_rules:
        section("Behaviour rules (transaction is accepted but flagged)")
        table(
            [
                {"Rule": "LARGE_TRANSACTION", "Severity": "HIGH",
                 "Fires when": f"Amount is {config.LARGE_TX_THRESHOLD:,.0f} {config.COIN_SYMBOL} or more"},
                {"Rule": "HIGH_VELOCITY", "Severity": "HIGH",
                 "Fires when": f"More than {config.VELOCITY_MAX_TX} payments from one wallet within "
                               f"{config.VELOCITY_WINDOW_SECONDS} seconds"},
                {"Rule": "BALANCE_DRAIN", "Severity": "MEDIUM",
                 "Fires when": f"One payment spends {config.BALANCE_DRAIN_RATIO:.0%} or more of the available balance"},
                {"Rule": "FIRST_TIME_RECIPIENT", "Severity": "LOW",
                 "Fires when": "The sender has never paid this recipient before"},
            ]
        )
        section("Security events (transaction is rejected)")
        table(
            [
                {"Event": "REJECTED_FORGED_SIGNATURE", "Severity": "CRITICAL",
                 "Meaning": "Signature missing, invalid, or made with a key that is not the sender's"},
                {"Event": "CHAIN_TAMPERING_DETECTED", "Severity": "CRITICAL",
                 "Meaning": "Chain validation found modified blocks or transactions"},
                {"Event": "REJECTED_DOUBLE_SPEND", "Severity": "HIGH",
                 "Meaning": "Replayed transaction, or coins already committed to a pending payment"},
                {"Event": "REJECTED_INSUFFICIENT_BALANCE", "Severity": "MEDIUM",
                 "Meaning": "Sender tried to spend more than the wallet owns"},
                {"Event": "REJECTED_INVALID_TRANSACTION", "Severity": "MEDIUM",
                 "Meaning": "Malformed data: bad address, bad amount, modified fields"},
            ]
        )
        st.caption(
            "Risk score per transaction: LOW = 10, MEDIUM = 30, HIGH = 50 points, capped at 100. "
            "Thresholds are defined in config.py."
        )
