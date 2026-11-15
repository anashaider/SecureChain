"""Tests for security/validator.py: every way of corrupting the chain must be detected."""

import config
from blockchain import Block
from transactions import Transaction, create_signed_transaction


def checks(report) -> set[str]:
    """The set of check names that failed."""
    return {issue.check for issue in report.issues}


def payment_in(chain, block_index):
    """The first non-reward transaction of a block."""
    return chain.chain[block_index].transactions[1]


# ----- healthy chains ------------------------------------------------------------
def test_fresh_chain_is_valid(chain):
    report = chain.validate()
    assert report.is_valid
    assert report.blocks_checked == 1
    assert report.first_bad_block is None


def test_chain_with_transactions_is_valid(busy_chain):
    report = busy_chain.validate()
    assert report.is_valid, report.issues
    assert report.blocks_checked == 5
    assert report.transactions_checked == 6
    assert all(result.ok for result in report.block_results)


# ----- tampering with historical transactions ------------------------------------
def test_modified_historical_amount_is_detected(busy_chain):
    payment_in(busy_chain, 3).amount = 3000.0
    report = busy_chain.validate()
    assert not report.is_valid
    assert "TRANSACTION" in checks(report)
    assert report.first_bad_block == 3
    assert not report.block_results[3].transactions_ok


def test_modified_receiver_is_detected(busy_chain, mallory):
    payment_in(busy_chain, 3).receiver = mallory.address
    assert "TRANSACTION" in checks(busy_chain.validate())


def test_tampering_with_recomputed_tx_id_is_detected(busy_chain):
    """Attacker also fixes the transaction ID -> signature and Merkle root expose it."""
    tx = payment_in(busy_chain, 3)
    tx.amount = 3000.0
    tx.tx_id = tx.compute_hash()
    report = busy_chain.validate()
    assert {"TRANSACTION", "MERKLE_ROOT"} <= checks(report)
    assert any("signature" in issue.message.lower() for issue in report.issues)


def test_tampering_with_all_hashes_recomputed_is_detected(busy_chain):
    """Attacker recomputes tx ID, Merkle root AND block hash -> PoW / chain link expose it."""
    block = busy_chain.chain[3]
    tx = block.transactions[1]
    tx.amount = 3000.0
    tx.tx_id = tx.compute_hash()
    block.merkle_root = block.compute_merkle_root()
    block.hash = block.compute_hash()
    report = busy_chain.validate()
    failed = checks(report)
    assert "PREVIOUS_HASH" in failed          # block 4 no longer points at block 3
    assert "TRANSACTION" in failed            # the signature still does not match
    assert report.first_bad_block == 3


def test_even_re_mining_the_block_cannot_hide_tampering(busy_chain):
    """Attacker redoes the Proof-of-Work of the edited block -> the next link still breaks."""
    block = busy_chain.chain[3]
    tx = block.transactions[1]
    tx.amount = 1.0
    tx.tx_id = tx.compute_hash()
    block.merkle_root = block.compute_merkle_root()
    block.mine()
    report = busy_chain.validate()
    assert report.block_results[3].pow_ok                 # PoW was redone...
    assert not report.block_results[4].link_ok            # ...but the chain is broken
    assert not report.block_results[3].transactions_ok    # ...and the signature is invalid


def test_removed_transaction_is_detected(busy_chain):
    del busy_chain.chain[3].transactions[1]
    assert "MERKLE_ROOT" in checks(busy_chain.validate())


def test_inserted_transaction_is_detected(busy_chain, alice, mallory):
    extra = create_signed_transaction(alice, mallory.address, 1)
    busy_chain.chain[2].transactions.append(extra)
    assert "MERKLE_ROOT" in checks(busy_chain.validate())


# ----- tampering with block headers ------------------------------------------------
def test_modified_block_hash_is_detected(busy_chain):
    busy_chain.chain[2].hash = "0" * 64
    failed = checks(busy_chain.validate())
    assert {"BLOCK_HASH", "PREVIOUS_HASH"} <= failed


