"""
Bridge between Python and the interactive visual component (ui/frontend/).

Each `*_payload` function turns real ledger state into plain JSON, and the
matching function below it hands that JSON to the browser.

Two rules are enforced here:

  1. ONLY PUBLIC DATA is sent: hashes, addresses, public keys' owners,
     amounts, signatures' validity. Private keys and passwords never
     leave Python (the payload builders do not even have access to them).
  2. The component is ONE-WAY. It never returns a value, so rotating the
     3D view or clicking a block cannot trigger a rerun or change
     Streamlit's session state.
"""

from pathlib import Path

import streamlit.components.v1 as components

import config
from security import Severity
from transactions import Transaction
from wallet import verify_signature

FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"
MAX_BLOCKS_3D = 60          # the 3D chain shows the most recent blocks
MAX_TX_PER_BLOCK = 12       # transactions listed in a block's side panel
MAX_NETWORK_EVENTS = 70     # particles in the transaction network
MAX_EXTERNAL_NODES = 8      # unknown addresses shown around the network

_component = components.declare_component("securechain_viz", path=str(FRONTEND_DIR))


def _render(view: str, data: dict, height: int, key: str) -> None:
    _component(view=view, data=data, height=height, key=key, default=None)


# --------------------------------------------------------------------------
# Small formatting helpers (kept here so this module has no UI dependencies)
# --------------------------------------------------------------------------
def _short(text: str, head: int = 8, tail: int = 4) -> str:
    text = str(text)
    return text if len(text) <= head + tail + 3 else f"{text[:head]}...{text[-tail:]}"


def _amount(value: float) -> str:
    return f"{value:,.2f} {config.COIN_SYMBOL}"


def _time(timestamp: float) -> str:
    from datetime import datetime

    try:
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
    except (OverflowError, OSError, ValueError, TypeError):
        return "invalid time"


def _party(address: str, book: dict[str, str]) -> str:
    if address == config.COINBASE_SENDER:
        return "Mining reward"
    return book.get(address) or _short(address)


def _signature_state(tx: Transaction) -> str:
    """'n/a' for mining rewards, otherwise 'valid' or 'invalid' (really verified)."""
    if tx.is_coinbase:
        return "n/a"
    return "valid" if tx.is_valid() else "invalid"


# --------------------------------------------------------------------------
# 3D blockchain
# --------------------------------------------------------------------------
def chain_payload(node, focus: int | None = None, animate: int | None = None) -> dict:
    """Real chain data + real validation results for the 3D chain view."""
    chain = node.blockchain.chain
    report = node.blockchain.validate()
    book = node.address_book()
    issues: dict[int, list[str]] = {}
    for issue in report.issues:
        issues.setdefault(issue.block_index, []).append(issue.message)

    first = max(0, len(chain) - MAX_BLOCKS_3D)
    blocks = []
    for position in range(first, len(chain)):
        block = chain[position]
        result = report.block_results[position]
        blocks.append(
            {
                "index": position,
                "hash": block.hash,
                "previous_hash": block.previous_hash,
                "merkle_root": block.merkle_root,
                "nonce": block.nonce,
                "difficulty": block.difficulty,
                "time": "Fixed genesis time" if position == 0 else _time(block.timestamp),
                "tx_count": len(block.transactions),
                "genesis": position == 0,
                "ok": result.ok,
                "checks": {
                    "hash": result.hash_ok,
                    "link": result.link_ok,
                    "pow": result.pow_ok,
                    "merkle": result.merkle_ok,
                    "transactions": result.transactions_ok,
                },
                "issues": issues.get(position, [])[:6],
                "txs": [
                    {
                        "id": tx.tx_id,
                        "type": "reward" if tx.is_coinbase else "payment",
                        "from": _party(tx.sender, book),
                        "to": _party(tx.receiver, book),
                        "amount": _amount(tx.amount),
                        "sig": _signature_state(tx),
                    }
                    for tx in block.transactions[:MAX_TX_PER_BLOCK]
                ],
            }
        )
    return {
        "blocks": blocks,
        "total": len(chain),
        "valid": report.is_valid,
        "focus": focus if focus is not None and focus >= first else None,
        "animate": animate if animate is not None and animate >= first else None,
    }


def chain_3d(node, height: int = 460, focus: int | None = None, animate: int | None = None,
             key: str = "chain3d") -> None:
    """Interactive 3D blockchain (drag to rotate, scroll to zoom, click a block)."""
    _render("chain", chain_payload(node, focus=focus, animate=animate), height, key)


