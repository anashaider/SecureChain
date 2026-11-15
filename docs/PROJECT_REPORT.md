# SecureChain

## A Peer-to-Peer Transaction Ledger with Digital Signatures and Fraud Detection

**Semester Project Report - Cybersecurity**

---

## Abstract

SecureChain is a working blockchain ledger implemented in Python. Users hold
wallets made of ECDSA key pairs and pay each other directly; every payment is
digitally signed, collected into blocks, and secured by SHA-256 hash links and
Proof-of-Work mining. The system rejects forged signatures, overspending and
double spending, flags suspicious behaviour with a rule-based fraud detector,
and can detect any modification of historical data. All data is persisted in
SQLite, private keys are stored only in password-encrypted form, and a
Streamlit dashboard exposes every function, including an Attack Lab that
demonstrates each defence against a real attack. The implementation is covered
by an automated pytest suite.

---

## 1. Introduction

### 1.1 Problem

A traditional payment system relies on a trusted central party (a bank) to keep
the ledger honest. If that ledger is a normal database, whoever controls it can
change history, and users must simply trust that this does not happen. A
digital payment system without such a party has to solve four security
problems by itself:

1. **Authenticity** - only the owner of an account may spend from it.
2. **Integrity** - recorded transactions must not be changed afterwards.
3. **Double spending** - the same digital coins must not be spent twice.
4. **Abuse detection** - valid-looking but suspicious activity should be noticed.

### 1.2 Objectives

* Implement a blockchain with blocks, a genesis block, SHA-256 hashing,
  Proof-of-Work and previous-hash linking.
* Implement wallets with ECDSA key pairs, addresses, signing and verification,
  with secure private key storage.
* Manage transactions with a pending pool, balance verification and
  double-spend prevention.
* Detect suspicious transactions and keep a fraud log.
* Validate the entire chain and detect modified historical transactions.
* Provide a professional dashboard, SQLite persistence and automated tests.

### 1.3 Scope

SecureChain is an educational system that runs as a single node. Payments are
peer-to-peer in the sense that value moves directly between wallets, authorised
only by cryptographic signatures, with no central authority approving them.
Networking between multiple nodes and distributed consensus are outside the
scope and are discussed as future work (section 9).

---

## 2. Background

### 2.1 Cryptographic hash functions - SHA-256

A hash function maps any input to a fixed-size output (256 bits for SHA-256).
Three properties matter here: the same input always gives the same output; a
tiny change in the input gives a completely different output; and it is
infeasible to find an input for a chosen output. SecureChain uses SHA-256 for
transaction IDs, Merkle roots, block hashes, Proof-of-Work and wallet addresses.

### 2.2 Digital signatures - ECDSA

In the Elliptic Curve Digital Signature Algorithm a user has a secret
**private key** and a derived **public key**. Signing a message needs the
private key; verifying the signature needs only the public key. A valid
signature proves that the message was approved by the key owner
(authenticity) and has not been changed since (integrity), and the signer
cannot later deny it (non-repudiation). SecureChain uses the secp256k1 curve,
the curve used by Bitcoin, through the `cryptography` library.

### 2.3 Blockchain

A blockchain is a list of blocks in which each block stores the hash of the
previous one. Changing an old block changes its hash, which breaks the link
stored in the next block. The chain is therefore *tamper-evident*: history
cannot be modified without the change being visible.

### 2.4 Proof-of-Work

A block is only valid if its hash starts with a required number of zeros. The
only way to find such a hash is to try many values of a counter (the *nonce*).
With difficulty *d* (hex digits) this takes about 16^d attempts on average,
while verification takes one hash. Proof-of-Work makes rewriting history
expensive: an attacker must redo the work for the changed block and every
block after it.

---

## 3. System Design

The architecture is layered (details in `docs/ARCHITECTURE.md`):

```
Presentation   app.py, ui/                 Streamlit dashboard
Application    node.py                     SecureChainNode facade
Domain         wallet/ transactions/       keys, payments,
               blockchain/ security/       blocks, fraud + validation
Persistence    database/                   SQLite
```

Design decisions and their reasons:

| Decision | Reason |
|---|---|
| One facade class (`SecureChainNode`) between UI and logic | The UI cannot bypass validation, and the logic is testable without a browser |
| Account-based balances computed from the chain | Simple to explain; no stored balance that could be edited separately |
| Specific exception class per rejection reason | The UI, the fraud log and the tests can tell exactly why a transaction failed |
| Fraud detector as a pure function | Easy to test with exact inputs; no database needed |
| Validator returns a report instead of True/False | The UI can show which block and which check failed |
| Hashes loaded from the database exactly as stored | Otherwise tampering with the file could not be detected |
| All constants in `config.py` | Behaviour can be tuned and explained from one place |

