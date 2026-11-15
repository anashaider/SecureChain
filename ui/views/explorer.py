"""Blockchain explorer: fly through the 3D chain, inspect blocks, search by hash or transaction ID."""

import streamlit as st

from ui import viz
from ui.components import (
    fmt_amount,
    fmt_time,
    key_value_panel,
    page_header,
    party_label,
    section,
    short,
    table,
)


def render(node) -> None:
    page_header(
        "Blockchain Explorer",
        "Every block stores the hash of the block before it - that link is the chain. Click any block in the 3D view.",
        eyebrow="Ledger",
    )

    chain = node.blockchain.chain
    book = node.address_book()
    report = node.blockchain.validate()

    # ----- search ------------------------------------------------------------
    query = st.text_input("Search by block hash or transaction ID (full value or the first characters)",
                          key="explorer_search", placeholder="e.g. 0000a3f1...").strip().lower()
    # Jump only when the search text changes, so the slider stays usable afterwards.
    is_new_query = query != st.session_state.get("explorer_last_query", "")
    st.session_state["explorer_last_query"] = query
    if query and is_new_query:
        found = _search(chain, query)
        if found is None:
            st.warning("No block or transaction starts with that value.")
        else:
            block_index, description = found
            st.success(f"Found {description} in block #{block_index}.")
            st.session_state["explorer_block"] = block_index

    # ----- block picker ------------------------------------------------------
    if st.session_state.get("explorer_block", 0) >= len(chain):
        st.session_state["explorer_block"] = len(chain) - 1
    st.session_state.setdefault("explorer_block", len(chain) - 1)
    if len(chain) > 1:
        selected = st.slider("Block", 0, len(chain) - 1, key="explorer_block",
                             help="Moving the slider flies the 3D camera to that block.")
    else:
        selected = 0
        st.caption("Only the genesis block exists so far. Mine a block to extend the chain.")

    # ----- interactive 3D chain (the camera follows the slider) ----------------
    viz.chain_3d(node, height=500, focus=selected, key="explorer_chain")

    # ----- block details -----------------------------------------------------
    block = chain[selected]
    result = report.block_results[selected]
    section(f"Block #{selected}" + (" · Genesis" if selected == 0 else ""))
    if not result.ok:
        problems = [issue.message for issue in report.issues if issue.block_index == selected]
        st.error("This block fails validation: " + " ".join(problems))

    key_value_panel(
        [
            ("Hash", block.hash),
            ("Previous hash", block.previous_hash),
            ("Merkle root", block.merkle_root),
            ("Timestamp", "Fixed genesis time" if selected == 0 else fmt_time(block.timestamp)),
            ("Nonce", f"{block.nonce:,}"),
            ("Difficulty", f"{block.difficulty} leading zeros" if selected else "None (genesis is not mined)"),
            ("Transactions", str(len(block.transactions))),
            ("Integrity", "All checks passed" if result.ok else "FAILED"),
        ],
        mono={"Hash", "Previous hash", "Merkle root"},
        tone="" if result.ok else "bad",
    )

    section("Transactions in this block")
    table(
        [
            {
                "#": position,
                "Type": "Mining reward" if tx.is_coinbase else "Payment",
                "From": party_label(tx.sender, book),
                "To": party_label(tx.receiver, book),
                "Amount": fmt_amount(tx.amount),
                "Signature": "n/a" if tx.is_coinbase else ("Valid" if tx.is_valid() else "INVALID"),
                "Transaction ID": short(tx.tx_id, 12, 8),
            }
            for position, tx in enumerate(block.transactions)
        ],
        empty_message="The genesis block contains no transactions.",
    )

    with st.expander("Raw block data (JSON)", icon=":material/data_object:"):
        st.json(block.to_dict(), expanded=False)


def _search(chain, query: str):
    """Find a block hash or transaction ID starting with `query`."""
    for position, block in enumerate(chain):
        if block.hash.startswith(query):
            return position, "block hash"
        for tx in block.transactions:
            if tx.tx_id.startswith(query):
                return position, f"transaction {short(tx.tx_id, 10, 6)}"
    return None
