"""
Error types raised when a transaction is rejected.

Using a separate class for each reason lets the rest of the program (and the
tests) tell exactly WHY a transaction was refused.
"""


class TransactionError(Exception):
    """Base class for every transaction rejection."""


class InvalidTransactionError(TransactionError):
    """The transaction is malformed (bad address, bad amount, modified data...)."""


class InvalidSignatureError(InvalidTransactionError):
    """The digital signature is missing, forged, or made with the wrong key."""


class InsufficientBalanceError(TransactionError):
    """The sender does not own enough coins."""


class DoubleSpendError(TransactionError):
    """The same coins (or the very same transaction) are being spent twice."""
