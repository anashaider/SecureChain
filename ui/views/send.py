"""Send: create, sign and submit a payment - and watch each security step happen."""

import streamlit as st

import config
from node import ChainIntegrityError
from transactions import InvalidSignatureError, TransactionError
from ui.components import (
    flash,
    flow,
    fmt_amount,
    need_wallets_notice,
    page_header,
    section,
    short,
    stat_card,
    wallet_select,
)
from wallet import WalletError

SAVED = "One of my wallets"
CUSTOM = "Enter an address"

# The pipeline shown before anything has been sent.
_IDLE_STEPS = [
    {"state": "info", "title": "Unlock", "text": "The private key is decrypted in memory with your password."},
    {"state": "info", "title": "Hash and sign", "text": "SHA-256 fingerprint of the transaction, signed with ECDSA."},
    {"state": "info", "title": "Node verification", "text": "Signature, balance and double-spend checks."},
    {"state": "info", "title": "Fraud monitor", "text": "Four behaviour rules produce a risk score."},
    {"state": "info", "title": "Pending pool", "text": "The transaction waits until a block is mined."},
]


def render(node) -> None:
    page_header(
        "Send Transaction",
        "Payments are signed with the sender's private key and verified by the node before they are accepted.",
        eyebrow="Transfer",
    )
    if need_wallets_notice(node):
        return

    wallets = node.list_wallets()
    left, right = st.columns([3, 2])

    with left:
        sender = wallet_select("From wallet", wallets, key="send_sender")

        mode = st.radio("Recipient", [SAVED, CUSTOM], horizontal=True, key="send_mode")
        others = [w for w in wallets if w["address"] != sender["address"]]
        if mode == SAVED:
            if others:
                receiver_wallet = wallet_select("To wallet", others, key="send_receiver", show_balance=False)
                receiver = receiver_wallet["address"]
            else:
                st.caption("There is no other wallet on this node - create one or enter an address.")
                receiver = ""
        else:
            receiver = st.text_input(
                "Recipient address", key="send_custom", placeholder=f"{config.ADDRESS_PREFIX} followed by 40 hex characters"
            ).strip()

        # The form clears the password field after every submission.
        with st.form("send_form", clear_on_submit=True):
            amount = st.number_input(f"Amount ({config.COIN_SYMBOL})", min_value=0.0, value=10.0, step=1.0,
                                     format="%.2f")
            password = st.text_input("Wallet password (unlocks the private key to sign)", type="password")
            submitted = st.form_submit_button("Sign and send", type="primary", icon=":material/send:")

        if submitted:
            if not receiver:
                st.error("Choose a recipient first.")
            else:
                _send(node, sender, receiver, amount, password)

    with right:
        stat_card("Available to spend", fmt_amount(sender["available"]),
                  f"Confirmed balance {fmt_amount(sender['balance'])}")
        trace = st.session_state.get("send_trace")
        if trace:
            section("Last submission · step by step")
            flow(trace)
        else:
            section("What happens when you send")
            flow(_IDLE_STEPS, gap=0.12)


def _idle(titles: list[str]) -> list[dict]:
    return [{"state": "idle", "title": title, "text": "Not reached."} for title in titles]


def _send(node, sender: dict, receiver: str, amount: float, password: str) -> None:
    """Submit the payment, record what really happened at each step, and report it."""
    unlocked = {"state": "ok", "title": "Wallet unlocked", "text": f"{sender['name']}'s private key decrypted in memory."}
    try:
        result = node.send(sender["address"], password, receiver, amount)
    except WalletError as exc:
        st.session_state["send_trace"] = [
            {"state": "bad", "title": "Wallet could not be unlocked", "text": str(exc)},
            *_idle(["Hash and sign", "Node verification", "Fraud monitor", "Pending pool"]),
        ]
        st.error(f"Could not unlock the wallet: {exc}")
    except TransactionError as exc:
        failed = "Signature check failed" if isinstance(exc, InvalidSignatureError) else "Rejected by the node"
        st.session_state["send_trace"] = [
            unlocked,
            {"state": "ok", "title": "Hashed and signed", "text": f"{fmt_amount(float(amount))} to {short(receiver, 10, 6)}"},
            {"state": "bad", "title": failed, "text": str(exc)},
            {"state": "ok", "title": "Attempt written to the fraud log", "text": "Rejected transactions are kept as security events."},
            *_idle(["Pending pool"]),
        ]
        st.error(f"Transaction rejected: {exc}")
    except ChainIntegrityError as exc:
        st.session_state["send_trace"] = [
            {"state": "bad", "title": "Ledger integrity check failed", "text": str(exc)},
            *_idle(["Hash and sign", "Node verification", "Fraud monitor", "Pending pool"]),
        ]
        st.error(str(exc))
    else:
        tx = result.transaction
        if result.alerts:
            monitor = {
                "state": "warn",
                "title": f"Fraud monitor: {len(result.alerts)} alert(s), risk {result.risk_score}/100 ({result.risk_level})",
                "text": " · ".join(alert.rule.replace("_", " ").title() for alert in result.alerts),
            }
        else:
            monitor = {"state": "ok", "title": "Fraud monitor: no alerts", "text": "Risk score 0/100."}
        st.session_state["send_trace"] = [
            unlocked,
            {"state": "ok", "title": "Hashed (SHA-256) and signed (ECDSA)",
             "text": f"Transaction ID {short(tx.tx_id, 16, 8)}", "code": f"signature {tx.signature[:44]}..."},
            {"state": "ok", "title": "Verified by the node",
             "text": "Signature valid · balance sufficient · not a double spend"},
            monitor,
            {"state": "ok", "title": "Waiting in the pending pool",
             "text": f"{fmt_amount(tx.amount)} will be confirmed when the next block is mined."},
        ]
        flash("success", f"Transaction accepted and signed. {fmt_amount(tx.amount)} is now pending. "
                         f"ID: {short(tx.tx_id, 16, 8)}. Mine a block to confirm it.")
        for alert in result.alerts:
            flash("warning", f"Fraud monitor [{alert.severity}] {alert.rule.replace('_', ' ')}: {alert.message}")
        if result.alerts:
            flash("info", f"Risk score for this transaction: {result.risk_score}/100 ({result.risk_level}).")
        st.rerun()
