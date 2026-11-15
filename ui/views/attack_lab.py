"""
Attack Lab: run real attacks against the node and watch each defence stop them.

Each tab performs a genuine attempt (nothing is faked): the attack goes
through the same code path as a normal transaction and the node's own
checks reject it. The step-by-step visuals are built from what actually
happened - real transaction IDs, signatures, balances and error messages.
"""

import streamlit as st

import config
from node import ChainIntegrityError
from transactions import (
    DoubleSpendError,
    InsufficientBalanceError,
    InvalidSignatureError,
    Transaction,
    TransactionError,
    create_signed_transaction,
)
from ui import viz
from ui.components import (
    bars,
    flash,
    flow,
    fmt_amount,
    need_wallets_notice,
    note_panel,
    page_header,
    party_label,
    section,
    short,
    wallet_select,
)
from ui.theme import ACCENT, BAD, OK
from wallet import Wallet, WalletError


def render(node) -> None:
    page_header(
        "Attack Lab",
        "Launch real attacks against the ledger and see, step by step, how each defence stops them.",
        eyebrow="Red team",
    )
    if need_wallets_notice(node):
        return

    # The key keeps the chosen tab selected when an attack triggers a rerun;
    # while a tampering demo is active the lab opens straight on that tab.
    forged, overspend, double, tamper = st.tabs(
        ["Forged signature", "Insufficient balance", "Double spending", "Tamper with history"],
        key="lab_tabs",
        default="Tamper with history" if node.is_tampered() or st.session_state.get("lab_tamper_tab") else None,
    )
    with forged:
        _forged_signature(node)
    with overspend:
        _insufficient_balance(node)
    with double:
        _double_spend(node)
    with tamper:
        _tamper(node)


# --------------------------------------------------------------------------
# 1. Forged signature
# --------------------------------------------------------------------------
def _forged_signature(node) -> None:
    left, right = st.columns([2, 3])
    with left:
        note_panel(
            "Scenario: an attacker wants to steal from a victim. They do not know the victim's private key, "
            "so they write a transaction FROM the victim's address and sign it with their own key."
        )
        wallets = node.list_wallets()
        victim = wallet_select("Victim wallet", wallets, key="lab_victim")
        amount = st.number_input("Amount to steal", min_value=1.0, value=50.0, step=1.0, key="lab_forge_amount")
        variant = st.radio(
            "Attacker's trick",
            ["Attach the victim's public key (signature will not match)",
             "Attach the attacker's own public key (key will not match the address)"],
            key="lab_forge_variant",
        )

        if st.button("Launch forged transaction", key="lab_forge_go", type="primary", icon=":material/gpp_bad:"):
            attacker = Wallet.create()                         # throw-away attacker key pair
            use_victim_key = variant.startswith("Attach the victim")
            tx = Transaction(sender=victim["address"], receiver=attacker.address, amount=float(amount))
            tx.sender_public_key = victim["public_key"] if use_victim_key else attacker.public_key_hex
            tx.tx_id = tx.compute_hash()
            tx.signature = attacker.sign(tx.payload())         # signed with the WRONG private key
            steps = [
                {"state": "info", "title": "Attacker writes a transaction from the victim's address",
                 "text": f"'{victim['name']} pays {fmt_amount(tx.amount)} to {short(attacker.address, 10, 6)}'",
                 "code": f"tx id {tx.tx_id}"},
                {"state": "warn", "title": "Attacker signs it with their OWN private key",
                 "text": "They do not have the victim's key, so this is the only signature they can make.",
                 "code": f"signature {tx.signature[:56]}..."},
                {"state": "warn",
                 "title": "Attaches the victim's public key" if use_victim_key else "Attaches the attacker's own public key",
                 "text": "Claims the signature belongs to the victim." if use_victim_key
                 else "Hopes the node will verify against the attacker's key instead.",
                 "code": f"public key {tx.sender_public_key}"},
            ]
            try:
                node.submit_transaction(tx)
            except InvalidSignatureError as exc:
                steps += [
                    {"state": "bad", "title": "Node verification FAILS",
                     "text": f"{exc} " + ("ECDSA verification with the victim's public key does not accept a signature "
                                          "made by a different private key." if use_victim_key else
                                          "SHA-256(public key) does not produce the sender's address, so the key is not the owner's.")},
                    {"state": "ok", "title": "Attack blocked",
                     "text": "The transaction never entered the pending pool. Recorded in the fraud log as "
                             "REJECTED_FORGED_SIGNATURE (CRITICAL)."},
                ]
                st.session_state["lab_forged"] = {"steps": steps, "blocked": True, "message": str(exc)}
            except (TransactionError, ChainIntegrityError) as exc:
                steps.append({"state": "bad", "title": "Rejected for a different reason", "text": str(exc)})
                st.session_state["lab_forged"] = {"steps": steps, "blocked": True, "message": str(exc)}
            else:
                steps.append({"state": "bad", "title": "The forged transaction was ACCEPTED",
                              "text": "This should never happen."})
                st.session_state["lab_forged"] = {"steps": steps, "blocked": False, "message": ""}

    with right:
        result = st.session_state.get("lab_forged")
        if result:
            if result["blocked"]:
                st.success(f"Attack blocked. The node rejected the transaction: {result['message']}")
            else:
                st.error("The forged transaction was accepted - this should never happen.")
            section("What happened, step by step")
            flow(result["steps"])
        else:
            section("How the defence works")
            flow([
                {"state": "info", "title": "A signature can only be made with the private key",
                 "text": "ECDSA signatures are bound to both the key and the exact transaction data."},
                {"state": "info", "title": "The node verifies with the sender's public key",
                 "text": "A signature made with any other key fails verification."},
                {"state": "info", "title": "The public key must hash to the sender's address",
                 "text": "So an attacker cannot simply attach their own public key."},
            ], gap=0.15)


