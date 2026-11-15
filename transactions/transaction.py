"""
The Transaction model.

A transaction says "sender pays receiver this amount at this time".
To be accepted it must carry a valid ECDSA signature made by the sender's
private key. Two special facts make that secure:

  1. The signature covers ALL important fields (sender, receiver, amount,
     timestamp, nonce). Changing any of them afterwards breaks the signature.
  2. The sender's address is derived from the public key, so nobody can
     attach their own key to somebody else's address.

Mining rewards are "coinbase" transactions: they have the special sender
"COINBASE", create new coins and carry no signature.
"""

import hashlib
import json
import math
import secrets
import time
from dataclasses import dataclass, field

import config
from transactions.exceptions import InvalidSignatureError, InvalidTransactionError
from wallet import Wallet, WalletError, address_from_public_key, is_valid_address, verify_signature


def _now() -> float:
    """Current time, rounded so it survives being stored and re-loaded exactly."""
    return round(time.time(), 6)


def _format_number(value, decimals: int) -> str:
    """Format a number with a fixed number of decimals (fallback: plain text)."""
    try:
        return f"{value:.{decimals}f}"
    except (TypeError, ValueError):
        return str(value)


@dataclass
class Transaction:
    """A transfer of coins from one wallet address to another."""

    sender: str
    receiver: str
    amount: float
    timestamp: float = field(default_factory=_now)
    nonce: str = field(default_factory=lambda: secrets.token_hex(8))  # makes every tx unique
    sender_public_key: str = ""
    signature: str = ""
    tx_id: str = ""

    def __post_init__(self):
        # A freshly created transaction gets its ID from its own content.
        # A transaction loaded from storage keeps the stored ID so that any
        # later modification of its data can be detected.
        if not self.tx_id:
            self.tx_id = self.compute_hash()

    # ----- hashing --------------------------------------------------------
    def payload(self) -> bytes:
        """
        The exact bytes that are hashed and signed.

        Keys are sorted and numbers use a fixed format so the same
        transaction always produces the same bytes.
        """
        data = {
            "sender": str(self.sender),
            "sender_public_key": str(self.sender_public_key),
            "receiver": str(self.receiver),
            "amount": _format_number(self.amount, config.AMOUNT_DECIMALS),
            "timestamp": _format_number(self.timestamp, 6),
            "nonce": str(self.nonce),
        }
        return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def compute_hash(self) -> str:
        """SHA-256 fingerprint of the transaction content (this is the tx ID)."""
        return hashlib.sha256(self.payload()).hexdigest()

    # ----- coinbase -------------------------------------------------------
    @property
    def is_coinbase(self) -> bool:
        return self.sender == config.COINBASE_SENDER

    @classmethod
    def coinbase(cls, receiver: str, amount: float) -> "Transaction":
        """Create the mining-reward transaction for a new block."""
        return cls(sender=config.COINBASE_SENDER, receiver=receiver, amount=amount)

    # ----- signing --------------------------------------------------------
    def sign(self, wallet: Wallet) -> "Transaction":
        """Sign the transaction with the sender's wallet."""
        if self.is_coinbase:
            raise InvalidTransactionError("Coinbase transactions are not signed.")
        if wallet.address != self.sender:
            raise InvalidTransactionError("You can only sign transactions sent from your own wallet.")
        self.sender_public_key = wallet.public_key_hex
        self.tx_id = self.compute_hash()
        self.signature = wallet.sign(self.payload())
        return self

    # ----- validation -----------------------------------------------------
    def validate(self) -> None:
        """
        Check the transaction on its own (no balance check - that needs the chain).

        Raises InvalidTransactionError / InvalidSignatureError describing the
        first problem found. Returns nothing when the transaction is fine.
        """
        # 1. Field types and formats
        if isinstance(self.amount, bool) or not isinstance(self.amount, (int, float)):
            raise InvalidTransactionError("Amount must be a number.")
        if not math.isfinite(self.amount) or self.amount <= 0:
            raise InvalidTransactionError("Amount must be greater than zero.")
        if self.amount > config.MAX_TRANSACTION_AMOUNT:
            raise InvalidTransactionError("Amount exceeds the maximum allowed.")
        if round(self.amount, config.AMOUNT_DECIMALS) != self.amount:
            raise InvalidTransactionError(
                f"Amount can have at most {config.AMOUNT_DECIMALS} decimal places."
            )
        if isinstance(self.timestamp, bool) or not isinstance(self.timestamp, (int, float)):
            raise InvalidTransactionError("Timestamp must be a number.")
        if not math.isfinite(self.timestamp) or self.timestamp <= 0:
            raise InvalidTransactionError("Timestamp is not valid.")
        if not is_valid_address(self.receiver):
            raise InvalidTransactionError("Receiver address is not valid.")
        if not self.is_coinbase and not is_valid_address(self.sender):
            raise InvalidTransactionError("Sender address is not valid.")
        if self.sender == self.receiver:
            raise InvalidTransactionError("Sender and receiver must be different wallets.")

        # 2. Integrity: the stored ID must still match the content
        if self.tx_id != self.compute_hash():
            raise InvalidTransactionError(
                "Transaction data does not match its ID (the transaction was modified)."
            )

        # 3. Coinbase transactions carry no signature
        if self.is_coinbase:
            if self.signature or self.sender_public_key:
                raise InvalidTransactionError("Coinbase transactions must not be signed.")
            return

        # 4. Digital signature
        if not self.signature or not self.sender_public_key:
            raise InvalidSignatureError("Transaction is not signed.")
        try:
            key_address = address_from_public_key(self.sender_public_key)
        except WalletError as exc:
            raise InvalidSignatureError("Public key is malformed.") from exc
        if key_address != self.sender:
            raise InvalidSignatureError("Public key does not belong to the sender address.")
        if not verify_signature(self.sender_public_key, self.payload(), self.signature):
            raise InvalidSignatureError("Invalid digital signature.")

    def is_valid(self) -> bool:
        """True/False version of `validate`."""
        try:
            self.validate()
            return True
        except InvalidTransactionError:
            return False

    # ----- (de)serialisation ---------------------------------------------
    def to_dict(self) -> dict:
        return {
            "tx_id": self.tx_id,
            "sender": self.sender,
            "receiver": self.receiver,
            "amount": self.amount,
            "timestamp": self.timestamp,
            "nonce": self.nonce,
            "sender_public_key": self.sender_public_key,
            "signature": self.signature,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Transaction":
        return cls(
            sender=data["sender"],
            receiver=data["receiver"],
            amount=data["amount"],
            timestamp=data["timestamp"],
            nonce=data["nonce"],
            sender_public_key=data.get("sender_public_key", ""),
            signature=data.get("signature", ""),
            tx_id=data.get("tx_id", ""),
        )


def create_signed_transaction(wallet: Wallet, receiver: str, amount: float) -> Transaction:
    """Convenience helper: build a transaction from `wallet` and sign it."""
    return Transaction(sender=wallet.address, receiver=receiver, amount=amount).sign(wallet)
