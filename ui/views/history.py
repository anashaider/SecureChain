"""Transaction history: the 3D transaction network plus an animated, filterable timeline."""

import streamlit as st

from ui import viz
from ui.components import (
    fmt_amount,
    fmt_time,
    page_header,
    party_label,
    party_name,
    section,
    short,
    stat_row,
    table,
    tx_timeline,
)

ALL = "All wallets"
MAX_CARDS = 40


def _collect(node, book: dict[str, str]) -> list[dict]:
    """
    Every transaction outcome the node knows about, newest first:
    confirmed and pending transactions from the chain and the pool, plus
    rejected attempts from the fraud log.
    """
    flagged, rejected = viz.classify_transactions(node)
    alerts_by_tx: dict[str, list[dict]] = {}
    for alert in node.get_alerts():
        if alert["tx_id"] and not alert["rule"].startswith("REJECTED_"):
            alerts_by_tx.setdefault(alert["tx_id"], []).append(alert)

    items = []
    for entry in node.get_history():
        tx = entry["tx"]
        if tx.is_coinbase:
            state, signature = "reward", "Not required (mining reward created by the protocol)"
        else:
            state = "flagged" if tx.tx_id in flagged else entry["status"].lower()
            signature = "VALID - verified with the sender's public key" if tx.is_valid() else "INVALID - fails verification"
        where = "pending pool" if entry["block_index"] is None else f"block #{entry['block_index']}"
        details = [
            ("Transaction ID", tx.tx_id, True),
            ("Status", f"{entry['status']} · {where}", False),
            ("Sender", tx.sender, True),
            ("Receiver", tx.receiver, True),
            ("Nonce", tx.nonce, True),
            ("Signature", tx.signature or "-", True),
            ("Signature check", signature, False),
        ]
        for alert in alerts_by_tx.get(tx.tx_id, []):
            details.append((f"Alert · {alert['severity']}", f"{alert['rule'].replace('_', ' ').title()}: {alert['message']}", False))
        items.append({
            "state": state, "time": tx.timestamp, "sender_address": tx.sender, "receiver_address": tx.receiver,
            "sender": party_name(tx.sender, book), "receiver": party_name(tx.receiver, book),
            "amount": fmt_amount(tx.amount), "meta": f"{fmt_time(tx.timestamp)} · {where}",
            "details": details, "tx": tx, "block": entry["block_index"],
        })
    for alert in rejected:
        items.append({
            "state": "rejected", "time": alert["created_at"],
            "sender_address": alert["sender"], "receiver_address": alert["receiver"],
            "sender": party_name(alert["sender"], book) if alert["sender"] else "unknown",
            "receiver": party_name(alert["receiver"], book) if alert["receiver"] else "unknown",
            "amount": fmt_amount(alert["amount"]),
            "meta": f"{fmt_time(alert['created_at'])} · never entered the ledger",
            "details": [
                ("Reason", alert["message"], False),
                ("Security event", alert["rule"], True),
                ("Severity", alert["severity"], False),
                ("Claimed sender", alert["sender"] or "-", True),
                ("Receiver", alert["receiver"] or "-", True),
                ("Transaction ID", alert["tx_id"] or "-", True),
            ],
            "tx": None, "block": None,
        })
    items.sort(key=lambda item: item["time"], reverse=True)
    return items


def render(node) -> None:
    page_header(
        "Transaction Network & History",
        "Wallets are nodes, payments are particles. Green = confirmed, cyan = pending, amber = flagged, red = rejected.",
        eyebrow="Ledger activity",
    )

    wallets = node.list_wallets()
    book = node.address_book()
    items = _collect(node, book)
    counts = {state: sum(1 for item in items if item["state"] == state)
              for state in ("confirmed", "pending", "flagged", "rejected", "reward")}

    # ----- interactive 3D network ----------------------------------------------
    viz.tx_network(node, height=520, key="history_network")

    stat_row([
        {"label": "Confirmed payments", "value": counts["confirmed"], "hint": "Mined into a block", "tone": "ok"},
        {"label": "Pending", "value": counts["pending"], "hint": "Waiting in the pool"},
        {"label": "Flagged", "value": counts["flagged"], "hint": "Accepted, medium or higher risk",
         "tone": "warn" if counts["flagged"] else ""},
        {"label": "Rejected", "value": counts["rejected"], "hint": "Refused by the node",
         "tone": "bad" if counts["rejected"] else ""},
    ])

    # ----- filters --------------------------------------------------------------
    section("Timeline")
    col1, col2, col3 = st.columns(3)
    chosen = col1.selectbox("Wallet", [ALL] + [w["name"] for w in wallets], key="history_wallet")
    status = col2.selectbox("Status", ["All", "Confirmed", "Pending", "Flagged", "Rejected"], key="history_status")
    kind = col3.selectbox("Type", ["Payments", "Payments and mining rewards", "Mining rewards"], key="history_kind")

    address = next((w["address"] for w in wallets if w["name"] == chosen), None)
    visible = items
    if address:
        visible = [i for i in visible if address in (i["sender_address"], i["receiver_address"])]
    if status != "All":
        visible = [i for i in visible if i["state"] == status.lower()]
    if kind == "Payments":
        visible = [i for i in visible if i["state"] != "reward"]
    elif kind == "Mining rewards":
        visible = [i for i in visible if i["state"] == "reward"]

    tab_cards, tab_table = st.tabs(["Timeline", "Table"])
    with tab_cards:
        if not visible:
            st.caption("No transactions match these filters.")
        else:
            st.caption(f"{len(visible)} transaction(s) · click a card to expand it")
            tx_timeline(visible[:MAX_CARDS])
            if len(visible) > MAX_CARDS:
                st.caption(f"Showing the {MAX_CARDS} most recent. Use the Table tab or the filters to see the rest.")

    with tab_table:
        table(
            [
                {
                    "Time": fmt_time(item["time"]),
                    "Status": item["state"].title(),
                    "Block": "-" if item["block"] is None else str(item["block"]),
                    "From": party_label(item["sender_address"], book) if item["sender_address"] else "-",
                    "To": party_label(item["receiver_address"], book) if item["receiver_address"] else "-",
                    "Amount": item["amount"],
                    "Transaction ID": short(item["tx"].tx_id, 12, 8) if item["tx"] else "-",
                }
                for item in visible
            ],
            empty_message="No transactions match these filters.",
            height=420 if len(visible) > 10 else None,
        )
