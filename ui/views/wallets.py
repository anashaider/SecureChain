"""Wallets: create wallets, see balances, back up / rename / remove them."""

import streamlit as st

import config
from ui.components import (
    esc,
    flash,
    flow,
    fmt_amount,
    fmt_time,
    key_value_panel,
    page_header,
    render_html,
    section,
    short,
    stat_row,
    table,
    wallet_select,
)
from wallet import WalletError

# Colour pairs for the wallet avatars (picked by position, purely decorative).
_AVATARS = [("#22d3ee", "#3b82f6"), ("#8b5cf6", "#ec4899"), ("#34d399", "#22d3ee"),
            ("#fbbf24", "#f97316"), ("#60a5fa", "#8b5cf6"), ("#f472b6", "#8b5cf6")]


def _wallet_card(wallet: dict, index: int, supply: float) -> str:
    a, b = _AVATARS[index % len(_AVATARS)]
    share = wallet["balance"] / supply if supply else 0
    pending = wallet["balance"] - wallet["available"]
    hint = f"{share:.0%} of all coins" + (f" · {fmt_amount(pending)} pending out" if pending > 0 else "")
    return (
        f'<div class="sc-card sc-wallet" style="animation-delay:{index * 0.07:.2f}s">'
        f'<div class="sc-wallet-name"><span class="sc-avatar" style="--a:{a};--b:{b}">{esc(wallet["name"][:1].upper())}</span>'
        f'{esc(wallet["name"])}</div>'
        f'<div class="sc-mono" style="margin-top:.35rem">{esc(short(wallet["address"], 12, 8))}</div>'
        f'<div class="sc-wallet-balance">{esc(fmt_amount(wallet["balance"]))}</div>'
        f'<div class="sc-bar" style="margin:.45rem 0 .4rem 0"><i style="width:{max(2, min(100, share * 100)):.1f}%;--tone:{a}"></i></div>'
        f'<div class="sc-card-hint">Available {esc(fmt_amount(wallet["available"]))} · {esc(hint)}</div>'
        f"</div>"
    )


