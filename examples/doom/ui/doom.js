(function () {
  "use strict";

  var PLUGIN_ID = "doom";

  var astra =
    window.__astraPluginBridge && window.__astraPluginBridge[PLUGIN_ID];
  if (!astra) {
    console.error("[doom] Bridge not found");
    return;
  }

  var root =
    (document.currentScript && document.currentScript.parentElement) ||
    document.querySelector("[data-contribution-id='doom-page']") ||
    document.querySelector("[data-plugin-id='" + PLUGIN_ID + "']");
  if (!root) {
    console.error("[doom] Root container not found");
    return;
  }

  // ── CSS ────────────────────────────────────────────────────────
  var style = document.createElement("style");
  style.textContent =
    ".doom-wrap { width:100%; height:100%; background:#000; display:flex; align-items:center; justify-content:center; position:relative; overflow:hidden; }" +
    ".doom-wrap canvas { image-rendering:pixelated; outline:none; cursor:crosshair; display:block; width:100% !important; height:100% !important; object-fit:contain; }" +
    ".doom-loading { position:absolute; color:#c33; font-family:'Impact',sans-serif; text-transform:uppercase; font-size:32px; letter-spacing:3px; pointer-events:none; z-index:1; }";
  document.head.appendChild(style);

  // ── DOM ────────────────────────────────────────────────────────
  root.innerHTML =
    '<div class="doom-wrap"><div class="doom-loading">Loading DOOM...</div></div>';
  var wrap = root.querySelector(".doom-wrap");
  var loadingEl = root.querySelector(".doom-loading");

  // ── State ──────────────────────────────────────────────────────
  var gameFocused = false;

  // ── Keyboard: preventDefault only (no stopPropagation) ─────────
  // Emscripten SDL needs events to propagate to its own handlers.
  // We only preventDefault to stop Astra hotkeys from firing.
  function onKeyDown(e) {
    if (gameFocused) e.preventDefault();
  }
  function onKeyUp(e) {
    if (gameFocused) e.preventDefault();
  }
  document.addEventListener("keydown", onKeyDown, true);
  document.addEventListener("keyup", onKeyUp, true);

  // ── Prevent Emscripten from requesting fullscreen ──────────────
  var origRequestFullscreen = Element.prototype.requestFullscreen;
  Element.prototype.requestFullscreen = function () {
    return Promise.resolve();
  };

  // ── Base URL ───────────────────────────────────────────────────
  function getBaseUrl() {
    var scripts = document.querySelectorAll("script[src]");
    for (var i = 0; i < scripts.length; i++) {
      var src = scripts[i].getAttribute("src") || "";
      if (src.indexOf(PLUGIN_ID + "/doom.js") !== -1) {
        return src.replace("doom.js", "");
      }
    }
    return "http://astra-plugin.localhost/" + PLUGIN_ID + "/";
  }

  // ── Check if DOOM was already loaded (persisted across tab switches) ──
  var holder = document.getElementById("doom-persist");
  if (holder && holder.querySelector("canvas")) {
    // Restore persisted canvas
    var canvas = holder.querySelector("canvas");
    wrap.appendChild(canvas);
    canvas.focus();
    gameFocused = true;
    loadingEl.style.display = "none";
  } else {
    // ── First load: create canvas and load Emscripten module ─────
    var canvas = document.createElement("canvas");
    canvas.id = "canvas";
    canvas.tabIndex = 0;
    canvas.width = 640;
    canvas.height = 400;
    wrap.appendChild(canvas);

    var base = getBaseUrl();

    window.Module = {
      canvas: canvas,
      print: function (text) {
        console.log("[doom]", text);
      },
      printErr: function (text) {
        console.error("[doom]", text);
      },
      locateFile: function (path) {
        return base + path;
      },
      onRuntimeInitialized: function () {
        loadingEl.style.display = "none";
        canvas.focus();
        gameFocused = true;
      },
    };

    var script = document.createElement("script");
    script.src = base + "chocolate-doom.js";
    script.onerror = function () {
      loadingEl.textContent = "Failed to load DOOM";
    };
    document.head.appendChild(script);

    // Fallback: hide loading after 5s
    setTimeout(function () {
      if (loadingEl) loadingEl.style.display = "none";
      canvas.focus();
      gameFocused = true;
    }, 5000);
  }

  // ── Focus handling ─────────────────────────────────────────────
  wrap.addEventListener("click", function () {
    var c = wrap.querySelector("canvas");
    if (c) { c.focus(); gameFocused = true; }
  });
  wrap.addEventListener("focusin", function () { gameFocused = true; });
  wrap.addEventListener("focusout", function () { gameFocused = false; });

  // ── Cleanup: persist canvas instead of destroying ──────────────
  window.__astraPluginCleanup = window.__astraPluginCleanup || {};
  window.__astraPluginCleanup[PLUGIN_ID] = function () {
    document.removeEventListener("keydown", onKeyDown, true);
    document.removeEventListener("keyup", onKeyUp, true);

    // Restore original requestFullscreen
    if (origRequestFullscreen) {
      Element.prototype.requestFullscreen = origRequestFullscreen;
    }

    // Move canvas to hidden persist holder instead of destroying
    var c = wrap ? wrap.querySelector("canvas") : null;
    if (c) {
      var h = document.getElementById("doom-persist");
      if (!h) {
        h = document.createElement("div");
        h.id = "doom-persist";
        h.style.display = "none";
        document.body.appendChild(h);
      }
      h.appendChild(c);
    }

    if (style.parentNode) style.parentNode.removeChild(style);
    root.innerHTML = "";
    // Do NOT delete window.Module — keep WASM instance alive
  };
})();
