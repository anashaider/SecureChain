"""
Integration tests: the whole system working together through SecureChainNode.

The section "Required demonstrations" contains one test for each scenario
the project must demonstrate.
"""

import pytest

import config
from node import DEMO_PASSWORD, ChainIntegrityError, SecureChainNode
from security import Rule, Severity
from transactions import (
    DoubleSpendError,
    InsufficientBalanceError,
    InvalidSignatureError,
    InvalidTransactionError,
    Transaction,
)
from wallet import Wallet, WalletError

PASSWORD = "correct-horse-battery"


@pytest.fixture
def funded(node):
    """Node with wallets Alice (300 coins after 3 mined blocks), Bob and Charlie."""
    alice = node.create_wallet("Alice", PASSWORD)
    bob = node.create_wallet("Bob", PASSWORD)
    charlie = node.create_wallet("Charlie", PASSWORD)
    for _ in range(3):
        node.mine(alice["address"])
    return node, alice["address"], bob["address"], charlie["address"]


def logged_rules(node) -> list[str]:
    return [alert["rule"] for alert in node.get_alerts()]


# =============================================================================
# Required demonstrations
# =============================================================================
def test_demo_1_successful_signed_transaction(funded):
    node, alice, bob, _ = funded
    result = node.send(alice, PASSWORD, bob, 25)
    tx = result.transaction
    assert tx.is_valid() and tx.signature
    assert tx in node.blockchain.pending_transactions

    node.mine(bob)
    assert node.blockchain.get_balance(alice) == 275
    assert node.blockchain.get_balance(bob) == 25 + config.MINING_REWARD
    assert node.validate_chain().is_valid


def test_demo_2_forged_signature_is_rejected(funded):
    node, alice, _, _ = funded
    attacker = Wallet.create()
    forged = Transaction(sender=alice, receiver=attacker.address, amount=100)
    forged.sender_public_key = node.get_wallet_info(alice)["public_key"]
    forged.tx_id = forged.compute_hash()
    forged.signature = attacker.sign(forged.payload())

    with pytest.raises(InvalidSignatureError):
        node.submit_transaction(forged)
    assert node.blockchain.pending_transactions == []
    assert node.blockchain.get_available_balance(alice) == 300
    assert logged_rules(node)[0] == Rule.FORGED_SIGNATURE
    assert node.get_alerts()[0]["severity"] == Severity.CRITICAL


def test_demo_3_insufficient_balance_is_rejected(funded):
    node, alice, bob, _ = funded
    with pytest.raises(InsufficientBalanceError):
        node.send(alice, PASSWORD, bob, 300.01)
    with pytest.raises(InsufficientBalanceError):
        node.send(bob, PASSWORD, alice, 1)
    assert node.blockchain.pending_transactions == []
    assert logged_rules(node).count(Rule.INSUFFICIENT_BALANCE) == 2


def test_demo_4_double_spending_is_prevented(funded):
    node, alice, bob, charlie = funded
    first = node.send(alice, PASSWORD, bob, 250).transaction        # accepted
    with pytest.raises(DoubleSpendError):
        node.send(alice, PASSWORD, charlie, 250)                    # same coins again
    with pytest.raises(DoubleSpendError):
        node.submit_transaction(first)                              # replay of the same tx

    node.mine(bob)
    with pytest.raises(DoubleSpendError):
        node.submit_transaction(first)                              # replay after confirmation
    assert node.blockchain.get_balance(bob) == 250 + config.MINING_REWARD
    assert node.blockchain.get_balance(charlie) == 0
    assert logged_rules(node).count(Rule.DOUBLE_SPEND) == 3


def test_demo_5_suspicious_transactions_are_detected(funded):
    node, alice, bob, charlie = funded
    # Large payment to a new recipient that also drains most of the wallet
    result = node.send(alice, PASSWORD, bob, 280)
    fired = {alert.rule for alert in result.alerts}
    assert fired == {Rule.LARGE_TRANSACTION, Rule.BALANCE_DRAIN, Rule.FIRST_TIME_RECIPIENT}
    assert result.risk_level in (Severity.HIGH, Severity.CRITICAL)

    # Rapid-fire small payments trigger the velocity rule
    velocity_seen = False
    for _ in range(4):
        alerts = node.send(alice, PASSWORD, charlie, 1).alerts
        velocity_seen = velocity_seen or any(a.rule == Rule.HIGH_VELOCITY for a in alerts)
    assert velocity_seen

    # Everything is persisted in the fraud log
    rules = set(logged_rules(node))
    assert {Rule.LARGE_TRANSACTION, Rule.HIGH_VELOCITY, Rule.FIRST_TIME_RECIPIENT} <= rules
    # Flagged transactions are still accepted (alerts do not block)
    assert len(node.blockchain.pending_transactions) == 5