---

## 4. Implementation

### 4.1 Wallets (`wallet/wallet.py`)

A wallet wraps a secp256k1 private key.

* **Public key** - exported in compressed form (33 bytes).
* **Address** - `"SC"` followed by the first 40 hex characters of
  `SHA-256(public key)`. An address reveals nothing about the private key and
  cannot be chosen freely.
* **Signing** - `ECDSA(SHA-256)`; the signature is stored as hex.
* **Verification** - `verify_signature()` returns True or False and never
  raises, even for malformed input.

**Secure private key handling.** The private key is never written to disk in
plain form. `to_encrypted_pem(password)` serialises it as encrypted PKCS#8:
the password is stretched with PBKDF2-HMAC-SHA256 and the key is encrypted with
AES-256-CBC. Only this encrypted text is stored in the `wallets` table. The
password itself is never stored, so a stolen database file does not reveal any
key. To sign, the user supplies the password, the key is decrypted in memory,
used once and discarded. A test scans the raw database file to confirm that
the private key does not appear in binary, hex, decimal or unencrypted PEM form.

### 4.2 Transactions (`transactions/`)

A transaction contains sender, receiver, amount, timestamp, a random nonce, the
sender's public key and the signature.

```
payload   = canonical JSON of (sender, sender_public_key, receiver, amount, timestamp, nonce)
tx_id     = SHA-256(payload)
signature = ECDSA_sign(private_key, payload)
```

`Transaction.validate()` performs these checks in order:

1. Amount is a finite positive number with at most 8 decimals; addresses are
   well-formed; sender and receiver differ.
2. The stored `tx_id` equals the hash of the current content
   (detects modification).
