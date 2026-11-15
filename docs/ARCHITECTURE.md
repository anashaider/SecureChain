# SecureChain - Software Architecture

## 1. Overview

SecureChain is built in layers. Each layer only uses the layers below it, so
every module can be understood and tested on its own.

```
┌──────────────────────────────────────────────────────────────────────┐
│  PRESENTATION      app.py  +  ui/  (Streamlit pages, theme, widgets)   │
├──────────────────────────────────────────────────────────────────────┤
│  APPLICATION       node.py  -  SecureChainNode (facade)                │
│                    coordinates everything, saves to DB, logs alerts    │
├───────────────────────────────┬──────────────────────────────────────┤
│  DOMAIN                       │  PERSISTENCE                         │
│  blockchain/  Block, Blockchain│  database/  Database (SQLite)        │
│  security/    FraudDetector,   │                                      │
│               ChainValidator   │                                      │
│  transactions/ Transaction,    │                                      │
│               TransactionPool  │                                      │
│  wallet/      Wallet, signing  │                                      │
├───────────────────────────────┴──────────────────────────────────────┤
│  FOUNDATION        config.py, hashlib (SHA-256), cryptography (ECDSA)  │
└──────────────────────────────────────────────────────────────────────┘
```

Import direction (an arrow means "is imported by"):

```
config -> wallet -> transactions -> security -> blockchain -> database -> node -> ui -> app
```

There are no circular imports. The user interface never touches the database
or the blockchain classes for writing - it always goes through `SecureChainNode`.

## 2. Modules

### 2.1 `wallet/` - identity and signatures

