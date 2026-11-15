"""
Shared pytest fixtures.

Tests use a low mining difficulty (2) so blocks are mined instantly, and a
temporary database file so the real data/securechain.db is never touched.
"""

import pytest

from blockchain import Blockchain
from node import SecureChainNode
from transactions import create_signed_transaction
from wallet import Wallet

TEST_DIFFICULTY = 2
PASSWORD = "correct-horse-battery"


@pytest.fixture
def alice() -> Wallet:
    return Wallet.create()


@pytest.fixture
def bob() -> Wallet:
    return Wallet.create()


@pytest.fixture
def mallory() -> Wallet:
    """The attacker."""
    return Wallet.create()


@pytest.fixture
def chain() -> Blockchain:
    """An empty blockchain (genesis block only)."""
    return Blockchain(difficulty=TEST_DIFFICULTY)


@pytest.fixture
def funded_chain(chain, alice) -> Blockchain:
    """A blockchain where Alice has mined two blocks and owns 200 coins."""
    chain.mine_pending_transactions(alice.address)
    chain.mine_pending_transactions(alice.address)
    return chain


@pytest.fixture
def busy_chain(funded_chain, alice, bob) -> Blockchain:
    """A longer chain with confirmed payments: genesis + 4 mined blocks."""
    funded_chain.add_transaction(create_signed_transaction(alice, bob.address, 30))
    funded_chain.mine_pending_transactions(alice.address)
    funded_chain.add_transaction(create_signed_transaction(bob, alice.address, 5))
    funded_chain.mine_pending_transactions(bob.address)
    return funded_chain


@pytest.fixture
def node(tmp_path) -> SecureChainNode:
    """A full node backed by a temporary SQLite file."""
    return SecureChainNode(db_path=tmp_path / "test.db", difficulty=TEST_DIFFICULTY)
