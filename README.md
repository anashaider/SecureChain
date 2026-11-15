# SecureChain

**A Peer-to-Peer Transaction Ledger with Digital Signatures and Fraud Detection**

SecureChain is a small but complete blockchain written in Python for a university
cybersecurity project. Wallets hold ECDSA keys, every payment is digitally signed,
blocks are mined with Proof-of-Work, a rule-based monitor flags suspicious
transactions, and the whole ledger can be re-verified at any time. A Streamlit
dashboard makes every part visible and includes an **Attack Lab** where real
attacks are launched against the ledger and stopped.

| Area | Technology |
|---|---|
| Language | Python 3.10+ (developed on 3.13) |
| Hashing | SHA-256 (`hashlib`) |
| Signatures | ECDSA on secp256k1 (`cryptography`) |
| Key storage | Password-encrypted PKCS#8 (PBKDF2 + AES-256) |
| Database | SQLite (`sqlite3`) |
| Interface | Streamlit |
| Tests | Pytest |

---

## 1. Installation

Open a terminal (PowerShell on Windows) in the project folder.

```powershell
# 1. Create a virtual environment (skip if the venv folder already exists)
python -m venv venv

# 2. Activate it
.\venv\Scripts\Activate.ps1          # Windows PowerShell
# source venv/bin/activate           # macOS / Linux

# 3. Install the dependencies
pip install -r requirements.txt
```

> If PowerShell refuses to run the activation script, either run
> `Set-ExecutionPolicy -Scope Process RemoteSigned` first, or skip activation and
> call the venv's Python directly, e.g. `.\venv\Scripts\python.exe -m streamlit run app.py`.

## 2. Running the project

### The dashboard

```powershell
streamlit run app.py
```

The dashboard opens at <http://localhost:8501>. The first time Streamlit starts it
may ask for an e-mail address in the terminal - just press **Enter** to skip.

To get started quickly, open **Demo tools** in the sidebar and click
**Load demo data**. This creates three wallets (Alice, Bob, Charlie) with coins.
The password for all three is `demo-pass-123`.

### The command-line demonstration

```powershell
python demo.py
```

Runs all seven required demonstrations in a few seconds and prints a
PASS/FAIL line for each check. It uses a temporary database and does not
affect the dashboard's data.

### The automated tests

```powershell
python -m pytest            # run everything
python -m pytest -v         # one line per test
python -m pytest tests/test_validation.py    # one module
```

## 3. What the dashboard offers

| Page | What you can do |
|---|---|
| **Dashboard** | Chain status, block / transaction / wallet counts, recent blocks and alerts |
| **Wallets** | Create wallets, view balances, download the encrypted keystore, rename, delete |
| **Send Transaction** | Sign and submit a payment; see fraud warnings immediately |
| **Transaction History** | Filter confirmed and pending transactions; inspect signatures |
| **Mining** | See the pending pool, choose the difficulty, mine a block |
| **Fraud Alerts** | Alert feed, full fraud log, explanation of every rule |
| **Blockchain Explorer** | Browse blocks, follow hash links, search by hash or transaction ID |
| **Chain Validation** | Re-verify every hash, link, proof and signature |
| **Attack Lab** | Forged signature, overspending, double spend, tampering with history |

### Interactive 3D command center

The dashboard is a dark, glass-style "security command center" with four
interactive visual modules, all driven by real ledger data:

| Module | Where | What it does |
|---|---|---|
| **3D blockchain** | Dashboard, Explorer, Mining, Attack Lab | Floating blocks joined by glowing links. Drag to rotate, scroll to zoom, click a block for its hash, nonce, transactions and validation result. Green = verified, red = invalid. Newly mined blocks animate in. |
| **3D transaction network** | Transaction History | Wallets are nodes, payments are particles (green confirmed, cyan pending, amber flagged, red rejected). Click a wallet for its real balance and history. |
| **Proof-of-Work replay** | Mining | Recomputes the real final mining attempts and the winning hash with SHA-256 **in the browser** and compares the result with the hash stored by the node. |
| **Hash mismatch comparator** | Attack Lab > Tamper with history | Before/after table plus animated character-by-character SHA-256 comparison of a tampered block. |

Notes:

* Three.js (r147, MIT licence) is shipped in `ui/frontend/`, so everything works **offline**.
* If WebGL is unavailable, the 3D views fall back automatically to 2D cards with the same data.
* The visual component is one-way: it never writes to Streamlit's session state, and only
  public data (hashes, addresses, amounts) is sent to the browser - never keys or passwords.
* Pages can be opened directly, e.g. `http://localhost:8501/?page=mining`
  (`dashboard`, `wallets`, `send`, `history`, `mining`, `fraud`, `explorer`, `validation`, `attack`).
* After editing Python files, **restart** `streamlit run app.py` to be sure the changes are loaded.

## 4. Required demonstrations

