# SecureChain - Presentation Demo Guide

A script for a 10-12 minute live demonstration of the 3D command center.
Every step lists what to click, what you should see, and what to say.
All seven required demonstrations are covered.

## Before the presentation

1. Open a terminal in the project folder and start the app:

   ```powershell
   .\venv\Scripts\Activate.ps1
   streamlit run app.py
   ```

2. In the sidebar open **Demo tools**, tick **Yes, delete everything** and click
   **Reset all data** so you start from a clean ledger.
3. Click **Load demo data**. This creates:

   | Wallet | Balance | Password |
   |---|---|---|
   | Alice | 250 SCC | `demo-pass-123` |
   | Bob | 150 SCC | `demo-pass-123` |
   | Charlie | 0 SCC | `demo-pass-123` |

   The chain now has 5 blocks (genesis + 4 mined) and one confirmed payment
   (Alice -> Bob, 50 SCC, in block #4).
4. Keep a second terminal ready for `python demo.py` and `python -m pytest` (backup plan).
5. Use a normal desktop browser window (Chrome or Edge), maximised. The 3D views
   need WebGL; if it is unavailable they switch to 2D cards automatically.

> Tip: wait about a minute after loading the demo data before step 1, so the
> velocity rule in step 6 fires exactly when you want it to.

**How to use the 3D views:** drag to rotate, scroll to zoom, click an object
for details. The buttons under the chain (‹ › Tip, Reset, Auto-rotate) move
between blocks and reset the camera.

---

## Step 0 - Introduce the system (1 min)

**Page: Dashboard** ("Blockchain Command Center")

Say: *"SecureChain is a blockchain ledger. Wallets pay each other directly, every
payment is digitally signed, blocks are secured with Proof-of-Work, and a fraud
monitor watches every transaction. Everything on this screen is computed from
the real chain."*

1. Rotate the 3D chain a little, then **click block #4**.

Expected: a panel slides in with the block's hash, previous hash, Merkle root,
nonce, the five green check chips (Hash, Link, PoW, Merkle, Signatures) and its
two transactions (the mining reward and Alice -> Bob 50 SCC).

2. Point at the tiles: Chain integrity = VALID, 5 blocks, coins in circulation.

**Page: Wallets**

Show the wallet cards, then open the **Manage** tab.

Say: *"A wallet is an ECDSA key pair. The address is the SHA-256 hash of the
public key. The private key is encrypted with the user's password before it is
saved - it is never stored in plain text and never sent to the browser."*

---

## Step 1 - Successful signed transaction (Demo 1)

**Page: Send Transaction**

1. From wallet: **Alice**. Recipient: **Charlie**. Amount: **25**.
2. Password: `demo-pass-123`. Click **Sign and send**.

Expected:

* Green message "Transaction accepted and signed...", plus one warning
  *FIRST TIME RECIPIENT* (LOW).
* On the right, **Last submission · step by step** shows five steps: wallet
  unlocked, hashed and signed (with the real transaction ID and signature),
  verified by the node, fraud monitor result, waiting in the pending pool.

Say: *"The password decrypted Alice's private key in memory, the transaction was
hashed with SHA-256 and signed with ECDSA, and the node verified the signature
before accepting it. It is now pending."*

**Page: Transaction History** ("Transaction Network & History")

1. Show the 3D network: a cyan (pending) particle travels from Alice to Charlie.
2. Click the **Alice** node: her real balance and recent activity slide in.
3. Scroll to the **Timeline** and click the top card (Alice -> Charlie, PENDING)
   to expand it. Point at the signature and "Signature check: VALID".

---

## Step 2 - Blockchain mining (Demo 6)

**Page: Mining**

1. Miner wallet: **Bob**. Difficulty: **4**. Click **Mine block**.

Expected:

* Green message "Block #5 mined in ... after ... attempts".
* **Proof-of-Work verification · block #5** plays automatically: a reel of real
  nonces and hashes marked *reject*, ending on the winning nonce marked *VALID*
  with four leading zeros; then four green steps and "Block #5 secured".
* **The new block in the chain**: block #5 grows into the 3D chain.

Say: *"Mining means trying nonces until the SHA-256 hash of the block starts with
four zeros. What you see is not an animation of fake numbers: your browser is
recomputing the last real attempts and the winning hash, and checking that it
equals the hash the node stored. Bob received the 100 SCC reward."*

Click **Replay** if you want to show it again.

Optional: set the difficulty to **5** and mine again. It takes about 16 times
longer, and a live console shows the real number of hashes tried while the node
works. (This adds one more block, so later block numbers shift by one.)
Afterwards **move the difficulty slider back to 4**, otherwise every later
block in the demo takes several seconds to mine.

---

## Step 3 - Forged signature rejection (Demo 2)

**Page: Attack Lab > Forged signature**

1. Victim wallet: **Alice**. Amount: **50**.
2. Leave the first trick selected. Click **Launch forged transaction**.

Expected: "Attack blocked. The node rejected the transaction: Invalid digital
signature." and five steps on the right, the fourth in red:
**Node verification FAILS**.

Say: *"The attacker wrote 'Alice pays me 50' but could only sign it with their own
key. You can see the real forged signature here. Verification with Alice's
public key fails, so the node rejects it."*

3. Select the second trick (attacker's own public key) and launch again.

Expected: "Public key does not belong to the sender address."

Say: *"The attacker cannot swap in their own key either, because the address is
derived from the public key."*

---

## Step 4 - Insufficient balance rejection (Demo 3)

**Page: Attack Lab > Insufficient balance**

1. Receiver: any wallet. Amount: **25**. Click **Send from an empty wallet**.

Expected: "Attack blocked. Insufficient balance: wallet owns 0.00 SCC, tried to
send 25.00.", two bars comparing the real balance (0) with the requested
amount, and the steps: signature check passes, **Balance check FAILS**.

Say: *"This transaction is perfectly signed. It is rejected because balances are
calculated from the blockchain itself - coins cannot be invented."*

---

## Step 5 - Double-spending prevention (Demo 4)

**Page: Attack Lab > Double spending**

1. Dishonest spender: **Alice**. Password: `demo-pass-123`.
2. Click **Attempt double spend**.

Expected (messages at the top, and the same three results as steps on the right):

* Payment A: ACCEPTED into the pending pool.
* Payment B (the same coins again): BLOCKED - Double-spend attempt.
* Replay of payment A: BLOCKED - Duplicate transaction.

The bars show what Alice owned, what the two payments tried to spend in total,
and what was actually committed.

Say: *"Alice tried to promise the same coins to two people before a block was
mined. The node subtracts pending payments from the spendable balance, so the
second one fails. Re-submitting the first one fails too, because every
transaction ID can exist only once."*

---

## Step 6 - Suspicious transaction detection (Demo 5)

**Page: Fraud Alerts** ("Fraud Detection Command Center")

Show the **Command center** tab: the threat gauge, the Accepted / Flagged /
Rejected tiles, the activity timeline, and **Wallets by accumulated risk**.
Everything from steps 3-5 is already there: two CRITICAL forged signatures, the
insufficient balance attempt and two double-spend rejections.

**Page: Mining** - mine a block with **Alice** as miner (confirms payment A and
gives Alice fresh coins).

**Page: Send Transaction**

1. From **Bob** to **Charlie**, amount **220**, password `demo-pass-123`.

Expected warnings: LARGE TRANSACTION (HIGH) and FIRST TIME RECIPIENT (LOW),
with a risk score of 60/100. The step list on the right shows the fraud monitor
step in amber. (If you send 90 % or more of Bob's available balance instead,
BALANCE DRAIN (MEDIUM) fires as well.)

2. Now send **1** SCC from **Alice** to **Bob** four times in a row.

Expected: by the fourth payment HIGH VELOCITY fires (it can fire one payment
earlier if Alice's double-spend payment from step 5 was less than a minute ago).

Say: *"These transactions are valid, so they are accepted - but the fraud
detector flags unusual behaviour: large amounts, draining a wallet, new
recipients and rapid-fire payments. Everything is kept in the fraud log."*

**Page: Transaction History** - the network now shows amber (flagged) particles,
and red ones that stop half-way: rejected transactions never reach the receiver.
Use the Confirmed / Pending / Flagged / Rejected buttons in the top-right
corner of the network to show or hide each kind.

**Page: Fraud Alerts > Detection rules** - show the rule table.

---

## Step 7 - Historical tampering detection (Demo 7)

**Page: Mining** - mine one block so nothing is pending.

**Page: Chain Validation** - click **Run full validation**. Show "Blockchain is
VALID" and the **Verification scan**: one tile per block, five green check
lights each.

**Page: Attack Lab > Tamper with history**

1. Select the transaction **Block #4 · Alice -> Bob · 50.00 SCC**.
2. New amount: **5000**. Click **Tamper with the database**.

Expected:

* "Database modified..." and "Tampering DETECTED by chain validation".
* The sidebar turns red: **Chain compromised**.
* **Before and after** table: amount 50.00 -> 5,000.00, signature check
  VALID -> INVALID.
* Animated comparison **1 · Transaction fingerprint**: the hash recomputed in
  the browser no longer equals the stored transaction ID - red characters and
  a MISMATCH badge. (Comparisons 2 and 3 show MATCH for this simple attack.)
* The 3D chain below shows block #4 and the blocks that depend on it in red.

Say: *"I just edited an old transaction directly in the SQLite file, the way an
attacker with database access would. Your browser recomputed the SHA-256
fingerprint of the stored data, and it no longer matches the ID recorded in
the block. The signature is invalid too."*

**Page: Chain Validation** - show the INVALID verdict, the red tiles in the
scan starting at block #4, and the problems table.

**Page: Blockchain Explorer** - move the **Block** slider to 4: the camera flies
to the red block and its panel lists the failed checks.

**Page: Send Transaction** - try to send anything: the node refuses because the
ledger is corrupted.

**Back to Attack Lab > Tamper with history**

1. Click **Restore original data**.
2. Select the same transaction, tick **Sophisticated attacker**, set the amount
   to **5000** and click **Tamper with the database** again.

Expected: now comparison 1 shows MATCH (the attacker fixed the ID), but
**2 · Block header hash** and **3 · Chain link to block #5** show MISMATCH, and
the signature check is still INVALID.

Say: *"A smarter attacker also recomputes the transaction ID, the Merkle root
and the block hash. It is still detected: the header no longer matches the
hash that was mined, the next block points to the old hash, and the signature
cannot be forged without Alice's private key."*

3. Click **Restore original data** to finish with a valid chain.

---

## Closing (30 s)

Open a terminal and run:

```powershell
python -m pytest
```

Say: *"Every feature you saw is also covered by automated tests - 198 of them -
including the seven demonstrations and a test proving that no private key or
password is ever sent to the browser."*

## Backup plan

| Problem | What to do |
|---|---|
| A 3D view is blank or slow | The same data is on the page below it (tables, timeline). You can also continue with `python demo.py` |
| The browser or Streamlit misbehaves | Run `python demo.py` in the terminal: the same seven demonstrations, with a PASS line for each check |
| Sidebar says "Chain compromised" | Attack Lab > Tamper with history > **Restore original data** |
| You changed code and nothing happened | Stop and restart `streamlit run app.py` |
| You want a specific page quickly | Open `http://localhost:8501/?page=mining` (or `dashboard`, `wallets`, `send`, `history`, `fraud`, `explorer`, `validation`, `attack`) |

## Likely questions

| Question | Short answer |
|---|---|
| Is the mining animation real? | Yes. The node does the mining in Python. The browser then recomputes SHA-256 for the last real attempts and the winning nonce and compares it with the stored hash. |
| Why can't the attacker just fix all the hashes? | They would have to redo the Proof-of-Work for that block and every block after it, and they still cannot produce the sender's signature. |
| Where is the private key stored? | In SQLite, encrypted with the wallet password (PBKDF2 + AES-256). The password is never stored, and neither is ever sent to the browser. |
| Is it really peer-to-peer? | Payments go directly from wallet to wallet with no central authority, but the project runs a single node. Networking between nodes is listed as future work. |
| Why are flagged transactions not blocked? | Fraud rules produce false positives, so they alert rather than block. Invalid transactions (bad signature, no funds) are always blocked. |
| How are balances stored? | They are not. Balances are recalculated from the chain, so there is nothing separate to tamper with. |
| What does the nonce in a transaction do? | It makes each transaction unique, so an identical payment can be made twice on purpose, while a copied transaction is rejected as a replay. |
| How is the 3D built? | Three.js inside an isolated Streamlit component. Python sends public chain data in; nothing is sent back, so the visuals cannot change the application state. |
