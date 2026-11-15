"""
SecureChain - Streamlit command center entry point.

Run with:   streamlit run app.py

This file only does four things: page setup, sidebar navigation, handing
over to the selected page in ui/views/, and the status block in the sidebar.

A page can be opened directly with a link such as
    http://localhost:8501/?page=mining
"""

import streamlit as st

import config
from ui.components import flash, get_node, render_html, short
from ui.theme import apply_theme
from ui.views import (
    attack_lab,
    dashboard,
    explorer,
    fraud,
    history,
    mining,
    send,
    validation,
    wallets,
)
from node import DEMO_PASSWORD, ChainIntegrityError
from wallet import WalletError

# Page name -> (icon, function that draws it). The order is the menu order.
PAGES = {
    "Dashboard": (":material/space_dashboard:", dashboard.render),
    "Wallets": (":material/account_balance_wallet:", wallets.render),
    "Send Transaction": (":material/send:", send.render),
    "Transaction History": (":material/hub:", history.render),
    "Mining": (":material/memory:", mining.render),
    "Fraud Alerts": (":material/radar:", fraud.render),
    "Blockchain Explorer": (":material/deployed_code:", explorer.render),
    "Chain Validation": (":material/verified_user:", validation.render),
    "Attack Lab": (":material/bug_report:", attack_lab.render),
}
# Short names accepted in the ?page= link, e.g. "mining" or "attack-lab".
SLUGS = {name.lower().replace(" ", "-"): name for name in PAGES}
SLUGS.update({"send": "Send Transaction", "history": "Transaction History", "fraud": "Fraud Alerts",
              "explorer": "Blockchain Explorer", "validation": "Chain Validation", "attack": "Attack Lab"})

st.set_page_config(page_title="SecureChain · Command Center", page_icon=":material/shield_lock:", layout="wide")
apply_theme()
node = get_node()
node.sync()      # pick up changes made to the database by another process, if any


def sidebar_navigation() -> str:
    if "nav" not in st.session_state:                 # first run: honour a ?page= link
        wanted = SLUGS.get(str(st.query_params.get("page", "")).lower())
        if wanted:
            st.session_state["nav"] = wanted
    with st.sidebar:
        render_html(
            '<div class="sc-brand"><div class="sc-brand-logo">SC</div>'
            '<div><div class="sc-brand-name">SecureChain</div>'
            '<div class="sc-brand-tag">Security command center</div></div></div>'
        )
        return st.radio(
            "Navigation", list(PAGES), key="nav", label_visibility="collapsed", width="stretch",
            format_func=lambda name: f"{PAGES[name][0]} {name}",
        )


def sidebar_status() -> None:
    """Drawn AFTER the page, so it reflects any action the page just performed."""
    stats = node.get_stats()
    with st.sidebar:
        st.divider()
        if stats["is_valid"]:
            render_html('<div class="sc-status ok"><span class="sc-dot"></span>Chain integrity verified</div>')
        else:
            render_html('<div class="sc-status bad"><span class="sc-dot"></span>Chain compromised</div>')
        render_html(
            '<div class="sc-side-meta">'
            f'<div><b>{stats["blocks"] - 1}</b><span>Height</span></div>'
            f'<div><b>{stats["pending_transactions"]}</b><span>Pending</span></div>'
            f'<div><b>{stats["alerts"]}</b><span>Alerts</span></div></div>'
            f'<div class="sc-side-tip">Tip <span class="sc-mono">{short(stats["latest_hash"], 10, 6)}</span></div>'
        )

        with st.expander("Demo tools", icon=":material/science:"):
            st.caption(f"Creates Alice, Bob and Charlie with coins. Password for all three: `{DEMO_PASSWORD}`")
            if st.button("Load demo data", key="demo_load", icon=":material/dataset:"):
                try:
                    with st.spinner("Creating wallets and mining blocks..."):
                        node.seed_demo_data()
                except (WalletError, ChainIntegrityError) as exc:
                    flash("error", f"Could not load demo data: {exc} Reset first if the demo wallets already exist.")
                else:
                    flash("success", f"Demo data loaded. Wallet password: {DEMO_PASSWORD}")
                st.rerun()

            st.caption("Erase all blocks, wallets and alerts and start from a new genesis block.")
            confirmed = st.checkbox("Yes, delete everything", key="demo_reset_confirm")
            if st.button("Reset all data", key="demo_reset", disabled=not confirmed, icon=":material/restart_alt:"):
                node.reset()
                for key in ("last_mined", "explorer_block", "explorer_last_query", "send_trace",
                            "lab_forged", "lab_overspend", "lab_double", "animate_block", "lab_tamper_tab"):
                    st.session_state.pop(key, None)
                flash("warning", "All data erased. A new blockchain was started.")
                st.rerun()

        st.caption(f"{config.COIN_NAME} ({config.COIN_SYMBOL}) · SHA-256 · ECDSA secp256k1")


page = sidebar_navigation()
# The container key changes with the page, which replays the page-enter animation.
with st.container(key="page-" + page.lower().replace(" ", "-")):
    PAGES[page][1](node)
sidebar_status()