def test_demo_6_blockchain_mining(funded):
    node, alice, bob, _ = funded
    node.send(alice, PASSWORD, bob, 10)
    height = len(node.blockchain.chain)
    result = node.mine(bob)

    block = result.block
    assert len(node.blockchain.chain) == height + 1
    assert block.hash.startswith("0" * block.difficulty)
    assert block.previous_hash == node.blockchain.chain[-2].hash
    assert block.transactions[0].is_coinbase and block.transactions[0].receiver == bob
    assert len(block.transactions) == 2
    assert node.blockchain.pending_transactions == []


def test_demo_7_historical_tampering_is_detected(funded):
    node, alice, bob, _ = funded
    node.send(alice, PASSWORD, bob, 10)
    node.mine(alice)                      # block 4 holds the payment
    node.mine(alice)                      # block 5 on top
    assert node.validate_chain().is_valid

    original = node.tamper_with_transaction(block_index=4, tx_position=1, new_amount=9999)
    assert original == 10

    report = node.validate_chain()
    assert not report.is_valid
    assert report.first_bad_block == 4
    assert logged_rules(node)[0] == Rule.CHAIN_TAMPERING

    # A corrupted ledger refuses new work
    with pytest.raises(ChainIntegrityError):
        node.send(alice, PASSWORD, bob, 1)
    with pytest.raises(ChainIntegrityError):
        node.mine(alice)

    # Restoring the original block heals the chain
    assert node.restore_tampering() == 1
    assert node.validate_chain().is_valid
    assert not node.is_tampered()
    node.send(alice, PASSWORD, bob, 1)


def test_sophisticated_tampering_with_recomputed_hashes_is_detected(funded):
    node, alice, bob, _ = funded
    node.send(alice, PASSWORD, bob, 10)
    node.mine(alice)
    node.mine(alice)
    node.tamper_with_transaction(4, 1, 9999, recompute_hashes=True)
    report = node.validate_chain()
    failed = {issue.check for issue in report.issues}
    assert "PREVIOUS_HASH" in failed and "TRANSACTION" in failed
    node.restore_tampering()
    assert node.validate_chain().is_valid


def test_tampering_survives_restart_and_is_still_detected(funded, tmp_path):
    """Tampering is in the database file, so a restarted node sees (and detects) it."""
    node, alice, bob, _ = funded
    node.send(alice, PASSWORD, bob, 10)
    node.mine(alice)
    node.tamper_with_transaction(4, 1, 5000)
    restarted = SecureChainNode(db_path=node.db.path, difficulty=2)
    assert not restarted.validate_chain().is_valid
    assert restarted.is_tampered()
    restarted.restore_tampering()
    assert restarted.validate_chain().is_valid


@pytest.mark.parametrize("block_index, position, amount", [(0, 0, 5), (99, 0, 5), (1, 7, 5), (1, 0, -5)])
def test_tamper_rejects_bad_arguments(funded, block_index, position, amount):
    node = funded[0]
    with pytest.raises(ValueError):
        node.tamper_with_transaction(block_index, position, amount)
    assert not node.is_tampered()


# =============================================================================
# Persistence
# =============================================================================
def test_everything_survives_a_restart(funded):
    node, alice, bob, _ = funded
    node.send(alice, PASSWORD, bob, 40)
    node.mine(bob)
    pending = node.send(alice, PASSWORD, bob, 5).transaction
    stats_before = node.get_stats()

    restarted = SecureChainNode(db_path=node.db.path, difficulty=2)
    assert restarted.blockchain.chain == node.blockchain.chain
    assert restarted.blockchain.pending_transactions == [pending]
    assert restarted.get_stats() == stats_before
    assert restarted.validate_chain().is_valid
    assert [w["name"] for w in restarted.list_wallets()] == ["Alice", "Bob", "Charlie"]
    # The stored wallet can still sign after the restart
    restarted.send(alice, PASSWORD, bob, 1)


