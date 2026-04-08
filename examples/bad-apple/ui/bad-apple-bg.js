// Bad Apple background effect — renders behind the entire Astra UI.
// Uses dom_access for direct DOM injection. Loaded as an "effect" contribution
// (transparent, no pointer events, behind everything).

(function () {
  "use strict";

  var PLUGIN_ID = "bad-apple";
  var astra =
    window.__astraPluginBridge && window.__astraPluginBridge[PLUGIN_ID];
  if (!astra) {
    console.error("[bad-apple-bg] Bridge not found");
    return;
  }

  var root = (document.currentScript && document.currentScript.parentElement) ||
    document.querySelector("[data-contribution-id='bad-apple-bg']") ||
    document.querySelector("[data-plugin-id='" + PLUGIN_ID + "']");
  if (!root) {
    console.error("[bad-apple-bg] Root container not found");
    return;
  }

  // ── CSS ────────────────────────────────────────────────────────
  var style = document.createElement("style");
  style.textContent =
    "#ba-bg-wrap {" +
    "  width: 100%; height: 100%; position: relative;" +
    "  pointer-events: none;" +
    "}";
  document.head.appendChild(style);

  // ── DOM ────────────────────────────────────────────────────────
  root.innerHTML = '<div id="ba-bg-wrap"></div>';
  var wrap = document.getElementById("ba-bg-wrap");

  // ── Load renderer ──────────────────────────────────────────────
  function getBaseUrl() {
    var scripts = document.querySelectorAll("script[src]");
    for (var i = 0; i < scripts.length; i++) {
      var src = scripts[i].getAttribute("src") || "";
      if (src.indexOf(PLUGIN_ID + "/bad-apple-bg.js") !== -1) {
        return src.replace("bad-apple-bg.js", "");
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

  var renderer = null;

  async function init() {
    var base = getBaseUrl();

    try {
      // Load shared renderer
      await loadScript(base + "renderer.js");

      // Get config from backend
      var config = {
        render_mode: "ascii",
        charset: "blocks",
        color: "mono",
        opacity: 0.15,
        loop: true,
      };
      try {
        var cfgResult = await astra.callBackend("getConfig", {});
        if (cfgResult) {
          config.render_mode = cfgResult.render_mode || config.render_mode;
          config.charset = cfgResult.charset || config.charset;
          config.color = cfgResult.color || config.color;
          config.opacity = cfgResult.opacity != null ? cfgResult.opacity : config.opacity;
          config.loop = cfgResult.loop != null ? cfgResult.loop : config.loop;
        }
      } catch (_) {}

      // Apply opacity to container
      wrap.style.opacity = String(config.opacity);

      // Create renderer
      renderer = new window.BadAppleRenderer(wrap, config);

      // Load frames and play
      await renderer.load(base + "frames.bin");
      renderer.play();
    } catch (err) {
      console.warn(
        "[bad-apple-bg] Could not start:",
        err.message || err,
        "— place frames.bin in ui/ directory. See SETUP.md."
      );
    }
  }

  // Hide Threads animation while Bad Apple is active
  var threadsEl = document.querySelector(".threads-container");
  if (threadsEl) threadsEl.style.display = "none";

  init();

  // ── Cleanup ────────────────────────────────────────────────────
  window.__astraPluginCleanup = window.__astraPluginCleanup || {};
  window.__astraPluginCleanup[PLUGIN_ID] = function () {
    if (renderer) renderer.destroy();
    if (style.parentNode) style.parentNode.removeChild(style);
    root.innerHTML = "";
    // Restore Threads animation
    var threads = document.querySelector(".threads-container");
    if (threads) threads.style.display = "";
  };
})();