def test_broken_previous_hash_link_is_detected(busy_chain):
    busy_chain.chain[2].previous_hash = "f" * 64
    report = busy_chain.validate()
    assert not report.block_results[2].link_ok
    assert "BLOCK_HASH" in checks(report)                 # the header changed, so the hash is stale


def test_modified_nonce_is_detected(busy_chain):
    busy_chain.chain[1].nonce += 1
    assert "BLOCK_HASH" in checks(busy_chain.validate())


def test_reordered_blocks_are_detected(busy_chain):
    busy_chain.chain[1], busy_chain.chain[2] = busy_chain.chain[2], busy_chain.chain[1]
    assert {"BLOCK_INDEX", "PREVIOUS_HASH"} <= checks(busy_chain.validate())


def test_block_without_proof_of_work_is_detected(busy_chain, mallory):
    """A block appended without mining (difficulty 0) is refused."""
    fake = Block(
        index=len(busy_chain.chain),
        timestamp=busy_chain.latest_block.timestamp + 1,
        transactions=[Transaction.coinbase(mallory.address, config.MINING_REWARD)],
        previous_hash=busy_chain.latest_block.hash,
        difficulty=0,
    )
    busy_chain.chain.append(fake)
    assert "PROOF_OF_WORK" in checks(busy_chain.validate())


def test_hash_not_meeting_difficulty_is_detected(busy_chain):
    block = busy_chain.chain[-1]
    block.difficulty = 20                                  # claims far more work than was done
    block.hash = block.compute_hash()
    assert "PROOF_OF_WORK" in checks(busy_chain.validate())


def test_modified_genesis_block_is_detected(busy_chain):
    busy_chain.chain[0].previous_hash = "1" * 64
    failed = checks(busy_chain.validate())
    assert "PREVIOUS_HASH" in failed and "BLOCK_HASH" in failed


# ----- economic rules ----------------------------------------------------------------
def forge_block(chain, transactions) -> Block:
    """Build and properly mine a block containing arbitrary transactions."""
    block = Block(
        index=len(chain.chain),
        timestamp=chain.latest_block.timestamp + 1,
        transactions=transactions,
        previous_hash=chain.latest_block.hash,
        difficulty=chain.difficulty,
    )
    block.mine()
    chain.chain.append(block)
    return block


def test_inflated_mining_reward_is_detected(busy_chain, mallory):
    forge_block(busy_chain, [Transaction.coinbase(mallory.address, 1_000_000)])
    assert "COINBASE" in checks(busy_chain.validate())


def test_block_without_reward_or_with_two_rewards_is_detected(busy_chain, mallory):
    reward = config.MINING_REWARD
    forge_block(busy_chain, [Transaction.coinbase(mallory.address, reward),
                             Transaction.coinbase(mallory.address, reward)])
    assert "COINBASE" in checks(busy_chain.validate())


def test_replayed_transaction_in_a_later_block_is_detected(busy_chain, mallory):
    """A miner copies an old, validly signed payment into a new block to get paid twice."""
    old_payment = payment_in(busy_chain, 3)
    forge_block(busy_chain, [Transaction.coinbase(mallory.address, config.MINING_REWARD),
                             Transaction.from_dict(old_payment.to_dict())])
    assert "DUPLICATE_TRANSACTION" in checks(busy_chain.validate())


def test_block_spending_more_than_the_balance_is_detected(busy_chain, bob, mallory):
    """A dishonest miner includes a correctly signed payment the sender cannot afford."""
    overspend = create_signed_transaction(bob, mallory.address, 5000)
    forge_block(busy_chain, [Transaction.coinbase(mallory.address, config.MINING_REWARD), overspend])
    assert "BALANCE" in checks(busy_chain.validate())


def test_empty_chain_is_invalid(chain):
    chain.chain.clear()
    assert "EMPTY_CHAIN" in checks(chain.validate())