# --------------------------------------------------------------------------
# 2. Insufficient balance
# --------------------------------------------------------------------------
def _insufficient_balance(node) -> None:
    left, right = st.columns([2, 3])
    with left:
        note_panel(
            "Scenario: a brand-new wallet that owns 0 coins creates a perfectly signed payment. "
            "The signature is valid - but the blockchain shows the sender has no funds."
        )
        wallets = node.list_wallets()
        receiver = wallet_select("Receiver", wallets, key="lab_overspend_receiver", show_balance=False)
        amount = st.number_input("Amount to send", min_value=1.0, value=25.0, step=1.0, key="lab_overspend_amount")

        if st.button("Send from an empty wallet", key="lab_overspend_go", type="primary", icon=":material/money_off:"):
            broke = Wallet.create()
            tx = create_signed_transaction(broke, receiver["address"], float(amount))
            balance = node.blockchain.get_balance(broke.address)
            steps = [
                {"state": "info", "title": "A new wallet is created", "text": f"Address {short(broke.address, 12, 8)} - it has never received a coin."},
                {"state": "ok", "title": "The payment is correctly signed",
                 "text": f"{fmt_amount(tx.amount)} to {receiver['name']}. The signature is genuine.",
                 "code": f"signature {tx.signature[:56]}..."},
                {"state": "ok", "title": "Signature check passes", "text": "The node confirms the sender really signed this."},
            ]
            try:
                node.submit_transaction(tx)
            except InsufficientBalanceError as exc:
                steps += [
                    {"state": "bad", "title": "Balance check FAILS", "text": str(exc)},
                    {"state": "ok", "title": "Attack blocked",
                     "text": "Balances are recomputed from the chain, so coins cannot be invented. "
                             "Logged as REJECTED_INSUFFICIENT_BALANCE."},
                ]
                blocked, message = True, str(exc)
            except (TransactionError, ChainIntegrityError) as exc:
                steps.append({"state": "bad", "title": "Rejected for a different reason", "text": str(exc)})
                blocked, message = True, str(exc)
            else:
                steps.append({"state": "bad", "title": "The payment was ACCEPTED", "text": "This should never happen."})
                blocked, message = False, ""
            st.session_state["lab_overspend"] = {
                "steps": steps, "blocked": blocked, "message": message, "balance": balance, "amount": tx.amount,
            }

    with right:
        result = st.session_state.get("lab_overspend")
        if result:
            if result["blocked"]:
                st.success(f"Attack blocked. {result['message']}")
            else:
                st.error("The overspending transaction was accepted - this should never happen.")
            section("Requested amount versus real balance")
            top = max(result["amount"], result["balance"], 1e-9)
            bars([
                {"label": "Balance on the blockchain", "value": fmt_amount(result["balance"]),
                 "fraction": result["balance"] / top, "tone": OK},
                {"label": "Amount the transaction tries to spend", "value": fmt_amount(result["amount"]),
                 "fraction": result["amount"] / top, "tone": BAD},
            ])
            section("What happened, step by step")
            flow(result["steps"])
        else:
            section("How the defence works")
            flow([
                {"state": "info", "title": "Balances are never stored",
                 "text": "A wallet's balance is always recalculated from every transaction in the chain."},
                {"state": "info", "title": "A valid signature is not enough",
                 "text": "The node also checks that the sender owns at least the amount being sent."},
            ], gap=0.15)


