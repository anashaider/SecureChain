"""Tests for blockchain/: blocks, hashing, Proof-of-Work, balances, double spending."""

import time

import pytest

import config
from blockchain import Block, Blockchain, merkle_root, sha256
from transactions import (
    DoubleSpendError,
    InsufficientBalanceError,
    InvalidSignatureError,
    InvalidTransactionError,
    Transaction,
    create_signed_transaction,
)


# ----- Block -------------------------------------------------------------------
def make_block(transactions=None, difficulty=2) -> Block:
    return Block(index=1, timestamp=1700000000.0, transactions=transactions or [],
                 previous_hash="a" * 64, difficulty=difficulty)


def test_sha256_matches_known_value():
    assert sha256("abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_block_hash_is_deterministic_and_64_hex_chars():
    block = make_block()
    assert block.hash == block.compute_hash() == make_block().hash
    assert len(block.hash) == 64


def test_block_hash_changes_when_any_header_field_changes():
    original = make_block().hash
    for change in ({"index": 2}, {"timestamp": 1700000001.0}, {"previous_hash": "b" * 64},
                   {"nonce": 1}, {"difficulty": 3}):
        block = make_block()
        for name, value in change.items():
            setattr(block, name, value)
        assert block.compute_hash() != original, f"hash ignored {change}"


def test_mining_finds_hash_with_leading_zeros():
    block = make_block(difficulty=3)
    attempts = block.mine()
    assert block.hash.startswith("000")
    assert block.has_valid_proof()
    assert attempts == block.nonce + 1


def test_changing_a_mined_block_invalidates_its_proof():
    block = make_block(difficulty=3)
    block.mine()
    block.previous_hash = "c" * 64
    assert not block.has_valid_proof()


def test_merkle_root_changes_when_a_transaction_changes():
    assert merkle_root(["a", "b", "c"]) != merkle_root(["a", "b", "x"])
    assert merkle_root(["a", "b"]) != merkle_root(["b", "a"])     # order matters


def test_merkle_root_edge_cases():
    assert merkle_root([]) == sha256("")
    assert merkle_root(["only"]) == "only"
    assert merkle_root(["a", "b", "c"]) == sha256(sha256("ab") + sha256("cc"))   # odd count


def test_block_dict_roundtrip(alice, bob):
    block = make_block([create_signed_transaction(alice, bob.address, 5)])
    block.mine()
    assert Block.from_dict(block.to_dict()) == block


# ----- Genesis and mining --------------------------------------------------------
def test_new_chain_starts_with_genesis_block(chain):
    genesis = chain.chain[0]
    assert len(chain.chain) == 1
    assert genesis.index == 0
    assert genesis.previous_hash == config.GENESIS_PREVIOUS_HASH
    assert genesis.transactions == []


def test_genesis_block_is_identical_on_every_node():
    assert Blockchain().chain[0].hash == Blockchain().chain[0].hash


def test_mining_adds_a_linked_block_with_proof_of_work(chain, alice):
    result = chain.mine_pending_transactions(alice.address)
    block = result.block
    assert len(chain.chain) == 2
    assert block.previous_hash == chain.chain[0].hash
    assert block.hash.startswith("0" * chain.difficulty)
    assert result.attempts >= 1 and result.duration >= 0


def test_miner_receives_the_reward(chain, alice):
    chain.mine_pending_transactions(alice.address)
    assert chain.get_balance(alice.address) == config.MINING_REWARD


def test_mining_requires_a_valid_miner_address(chain):
    with pytest.raises(InvalidTransactionError):
        chain.mine_pending_transactions("not-an-address")


def test_every_block_links_to_the_previous_one(busy_chain):
    for previous, current in zip(busy_chain.chain, busy_chain.chain[1:]):
        assert current.previous_hash == previous.hash


def test_difficulty_limits(chain):
    chain.set_difficulty(3)
    assert chain.difficulty == 3
    for bad in (0, config.MAX_DIFFICULTY + 1, "4", 2.5):
        with pytest.raises(ValueError):
            chain.set_difficulty(bad)


# ----- Transactions and balances ---------------------------------------------------
def test_valid_transaction_enters_pending_pool(funded_chain, alice, bob):
    tx = create_signed_transaction(alice, bob.address, 40)
    funded_chain.add_transaction(tx)
    assert funded_chain.pending_transactions == [tx]


def test_pending_transaction_reserves_funds_but_is_not_confirmed(funded_chain, alice, bob):
    funded_chain.add_transaction(create_signed_transaction(alice, bob.address, 40))
    assert funded_chain.get_balance(alice.address) == 200
    assert funded_chain.get_available_balance(alice.address) == 160
    assert funded_chain.get_balance(bob.address) == 0


def test_mining_confirms_the_payment(funded_chain, alice, bob):
    funded_chain.add_transaction(create_signed_transaction(alice, bob.address, 40))
    result = funded_chain.mine_pending_transactions(bob.address)
    assert len(result.block.transactions) == 2                    # reward + payment
    assert funded_chain.pending_transactions == []
    assert funded_chain.get_balance(alice.address) == 160
    assert funded_chain.get_balance(bob.address) == 40 + config.MINING_REWARD


def test_insufficient_balance_is_rejected(funded_chain, alice, bob):
    with pytest.raises(InsufficientBalanceError):
        funded_chain.add_transaction(create_signed_transaction(alice, bob.address, 200.01))
    with pytest.raises(InsufficientBalanceError):
        funded_chain.add_transaction(create_signed_transaction(bob, alice.address, 1))   # Bob owns nothing
    assert funded_chain.pending_transactions == []


def test_spending_the_exact_balance_is_allowed(funded_chain, alice, bob):
    funded_chain.add_transaction(create_signed_transaction(alice, bob.address, 200))
    assert funded_chain.get_available_balance(alice.address) == 0


def test_double_spend_of_same_coins_is_rejected(funded_chain, alice, bob, mallory):
    """Alice owns 200. She promises 150 to Bob, then tries to promise 150 to someone else."""
    funded_chain.add_transaction(create_signed_transaction(alice, bob.address, 150))
    with pytest.raises(DoubleSpendError, match="Double-spend"):
        funded_chain.add_transaction(create_signed_transaction(alice, mallory.address, 150))
    assert len(funded_chain.pending_transactions) == 1


def test_replaying_a_pending_transaction_is_rejected(funded_chain, alice, bob):
    tx = create_signed_transaction(alice, bob.address, 10)
    funded_chain.add_transaction(tx)
    with pytest.raises(DoubleSpendError, match="Duplicate"):
        funded_chain.add_transaction(tx)


def test_replaying_a_confirmed_transaction_is_rejected(funded_chain, alice, bob):
    tx = create_signed_transaction(alice, bob.address, 10)
    funded_chain.add_transaction(tx)
    funded_chain.mine_pending_transactions(alice.address)
    with pytest.raises(DoubleSpendError, match="Duplicate"):
        funded_chain.add_transaction(Transaction.from_dict(tx.to_dict()))
    assert funded_chain.get_balance(bob.address) == 10            # paid once only


def test_forged_transaction_never_reaches_the_pool(funded_chain, alice, mallory):
    forged = Transaction(sender=alice.address, receiver=mallory.address, amount=50)
    forged.sender_public_key = alice.public_key_hex
    forged.tx_id = forged.compute_hash()
    forged.signature = mallory.sign(forged.payload())
    with pytest.raises(InvalidSignatureError):
        funded_chain.add_transaction(forged)
    assert funded_chain.pending_transactions == []


def test_users_cannot_submit_mining_rewards(chain, mallory):
    with pytest.raises(InvalidTransactionError, match="mining"):
        chain.add_transaction(Transaction.coinbase(mallory.address, 1_000_000))


def test_future_dated_transaction_is_rejected(funded_chain, alice, bob):
    tx = Transaction(sender=alice.address, receiver=bob.address, amount=1,
                     timestamp=time.time() + 3600).sign(alice)
    with pytest.raises(InvalidTransactionError, match="future"):
        funded_chain.add_transaction(tx)


def test_non_transaction_objects_are_rejected(chain):
    with pytest.raises(InvalidTransactionError):
        chain.add_transaction({"sender": "x", "receiver": "y", "amount": 1})


def test_mining_drops_transactions_that_became_invalid(funded_chain, alice, bob):
    """Even if a bad transaction somehow sat in the pool, it must not be mined."""
    good = create_signed_transaction(alice, bob.address, 10)
    bad = create_signed_transaction(alice, bob.address, 20)
    funded_chain.add_transaction(good)
    funded_chain.add_transaction(bad)
    bad.amount = 9999.0                                           # corrupted while pending
    result = funded_chain.mine_pending_transactions(alice.address)
    assert [tx.tx_id for tx in result.block.transactions[1:]] == [good.tx_id]
    assert len(result.rejected) == 1
    assert funded_chain.is_valid()


def test_transaction_history(busy_chain, alice, bob):
    everything = busy_chain.get_transactions()
    assert len(everything) == 6                                   # 4 rewards + 2 payments
    assert all(entry["status"] == "Confirmed" for entry in everything)
    bobs = busy_chain.get_transactions(bob.address)
    assert all(bob.address in (e["tx"].sender, e["tx"].receiver) for e in bobs)
    assert len(busy_chain.get_sent_transactions(bob.address)) == 1

    busy_chain.add_transaction(create_signed_transaction(alice, bob.address, 1))
    assert busy_chain.get_transactions()[-1]["status"] == "Pending"
