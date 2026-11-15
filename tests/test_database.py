"""Tests for database/: SQLite persistence and private-key confidentiality."""

import sqlite3

import pytest

from database import Database
from security import FraudAlert, Rule, Severity
from transactions import create_signed_transaction

PASSWORD = "correct-horse-battery"


@pytest.fixture
def db(tmp_path) -> Database:
    return Database(tmp_path / "ledger.db")


def test_schema_is_created(db):
    with sqlite3.connect(db.path) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"blocks", "transactions", "wallets", "fraud_alerts", "meta"} <= tables


def test_database_directory_is_created_automatically(tmp_path):
    db = Database(tmp_path / "nested" / "folder" / "ledger.db")
    assert db.path.exists()


def test_blocks_roundtrip_exactly(db, busy_chain):
    for block in busy_chain.chain:
        db.save_block(block)
    loaded = db.load_blocks()
    assert loaded == busy_chain.chain                      # hashes, nonces, signatures all identical
    assert all(tx.is_valid() for block in loaded for tx in block.transactions)


def test_saving_a_block_twice_does_not_duplicate_it(db, busy_chain):
    db.save_block(busy_chain.chain[3])
    db.save_block(busy_chain.chain[3])
    loaded = db.load_blocks()
    assert len(loaded) == 1 and len(loaded[0].transactions) == 2


def test_pending_transactions_roundtrip_in_order(db, alice, bob):
    txs = [create_signed_transaction(alice, bob.address, n) for n in (1, 2, 3)]
    for tx in txs:
        db.save_pending(tx)
    assert db.load_pending() == txs
    db.clear_pending()
    assert db.load_pending() == []


def test_mined_transaction_leaves_the_pending_table(db, funded_chain, alice, bob):
    tx = create_signed_transaction(alice, bob.address, 10)
    funded_chain.add_transaction(tx)
    db.save_pending(tx)
    result = funded_chain.mine_pending_transactions(alice.address)
    db.save_block(result.block)
    assert db.load_pending() == []
    assert tx in db.load_blocks()[0].transactions


def test_wallet_storage(db, alice):
    db.save_wallet(alice.address, "Alice", alice.public_key_hex, alice.to_encrypted_pem(PASSWORD), 1.0)
    assert db.get_wallet(alice.address)["name"] == "Alice"
    assert db.get_wallet_by_name("alice")["address"] == alice.address      # case-insensitive
    assert db.get_wallet("SC" + "0" * 40) is None
    assert len(db.list_wallets()) == 1

    db.rename_wallet(alice.address, "Alice2")
    assert db.get_wallet(alice.address)["name"] == "Alice2"
    db.delete_wallet(alice.address)
    assert db.list_wallets() == []


def test_duplicate_wallet_is_refused(db, alice, bob):
    db.save_wallet(alice.address, "Alice", alice.public_key_hex, "x", 1.0)
    with pytest.raises(sqlite3.IntegrityError):
        db.save_wallet(alice.address, "Other", alice.public_key_hex, "x", 1.0)   # same address
    with pytest.raises(sqlite3.IntegrityError):
        db.save_wallet(bob.address, "Alice", bob.public_key_hex, "x", 1.0)       # same name


def test_private_key_is_never_stored_in_plaintext(db, alice):
    """Search the raw database file for the private key in every plain form."""
    db.save_wallet(alice.address, "Alice", alice.public_key_hex, alice.to_encrypted_pem(PASSWORD), 1.0)
    raw = db.path.read_bytes()

    private_number = alice._private_key.private_numbers().private_value
    private_bytes = private_number.to_bytes(32, "big")
    assert private_bytes not in raw                           # raw binary key
    assert private_bytes.hex().encode() not in raw            # hex text
    assert str(private_number).encode() not in raw            # decimal text
    assert b"BEGIN PRIVATE KEY" not in raw                    # unencrypted PEM
    assert b"BEGIN EC PRIVATE KEY" not in raw
    assert b"BEGIN ENCRYPTED PRIVATE KEY" in raw              # only the encrypted form
    assert PASSWORD.encode() not in raw                       # the password is not stored either


def test_sql_injection_attempt_is_stored_as_plain_text(db, alice):
    evil = "x'; DROP TABLE wallets; --"
    db.save_wallet(alice.address, evil, alice.public_key_hex, "x", 1.0)
    assert db.get_wallet_by_name(evil)["address"] == alice.address
    assert db.get_wallet_by_name("' OR '1'='1") is None
    assert len(db.list_wallets()) == 1                        # table still exists


def test_fraud_log(db):
    for n in range(3):
        db.log_alert(FraudAlert(Rule.LARGE_TRANSACTION, Severity.HIGH, f"alert {n}", amount=float(n)))
    alerts = db.list_alerts()
    assert [a["message"] for a in alerts] == ["alert 2", "alert 1", "alert 0"]     # newest first
    assert len(db.list_alerts(limit=2)) == 2
    assert db.count_alerts() == 3


def test_meta_store(db):
    assert db.get_meta("missing", "default") == "default"
    db.set_meta("key", {"a": [1, 2, 3]})
    assert db.get_meta("key") == {"a": [1, 2, 3]}
    db.delete_meta("key")
    assert db.get_meta("key") is None


def test_reset_erases_everything(db, busy_chain, alice):
    db.save_block(busy_chain.chain[1])
    db.save_wallet(alice.address, "Alice", alice.public_key_hex, "x", 1.0)
    db.log_alert(FraudAlert(Rule.DOUBLE_SPEND, Severity.HIGH, "x"))
    db.reset()
    assert db.load_blocks() == [] and db.list_wallets() == [] and db.count_alerts() == 0
