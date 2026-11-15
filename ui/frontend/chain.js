/*
 * View "chain": the blockchain as floating 3D blocks joined by glowing links.
 *
 * data = {
 *   blocks: [{ index, hash, previous_hash, merkle_root, nonce, difficulty, time,
 *              tx_count, ok, genesis, checks: {hash, link, pow, merkle, transactions},
 *              issues: [text], txs: [{id, type, from, to, amount, sig}] }],
 *   total, valid, focus (block index or null), animate (block index or null)
 * }
 * Green = verified block, red = block that fails validation.
 */
(function () {
  "use strict";
  const SC = window.SC;
  const SPACING = 2.7;

  SC.views.chain = function (root, data) {
    const wrap = SC.el("div", "viz viz-chain");
    root.appendChild(wrap);
    const canvasBox = SC.el("div", "viz-canvas");
    wrap.appendChild(canvasBox);

    // ----- overlays -----
    const hud = SC.el("div", "viz-hud");
    wrap.appendChild(hud);
    const hint = SC.el("div", "viz-hint", "Drag to rotate  ·  Scroll to zoom  ·  Click a block");
    wrap.appendChild(hint);
    const tooltip = SC.el("div", "viz-tooltip");
    wrap.appendChild(tooltip);
    const panel = SC.el("aside", "viz-panel");
    wrap.appendChild(panel);
    const controls = SC.el("div", "viz-controls");
    wrap.appendChild(controls);

    let blocks = [];
    let selected = null;        // block index
    let stage = null;
    let group = null;           // THREE.Group holding blocks + links
    let items = [];             // per block: { block, node, cube, edges, core, glow, base, born }
    let links = [];             // per link: { mesh, from, to, bad, pulses[] }
    let ring = null;
    let known = {};             // hashes already shown (to detect newly mined blocks)
    const up = typeof THREE !== "undefined" ? new THREE.Vector3(0, 1, 0) : null;

    function button(label, title, handler) {
      const b = SC.el("button", "viz-btn", label);
      b.title = title;
      b.addEventListener("click", handler);
      controls.appendChild(b);
      return b;
    }

    function byIndex(index) {
      for (let i = 0; i < items.length; i++) if (items[i].block.index === index) return items[i];
      return null;
    }

    function basePosition(k, n) {
      return new THREE.Vector3((k - (n - 1) / 2) * SPACING, Math.sin(k * 0.75) * 0.6, Math.cos(k * 0.55) * 1.0);
    }

    function blockColor(block) {
      if (!block.ok) return SC.colors.red;
      return block.genesis ? SC.colors.purple : SC.colors.green;
    }

    // ------------------------------------------------------------------
    // Detail panel (slides in from the right)
    // ------------------------------------------------------------------
    function chip(label, ok, neutral) {
      const cls = neutral ? "chip" : ok ? "chip ok" : "chip bad";
      return '<span class="' + cls + '">' + SC.esc(label) + (neutral ? "" : ok ? " ✓" : " ✗") + "</span>";
    }

    function showPanel(block) {
      const status = !block.ok ? '<span class="badge bad">INVALID</span>'
        : block.genesis ? '<span class="badge purple">GENESIS</span>'
        : '<span class="badge ok">VERIFIED</span>';
      const c = block.checks || {};
      let html =
        '<button class="viz-close" title="Close">×</button>' +
        '<div class="panel-eyebrow">Block</div>' +
        '<div class="panel-title">#' + SC.esc(block.index) + " " + status + "</div>" +
        '<div class="chips">' +
        chip("Hash", c.hash) + chip("Link", c.link) + (block.genesis ? chip("PoW n/a", true, true) : chip("PoW", c.pow)) +
        chip("Merkle", c.merkle) + chip("Signatures", c.transactions) + "</div>";
      if (block.issues && block.issues.length) {
        html += '<div class="issues">' + block.issues.map(function (t) { return "<div>" + SC.esc(t) + "</div>"; }).join("") + "</div>";
      }
      html +=
        '<dl class="kv">' +
        "<dt>Hash</dt><dd class='mono'>" + SC.esc(block.hash) + "</dd>" +
        "<dt>Previous hash</dt><dd class='mono'>" + SC.esc(block.previous_hash) + "</dd>" +
        "<dt>Merkle root</dt><dd class='mono'>" + SC.esc(block.merkle_root) + "</dd>" +
        "<dt>Nonce</dt><dd>" + SC.esc(Number(block.nonce).toLocaleString()) + "</dd>" +
        "<dt>Difficulty</dt><dd>" + (block.genesis ? "Not mined (genesis)" : SC.esc(block.difficulty) + " leading zeros") + "</dd>" +
        "<dt>Timestamp</dt><dd>" + SC.esc(block.time) + "</dd>" +
        "</dl>" +
        '<div class="panel-eyebrow">Transactions (' + SC.esc(block.tx_count) + ")</div>";
      if (!block.txs || !block.txs.length) {
        html += '<div class="muted">The genesis block contains no transactions.</div>';
      } else {
        html += block.txs.map(function (tx) {
          const sigClass = tx.sig === "valid" ? "ok" : tx.sig === "invalid" ? "bad" : "";
          const sigText = tx.sig === "valid" ? "signature valid" : tx.sig === "invalid" ? "SIGNATURE INVALID" : "protocol reward";
          return (
            '<div class="tx ' + (tx.sig === "invalid" ? "bad" : "") + '">' +
            '<div class="tx-top"><span class="tx-type">' + (tx.type === "reward" ? "Mining reward" : "Payment") + "</span>" +
            '<span class="tx-amount">' + SC.esc(tx.amount) + "</span></div>" +
            '<div class="tx-route">' + SC.esc(tx.from) + " → " + SC.esc(tx.to) + "</div>" +
            '<div class="tx-meta"><span class="mono">' + SC.esc(SC.short(tx.id, 10, 6)) + "</span>" +
            '<span class="' + sigClass + '">' + sigText + "</span></div></div>"
          );
        }).join("");
        if (block.tx_count > block.txs.length) {
          html += '<div class="muted">+ ' + (block.tx_count - block.txs.length) + " more (see the table below)</div>";
        }
      }
      panel.innerHTML = html;
      panel.classList.add("open");
      panel.querySelector(".viz-close").addEventListener("click", function () { select(null); });
    }

    function select(index, moveCamera) {
      selected = index;
      const item = index === null ? null : byIndex(index);
      if (!item) {
        selected = null;
        panel.classList.remove("open");
        if (ring) ring.visible = false;
        if (fallback) fallback.mark(null);
        return;
      }
      showPanel(item.block);
      if (fallback) fallback.mark(index);
      if (stage) {
        if (moveCamera !== false) stage.goalTarget.copy(item.base);
        stage.lastInteraction = stage.time;
        if (ring) { ring.visible = true; ring.material.color.setHex(blockColor(item.block)); }
      }
    }

    function step(delta) {
      if (!items.length) return;
      let position = 0;
      if (selected !== null) {
        for (let i = 0; i < items.length; i++) if (items[i].block.index === selected) position = i;
        position = Math.min(items.length - 1, Math.max(0, position + delta));
      } else {
        position = items.length - 1;
      }
      select(items[position].block.index);
    }

    function renderHud(payload) {
      const bad = blocks.filter(function (b) { return !b.ok; }).length;
      hud.innerHTML =
        '<div class="hud-eyebrow"><span class="live-dot"></span>Live chain</div>' +
        '<div class="hud-title">' + SC.esc(payload.total) + " block" + (payload.total === 1 ? "" : "s") + "</div>" +
        (bad
          ? '<span class="badge bad">' + bad + " INVALID</span>"
          : '<span class="badge ok">ALL VERIFIED</span>') +
        (payload.total > blocks.length ? '<div class="hud-note">Showing the latest ' + blocks.length + "</div>" : "");
    }

    // ------------------------------------------------------------------
    // 2D fallback (no WebGL): the same data as a scrolling row of cards
    // ------------------------------------------------------------------
    let fallback = null;
    function buildFallback() {
      canvasBox.innerHTML = "";
      const row = SC.el("div", "fallback-chain");
      canvasBox.appendChild(row);
      const cards = {};
      blocks.forEach(function (block, k) {
        if (k > 0) row.appendChild(SC.el("div", "fallback-link" + (block.checks && !block.checks.link ? " bad" : "")));
        const card = SC.el("button", "fallback-block" + (block.ok ? "" : " bad") + (block.genesis ? " genesis" : ""));
        card.style.animationDelay = (k % 6) * 0.35 + "s";
        card.innerHTML =
          '<div class="fb-title">' + (block.genesis ? "Genesis" : "Block #" + SC.esc(block.index)) + "</div>" +
          '<div class="fb-meta">' + SC.esc(block.tx_count) + " tx</div>" +
          '<div class="fb-hash mono">' + SC.esc(SC.short(block.hash, 8, 4)) + "</div>";
        card.addEventListener("click", function () { select(block.index); });
        row.appendChild(card);
        cards[block.index] = card;
      });
      items = blocks.map(function (block) { return { block: block }; });
      hint.textContent = "3D view unavailable (no WebGL) - showing the 2D chain. Click a block.";
      row.scrollLeft = row.scrollWidth;
      fallback = {
        mark: function (index) {
          Object.keys(cards).forEach(function (key) { cards[key].classList.toggle("selected", Number(key) === index); });
        },
      };
    }

    // ------------------------------------------------------------------
    // 3D scene
    // ------------------------------------------------------------------
    function makeBlock(block, k, n) {
      const color = blockColor(block);
      const node = new THREE.Group();
      const base = basePosition(k, n);
      node.position.copy(base);

      const geometry = new THREE.BoxGeometry(1.25, 1.25, 1.25);
      const cube = new THREE.Mesh(
        geometry,
        new THREE.MeshStandardMaterial({
          color: 0x0e2240, metalness: 0.55, roughness: 0.2, emissive: color, emissiveIntensity: 0.3,
          transparent: true, opacity: 0.88,
        })
      );
      cube.userData = { index: block.index };
      node.add(cube);

      const edges = new THREE.LineSegments(
        new THREE.EdgesGeometry(geometry),
        new THREE.LineBasicMaterial({ color: color, transparent: true, opacity: 0.95 })
      );
      edges.scale.setScalar(1.012);
      node.add(edges);

      // Inner core: its size reflects how many transactions the block holds.
      const coreSize = 0.2 + Math.min(block.tx_count, 8) * 0.04;
      const core = new THREE.Mesh(
        new THREE.IcosahedronGeometry(coreSize, 0),
        new THREE.MeshBasicMaterial({ color: color, wireframe: true, transparent: true, opacity: 0.9 })
      );
      node.add(core);

      const glow = SC.glowSprite(color, 3.6, block.ok ? 0.42 : 0.7);
      node.add(glow);

      const label = SC.textSprite(block.genesis ? "GENESIS" : "#" + block.index, block.ok ? "#cfeffd" : "#fecaca");
      label.scale.set(2.8, 0.7, 1);
      label.position.set(0, 1.3, 0);
      node.add(label);

      return { block: block, node: node, cube: cube, edges: edges, core: core, glow: glow, base: base, born: -100, k: k };
    }

    function makeLink(from, to) {
      const bad = to.block.checks && to.block.checks.link === false;
      const color = bad ? SC.colors.red : SC.colors.cyan;
      const mesh = new THREE.Mesh(
        new THREE.CylinderGeometry(0.035, 0.035, 1, 6, 1, true),
        new THREE.MeshBasicMaterial({
          color: color, transparent: true, opacity: bad ? 0.9 : 0.55,
          blending: THREE.AdditiveBlending, depthWrite: false,
        })
      );
      const pulses = [];
      if (!bad) {
        for (let j = 0; j < 2; j++) {
          const pulse = SC.glowSprite(0x9bebff, 0.55, 0.95);
          group.add(pulse);
          pulses.push(pulse);
        }
      }
      group.add(mesh);
      return { mesh: mesh, from: from, to: to, bad: bad, pulses: pulses };
    }

    function buildScene(payload) {
      SC.clearGroup(group);
      stage.pickables.length = 0;
      items = []; links = [];
      const n = blocks.length;
      blocks.forEach(function (block, k) {
        const item = makeBlock(block, k, n);
        group.add(item.node);
        stage.pickables.push(item.cube);
        items.push(item);
      });
      for (let k = 1; k < items.length; k++) links.push(makeLink(items[k - 1], items[k]));

      ring = new THREE.Mesh(
        new THREE.TorusGeometry(1.25, 0.02, 8, 64),
        new THREE.MeshBasicMaterial({ color: SC.colors.cyan, transparent: true, opacity: 0.9, blending: THREE.AdditiveBlending, depthWrite: false })
      );
      ring.visible = false;
      group.add(ring);

      // Newly mined blocks grow into place.
      const firstBuild = Object.keys(known).length === 0;
      items.forEach(function (item) {
        const isNew = !known[item.block.hash];
        if ((isNew && !firstBuild) || payload.animate === item.block.index) item.born = stage.time;
        known[item.block.hash] = true;
      });
    }

    const tmpA = up ? new THREE.Vector3() : null;
    const tmpDir = up ? new THREE.Vector3() : null;

    function frame(dt, t) {
      for (let i = 0; i < items.length; i++) {
        const item = items[i];
        const k = item.k;
        const age = t - item.born;
        const grow = age < 1.2 ? Math.max(0.001, SC.easeOutBack(Math.min(1, age / 1.2))) : 1;
        const bob = SC.reducedMotion ? 0 : Math.sin(t * 0.8 + k * 1.3) * 0.13;
        item.node.position.set(item.base.x, item.base.y + bob, item.base.z);
        if (!item.block.ok && !SC.reducedMotion) item.node.position.x += Math.sin(t * 38 + k) * 0.012;   // uneasy tremble
        const hoverBoost = hovered === item.block.index ? 1.08 : 1;
        item.node.scale.setScalar(grow * hoverBoost);
        if (!SC.reducedMotion) {
          item.cube.rotation.y += dt * 0.28 * (k % 2 ? 1 : -1);
          item.cube.rotation.x = Math.sin(t * 0.35 + k) * 0.18;
          item.edges.rotation.copy(item.cube.rotation);
          item.core.rotation.x += dt * 0.9; item.core.rotation.y += dt * 1.2;
        }
        const pulse = 0.5 + 0.5 * Math.sin(t * (item.block.ok ? 1.6 : 6) + k);
        item.glow.material.opacity = (item.block.ok ? 0.3 : 0.5) + pulse * (item.block.ok ? 0.16 : 0.35) + (age < 2 ? (2 - age) * 0.5 : 0);
        item.glow.scale.setScalar(3.6 + (age < 2 ? (2 - age) * 2.2 : 0));
        if (selected === item.block.index && ring) {
          ring.position.copy(item.node.position);
          ring.rotation.x = Math.PI / 2 + Math.sin(t * 0.9) * 0.5;
          ring.rotation.y += dt * 0.8;
        }
      }
      for (let i = 0; i < links.length; i++) {
        const link = links[i];
        const a = link.from.node.position, b = link.to.node.position;
        const age = t - link.to.born;
        const progress = age < 1.2 ? Math.min(1, Math.max(0.001, age / 1.2)) : 1;
        tmpDir.subVectors(b, a);
        const length = tmpDir.length();
        tmpDir.normalize();
        tmpA.copy(a).addScaledVector(tmpDir, length * progress * 0.5);
        link.mesh.position.copy(tmpA);
        link.mesh.scale.set(1, length * progress, 1);
        link.mesh.quaternion.setFromUnitVectors(up, tmpDir);
        if (link.bad) link.mesh.material.opacity = 0.35 + 0.55 * Math.abs(Math.sin(t * 5));
        for (let j = 0; j < link.pulses.length; j++) {
          const u = (t * 0.45 + j * 0.5 + i * 0.17) % 1;
          link.pulses[j].position.copy(a).addScaledVector(tmpDir, length * u);
          link.pulses[j].material.opacity = Math.sin(Math.PI * u) * 0.95 * progress;
        }
      }
      if (stars) stars.rotation.y += dt * 0.01;
    }

    let hovered = null;
    let stars = null;

    function startStage() {
      const n = blocks.length;
      stage = new SC.Stage(canvasBox, {
        theta: -0.3, phi: 1.2, radius: Math.min(12.5, Math.max(8, n * 1.5)), minRadius: 4, maxRadius: 60, autoSpeed: 0.035,
      });
      group = new THREE.Group();
      stage.scene.add(group);
      // A faint floor grid gives the floating blocks a sense of depth.
      const grid = new THREE.GridHelper(160, 80, 0x22d3ee, 0x1e3a5f);
      grid.position.y = -2.6;
      grid.material.transparent = true;
      grid.material.opacity = 0.16;
      grid.material.depthWrite = false;
      stage.scene.add(grid);
      stars = SC.addStars(stage.scene, 420, 60);
      stage.onFrame = frame;
      stage.onClick = function (hit) {
        if (hit) select(hit.index === selected ? null : hit.index);
      };
      stage.onHover = function (hit, event) {
        hovered = hit ? hit.index : null;
        stage.dom.style.cursor = hit ? "pointer" : "grab";
        if (hit && event) {
          const item = byIndex(hit.index);
          const rect = wrap.getBoundingClientRect();
          tooltip.innerHTML =
            "<b>" + (item.block.genesis ? "Genesis block" : "Block #" + SC.esc(item.block.index)) + "</b><br>" +
            SC.esc(item.block.tx_count) + " transaction" + (item.block.tx_count === 1 ? "" : "s") + " · " +
            (item.block.ok ? '<span class="ok">verified</span>' : '<span class="bad">invalid</span>');
          tooltip.style.left = event.clientX - rect.left + 14 + "px";
          tooltip.style.top = event.clientY - rect.top + 14 + "px";
          tooltip.classList.add("show");
        } else {
          tooltip.classList.remove("show");
        }
      };
    }

    function focusDefault(payload) {
      if (!stage || !items.length) return;
      const wanted = payload.animate !== null && payload.animate !== undefined ? payload.animate
        : payload.focus !== null && payload.focus !== undefined ? payload.focus : null;
      const item = wanted !== null ? byIndex(wanted) : null;
      if (item) {
        stage.goalTarget.copy(item.base);
        return;
      }
      // Half of the world width visible at the current zoom.
      const halfWidth = stage.goalRadius * Math.tan((stage.camera.fov * Math.PI) / 360) * stage.camera.aspect;
      const chainHalf = ((items.length - 1) * SPACING) / 2;
      if (chainHalf <= halfWidth * 0.82) {
        stage.goalTarget.set(0, -0.2, 0);                        // the whole chain fits: centre it
      } else {
        // Long chain: keep the newest block near the right edge of the view.
        stage.goalTarget.set(items[items.length - 1].base.x - halfWidth * 0.62, -0.2, 0);
      }
    }

    let lastFocus;
    function apply(payload, first) {
      const previousHashes = blocks.map(function (b) { return b.hash + b.ok; }).join("|");
      blocks = payload.blocks || [];
      const changed = previousHashes !== blocks.map(function (b) { return b.hash + b.ok; }).join("|");
      renderHud(payload);

      if (!SC.hasWebGL()) {
        if (changed || first) buildFallback();
      } else {
        if (!stage) {
          try {
            startStage();
          } catch (err) {
            console.warn("WebGL start failed, using 2D fallback", err);
            stage = null;
            buildFallback();
            return;
          }
        }
        if (changed || first) {
          buildScene(payload);
          if (first) { focusDefault(payload); stage.target.copy(stage.goalTarget); }
          else focusDefault(payload);
        }
      }
      // Keep an open panel in sync with fresh data (or close it if the block is gone).
      if (selected !== null) {
        const item = byIndex(selected);
        if (item) { showPanel(item.block); if (ring) ring.visible = true; } else select(null);
      }
      // Python asked to focus a specific block (explorer slider / search).
      if (payload.focus !== lastFocus) {
        lastFocus = payload.focus;
        if (payload.focus !== null && payload.focus !== undefined && !first) select(payload.focus);
        else if (payload.focus !== null && payload.focus !== undefined && first && payload.open_panel) select(payload.focus);
      }
    }

    button("‹", "Previous block", function () { step(-1); });
    button("›", "Next block", function () { step(1); });
    button("Tip", "Jump to the newest block", function () { if (items.length) select(items[items.length - 1].block.index); });
    button("Reset", "Reset the camera", function () { if (stage) { stage.resetView(); focusDefault({}); } select(null); });
    const spin = button("Auto-rotate", "Toggle slow rotation", function () {
      if (!stage) return;
      stage.autoRotate = !stage.autoRotate;
      spin.classList.toggle("off", !stage.autoRotate);
    });
    if (SC.reducedMotion) spin.classList.add("off");

    apply(data, true);

    return {
      update: function (payload) { apply(payload, false); },
      destroy: function () { if (stage) stage.dispose(); },
    };
  };
})();
