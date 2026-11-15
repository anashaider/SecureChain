"""
SQLite persistence.

Tables
------
blocks        one row per block header
transactions  one row per transaction; `block_index` is NULL while pending
wallets       address, name, public key and the ENCRYPTED private key
fraud_alerts  the fraud / security log
meta          small key-value store (used by the tampering demo backup)

Security notes
--------------
* Private keys are stored only in password-encrypted form
  (see wallet.Wallet.to_encrypted_pem) - never as plain text.
* Every query uses "?" placeholders, so user input can never be
  interpreted as SQL (no SQL injection).

A new connection is opened for each operation. That is slightly slower than
keeping one open, but it is simple and safe with Streamlit, which runs the
app in several threads.
"""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from blockchain import Block
from security import FraudAlert
from transactions import Transaction

SCHEMA = """
CREATE TABLE IF NOT EXISTS blocks (
    block_index   INTEGER PRIMARY KEY,
    timestamp     REAL    NOT NULL,
    previous_hash TEXT    NOT NULL,
    merkle_root   TEXT    NOT NULL,
    difficulty    INTEGER NOT NULL,
    nonce         INTEGER NOT NULL,
    hash          TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS transactions (
    row_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    tx_id             TEXT    NOT NULL,
    block_index       INTEGER,            -- NULL = still in the pending pool
    position          INTEGER NOT NULL DEFAULT 0,
    sender            TEXT    NOT NULL,
    receiver          TEXT    NOT NULL,
    amount            REAL    NOT NULL,
    timestamp         REAL    NOT NULL,
    nonce             TEXT    NOT NULL,
    sender_public_key TEXT    NOT NULL DEFAULT '',
    signature         TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_tx_block ON transactions (block_index, position);
CREATE INDEX IF NOT EXISTS idx_tx_id ON transactions (tx_id);

CREATE TABLE IF NOT EXISTS wallets (
    address               TEXT PRIMARY KEY,
    name                  TEXT NOT NULL UNIQUE,
    public_key            TEXT NOT NULL,
    encrypted_private_key TEXT NOT NULL,   -- password-encrypted PEM, never plaintext
    created_at            REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS fraud_alerts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at REAL NOT NULL,
    rule       TEXT NOT NULL,
    severity   TEXT NOT NULL,
    message    TEXT NOT NULL,
    tx_id      TEXT NOT NULL DEFAULT '',
    sender     TEXT NOT NULL DEFAULT '',
    receiver   TEXT NOT NULL DEFAULT '',
    amount     REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

_TX_COLUMNS = "tx_id, sender, receiver, amount, timestamp, nonce, sender_public_key, signature"


class Database:
    """All reading and writing of the SQLite file goes through this class."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self):
        """Open a connection, commit on success, roll back on error, always close."""
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Blocks
    # ------------------------------------------------------------------
    def save_block(self, block: Block) -> None:
        """
        Store a block and its transactions (replacing any stored copy).

        Transactions that were waiting in the pending pool and are now in
        this block are removed from the pool rows in the same database
        transaction, so the file is never left half-updated.
        """
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO blocks "
                "(block_index, timestamp, previous_hash, merkle_root, difficulty, nonce, hash) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (block.index, block.timestamp, block.previous_hash, block.merkle_root,
                 block.difficulty, block.nonce, block.hash),
            )
            conn.execute("DELETE FROM transactions WHERE block_index = ?", (block.index,))
            for position, tx in enumerate(block.transactions):
                conn.execute(
                    "DELETE FROM transactions WHERE tx_id = ? AND block_index IS NULL", (tx.tx_id,)
                )
                self._insert_transaction(conn, tx, block.index, position)

    def load_blocks(self) -> list[Block]:
        """Rebuild every block, in order, exactly as stored (no recalculation)."""
        with self._connect() as conn:
            block_rows = conn.execute("SELECT * FROM blocks ORDER BY block_index").fetchall()
            blocks = []
            for row in block_rows:
                tx_rows = conn.execute(
                    f"SELECT {_TX_COLUMNS} FROM transactions WHERE block_index = ? ORDER BY position",
                    (row["block_index"],),
                ).fetchall()
                blocks.append(
                    Block(
                        index=row["block_index"],
                        timestamp=row["timestamp"],
                        transactions=[Transaction.from_dict(dict(tx)) for tx in tx_rows],
                        previous_hash=row["previous_hash"],
                        difficulty=row["difficulty"],
                        nonce=row["nonce"],
                        merkle_root=row["merkle_root"],
                        hash=row["hash"],
                    )
                )
            return blocks

    # ------------------------------------------------------------------
    # Pending transactions
    # ------------------------------------------------------------------
    @staticmethod
    def _insert_transaction(conn, tx: Transaction, block_index, position: int) -> None:
        conn.execute(
            f"INSERT INTO transactions (block_index, position, {_TX_COLUMNS}) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (block_index, position, tx.tx_id, tx.sender, tx.receiver, tx.amount,
             tx.timestamp, tx.nonce, tx.sender_public_key, tx.signature),
        )

    def save_pending(self, tx: Transaction) -> None:
        with self._connect() as conn:
            self._insert_transaction(conn, tx, None, 0)

    def load_pending(self) -> list[Transaction]:
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT {_TX_COLUMNS} FROM transactions WHERE block_index IS NULL ORDER BY row_id"
            ).fetchall()
            return [Transaction.from_dict(dict(row)) for row in rows]

    def clear_pending(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM transactions WHERE block_index IS NULL")

    # ------------------------------------------------------------------
    # Wallets
    # ------------------------------------------------------------------
    def save_wallet(self, address, name, public_key, encrypted_private_key, created_at) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO wallets (address, name, public_key, encrypted_private_key, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (address, name, public_key, encrypted_private_key, created_at),
            )

    def get_wallet(self, address: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM wallets WHERE address = ?", (address,)).fetchone()
            return dict(row) if row else None

    def get_wallet_by_name(self, name: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM wallets WHERE name = ? COLLATE NOCASE", (name,)
            ).fetchone()
            return dict(row) if row else None

    def list_wallets(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM wallets ORDER BY created_at, name").fetchall()
            return [dict(row) for row in rows]

    def rename_wallet(self, address: str, new_name: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE wallets SET name = ? WHERE address = ?", (new_name, address))

    def delete_wallet(self, address: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM wallets WHERE address = ?", (address,))

    # ------------------------------------------------------------------
    # Fraud log
    # ------------------------------------------------------------------
    def log_alert(self, alert: FraudAlert) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO fraud_alerts (created_at, rule, severity, message, tx_id, sender, receiver, amount) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (alert.created_at, alert.rule, alert.severity, alert.message,
                 alert.tx_id, alert.sender, alert.receiver, alert.amount),
            )

    def list_alerts(self, limit: int | None = None) -> list[dict]:
        """Fraud log entries, newest first."""
        query = "SELECT * FROM fraud_alerts ORDER BY id DESC"
        params = ()
        if limit is not None:
            query += " LIMIT ?"
            params = (int(limit),)
        with self._connect() as conn:
            return [dict(row) for row in conn.execute(query, params).fetchall()]

    def count_alerts(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM fraud_alerts").fetchone()[0]

    # ------------------------------------------------------------------
    # Meta key-value store
    # ------------------------------------------------------------------
    def set_meta(self, key: str, value) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, json.dumps(value))
            )

    def get_meta(self, key: str, default=None):
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
            return json.loads(row["value"]) if row else default

    def delete_meta(self, key: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM meta WHERE key = ?", (key,))

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------
    def fingerprint(self) -> tuple:
        """
        A cheap summary of the stored ledger: (blocks, tip hash, confirmed
        transactions, pending transactions). The node compares it with its
        in-memory chain to notice when the file was changed by another process.
        """
        with self._connect() as conn:
            blocks = conn.execute("SELECT COUNT(*) FROM blocks").fetchone()[0]
            tip = conn.execute("SELECT hash FROM blocks ORDER BY block_index DESC LIMIT 1").fetchone()
            confirmed = conn.execute(
                "SELECT COUNT(*) FROM transactions WHERE block_index IS NOT NULL"
            ).fetchone()[0]
            pending = conn.execute(
                "SELECT COUNT(*) FROM transactions WHERE block_index IS NULL"
            ).fetchone()[0]
            return (blocks, tip[0] if tip else "", confirmed, pending)

    def reset(self) -> None:
        """Delete ALL data (used by the 'reset demo' button and tests)."""
        with self._connect() as conn:
            for table in ("transactions", "blocks", "wallets", "fraud_alerts", "meta"):
                conn.execute(f"DELETE FROM {table}")
