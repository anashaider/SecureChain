/*
 * SecureChain visual component - core.
 *
 * This frame is a one-way display: Streamlit sends real ledger data in,
 * and everything the user does here (rotate, zoom, click a block) stays
 * inside the frame. Nothing is ever written back to Streamlit, so the
 * visuals cannot disturb the application's session state.
 *
 * Only public data is received: hashes, addresses, amounts, signatures.
 * Private keys and passwords never leave the Python process.
 */
(function () {
  "use strict";

  const SC = (window.SC = { views: {}, instance: null, viewName: null });

  // ------------------------------------------------------------------
  // Streamlit component protocol (the small part of it we need)
  // ------------------------------------------------------------------
  SC.post = function (type, data) {
    window.parent.postMessage(Object.assign({ isStreamlitMessage: true, type: type }, data || {}), "*");
  };
  SC.setHeight = function (height) {
    SC.post("streamlit:setFrameHeight", { height: height });
  };

  SC.render = function (args) {
    const root = document.getElementById("root");
    const height = args.height || 480;
    root.style.height = height + "px";
    SC.setHeight(height);
    try {
      if (!SC.instance || SC.viewName !== args.view) {
        if (SC.instance && SC.instance.destroy) SC.instance.destroy();
        root.innerHTML = "";
        SC.viewName = args.view;
        const factory = SC.views[args.view];
        if (!factory) throw new Error("Unknown view: " + args.view);
        SC.instance = factory(root, args.data || {}, args);
      } else if (SC.instance.update) {
        SC.instance.update(args.data || {}, args);
      }
    } catch (err) {
      console.error(err);
      root.innerHTML = "";
      const box = SC.el("div", "viz viz-error");
      box.appendChild(SC.el("div", "viz-error-title", "Visualization could not start"));
      box.appendChild(SC.el("div", "viz-error-text", String(err && err.message ? err.message : err)));
      root.appendChild(box);
    }
  };

  window.addEventListener("message", function (event) {
    if (event.data && event.data.type === "streamlit:render") SC.render(event.data.args || {});
  });

  // ------------------------------------------------------------------
  // Small DOM helpers
  // ------------------------------------------------------------------
  SC.el = function (tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  };
  SC.esc = function (value) {
    return String(value === undefined || value === null ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  };
  SC.short = function (text, head, tail) {
    text = String(text || "");
    head = head || 10; tail = tail || 6;
    return text.length <= head + tail + 3 ? text : text.slice(0, head) + "..." + text.slice(-tail);
  };
  SC.reducedMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  SC.colors = {
    cyan: 0x22d3ee, blue: 0x3b82f6, purple: 0x8b5cf6, green: 0x34d399,
    amber: 0xfbbf24, red: 0xf87171, grey: 0x64748b, ink: 0x0a1528,
  };
  SC.css = { cyan: "#22d3ee", blue: "#60a5fa", purple: "#a78bfa", green: "#34d399", amber: "#fbbf24", red: "#f87171", grey: "#94a3b8" };

  // ------------------------------------------------------------------
  // SHA-256 (pure JavaScript, synchronous)
  // Used to RE-VERIFY hashes in the browser: the Proof-of-Work replay and
  // the tampering comparison show hashes computed here, not canned values.
  // ------------------------------------------------------------------
  SC.sha256 = (function () {
    const K = new Uint32Array([
      0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
      0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
      0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
      0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
      0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
      0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
      0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
      0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
    ]);
    const encoder = new TextEncoder();
    const w = new Uint32Array(64);
    return function (text) {
      const message = encoder.encode(String(text));
      const length = message.length;
      const total = ((length + 9 + 63) >> 6) << 6;
      const buffer = new Uint8Array(total);
      buffer.set(message);
      buffer[length] = 0x80;
      const view = new DataView(buffer.buffer);
      view.setUint32(total - 8, Math.floor(length / 0x20000000));
      view.setUint32(total - 4, (length << 3) >>> 0);
      let h0 = 0x6a09e667, h1 = 0xbb67ae85, h2 = 0x3c6ef372, h3 = 0xa54ff53a;
      let h4 = 0x510e527f, h5 = 0x9b05688c, h6 = 0x1f83d9ab, h7 = 0x5be0cd19;
      for (let offset = 0; offset < total; offset += 64) {
        for (let i = 0; i < 16; i++) w[i] = view.getUint32(offset + i * 4);
        for (let i = 16; i < 64; i++) {
          const x = w[i - 15], y = w[i - 2];
          const s0 = ((x >>> 7) | (x << 25)) ^ ((x >>> 18) | (x << 14)) ^ (x >>> 3);
          const s1 = ((y >>> 17) | (y << 15)) ^ ((y >>> 19) | (y << 13)) ^ (y >>> 10);
          w[i] = (w[i - 16] + s0 + w[i - 7] + s1) | 0;
        }
        let a = h0, b = h1, c = h2, d = h3, e = h4, f = h5, g = h6, h = h7;
        for (let i = 0; i < 64; i++) {
          const S1 = ((e >>> 6) | (e << 26)) ^ ((e >>> 11) | (e << 21)) ^ ((e >>> 25) | (e << 7));
          const ch = (e & f) ^ (~e & g);
          const t1 = (h + S1 + ch + K[i] + w[i]) | 0;
          const S0 = ((a >>> 2) | (a << 30)) ^ ((a >>> 13) | (a << 19)) ^ ((a >>> 22) | (a << 10));
          const maj = (a & b) ^ (a & c) ^ (b & c);
          const t2 = (S0 + maj) | 0;
          h = g; g = f; f = e; e = (d + t1) | 0; d = c; c = b; b = a; a = (t1 + t2) | 0;
        }
        h0 = (h0 + a) | 0; h1 = (h1 + b) | 0; h2 = (h2 + c) | 0; h3 = (h3 + d) | 0;
        h4 = (h4 + e) | 0; h5 = (h5 + f) | 0; h6 = (h6 + g) | 0; h7 = (h7 + h) | 0;
      }
      return [h0, h1, h2, h3, h4, h5, h6, h7]
        .map(function (word) { return (word >>> 0).toString(16).padStart(8, "0"); })
        .join("");
    };
  })();

  // ------------------------------------------------------------------
  // WebGL helpers
  // ------------------------------------------------------------------
  SC.hasWebGL = function () {
    if (typeof THREE === "undefined") return false;
    try {
      const canvas = document.createElement("canvas");
      return !!(window.WebGLRenderingContext && (canvas.getContext("webgl2") || canvas.getContext("webgl")));
    } catch (err) {
      return false;
    }
  };

  let glowTexture = null;
  SC.glowTexture = function () {
    if (glowTexture) return glowTexture;
    const size = 128;
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = size;
    const ctx = canvas.getContext("2d");
    const gradient = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
    gradient.addColorStop(0, "rgba(255,255,255,1)");
    gradient.addColorStop(0.18, "rgba(255,255,255,0.55)");
    gradient.addColorStop(0.45, "rgba(255,255,255,0.14)");
    gradient.addColorStop(1, "rgba(255,255,255,0)");
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, size, size);
    glowTexture = new THREE.CanvasTexture(canvas);
    return glowTexture;
  };

  SC.glowSprite = function (color, scale, opacity) {
    const material = new THREE.SpriteMaterial({
      map: SC.glowTexture(), color: color, transparent: true, opacity: opacity === undefined ? 0.6 : opacity,
      blending: THREE.AdditiveBlending, depthWrite: false,
    });
    const sprite = new THREE.Sprite(material);
    sprite.scale.set(scale, scale, 1);
    return sprite;
  };

  SC.textSprite = function (text, cssColor) {
    const canvas = document.createElement("canvas");
    canvas.width = 256; canvas.height = 64;
    const ctx = canvas.getContext("2d");
    ctx.font = "600 30px 'Segoe UI', Inter, system-ui, sans-serif";
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.shadowColor = cssColor; ctx.shadowBlur = 12;
    ctx.fillStyle = cssColor;
    ctx.fillText(text, 128, 32);
    const texture = new THREE.CanvasTexture(canvas);
    const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: texture, transparent: true, depthWrite: false }));
    sprite.scale.set(2.0, 0.5, 1);
    return sprite;
  };

  SC.addStars = function (scene, count, radius) {
    const positions = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      const r = radius * (0.45 + Math.random() * 0.55);
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      positions[i * 3] = r * Math.sin(phi) * Math.cos(theta);
      positions[i * 3 + 1] = r * Math.cos(phi) * 0.6;
      positions[i * 3 + 2] = r * Math.sin(phi) * Math.sin(theta);
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    const material = new THREE.PointsMaterial({
      map: SC.glowTexture(), color: 0x7dd3fc, size: 0.22, transparent: true, opacity: 0.55,
      blending: THREE.AdditiveBlending, depthWrite: false, sizeAttenuation: true,
    });
    const stars = new THREE.Points(geometry, material);
    scene.add(stars);
    return stars;
  };

  // ------------------------------------------------------------------
  // Stage: renderer + camera orbit (drag to rotate, wheel to zoom) + picking.
  // Rendering pauses automatically while the frame is off-screen or the
  // browser tab is hidden, so idle pages cost no GPU time.
  // ------------------------------------------------------------------
  SC.Stage = function (container, options) {
    options = options || {};
    const self = this;
    this.container = container;
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.renderer.setClearColor(0x000000, 0);
    this.dom = this.renderer.domElement;
    this.dom.style.touchAction = "none";
    container.appendChild(this.dom);

    this.scene = new THREE.Scene();
    this.scene.fog = new THREE.FogExp2(0x050912, options.fog === undefined ? 0.03 : options.fog);
    this.camera = new THREE.PerspectiveCamera(46, 1, 0.1, 300);

    this.target = new THREE.Vector3();
    this.goalTarget = new THREE.Vector3();
    this.theta = this.goalTheta = options.theta === undefined ? 0.0 : options.theta;
    this.phi = this.goalPhi = options.phi === undefined ? 1.25 : options.phi;
    this.radius = this.goalRadius = options.radius || 10;
    this.minRadius = options.minRadius || 3.5;
    this.maxRadius = options.maxRadius || 40;
    this.home = { theta: this.theta, phi: this.phi, radius: this.radius };
    this.autoRotate = options.autoRotate !== false && !SC.reducedMotion;
    this.autoSpeed = options.autoSpeed || 0.05;
    this.lastInteraction = -10;
    this.time = 0;

    this.scene.add(new THREE.AmbientLight(0x8fb6ff, 0.55));
    const key = new THREE.DirectionalLight(0xffffff, 0.9);
    key.position.set(4, 8, 6);
    this.scene.add(key);
    const rim = new THREE.PointLight(0x22d3ee, 1.1, 60);
    rim.position.set(-8, 3, -6);
    this.scene.add(rim);
    const fill = new THREE.PointLight(0x8b5cf6, 0.8, 60);
    fill.position.set(8, -4, 6);
    this.scene.add(fill);

    this.pickables = [];
    this.raycaster = new THREE.Raycaster();
    this.pointer = new THREE.Vector2();
    this.onFrame = null; this.onClick = null; this.onHover = null;

    // ----- pointer interaction -----
    let dragging = false, moved = 0, lastX = 0, lastY = 0, lastHover = 0;
    this._down = function (event) {
      dragging = true; moved = 0; lastX = event.clientX; lastY = event.clientY;
      try { self.dom.setPointerCapture(event.pointerId); } catch (err) { /* ignore */ }
      self.lastInteraction = self.time;
    };
    this._move = function (event) {
      if (dragging) {
        const dx = event.clientX - lastX, dy = event.clientY - lastY;
        lastX = event.clientX; lastY = event.clientY;
        moved += Math.abs(dx) + Math.abs(dy);
        self.goalTheta -= dx * 0.006;
        self.goalPhi = Math.min(Math.PI - 0.25, Math.max(0.25, self.goalPhi - dy * 0.005));
        self.lastInteraction = self.time;
        self.dom.style.cursor = "grabbing";
      } else if (self.onHover) {
        const now = performance.now();
        if (now - lastHover < 40) return;
        lastHover = now;
        self.onHover(self.pick(event), event);
      }
    };
    this._up = function (event) {
      if (!dragging) return;
      dragging = false;
      self.dom.style.cursor = "grab";
      if (moved < 6 && self.onClick) self.onClick(self.pick(event), event);
    };
    this._wheel = function (event) {
      event.preventDefault();
      self.goalRadius = Math.min(self.maxRadius, Math.max(self.minRadius, self.goalRadius * Math.exp(event.deltaY * 0.0012)));
      self.lastInteraction = self.time;
    };
    this._leave = function () { if (self.onHover) self.onHover(null, null); };
    this.dom.style.cursor = "grab";
    this.dom.addEventListener("pointerdown", this._down);
    this.dom.addEventListener("pointermove", this._move);
    this.dom.addEventListener("pointerup", this._up);
    this.dom.addEventListener("pointercancel", this._up);
    this.dom.addEventListener("pointerleave", this._leave);
    this.dom.addEventListener("wheel", this._wheel, { passive: false });

    // ----- size + visibility -----
    this.visible = true;
    this.resize = function () {
      const width = Math.max(container.clientWidth, 50), height = Math.max(container.clientHeight, 50);
      self.renderer.setSize(width, height, false);
      self.dom.style.width = width + "px"; self.dom.style.height = height + "px";
      self.camera.aspect = width / height;
      self.camera.updateProjectionMatrix();
    };
    this.resize();
    if (window.ResizeObserver) {
      this._resizeObserver = new ResizeObserver(this.resize);
      this._resizeObserver.observe(container);
    } else {
      window.addEventListener("resize", this.resize);
    }
    if (window.IntersectionObserver) {
      this._io = new IntersectionObserver(function (entries) { self.visible = entries[0].isIntersecting; });
      this._io.observe(container);
    }

    this.clock = new THREE.Clock();
    this.disposed = false;
    this._frame = function () {
      if (self.disposed) return;
      self._raf = requestAnimationFrame(self._frame);
      const dt = Math.min(self.clock.getDelta(), 0.05);
      if (!self.visible || document.hidden) return;
      self.time += dt;
      if (self.autoRotate && self.time - self.lastInteraction > 3.5) self.goalTheta += dt * self.autoSpeed;
      const k = 1 - Math.exp(-dt * 6);
      self.theta += (self.goalTheta - self.theta) * k;
      self.phi += (self.goalPhi - self.phi) * k;
      self.radius += (self.goalRadius - self.radius) * k;
      self.target.lerp(self.goalTarget, k);
      const sinPhi = Math.sin(self.phi);
      self.camera.position.set(
        self.target.x + self.radius * sinPhi * Math.sin(self.theta),
        self.target.y + self.radius * Math.cos(self.phi),
        self.target.z + self.radius * sinPhi * Math.cos(self.theta)
      );
      self.camera.lookAt(self.target);
      if (self.onFrame) self.onFrame(dt, self.time);
      self.renderer.render(self.scene, self.camera);
    };
    this._raf = requestAnimationFrame(this._frame);
  };

  SC.Stage.prototype.pick = function (event) {
    const rect = this.dom.getBoundingClientRect();
    this.pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    this.pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    this.raycaster.setFromCamera(this.pointer, this.camera);
    const hits = this.raycaster.intersectObjects(this.pickables, false);
    return hits.length ? hits[0].object.userData : null;
  };

  SC.Stage.prototype.resetView = function () {
    this.goalTheta = this.home.theta; this.goalPhi = this.home.phi; this.goalRadius = this.home.radius;
    this.lastInteraction = this.time;
  };

  // Screen position (pixels inside the container) of a 3D point, or null if behind the camera.
  SC.Stage.prototype.project = function (vector) {
    const v = vector.clone().project(this.camera);
    if (v.z > 1) return null;
    return { x: (v.x * 0.5 + 0.5) * this.container.clientWidth, y: (-v.y * 0.5 + 0.5) * this.container.clientHeight };
  };

  SC.Stage.prototype.dispose = function () {
    this.disposed = true;
    cancelAnimationFrame(this._raf);
    if (this._resizeObserver) this._resizeObserver.disconnect();
    if (this._io) this._io.disconnect();
    window.removeEventListener("resize", this.resize);
    this.scene.traverse(function (object) {
      if (object.geometry) object.geometry.dispose();
      if (object.material) {
        (Array.isArray(object.material) ? object.material : [object.material]).forEach(function (m) {
          if (m.map && m.map !== glowTexture) m.map.dispose();
          m.dispose();
        });
      }
    });
    this.renderer.dispose();
    if (this.dom.parentNode) this.dom.parentNode.removeChild(this.dom);
  };

  // Remove every child of a THREE.Group and free its GPU resources.
  SC.clearGroup = function (group) {
    while (group.children.length) {
      const child = group.children[0];
      group.remove(child);
      child.traverse(function (object) {
        if (object.geometry) object.geometry.dispose();
        if (object.material) {
          (Array.isArray(object.material) ? object.material : [object.material]).forEach(function (m) {
            if (m.map && m.map !== glowTexture) m.map.dispose();
            m.dispose();
          });
        }
      });
    }
  };

  SC.easeOutBack = function (x) {
    const c1 = 1.70158, c3 = c1 + 1;
    return 1 + c3 * Math.pow(x - 1, 3) + c1 * Math.pow(x - 1, 2);
  };
})();
