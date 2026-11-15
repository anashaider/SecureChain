"""
SecureChainNode - the application service that ties every module together.

The user interface (and demo.py) only ever talk to this class:

        UI / demo script
              |
        SecureChainNode  ----->  Database (SQLite)
          |     |     |
     Blockchain | FraudDetector
            Wallets

It makes sure that whatever happens in memory is also saved to the
database, and that every rejected or suspicious transaction ends up in the
fraud log.
"""

import math
import threading
import time
from dataclasses import dataclass, field

import config
from blockchain import Block, Blockchain, MiningResult
from database import Database
from security import FraudAlert, FraudDetector, Rule, Severity, ValidationReport
from transactions import (
    DoubleSpendError,
    InsufficientBalanceError,
    InvalidSignatureError,
    InvalidTransactionError,
    Transaction,
)
from wallet import Wallet, WalletError, is_valid_address

DEMO_PASSWORD = "demo-pass-123"          # password of the wallets created by "Load demo data"
_TAMPER_BACKUP_KEY = "tamper_backup"


class ChainIntegrityError(Exception):
    """Raised when an operation is refused because the stored chain is corrupted."""


@dataclass
class SubmitResult:
    """Returned when a transaction is accepted into the pending pool."""

    transaction: Transaction
    alerts: list[FraudAlert] = field(default_factory=list)

    @property
    def risk_score(self) -> int:
        return FraudDetector.risk_score(self.alerts)

    @property
    def risk_level(self) -> str:
        return FraudDetector.risk_level(self.risk_score)


