/*
 * View "pow": replay and re-verify a real Proof-of-Work result.
 *
 * data = {
 *   index, prefix (block header text without the nonce), nonce, hash, difficulty,
 *   attempts, duration, miner, reward, tx_count, previous_hash,
 *   chain: [{index, hash}]  (a few blocks before the new one),
 *   autoplay (bool), token (changes when a new block was mined)
 * }
 *
 * Nothing here is simulated. The node already found the nonce; this view
 * recomputes SHA-256(prefix + nonce) IN THE BROWSER for the last real
 * attempts and for the winning nonce, and compares the result with the
 * hash stored by the node.
 */
(function () {
  "use strict";
  const SC = window.SC;
  const REPLAY = 90;       // how many of the final real attempts are replayed
  const ROWS = 7;

  SC.views.pow = function (root, data) {
    const wrap = SC.el("div", "viz viz-pow");
    root.appendChild(wrap);
    let payload = data;
    let timers = [];
    let playedToken = null;
    let runId = 0;

    function later(fn, ms) { const id = setTimeout(fn, ms); timers.push(id); return id; }
    function clearTimers() { timers.forEach(clearTimeout); timers = []; }

    function hashRow(nonce, hash, difficulty, winner) {
      const zeros = (hash.match(/^0*/) || [""])[0].length;
      const good = Math.min(zeros, difficulty);
      let cells = "";
      for (let i = 0; i < difficulty; i++) {
        cells += '<span class="' + (i < good ? "hit" : i === good ? "miss" : "rest") + '">' + SC.esc(hash[i]) + "</span>";
      }
      return (
        '<div class="reel-row' + (winner ? " winner" : "") + '">' +
        '<span class="reel-nonce">' + Number(nonce).toLocaleString() + "</span>" +
        '<span class="reel-hash mono">' + cells + '<span class="tail">' + SC.esc(hash.slice(difficulty, 44)) + "…</span></span>" +
        '<span class="reel-verdict">' + (winner ? "VALID" : "reject") + "</span></div>"
      );
    }

    function build() {
      const d = payload;
      const target = "0".repeat(d.difficulty);
      const chainTiles = (d.chain || []).map(function (b) {
        return '<div class="pc-block"><b>#' + SC.esc(b.index) + '</b><span class="mono">' + SC.esc(SC.short(b.hash, 6, 4)) + '</span></div><div class="pc-link"></div>';
      }).join("");
      wrap.innerHTML =
        '<div class="pow-left">' +
        '<div class="hud-eyebrow"><span class="live-dot"></span>Proof-of-Work · block #' + SC.esc(d.index) + "</div>" +
        '<div class="pow-target">Target: hash must start with <span class="mono hit">' + target + "</span></div>" +
        '<div class="pow-counter"><span class="pow-counter-label">Nonce</span><span class="pow-nonce mono">0</span></div>' +
        '<div class="pow-bar"><div class="pow-bar-fill"></div></div>' +
        '<div class="pow-bar-text"></div>' +
        '<div class="reel"></div>' +
        '<div class="pow-note"></div>' +
        "</div>" +
        '<div class="pow-right">' +
        '<div class="steps">' +
        '<div class="step" data-step="0"><span class="step-icon"></span><div><b>Hash meets the target</b><span class="step-text">Waiting for a hash with ' + d.difficulty + " leading zeros</span></div></div>" +
        '<div class="step" data-step="1"><span class="step-icon"></span><div><b>Independent verification</b><span class="step-text">Browser recomputes SHA-256(header + nonce)</span></div></div>' +
        '<div class="step" data-step="2"><span class="step-icon"></span><div><b>Linked to the previous block</b><span class="step-text mono">prev ' + SC.esc(SC.short(d.previous_hash, 10, 6)) + "</span></div></div>" +
        '<div class="step" data-step="3"><span class="step-icon"></span><div><b>Block appended to the chain</b><span class="step-text">' +
        SC.esc(d.tx_count) + " transaction" + (d.tx_count === 1 ? "" : "s") + " · reward " + SC.esc(d.reward) + " to " + SC.esc(d.miner) + "</span></div></div>" +
        "</div>" +
        '<div class="pow-chain">' + chainTiles +
        '<div class="pc-block new"><b>#' + SC.esc(d.index) + '</b><span class="mono">' + SC.esc(SC.short(d.hash, 6, 4)) + "</span></div></div>" +
        '<div class="pow-footer"><div class="pow-success"><span class="ring"></span><span class="tick">✓</span><span class="pow-success-text">Block #' + SC.esc(d.index) + " secured</span></div>" +
        '<button class="viz-btn replay">Replay</button></div>' +
        "</div>";
      wrap.querySelector(".replay").addEventListener("click", function () { play(); });
    }

    function setStep(index, state, text) {
      const node = wrap.querySelector('.step[data-step="' + index + '"]');
      if (!node) return;
      node.classList.remove("ok", "bad", "active");
      if (state) node.classList.add(state);
      if (text) node.querySelector(".step-text").textContent = text;
    }

    function attemptsText(shown) {
      const d = payload;
      return Number(shown).toLocaleString() + " of " + Number(d.attempts).toLocaleString() + " attempts · mined by the node in " +
        Number(d.duration).toFixed(2) + " s";
    }

    // Final state: everything verified (also used when the replay is not auto-played).
    function finish(animated) {
      const d = payload;
      const computed = SC.sha256(d.prefix + d.nonce);
      const meets = computed.startsWith("0".repeat(d.difficulty));
      const matches = computed === d.hash;
      wrap.querySelector(".pow-nonce").textContent = Number(d.nonce).toLocaleString();
      wrap.querySelector(".pow-bar-fill").style.width = "100%";
      wrap.querySelector(".pow-bar-text").textContent = attemptsText(d.attempts);
      const first = Math.max(0, d.nonce - ROWS + 1);
      let rows = "";
      for (let n = first; n <= d.nonce; n++) rows += hashRow(n, n === d.nonce ? computed : SC.sha256(d.prefix + n), d.difficulty, n === d.nonce);
      wrap.querySelector(".reel").innerHTML = rows;
      const delay = animated ? 420 : 0;
      const stepsDone = function () {
        setStep(0, meets ? "ok" : "bad", meets ? "Nonce " + Number(d.nonce).toLocaleString() + " gives " + d.difficulty + " leading zeros" : "Hash does NOT meet the target");
        later(function () {
          setStep(1, matches ? "ok" : "bad", matches ? "Browser hash equals the hash stored by the node" : "MISMATCH between browser hash and stored hash");
          later(function () {
            setStep(2, "ok");
            later(function () {
              setStep(3, "ok");
              wrap.classList.add("done");
              if (meets && matches) wrap.classList.add("success");
            }, delay);
          }, delay);
        }, delay);
      };
      stepsDone();
    }

    function play() {
      clearTimers();
      const myRun = ++runId;
      const d = payload;
      wrap.classList.remove("done", "success");
      for (let i = 0; i < 4; i++) setStep(i, null);
      setStep(0, "active", "Searching for a hash with " + d.difficulty + " leading zeros");
      const reel = wrap.querySelector(".reel");
      const nonceEl = wrap.querySelector(".pow-nonce");
      const fill = wrap.querySelector(".pow-bar-fill");
      const barText = wrap.querySelector(".pow-bar-text");
      reel.innerHTML = "";
      const count = Math.min(d.nonce + 1, REPLAY);
      const first = d.nonce - count + 1;
      wrap.querySelector(".pow-note").textContent =
        count < d.attempts
          ? "Replaying the final " + count + " of " + Number(d.attempts).toLocaleString() + " real attempts. Every hash shown is recomputed in your browser."
          : "Replaying all " + count + " real attempts. Every hash shown is recomputed in your browser.";
      if (SC.reducedMotion) { finish(false); return; }

      let n = first;
      const rows = [];
      function tick() {
        if (myRun !== runId) return;
        const hash = SC.sha256(d.prefix + n);
        const winner = n === d.nonce;
        rows.push(hashRow(n, hash, d.difficulty, winner));
        if (rows.length > ROWS) rows.shift();
        reel.innerHTML = rows.join("");
        nonceEl.textContent = Number(n).toLocaleString();
        const done = (n + 1) / (d.nonce + 1);
        fill.style.width = (done * 100).toFixed(1) + "%";
        barText.textContent = attemptsText(n + 1);
        if (winner) { finish(true); return; }
        n += 1;
        const remaining = d.nonce - n;
        later(tick, remaining < 6 ? 150 : remaining < 16 ? 60 : 22);   // slow down for the final attempts
      }
      tick();
    }

    function apply(next, first) {
      const tokenChanged = !first && next.token !== payload.token;
      payload = next;
      if (first || tokenChanged) {
        clearTimers();
        runId++;
        build();
        if (payload.autoplay && payload.token !== playedToken) { playedToken = payload.token; play(); }
        else { wrap.querySelector(".pow-note").textContent = "Verified in your browser. Press Replay to watch the final real attempts again."; finish(false); }
      }
    }

    apply(data, true);
    return {
      update: function (next) { apply(next, false); },
      destroy: function () { clearTimers(); runId++; },
    };
  };
})();
