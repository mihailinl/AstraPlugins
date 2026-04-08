/**
 * Companion Cat — DOM plugin version
 * Runs directly in the Astra app document (dom_access = true).
 * Grabs REAL UI elements when user is AFK.
 */
(function () {
  "use strict";

  // Prevent double initialization (React strict mode)
  if (window.__companionCatActive) return;
  window.__companionCatActive = true;

  var astra = window.__astraPluginBridge && window.__astraPluginBridge["companion-cat"];
  if (!astra) { console.error("[companion-cat] Bridge not found"); return; }

  var root = (document.currentScript && document.currentScript.parentElement) ||
    document.querySelector("[data-contribution-id='cat-overlay']") ||
    document.querySelector("[data-plugin-id='companion-cat']");
  if (!root) { console.error("[companion-cat] Root container not found"); return; }

  // ── Inject CSS ──
  var style = document.createElement("style");
  style.dataset.pluginId = "companion-cat";
  style.textContent = `
    .cc-container {
      position: fixed;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 4px;
      cursor: pointer;
      user-select: none;
      pointer-events: auto;
      z-index: 10001;
    }
    .cc-bubble {
      background: var(--color-surface, #1a1a1a);
      color: var(--color-text, #e5e5e5);
      border: 1px solid var(--color-border, rgba(255,255,255,0.15));
      border-radius: 10px;
      padding: 6px 10px;
      font-size: 11px;
      font-family: var(--font-sans, "Segoe UI", sans-serif);
      max-width: 160px;
      text-align: center;
      position: relative;
      opacity: 0;
      transform: translateY(4px);
      transition: opacity 0.3s, transform 0.3s;
      pointer-events: none;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .cc-bubble.visible { opacity: 1; transform: translateY(0); }
    .cc-bubble::after {
      content: "";
      position: absolute;
      bottom: -6px; left: 50%;
      transform: translateX(-50%);
      width: 0; height: 0;
      border-left: 6px solid transparent;
      border-right: 6px solid transparent;
      border-top: 6px solid var(--color-surface, #1a1a1a);
    }
    .cc-cat {
      width: 60px; height: 50px;
      position: relative;
      animation: cc-float 3s ease-in-out infinite;
    }
    .cc-body {
      width: 44px; height: 32px;
      background: #555;
      border-radius: 50% 50% 45% 45%;
      position: absolute; bottom: 0; left: 50%;
      transform: translateX(-50%);
    }
    .cc-head {
      width: 34px; height: 28px;
      background: #555;
      border-radius: 50% 50% 40% 40%;
      position: absolute; top: 0; left: 50%;
      transform: translateX(-50%);
    }
    .cc-ear {
      width: 0; height: 0;
      border-left: 7px solid transparent;
      border-right: 7px solid transparent;
      border-bottom: 12px solid #555;
      position: absolute; top: -6px;
    }
    .cc-ear--left { left: 2px; transform: rotate(-15deg); }
    .cc-ear--right { right: 2px; transform: rotate(15deg); }
    .cc-ear-inner {
      width: 0; height: 0;
      border-left: 4px solid transparent;
      border-right: 4px solid transparent;
      border-bottom: 8px solid #d4a0a0;
      position: absolute; top: 2px; left: -2px;
    }
    .cc-eyes {
      position: absolute; top: 10px; left: 50%;
      transform: translateX(-50%);
      display: flex; gap: 8px;
    }
    .cc-eye {
      width: 6px; height: 7px;
      background: #2dd;
      border-radius: 50%;
      position: relative;
      animation: cc-blink 4s infinite;
    }
    .cc-eye::after {
      content: "";
      width: 3px; height: 5px;
      background: #111; border-radius: 50%;
      position: absolute; top: 1px; left: 1.5px;
    }
    .cc-nose {
      width: 4px; height: 3px;
      background: #d4a0a0; border-radius: 50%;
      position: absolute; top: 18px; left: 50%;
      transform: translateX(-50%);
    }
    .cc-mouth {
      position: absolute; top: 20px; left: 50%;
      transform: translateX(-50%);
      width: 10px; height: 4px;
    }
    .cc-mouth::before, .cc-mouth::after {
      content: ""; position: absolute; top: 0;
      width: 6px; height: 4px;
      border-bottom: 1.5px solid #888;
      border-radius: 0 0 50% 50%;
    }
    .cc-mouth::before { left: 0; }
    .cc-mouth::after { right: 0; }
    .cc-tail {
      width: 30px; height: 20px;
      border: 3px solid #555;
      border-color: transparent transparent #555 transparent;
      border-radius: 0 0 50% 50%;
      position: absolute; bottom: 5px; right: -12px;
      animation: cc-wag 2s ease-in-out infinite;
      transform-origin: left center;
    }
    .cc-zzz {
      position: absolute; top: -8px; right: -4px;
      font-size: 10px; opacity: 0; pointer-events: none;
    }
    @keyframes cc-float {
      0%, 100% { transform: translateY(0); }
      50% { transform: translateY(-6px); }
    }
    @keyframes cc-wag {
      0%, 100% { transform: rotate(-10deg); }
      50% { transform: rotate(10deg); }
    }
    @keyframes cc-blink {
      0%, 95%, 100% { transform: scaleY(1); }
      97% { transform: scaleY(0.1); }
    }
    .cc-container:hover .cc-body {
      animation: cc-purr 0.15s ease-in-out infinite alternate;
    }
    @keyframes cc-purr {
      from { transform: translateX(-50%) scale(1); }
      to { transform: translateX(-50%) scale(1.04); }
    }
    .cc-container.clicked .cc-cat { animation: cc-bounce 0.4s ease; }
    @keyframes cc-bounce {
      0% { transform: translateY(0); }
      30% { transform: translateY(-18px) scaleX(0.9) scaleY(1.1); }
      50% { transform: translateY(-12px); }
      70% { transform: translateY(-4px) scaleX(1.05) scaleY(0.95); }
      100% { transform: translateY(0); }
    }
    .cc-container.sleeping .cc-eye { animation: none; transform: scaleY(0.1); }
    .cc-container.sleeping .cc-cat { animation: cc-float-slow 5s ease-in-out infinite; }
    @keyframes cc-float-slow {
      0%, 100% { transform: translateY(0); }
      50% { transform: translateY(-3px); }
    }
    .cc-container.sleeping .cc-zzz { animation: cc-zzz 2.5s ease-in-out infinite; }
    @keyframes cc-zzz {
      0% { opacity: 0; transform: translate(0,0) scale(0.8); }
      30% { opacity: 1; }
      100% { opacity: 0; transform: translate(8px,-16px) scale(1.2); }
    }
    .cc-container.stretching .cc-body { animation: cc-stretch 1.2s ease-in-out; }
    @keyframes cc-stretch {
      0% { transform: translateX(-50%) scaleX(1) scaleY(1); }
      40% { transform: translateX(-50%) scaleX(1.25) scaleY(0.8); }
      70% { transform: translateX(-50%) scaleX(0.9) scaleY(1.1); }
      100% { transform: translateX(-50%) scaleX(1) scaleY(1); }
    }
    .cc-container.stretching .cc-tail { animation: cc-tail-stretch 1.2s ease-in-out; }
    @keyframes cc-tail-stretch {
      0% { transform: rotate(-10deg); }
      50% { transform: rotate(25deg); }
      100% { transform: rotate(-10deg); }
    }
    .cc-container.carrying .cc-head { transform: translateX(-50%) rotate(-8deg); }
    .cc-container.carrying .cc-tail { animation: cc-wag-fast 0.6s ease-in-out infinite; }
    @keyframes cc-wag-fast {
      0%, 100% { transform: rotate(-15deg); }
      50% { transform: rotate(20deg); }
    }
    .cc-container.startled .cc-cat { animation: cc-startled 0.5s ease; }
    @keyframes cc-startled {
      0% { transform: translateY(0) scale(1); }
      20% { transform: translateY(-12px) scale(1.15); }
      40% { transform: translateY(-8px) scaleX(0.85) scaleY(1.1); }
      100% { transform: translateY(0) scale(1); }
    }
    .cc-container.startled .cc-eye {
      animation: none !important;
      width: 8px; height: 9px;
      transition: all 0.1s;
    }
    .cc-clone {
      position: fixed !important;
      z-index: 10000;
      pointer-events: none;
      margin: 0 !important;
    }
  `;
  document.head.appendChild(style);

  // ── Build cat DOM ──
  var container = document.createElement("div");
  container.className = "cc-container";
  container.innerHTML =
    '<div class="cc-bubble"></div>' +
    '<div class="cc-cat">' +
      '<div class="cc-head">' +
        '<div class="cc-ear cc-ear--left"><div class="cc-ear-inner"></div></div>' +
        '<div class="cc-ear cc-ear--right"><div class="cc-ear-inner"></div></div>' +
        '<div class="cc-eyes"><div class="cc-eye"></div><div class="cc-eye"></div></div>' +
        '<div class="cc-nose"></div>' +
        '<div class="cc-mouth"></div>' +
      '</div>' +
      '<div class="cc-body"></div>' +
      '<div class="cc-tail"></div>' +
      '<div class="cc-zzz">z</div>' +
    '</div>';
  root.appendChild(container);

  var bubble = container.querySelector(".cc-bubble");
  var bubbleTimeout;
  var sleeping = false;

  // ── Messages ──
  function showMessage(text) {
    if (text) {
      bubble.textContent = text;
    } else {
      if (sleeping) return;
      astra.callBackend("getRandomMessage", {}).then(function (result) {
        if (result && result.message) {
          bubble.textContent = result.message;
          bubble.classList.add("visible");
          clearTimeout(bubbleTimeout);
          bubbleTimeout = setTimeout(function () { bubble.classList.remove("visible"); }, 3500);
        }
      }).catch(function () {});
      return;
    }
    bubble.classList.add("visible");
    clearTimeout(bubbleTimeout);
    bubbleTimeout = setTimeout(function () { bubble.classList.remove("visible"); }, 3500);
  }

  // ═══════════════════════════════════
  // ── JS-based animation system ──
  // ═══════════════════════════════════
  var catX = window.innerWidth - 110;
  var catY = window.innerHeight - 90;
  container.style.left = catX + "px";
  container.style.top = catY + "px";
  var flyRaf = null;
  var flyAborted = false;

  function easeInOut(t) {
    return t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;
  }

  function flyTo(tx, ty, duration) {
    duration = duration || 2000;
    return new Promise(function (resolve) {
      if (flyRaf) { cancelAnimationFrame(flyRaf); flyRaf = null; }
      var sx = catX, sy = catY;
      var start = performance.now();

      function frame(now) {
        var t = Math.min((now - start) / duration, 1);
        var e = easeInOut(t);
        catX = sx + (tx - sx) * e;
        catY = sy + (ty - sy) * e;
        container.style.left = catX + "px";
        container.style.top = catY + "px";

        // Stick carried clone to cat
        if (mischief.carrying) {
          mischief.carrying.clone.style.left = (catX + 20) + "px";
          mischief.carrying.clone.style.top = (catY + 55) + "px";
        }

        if (t < 1 && !flyAborted) {
          flyRaf = requestAnimationFrame(frame);
        } else {
          flyRaf = null;
          resolve();
        }
      }
      flyRaf = requestAnimationFrame(frame);
    });
  }

  function moveCatStep() {
    if (sleeping || mischief.active) return;
    var maxX = window.innerWidth - 100;
    var maxY = window.innerHeight - 100;
    var nx = Math.max(20, Math.min(maxX, catX + (Math.random() - 0.5) * 300));
    var ny = Math.max(40, Math.min(maxY, catY + (Math.random() - 0.5) * 200));
    flyTo(nx, ny, 2000);
  }

  // ── Click ──
  container.addEventListener("click", function (e) {
    e.stopPropagation();
    resetAfk();
    if (mischief.active) { stopMischief(); return; }
    if (sleeping) { wakeUp(); return; }
    container.classList.add("clicked");
    setTimeout(function () { container.classList.remove("clicked"); }, 400);
    showMessage();
  });

  // ── Stretch ──
  function doStretch() {
    if (sleeping || mischief.active) return;
    container.classList.add("stretching");
    setTimeout(function () { container.classList.remove("stretching"); }, 1200);
  }

  // ── Sleep ──
  function fallAsleep() {
    if (mischief.active) return;
    sleeping = true;
    showMessage("\u{1F4A4}");
    container.classList.add("sleeping");
  }
  function wakeUp() {
    sleeping = false;
    container.classList.remove("sleeping");
    bubble.classList.remove("visible");
    setTimeout(function () { showMessage(); }, 300);
  }

  // ═══════════════════════════════════════════
  // ── AFK Detection & Real Element Grabbing ──
  // ═══════════════════════════════════════════
  var AFK_DELAY = 20000;
  var afkTimer = null;

  var MISCHIEF_MESSAGES = [
    "Ooh, what's this?", "Mine now!", "Hehe~",
    "This looks fun to move", "Nobody's watching...",
    "*grabs*", "I'm redecorating!", "This goes over here now",
  ];

  var mischief = {
    active: false,
    grabbed: [],    // { original, clone, origRect }
    carrying: null, // current { original, clone, origRect }
  };

  function resetAfk() {
    clearTimeout(afkTimer);
    if (mischief.active) stopMischief();
    afkTimer = setTimeout(startMischief, AFK_DELAY);
  }

  // ── Focus detection — direct window events ──
  window.addEventListener("focus", function () {
    if (mischief.active) resetAfk();
  });
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden && mischief.active) resetAfk();
  });
  var mouseMoveThrottle = 0;
  document.addEventListener("mousemove", function () {
    var now = Date.now();
    if (now - mouseMoveThrottle < 2000) return;
    mouseMoveThrottle = now;
    if (mischief.active) resetAfk();
  });

  // ── Is this element a standalone UI component? ──
  function isComponent(el) {
    var tag = el.tagName;
    // Interactive elements are always components
    if (tag === "BUTTON" || tag === "A" || tag === "INPUT" ||
        tag === "SELECT" || tag === "TEXTAREA" || tag === "IMG") return true;
    // Role-based components
    var role = el.getAttribute && el.getAttribute("role");
    if (role === "button" || role === "switch" || role === "checkbox" ||
        role === "tab" || role === "menuitem" || role === "option" ||
        role === "listitem") return true;
    // Styled elements (have visible background, border, shadow, or radius)
    if (el.className && typeof el.className === "string" && el.className.trim()) {
      var cs = getComputedStyle(el);
      var hasBg = cs.backgroundColor !== "rgba(0, 0, 0, 0)" && cs.backgroundColor !== "transparent";
      var hasBorder = parseFloat(cs.borderWidth) > 0 && cs.borderStyle !== "none";
      var hasShadow = cs.boxShadow !== "none" && cs.boxShadow !== "";
      var hasRadius = parseFloat(cs.borderRadius) > 0;
      if (hasBg || hasBorder || hasShadow || hasRadius) return true;
    }
    return false;
  }

  // ── Walk up from an element to find the nearest component boundary ──
  function findComponentBoundary(el) {
    var current = el;
    var best = null;
    while (current && current !== document.body && current !== document.documentElement) {
      if (isComponent(current)) best = current;
      // Stop walking up if we hit a large container (likely a page section)
      if (best) {
        var parentRect = current.parentElement ? current.parentElement.getBoundingClientRect() : null;
        if (parentRect && (parentRect.width > 600 || parentRect.height > 300)) break;
        // If parent is also a component and not much bigger, keep walking up
        if (current.parentElement && isComponent(current.parentElement)) {
          var pRect = current.parentElement.getBoundingClientRect();
          var bRect = best.getBoundingClientRect();
          // Only adopt parent if it's a similar size (not a huge wrapper)
          if (pRect.width < bRect.width * 2 && pRect.height < bRect.height * 2.5) {
            best = current.parentElement;
          } else {
            break;
          }
        } else {
          break;
        }
      }
      current = current.parentElement;
    }
    return best;
  }

  // ── Find a grabbable component on the current page ──
  function findGrabbableElement() {
    var all = document.querySelectorAll("*");
    var seen = new Set();
    var candidates = [];

    for (var i = 0; i < all.length; i++) {
      var el = all[i];

      // Skip cat, clones, titlebar
      if (el.closest(".cc-container")) continue;
      if (el.closest("[data-plugin-id='companion-cat']")) continue;
      if (el.classList.contains("cc-clone")) continue;
      if (el.closest("[data-tauri-drag-region]")) continue;

      // Skip not rendered
      if (el.offsetParent === null) continue;

      // Walk up to find the component boundary
      var comp = findComponentBoundary(el);
      if (!comp) continue;
      if (seen.has(comp)) continue;
      seen.add(comp);

      // Check size
      var rect = comp.getBoundingClientRect();
      if (rect.width < 20 || rect.height < 14) continue;
      if (rect.width > 500 || rect.height > 200) continue;
      if (rect.top < 35) continue;
      if (rect.bottom > window.innerHeight || rect.right > window.innerWidth) continue;

      // Skip if already grabbed
      var alreadyGrabbed = false;
      for (var k = 0; k < mischief.grabbed.length; k++) {
        if (mischief.grabbed[k].original === comp) { alreadyGrabbed = true; break; }
      }
      if (alreadyGrabbed) continue;

      candidates.push({ el: comp, rect: rect });
    }

    if (candidates.length === 0) return null;
    return candidates[Math.floor(Math.random() * candidates.length)];
  }

  // ── Clone an element and position it exactly where the original is ──
  function cloneElement(el, rect) {
    var clone = el.cloneNode(true);
    clone.className = el.className + " cc-clone";
    clone.style.position = "fixed";
    clone.style.left = rect.left + "px";
    clone.style.top = rect.top + "px";
    clone.style.width = rect.width + "px";
    clone.style.height = rect.height + "px";
    clone.style.zIndex = "10000";
    clone.style.pointerEvents = "none";
    clone.style.margin = "0";
    clone.style.transition = "none";
    document.body.appendChild(clone);
    return clone;
  }

  // ── Grab: fly to real element → clone it → hide original → carry clone ──
  function grabElement() {
    if (!mischief.active) return Promise.resolve();

    var target = findGrabbableElement();
    if (!target) return Promise.resolve();

    var el = target.el;
    var rect = target.rect;

    var msg = MISCHIEF_MESSAGES[Math.floor(Math.random() * MISCHIEF_MESSAGES.length)];
    showMessage(msg);

    // Fly to the element
    return flyTo(rect.left - 10, rect.top - 55, 2000).then(function () {
      if (!mischief.active) return;

      // Clone, hide original, carry clone
      var clone = cloneElement(el, rect);
      el.style.visibility = "hidden";

      var grabbed = { original: el, clone: clone, origRect: rect };
      mischief.grabbed.push(grabbed);
      mischief.carrying = grabbed;
      container.classList.add("carrying");

      // Fly to a random drop position
      var dropX = 40 + Math.random() * (window.innerWidth - 160);
      var dropY = 60 + Math.random() * (window.innerHeight - 160);
      return flyTo(dropX, dropY, 2500);
    }).then(function () {
      if (!mischief.active) return;
      // Drop the clone
      container.classList.remove("carrying");
      mischief.carrying = null;
    });
  }

  // ── Mischief loop ──
  function mischiefLoop() {
    if (!mischief.active) return;

    grabElement().then(function () {
      if (!mischief.active) return;
      // Limit to ~5 grabbed elements
      if (mischief.grabbed.length >= 5) {
        // Just idle, don't grab more
        setTimeout(mischiefLoop, 3000 + Math.random() * 3000);
      } else {
        setTimeout(mischiefLoop, 2000 + Math.random() * 3000);
      }
    });
  }

  function startMischief() {
    if (mischief.active || sleeping) return;
    mischief.active = true;
    mischiefLoop();
  }

  function stopMischief() {
    mischief.active = false;
    flyAborted = true;
    if (flyRaf) { cancelAnimationFrame(flyRaf); flyRaf = null; }
    requestAnimationFrame(function () { flyAborted = false; });

    container.classList.remove("carrying");
    mischief.carrying = null;

    // Startled
    container.classList.add("startled");
    showMessage("...!");
    setTimeout(function () { container.classList.remove("startled"); }, 600);

    // Animate each clone back to its original position with JS easing, staggered
    var toReturn = mischief.grabbed.slice();
    mischief.grabbed = [];

    toReturn.forEach(function (g, i) {
      setTimeout(function () {
        // Re-read where the original element actually is now (layout may have shifted)
        g.original.style.visibility = "";
        var destRect = g.original.getBoundingClientRect();
        g.original.style.visibility = "hidden";

        var startX = parseFloat(g.clone.style.left);
        var startY = parseFloat(g.clone.style.top);
        var endX = destRect.left;
        var endY = destRect.top;
        var duration = 800;
        var startTime = performance.now();

        function animateReturn(now) {
          var t = Math.min((now - startTime) / duration, 1);
          var e = t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;
          g.clone.style.left = (startX + (endX - startX) * e) + "px";
          g.clone.style.top = (startY + (endY - startY) * e) + "px";

          if (t < 1) {
            requestAnimationFrame(animateReturn);
          } else {
            // Arrived — restore original, remove clone
            g.original.style.visibility = "";
            g.clone.remove();
          }
        }
        requestAnimationFrame(animateReturn);
      }, i * 200);
    });
  }

  // ── Schedulers ──
  var timers = [];
  function schedule(fn, minDelay, maxDelay) {
    function run() {
      var id = setTimeout(function () {
        fn();
        run();
      }, minDelay + Math.random() * (maxDelay - minDelay));
      timers.push(id);
    }
    run();
  }

  schedule(moveCatStep, 5000, 10000);
  schedule(function () { showMessage(); }, 8000, 15000);
  schedule(doStretch, 15000, 30000);
  schedule(function () {
    if (!sleeping && !mischief.active) {
      fallAsleep();
      var id = setTimeout(function () { if (sleeping) wakeUp(); }, 10000 + Math.random() * 10000);
      timers.push(id);
    }
  }, 40000, 80000);

  setTimeout(function () { showMessage(); }, 2000);
  afkTimer = setTimeout(startMischief, AFK_DELAY);

  // ── Cleanup ──
  window.__astraPluginCleanup = window.__astraPluginCleanup || {};
  window.__astraPluginCleanup["companion-cat"] = function () {
    // Restore any grabbed elements
    mischief.grabbed.forEach(function (g) {
      g.original.style.visibility = "";
      g.clone.remove();
    });
    mischief.grabbed = [];
    mischief.active = false;

    clearTimeout(afkTimer);
    timers.forEach(clearTimeout);
    if (flyRaf) cancelAnimationFrame(flyRaf);
    style.remove();
    container.remove();
    delete window.__companionCatActive;
  };
})();