# --------------------------------------------------------------------------
# 3D transaction network
# --------------------------------------------------------------------------
def classify_transactions(node) -> tuple[dict[str, str], list[dict]]:
    """
    Split the fraud log into:
      flagged   {tx_id: highest severity}  for ACCEPTED transactions with a
                MEDIUM-or-higher behaviour alert
      rejected  list of fraud-log rows for transactions the node refused
    """
    flagged: dict[str, str] = {}
    rejected: list[dict] = []
    for alert in node.get_alerts():
        if alert["rule"].startswith("REJECTED_"):
            rejected.append(alert)
        elif alert["tx_id"] and alert["severity"] != Severity.LOW:
            current = flagged.get(alert["tx_id"])
            if current is None or Severity.ORDER.index(alert["severity"]) > Severity.ORDER.index(current):
                flagged[alert["tx_id"]] = alert["severity"]
    return flagged, rejected


def network_payload(node) -> dict:
    """Wallets, counterparties and every transaction outcome, for the network view."""
    wallets = node.list_wallets()
    book = {w["address"]: w["name"] for w in wallets}
    flagged, rejected = classify_transactions(node)
    history = node.blockchain.get_transactions()          # oldest first

    # ----- events (one particle each) ---------------------------------------
    events = []
    for entry in history:
        tx = entry["tx"]
        if tx.tx_id in flagged:
            status = "flagged"
        elif entry["status"] == "Pending":
            status = "pending"
        else:
            status = "confirmed"
        events.append({"from": tx.sender, "to": tx.receiver, "amount": tx.amount,
                       "status": status, "time": tx.timestamp})
    for alert in rejected:
        if alert["sender"] and alert["receiver"] and alert["sender"] != alert["receiver"]:
            events.append({"from": alert["sender"], "to": alert["receiver"], "amount": alert["amount"],
                           "status": "rejected", "time": alert["created_at"]})
    events.sort(key=lambda e: e["time"])
    stats = {name: sum(1 for e in events if e["status"] == name)
             for name in ("confirmed", "pending", "flagged", "rejected")}
    events = events[-MAX_NETWORK_EVENTS:]

    # ----- nodes ------------------------------------------------------------
    externals: list[str] = []
    for event in reversed(events):                          # most recent unknown addresses first
        for address in (event["from"], event["to"]):
            if address not in book and address != config.COINBASE_SENDER and address not in externals:
                externals.append(address)
    externals = externals[:MAX_EXTERNAL_NODES]
    known = set(book) | set(externals) | {config.COINBASE_SENDER}
    events = [e for e in events if e["from"] in known and e["to"] in known]

    def node_stats(address: str) -> dict:
        sent = received = count = 0
        flagged_count = 0
        activity = []
        for entry in history:
            tx = entry["tx"]
            if address not in (tx.sender, tx.receiver):
                continue
            count += 1
            incoming = tx.receiver == address
            if entry["status"] == "Confirmed":
                if incoming:
                    received += tx.amount
                else:
                    sent += tx.amount
            is_flagged = tx.tx_id in flagged
            if is_flagged and not incoming:
                flagged_count += 1
            activity.append({
                "t": tx.timestamp,
                "time": _time(tx.timestamp),
                "direction": "in" if incoming else "out",
                "peer": _party(tx.sender if incoming else tx.receiver, book),
                "amount": _amount(tx.amount),
                "status": "flagged" if is_flagged else entry["status"].lower(),
            })
        rejected_count = 0
        for alert in rejected:
            if alert["sender"] == address:
                rejected_count += 1
                activity.append({
                    "t": alert["created_at"],
                    "time": _time(alert["created_at"]),
                    "direction": "out",
                    "peer": _party(alert["receiver"], book) if alert["receiver"] else "unknown",
                    "amount": _amount(alert["amount"]),
                    "status": "rejected",
                })
        activity.sort(key=lambda item: item["t"], reverse=True)
        for item in activity:
            del item["t"]
        return {
            "sent_text": _amount(sent), "received_text": _amount(received), "tx_count": count,
            "flagged": flagged_count, "rejected": rejected_count,
            "risk": "rejected" if rejected_count else "flagged" if flagged_count else "ok",
            "history": activity[:10],
        }

    nodes = []
    if any(e["from"] == config.COINBASE_SENDER for e in events):
        nodes.append({"id": config.COINBASE_SENDER, "label": "Coinbase", "kind": "mint", "balance": 0,
                      "balance_text": "", "available_text": "", "sent_text": "", "received_text": "",
                      "tx_count": 0, "flagged": 0, "rejected": 0, "risk": "ok", "history": []})
    for wallet in wallets:
        nodes.append({"id": wallet["address"], "label": wallet["name"], "kind": "wallet",
                      "balance": wallet["balance"], "balance_text": _amount(wallet["balance"]),
                      "available_text": _amount(wallet["available"]), **node_stats(wallet["address"])})
    for address in externals:
        balance = node.blockchain.get_balance(address)
        nodes.append({"id": address, "label": _short(address, 6, 4), "kind": "external",
                      "balance": balance, "balance_text": _amount(balance),
                      "available_text": _amount(node.blockchain.get_available_balance(address)),
                      **node_stats(address)})

    for event in events:
        event["amount_text"] = _amount(event["amount"])
        del event["time"]
    return {"nodes": nodes, "events": events, "stats": stats}