def render(node) -> None:
    page_header(
        "Wallets",
        "Each wallet is an ECDSA key pair. The address is derived from the public key; the private key never leaves the server.",
        eyebrow="Identity",
    )

    wallets = node.list_wallets()
    supply = node.get_stats()["total_supply"]
    held = sum(w["balance"] for w in wallets)
    stat_row([
        {"label": "Wallets", "value": len(wallets), "hint": "Key pairs stored on this node", "tone": "purple"},
        {"label": "Held by these wallets", "value": f"{held:,.2f}", "unit": config.COIN_SYMBOL,
         "hint": f"of {supply:,.0f} {config.COIN_SYMBOL} in circulation"},
        {"label": "Signature scheme", "value": "ECDSA", "hint": "secp256k1 curve · SHA-256 digest"},
        {"label": "Key storage", "value": "AES-256", "hint": "Password-encrypted, PBKDF2 key derivation", "tone": "ok"},
    ])

    tab_list, tab_create, tab_manage = st.tabs(["My wallets", "Create wallet", "Manage"])

    # ----- overview ----------------------------------------------------------
    with tab_list:
        if not wallets:
            st.caption("No wallets yet - create your first one in the next tab.")
        else:
            columns = st.columns(3)
            for index, wallet in enumerate(wallets):
                with columns[index % 3]:
                    render_html(_wallet_card(wallet, index, supply))
            with st.expander("Show as table", icon=":material/table_rows:"):
                table(
                    [
                        {
                            "Name": w["name"],
                            "Address": w["address"],
                            "Confirmed balance": fmt_amount(w["balance"]),
                            "Available to spend": fmt_amount(w["available"]),
                            "Created": fmt_time(w["created_at"]),
                        }
                        for w in wallets
                    ]
                )
            st.caption(
                "Confirmed balance counts mined blocks only. Available balance also subtracts "
                "payments that are still pending, which is what prevents double spending."
            )

    # ----- create ------------------------------------------------------------
    with tab_create:
        left, right = st.columns([3, 2])
        with left:
            with st.form("create_wallet", clear_on_submit=True):
                name = st.text_input("Wallet name", max_chars=config.MAX_WALLET_NAME_LENGTH, placeholder="e.g. Alice")
                col1, col2 = st.columns(2)
                password = col1.text_input("Password", type="password",
                                           help=f"At least {config.MIN_PASSWORD_LENGTH} characters.")
                confirm = col2.text_input("Confirm password", type="password")
                submitted = st.form_submit_button("Create wallet", type="primary", icon=":material/add_circle:")

            if submitted:
                if password != confirm:
                    st.error("The two passwords do not match.")
                else:
                    try:
                        info = node.create_wallet(name, password)
                    except WalletError as exc:
                        st.error(str(exc))
                    else:
                        flash("success", f"Wallet '{info['name']}' created. Address: {info['address']}")
                        st.rerun()
            st.warning(
                "There is no password recovery. If the password is lost, the coins in the wallet "
                "can never be spent again.", icon=":material/key:",
            )
        with right:
            section("What happens when you click create")
            flow([
                {"state": "info", "title": "Generate a private key",
                 "text": "A random 256-bit number on the secp256k1 curve - the same curve Bitcoin uses."},
                {"state": "info", "title": "Derive the public key and address",
                 "text": f"Address = '{config.ADDRESS_PREFIX}' + first {config.ADDRESS_HASH_LENGTH} hex characters of SHA-256(public key)."},
                {"state": "ok", "title": "Encrypt the private key with your password",
                 "text": "PBKDF2 stretches the password into a key; AES-256 encrypts the private key."},
                {"state": "ok", "title": "Store only the encrypted form",
                 "text": "SQLite never contains the plain private key or the password."},
            ], gap=0.18)

    # ----- manage ------------------------------------------------------------
    with tab_manage:
        if not wallets:
            st.caption("Create a wallet first.")
            return
        wallet = wallet_select("Wallet", wallets, key="manage_wallet", show_balance=False)

        key_value_panel(
            [
                ("Name", wallet["name"]),
                ("Address", wallet["address"]),
                ("Public key", wallet["public_key"]),
                ("Private key", "Encrypted in the database - never displayed and never sent to the browser"),
                ("Balance", fmt_amount(wallet["balance"])),
                ("Available", fmt_amount(wallet["available"])),
            ],
            mono={"Address", "Public key"},
        )

        col_backup, col_rename, col_delete = st.columns(3)

        with col_backup:
            section("Backup")
            st.download_button(
                "Download encrypted keystore",
                data=node.export_keystore(wallet["address"]),
                file_name=f"securechain-{wallet['name'].replace(' ', '_')}.pem",
                mime="application/x-pem-file",
                icon=":material/download:",
                help="The key inside this file is encrypted with the wallet password.",
            )
            st.caption("Safe to store: useless without the password.")

        with col_rename:
            section("Rename")
            with st.form("rename_wallet", clear_on_submit=True):
                new_name = st.text_input("New name", max_chars=config.MAX_WALLET_NAME_LENGTH)
                if st.form_submit_button("Rename"):
                    try:
                        node.rename_wallet(wallet["address"], new_name)
                    except WalletError as exc:
                        st.error(str(exc))
                    else:
                        flash("success", f"Wallet renamed to '{new_name.strip()}'.")
                        st.rerun()

        with col_delete:
            section("Remove from this node")
            with st.form("delete_wallet", clear_on_submit=True):
                password = st.text_input("Wallet password", type="password", key="delete_password")
                if st.form_submit_button("Delete wallet"):
                    try:
                        node.delete_wallet(wallet["address"], password)
                    except WalletError as exc:
                        st.error(str(exc))
                    else:
                        flash("warning", f"Wallet '{wallet['name']}' ({short(wallet['address'])}) was removed "
                                         "from this node. Its coins remain on the blockchain.")
                        st.rerun()
            st.caption("Deleting removes the keys from this computer. Download the keystore first if "
                       "the wallet still holds coins.")
