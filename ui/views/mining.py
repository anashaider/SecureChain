"""
Mining: turn pending transactions into a new block with Proof-of-Work.

Nothing on this page is simulated:
  * while the node mines, the console shows the REAL number of hashes tried
    and the last real candidate hash (reported by the mining loop itself);
  * afterwards the Proof-of-Work panel recomputes the winning hash in the
    browser and compares it with the hash the node stored.
"""

import time

import streamlit as st

import config
from node import ChainIntegrityError
from transactions import TransactionError
from ui import viz
from ui.components import (
    esc,
    flash,
    fmt_amount,
    fmt_time,
    need_wallets_notice,
    page_header,
    party_label,
    render_html,
    section,
    short,
    stat_row,
    table,
    wallet_select,
)


def _console_html(attempts: int, last_hash: str, difficulty: int, elapsed: float, expected: int) -> str:
    """The live mining console (real numbers from the mining loop)."""
    rate = attempts / elapsed if elapsed > 0 else 0
    width = min(100.0, attempts / expected * 100) if expected else 0
    zeros = len(last_hash) - len(last_hash.lstrip("0"))
    shown = (f'<span style="color:#34d399">{esc(last_hash[:zeros])}</span><b>{esc(last_hash[zeros:zeros + 1])}</b>'
             f"{esc(last_hash[zeros + 1:])}") if last_hash else "starting..."
    return (
        '<div class="sc-panel sc-mine">'
        '<div class="sc-card-label">Mining in progress · live from the node</div>'
        f'<div class="sc-mine-num">{attempts:,} <span class="sc-card-unit">hashes tried</span></div>'
        f'<div class="sc-mine-bar"><i style="width:{width:.1f}%"></i></div>'
        f'<div class="sc-card-hint">{rate:,.0f} hashes/s · {elapsed:.1f} s · on average about {expected:,} attempts are '
        f"needed for {difficulty} leading zeros</div>"
        f'<div class="sc-mine-hash">last candidate&nbsp; {shown}</div>'
        "</div>"
    )


def render(node) -> None:
    page_header(
        "Mining",
        "Proof-of-Work: search for a nonce that makes the block hash start with enough zeros.",
        eyebrow="Consensus",
    )
    if need_wallets_notice(node):
        return

    wallets = node.list_wallets()
    book = node.address_book()
    chain = node.blockchain
    pending = chain.pending_transactions

    stat_row([
        {"label": "Pending transactions", "value": len(pending), "hint": "Will be included in the next block",
         "tone": "warn" if pending else ""},
        {"label": "Next block", "value": f"#{len(chain.chain)}", "hint": f"Builds on {short(chain.latest_block.hash, 10, 6)}"},
        {"label": "Block reward", "value": int(chain.mining_reward), "unit": config.COIN_SYMBOL,
         "hint": "New coins paid to the miner", "tone": "purple"},
        {"label": "Difficulty", "value": chain.difficulty, "hint": f"About {16 ** chain.difficulty:,} attempts on average"},
    ])

    left, right = st.columns([3, 2])

    with left:
        section("Pending transaction pool")
        table(
            [
                {
                    "Time": fmt_time(tx.timestamp),
                    "From": party_label(tx.sender, book),
                    "To": party_label(tx.receiver, book),
                    "Amount": fmt_amount(tx.amount),
                    "Transaction ID": short(tx.tx_id, 12, 8),
                }
                for tx in pending
            ],
            empty_message="The pool is empty. You can still mine: the block will contain only the reward.",
        )
        console = st.empty()     # the live mining console appears here while the node works

    with right:
        section("Mine a block")
        miner = wallet_select("Miner wallet (receives the reward)", wallets, key="mining_miner")
        difficulty = st.slider(
            "Difficulty (leading zeros)",
            min_value=config.MIN_DIFFICULTY,
            max_value=config.MAX_DIFFICULTY,
            value=chain.difficulty,
            key="mining_difficulty",
            help="Each extra zero makes mining about 16 times harder.",
        )
        st.caption(f"Expected work: about {16 ** difficulty:,} hash attempts.")
        if difficulty != chain.difficulty:
            # Apply the new difficulty straight away (not only when a block is mined),
            # so it is remembered when you leave this page and the tiles above stay correct.
            node.set_difficulty(difficulty)
            st.rerun()

        if st.button("Mine block", type="primary", icon=":material/bolt:"):
            expected = 16 ** difficulty
            started = time.perf_counter()

            def on_progress(attempts: int, last_hash: str) -> None:
                console.markdown(
                    _console_html(attempts, last_hash, difficulty, time.perf_counter() - started, expected),
                    unsafe_allow_html=True,
                )

            try:
                node.set_difficulty(difficulty)
                console.markdown(_console_html(0, "", difficulty, 0.0, expected), unsafe_allow_html=True)
                result = node.mine(miner["address"], on_progress=on_progress)
            except (ChainIntegrityError, TransactionError, ValueError) as exc:
                console.empty()
                st.error(str(exc))
            else:
                block = result.block
                st.session_state["last_mined"] = {
                    "index": block.index,
                    "hash": block.hash,
                    "attempts": result.attempts,
                    "duration": result.duration,
                    "miner": miner["name"],
                    "autoplay": True,
                }
                st.session_state["animate_block"] = block.index
                flash("success", f"Block #{block.index} mined in {result.duration:.2f}s after "
                                 f"{result.attempts:,} attempts. {miner['name']} earned "
                                 f"{fmt_amount(chain.mining_reward)}.")
                for tx, reason in result.rejected:
                    flash("warning", f"Dropped pending transaction {short(tx.tx_id)}: {reason}")
                st.rerun()

    # ----- verification of the block mined in this session --------------------------
    last = st.session_state.get("last_mined")
    if last and last["index"] < len(chain.chain) and chain.chain[last["index"]].hash == last["hash"]:
        section(f"Proof-of-Work verification · block #{last['index']}")
        viz.pow_replay(
            node, last["index"], last["attempts"], last["duration"], last["miner"],
            autoplay=last.pop("autoplay", False), height=410, key="mining_pow",
        )
        section("The new block in the chain")
        viz.chain_3d(node, height=340, animate=st.session_state.pop("animate_block", None), key="mining_chain")
    else:
        render_html(
            '<div class="sc-panel"><div class="sc-note">Mine a block to see its Proof-of-Work replayed and '
            "independently re-verified in your browser, and the new block joining the 3D chain.</div></div>"
        )
