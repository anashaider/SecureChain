"""Chain validation: re-verify every hash, link, proof and signature in the ledger."""

import streamlit as st

from ui.components import esc, page_header, render_html, section, short, stat_row, table

# Order of the five check lights shown on each block tile.
_CHECKS = [("hash_ok", "Block hash"), ("link_ok", "Previous-hash link"), ("pow_ok", "Proof-of-Work"),
           ("merkle_ok", "Merkle root"), ("transactions_ok", "Transactions and signatures")]


def _mark(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def _scanner(chain, report) -> str:
    """One animated tile per block; a scanning light sweeps across them in chain order."""
    tiles = []
    for position, result in enumerate(report.block_results):
        dots = "".join(
            f'<i class="{"na" if (position == 0 and name == "pow_ok") else "" if getattr(result, name) else "bad"}" '
            f'title="{esc(label)}: {"n/a" if (position == 0 and name == "pow_ok") else _mark(getattr(result, name))}"></i>'
            for name, label in _CHECKS
        )
        tiles.append(
            f'<div class="sc-scan-block {"" if result.ok else "bad"}" style="animation-delay:{min(position, 40) * 0.06:.2f}s">'
            f'<div class="sc-scan-title">{"Genesis" if position == 0 else f"Block #{position}"}</div>'
            f'<div class="sc-scan-hash">{esc(short(chain[position].hash, 6, 4))}</div>'
            f'<div class="sc-scan-dots">{dots}</div></div>'
        )
    legend = (
        '<div class="sc-legend"><span>Each block shows five checks, left to right: hash · link · proof-of-work · '
        "Merkle root · signatures</span>"
        '<span><i style="background:#34d399"></i>pass</span><span><i style="background:#f87171"></i>fail</span>'
        '<span><i style="background:#334155"></i>not applicable</span></div>'
    )
    return f'<div class="sc-scan">{"".join(tiles)}</div>{legend}'


def render(node) -> None:
    page_header(
        "Chain Validation",
        "Trust nothing that is stored: recompute and verify the entire blockchain, block by block.",
        eyebrow="Integrity",
    )

    if st.button("Run full validation", type="primary", icon=":material/verified_user:"):
        st.session_state["validation_runs"] = st.session_state.get("validation_runs", 0) + 1
    # The check is fast, so the page always shows a fresh result.
    report = node.validate_chain()

    if report.is_valid:
        st.success(
            f"Blockchain is VALID. Verified {report.blocks_checked} block(s) and "
            f"{report.transactions_checked} transaction(s): every hash, link, proof-of-work and signature is correct."
        )
    else:
        st.error(
            f"Blockchain is INVALID. {len(report.issues)} problem(s) found - the earliest in "
            f"block #{report.first_bad_block}. The ledger has been tampered with; sending and mining are disabled."
        )
        if node.is_tampered():
            st.info("This is the result of a simulated attack. Open the Attack Lab and click "
                    "'Restore original data' to undo it.")

    failed_blocks = sum(1 for result in report.block_results if not result.ok)
    stat_row([
        {"label": "Result", "value": "VALID" if report.is_valid else "INVALID", "hint": "Overall verdict",
         "tone": "ok" if report.is_valid else "bad"},
        {"label": "Blocks checked", "value": report.blocks_checked, "hint": "From genesis to the tip"},
        {"label": "Transactions checked", "value": report.transactions_checked, "hint": "IDs and ECDSA signatures"},
        {"label": "Blocks failing", "value": failed_blocks, "hint": f"{len(report.issues)} problem(s) in total",
         "tone": "bad" if failed_blocks else "ok"},
    ])

    section("Verification scan")
    # The run counter is part of the container key, so pressing the button replays the scan animation.
    with st.container(key=f"scan-{st.session_state.get('validation_runs', 0)}"):
        render_html(_scanner(node.blockchain.chain, report))

    if report.issues:
        section("Problems found")
        table(
            [
                {"Block": issue.block_index, "Check": issue.check.replace("_", " ").title(), "Details": issue.message}
                for issue in report.issues
            ]
        )

    chain = node.blockchain.chain
    with st.expander("Result per block (table)", expanded=not report.is_valid, icon=":material/table_rows:"):
        table(
            [
                {
                    "Block": result.index,
                    "Hash": short(chain[result.index].hash, 12, 6),
                    "Block hash": _mark(result.hash_ok),
                    "Previous-hash link": _mark(result.link_ok),
                    "Proof-of-Work": "n/a" if result.index == 0 else _mark(result.pow_ok),
                    "Merkle root": _mark(result.merkle_ok),
                    "Transactions and signatures": _mark(result.transactions_ok),
                    "Verdict": "VALID" if result.ok else "INVALID",
                }
                for result in report.block_results
            ],
            height=390 if len(report.block_results) > 10 else None,
        )

    with st.expander("What exactly is verified?", icon=":material/help:"):
        st.markdown(
            "- **Block hash** - the stored hash equals SHA-256 of the block header, recomputed now.\n"
            "- **Previous-hash link** - each block points to the real hash of the block before it.\n"
            "- **Proof-of-Work** - the hash starts with the required number of zeros.\n"
            "- **Merkle root** - the fingerprint of the block's transactions matches its contents.\n"
            "- **Transactions** - each transaction's data matches its ID and carries a valid ECDSA "
            "signature from the sender's key; rewards are correct; nothing is duplicated and no "
            "wallet ever spends more than it owns.\n\n"
            "Changing a single old transaction breaks several of these at once, and every block "
            "after it as well - that is what makes the ledger tamper-evident."
        )