def tx_network(node, height: int = 540, key: str = "txnet") -> None:
    """Interactive 3D transaction network (click a wallet for its real history)."""
    _render("network", network_payload(node), height, key)


# --------------------------------------------------------------------------
# Proof-of-Work replay
# --------------------------------------------------------------------------
def pow_payload(node, block_index: int, attempts: int, duration: float, miner: str, autoplay: bool) -> dict:
    """Everything the browser needs to RE-COMPUTE the block's Proof-of-Work itself."""
    chain = node.blockchain.chain
    block = chain[block_index]
    return {
        "index": block_index,
        "prefix": block.header_prefix(),          # header text; the browser appends the nonce and hashes
        "nonce": block.nonce,
        "hash": block.hash,
        "difficulty": block.difficulty,
        "attempts": attempts,
        "duration": duration,
        "miner": miner,
        "reward": _amount(node.blockchain.mining_reward),
        "tx_count": len(block.transactions),
        "previous_hash": block.previous_hash,
        "chain": [{"index": i, "hash": chain[i].hash} for i in range(max(0, block_index - 3), block_index)],
        "autoplay": autoplay,
        "token": block.hash,
    }


def pow_replay(node, block_index: int, attempts: int, duration: float, miner: str,
               autoplay: bool = False, height: int = 400, key: str = "pow") -> None:
    _render("pow", pow_payload(node, block_index, attempts, duration, miner, autoplay), height, key)


# --------------------------------------------------------------------------
# Tampering: before / after + animated hash comparison
# --------------------------------------------------------------------------
def tamper_payload(node) -> dict | None:
    """
    Compare the original block (from the tamper backup) with what is stored
    now. Returns None when no simulated tampering is active.
    """
    comparison = node.get_tamper_comparison()
    if not comparison:
        return None
    entry = comparison[0]
    index = entry["index"]
    original, current = entry["original"], entry["current"]
    chain = node.blockchain.chain
    block = chain[index]

    # Which transaction was edited?
    position = next(
        (i for i, (a, b) in enumerate(zip(original["transactions"], current["transactions"])) if a != b), 0
    )
    before = Transaction.from_dict(original["transactions"][position])
    after = Transaction.from_dict(current["transactions"][position])

    def signature_text(tx: Transaction) -> str:
        if tx.is_coinbase:
            return "not required (mining reward)"
        ok = verify_signature(tx.sender_public_key, tx.payload(), tx.signature)
        return "VALID" if ok else "INVALID - does not match this data"

    fields = [
        ("Amount", _amount(before.amount), _amount(after.amount)),
        ("Transaction ID", _short(before.tx_id, 14, 8), _short(after.tx_id, 14, 8)),
        ("Signature check", signature_text(before), signature_text(after)),
        ("Merkle root", _short(original["merkle_root"], 14, 8), _short(current["merkle_root"], 14, 8)),
        ("Block hash", _short(original["hash"], 14, 8), _short(current["hash"], 14, 8)),
    ]
    comparisons = [
        {
            "title": "1 · Transaction fingerprint",
            "explain": "SHA-256 of the transaction data as it is stored NOW (computed in your browser) "
                       "versus the transaction ID recorded in the block.",
            "a": {"label": "Recomputed now", "compute": after.payload().decode("utf-8")},
            "b": {"label": "Stored transaction ID", "value": after.tx_id},
        },
        {
            "title": "2 · Block header hash",
            "explain": "SHA-256 of the block header (computed in your browser) versus the block hash "
                       "that was found by mining.",
            "a": {"label": "Recomputed now", "compute": block.header_prefix() + str(block.nonce)},
            "b": {"label": "Original mined hash", "value": original["hash"]},
        },
    ]
    if index + 1 < len(chain):
        comparisons.append(
            {
                "title": f"3 · Chain link to block #{index + 1}",
                "explain": f"The hash block #{index} has now versus the previous-hash that "
                           f"block #{index + 1} stored when it was mined.",
                "a": {"label": f"Block #{index} hash now", "value": block.hash},
                "b": {"label": f"Block #{index + 1} previous-hash", "value": chain[index + 1].previous_hash},
            }
        )
    return {
        "title": f"Integrity check · block #{index}, transaction #{position}",
        "token": f"{block.hash}:{after.tx_id}:{after.amount}",
        "block_index": index,
        "tx_position": position,
        "fields": [{"label": label, "before": a, "after": b, "changed": a != b} for label, a, b in fields],
        "comparisons": comparisons,
    }


def hash_diff(payload: dict, height: int = 640, key: str = "hashdiff") -> None:
    _render("hashdiff", payload, height, key)