| Item | Purpose |
|---|---|
| `Wallet.create()` | Generates a random secp256k1 private key |
| `Wallet.public_key_hex` | Compressed public key (33 bytes, 66 hex characters) |
| `Wallet.address` | `"SC"` + first 40 hex characters of `SHA-256(public key)` |
| `Wallet.sign(bytes)` | ECDSA signature with SHA-256, returned as hex |
| `verify_signature(pub, msg, sig)` | Returns True/False, never raises |
| `Wallet.to_encrypted_pem(password)` | Private key encrypted with the password (PKCS#8, PBKDF2 + AES-256-CBC) |
| `Wallet.from_encrypted_pem(pem, password)` | Unlocks a wallet; wrong password raises `WalletError` |

The private key lives in a private attribute, is excluded from `repr`, and can
only leave the object in encrypted form.

### 2.2 `transactions/` - payments

`Transaction` fields: `sender`, `receiver`, `amount`, `timestamp`, `nonce`,
`sender_public_key`, `signature`, `tx_id`.

* **Payload** - the six content fields serialised as canonical JSON (sorted keys,
  fixed number formats). The same transaction always gives the same bytes.
* **Transaction ID** - `SHA-256(payload)`.
* **Signature** - ECDSA over the payload, made by the sender's wallet.
* **`validate()`** checks, in order: field formats, ID matches content,
  public key hashes to the sender address, signature is valid.
* **Coinbase** transactions (sender `"COINBASE"`) are the mining rewards; they
  create coins and carry no signature.
* The random `nonce` makes two otherwise identical payments different
  transactions, so each can be accepted exactly once.

`TransactionPool` is the ordered set of accepted-but-unmined transactions and
can report how much each sender has already committed.

Rejections use specific exception classes:

```
TransactionError
├── InvalidTransactionError       malformed or modified data
│   └── InvalidSignatureError     missing / forged signature, wrong key
├── InsufficientBalanceError      sender does not own enough
└── DoubleSpendError              replay, or coins already committed
```

### 2.3 `blockchain/` - blocks and the chain

`Block` fields: `index`, `timestamp`, `transactions`, `previous_hash`,
`difficulty`, `nonce`, `merkle_root`, `hash`.

```
block hash = SHA-256( index | timestamp | previous_hash | merkle_root | difficulty | nonce )
merkle root = pairwise SHA-256 tree over the transaction IDs
```

`Block.mine()` increments the nonce until the hash starts with `difficulty` zeros.

`Blockchain` owns the list of blocks and the pending pool:

| Method | Behaviour |
|---|---|
| `add_transaction(tx)` | Validate, check replay, check balance / double spend, add to pool |
| `mine_pending_transactions(miner)` | Re-check the pool, add the reward, mine, append |
| `get_balance(address)` | Received minus sent, over mined blocks |
| `get_available_balance(address)` | Balance minus the sender's pending payments |
| `validate()` | Delegates to `ChainValidator` |

Balances are **never stored** - they are always recomputed from the chain, so
there is no separate number an attacker could edit.

### 2.4 `security/` - fraud detection and validation

**`FraudDetector.analyze(tx, sender_history, sender_balance)`** is a pure
function returning a list of `FraudAlert`s.

| Rule | Severity | Condition |
|---|---|---|
| `LARGE_TRANSACTION` | HIGH | amount >= 200 SCC |
| `HIGH_VELOCITY` | HIGH | more than 3 payments from the wallet within 60 s |
| `BALANCE_DRAIN` | MEDIUM | amount >= 90 % of the available balance |
| `FIRST_TIME_RECIPIENT` | LOW | sender never paid this receiver before |

Alerts flag a transaction; they do not block it (like a bank's monitoring
system). Each severity contributes to a 0-100 risk score.

**`ChainValidator.validate(chain)`** walks every block and returns a
`ValidationReport` with a per-block result and a list of issues:

| Check | Detects |
|---|---|
| `BLOCK_INDEX` | Reordered or missing blocks |
| `BLOCK_HASH` | Any change to a block header |
| `MERKLE_ROOT` | Added, removed or swapped transactions |
| `PREVIOUS_HASH` | A broken link between blocks |
| `PROOF_OF_WORK` | A block that was not mined |
| `COINBASE` | Missing, duplicated or inflated mining reward |
| `TRANSACTION` | Modified transaction data, invalid signature |
| `DUPLICATE_TRANSACTION` | The same transaction in two places |
| `BALANCE` | A wallet spending more than it owned at that point |

### 2.5 `database/` - persistence

One SQLite file (`data/securechain.db`) with five tables:

```
blocks(block_index PK, timestamp, previous_hash, merkle_root, difficulty, nonce, hash)

transactions(row_id PK, tx_id, block_index NULL=pending, position,
             sender, receiver, amount, timestamp, nonce, sender_public_key, signature)

wallets(address PK, name UNIQUE, public_key, encrypted_private_key, created_at)

fraud_alerts(id PK, created_at, rule, severity, message, tx_id, sender, receiver, amount)

meta(key PK, value)            -- backup used by the tampering demonstration
```

* All SQL uses `?` placeholders (no SQL injection).
* Stored hashes are loaded exactly as stored and **never recalculated on load** -
  that is what allows validation to detect a modified database.
* Saving a block and removing its transactions from the pending rows happen in
  one database transaction.

### 2.6 `node.py` - the application facade

`SecureChainNode` is the single entry point for the UI and the demo script.

| Group | Methods |
|---|---|
| Wallets | `create_wallet`, `list_wallets`, `unlock_wallet`, `export_keystore`, `rename_wallet`, `delete_wallet` |
| Transactions | `send`, `submit_transaction`, `get_history` |
| Mining | `mine`, `set_difficulty` |
| Security | `validate_chain`, `get_alerts`, `get_stats` |
| Demonstrations | `tamper_with_transaction`, `restore_tampering`, `seed_demo_data`, `reset` |

It adds three guarantees on top of the domain classes:

1. everything accepted in memory is written to SQLite;
2. every rejected or suspicious transaction is written to the fraud log;
3. no transaction or block is accepted while the stored chain fails validation.

### 2.7 `ui/` - the dashboard

`app.py` sets up the page and the sidebar, then calls `render(node)` of the
selected module in `ui/views/`. `ui/components.py` holds shared widgets;
`ui/theme.py` holds the CSS. The node is created once with
`st.cache_resource` and shared by all sessions.

### 2.8 `ui/frontend/` and `ui/viz.py` - interactive visualizations

The 3D views are a single custom Streamlit component written in plain
JavaScript (no build step) on top of Three.js r147, which is vendored in
the project so the app works offline.

```
Python (ui/viz.py)                          Browser (ui/frontend/, sandboxed iframe)
  chain_payload(node)    ── JSON ──▶  chain.js     3D blocks, links, click-to-inspect
  network_payload(node)  ── JSON ──▶  network.js   wallets as nodes, payments as particles
  pow_payload(node, …)   ── JSON ──▶  pow.js       re-computes SHA-256(header + nonce)
  tamper_payload(node)   ── JSON ──▶  hashdiff.js  re-computes hashes, compares per character
```

Design rules:

* **One-way data flow.** The component never returns a value, so camera
  movement and clicks cannot trigger reruns or touch `st.session_state`.
* **Public data only.** Payloads contain hashes, addresses, amounts and
  signature validity. A test (`test_no_secret_ever_reaches_the_browser`)
  serialises every payload and searches it for private keys, the keystore
  and the password.
* **Nothing simulated.** `core.js` contains a SHA-256 implementation
  (checked against Node's `crypto`), so the Proof-of-Work replay and the
  tampering comparison show hashes computed in the browser from real data.
* **Graceful fallback.** Without WebGL the chain and network render as 2D cards.
* **GPU-friendly.** Rendering pauses when the frame is off-screen or the tab
  is hidden; pixel ratio is capped; `prefers-reduced-motion` is honoured.

Three small backend hooks support the UI without changing any security logic:
`Block.mine(on_progress=...)` (live mining console), `SecureChainNode.sync()`
(reload if another process changed the database) and
`SecureChainNode.get_tamper_comparison()` (read-only before/after data).

## 3. Key flows

### 3.1 Sending a payment

```
User (Send page)
  │  sender, receiver, amount, password
  ▼
node.send()
  │  1. validate_chain()                     refuse if the ledger is corrupted
  │  2. unlock_wallet(password)              decrypt private key in memory
  │  3. Transaction(...).sign(wallet)        SHA-256 + ECDSA
  ▼
node.submit_transaction(tx)
  │  4. blockchain.add_transaction(tx)
  │        tx.validate()                     format, ID, signature
  │        replay check                      pool + chain
  │        balance / double-spend check      confirmed and available balance
  │  5. db.save_pending(tx)
  │  6. fraud_detector.analyze(tx)  ->  db.log_alert(...)
  ▼
SubmitResult(transaction, alerts)            shown to the user
        (any rejection in step 4 is logged to fraud_alerts and re-raised)
```

### 3.2 Mining a block

```
node.mine(miner_address)
  │  1. validate_chain()
  │  2. blockchain.mine_pending_transactions()
  │        re-verify every pending transaction
  │        create coinbase reward transaction
  │        build block (previous_hash = hash of the tip, Merkle root)
  │        Proof-of-Work loop: nonce += 1 until hash starts with N zeros
  │        append block, clear pool
  │  3. db.save_block(block), db.clear_pending()
  ▼
MiningResult(block, attempts, duration, rejected)
```

### 3.3 Detecting tampering

```
Attacker edits a transaction amount in SQLite
  ▼
Node loads the chain exactly as stored
  ▼
ChainValidator
  transaction payload hash != stored tx_id          -> TRANSACTION
  (attacker fixes tx_id)      signature invalid     -> TRANSACTION
                              Merkle root mismatch  -> MERKLE_ROOT
  (attacker fixes Merkle root) block hash mismatch  -> BLOCK_HASH
  (attacker fixes block hash)  no Proof-of-Work     -> PROOF_OF_WORK
                               next block's link    -> PREVIOUS_HASH
  ▼
ValidationReport(is_valid=False) -> CRITICAL alert, sending and mining disabled
```

## 4. Security design summary

| Threat | Defence | Where |
|---|---|---|
| Spending someone else's coins | ECDSA signature required; public key must hash to the sender address | `Transaction.validate` |
| Changing a signed transaction | Signature covers every field; transaction ID is a hash of the content | `Transaction.validate` |
| Spending more than owned | Balance computed from the chain | `Blockchain.add_transaction` |
| Double spending before mining | Available balance subtracts pending payments | `Blockchain.get_available_balance` |
| Replaying an old transaction | Transaction IDs are unique in the pool and the chain | `Blockchain.add_transaction`, `ChainValidator` |
| Creating coins from nothing | Only one fixed coinbase reward per mined block | `ChainValidator._check_coinbase` |
| Rewriting history | Hash links + Merkle root + Proof-of-Work + signatures | `ChainValidator` |
| Stolen database file | Private keys encrypted with a password that is never stored | `Wallet.to_encrypted_pem` |
| SQL injection | Parameterised queries only | `database/db.py` |
| Script injection in the UI | User text is HTML-escaped; wallet names are restricted | `ui/components.py`, `node._clean_wallet_name` |
| Suspicious but valid behaviour | Rule-based fraud detector and persistent fraud log | `security/fraud_detector.py` |

## 5. Testing strategy

| File | Level | Covers |
|---|---|---|
| `tests/test_wallet.py` | Unit | Keys, addresses, signatures, encrypted export |
| `tests/test_transactions.py` | Unit | Signing, forgery, field validation, pool |
| `tests/test_blockchain.py` | Unit | Hashing, PoW, balances, double spending |
| `tests/test_validation.py` | Unit | Every kind of chain corruption |
| `tests/test_fraud.py` | Unit | Each fraud rule, boundaries, scoring |
| `tests/test_database.py` | Unit | Round-trips, no plaintext keys, SQL injection |
| `tests/test_node.py` | Integration | The seven demonstrations, restart persistence |
| `tests/test_ui.py` | UI smoke | Every page renders; send and mine from the UI |
| `tests/test_viz.py` | Unit | Visualization payloads are real and contain no secrets; mining progress, sync |

Tests use a temporary database and difficulty 2, so the full suite runs in seconds.
