"""
SecureChain command-line demonstration.

Runs the seven required demonstrations one after another and prints what
happens. It uses a temporary database, so it never touches the data shown
in the dashboard.

Run with:   python demo.py
"""

import sys
import tempfile
from pathlib import Path

import config
from node import ChainIntegrityError, SecureChainNode
from transactions import (
    DoubleSpendError,
    InsufficientBalanceError,
    InvalidSignatureError,
    Transaction,
)
from wallet import Wallet

PASSWORD = "demo-pass-123"
results: list[tuple[str, bool]] = []


def title(number: int, text: str) -> None:
    print(f"\n{'=' * 72}\nDEMO {number}: {text}\n{'=' * 72}")


def check(description: str, passed: bool) -> None:
    """Print one verified fact and remember whether it held."""
    print(f"  [{'PASS' if passed else 'FAIL'}] {description}")
    results.append((description, passed))


def main() -> int:
    with tempfile.TemporaryDirectory() as folder:
        node = SecureChainNode(db_path=Path(folder) / "demo.db", difficulty=3)
        coin = config.COIN_SYMBOL

        # ----- setup ---------------------------------------------------------
        print("SETUP: creating wallets for Alice, Bob and Charlie")
        alice = node.create_wallet("Alice", PASSWORD)["address"]
        bob = node.create_wallet("Bob", PASSWORD)["address"]
        charlie = node.create_wallet("Charlie", PASSWORD)["address"]
        for name, address in (("Alice", alice), ("Bob", bob), ("Charlie", charlie)):
            print(f"  {name:8} {address}")

        # ----- 6. mining (first, because it creates the coins) -----------------
        title(6, "Blockchain mining (Proof-of-Work)")
        for _ in range(3):
            mined = node.mine(alice)
            block = mined.block
            print(f"  Block #{block.index} mined: nonce={block.nonce:<6} attempts={mined.attempts:<6} "
                  f"hash={block.hash[:24]}...")
        check("each block hash starts with the required zeros",
              all(b.hash.startswith("0" * b.difficulty) for b in node.blockchain.chain[1:]))
        check("each block points to the hash of the previous block",
              all(b.previous_hash == a.hash for a, b in zip(node.blockchain.chain, node.blockchain.chain[1:])))
        check(f"Alice earned 3 x {config.MINING_REWARD:.0f} {coin} in rewards",
              node.blockchain.get_balance(alice) == 3 * config.MINING_REWARD)

        # ----- 1. successful signed transaction ---------------------------------
        title(1, "Successful signed transaction")
        sent = node.send(alice, PASSWORD, bob, 40)
        tx = sent.transaction
        print(f"  Alice -> Bob 40 {coin}")
        print(f"  tx id     {tx.tx_id}")
        print(f"  signature {tx.signature[:48]}...")
        check("signature verifies with Alice's public key", tx.is_valid())
        check("transaction is waiting in the pending pool", tx in node.blockchain.pending_transactions)
        node.mine(bob)
        check("after mining, Bob owns 40 + the block reward",
              node.blockchain.get_balance(bob) == 40 + config.MINING_REWARD)
        check("Alice's balance went down by 40", node.blockchain.get_balance(alice) == 260)

        # ----- 2. forged signature ----------------------------------------------
        title(2, "Forged signature rejection")
        mallory = Wallet.create()
        forged = Transaction(sender=alice, receiver=mallory.address, amount=100)
        forged.sender_public_key = node.get_wallet_info(alice)["public_key"]
        forged.tx_id = forged.compute_hash()
        forged.signature = mallory.sign(forged.payload())
        print("  Mallory writes 'Alice pays Mallory 100' and signs it with her own key")
        try:
            node.submit_transaction(forged)
            check("forged transaction rejected", False)
        except InvalidSignatureError as exc:
            print(f"  Node said: {exc}")
            check("forged transaction rejected", True)
        check("Alice's balance is untouched", node.blockchain.get_available_balance(alice) == 260)

        # ----- 3. insufficient balance ------------------------------------------
        title(3, "Insufficient balance rejection")
        print(f"  Charlie owns {node.blockchain.get_balance(charlie):.0f} {coin} and tries to send 25")
        try:
            node.send(charlie, PASSWORD, bob, 25)
            check("overspending transaction rejected", False)
        except InsufficientBalanceError as exc:
            print(f"  Node said: {exc}")
            check("overspending transaction rejected", True)

        # ----- 4. double spending -----------------------------------------------
        title(4, "Double-spending prevention")
        print(f"  Alice owns 260 {coin}. She signs 200 to Bob, then 200 to Charlie.")
        first = node.send(alice, PASSWORD, bob, 200).transaction
        check("first payment accepted", first in node.blockchain.pending_transactions)
        try:
            node.send(alice, PASSWORD, charlie, 200)
            check("second payment of the same coins rejected", False)
        except DoubleSpendError as exc:
            print(f"  Node said: {exc}")
            check("second payment of the same coins rejected", True)
        try:
            node.submit_transaction(first)
            check("replay of the first payment rejected", False)
        except DoubleSpendError as exc:
            print(f"  Node said: {exc}")
            check("replay of the first payment rejected", True)
        node.mine(alice)
        check("Charlie received nothing", node.blockchain.get_balance(charlie) == 0)

        # ----- 5. suspicious transactions ---------------------------------------
        title(5, "Suspicious transaction detection")
        print(f"  The 200 {coin} payment above was accepted but flagged:")
        for alert in node.get_alerts():
            if alert["tx_id"] == first.tx_id and not alert["rule"].startswith("REJECTED"):
                print(f"    [{alert['severity']:8}] {alert['rule']}: {alert['message']}")
        rules = {a["rule"] for a in node.get_alerts() if a["tx_id"] == first.tx_id}
        check("large transaction detected", "LARGE_TRANSACTION" in rules)
        print("  Alice now fires 4 small payments to Charlie within seconds:")
        velocity = False
        for _ in range(4):
            for alert in node.send(alice, PASSWORD, charlie, 1).alerts:
                print(f"    [{alert.severity:8}] {alert.rule}: {alert.message}")
                velocity = velocity or alert.rule == "HIGH_VELOCITY"
        check("first-time recipient detected",
              any(a["rule"] == "FIRST_TIME_RECIPIENT" and a["receiver"] == charlie for a in node.get_alerts()))
        check("rapid transactions (velocity) detected", velocity)
        check("every alert is stored in the fraud log", node.get_stats()["alerts"] >= 6)
        node.mine(bob)

        # ----- 7. tampering -------------------------------------------------------
        title(7, "Historical transaction tampering detection")
        check("chain is valid before the attack", node.validate_chain().is_valid)
        print("  Attacker edits the database: Alice -> Bob 40 becomes 4000 (block #4)")
        node.tamper_with_transaction(block_index=4, tx_position=1, new_amount=4000)
        report = node.validate_chain()
        for issue in report.issues[:4]:
            print(f"    block #{issue.block_index} {issue.check}: {issue.message}")
        check("validation detects the modified transaction", not report.is_valid)
        check("the problem is located in block #4", report.first_bad_block == 4)
        try:
            node.mine(alice)
            check("node refuses to mine on a corrupted chain", False)
        except ChainIntegrityError:
            check("node refuses to mine on a corrupted chain", True)
        node.restore_tampering()
        check("chain is valid again after restoring the original block", node.validate_chain().is_valid)

        # ----- summary --------------------------------------------------------------
        stats = node.get_stats()
        failed = [description for description, passed in results if not passed]
        print(f"\n{'=' * 72}")
        print(f"Final state: {stats['blocks']} blocks, {stats['confirmed_transactions']} confirmed "
              f"transactions, {stats['alerts']} fraud-log entries, chain valid = {stats['is_valid']}")
        print(f"RESULT: {len(results) - len(failed)}/{len(results)} checks passed")
        for description in failed:
            print(f"  FAILED: {description}")
        return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
