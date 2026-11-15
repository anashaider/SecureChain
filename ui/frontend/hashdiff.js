/*
 * View "hashdiff": animated hash comparison used by the tampering demo.
 *
 * data = {
 *   title, token,
 *   fields: [{ label, before, after, changed }],          (before / after table)
 *   comparisons: [{
 *       title, explain,
 *       a: { label, value }  or  { label, compute: "text to hash in the browser" },
 *       b: { label, value }
 *   }]
 * }
 * For "compute" entries the SHA-256 hash is calculated here, in the
 * browser, from the data currently stored - then compared character by
 * character with the stored fingerprint.
 */
(function () {
  "use strict";
  const SC = window.SC;
  const HEX = "0123456789abcdef";

  SC.views.hashdiff = function (root, data) {
    const wrap = SC.el("div", "viz viz-hashdiff");
    root.appendChild(wrap);
    let payload = data;
    let timers = [];
    let runId = 0;

    function later(fn, ms) { const id = setTimeout(fn, ms); timers.push(id); }
    function clearTimers() { timers.forEach(clearTimeout); timers = []; }

    function cells(value) {
      let html = "";
      for (let i = 0; i < value.length; i++) html += "<i>" + SC.esc(value[i]) + "</i>";
      return html;
    }

    function build() {
      let html = '<div class="hd-head"><div class="hud-eyebrow"><span class="live-dot"></span>' + SC.esc(payload.title || "Integrity check") +
        '</div><button class="viz-btn replay">Replay</button></div>';
      if (payload.fields && payload.fields.length) {
        html += '<div class="hd-fields"><div class="hd-fields-head"><span></span><span>Original</span><span>Stored now</span></div>' +
          payload.fields.map(function (f) {
            return '<div class="hd-field' + (f.changed ? " changed" : "") + '"><span class="hd-label">' + SC.esc(f.label) + "</span>" +
              '<span class="mono">' + SC.esc(f.before) + '</span><span class="mono">' + SC.esc(f.after) + "</span></div>";
          }).join("") + "</div>";
      }
      html += (payload.comparisons || []).map(function (c, i) {
        return (
          '<div class="hd-cmp" data-cmp="' + i + '">' +
          '<div class="hd-cmp-top"><div><b>' + SC.esc(c.title) + '</b><span class="hd-explain">' + SC.esc(c.explain || "") + "</span></div>" +
          '<span class="badge verdict">…</span></div>' +
          '<div class="hd-row"><span class="hd-label">' + SC.esc(c.a.label) + '</span><span class="hd-hash mono a"></span></div>' +
          '<div class="hd-row"><span class="hd-label">' + SC.esc(c.b.label) + '</span><span class="hd-hash mono b"></span></div>' +
          "</div>"
        );
      }).join("");
      wrap.innerHTML = html;
      wrap.querySelector(".replay").addEventListener("click", function () { play(true); });
    }

    function resolve(side) {
      return side.compute !== undefined && side.compute !== null ? SC.sha256(side.compute) : String(side.value || "");
    }

    function settle(index, a, b) {
      const box = wrap.querySelector('.hd-cmp[data-cmp="' + index + '"]');
      const ra = box.querySelector(".a"), rb = box.querySelector(".b");
      ra.innerHTML = cells(a); rb.innerHTML = cells(b);
      const ca = ra.children, cb = rb.children;
      let diff = Math.abs(a.length - b.length);
      for (let i = 0; i < Math.max(a.length, b.length); i++) {
        const same = a[i] === b[i];
        if (!same && i < Math.min(a.length, b.length)) diff++;
        if (ca[i]) ca[i].className = same ? "same" : "diff";
        if (cb[i]) cb[i].className = same ? "same" : "diff";
      }
      verdict(box, diff);
    }

    function verdict(box, diff) {
      const badge = box.querySelector(".verdict");
      badge.className = "badge verdict " + (diff ? "bad" : "ok");
      const total = box.querySelector(".a").children.length;
      badge.textContent = diff ? "MISMATCH · " + diff + " of " + total + " characters differ" : "MATCH";
      box.classList.add(diff ? "bad" : "ok");
    }

    function animate(index, done, myRun) {
      const c = payload.comparisons[index];
      const box = wrap.querySelector('.hd-cmp[data-cmp="' + index + '"]');
      const a = resolve(c.a), b = resolve(c.b);
      const ra = box.querySelector(".a"), rb = box.querySelector(".b");
      box.classList.add("active");
      rb.innerHTML = cells(b);
      const computing = c.a.compute !== undefined && c.a.compute !== null;
      let frames = computing ? 16 : 0;

      function scramble() {
        if (myRun !== runId) return;
        if (frames-- > 0) {
          let noise = "";
          for (let i = 0; i < a.length; i++) noise += HEX[(Math.random() * 16) | 0];
          ra.innerHTML = cells(noise);
          ra.classList.add("computing");
          later(scramble, 45);
        } else {
          ra.classList.remove("computing");
          ra.innerHTML = cells(a);
          sweep(0, 0);
        }
      }
      function sweep(i, diff) {
        if (myRun !== runId) return;
        const ca = ra.children, cb = rb.children;
        const stepSize = 4;
        for (let k = i; k < Math.min(i + stepSize, Math.max(a.length, b.length)); k++) {
          const same = a[k] === b[k];
          if (!same) diff++;
          if (ca[k]) ca[k].className = same ? "same" : "diff";
          if (cb[k]) cb[k].className = same ? "same" : "diff";
        }
        if (i + stepSize < Math.max(a.length, b.length)) later(function () { sweep(i + stepSize, diff); }, 38);
        else { verdict(box, diff); box.classList.remove("active"); later(done, 380); }
      }
      scramble();
    }

    function play(animated) {
      clearTimers();
      const myRun = ++runId;
      build();
      const list = payload.comparisons || [];
      if (!animated || SC.reducedMotion) {
        list.forEach(function (c, i) { settle(i, resolve(c.a), resolve(c.b)); });
        return;
      }
      let index = 0;
      (function next() {
        if (myRun !== runId || index >= list.length) return;
        animate(index++, next, myRun);
      })();
    }

    let token = null;
    function apply(next, first) {
      payload = next;
      if (first || next.token !== token) { token = next.token; play(true); }
    }
    apply(data, true);
    return {
      update: function (next) { apply(next, false); },
      destroy: function () { clearTimers(); runId++; },
    };
  };
})();
