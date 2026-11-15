"""
The Block: a batch of transactions sealed with a SHA-256 hash.

Each block stores the hash of the block before it. That single field is
what turns a list of blocks into a *chain*: changing an old block changes
its hash, which no longer matches the "previous hash" stored in the next
block, and so on up to the tip.

Proof-of-Work
-------------
A block is only accepted if its hash starts with `difficulty` zeros.
The only way to find such a hash is to try different `nonce` values until
one works ("mining"). Finding it is slow; checking it takes one hash.
"""

import hashlib
import time
from dataclasses import dataclass, field

from transactions import Transaction


def sha256(text: str) -> str:
    """SHA-256 of a string, as 64 hex characters."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def merkle_root(tx_ids: list[str]) -> str:
    """
    Combine all transaction IDs into one fingerprint (the Merkle root).

    IDs are hashed together in pairs, then the results are paired again,
    until only one hash is left. If any transaction changes, the root changes.
    """
    if not tx_ids:
        return sha256("")
    level = list(tx_ids)
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])          # odd count: pair the last one with itself
        level = [sha256(level[i] + level[i + 1]) for i in range(0, len(level), 2)]
    return level[0]


@dataclass
class Block:
    """One block of the chain."""

    index: int
    timestamp: float
    transactions: list[Transaction]
    previous_hash: str
    difficulty: int
    nonce: int = 0
    merkle_root: str = ""
    hash: str = ""

    def __post_init__(self):
        # New blocks compute their own fingerprints; blocks loaded from
        # storage keep the stored values so tampering can be detected.
        if not self.merkle_root:
            self.merkle_root = self.compute_merkle_root()
        if not self.hash:
            self.hash = self.compute_hash()

    # ----- hashing --------------------------------------------------------
    def compute_merkle_root(self) -> str:
        return merkle_root([tx.tx_id for tx in self.transactions])

    def _header_prefix(self) -> str:
        """Everything that goes into the hash except the nonce."""
        return (
            f"{self.index}|{self.timestamp:.6f}|{self.previous_hash}|"
            f"{self.merkle_root}|{self.difficulty}|"
        )

    def compute_hash(self) -> str:
        """SHA-256 of the block header (index, time, previous hash, Merkle root, difficulty, nonce)."""
        return sha256(self._header_prefix() + str(self.nonce))

    # ----- Proof-of-Work --------------------------------------------------
    def header_prefix(self) -> str:
        """Public, read-only view of the header text that is hashed together with the nonce."""
        return self._header_prefix()

    def mine(self, on_progress=None, progress_every: int = 20_000) -> int:
        """
        Search for a nonce that gives a hash with `difficulty` leading zeros.

        on_progress  optional function called as on_progress(attempts, last_hash)
                     every `progress_every` attempts, so a user interface can
                     show the real search while it runs.

        Returns the number of hashes that were tried.
        """
        target = "0" * self.difficulty
        prefix = self._header_prefix()       # built once: only the nonce changes
        nonce = 0
        while True:
            candidate = sha256(prefix + str(nonce))
            if candidate.startswith(target):
                self.nonce = nonce
                self.hash = candidate
                return nonce + 1
            nonce += 1
            if on_progress is not None and nonce % progress_every == 0:
                on_progress(nonce, candidate)

    def has_valid_proof(self) -> bool:
        """True if the stored hash is correct AND meets the difficulty target."""
        return self.hash == self.compute_hash() and self.hash.startswith("0" * self.difficulty)

    # ----- (de)serialisation ---------------------------------------------
    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "previous_hash": self.previous_hash,
            "difficulty": self.difficulty,
            "nonce": self.nonce,
            "merkle_root": self.merkle_root,
            "hash": self.hash,
            "transactions": [tx.to_dict() for tx in self.transactions],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Block":
        return cls(
            index=data["index"],
            timestamp=data["timestamp"],
            transactions=[Transaction.from_dict(tx) for tx in data["transactions"]],
            previous_hash=data["previous_hash"],
            difficulty=data["difficulty"],
            nonce=data["nonce"],
            merkle_root=data["merkle_root"],
            hash=data["hash"],
        )


def new_block_timestamp() -> float:
    """Current time rounded so it is stored and re-loaded without change."""
    return round(time.time(), 6)
