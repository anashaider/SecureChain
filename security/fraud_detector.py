"""
Rule-based fraud detection.

Every accepted transaction is checked against a few simple, explainable
rules. A rule that fires produces a FraudAlert. Alerts do NOT block the
transaction - like a bank's monitoring system, they flag it for review and
are written to the fraud log.

Rules
-----
LARGE_TRANSACTION     amount is at or above a fixed threshold
BALANCE_DRAIN         one payment spends (almost) the whole balance
HIGH_VELOCITY         too many payments from one wallet in a short time
FIRST_TIME_RECIPIENT  the sender has never paid this receiver before

The detector is a pure calculation: it receives the transaction and the
sender's past transactions and returns alerts. It never touches the
database, which keeps it easy to test.
"""

import time
from dataclasses import dataclass, field

import config


class Severity:
    """Alert severity levels, from least to most serious."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

    ORDER = [LOW, MEDIUM, HIGH, CRITICAL]
    # How much each level adds to a transaction's risk score (0-100).
    SCORES = {LOW: 10, MEDIUM: 30, HIGH: 50, CRITICAL: 100}


class Rule:
    """Names of everything that can appear in the fraud log."""

    # Behaviour rules (transaction accepted but flagged)
    LARGE_TRANSACTION = "LARGE_TRANSACTION"
    BALANCE_DRAIN = "BALANCE_DRAIN"
    HIGH_VELOCITY = "HIGH_VELOCITY"
    FIRST_TIME_RECIPIENT = "FIRST_TIME_RECIPIENT"
    # Security events (transaction rejected / attack detected)
    FORGED_SIGNATURE = "REJECTED_FORGED_SIGNATURE"
    INSUFFICIENT_BALANCE = "REJECTED_INSUFFICIENT_BALANCE"
    DOUBLE_SPEND = "REJECTED_DOUBLE_SPEND"
    INVALID_TRANSACTION = "REJECTED_INVALID_TRANSACTION"
    CHAIN_TAMPERING = "CHAIN_TAMPERING_DETECTED"


@dataclass
class FraudAlert:
    """One entry of the fraud log."""

    rule: str
    severity: str
    message: str
    tx_id: str = ""
    sender: str = ""
    receiver: str = ""
    amount: float = 0.0
    created_at: float = field(default_factory=lambda: round(time.time(), 6))


class FraudDetector:
    """Checks transactions against the fraud rules."""

    def __init__(
        self,
        large_threshold: float = config.LARGE_TX_THRESHOLD,
        drain_ratio: float = config.BALANCE_DRAIN_RATIO,
        velocity_window: float = config.VELOCITY_WINDOW_SECONDS,
        velocity_max: int = config.VELOCITY_MAX_TX,
    ):
        self.large_threshold = large_threshold
        self.drain_ratio = drain_ratio
        self.velocity_window = velocity_window
        self.velocity_max = velocity_max

    def analyze(self, tx, sender_history, sender_balance: float) -> list[FraudAlert]:
        """
        Run every rule against `tx`.

        tx              the new transaction
        sender_history  the sender's EARLIER outgoing transactions
                        (confirmed and pending, not including `tx`)
        sender_balance  what the sender could spend just before `tx`
        """
        if tx.is_coinbase:
            return []  # mining rewards are created by the system itself

        history = [old for old in sender_history if old.tx_id != tx.tx_id]
        alerts = []

        def alert(rule, severity, message):
            alerts.append(
                FraudAlert(
                    rule=rule,
                    severity=severity,
                    message=message,
                    tx_id=tx.tx_id,
                    sender=tx.sender,
                    receiver=tx.receiver,
                    amount=tx.amount,
                )
            )

        # Rule 1: large transaction
        if tx.amount >= self.large_threshold:
            alert(
                Rule.LARGE_TRANSACTION,
                Severity.HIGH,
                f"Large transfer of {tx.amount:,.2f} {config.COIN_SYMBOL} "
                f"(threshold {self.large_threshold:,.2f}).",
            )

        # Rule 2: wallet drained in a single payment
        if sender_balance > 0 and tx.amount >= self.drain_ratio * sender_balance:
            share = min(tx.amount / sender_balance, 1.0)
            alert(
                Rule.BALANCE_DRAIN,
                Severity.MEDIUM,
                f"Single payment spends {share:.0%} of the sender's available balance.",
            )

        # Rule 3: velocity - many payments in a short time
        window_start = tx.timestamp - self.velocity_window
        recent = [old for old in history if window_start <= old.timestamp <= tx.timestamp]
        count = len(recent) + 1  # +1 for the new transaction itself
        if count > self.velocity_max:
            alert(
                Rule.HIGH_VELOCITY,
                Severity.HIGH,
                f"{count} transactions from this wallet within "
                f"{self.velocity_window:.0f} seconds (limit {self.velocity_max}).",
            )

        # Rule 4: first payment to this receiver
        known_receivers = {old.receiver for old in history}
        if tx.receiver not in known_receivers:
            alert(
                Rule.FIRST_TIME_RECIPIENT,
                Severity.LOW,
                "First payment from this wallet to this recipient.",
            )

        return alerts

    # ----- scoring --------------------------------------------------------
    @staticmethod
    def risk_score(alerts) -> int:
        """Combine alerts into a single 0-100 risk score."""
        return min(100, sum(Severity.SCORES.get(a.severity, 0) for a in alerts))

    @staticmethod
    def risk_level(score: int) -> str:
        """Translate a risk score into a label."""
        if score >= 80:
            return Severity.CRITICAL
        if score >= 50:
            return Severity.HIGH
        if score >= 30:
            return Severity.MEDIUM
        if score > 0:
            return Severity.LOW
        return "NONE"
