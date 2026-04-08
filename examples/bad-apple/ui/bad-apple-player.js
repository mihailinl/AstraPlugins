// Bad Apple player page — full view with playback controls and mode switcher.
// Uses dom_access for direct DOM injection. Loaded as a "page.custom" contribution.

(function () {
  "use strict";

  var PLUGIN_ID = "bad-apple";
  var astra =
    window.__astraPluginBridge && window.__astraPluginBridge[PLUGIN_ID];
  if (!astra) {
    console.error("[bad-apple-player] Bridge not found");
    return;
  }

  var root = (document.currentScript && document.currentScript.parentElement) ||
    document.querySelector("[data-contribution-id='bad-apple-page']") ||
    document.querySelector("[data-plugin-id='" + PLUGIN_ID + "'][style*='relative']");
  if (!root) {
    console.error("[bad-apple-player] Root container not found");
    return;
  }

  // ── CSS ────────────────────────────────────────────────────────
  var style = document.createElement("style");
  style.textContent =
    "#ba-player { width:100%; height:100%; display:flex; flex-direction:column; background:#0a0a0a; color:#ccc; font-family:system-ui,sans-serif; }" +
    "#ba-viewport { flex:1; position:relative; overflow:hidden; display:flex; align-items:center; justify-content:center; }" +
    "#ba-controls { display:flex; align-items:center; gap:12px; padding:10px 16px; background:#111; border-top:1px solid #222; flex-shrink:0; }" +
    "#ba-controls button { background:#222; border:1px solid #333; color:#ccc; padding:6px 14px; border-radius:4px; cursor:pointer; font-size:13px; }" +
    "#ba-controls button:hover { background:#333; }" +
    "#ba-controls button.active { background:#444; border-color:#666; color:#fff; }" +
    "#ba-scrub { flex:1; height:4px; -webkit-appearance:none; appearance:none; background:#333; border-radius:2px; cursor:pointer; }" +
    "#ba-scrub::-webkit-slider-thumb { -webkit-appearance:none; width:12px; height:12px; border-radius:50%; background:#888; cursor:pointer; }" +
    "#ba-frame-num { font-size:11px; color:#666; font-family:monospace; min-width:80px; text-align:right; }" +
    "#ba-mode-bar { display:flex; gap:6px; }" +
    "#ba-color-bar { display:flex; gap:6px; }" +
    "#ba-charset-bar { display:flex; gap:6px; }" +
    "#ba-loading { display:flex; flex-direction:column; align-items:center; justify-content:center; gap:12px; height:100%; color:#666; }" +
    "#ba-loading h2 { margin:0; color:#888; }" +
    "#ba-sep { width:1px; height:20px; background:#333; flex-shrink:0; }";
  document.head.appendChild(style);

  // ── DOM ────────────────────────────────────────────────────────
  root.innerHTML =
    '<div id="ba-player">' +
    '  <div id="ba-viewport">' +
    '    <div id="ba-loading"><h2>Bad Apple!!</h2><p>Loading frames...</p></div>' +
    "  </div>" +
    '  <div id="ba-controls">' +
    '    <button id="ba-play">\u25B6</button>' +
    '    <button id="ba-stop">\u25A0</button>' +
    '    <input type="range" id="ba-scrub" min="0" max="1" value="0" step="1" />' +
    '    <span id="ba-frame-num">0 / 0</span>' +
    '    <div id="ba-sep"></div>' +
    '    <div id="ba-mode-bar">' +
    '      <button data-mode="ascii" class="active">ASCII</button>' +
    '      <button data-mode="crt">CRT</button>' +
    '      <button data-mode="particles">Particles</button>' +
    '      <button data-mode="silhouette">Silhouette</button>' +
    "    </div>" +
    '    <div id="ba-sep"></div>' +
    '    <div id="ba-color-bar">' +
    '      <button data-color="mono" class="active">Mono</button>' +
    '      <button data-color="green">Green</button>' +
    '      <button data-color="amber">Amber</button>' +
    '      <button data-color="accent">Accent</button>' +
    "    </div>" +
    "  </div>" +
    "</div>";

  var viewport = document.getElementById("ba-viewport");
  var loadingDiv = document.getElementById("ba-loading");
  var playBtn = document.getElementById("ba-play");
  var stopBtn = document.getElementById("ba-stop");
  var scrub = document.getElementById("ba-scrub");
  var frameNum = document.getElementById("ba-frame-num");
  var modeBtns = document.querySelectorAll("#ba-mode-bar button");
  var colorBtns = document.querySelectorAll("#ba-color-bar button");

  // ── State ──────────────────────────────────────────────────────
  var renderer = null;
  var audio = null;
  var currentConfig = {
    render_mode: "ascii",
    charset: "blocks",
    color: "mono",
    loop: true,
    opacity: 1.0,
  };
  var isPlaying = false;

  // ── Helpers ────────────────────────────────────────────────────
  function getBaseUrl() {
    var scripts = document.querySelectorAll("script[src]");
    for (var i = 0; i < scripts.length; i++) {
      var src = scripts[i].getAttribute("src") || "";
      if (src.indexOf(PLUGIN_ID + "/bad-apple-player.js") !== -1) {
        return src.replace("bad-apple-player.js", "");
      }
    }
    return "http://astra-plugin.localhost/" + PLUGIN_ID + "/";
  }

  function loadScript(url) {
    return new Promise(function (resolve, reject) {
      if (window.BadAppleRenderer) {
        resolve();
        return;
      }
      var s = document.createElement("script");
      s.src = url;
      s.onload = resolve;
      s.onerror = function () {
        reject(new Error("Failed to load: " + url));
      };
      document.head.appendChild(s);
    });
  }

  function updateActiveBtn(btns, attr, value) {
    for (var i = 0; i < btns.length; i++) {
      var btn = btns[i];
      if (btn.getAttribute("data-" + attr) === value) {
        btn.classList.add("active");
      } else {
        btn.classList.remove("active");
      }
    }
  }

  function updateFrameDisplay() {
    if (!renderer) return;
    var current = renderer.getCurrentFrame();
    var total = renderer.getFrameCount();
    frameNum.textContent = current + " / " + total;
    scrub.value = current;
  }

  // ── Init ───────────────────────────────────────────────────────
  async function init() {
    var base = getBaseUrl();

    try {
      await loadScript(base + "renderer.js");

      // Get config from backend
      try {
        var cfgResult = await astra.callBackend("getConfig", {});
        if (cfgResult) {
          currentConfig.render_mode =
            cfgResult.render_mode || currentConfig.render_mode;
          currentConfig.charset = cfgResult.charset || currentConfig.charset;
          currentConfig.color = cfgResult.color || currentConfig.color;
          currentConfig.loop =
            cfgResult.loop != null ? cfgResult.loop : currentConfig.loop;
        }
      } catch (_) {}

      // Build renderer in viewport
      loadingDiv.style.display = "none";

      var renderContainer = document.createElement("div");
      renderContainer.style.cssText =
        "width:100%;height:100%;position:relative;";
      viewport.appendChild(renderContainer);

      currentConfig.onFrame = updateFrameDisplay;
      currentConfig.onEnd = function () {
        isPlaying = false;
        playBtn.textContent = "\u25B6";
      };

      renderer = new window.BadAppleRenderer(renderContainer, currentConfig);
      await renderer.load(base + "frames.bin");

      scrub.max = renderer.getFrameCount() - 1;
      updateFrameDisplay();
      updateActiveBtn(modeBtns, "mode", currentConfig.render_mode);
      updateActiveBtn(colorBtns, "color", currentConfig.color);

      // Try loading audio (optional — works without it)
      // Reuse existing audio element if page remounts
      audio = document.getElementById("ba-audio");
      if (!audio) {
        audio = document.createElement("audio");
        audio.id = "ba-audio";
        audio.preload = "auto";
        audio.volume = 0.7;
        root.appendChild(audio);
      }
      audio.src = base + "bad-apple.mp3";
      audio.loop = currentConfig.loop;

      // Auto-play
      renderer.play();
      try { audio.play().catch(function () {}); } catch (_) {}
      isPlaying = true;
      playBtn.textContent = "\u23F8";
    } catch (err) {
      loadingDiv.innerHTML =
        "<h2>Bad Apple!!</h2><p style='color:#c33'>Could not load: " +
        (err.message || err) +
        "</p><p>Place frames.bin in the ui/ directory. See SETUP.md.</p>";
    }
  }

  // ── Controls ───────────────────────────────────────────────────
  playBtn.addEventListener("click", function () {
    if (!renderer) return;
    if (isPlaying) {
      renderer.pause();
      if (audio) audio.pause();
      isPlaying = false;
      playBtn.textContent = "\u25B6";
    } else {
      renderer.play();
      if (audio) audio.play().catch(function () {});
      isPlaying = true;
      playBtn.textContent = "\u23F8";
    }
  });

  stopBtn.addEventListener("click", function () {
    if (!renderer) return;
    renderer.stop();
    if (audio) { audio.pause(); audio.currentTime = 0; }
    isPlaying = false;
    playBtn.textContent = "\u25B6";
    updateFrameDisplay();
  });

  scrub.addEventListener("input", function () {
    if (!renderer) return;
    var frame = parseInt(scrub.value, 10);
    renderer.seek(frame);
    if (audio) audio.currentTime = frame / 30;
    updateFrameDisplay();
  });

  // Mode buttons
  for (var i = 0; i < modeBtns.length; i++) {
    modeBtns[i].addEventListener("click", function () {
      var mode = this.getAttribute("data-mode");
      currentConfig.render_mode = mode;
      updateActiveBtn(modeBtns, "mode", mode);
      if (renderer) renderer.setConfig(currentConfig);
    });
  }

  // Color buttons
  for (var j = 0; j < colorBtns.length; j++) {
    colorBtns[j].addEventListener("click", function () {
      var color = this.getAttribute("data-color");
      currentConfig.color = color;
      updateActiveBtn(colorBtns, "color", color);
      if (renderer) renderer.setConfig(currentConfig);
    });
  }

  init();

  // ── Cleanup ────────────────────────────────────────────────────
  window.__astraPluginCleanup = window.__astraPluginCleanup || {};
  var prevCleanup = window.__astraPluginCleanup[PLUGIN_ID];
  window.__astraPluginCleanup[PLUGIN_ID] = function () {
    if (audio) { audio.pause(); audio.src = ""; }
    if (renderer) renderer.destroy();
    if (style.parentNode) style.parentNode.removeChild(style);
    root.innerHTML = "";
    // Chain previous cleanup (background effect)
    if (prevCleanup) prevCleanup();
  };
})();
