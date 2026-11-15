"""
The pending transaction pool (often called the "mempool").

Transactions wait here after they have been accepted and before a miner
puts them into a block.
"""

from transactions.exceptions import DoubleSpendError
from transactions.transaction import Transaction


class TransactionPool:
    """Ordered collection of transactions waiting to be mined."""

    def __init__(self, transactions=None):
        # dict keeps insertion order, and gives fast lookup by transaction ID
        self._transactions: dict[str, Transaction] = {}
        for tx in transactions or []:
            self._transactions[tx.tx_id] = tx

    def add(self, tx: Transaction) -> None:
        """Add a transaction; the same transaction can never be added twice."""
        if tx.tx_id in self._transactions:
            raise DoubleSpendError("This transaction is already waiting in the pending pool.")
        self._transactions[tx.tx_id] = tx

    def remove(self, tx_id: str) -> None:
        self._transactions.pop(tx_id, None)

    def clear(self) -> None:
        self._transactions.clear()

    def contains(self, tx_id: str) -> bool:
        return tx_id in self._transactions

    def all(self) -> list[Transaction]:
        """All pending transactions, oldest first."""
        return list(self._transactions.values())

    def by_sender(self, address: str) -> list[Transaction]:
        return [tx for tx in self._transactions.values() if tx.sender == address]

    def pending_outgoing(self, address: str) -> float:
        """Total amount `address` has already promised in pending transactions."""
        return sum(tx.amount for tx in self.by_sender(address))

    def __len__(self) -> int:
        return len(self._transactions)

    def __contains__(self, tx_id: str) -> bool:
        return self.contains(tx_id)