| # | Demonstration | In the dashboard | Automated test |
|---|---|---|---|
| 1 | Successful signed transaction | Send Transaction, then Mining | `test_demo_1_successful_signed_transaction` |
| 2 | Forged signature rejection | Attack Lab > Forged signature | `test_demo_2_forged_signature_is_rejected` |
| 3 | Insufficient balance rejection | Attack Lab > Insufficient balance | `test_demo_3_insufficient_balance_is_rejected` |
| 4 | Double-spending prevention | Attack Lab > Double spending | `test_demo_4_double_spending_is_prevented` |
| 5 | Suspicious transaction detection | Send 200+ SCC, then Fraud Alerts | `test_demo_5_suspicious_transactions_are_detected` |
| 6 | Blockchain mining | Mining | `test_demo_6_blockchain_mining` |
| 7 | Historical tampering detection | Attack Lab > Tamper with history | `test_demo_7_historical_tampering_is_detected` |

All seven tests are in `tests/test_node.py`. A step-by-step presentation script
is in [docs/DEMO_GUIDE.md](docs/DEMO_GUIDE.md).

## 5. Project structure

```
SecureChain/
├── app.py                  Streamlit entry point (navigation only)
├── node.py                 SecureChainNode: connects all modules, used by the UI
├── config.py               Every tunable constant (difficulty, reward, thresholds)
├── demo.py                 Command-line run of the seven demonstrations
├── requirements.txt
│
├── wallet/                 ECDSA keys, addresses, signing, encrypted export
│   └── wallet.py
├── transactions/           Transaction model, pending pool, rejection errors
│   ├── transaction.py
│   ├── pool.py
│   └── exceptions.py
├── security/               Fraud detection and full-chain validation
│   ├── fraud_detector.py
│   └── validator.py
├── blockchain/             Block (hash, Merkle root, PoW) and the chain
│   ├── block.py
│   └── blockchain.py
├── database/               SQLite persistence
│   └── db.py
├── ui/                     Dashboard
│   ├── theme.py            Design system (glass cards, animations, widget styling)
│   ├── components.py       Shared pieces (KPI tiles, flows, gauge, timeline, charts)
│   ├── viz.py              Builds the public-only JSON sent to the visual component
│   ├── frontend/           Isolated visual component: Three.js + plain JavaScript
│   │   ├── core.js         Protocol, SHA-256, camera orbit, WebGL helpers
│   │   ├── chain.js        3D blockchain
│   │   ├── network.js      3D transaction network
│   │   ├── pow.js          Proof-of-Work replay
│   │   └── hashdiff.js     Hash mismatch comparator
│   └── views/              One file per page
├── tests/                  Pytest suite (one file per module + integration + UI)
├── docs/
│   ├── ARCHITECTURE.md     Software architecture
│   ├── PROJECT_REPORT.md   Project report
│   └── DEMO_GUIDE.md       Presentation script
└── data/securechain.db     Created automatically on first run
```

## 6. Configuration

All settings are in `config.py`. The most useful ones:

| Setting | Default | Meaning |
|---|---|---|
| `MINING_DIFFICULTY` | 4 | Leading zeros required in a block hash |
| `MINING_REWARD` | 100 | Coins created for the miner of each block |
| `LARGE_TX_THRESHOLD` | 200 | Amount that triggers the large-transaction alert |
| `VELOCITY_MAX_TX` / `VELOCITY_WINDOW_SECONDS` | 3 / 60 | More than 3 payments in 60 s is flagged |
| `BALANCE_DRAIN_RATIO` | 0.90 | Spending 90 % or more of a balance is flagged |
| `MIN_PASSWORD_LENGTH` | 8 | Minimum wallet password length |

The database location can be changed with the `SECURECHAIN_DB` environment variable.

## 7. Troubleshooting

| Problem | Solution |
|---|---|
| `streamlit` is not recognised | Activate the venv, or run `python -m streamlit run app.py` |
| Port 8501 is busy | `streamlit run app.py --server.port 8502` |
| Forgot a wallet password | It cannot be recovered (by design). Create a new wallet |
| "Chain compromised" in the sidebar | A tampering demo is active. Attack Lab > Tamper with history > **Restore original data** |
| Want a clean start | Sidebar > Demo tools > tick the box > **Reset all data** (or delete `data/securechain.db`) |

## 8. Scope and limitations

SecureChain is an educational system. It runs as a **single node**: transactions
are peer-to-peer in the sense that wallets pay each other directly with no bank
in between, but there is no network of nodes and no consensus between computers.
Balances use an account model (not Bitcoin's UTXO model), there are no
transaction fees, and the difficulty is fixed rather than self-adjusting.
See the project report for a full discussion.


## Screenshots

Add screenshots captured from the running application to the [`screenshots/`](screenshots/)
folder. Do not use mockups in place of actual application screenshots.

## License

SecureChain is distributed under the MIT License. See [LICENSE](LICENSE).
Before publishing, replace `[COPYRIGHT HOLDER]` in the LICENSE file with the
copyright holder's preferred name or organization.
