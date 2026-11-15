"""
Central configuration for SecureChain.

Every tunable number in the project lives here so that behaviour can be
changed in one place (and explained easily during a presentation).
"""

import os
from pathlib import Path

# --------------------------------------------------------------------------
# Storage
# --------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
# The database location can be overridden with the SECURECHAIN_DB environment
# variable (used by the tests so they never touch the real database).
DB_PATH = Path(os.environ.get("SECURECHAIN_DB", DATA_DIR / "securechain.db"))

# --------------------------------------------------------------------------
# Currency
# --------------------------------------------------------------------------
COIN_NAME = "SecureCoin"
COIN_SYMBOL = "SCC"
AMOUNT_DECIMALS = 8                    # smallest unit is 0.00000001 SCC
MAX_TRANSACTION_AMOUNT = 1_000_000_000

# --------------------------------------------------------------------------
# Blockchain / Proof-of-Work
# --------------------------------------------------------------------------
MINING_DIFFICULTY = 4                  # block hash must start with this many zeros
MIN_DIFFICULTY = 1                     # blocks below this difficulty are rejected
MAX_DIFFICULTY = 5                     # upper limit offered in the UI (keeps mining fast)
MINING_REWARD = 100.0                  # new coins paid to the miner of each block
COINBASE_SENDER = "COINBASE"           # pseudo-sender of mining-reward transactions
GENESIS_PREVIOUS_HASH = "0" * 64
GENESIS_TIMESTAMP = 1767225600.0       # 2026-01-01 00:00:00 UTC (fixed => same genesis everywhere)
MAX_FUTURE_DRIFT_SECONDS = 120         # reject transactions dated too far in the future

# --------------------------------------------------------------------------
# Wallets
# --------------------------------------------------------------------------
ADDRESS_PREFIX = "SC"
ADDRESS_HASH_LENGTH = 40               # hex characters taken from SHA-256(public key)
MIN_PASSWORD_LENGTH = 8
MAX_WALLET_NAME_LENGTH = 30

# --------------------------------------------------------------------------
# Fraud detection thresholds
# --------------------------------------------------------------------------
LARGE_TX_THRESHOLD = 200.0             # amounts >= this are flagged as "large"
BALANCE_DRAIN_RATIO = 0.90             # spending >= 90% of the balance in one go
VELOCITY_WINDOW_SECONDS = 60           # look-back window for rapid transactions
VELOCITY_MAX_TX = 3                    # more than this many tx in the window is flagged