class SecureChainNode:
    """One node of the SecureChain ledger: blockchain + wallets + fraud monitor + storage."""

    def __init__(self, db_path=None, difficulty: int | None = None):
        self.db = Database(db_path or config.DB_PATH)
        self.detector = FraudDetector()
        self._difficulty = difficulty if difficulty is not None else config.MINING_DIFFICULTY
        # Streamlit serves each browser session from a different thread;
        # the lock makes sure two actions never modify the chain at once.
        self._lock = threading.RLock()
        self._last_tamper_signature = None
        self.blockchain: Blockchain = None
        self._load()

    def _load(self) -> None:
        """Load the chain from SQLite, or start a new one with a genesis block."""
        blocks = self.db.load_blocks()
        pending = self.db.load_pending()
        self.blockchain = Blockchain(difficulty=self._difficulty, chain=blocks, pending=pending)
        if not blocks:
            self.db.save_block(self.blockchain.chain[0])   # persist the genesis block

    def sync(self) -> bool:
        """
        Reload the chain if the database no longer matches what is in memory
        (for example when a second copy of the app wrote to the same file).
        Returns True if a reload happened.
        """
        with self._lock:
            chain = self.blockchain.chain
            in_memory = (
                len(chain),
                chain[-1].hash if chain else "",
                sum(len(block.transactions) for block in chain),
                len(self.blockchain.pool),
            )
            if self.db.fingerprint() == in_memory:
                return False
            self._load()
            return True

    # ==================================================================
    # Wallets
    # ==================================================================
    def create_wallet(self, name: str, password: str) -> dict:
        """
        Create a wallet and store it with its private key ENCRYPTED by `password`.
        The password itself is never stored - forget it and the wallet is lost.
        """
        name = self._clean_wallet_name(name)
        with self._lock:
            if self.db.get_wallet_by_name(name):
                raise WalletError(f"A wallet named '{name}' already exists.")
            wallet = Wallet.create()
            encrypted_key = wallet.to_encrypted_pem(password)   # also checks password strength
            self.db.save_wallet(
                address=wallet.address,
                name=name,
                public_key=wallet.public_key_hex,
                encrypted_private_key=encrypted_key,
                created_at=round(time.time(), 6),
            )
            return self.get_wallet_info(wallet.address)

    @staticmethod
    def _clean_wallet_name(name) -> str:
        if not isinstance(name, str) or not name.strip():
            raise WalletError("Wallet name cannot be empty.")
        name = name.strip()
        if len(name) > config.MAX_WALLET_NAME_LENGTH:
            raise WalletError(f"Wallet name can be at most {config.MAX_WALLET_NAME_LENGTH} characters.")
        if not all(ch.isalnum() or ch in " _-." for ch in name):
            raise WalletError("Wallet name may only contain letters, digits, spaces and _ - .")
        return name

    def unlock_wallet(self, address: str, password: str) -> Wallet:
        """Decrypt a stored wallet. The decrypted key lives only in memory, only briefly."""
        record = self.db.get_wallet(address)
        if record is None:
            raise WalletError("Wallet not found on this node.")
        return Wallet.from_encrypted_pem(record["encrypted_private_key"], password)

    def get_wallet_info(self, address: str) -> dict | None:
        """Public wallet details plus balances (never includes key material)."""
        record = self.db.get_wallet(address)
        return self._public_wallet_view(record) if record else None

    def list_wallets(self) -> list[dict]:
        return [self._public_wallet_view(record) for record in self.db.list_wallets()]

    def _public_wallet_view(self, record: dict) -> dict:
        address = record["address"]
        return {
            "name": record["name"],
            "address": address,
            "public_key": record["public_key"],
            "created_at": record["created_at"],
            "balance": self.blockchain.get_balance(address),
            "available": self.blockchain.get_available_balance(address),
        }

    def export_keystore(self, address: str) -> str:
        """The encrypted private key (safe to back up - useless without the password)."""
        record = self.db.get_wallet(address)
        if record is None:
            raise WalletError("Wallet not found on this node.")
        return record["encrypted_private_key"]

    def rename_wallet(self, address: str, new_name: str) -> None:
        new_name = self._clean_wallet_name(new_name)
        with self._lock:
            if self.db.get_wallet(address) is None:
                raise WalletError("Wallet not found on this node.")
            existing = self.db.get_wallet_by_name(new_name)
            if existing and existing["address"] != address:
                raise WalletError(f"A wallet named '{new_name}' already exists.")
            self.db.rename_wallet(address, new_name)

    def delete_wallet(self, address: str, password: str) -> None:
        """Remove a wallet's keys from this node. Requires the password as proof of ownership."""
        with self._lock:
            self.unlock_wallet(address, password)   # raises WalletError if the password is wrong
            self.db.delete_wallet(address)

    def address_book(self) -> dict[str, str]:
        """Map of address -> wallet name for wallets stored on this node."""
        return {record["address"]: record["name"] for record in self.db.list_wallets()}

    # ==================================================================
    # Transactions
    # ==================================================================
    def send(self, sender_address: str, password: str, receiver: str, amount) -> SubmitResult:
        """Create, sign and submit a payment from one of this node's wallets."""
        self._require_valid_chain()
        try:
            amount = round(float(amount), config.AMOUNT_DECIMALS)
        except (TypeError, ValueError) as exc:
            raise InvalidTransactionError("Amount must be a number.") from exc
        wallet = self.unlock_wallet(sender_address, password)
        tx = Transaction(sender=wallet.address, receiver=receiver, amount=amount)
        tx.sign(wallet)
        del wallet                      # drop the decrypted key as soon as it has signed
        return self.submit_transaction(tx)

    def submit_transaction(self, tx: Transaction) -> SubmitResult:
        """
        Offer an already-signed transaction to the node.

        Accepted  -> stored in the pending pool, checked by the fraud detector.
        Rejected  -> the reason is written to the fraud log and the error re-raised.
        """
        with self._lock:
            self._require_valid_chain()
            sender = tx.sender if isinstance(tx, Transaction) else ""
            balance_before = self.blockchain.get_available_balance(sender)
            history = self.blockchain.get_sent_transactions(sender)

            try:
                self.blockchain.add_transaction(tx)
            except InvalidSignatureError as exc:
                self._log_rejection(Rule.FORGED_SIGNATURE, Severity.CRITICAL, tx, exc)
                raise
            except InsufficientBalanceError as exc:
                self._log_rejection(Rule.INSUFFICIENT_BALANCE, Severity.MEDIUM, tx, exc)
                raise
            except DoubleSpendError as exc:
                self._log_rejection(Rule.DOUBLE_SPEND, Severity.HIGH, tx, exc)
                raise
            except InvalidTransactionError as exc:
                self._log_rejection(Rule.INVALID_TRANSACTION, Severity.MEDIUM, tx, exc)
                raise

            self.db.save_pending(tx)
            alerts = self.detector.analyze(tx, history, balance_before)
            for alert in alerts:
                self.db.log_alert(alert)
            return SubmitResult(transaction=tx, alerts=alerts)

    def _log_rejection(self, rule: str, severity: str, tx, reason) -> None:
        """Write a rejected transaction to the fraud log (tolerates garbage fields)."""
        amount = getattr(tx, "amount", 0)
        if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not math.isfinite(amount):
            amount = 0.0
        self.db.log_alert(
            FraudAlert(
                rule=rule,
                severity=severity,
                message=f"Transaction rejected: {reason}",
                tx_id=str(getattr(tx, "tx_id", "")),
                sender=str(getattr(tx, "sender", "")),
                receiver=str(getattr(tx, "receiver", "")),
                amount=float(amount),
            )
        )

    def get_history(self, address: str | None = None) -> list[dict]:
        """Transaction history (confirmed + pending), newest first."""
        return list(reversed(self.blockchain.get_transactions(address)))

    # ==================================================================
    # Mining
    # ==================================================================
    def mine(self, miner_address: str, on_progress=None) -> MiningResult:
        """Mine the pending transactions into a new block and save it."""
        with self._lock:
            self._require_valid_chain()
            result = self.blockchain.mine_pending_transactions(miner_address, on_progress=on_progress)
            self.db.save_block(result.block)
            self.db.clear_pending()     # anything left over was rejected at mining time
            return result

    def set_difficulty(self, difficulty: int) -> None:
        with self._lock:
            self.blockchain.set_difficulty(difficulty)
            self._difficulty = difficulty

    # ==================================================================
    # Validation
    # ==================================================================
    def validate_chain(self) -> ValidationReport:
        """Run the full integrity check. A failure is recorded in the fraud log (once)."""
        with self._lock:
            report = self.blockchain.validate()
            if report.is_valid:
                self._last_tamper_signature = None
            else:
                signature = tuple((i.block_index, i.check, i.message) for i in report.issues)
                if signature != self._last_tamper_signature:
                    self._last_tamper_signature = signature
                    first = report.issues[0]
                    self.db.log_alert(
                        FraudAlert(
                            rule=Rule.CHAIN_TAMPERING,
                            severity=Severity.CRITICAL,
                            message=(
                                f"Chain validation failed with {len(report.issues)} issue(s). "
                                f"First: block #{first.block_index} - {first.message}"
                            ),
                        )
                    )
            return report

    def _require_valid_chain(self) -> None:
        """Refuse to build on top of a corrupted ledger."""
        if not self.validate_chain().is_valid:
            raise ChainIntegrityError(
                "Blockchain integrity check failed - the ledger has been tampered with. "
                "New transactions and mining are disabled until the chain is restored."
            )

    # ==================================================================
    # Fraud log and statistics
    # ==================================================================
    def get_alerts(self, limit: int | None = None) -> list[dict]:
        return self.db.list_alerts(limit)

    def get_stats(self) -> dict:
        chain = self.blockchain.chain
        confirmed = sum(len(block.transactions) for block in chain)
        supply = sum(tx.amount for block in chain for tx in block.transactions if tx.is_coinbase)
        return {
            "blocks": len(chain),
            "confirmed_transactions": confirmed,
            "pending_transactions": len(self.blockchain.pool),
            "wallets": len(self.db.list_wallets()),
            "total_supply": round(supply, config.AMOUNT_DECIMALS),
            "alerts": self.db.count_alerts(),
            "difficulty": self.blockchain.difficulty,
            "mining_reward": self.blockchain.mining_reward,
            "latest_hash": self.blockchain.latest_block.hash,
            "is_valid": self.blockchain.is_valid(),
        }

    # ==================================================================
    # Attack simulation (for the security demonstrations)
    # ==================================================================
    def tamper_with_transaction(
        self, block_index: int, tx_position: int, new_amount: float, recompute_hashes: bool = False
    ) -> float:
        """
        SIMULATED ATTACK: edit a confirmed transaction directly in the database,
        exactly as someone with access to the database file could.

        recompute_hashes=False  the attacker only changes the amount
        recompute_hashes=True   a smarter attacker also recomputes the
                                transaction ID, Merkle root and block hash
                                to try to hide the change

        Either way `validate_chain` detects it. The original block is backed
        up first so `restore_tampering` can undo the attack.
        Returns the original amount.
        """
        with self._lock:
            chain = self.blockchain.chain
            if not isinstance(block_index, int) or not 1 <= block_index < len(chain):
                raise ValueError("Choose a mined block (not the genesis block).")
            block = chain[block_index]
            if not isinstance(tx_position, int) or not 0 <= tx_position < len(block.transactions):
                raise ValueError("That block has no transaction at this position.")
            new_amount = float(new_amount)
            if not math.isfinite(new_amount) or new_amount <= 0:
                raise ValueError("The tampered amount must be a positive number.")

            backup = self.db.get_meta(_TAMPER_BACKUP_KEY, {})
            backup.setdefault(str(block_index), block.to_dict())   # keep the ORIGINAL only
            self.db.set_meta(_TAMPER_BACKUP_KEY, backup)

            forged = Block.from_dict(block.to_dict())
            tx = forged.transactions[tx_position]
            original_amount = tx.amount
            tx.amount = new_amount
            if recompute_hashes:
                tx.tx_id = tx.compute_hash()
                forged.merkle_root = forged.compute_merkle_root()
                forged.hash = forged.compute_hash()

            self.db.save_block(forged)   # overwrite history in the database...
            self._load()                 # ...and reload, as a restarted node would
            return original_amount

    def is_tampered(self) -> bool:
        """True while a simulated tampering attack has not been undone."""
        return bool(self.db.get_meta(_TAMPER_BACKUP_KEY, {}))

    def get_tamper_comparison(self) -> list[dict]:
        """
        For each block changed by a simulated attack: the original block (from
        the backup) and the block as it is stored now. Read-only; used by the
        Attack Lab to show a before/after comparison.
        """
        backup = self.db.get_meta(_TAMPER_BACKUP_KEY, {})
        chain = self.blockchain.chain
        comparison = []
        for index_text, original in sorted(backup.items(), key=lambda item: int(item[0])):
            index = int(index_text)
            if index < len(chain):
                comparison.append({"index": index, "original": original, "current": chain[index].to_dict()})
        return comparison

    def restore_tampering(self) -> int:
        """Undo simulated tampering by restoring the backed-up blocks. Returns how many."""
        with self._lock:
            backup = self.db.get_meta(_TAMPER_BACKUP_KEY, {})
            for block_data in backup.values():
                self.db.save_block(Block.from_dict(block_data))
            self.db.delete_meta(_TAMPER_BACKUP_KEY)
            self._load()
            return len(backup)

    # ==================================================================
    # Demo helpers
    # ==================================================================
    def seed_demo_data(self) -> list[dict]:
        """
        Create three demo wallets (Alice, Bob, Charlie), mine some coins for
        Alice and confirm one payment, so every screen has something to show.
        All demo wallets use the password in DEMO_PASSWORD.
        """
        with self._lock:
            self._require_valid_chain()
            for name in ("Alice", "Bob", "Charlie"):       # check first: create all three or none
                if self.db.get_wallet_by_name(name):
                    raise WalletError(f"A wallet named '{name}' already exists.")
            alice = self.create_wallet("Alice", DEMO_PASSWORD)
            bob = self.create_wallet("Bob", DEMO_PASSWORD)
            charlie = self.create_wallet("Charlie", DEMO_PASSWORD)
            for _ in range(3):
                self.mine(alice["address"])                      # Alice earns 3 rewards
            self.send(alice["address"], DEMO_PASSWORD, bob["address"], 50)
            self.mine(bob["address"])                            # Bob mines the payment
            return [self.get_wallet_info(w["address"]) for w in (alice, bob, charlie)]

    def reset(self) -> None:
        """Erase everything and start again from a fresh genesis block."""
        with self._lock:
            self.db.reset()
            self._last_tamper_signature = None
            self._load()


__all__ = [
    "SecureChainNode",
    "SubmitResult",
    "ChainIntegrityError",
    "DEMO_PASSWORD",
    "is_valid_address",
]
