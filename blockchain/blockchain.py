"""
The Blockchain: the ledger itself.

Responsibilities
----------------
* keep the list of blocks, starting with the genesis block
* accept new transactions into the pending pool - but only after checking
  the signature, the balance and double-spending
* mine pending transactions into a new block (Proof-of-Work)
* answer questions: balances, transaction history, validity

Coins come into existence only as mining rewards. A wallet's balance is
never stored anywhere: it is always recalculated from the chain, so it
cannot be edited separately from the transaction history.
"""

import time
from dataclasses import dataclass, field

import config
from blockchain.block import Block, new_block_timestamp
from security.validator import ChainValidator, ValidationReport
from transactions import (
    DoubleSpendError,
    InsufficientBalanceError,
    InvalidTransactionError,
    Transaction,
    TransactionPool,
)
from wallet import is_valid_address


@dataclass
class MiningResult:
    """What happened when a block was mined."""

    block: Block
    attempts: int                 # number of hashes tried
    duration: float               # seconds spent mining
    rejected: list = field(default_factory=list)   # (transaction, reason) pairs dropped at mining time


def create_genesis_block() -> Block:
    """The fixed first block. It has no transactions and no predecessor."""
    return Block(
        index=0,
        timestamp=config.GENESIS_TIMESTAMP,
        transactions=[],
        previous_hash=config.GENESIS_PREVIOUS_HASH,
        difficulty=0,
    )