# --------------------------------------------------------------------------
# 3. Double spending
# --------------------------------------------------------------------------
def _double_spend(node) -> None:
    wallets = node.list_wallets()
    funded = [w for w in wallets if w["available"] > 0]
    left, right = st.columns([2, 3])
    with left:
        note_panel(
            "Scenario: a wallet owner signs two payments that each spend most of the balance, to two different "
            "people, before any block is mined - hoping both get accepted. Then they re-submit the first one (a replay)."
        )
        if len(wallets) < 3 or not funded:
            st.info("This demo needs three wallets, one of them with an available balance. "
                    "Use 'Load demo data' in the sidebar or mine a block first.")
        else:
            spender = wallet_select("Dishonest spender", funded, key="lab_double_spender")
            others = [w for w in wallets if w["address"] != spender["address"]]
            first_receiver, second_receiver = others[0], others[1]
            amount = round(spender["available"] * 0.8, 2)
            st.caption(
                f"Payment A: {fmt_amount(amount)} to {first_receiver['name']}  ·  "
                f"Payment B: {fmt_amount(amount)} to {second_receiver['name']}  ·  "
                f"Available: {fmt_amount(spender['available'])}"
            )
            password = st.text_input("Spender's wallet password", type="password", key="lab_double_password")

            if st.button("Attempt double spend", key="lab_double_go", type="primary", icon=":material/content_copy:"):
                try:
                    wallet = node.unlock_wallet(spender["address"], password)
                except WalletError as exc:
                    st.error(f"Could not unlock the wallet: {exc}")
                else:
                    available = spender["available"]
                    payment_a = create_signed_transaction(wallet, first_receiver["address"], amount)
                    payment_b = create_signed_transaction(wallet, second_receiver["address"], amount)
                    del wallet
                    steps = []
                    for label, tx, receiver in (
                        ("Payment A", payment_a, first_receiver["name"]),
                        ("Payment B (the same coins again)", payment_b, second_receiver["name"]),
                        ("Replay of payment A", payment_a, first_receiver["name"]),
                    ):
                        title = f"{label}: {fmt_amount(tx.amount)} to {receiver}"
                        try:
                            node.submit_transaction(tx)
                            steps.append({"state": "ok", "title": title + " - ACCEPTED",
                                          "text": "Valid signature and enough unspent coins. Now waiting in the pending pool.",
                                          "code": f"tx id {tx.tx_id}"})
                            flash("info", f"{label}: ACCEPTED into the pending pool.")
                        except DoubleSpendError as exc:
                            steps.append({"state": "bad", "title": title + " - BLOCKED", "text": str(exc),
                                          "code": f"tx id {tx.tx_id}"})
                            flash("success", f"{label}: BLOCKED. {exc}")
                        except (TransactionError, ChainIntegrityError) as exc:
                            steps.append({"state": "bad", "title": title + " - rejected", "text": str(exc)})
                            flash("warning", f"{label}: rejected - {exc}")
                    steps.append({"state": "ok", "title": "Result: the coins can only be spent once",
                                  "text": "Mine a block to confirm payment A. Payment B can never be included."})
                    st.session_state["lab_double"] = {
                        "steps": steps, "available": available, "amount": amount, "spender": spender["name"],
                    }
                    st.rerun()

    with right:
        result = st.session_state.get("lab_double")
        if result:
            section(f"{result['spender']}'s coins: owned versus promised")
            top = max(result["amount"] * 2, result["available"], 1e-9)
            bars([
                {"label": "Available before the attack", "value": fmt_amount(result["available"]),
                 "fraction": result["available"] / top, "tone": OK},
                {"label": "Total the two payments try to spend", "value": fmt_amount(result["amount"] * 2),
                 "fraction": result["amount"] * 2 / top, "tone": BAD},
                {"label": "Actually committed (payment A only)", "value": fmt_amount(result["amount"]),
                 "fraction": result["amount"] / top, "tone": ACCENT},
            ])
            section("What happened, step by step")
            flow(result["steps"])
        else:
            section("How the defence works")
            flow([
                {"state": "info", "title": "Pending payments reserve coins",
                 "text": "Spendable balance = confirmed balance minus everything already waiting in the pool."},
                {"state": "info", "title": "Every transaction ID is unique",
                 "text": "A random nonce is part of the signed data, so a copied transaction is recognised as a replay."},
                {"state": "info", "title": "Validation replays the whole chain",
                 "text": "Even a dishonest miner cannot include the same transaction twice."},
            ], gap=0.15)