def test_new_database_gets_a_genesis_block(node):
    assert len(node.blockchain.chain) == 1
    assert len(node.db.load_blocks()) == 1


# =============================================================================
# Wallet management
# =============================================================================
def test_create_wallet_returns_public_info_only(node):
    info = node.create_wallet("Alice", PASSWORD)
    assert set(info) == {"name", "address", "public_key", "created_at", "balance", "available"}
    assert info["balance"] == 0


def test_wallet_name_rules(node):
    node.create_wallet("Alice", PASSWORD)
    for bad_name in ("alice", "", "   ", "x" * 31, "<script>", None):
        with pytest.raises(WalletError):
            node.create_wallet(bad_name, PASSWORD)
    with pytest.raises(WalletError):
        node.create_wallet("Weak", "123")
    assert len(node.list_wallets()) == 1


def test_wrong_password_cannot_send(funded):
    node, alice, bob, _ = funded
    with pytest.raises(WalletError):
        node.send(alice, "wrong-password", bob, 10)
    assert node.blockchain.pending_transactions == []


def test_cannot_send_from_unknown_wallet(funded):
    node, _, bob, _ = funded
    with pytest.raises(WalletError):
        node.send(Wallet.create().address, PASSWORD, bob, 10)


@pytest.mark.parametrize("amount", [0, -10, "abc", None, float("nan")])
def test_invalid_amounts_are_rejected(funded, amount):
    node, alice, bob, _ = funded
    with pytest.raises(InvalidTransactionError):
        node.send(alice, PASSWORD, bob, amount)


def test_invalid_receiver_is_rejected_and_logged(funded):
    node, alice, _, _ = funded
    with pytest.raises(InvalidTransactionError):
        node.send(alice, PASSWORD, "not-an-address", 10)
    assert logged_rules(node)[0] == Rule.INVALID_TRANSACTION


def test_rename_and_delete_wallet(funded):
    node, alice, bob, _ = funded
    node.rename_wallet(alice, "Alice Savings")
    assert node.address_book()[alice] == "Alice Savings"
    with pytest.raises(WalletError):
        node.rename_wallet(alice, "Bob")                      # name taken
    with pytest.raises(WalletError):
        node.delete_wallet(bob, "wrong-password")
    node.delete_wallet(bob, PASSWORD)
    assert bob not in node.address_book()
    assert node.blockchain.get_balance(alice) == 300          # coins stay on the chain


def test_keystore_export_is_encrypted(funded):
    node, alice, _, _ = funded
    keystore = node.export_keystore(alice)
    assert "BEGIN ENCRYPTED PRIVATE KEY" in keystore
    assert Wallet.from_encrypted_pem(keystore, PASSWORD).address == alice


# =============================================================================
# Statistics, difficulty, demo data
# =============================================================================
def test_stats(funded):
    node, alice, bob, _ = funded
    node.send(alice, PASSWORD, bob, 10)
    stats = node.get_stats()
    assert stats["blocks"] == 4
    assert stats["confirmed_transactions"] == 3
    assert stats["pending_transactions"] == 1
    assert stats["wallets"] == 3
    assert stats["total_supply"] == 300
    assert stats["is_valid"] is True


def test_history_is_newest_first(funded):
    node, alice, bob, _ = funded
    node.send(alice, PASSWORD, bob, 10)
    history = node.get_history()
    assert history[0]["status"] == "Pending"
    assert len(node.get_history(bob)) == 1


def test_difficulty_can_be_changed(node):
    wallet = node.create_wallet("Miner", PASSWORD)
    node.set_difficulty(3)
    block = node.mine(wallet["address"]).block
    assert block.difficulty == 3 and block.hash.startswith("000")
    with pytest.raises(ValueError):
        node.set_difficulty(99)


def test_seed_demo_data_and_reset(node):
    wallets = node.seed_demo_data()
    assert [w["name"] for w in wallets] == ["Alice", "Bob", "Charlie"]
    assert [w["balance"] for w in wallets] == [250, 150, 0]
    assert node.validate_chain().is_valid
    node.unlock_wallet(wallets[0]["address"], DEMO_PASSWORD)
    with pytest.raises(WalletError):
        node.seed_demo_data()                                 # wallets already exist

    node.reset()
    assert node.list_wallets() == [] and len(node.blockchain.chain) == 1
    assert node.get_alerts() == []