class Blockchain:
    """An in-memory blockchain with a pending transaction pool."""

    def __init__(
        self,
        difficulty: int = config.MINING_DIFFICULTY,
        mining_reward: float = config.MINING_REWARD,
        chain: list[Block] | None = None,
        pending: list[Transaction] | None = None,
    ):
        self.difficulty = difficulty
        self.mining_reward = mining_reward
        # Start a new chain with the genesis block, or continue a stored one.
        self.chain: list[Block] = list(chain) if chain else [create_genesis_block()]
        self.pool = TransactionPool(pending)
        self.validator = ChainValidator(mining_reward=mining_reward)

    # ----- simple accessors ----------------------------------------------
    @property
    def latest_block(self) -> Block:
        return self.chain[-1]

    @property
    def pending_transactions(self) -> list[Transaction]:
        return self.pool.all()

    def set_difficulty(self, difficulty: int) -> None:
        if not isinstance(difficulty, int) or not config.MIN_DIFFICULTY <= difficulty <= config.MAX_DIFFICULTY:
            raise ValueError(
                f"Difficulty must be between {config.MIN_DIFFICULTY} and {config.MAX_DIFFICULTY}."
            )
        self.difficulty = difficulty

    # ----- balances -------------------------------------------------------
    def get_balance(self, address: str) -> float:
        """Confirmed balance: everything received minus everything sent, in mined blocks."""
        balance = 0.0
        for block in self.chain:
            for tx in block.transactions:
                if tx.receiver == address:
                    balance += tx.amount
                if tx.sender == address:
                    balance -= tx.amount
        return round(balance, config.AMOUNT_DECIMALS)

    def get_available_balance(self, address: str) -> float:
        """
        Spendable balance: confirmed balance minus coins already promised in
        pending transactions. Using THIS number for new payments is what
        stops the same coins from being spent twice before a block is mined.
        """
        available = self.get_balance(address) - self.pool.pending_outgoing(address)
        return round(available, config.AMOUNT_DECIMALS)

    # ----- transaction lookup --------------------------------------------
    def is_confirmed(self, tx_id: str) -> bool:
        """True if a transaction with this ID is already inside a block."""
        return any(tx.tx_id == tx_id for block in self.chain for tx in block.transactions)

    def get_transactions(self, address: str | None = None) -> list[dict]:
        """
        Transaction history, oldest first.

        Each entry is {"tx": Transaction, "block_index": int or None, "status": ...}.
        Pass an address to get only that wallet's transactions.
        """
        history = []
        for block in self.chain:
            for tx in block.transactions:
                history.append({"tx": tx, "block_index": block.index, "status": "Confirmed"})
        for tx in self.pool.all():
            history.append({"tx": tx, "block_index": None, "status": "Pending"})
        if address is not None:
            history = [h for h in history if address in (h["tx"].sender, h["tx"].receiver)]
        return history

    def get_sent_transactions(self, address: str) -> list[Transaction]:
        """Every transaction (confirmed or pending) sent FROM `address`."""
        return [h["tx"] for h in self.get_transactions(address) if h["tx"].sender == address]

    # ----- accepting transactions ----------------------------------------
    def add_transaction(self, tx: Transaction) -> None:
        """
        Validate a transaction and put it in the pending pool.

        Raises (and adds nothing) if the transaction is not acceptable:
          InvalidTransactionError   malformed or modified
          InvalidSignatureError     missing / forged signature
          DoubleSpendError          replayed, or its coins are already committed
          InsufficientBalanceError  sender does not own enough coins
        """
        if not isinstance(tx, Transaction):
            raise InvalidTransactionError("Not a transaction.")
        if tx.is_coinbase:
            raise InvalidTransactionError("Mining rewards can only be created by mining a block.")

        # 1. Format, integrity and digital signature
        tx.validate()
        if tx.timestamp > time.time() + config.MAX_FUTURE_DRIFT_SECONDS:
            raise InvalidTransactionError("Transaction timestamp is in the future.")

        # 2. Replay protection: the very same transaction may only exist once
        if tx.tx_id in self.pool or self.is_confirmed(tx.tx_id):
            raise DoubleSpendError("Duplicate transaction: this exact transaction was already submitted.")

        # 3. Balance and double-spend check
        confirmed = self.get_balance(tx.sender)
        available = self.get_available_balance(tx.sender)
        if tx.amount > confirmed:
            raise InsufficientBalanceError(
                f"Insufficient balance: wallet owns {confirmed:,.2f} {config.COIN_SYMBOL}, "
                f"tried to send {tx.amount:,.2f}."
            )
        if tx.amount > available:
            raise DoubleSpendError(
                f"Double-spend attempt: only {available:,.2f} {config.COIN_SYMBOL} is still "
                f"unspent - the rest is already committed to pending transactions."
            )

        self.pool.add(tx)

    # ----- mining ---------------------------------------------------------
    def mine_pending_transactions(self, miner_address: str, on_progress=None) -> MiningResult:
        """
        Put all valid pending transactions into a new block, mine it, and
        append it to the chain. The miner receives the mining reward.

        An empty pool is allowed: the block then contains only the reward
        (this is how the first coins enter circulation).

        on_progress is passed to Block.mine (live progress for the UI).
        """
        if not is_valid_address(miner_address):
            raise InvalidTransactionError("Miner address is not valid.")

        selected, rejected = self._select_valid_pending()
        reward = Transaction.coinbase(miner_address, self.mining_reward)
        block = Block(
            index=len(self.chain),
            timestamp=new_block_timestamp(),
            transactions=[reward] + selected,
            previous_hash=self.latest_block.hash,
            difficulty=self.difficulty,
        )

        started = time.perf_counter()
        attempts = block.mine(on_progress=on_progress)
        duration = time.perf_counter() - started

        self.chain.append(block)
        self.pool.clear()
        return MiningResult(block=block, attempts=attempts, duration=duration, rejected=rejected)

    def _select_valid_pending(self):
        """
        Final safety check before mining: re-verify every pending transaction
        and replay the spending so no wallet can go below zero inside the block.
        """
        selected, rejected = [], []
        running_balance: dict[str, float] = {}
        for tx in self.pool.all():
            try:
                tx.validate()
            except InvalidTransactionError as exc:
                rejected.append((tx, str(exc)))
                continue
            if self.is_confirmed(tx.tx_id):
                rejected.append((tx, "Already confirmed in an earlier block."))
                continue
            balance = running_balance.get(tx.sender, self.get_balance(tx.sender))
            if tx.amount > balance:
                rejected.append((tx, "Insufficient balance at mining time."))
                continue
            running_balance[tx.sender] = round(balance - tx.amount, config.AMOUNT_DECIMALS)
            selected.append(tx)
        return selected, rejected

    # ----- validation -----------------------------------------------------
    def validate(self) -> ValidationReport:
        """Run the full integrity check and return a detailed report."""
        return self.validator.validate(self.chain)

    def is_valid(self) -> bool:
        return self.validate().is_valid
