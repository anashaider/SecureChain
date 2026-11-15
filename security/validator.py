"""
Full blockchain validation.

`ChainValidator.validate` walks the chain from the genesis block to the tip
and re-checks EVERYTHING, trusting nothing that is stored:

  per block        index, stored hash vs recomputed hash, Merkle root,
                   link to the previous block, Proof-of-Work
  per transaction  data vs transaction ID, digital signature,
                   mining-reward rules, duplicates, balances

Because each layer protects the next, changing one old transaction is
caught several times over:

    edit amount            -> transaction no longer matches its ID / signature
    also fix the tx ID     -> Merkle root of the block no longer matches
    also fix Merkle root   -> block hash no longer matches
    also fix block hash    -> Proof-of-Work is gone and the NEXT block's
                              "previous hash" link is broken

The result is a ValidationReport listing every problem found.
"""

from dataclasses import dataclass, field

import config
from transactions.exceptions import InvalidTransactionError


@dataclass
class ValidationIssue:
    """One problem found in the chain."""

    block_index: int
    check: str          # short machine-friendly name, e.g. "BLOCK_HASH"
    message: str        # human explanation


@dataclass
class BlockResult:
    """Outcome of each check for a single block (shown in the UI table)."""

    index: int
    hash_ok: bool = True
    link_ok: bool = True
    pow_ok: bool = True
    merkle_ok: bool = True
    transactions_ok: bool = True

    @property
    def ok(self) -> bool:
        return all([self.hash_ok, self.link_ok, self.pow_ok, self.merkle_ok, self.transactions_ok])


@dataclass
class ValidationReport:
    """Everything `ChainValidator.validate` found."""

    blocks_checked: int = 0
    transactions_checked: int = 0
    issues: list[ValidationIssue] = field(default_factory=list)
    block_results: list[BlockResult] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.issues

    @property
    def first_bad_block(self):
        """Index of the earliest block with a problem (None if the chain is valid)."""
        return min((issue.block_index for issue in self.issues), default=None)


class ChainValidator:
    """Verifies the integrity of a list of blocks."""

    def __init__(
        self,
        mining_reward: float = config.MINING_REWARD,
        min_difficulty: int = config.MIN_DIFFICULTY,
    ):
        self.mining_reward = mining_reward
        self.min_difficulty = min_difficulty

    def validate(self, chain) -> ValidationReport:
        report = ValidationReport()
        if not chain:
            report.issues.append(ValidationIssue(0, "EMPTY_CHAIN", "The chain has no genesis block."))
            return report

        balances: dict[str, float] = {}   # replayed from scratch while walking the chain
        seen_tx_ids: set[str] = set()     # to catch a transaction included twice

        for position, block in enumerate(chain):
            result = BlockResult(index=position)

            def problem(check, message, flag):
                report.issues.append(ValidationIssue(position, check, message))
                setattr(result, flag, False)

            # ---- block header checks -----------------------------------
            if block.index != position:
                problem("BLOCK_INDEX", f"Block claims index {block.index} but sits at position {position}.", "hash_ok")

            if block.hash != block.compute_hash():
                problem("BLOCK_HASH", "Stored block hash does not match the recomputed SHA-256 hash.", "hash_ok")

            if block.merkle_root != block.compute_merkle_root():
                problem("MERKLE_ROOT", "Merkle root does not match the block's transactions.", "merkle_ok")

            if position == 0:
                if block.previous_hash != config.GENESIS_PREVIOUS_HASH:
                    problem("PREVIOUS_HASH", "Genesis block must point to the all-zero hash.", "link_ok")
                if block.transactions:
                    problem("GENESIS", "Genesis block must not contain transactions.", "transactions_ok")
            else:
                if block.previous_hash != chain[position - 1].hash:
                    problem("PREVIOUS_HASH", "Previous-hash link does not match the hash of the block before it.", "link_ok")
                if block.difficulty < self.min_difficulty:
                    problem("PROOF_OF_WORK", f"Difficulty {block.difficulty} is below the minimum of {self.min_difficulty}.", "pow_ok")
                elif not block.hash.startswith("0" * block.difficulty):
                    problem("PROOF_OF_WORK", f"Hash does not start with {block.difficulty} zeros - Proof-of-Work is invalid.", "pow_ok")
                self._check_coinbase(block, problem)

            # ---- transaction checks ------------------------------------
            for tx_position, tx in enumerate(block.transactions):
                report.transactions_checked += 1
                label = f"Transaction #{tx_position} ({str(tx.tx_id)[:12]}...)"

                try:
                    tx.validate()   # format, ID integrity and digital signature
                except InvalidTransactionError as exc:
                    problem("TRANSACTION", f"{label}: {exc}", "transactions_ok")

                if tx.tx_id in seen_tx_ids:
                    problem("DUPLICATE_TRANSACTION", f"{label}: appears more than once in the chain (double spend).", "transactions_ok")
                seen_tx_ids.add(tx.tx_id)

                # Replay the payment to make sure nobody spends coins they do not have.
                amount = tx.amount if isinstance(tx.amount, (int, float)) else 0.0
                if not tx.is_coinbase:
                    sender_balance = round(balances.get(tx.sender, 0.0), config.AMOUNT_DECIMALS)
                    if amount > sender_balance:
                        problem("BALANCE", f"{label}: sender spends {amount:,.2f} but only owns {sender_balance:,.2f}.", "transactions_ok")
                    balances[tx.sender] = balances.get(tx.sender, 0.0) - amount
                balances[tx.receiver] = balances.get(tx.receiver, 0.0) + amount

            report.blocks_checked += 1
            report.block_results.append(result)

        return report

    def _check_coinbase(self, block, problem) -> None:
        """Each mined block must start with exactly one correct mining reward."""
        coinbase_positions = [i for i, tx in enumerate(block.transactions) if tx.is_coinbase]
        if coinbase_positions != [0]:
            problem("COINBASE", "Block must contain exactly one mining reward, as its first transaction.", "transactions_ok")
        elif block.transactions[0].amount != self.mining_reward:
            problem("COINBASE", f"Mining reward must be exactly {self.mining_reward:,.2f} {config.COIN_SYMBOL}.", "transactions_ok")
