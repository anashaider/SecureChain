"""
Tests for the command-center additions:

  * the data sent to the browser visualizations is real, JSON-safe and
    never contains private keys or passwords;
  * the small backend hooks added for the UI (mining progress, database
    re-sync, tamper comparison) behave correctly.
"""

import hashlib
import json

import pytest

pytest.importorskip("streamlit")

from blockchain import Block  # noqa: E402
from node import SecureChainNode  # noqa: E402
from transactions import Transaction, TransactionError  # noqa: E402
from ui import viz  # noqa: E402
from wallet import Wallet  # noqa: E402

PASSWORD = "correct-horse-battery"


@pytest.fixture
def busy(node):
    """A node with wallets, confirmed payments, a flagged payment and a rejected forgery."""
    alice = node.create_wallet("Alice", PASSWORD)["address"]
    bob = node.create_wallet("Bob", PASSWORD)["address"]
    for _ in range(3):
        node.mine(alice)
    node.send(alice, PASSWORD, bob, 20)
    node.mine(bob)                                   # block 4: reward + payment
    node.send(alice, PASSWORD, bob, 250)             # large + drain -> flagged, stays pending
    attacker = Wallet.create()
    forged = Transaction(sender=alice, receiver=attacker.address, amount=5)
    forged.sender_public_key = node.get_wallet_info(alice)["public_key"]
    forged.tx_id = forged.compute_hash()
    forged.signature = attacker.sign(forged.payload())
    with pytest.raises(TransactionError):
        node.submit_transaction(forged)
    return node, alice, bob


def private_material(node, address: str) -> list[str]:
    """Every textual form of a wallet's secrets that must never reach the browser."""
    wallet = node.unlock_wallet(address, PASSWORD)
    secret = wallet._private_key.private_numbers().private_value
    return [format(secret, "x"), str(secret), PASSWORD, "PRIVATE KEY", node.export_keystore(address)[40:90]]


# ----- payloads -------------------------------------------------------------------
def test_chain_payload_matches_the_real_chain(busy):
    node, _, _ = busy
    payload = viz.chain_payload(node)
    chain = node.blockchain.chain
    assert payload["total"] == len(chain) and payload["valid"] is True
    assert [b["hash"] for b in payload["blocks"]] == [b.hash for b in chain]
    assert [b["nonce"] for b in payload["blocks"]] == [b.nonce for b in chain]
    assert payload["blocks"][0]["genesis"] and all(b["ok"] for b in payload["blocks"])
    block4 = payload["blocks"][4]
    assert block4["tx_count"] == 2
    assert [tx["sig"] for tx in block4["txs"]] == ["n/a", "valid"]
    assert block4["txs"][1]["from"] == "Alice" and block4["txs"][1]["to"] == "Bob"


def test_chain_payload_marks_tampered_blocks_invalid(busy):
    node, _, _ = busy
    node.tamper_with_transaction(4, 1, 9999)
    payload = viz.chain_payload(node)
    assert payload["valid"] is False
    assert payload["blocks"][4]["ok"] is False
    assert payload["blocks"][4]["checks"]["transactions"] is False
    assert payload["blocks"][4]["issues"]
    assert payload["blocks"][4]["txs"][1]["sig"] == "invalid"
    assert payload["blocks"][3]["ok"] is True


def test_network_payload_classifies_every_outcome(busy):
    node, alice, bob = busy
    payload = viz.network_payload(node)
    assert payload["stats"] == {"confirmed": 5, "pending": 0, "flagged": 1, "rejected": 1}
    kinds = {n["label"]: n["kind"] for n in payload["nodes"]}
    assert kinds["Alice"] == "wallet" and kinds["Coinbase"] == "mint"
    assert "external" in kinds.values()                       # the attacker's address
    by_id = {n["id"]: n for n in payload["nodes"]}
    assert by_id[alice]["risk"] == "rejected" and by_id[alice]["rejected"] == 1 and by_id[alice]["flagged"] == 1
    assert by_id[bob]["risk"] == "ok"
    assert by_id[alice]["balance"] == node.blockchain.get_balance(alice)
    statuses = {h["status"] for h in by_id[alice]["history"]}
    assert {"confirmed", "flagged", "rejected"} <= statuses
    known = set(by_id)
    assert all(e["from"] in known and e["to"] in known for e in payload["events"])


def test_pow_payload_lets_the_browser_recompute_the_hash(busy):
    node, _, _ = busy
    payload = viz.pow_payload(node, 4, attempts=123, duration=0.5, miner="Bob", autoplay=True)
    block = node.blockchain.chain[4]
    recomputed = hashlib.sha256((payload["prefix"] + str(payload["nonce"])).encode()).hexdigest()
    assert recomputed == payload["hash"] == block.hash
    assert payload["hash"].startswith("0" * payload["difficulty"])
    assert payload["previous_hash"] == node.blockchain.chain[3].hash
    assert [b["index"] for b in payload["chain"]] == [1, 2, 3]