3. The public key hashes to the sender's address
   (an attacker cannot attach their own key to a victim's address).
4. The signature verifies against the payload with that public key.

Mining rewards are *coinbase* transactions with the sender `"COINBASE"`. They
are unsigned, can only be created by the mining code, and are restricted by the
validator to exactly one per block with a fixed amount.

### 4.3 Pending pool, balances and double spending (`blockchain/blockchain.py`)

`Blockchain.add_transaction()` admits a transaction to the pending pool only if:

| Check | Error raised |
|---|---|
| It is a well-formed, correctly signed transaction | `InvalidTransactionError` / `InvalidSignatureError` |
| Its ID is not already in the pool or in a block (replay) | `DoubleSpendError` |
| Amount <= confirmed balance | `InsufficientBalanceError` |
| Amount <= available balance (confirmed minus pending) | `DoubleSpendError` |

Two balances are distinguished:

* **Confirmed balance** - received minus sent across all mined blocks.
* **Available balance** - confirmed balance minus the sender's own pending
  payments.

Double spending is prevented in three places:

1. **Before mining** - new payments are checked against the *available*
   balance, so coins already promised in a pending transaction cannot be
   promised again.
2. **Replay** - each transaction has a unique ID (thanks to the nonce); the
   same signed transaction is refused if it is already pending or confirmed.
3. **In validation** - the validator replays the whole chain, rejecting
   duplicate transaction IDs and any payment that exceeds the sender's balance
   at that point in history.

### 4.4 Blocks and Proof-of-Work (`blockchain/block.py`)

```
merkle_root = pairwise SHA-256 tree over the block's transaction IDs
hash        = SHA-256(index | timestamp | previous_hash | merkle_root | difficulty | nonce)
```

`Block.mine()` increases the nonce from 0 until the hash starts with
`difficulty` zeros and returns the number of attempts. The genesis block is
fixed (index 0, constant timestamp, all-zero previous hash, no transactions) so
every node starts from the identical block.

`Blockchain.mine_pending_transactions(miner)` re-verifies the pool, prepends
the reward transaction, builds the block on top of the current tip, mines it
and appends it. Mining an empty pool is allowed; this is how the first coins
enter circulation.

### 4.5 Fraud detection (`security/fraud_detector.py`)

Each accepted transaction is analysed against four rules:

| Rule | Severity | Condition (defaults) |
|---|---|---|
| Large transaction | HIGH | amount >= 200 SCC |
| High velocity | HIGH | more than 3 payments from the same wallet within 60 s |
| Balance drain | MEDIUM | amount >= 90 % of the sender's available balance |
| First-time recipient | LOW | no earlier payment from this sender to this receiver |

Severities add up to a risk score (LOW 10, MEDIUM 30, HIGH 50, maximum 100).
Alerts do not block the transaction: rule-based detection produces false
positives, so the system follows the practice of flagging for review.
Transactions that are actually *invalid* are always blocked by the checks in
4.2 and 4.3.

The fraud log (table `fraud_alerts`) also records security events: forged
signatures (CRITICAL), detected chain tampering (CRITICAL), double-spend
attempts (HIGH), overspending attempts and malformed transactions (MEDIUM).

### 4.6 Blockchain validation (`security/validator.py`)

`ChainValidator.validate()` walks the chain from the genesis block and
recomputes everything:

* stored block hash equals the recomputed header hash;
* Merkle root matches the block's transactions;
* `previous_hash` equals the hash of the preceding block;
* the hash satisfies the Proof-of-Work target;
* exactly one correct mining reward per block;
* every transaction passes `validate()` (ID and signature);
* no transaction ID appears twice;
* replaying all payments never makes a balance negative.

The result is a `ValidationReport` with a per-block result and a list of
issues (block number, failed check, explanation).

**Why tampering is always detected.** Suppose an attacker changes an amount in
an old transaction:

| Attacker's effort | What still exposes it |
|---|---|
| Changes only the amount | Transaction content no longer hashes to its ID |
| Also recomputes the transaction ID | Signature is invalid; Merkle root does not match |
| Also recomputes the Merkle root | Block hash does not match the header |
| Also recomputes the block hash | Proof-of-Work is lost; next block's link is broken |
| Also re-mines that block | Next block's link is still broken; signature still invalid |
| Re-mines every later block too | The signature is **still** invalid - it cannot be forged without the private key |

While validation fails, the node refuses new transactions and mining, so
nothing can be built on a corrupted ledger.

### 4.7 Persistence (`database/db.py`)

SQLite stores blocks, transactions (pending ones have a NULL block index),
wallets, the fraud log and a small key-value table. All statements are
parameterised, which prevents SQL injection. On start-up the node loads the
chain exactly as stored; if the database is empty it creates and saves the
genesis block. Tests confirm that blocks, pending transactions, wallets and
alerts survive a restart unchanged.

### 4.8 User interface (`app.py`, `ui/`)

The Streamlit dashboard has nine pages: Dashboard, Wallets, Send Transaction,
Transaction History, Mining, Fraud Alerts, Blockchain Explorer, Chain
Validation and Attack Lab. A dark theme with status colours (green = valid,
amber = warning, red = compromised) is defined in `ui/theme.py`. User-supplied
text is HTML-escaped before it is rendered, and wallet names are restricted to
letters, digits and a few punctuation characters.

The Attack Lab performs genuine attacks through the same code path as normal
transactions: a forged signature, a signed payment from an empty wallet, a
double spend with a replay, and direct modification of a confirmed transaction
in the SQLite file (with a backup so the demonstration can be undone).

---

## 5. Security Analysis

| Threat | Countermeasure | Verified by |
|---|---|---|
| Attacker spends from a victim's wallet | ECDSA signature; public key bound to address | `test_forged_signature_is_rejected`, `test_attacker_cannot_attach_own_public_key_to_victims_address` |
| Signed transaction modified in transit | Signature and ID cover all fields | `test_changing_amount_after_signing_is_detected` |
| Spending more than the balance | Balance derived from the chain | `test_insufficient_balance_is_rejected` |
| Double spend before confirmation | Available balance excludes pending payments | `test_double_spend_of_same_coins_is_rejected` |
| Replay of an old transaction | Unique IDs in pool and chain | `test_replaying_a_confirmed_transaction_is_rejected` |
| Minting coins | Coinbase only via mining; fixed reward | `test_users_cannot_submit_mining_rewards`, `test_inflated_mining_reward_is_detected` |
| Modifying historical data | Hash chain, Merkle root, PoW, signatures | `tests/test_validation.py` |
| Theft of the database file | Keys encrypted with PBKDF2 + AES-256 | `test_private_key_is_never_stored_in_plaintext` |
| Password guessing made easy | Minimum length; vague unlock error | `test_weak_passwords_are_rejected` |
| SQL injection | Parameterised queries | `test_sql_injection_attempt_is_stored_as_plain_text` |
| Fraudulent but valid behaviour | Fraud rules and persistent log | `tests/test_fraud.py` |

**Residual risks.** A weak wallet password can be brute-forced offline if the
database is stolen. An attacker who controls the machine while a wallet is
unlocked can read the key from memory. Because there is only one node, an
attacker who can replace the *entire* database with a different, internally
consistent chain would not be detected - in a real network other nodes'
copies and the accumulated Proof-of-Work prevent this.

---

## 6. Testing

Testing was done at three levels with pytest.

| Level | Files | Purpose |
|---|---|---|
| Unit | `test_wallet`, `test_transactions`, `test_blockchain`, `test_validation`, `test_fraud`, `test_database` | Each module in isolation, including invalid input and boundary values |
| Integration | `test_node` | Complete scenarios through `SecureChainNode`, including restart persistence |
| User interface | `test_ui` | Every dashboard page renders in three states (empty, demo data, tampered); sending and mining through the UI |

**Result: 198 tests, all passing** (170 unit and integration tests, 15 user
interface tests, 13 tests for the visualization data and UI hooks), in about
30 seconds. The command-line demonstration
(`python demo.py`) additionally reports 23 of 23 checks passed.

### Required demonstrations

| # | Demonstration | Test | Result |
|---|---|---|---|
| 1 | Successful signed transaction | `test_demo_1_successful_signed_transaction` | Pass |
| 2 | Forged signature rejection | `test_demo_2_forged_signature_is_rejected` | Pass |
| 3 | Insufficient balance rejection | `test_demo_3_insufficient_balance_is_rejected` | Pass |
| 4 | Double-spending prevention | `test_demo_4_double_spending_is_prevented` | Pass |
| 5 | Suspicious transaction detection | `test_demo_5_suspicious_transactions_are_detected` | Pass |
| 6 | Blockchain mining | `test_demo_6_blockchain_mining` | Pass |
| 7 | Historical tampering detection | `test_demo_7_historical_tampering_is_detected` | Pass |

The same seven scenarios can be run interactively in the dashboard and from
the command line with `python demo.py`.

---

## 7. Results

* A payment signed by its owner is accepted, mined and reflected in both balances.
* A transaction signed with the wrong key is rejected with "Invalid digital
  signature"; attaching the attacker's own public key is rejected because the
  key does not match the sender address.
* A payment larger than the sender's balance is rejected.
* A second payment of already-committed coins and a replayed transaction are
  both rejected as double spends.
* Large, rapid, draining and first-time payments produce alerts of the
  expected severity, stored in the fraud log.
* Mining produces blocks whose hashes meet the difficulty target; each extra
  difficulty level multiplies the expected work by 16.
* Editing a confirmed transaction in the database is detected and located to
  the exact block, even when the attacker recomputes the hashes; the node then
  refuses further transactions until the data is restored.

---

## 8. Limitations

* **Single node** - no networking, peer discovery or consensus between nodes.
* **Account model** - simpler than Bitcoin's UTXO model; adequate for the
  project's goals.
* **Fixed difficulty and reward** - no automatic difficulty adjustment or halving.
* **No transaction fees** - miners are paid only by the block reward.
* **Rule-based fraud detection** - fixed thresholds; no learning from data.
* **Floating-point amounts** - limited to 8 decimals and rounded consistently;
  a production system would use integer units.
* **Python mining speed** - difficulty is kept low so demonstrations are fast.

## 9. Future Work

* Multiple nodes communicating over a network, with the longest-valid-chain rule.
* Automatic difficulty adjustment based on block times.
* Transaction fees and miner prioritisation.
* Machine-learning-based anomaly detection alongside the rules.
* Mnemonic seed phrases and hardware-backed key storage.
* Merkle proofs so light clients can verify single transactions.

## 10. Conclusion

SecureChain demonstrates how a small number of cryptographic tools combine
into a ledger that does not depend on trust. Digital signatures ensure that
only owners can spend; hashing and Proof-of-Work make history tamper-evident;
balance and replay checks stop double spending; and a monitoring layer flags
unusual behaviour. Every objective in section 1.2 was implemented, exercised
in the dashboard, and verified by automated tests.

---

## References

1. S. Nakamoto, "Bitcoin: A Peer-to-Peer Electronic Cash System", 2008.
2. NIST FIPS 180-4, "Secure Hash Standard (SHS)", 2015.
3. NIST FIPS 186-5, "Digital Signature Standard (DSS)", 2023.
4. Certicom Research, "SEC 2: Recommended Elliptic Curve Domain Parameters", 2010.
5. RFC 8018, "PKCS #5: Password-Based Cryptography Specification Version 2.1", 2017.
6. Python Cryptographic Authority, `cryptography` library documentation, https://cryptography.io
7. Streamlit documentation, https://docs.streamlit.io
8. SQLite documentation, https://www.sqlite.org/docs.html

## Appendix A - Running the project

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

streamlit run app.py      # dashboard
python demo.py            # command-line demonstration
python -m pytest          # automated tests
```
