"""Tests for transactions/: signing, verification, validation rules and the pool."""

import pytest

import config
from transactions import (
    DoubleSpendError,
    InvalidSignatureError,
    InvalidTransactionError,
    Transaction,
    TransactionPool,
    create_signed_transaction,
)


# ----- signatures ------------------------------------------------------------
def test_signed_transaction_is_valid(alice, bob):
    tx = create_signed_transaction(alice, bob.address, 10)
    tx.validate()
    assert tx.is_valid()
    assert tx.sender == alice.address and tx.receiver == bob.address


def test_unsigned_transaction_is_rejected(alice, bob):
    tx = Transaction(sender=alice.address, receiver=bob.address, amount=10)
    with pytest.raises(InvalidSignatureError, match="not signed"):
        tx.validate()


def test_forged_signature_is_rejected(alice, bob, mallory):
    """Mallory writes 'Alice pays Mallory' and signs it with her OWN key."""
    forged = Transaction(sender=alice.address, receiver=mallory.address, amount=50)
    forged.sender_public_key = alice.public_key_hex      # claims to be Alice
    forged.tx_id = forged.compute_hash()
    forged.signature = mallory.sign(forged.payload())    # but cannot sign as Alice
    with pytest.raises(InvalidSignatureError, match="Invalid digital signature"):
        forged.validate()


def test_attacker_cannot_attach_own_public_key_to_victims_address(alice, mallory):
    forged = Transaction(sender=alice.address, receiver=mallory.address, amount=50)
    forged.sender_public_key = mallory.public_key_hex    # valid signature, wrong owner
    forged.tx_id = forged.compute_hash()
    forged.signature = mallory.sign(forged.payload())
    with pytest.raises(InvalidSignatureError, match="does not belong"):
        forged.validate()


def test_wallet_cannot_sign_someone_elses_transaction(alice, bob, mallory):
    tx = Transaction(sender=alice.address, receiver=bob.address, amount=10)
    with pytest.raises(InvalidTransactionError):
        tx.sign(mallory)


def test_random_signature_is_rejected(alice, bob):
    tx = create_signed_transaction(alice, bob.address, 10)
    tx.signature = "ab" * 70
    with pytest.raises(InvalidSignatureError):
        tx.validate()


# ----- tampering after signing -------------------------------------------------
def test_changing_amount_after_signing_is_detected(alice, bob):
    tx = create_signed_transaction(alice, bob.address, 10)
    tx.amount = 1000.0
    with pytest.raises(InvalidTransactionError, match="modified"):
        tx.validate()


def test_changing_amount_and_id_still_fails_signature(alice, bob):
    tx = create_signed_transaction(alice, bob.address, 10)
    tx.amount = 1000.0
    tx.tx_id = tx.compute_hash()          # attacker fixes the ID too
    with pytest.raises(InvalidSignatureError):
        tx.validate()


def test_changing_receiver_after_signing_is_detected(alice, bob, mallory):
    tx = create_signed_transaction(alice, bob.address, 10)
    tx.receiver = mallory.address
    tx.tx_id = tx.compute_hash()
    assert not tx.is_valid()


# ----- field validation --------------------------------------------------------
@pytest.mark.parametrize(
    "amount", [0, -5, float("nan"), float("inf"), "10", None, True, 0.123456789, config.MAX_TRANSACTION_AMOUNT + 1]
)
def test_invalid_amounts_are_rejected(alice, bob, amount):
    tx = Transaction(sender=alice.address, receiver=bob.address, amount=amount).sign(alice)
    with pytest.raises(InvalidTransactionError):
        tx.validate()


@pytest.mark.parametrize("receiver", ["", "bob", "SC123", None])
def test_invalid_receiver_is_rejected(alice, receiver):
    tx = Transaction(sender=alice.address, receiver=receiver, amount=1).sign(alice)
    with pytest.raises(InvalidTransactionError, match="Receiver"):
        tx.validate()


def test_sending_to_yourself_is_rejected(alice):
    tx = create_signed_transaction(alice, alice.address, 1)
    with pytest.raises(InvalidTransactionError, match="different"):
        tx.validate()


def test_invalid_timestamp_is_rejected(alice, bob):
    tx = Transaction(sender=alice.address, receiver=bob.address, amount=1, timestamp=-1).sign(alice)
    with pytest.raises(InvalidTransactionError, match="Timestamp"):
        tx.validate()


# ----- identity ------------------------------------------------------------------
def test_identical_payments_get_different_ids(alice, bob):
    first = create_signed_transaction(alice, bob.address, 10)
    second = create_signed_transaction(alice, bob.address, 10)
    assert first.tx_id != second.tx_id


def test_dict_roundtrip_keeps_transaction_valid(alice, bob):
    tx = create_signed_transaction(alice, bob.address, 12.5)
    copy = Transaction.from_dict(tx.to_dict())
    assert copy == tx
    copy.validate()


# ----- coinbase ------------------------------------------------------------------
def test_coinbase_transaction_is_valid_without_signature(alice):
    reward = Transaction.coinbase(alice.address, config.MINING_REWARD)
    assert reward.is_coinbase
    reward.validate()


def test_coinbase_cannot_be_signed(alice):
    reward = Transaction.coinbase(alice.address, 100)
    with pytest.raises(InvalidTransactionError):
        reward.sign(alice)
    reward.signature = "abcd"
    with pytest.raises(InvalidTransactionError):
        reward.validate()


# ----- pending pool ----------------------------------------------------------------
def test_pool_stores_transactions_in_order(alice, bob):
    pool = TransactionPool()
    txs = [create_signed_transaction(alice, bob.address, n) for n in (1, 2, 3)]
    for tx in txs:
        pool.add(tx)
    assert pool.all() == txs
    assert len(pool) == 3
    assert txs[0].tx_id in pool


def test_pool_rejects_duplicates(alice, bob):
    pool = TransactionPool()
    tx = create_signed_transaction(alice, bob.address, 1)
    pool.add(tx)
    with pytest.raises(DoubleSpendError):
        pool.add(tx)


def test_pool_tracks_pending_outgoing_per_sender(alice, bob):
    pool = TransactionPool()
    pool.add(create_signed_transaction(alice, bob.address, 10))
    pool.add(create_signed_transaction(alice, bob.address, 15))
    pool.add(create_signed_transaction(bob, alice.address, 7))
    assert pool.pending_outgoing(alice.address) == 25
    assert pool.pending_outgoing(bob.address) == 7


def test_pool_remove_and_clear(alice, bob):
    pool = TransactionPool()
    tx = create_signed_transaction(alice, bob.address, 1)
    pool.add(tx)
    pool.remove(tx.tx_id)
    assert len(pool) == 0
    pool.add(tx)
    pool.clear()
    assert pool.all() == []
