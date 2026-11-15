/*
 * View "network": wallets as 3D nodes, transactions as particles flying
 * from sender to receiver.
 *
 * data = {
 *   nodes:  [{ id, label, kind: wallet|external|mint, balance, balance_text, available_text,
 *              sent_text, received_text, tx_count, flagged, rejected, risk: ok|flagged|rejected,
 *              history: [{time, direction: in|out, peer, amount, status}] }],
 *   events: [{ from, to, amount, amount_text, status: confirmed|pending|flagged|rejected }],
 *   stats:  { confirmed, pending, flagged, rejected }
 * }
 * confirmed = green, pending = cyan, flagged by the fraud monitor = amber,
 * rejected = red (the particle never reaches the receiver).
 */
(function () {
  "use strict";
  const SC = window.SC;
  const STATUS = {
    confirmed: { color: SC.colors.green, css: SC.css.green, label: "Confirmed" },
    pending: { color: SC.colors.cyan, css: SC.css.cyan, label: "Pending" },
    flagged: { color: SC.colors.amber, css: SC.css.amber, label: "Flagged" },
    rejected: { color: SC.colors.red, css: SC.css.red, label: "Rejected" },
  };
  const SEVERITY = { confirmed: 0, pending: 1, flagged: 2, rejected: 3 };

  SC.views.network = function (root, data) {
    const wrap = SC.el("div", "viz viz-network");
    root.appendChild(wrap);
    const canvasBox = SC.el("div", "viz-canvas");
    wrap.appendChild(canvasBox);
    const labelLayer = SC.el("div", "viz-labels");
    wrap.appendChild(labelLayer);
    const hud = SC.el("div", "viz-hud");
    wrap.appendChild(hud);
    const filters = SC.el("div", "viz-filters");
    wrap.appendChild(filters);
    const hint = SC.el("div", "viz-hint", "Drag to rotate  ·  Scroll to zoom  ·  Click a wallet");
    wrap.appendChild(hint);
    const tooltip = SC.el("div", "viz-tooltip");
    wrap.appendChild(tooltip);
    const panel = SC.el("aside", "viz-panel");
    wrap.appendChild(panel);

    let payload = data;
    let stage = null, group = null, stars = null;
    let nodes = [];            // { data, mesh, shell, glow, ring, base, label }
    let nodeById = {};
    let edges = [];            // { key, from, to, curve, line, status }
    let particles = [];        // { event, edge, sprite, burst, phase, speed }
    let selected = null, hovered = null;
    const visible = { confirmed: true, pending: true, flagged: true, rejected: true };

    // ------------------------------------------------------------------
    // Panel
    // ------------------------------------------------------------------
    function showPanel(node) {
      const d = node.data;
      const kind = d.kind === "mint" ? '<span class="badge purple">PROTOCOL</span>'
        : d.kind === "external" ? '<span class="badge">EXTERNAL ADDRESS</span>'
        : d.risk === "rejected" ? '<span class="badge bad">REJECTED ATTEMPTS</span>'
        : d.risk === "flagged" ? '<span class="badge warn">FLAGGED ACTIVITY</span>'
        : '<span class="badge ok">WALLET</span>';
      let html =
        '<button class="viz-close" title="Close">×</button>' +
        '<div class="panel-eyebrow">' + (d.kind === "mint" ? "Coin source" : "Wallet") + "</div>" +
        '<div class="panel-title">' + SC.esc(d.label) + " " + kind + "</div>";
      if (d.kind !== "mint") html += '<div class="mono small break">' + SC.esc(d.id) + "</div>";
      if (d.kind === "mint") {
        html += '<div class="muted">Mining rewards are created by the protocol. This is the only way new coins enter circulation.</div>';
      } else {
        html +=
          '<div class="stat-grid">' +
          '<div><span>Balance</span><b>' + SC.esc(d.balance_text) + "</b></div>" +
          '<div><span>Available</span><b>' + SC.esc(d.available_text) + "</b></div>" +
          '<div><span>Sent</span><b>' + SC.esc(d.sent_text) + "</b></div>" +
          '<div><span>Received</span><b>' + SC.esc(d.received_text) + "</b></div>" +
          "</div>" +
          '<div class="chips">' +
          '<span class="chip">' + SC.esc(d.tx_count) + " transactions</span>" +
          (d.flagged ? '<span class="chip warn">' + SC.esc(d.flagged) + " flagged</span>" : "") +
          (d.rejected ? '<span class="chip bad">' + SC.esc(d.rejected) + " rejected</span>" : "") +
          "</div>";
      }
      html += '<div class="panel-eyebrow">Recent activity</div>';
      if (!d.history || !d.history.length) {
        html += '<div class="muted">No transactions yet.</div>';
      } else {
        html += d.history.map(function (h) {
          const s = STATUS[h.status] || STATUS.confirmed;
          return (
            '<div class="tx ' + (h.status === "rejected" ? "bad" : h.status === "flagged" ? "warn" : "") + '">' +
            '<div class="tx-top"><span class="tx-type">' + (h.direction === "in" ? "← from " : "→ to ") + SC.esc(h.peer) + "</span>" +
            '<span class="tx-amount ' + (h.direction === "in" ? "ok" : "") + '">' + (h.direction === "in" ? "+" : "−") + SC.esc(h.amount) + "</span></div>" +
            '<div class="tx-meta"><span>' + SC.esc(h.time) + '</span><span style="color:' + s.css + '">' + s.label + "</span></div></div>"
          );
        }).join("");
      }
      panel.innerHTML = html;
      panel.classList.add("open");
      panel.querySelector(".viz-close").addEventListener("click", function () { select(null); });
    }

    function select(id) {
      selected = id && nodeById[id] ? id : null;
      if (!selected) { panel.classList.remove("open"); }
      else {
        showPanel(nodeById[selected]);
        if (stage) { stage.goalTarget.copy(nodeById[selected].base).multiplyScalar(0.35); stage.lastInteraction = stage.time; }
      }
      nodes.forEach(function (n) { if (n.label) n.label.classList.toggle("selected", n.data.id === selected); if (n.card) n.card.classList.toggle("selected", n.data.id === selected); });
      refreshVisibility();
    }

    function refreshVisibility() {
      edges.forEach(function (edge) {
        const touches = !selected || edge.from === selected || edge.to === selected;
        const any = edge.statuses.some(function (s) { return visible[s]; });
        if (edge.line) { edge.line.visible = any; edge.line.material.opacity = touches ? 0.34 : 0.05; }
      });
      particles.forEach(function (p) {
        const touches = !selected || p.event.from === selected || p.event.to === selected;
        p.on = visible[p.event.status] && touches;
        if (p.sprite) p.sprite.visible = p.on;
        if (p.burst) p.burst.visible = p.on;
      });
    }

    function renderHud() {
      const s = payload.stats || {};
      hud.innerHTML =
        '<div class="hud-eyebrow"><span class="live-dot"></span>Transaction network</div>' +
        '<div class="hud-title">' + SC.esc((payload.nodes || []).filter(function (n) { return n.kind === "wallet"; }).length) + " wallets</div>";
      filters.innerHTML = "";
      Object.keys(STATUS).forEach(function (key) {
        const b = SC.el("button", "filter" + (visible[key] ? "" : " off"));
        b.innerHTML = '<span class="dot" style="background:' + STATUS[key].css + '"></span>' + STATUS[key].label + " <b>" + SC.esc(s[key] || 0) + "</b>";
        b.title = "Show / hide " + STATUS[key].label.toLowerCase() + " transactions";
        b.addEventListener("click", function () { visible[key] = !visible[key]; b.classList.toggle("off", !visible[key]); refreshVisibility(); });
        filters.appendChild(b);
      });
    }

    // ------------------------------------------------------------------
    // 2D fallback
    // ------------------------------------------------------------------
    function buildFallback() {
      canvasBox.innerHTML = "";
      labelLayer.innerHTML = "";
      const grid = SC.el("div", "fallback-grid");
      canvasBox.appendChild(grid);
      nodes = []; nodeById = {};
      (payload.nodes || []).forEach(function (d) {
        const card = SC.el("button", "fallback-node " + d.kind + " " + d.risk);
        card.innerHTML = '<div class="fb-title">' + SC.esc(d.label) + '</div><div class="fb-meta">' + SC.esc(d.kind === "mint" ? "protocol" : d.balance_text) + "</div>";
        card.addEventListener("click", function () { select(d.id === selected ? null : d.id); });
        grid.appendChild(card);
        const node = { data: d, card: card, base: { copy: function () {} } };
        nodes.push(node); nodeById[d.id] = node;
      });
      hint.textContent = "3D view unavailable (no WebGL) - showing wallets as cards. Click one.";
    }

    // ------------------------------------------------------------------
    // 3D scene
    // ------------------------------------------------------------------
    function layout(list) {
      const wallets = list.filter(function (n) { return n.kind === "wallet"; });
      const externals = list.filter(function (n) { return n.kind === "external"; });
      const radius = Math.min(6.5, 3.4 + wallets.length * 0.28);
      const positions = {};
      wallets.forEach(function (n, i) {
        const angle = (i / Math.max(wallets.length, 1)) * Math.PI * 2 + Math.PI / 6;
        positions[n.id] = new THREE.Vector3(Math.cos(angle) * radius, (i % 2 ? 0.55 : -0.55), Math.sin(angle) * radius);
      });
      externals.forEach(function (n, i) {
        const angle = (i / Math.max(externals.length, 1)) * Math.PI * 2 + 0.9;
        positions[n.id] = new THREE.Vector3(Math.cos(angle) * (radius + 2.4), -1.1, Math.sin(angle) * (radius + 2.4));
      });
      list.forEach(function (n) { if (n.kind === "mint") positions[n.id] = new THREE.Vector3(0, 3.3, 0); });
      return { positions: positions, radius: radius };
    }

    function nodeColor(d) {
      if (d.kind === "mint") return SC.colors.purple;
      if (d.kind === "external") return d.risk === "rejected" ? SC.colors.red : SC.colors.grey;
      return SC.colors.cyan;
    }

    function buildScene() {
      SC.clearGroup(group);
      stage.pickables.length = 0;
      labelLayer.innerHTML = "";
      nodes = []; nodeById = {}; edges = []; particles = [];
      const list = payload.nodes || [];
      const placed = layout(list);
      const maxBalance = Math.max.apply(null, list.map(function (n) { return n.balance || 0; }).concat([1]));

      list.forEach(function (d, i) {
        const color = nodeColor(d);
        const size = d.kind === "mint" ? 0.5 : d.kind === "external" ? 0.24 : 0.36 + 0.3 * Math.sqrt(Math.max(0, d.balance || 0) / maxBalance);   // (a tampered chain can show a negative balance)
        const holder = new THREE.Group();
        const base = placed.positions[d.id];
        holder.position.copy(base);
        const mesh = new THREE.Mesh(
          d.kind === "mint" ? new THREE.OctahedronGeometry(size, 0) : new THREE.SphereGeometry(size, 32, 20),
          new THREE.MeshStandardMaterial({ color: 0x0b1930, emissive: color, emissiveIntensity: 0.55, metalness: 0.5, roughness: 0.25 })
        );
        mesh.userData = { id: d.id };
        holder.add(mesh);
        const shell = new THREE.Mesh(
          new THREE.IcosahedronGeometry(size * 1.45, 1),
          new THREE.MeshBasicMaterial({ color: color, wireframe: true, transparent: true, opacity: d.kind === "external" ? 0.18 : 0.32 })
        );
        holder.add(shell);
        const glow = SC.glowSprite(color, size * 6.5, 0.5);
        holder.add(glow);
        let ring = null;
        if (d.risk !== "ok") {
          // Suspicious wallet highlight: amber = flagged by the fraud monitor, red = rejected attempts.
          ring = new THREE.Mesh(
            new THREE.TorusGeometry(size * 2.0, 0.025, 8, 48),
            new THREE.MeshBasicMaterial({
              color: d.risk === "rejected" ? SC.colors.red : SC.colors.amber, transparent: true, opacity: 0.95,
              blending: THREE.AdditiveBlending, depthWrite: false,
            })
          );
          holder.add(ring);
        }
        group.add(holder);
        stage.pickables.push(mesh);

        const label = SC.el("div", "node-label " + d.kind + " " + d.risk);
        label.innerHTML = "<b>" + SC.esc(d.label) + "</b>" + (d.kind === "wallet" ? "<span>" + SC.esc(d.balance_text) + "</span>" : "");
        labelLayer.appendChild(label);

        const node = { data: d, holder: holder, mesh: mesh, shell: shell, glow: glow, ring: ring, base: base, label: label, size: size, i: i };
        nodes.push(node); nodeById[d.id] = node;
      });

      // One curved edge per (sender, receiver) pair.
      const edgeByKey = {};
      const upVec = new THREE.Vector3(0, 1, 0);
      (payload.events || []).forEach(function (event, index) {
        const a = nodeById[event.from], b = nodeById[event.to];
        if (!a || !b) return;
        const key = event.from + ">" + event.to;
        let edge = edgeByKey[key];
        if (!edge) {
          const delta = new THREE.Vector3().subVectors(b.base, a.base);
          const distance = delta.length();
          const side = new THREE.Vector3().crossVectors(delta, upVec).normalize();
          const control = new THREE.Vector3().addVectors(a.base, b.base).multiplyScalar(0.5)
            .addScaledVector(upVec, 0.7 + distance * 0.14)
            .addScaledVector(side, 0.55);
          const curve = new THREE.QuadraticBezierCurve3(a.base.clone(), control, b.base.clone());
          edge = edgeByKey[key] = { key: key, from: event.from, to: event.to, curve: curve, statuses: [], worst: "confirmed", count: 0 };
          edges.push(edge);
        }
        edge.count += 1;
        if (edge.statuses.indexOf(event.status) < 0) edge.statuses.push(event.status);
        if (SEVERITY[event.status] > SEVERITY[edge.worst]) edge.worst = event.status;

        const s = STATUS[event.status] || STATUS.confirmed;
        const scale = 0.34 + Math.min(0.5, Math.log10(1 + (event.amount || 0)) * 0.16);
        const sprite = SC.glowSprite(s.color, scale, 1);
        group.add(sprite);
        let burst = null;
        if (event.status === "rejected") {
          burst = SC.glowSprite(SC.colors.red, 0.1, 0);
          group.add(burst);
        }
        particles.push({
          event: event, edge: edge, sprite: sprite, burst: burst, scale: scale, on: true,
          phase: (index * 0.137) % 1, speed: 0.16 + ((index * 7) % 5) * 0.012,
        });
      });

      edges.forEach(function (edge) {
        const geometry = new THREE.BufferGeometry().setFromPoints(edge.curve.getPoints(30));
        edge.line = new THREE.Line(
          geometry,
          new THREE.LineBasicMaterial({ color: STATUS[edge.worst].color, transparent: true, opacity: 0.34, blending: THREE.AdditiveBlending, depthWrite: false })
        );
        group.add(edge.line);
      });

      // Far enough back that the whole ring of wallets (and the outer addresses) fits in view.
      const outer = placed.radius + ((payload.nodes || []).some(function (n) { return n.kind === "external"; }) ? 2.6 : 0);
      stage.goalRadius = stage.home.radius = Math.max(14.5, outer * 2.2 + 2.5);
      refreshVisibility();
    }

    const point = typeof THREE !== "undefined" ? new THREE.Vector3() : null;
    function frame(dt, t) {
      for (let i = 0; i < nodes.length; i++) {
        const n = nodes[i];
        const bob = SC.reducedMotion ? 0 : Math.sin(t * 0.7 + i * 1.7) * 0.12;
        n.holder.position.set(n.base.x, n.base.y + bob, n.base.z);
        const boost = hovered === n.data.id || selected === n.data.id ? 1.18 : 1;
        n.holder.scale.setScalar(n.holder.scale.x + (boost - n.holder.scale.x) * 0.15);
        if (!SC.reducedMotion) {
          n.shell.rotation.y += dt * 0.35; n.shell.rotation.x += dt * 0.2;
          if (n.data.kind === "mint") n.mesh.rotation.y += dt * 0.8;
          if (n.ring) { n.ring.rotation.x = Math.PI / 2 + Math.sin(t * 1.3 + i) * 0.6; n.ring.rotation.y += dt * 1.4; }
        }
        n.glow.material.opacity = 0.4 + 0.14 * Math.sin(t * 1.4 + i);
        // HTML label follows the node on screen.
        point.copy(n.holder.position); point.y -= n.size * 1.9 + 0.25;
        const screen = stage.project(point);
        if (screen) {
          n.label.style.transform = "translate(" + screen.x.toFixed(1) + "px," + screen.y.toFixed(1) + "px) translate(-50%, 0)";
          n.label.style.opacity = selected && selected !== n.data.id ? "0.45" : "1";
        } else {
          n.label.style.opacity = "0";
        }
      }
      for (let i = 0; i < particles.length; i++) {
        const p = particles[i];
        if (!p.on) continue;
        const u = SC.reducedMotion ? 0.5 : (t * p.speed + p.phase) % 1;
        if (p.event.status === "rejected") {
          // A rejected transaction never arrives: it stops part-way and bursts.
          const travel = Math.min(u / 0.7, 1) * 0.58;
          p.edge.curve.getPoint(travel, point);
          p.sprite.position.copy(point);
          const fade = u < 0.7 ? Math.min(1, u * 8) : Math.max(0, 1 - (u - 0.7) / 0.12);
          p.sprite.material.opacity = fade;
          const b = u < 0.7 ? 0 : (u - 0.7) / 0.3;
          p.burst.position.copy(point);
          p.burst.scale.setScalar(0.2 + b * 2.4);
          p.burst.material.opacity = u < 0.7 ? 0 : (1 - b) * 0.85;
        } else {
          p.edge.curve.getPoint(u, point);
          p.sprite.position.copy(point);
          p.sprite.material.opacity = Math.min(1, Math.sin(Math.PI * u) * 1.6);
          if (p.event.status === "flagged") p.sprite.scale.setScalar(p.scale * (1 + 0.35 * Math.abs(Math.sin(t * 6 + i))));
        }
      }
      if (stars) stars.rotation.y += dt * 0.008;
    }

    function startStage() {
      stage = new SC.Stage(canvasBox, { theta: 0.5, phi: 1.02, radius: 16, minRadius: 5, maxRadius: 50, autoSpeed: 0.06, fog: 0.016 });
      stage.goalTarget.set(0, -0.3, 0); stage.target.set(0, -0.3, 0);
      group = new THREE.Group();
      stage.scene.add(group);
      stars = SC.addStars(stage.scene, 360, 55);
      stage.onFrame = frame;
      stage.onClick = function (hit) {
        if (hit) select(hit.id === selected ? null : hit.id);
        else if (selected) { select(null); stage.goalTarget.set(0, -0.3, 0); }
      };
      stage.onHover = function (hit, event) {
        hovered = hit ? hit.id : null;
        stage.dom.style.cursor = hit ? "pointer" : "grab";
        if (hit && event) {
          const d = nodeById[hit.id].data;
          const rect = wrap.getBoundingClientRect();
          tooltip.innerHTML = "<b>" + SC.esc(d.label) + "</b><br>" +
            (d.kind === "mint" ? "Source of mining rewards" : SC.esc(d.balance_text) + " · " + SC.esc(d.tx_count) + " tx");
          tooltip.style.left = event.clientX - rect.left + 14 + "px";
          tooltip.style.top = event.clientY - rect.top + 14 + "px";
          tooltip.classList.add("show");
        } else tooltip.classList.remove("show");
      };
    }

    let signature = "";
    function apply(next, first) {
      payload = next;
      renderHud();
      const sig = JSON.stringify([(payload.nodes || []).map(function (n) { return [n.id, n.balance, n.risk, n.tx_count, n.label]; }),
        (payload.events || []).map(function (e) { return [e.from, e.to, e.amount, e.status]; })]);
      const changed = sig !== signature;
      signature = sig;
      if (!(payload.nodes || []).length) {
        canvasBox.innerHTML = '<div class="viz-empty">No wallets yet. Create a wallet or load the demo data to see the network.</div>';
        return;
      }
      if (!SC.hasWebGL()) { if (changed || first) buildFallback(); }
      else {
        if (!stage) {
          try { canvasBox.innerHTML = ""; startStage(); }
          catch (err) { console.warn("WebGL start failed, using 2D fallback", err); stage = null; buildFallback(); return; }
        }
        if (changed || first) buildScene();
      }
      if (selected) { if (nodeById[selected]) showPanel(nodeById[selected]); else select(null); }
    }

    apply(data, true);
    return {
      update: function (next) { apply(next, false); },
      destroy: function () { if (stage) stage.dispose(); },
    };
  };
})();