@pytest.mark.parametrize("smart", [False, True])
def test_tamper_payload_shows_a_real_mismatch(busy, smart):
    node, _, _ = busy
    assert viz.tamper_payload(node) is None                   # nothing tampered yet
    node.mine(node.list_wallets()[0]["address"])              # a block after #4, so the chain link can break
    node.tamper_with_transaction(4, 1, 9999, recompute_hashes=smart)
    payload = viz.tamper_payload(node)
    assert payload["block_index"] == 4 and payload["tx_position"] == 1
    changed = {f["label"] for f in payload["fields"] if f["changed"]}
    assert {"Amount", "Signature check"} <= changed

    def resolve(side):
        return hashlib.sha256(side["compute"].encode()).hexdigest() if "compute" in side else side["value"]

    mismatches = [c["title"] for c in payload["comparisons"] if resolve(c["a"]) != resolve(c["b"])]
    assert mismatches, "at least one hash comparison must expose the tampering"
    if smart:      # attacker fixed the tx ID, so the block header / chain link expose it instead
        assert any("header" in title or "link" in title for title in mismatches)
    else:
        assert any("fingerprint" in title for title in mismatches)


def test_no_secret_ever_reaches_the_browser(busy):
    node, alice, bob = busy
    node.mine(alice)
    node.tamper_with_transaction(4, 1, 9999)
    sent_to_browser = json.dumps([                            # also proves every payload is JSON-safe
        viz.chain_payload(node),
        viz.network_payload(node),
        viz.pow_payload(node, 4, 10, 0.1, "Bob", False),
        viz.tamper_payload(node),
    ])
    node.restore_tampering()
    for address in (alice, bob):
        for secret in private_material(node, address):
            assert secret not in sent_to_browser


def test_frontend_files_are_shipped_with_the_project():
    for name in ("index.html", "core.js", "chain.js", "network.js", "pow.js", "hashdiff.js", "viz.css", "three.min.js"):
        assert (viz.FRONTEND_DIR / name).is_file(), name
    html = (viz.FRONTEND_DIR / "index.html").read_text(encoding="utf-8")
    assert "http://" not in html and "https://" not in html   # nothing is loaded from the internet


# ----- backend hooks added for the UI ------------------------------------------------
def test_mining_reports_real_progress():
    block = Block(index=1, timestamp=1700000000.0, transactions=[], previous_hash="a" * 64, difficulty=3)
    calls = []
    attempts = block.mine(on_progress=lambda count, last: calls.append((count, last)), progress_every=100)
    assert block.has_valid_proof() and attempts == block.nonce + 1
    assert [count for count, _ in calls] == list(range(100, attempts, 100))
    prefix = block.header_prefix()
    for count, last_hash in calls[:5]:                         # each reported hash is a real failed attempt
        assert last_hash == hashlib.sha256((prefix + str(count - 1)).encode()).hexdigest()
        assert not last_hash.startswith("000")


def test_mining_without_a_callback_is_unchanged():
    a = Block(index=1, timestamp=1700000000.0, transactions=[], previous_hash="a" * 64, difficulty=3)
    b = Block(index=1, timestamp=1700000000.0, transactions=[], previous_hash="a" * 64, difficulty=3)
    assert a.mine() == b.mine(on_progress=lambda *_: None, progress_every=7)
    assert a.hash == b.hash and a.nonce == b.nonce


def test_node_mine_passes_progress_through(node):
    miner = node.create_wallet("Miner", PASSWORD)["address"]
    node.set_difficulty(4)
    seen = []
    for _ in range(3):                                         # at difficulty 4 a block almost always needs > 20,000 attempts
        result = node.mine(miner, on_progress=lambda count, last: seen.append(count))
        if result.attempts > 20_000:
            assert seen and seen[0] == 20_000
            break


def test_sync_reloads_when_another_process_changed_the_database(node):
    """Two nodes on one file: the second must notice what the first one wrote."""
    other = SecureChainNode(db_path=node.db.path, difficulty=2)
    assert other.sync() is False                               # nothing changed yet
    wallet = node.create_wallet("Alice", PASSWORD)["address"]
    node.mine(wallet)
    node.mine(wallet)
    assert len(other.blockchain.chain) == 1                    # stale copy in memory
    assert other.sync() is True
    assert other.blockchain.chain == node.blockchain.chain
    assert other.blockchain.get_balance(wallet) == 200
    assert other.sync() is False                               # already up to date
    node.send(wallet, PASSWORD, Wallet.create().address, 5)    # pending transactions count too
    assert other.sync() is True
    assert len(other.blockchain.pending_transactions) == 1


def test_tamper_comparison_is_read_only_and_accurate(busy):
    node, _, _ = busy
    assert node.get_tamper_comparison() == []
    node.tamper_with_transaction(4, 1, 9999)
    comparison = node.get_tamper_comparison()
    assert len(comparison) == 1 and comparison[0]["index"] == 4
    assert comparison[0]["original"]["transactions"][1]["amount"] == 20
    assert comparison[0]["current"]["transactions"][1]["amount"] == 9999
    assert node.is_tampered()                                  # looking did not change anything
    node.restore_tampering()
    assert node.get_tamper_comparison() == [] and node.validate_chain().is_valid
