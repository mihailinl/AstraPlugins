// Bad Apple Renderer — shared rendering core for all display modes.
// Loaded by both bad-apple-bg.js and bad-apple-player.js.
//
// Binary frame format (frames.bin):
//   Header: 4 bytes frameCount (LE u32) + 2 bytes width (LE u16) + 2 bytes height (LE u16)
//   Per frame: 4 bytes dataLen (LE u32) + dataLen bytes RLE data
//   RLE: each pair [count, value] where value is 0 (black) or 255 (white)
//
// Usage:
//   var renderer = new BadAppleRenderer(container, config);
//   renderer.load(baseUrl + "frames.bin").then(() => renderer.play());

(function () {
  "use strict";

  // ── Character sets ─────────────────────────────────────────────
  var CHARSETS = {
    blocks: [" ", "\u2591", "\u2592", "\u2593", "\u2588"],
    classic: [" ", ".", ":", "-", "=", "+", "*", "#", "%", "@"],
    braille: null, // special handling
    katakana: null, // special handling
  };

  var KATAKANA =
    "\u30A2\u30A4\u30A6\u30A8\u30AA\u30AB\u30AD\u30AF\u30B1\u30B3" +
    "\u30B5\u30B7\u30B9\u30BB\u30BD\u30BF\u30C1\u30C4\u30C6\u30C8" +
    "\u30CA\u30CB\u30CC\u30CD\u30CE\u30CF\u30D2\u30D5\u30D8\u30DB" +
    "\u30DE\u30DF\u30E0\u30E1\u30E2\u30E4\u30E6\u30E8\u30E9\u30EA" +
    "\u30EB\u30EC\u30ED\u30EF\u30F2\u30F3";

  var COLOR_MAP = {
    mono: "#ffffff",
    green: "#33ff33",
    amber: "#ffaa00",
    accent: null, // resolved from CSS vars
  };

  // ── Frame decoder ──────────────────────────────────────────────
  function decodeFrames(buffer) {
    var view = new DataView(buffer);
    var frameCount = view.getUint32(0, true);
    var width = view.getUint16(4, true);
    var height = view.getUint16(6, true);
    var offset = 8;
    var frames = new Array(frameCount);

    for (var i = 0; i < frameCount; i++) {
      var dataLen = view.getUint32(offset, true);
      offset += 4;
      var pixels = new Uint8Array(width * height);
      var p = 0;
      var end = offset + dataLen;
      while (offset < end) {
        var count = view.getUint8(offset++);
        var value = view.getUint8(offset++);
        for (var j = 0; j < count && p < pixels.length; j++) {
          pixels[p++] = value;
        }
      }
      frames[i] = pixels;
    }

    return { frames: frames, width: width, height: height };
  }

  // ── Braille encoder (2x4 dot matrix per character) ─────────────
  // Braille pattern: dots are numbered 1-8:
  //   1 4
  //   2 5
  //   3 6
  //   7 8
  // Codepoint = 0x2800 + dot bitmask
  var BRAILLE_DOT_MAP = [
    [0, 0, 0x01],
    [0, 1, 0x02],
    [0, 2, 0x04],
    [1, 0, 0x08],
    [1, 1, 0x10],
    [1, 2, 0x20],
    [0, 3, 0x40],
    [1, 3, 0x80],
  ];

  function pixelsToBraille(pixels, pw, ph) {
    var cols = Math.floor(pw / 2);
    var rows = Math.floor(ph / 4);
    var out = new Array(rows);

    for (var r = 0; r < rows; r++) {
      var line = "";
      for (var c = 0; c < cols; c++) {
        var code = 0;
        for (var d = 0; d < 8; d++) {
          var dx = BRAILLE_DOT_MAP[d][0];
          var dy = BRAILLE_DOT_MAP[d][1];
          var bit = BRAILLE_DOT_MAP[d][2];
          var px = c * 2 + dx;
          var py = r * 4 + dy;
          if (px < pw && py < ph && pixels[py * pw + px] > 127) {
            code |= bit;
          }
        }
        line += String.fromCharCode(0x2800 + code);
      }
      out[r] = line;
    }
    return out;
  }

  // ── Renderer class ─────────────────────────────────────────────
  function BadAppleRenderer(container, config) {
    this.container = container;
    this.config = Object.assign(
      {
        render_mode: "ascii",
        charset: "blocks",
        color: "mono",
        loop: true,
        opacity: 1.0,
        onFrame: null,
        onEnd: null,
      },
      config
    );

    this.data = null; // { frames, width, height }
    this.frame = 0;
    this.playing = false;
    this.lastFrameTime = 0;
    this.animId = null;
    this.FRAME_MS = 1000 / 30;

    // Rendering elements
    this.pre = null;
    this.canvas = null;
    this.ctx = null;
    this.particleCanvas = null;
    this.particleCtx = null;
    this.particles = [];

    this._buildDom();
  }

  BadAppleRenderer.prototype._buildDom = function () {
    this.container.innerHTML = "";
    this.container.style.overflow = "hidden";

    // ASCII mode uses <pre>
    this.pre = document.createElement("pre");
    this.pre.style.cssText =
      "margin:0;padding:0;line-height:1;font-size:8px;font-family:'Courier New',monospace;" +
      "letter-spacing:0;white-space:pre;overflow:hidden;width:100%;height:100%;" +
      "display:flex;align-items:center;justify-content:center;";
    this.pre.style.display = "none";
    this.container.appendChild(this.pre);

    // Canvas modes
    this.canvas = document.createElement("canvas");
    this.canvas.style.cssText =
      "width:100%;height:100%;object-fit:contain;image-rendering:pixelated;display:none;";
    this.container.appendChild(this.canvas);
    this.ctx = this.canvas.getContext("2d");

    // Particle overlay canvas
    this.particleCanvas = document.createElement("canvas");
    this.particleCanvas.style.cssText =
      "position:absolute;inset:0;width:100%;height:100%;display:none;";
    this.container.appendChild(this.particleCanvas);
    this.particleCtx = this.particleCanvas.getContext("2d");
  };

  BadAppleRenderer.prototype.load = async function (url) {
    var response = await fetch(url);
    if (!response.ok) throw new Error("Failed to load frames: " + response.status);
    var buffer = await response.arrayBuffer();
    this.data = decodeFrames(buffer);
    this.canvas.width = this.data.width;
    this.canvas.height = this.data.height;
    this.frame = 0;
  };

  BadAppleRenderer.prototype._resolveColor = function () {
    if (this.config.color === "accent") {
      var vars = window.__astraPluginBridge;
      var pluginBridge =
        vars && (vars["bad-apple"] || vars[Object.keys(vars)[0]]);
      if (pluginBridge && pluginBridge.getCssVariables) {
        var cssVars = pluginBridge.getCssVariables();
        return cssVars["--color-accent"] || "#7c6cff";
      }
      return "#7c6cff";
    }
    return COLOR_MAP[this.config.color] || "#ffffff";
  };

  BadAppleRenderer.prototype.play = function () {
    if (!this.data || this.playing) return;
    this.playing = true;
    this.lastFrameTime = performance.now();
    this._setupMode();
    this._tick();
  };

  BadAppleRenderer.prototype.pause = function () {
    this.playing = false;
    if (this.animId) {
      cancelAnimationFrame(this.animId);
      this.animId = null;
    }
  };

  BadAppleRenderer.prototype.stop = function () {
    this.pause();
    this.frame = 0;
  };

  BadAppleRenderer.prototype.seek = function (frameNum) {
    this.frame = Math.max(
      0,
      Math.min(frameNum, this.data ? this.data.frames.length - 1 : 0)
    );
    if (!this.playing) this._renderFrame();
  };

  BadAppleRenderer.prototype.setConfig = function (newConfig) {
    var modeChanged = newConfig.render_mode !== this.config.render_mode;
    var charsetChanged = newConfig.charset !== this.config.charset;
    Object.assign(this.config, newConfig);
    if (modeChanged || charsetChanged) this._setupMode();
  };

  BadAppleRenderer.prototype.getFrameCount = function () {
    return this.data ? this.data.frames.length : 0;
  };

  BadAppleRenderer.prototype.getCurrentFrame = function () {
    return this.frame;
  };

  BadAppleRenderer.prototype._setupMode = function () {
    var mode = this.config.render_mode;
    this.pre.style.display = mode === "ascii" ? "flex" : "none";
    this.canvas.style.display =
      mode === "crt" || mode === "silhouette" ? "block" : "none";
    this.particleCanvas.style.display = mode === "particles" ? "block" : "none";
    if (mode === "particles") {
      this.particles = [];
      this.particleCanvas.width = this.container.clientWidth || 640;
      this.particleCanvas.height = this.container.clientHeight || 480;
    }
  };

  BadAppleRenderer.prototype._tick = function () {
    if (!this.playing) return;
    var self = this;
    this.animId = requestAnimationFrame(function (now) {
      if (now - self.lastFrameTime >= self.FRAME_MS) {
        self.lastFrameTime = now;
        self._renderFrame();
        self.frame++;

        if (self.frame >= self.data.frames.length) {
          if (self.config.loop) {
            self.frame = 0;
          } else {
            self.playing = false;
            if (self.config.onEnd) self.config.onEnd();
            return;
          }
        }
        if (self.config.onFrame) self.config.onFrame(self.frame);
      }
      self._tick();
    });
  };

  BadAppleRenderer.prototype._renderFrame = function () {
    if (!this.data) return;
    var pixels = this.data.frames[this.frame];
    var w = this.data.width;
    var h = this.data.height;

    switch (this.config.render_mode) {
      case "ascii":
        this._renderAscii(pixels, w, h);
        break;
      case "crt":
        this._renderCrt(pixels, w, h);
        break;
      case "particles":
        this._renderParticles(pixels, w, h);
        break;
      case "silhouette":
        this._renderSilhouette(pixels, w, h);
        break;
    }
  };

  // ── ASCII renderer ─────────────────────────────────────────────
  BadAppleRenderer.prototype._renderAscii = function (pixels, w, h) {
    var charset = this.config.charset;
    var color = this._resolveColor();
    this.pre.style.color = color;

    if (charset === "braille") {
      var lines = pixelsToBraille(pixels, w, h);
      this.pre.textContent = lines.join("\n");
      return;
    }

    if (charset === "katakana") {
      var text = "";
      for (var y = 0; y < h; y++) {
        for (var x = 0; x < w; x++) {
          var v = pixels[y * w + x];
          if (v > 127) {
            text += KATAKANA[Math.floor(Math.random() * KATAKANA.length)];
          } else {
            text += " ";
          }
        }
        text += "\n";
      }
      this.pre.textContent = text;
      return;
    }

    // blocks or classic
    var chars = CHARSETS[charset] || CHARSETS.blocks;
    var maxIdx = chars.length - 1;
    var text2 = "";
    for (var y2 = 0; y2 < h; y2++) {
      for (var x2 = 0; x2 < w; x2++) {
        var brightness = pixels[y2 * w + x2] / 255;
        var idx = Math.round(brightness * maxIdx);
        text2 += chars[idx];
      }
      text2 += "\n";
    }
    this.pre.textContent = text2;
  };

  // ── CRT renderer ───────────────────────────────────────────────
  BadAppleRenderer.prototype._renderCrt = function (pixels, w, h) {
    var ctx = this.ctx;
    var color = this._resolveColor();

    // Parse color for tinting
    var r = 255,
      g = 255,
      b = 255;
    if (color.charAt(0) === "#" && color.length === 7) {
      r = parseInt(color.substr(1, 2), 16);
      g = parseInt(color.substr(3, 2), 16);
      b = parseInt(color.substr(5, 2), 16);
    }

    // Draw base frame
    var imageData = ctx.createImageData(w, h);
    var data = imageData.data;
    for (var i = 0; i < pixels.length; i++) {
      var v = pixels[i] / 255;
      data[i * 4] = Math.round(v * r);
      data[i * 4 + 1] = Math.round(v * g);
      data[i * 4 + 2] = Math.round(v * b);
      data[i * 4 + 3] = 255;
    }
    ctx.putImageData(imageData, 0, 0);

    // Scanlines
    ctx.fillStyle = "rgba(0,0,0,0.15)";
    for (var y = 0; y < h; y += 2) {
      ctx.fillRect(0, y, w, 1);
    }

    // VHS jitter — random horizontal offset for a few scanlines
    var jitterLines = 3;
    for (var j = 0; j < jitterLines; j++) {
      var jy = Math.floor(Math.random() * h);
      var shift = Math.floor(Math.random() * 5) - 2;
      if (shift !== 0) {
        var scanline = ctx.getImageData(0, jy, w, 1);
        ctx.putImageData(scanline, shift, jy);
      }
    }

    // Phosphor glow (slight brightness on bright pixels via composite)
    ctx.globalCompositeOperation = "lighter";
    ctx.globalAlpha = 0.05;
    ctx.drawImage(this.canvas, 1, 0);
    ctx.drawImage(this.canvas, -1, 0);
    ctx.globalAlpha = 1.0;
    ctx.globalCompositeOperation = "source-over";
  };

  // ── Particle renderer ──────────────────────────────────────────
  BadAppleRenderer.prototype._renderParticles = function (pixels, w, h) {
    var pCtx = this.particleCtx;
    var pw = this.particleCanvas.width;
    var ph = this.particleCanvas.height;
    var color = this._resolveColor();
    var scaleX = pw / w;
    var scaleY = ph / h;

    // Fade previous frame
    pCtx.fillStyle = "rgba(0,0,0,0.15)";
    pCtx.fillRect(0, 0, pw, ph);

    // Spawn new particles from white pixels (sample to avoid too many)
    var sampleStep = Math.max(1, Math.floor(w * h / 800));
    for (var i = 0; i < pixels.length; i += sampleStep) {
      if (pixels[i] > 127) {
        var x = (i % w) * scaleX;
        var y = Math.floor(i / w) * scaleY;
        this.particles.push({
          x: x + (Math.random() - 0.5) * scaleX,
          y: y + (Math.random() - 0.5) * scaleY,
          vx: (Math.random() - 0.5) * 1.5,
          vy: (Math.random() - 0.5) * 1.5,
          life: 1.0,
          decay: 0.02 + Math.random() * 0.03,
        });
      }
    }

    // Cap particle count
    if (this.particles.length > 5000) {
      this.particles = this.particles.slice(-5000);
    }

    // Update and draw particles
    pCtx.fillStyle = color;
    var alive = [];
    for (var p = 0; p < this.particles.length; p++) {
      var pt = this.particles[p];
      pt.x += pt.vx;
      pt.y += pt.vy;
      pt.life -= pt.decay;
      if (pt.life > 0) {
        pCtx.globalAlpha = pt.life;
        pCtx.fillRect(pt.x, pt.y, 2, 2);
        alive.push(pt);
      }
    }
    pCtx.globalAlpha = 1.0;
    this.particles = alive;
  };

  // ── Silhouette renderer ────────────────────────────────────────
  BadAppleRenderer.prototype._renderSilhouette = function (pixels, w, h) {
    var ctx = this.ctx;
    var color = this._resolveColor();

    var r = 255,
      g = 255,
      b = 255;
    if (color.charAt(0) === "#" && color.length === 7) {
      r = parseInt(color.substr(1, 2), 16);
      g = parseInt(color.substr(3, 2), 16);
      b = parseInt(color.substr(5, 2), 16);
    }

    var imageData = ctx.createImageData(w, h);
    var data = imageData.data;
    for (var i = 0; i < pixels.length; i++) {
      var v = pixels[i] > 127 ? 1 : 0;
      data[i * 4] = v * r;
      data[i * 4 + 1] = v * g;
      data[i * 4 + 2] = v * b;
      data[i * 4 + 3] = 255;
    }
    ctx.putImageData(imageData, 0, 0);

    // Subtle glow
    ctx.globalCompositeOperation = "lighter";
    ctx.globalAlpha = 0.08;
    ctx.filter = "blur(2px)";
    ctx.drawImage(this.canvas, 0, 0);
    ctx.filter = "none";
    ctx.globalAlpha = 1.0;
    ctx.globalCompositeOperation = "source-over";
  };

  BadAppleRenderer.prototype.destroy = function () {
    this.stop();
    this.container.innerHTML = "";
    this.particles = [];
    this.data = null;
  };

  // Export
  window.BadAppleRenderer = BadAppleRenderer;
})();
