"""Tests for security/fraud_detector.py: each rule fires when it should - and only then."""

import pytest

import config
from security import FraudAlert, FraudDetector, Rule, Severity
from transactions import Transaction

SENDER = "SC" + "a" * 40
KNOWN = "SC" + "b" * 40
STRANGER = "SC" + "c" * 40
NOW = 1_800_000_000.0


def make_tx(amount=10.0, receiver=KNOWN, timestamp=NOW, sender=SENDER) -> Transaction:
    # The detector only looks at the data, so unsigned transactions are fine here.
    return Transaction(sender=sender, receiver=receiver, amount=amount, timestamp=timestamp)


@pytest.fixture
def detector() -> FraudDetector:
    return FraudDetector(large_threshold=200, drain_ratio=0.9, velocity_window=60, velocity_max=3)


@pytest.fixture
def history() -> list[Transaction]:
    """One old payment to KNOWN, made long ago."""
    return [make_tx(timestamp=NOW - 10_000)]


def rules(alerts) -> set[str]:
    return {alert.rule for alert in alerts}


def test_normal_payment_raises_no_alerts(detector, history):
    assert detector.analyze(make_tx(amount=10), history, sender_balance=1000) == []


# ----- large transactions ---------------------------------------------------------
def test_large_transaction_is_flagged(detector, history):
    alerts = detector.analyze(make_tx(amount=250), history, sender_balance=5000)
    assert rules(alerts) == {Rule.LARGE_TRANSACTION}
    assert alerts[0].severity == Severity.HIGH
    assert alerts[0].amount == 250 and alerts[0].sender == SENDER


def test_large_threshold_boundary(detector, history):
    assert Rule.LARGE_TRANSACTION in rules(detector.analyze(make_tx(amount=200), history, 5000))
    assert Rule.LARGE_TRANSACTION not in rules(detector.analyze(make_tx(amount=199.99), history, 5000))


# ----- balance drain -----------------------------------------------------------------
def test_draining_the_wallet_is_flagged(detector, history):
    alerts = detector.analyze(make_tx(amount=95), history, sender_balance=100)
    assert rules(alerts) == {Rule.BALANCE_DRAIN}


def test_spending_part_of_the_balance_is_not_a_drain(detector, history):
    assert detector.analyze(make_tx(amount=50), history, sender_balance=100) == []


# ----- velocity ------------------------------------------------------------------------
def test_rapid_transactions_are_flagged(detector):
    recent = [make_tx(timestamp=NOW - seconds) for seconds in (30, 20, 10)]
    alerts = detector.analyze(make_tx(), recent, sender_balance=1000)
    assert rules(alerts) == {Rule.HIGH_VELOCITY}
    assert "4 transactions" in alerts[0].message


def test_velocity_limit_itself_is_allowed(detector):
    recent = [make_tx(timestamp=NOW - seconds) for seconds in (20, 10)]
    assert detector.analyze(make_tx(), recent, sender_balance=1000) == []     # 3rd tx in window


def test_old_transactions_do_not_count_towards_velocity(detector):
    old = [make_tx(timestamp=NOW - seconds) for seconds in (500, 400, 300)]
    assert detector.analyze(make_tx(), old, sender_balance=1000) == []


# ----- first-time recipient --------------------------------------------------------------
def test_first_time_recipient_is_flagged(detector, history):
    alerts = detector.analyze(make_tx(receiver=STRANGER), history, sender_balance=1000)
    assert rules(alerts) == {Rule.FIRST_TIME_RECIPIENT}
    assert alerts[0].severity == Severity.LOW


def test_known_recipient_is_not_flagged(detector, history):
    assert Rule.FIRST_TIME_RECIPIENT not in rules(detector.analyze(make_tx(receiver=KNOWN), history, 1000))


def test_very_first_transaction_of_a_wallet_is_first_time_recipient(detector):
    assert Rule.FIRST_TIME_RECIPIENT in rules(detector.analyze(make_tx(), [], 1000))


# ----- combinations and scoring --------------------------------------------------------------
def test_multiple_rules_can_fire_together(detector):
    recent = [make_tx(timestamp=NOW - seconds) for seconds in (30, 20, 10)]
    alerts = detector.analyze(make_tx(amount=300, receiver=STRANGER), recent, sender_balance=310)
    assert rules(alerts) == {
        Rule.LARGE_TRANSACTION, Rule.BALANCE_DRAIN, Rule.HIGH_VELOCITY, Rule.FIRST_TIME_RECIPIENT,
    }
    assert FraudDetector.risk_score(alerts) == 100           # capped at 100
    assert FraudDetector.risk_level(100) == Severity.CRITICAL


def test_risk_score_and_levels():
    low = [FraudAlert(Rule.FIRST_TIME_RECIPIENT, Severity.LOW, "")]
    high = low + [FraudAlert(Rule.LARGE_TRANSACTION, Severity.HIGH, "")]
    assert FraudDetector.risk_score([]) == 0
    assert FraudDetector.risk_level(0) == "NONE"
    assert FraudDetector.risk_level(FraudDetector.risk_score(low)) == Severity.LOW
    assert FraudDetector.risk_level(FraudDetector.risk_score(high)) == Severity.HIGH


def test_mining_rewards_are_never_flagged(detector):
    reward = Transaction.coinbase(KNOWN, 1_000_000)
    assert detector.analyze(reward, [], 0) == []


def test_the_transaction_itself_is_ignored_if_present_in_history(detector, history):
    tx = make_tx()
    assert detector.analyze(tx, history + [tx], sender_balance=1000) == []


def test_default_thresholds_come_from_config():
    detector = FraudDetector()
    assert detector.large_threshold == config.LARGE_TX_THRESHOLD
    assert detector.velocity_max == config.VELOCITY_MAX_TX
