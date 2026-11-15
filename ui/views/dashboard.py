"""Dashboard: the live overview - 3D chain, KPIs, activity chart, alerts and balances."""

import streamlit as st

import config
from ui import viz
from ui.components import (
    alert_feed,
    area_gradient,
    bars,
    chart,
    fmt_amount,
    fmt_time,
    page_header,
    section,
    short,
    stat_row,
    table,
)
from ui.theme import ACCENT, PURPLE


def render(node) -> None:
    page_header(
        "Blockchain Command Center",
        "Live view of the SecureChain ledger. Every figure below is computed from the real chain.",
        eyebrow="Overview",
    )

    stats = node.get_stats()
    book = node.address_book()
    wallets = node.list_wallets()

    if stats["wallets"] == 0:
        st.info(
            "Welcome to SecureChain. Start by creating a wallet on the **Wallets** page, "
            "or open **Demo tools** in the sidebar and click **Load demo data**."
        )

    # ----- interactive 3D chain ------------------------------------------------
    viz.chain_3d(node, height=430, animate=st.session_state.pop("animate_block", None), key="dashboard_chain")

    # ----- headline numbers ----------------------------------------------------
    stat_row([
        {"label": "Chain integrity", "value": "VALID" if stats["is_valid"] else "COMPROMISED",
         "hint": "All hashes, links and signatures verified" if stats["is_valid"] else "Tampering detected - see Chain Validation",
         "tone": "ok" if stats["is_valid"] else "bad"},
        {"label": "Blocks", "value": stats["blocks"], "hint": "Including the genesis block"},
        {"label": "Confirmed transactions", "value": stats["confirmed_transactions"], "hint": "Stored in mined blocks"},
        {"label": "Pending transactions", "value": stats["pending_transactions"], "hint": "Waiting to be mined",
         "tone": "warn" if stats["pending_transactions"] else ""},
    ])
    stat_row([
        {"label": "Wallets", "value": stats["wallets"], "hint": "Stored on this node", "tone": "purple"},
        {"label": "Coins in circulation", "value": int(stats["total_supply"]), "unit": config.COIN_SYMBOL,
         "hint": "Created only by mining rewards"},
        {"label": "Security alerts", "value": stats["alerts"], "hint": "Entries in the fraud log",
         "tone": "warn" if stats["alerts"] else ""},
        {"label": "Mining difficulty", "value": stats["difficulty"],
         "hint": f"Leading zeros · reward {stats['mining_reward']:,.0f} {config.COIN_SYMBOL}"},
    ])

    # ----- activity + alerts -----------------------------------------------------
    left, right = st.columns([3, 2])
    with left:
        section("Activity per block")
        mined = node.blockchain.chain[1:]
        if mined:
            rows = [
                {
                    "Block": block.index,
                    "Payments": sum(1 for tx in block.transactions if not tx.is_coinbase),
                    "Volume": round(sum(tx.amount for tx in block.transactions if not tx.is_coinbase), 2),
                    "Attempts": block.nonce + 1,
                }
                for block in mined[-40:]
            ]
            tooltip = [
                {"field": "Block", "title": "Block"},
                {"field": "Volume", "title": f"Volume ({config.COIN_SYMBOL})", "format": ",.2f"},
                {"field": "Payments", "title": "Payments"},
                {"field": "Attempts", "title": "Mining attempts", "format": ","},
            ]
            chart(
                rows,
                {
                    "encoding": {"x": {"field": "Block", "type": "ordinal", "axis": {"labelAngle": 0, "title": "Block"}}},
                    "layer": [
                        {
                            "mark": {"type": "area", "interpolate": "monotone", "color": area_gradient(),
                                     "line": {"color": ACCENT, "strokeWidth": 2}},
                            "encoding": {"y": {"field": "Volume", "type": "quantitative",
                                               "axis": {"title": f"Payment volume ({config.COIN_SYMBOL})"}}},
                        },
                        {
                            "mark": {"type": "point", "filled": True, "size": 70, "color": PURPLE, "opacity": 0.95},
                            "encoding": {"y": {"field": "Volume", "type": "quantitative"}, "tooltip": tooltip},
                        },
                    ],
                },
                height=230,
            )
        else:
            st.caption("Mine the first block to see activity here.")

        section("Latest blocks")
        table(
            [
                {
                    "Block": block.index,
                    "Mined at": "Genesis" if block.index == 0 else fmt_time(block.timestamp),
                    "Transactions": len(block.transactions),
                    "Nonce": block.nonce,
                    "Hash": short(block.hash, 14, 8),
                }
                for block in reversed(node.blockchain.chain[-6:])
            ]
        )

    with right:
        section("Recent security alerts")
        alerts = node.get_alerts(limit=4)
        if alerts:
            alert_feed(alerts, book)
        else:
            st.caption("No alerts. Suspicious or rejected transactions will appear here.")

        section("Wallet balances")
        if wallets:
            top = max((w["balance"] for w in wallets), default=0) or 1
            bars([
                {"label": w["name"], "value": fmt_amount(w["balance"]), "fraction": w["balance"] / top}
                for w in sorted(wallets, key=lambda w: w["balance"], reverse=True)[:8]
            ])
        else:
            st.caption("No wallets yet.")