# --------------------------------------------------------------------------
# 4. Tampering with history
# --------------------------------------------------------------------------
def _tamper(node) -> None:
    if node.is_tampered():
        _tamper_result(node)
        return

    left, right = st.columns([2, 3])
    with left:
        note_panel(
            "Scenario: someone with access to the database file edits the amount of an old, already-confirmed "
            "transaction. The change is written straight into SQLite, bypassing the application - then the node "
            "reloads the chain and validates it."
        )
        book = node.address_book()
        confirmed = [
            (position, tx_position, tx)
            for position, block in enumerate(node.blockchain.chain)
            for tx_position, tx in enumerate(block.transactions)
            if position > 0
        ]
        if not confirmed:
            st.info("There are no confirmed transactions yet. Mine a block first.")
            return

        # Prefer showing real payments first (they make the best demo), then rewards.
        confirmed.sort(key=lambda item: item[2].is_coinbase)
        choice = st.selectbox(
            "Confirmed transaction to modify",
            range(len(confirmed)),
            format_func=lambda i: (
                f"Block #{confirmed[i][0]}  ·  {party_label(confirmed[i][2].sender, book)} -> "
                f"{party_label(confirmed[i][2].receiver, book)}  ·  {fmt_amount(confirmed[i][2].amount)}"
            ),
            key="lab_tamper_choice",
        )
        block_index, position, tx = confirmed[choice]
        new_amount = st.number_input("New (fraudulent) amount", min_value=0.01, value=float(tx.amount) * 10,
                                     step=1.0, key="lab_tamper_amount")
        smart = st.checkbox(
            "Sophisticated attacker: also recompute the transaction ID, Merkle root and block hash to hide the change",
            key="lab_tamper_smart",
        )

        if st.button("Tamper with the database", key="lab_tamper_go", type="primary", icon=":material/edit_off:"):
            if round(new_amount, config.AMOUNT_DECIMALS) == tx.amount:
                st.error("Choose an amount different from the original.")
                return
            try:
                original = node.tamper_with_transaction(block_index, position, new_amount, recompute_hashes=smart)
            except ValueError as exc:
                st.error(str(exc))
                return
            report = node.validate_chain()
            flash("warning", f"Database modified: amount in block #{block_index} changed from "
                             f"{fmt_amount(original)} to {fmt_amount(new_amount)}.")
            if report.is_valid:
                flash("error", "Validation did not notice the change - this should never happen.")
            else:
                flash("success", f"Tampering DETECTED by chain validation: {len(report.issues)} problem(s), "
                                 f"starting at block #{report.first_bad_block}.")
            st.rerun()

    with right:
        section("Why a hidden edit is impossible")
        flow([
            {"state": "info", "title": "Edit the amount", "text": "The transaction no longer hashes to its ID, and its signature breaks."},
            {"state": "info", "title": "Also fix the transaction ID", "text": "The block's Merkle root no longer matches its transactions."},
            {"state": "info", "title": "Also fix the Merkle root", "text": "The block header changes, so the mined block hash is wrong."},
            {"state": "info", "title": "Also fix the block hash", "text": "Proof-of-Work is lost and the next block's previous-hash link breaks."},
            {"state": "ok", "title": "And the signature can never be fixed", "text": "Only the sender's private key can sign the new amount."},
        ], gap=0.15)


def _tamper_result(node) -> None:
    """Shown while a simulated tampering attack is active."""
    report = node.validate_chain()
    st.error(
        f"The stored blockchain is currently TAMPERED: {len(report.issues)} validation problem(s), "
        f"first in block #{report.first_bad_block}. Sending and mining are disabled until it is restored."
    )
    if st.button("Restore original data", type="primary", key="lab_restore", icon=":material/restore:"):
        restored = node.restore_tampering()
        st.session_state["lab_tamper_tab"] = True      # stay on this tab after the page refreshes
        flash("success", f"Restored {restored} block(s) from backup. The chain is valid again.")
        st.rerun()

    payload = viz.tamper_payload(node)
    if payload:
        section("Before and after · SHA-256 mismatch detection")
        viz.hash_diff(payload, height=100 + 30 * len(payload["fields"]) + 128 * len(payload["comparisons"]), key="lab_hashdiff")

    section("The chain as the node sees it now")
    viz.chain_3d(node, height=340, focus=payload["block_index"] if payload else None, key="lab_chain")

    section("Problems reported by chain validation")
    flow(
        [
            {"state": "bad", "title": f"Block #{issue.block_index} · {issue.check.replace('_', ' ').title()}", "text": issue.message}
            for issue in report.issues[:8]
        ],
        gap=0.1,
    )
    if len(report.issues) > 8:
        st.caption(f"+ {len(report.issues) - 8} more - see the Chain Validation page.")
