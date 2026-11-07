// ViSAGE client-side helpers — served via trame's module system.
// Vue 3 silently strips <script> tags from templates, so any client JS
// has to come in via a real .js file the browser can load.
(function () {
  // ─── Step-button chrome removal ───────────────────────────────────
  // Vuetify injects ::before/::after pseudo-elements onto VBtn for hover
  // overlays and focus rings.  Inline style= cannot target pseudo-elements,
  // so we inject a stylesheet rule targeting our custom sage-step-btn class.
  (function () {
    var s = document.createElement('style');
    s.textContent =
      '.sage-step-btn, .sage-step-btn:focus, .sage-step-btn:focus-visible,' +
      ' .sage-step-btn:focus-within, .sage-step-btn:hover, .sage-step-btn:active' +
      ' { border:none !important; outline:none !important; box-shadow:none !important;' +
      '   background:none !important; opacity:1 !important; }' +
      '.sage-step-btn::before, .sage-step-btn::after { display:none !important; }' +
      '.sage-step-btn .v-btn__overlay, .sage-step-btn .v-btn__underlay' +
      ' { display:none !important; opacity:0 !important; }' +
      '.sage-step-btn .mdi { font-size:20px !important; }';
    document.head.appendChild(s);

    document.addEventListener('click', function (e) {
      var btn = e.target.closest('.sage-step-btn');
      if (!btn) return;
      btn.style.color = 'cyan';
      var icon = btn.querySelector('.mdi');
      if (icon) icon.style.color = 'cyan';
      clearTimeout(btn._flashTimer);
      btn._flashTimer = setTimeout(function () {
        btn.style.color = 'white';
        if (icon) icon.style.color = '';
      }, 300);
    });
  })();

  // ─── Viewport fit ─────────────────────────────────────────────────
  // Fit the .sage-content panel to fill exactly the space between the
  // toolbar and footer, measured from actual DOM positions.  Pure CSS
  // chains through Vuetify's flex layout are unreliable across screen
  // sizes — direct JS measurement is the only thing that always works.
  //
  // trame loads module scripts dynamically after Vue mounts, so the DOM
  // is ready by the time this runs.  We also poll with setTimeout to
  // handle any delay between script load and element availability.
  function sageFitViewport() {
    var el = document.querySelector('.sage-content');
    if (!el) { setTimeout(sageFitViewport, 100); return; }

    // Measure actual rendered bar/footer heights so any density or
    // border tweaks are accounted for automatically.
    var bar  = document.querySelector('.v-app-bar');
    var foot = document.querySelector('.v-footer');
    var barH  = bar  ? bar.getBoundingClientRect().height  : 48;
    var footH = foot ? foot.getBoundingClientRect().height : 36;

    // Clamp to at least 200 px so the view never collapses on tiny screens.
    var h = Math.max(window.innerHeight - barH - footH, 200);

    // Override both the position:fixed CSS vars and a direct height in case
    // the fixed approach didn't fire (e.g. Safari backface-visibility quirk).
    el.style.top    = barH  + 'px';
    el.style.bottom = footH + 'px';
    el.style.height = h + 'px';

    // Hard-stop document scroll at every level.
    document.documentElement.style.overflow = 'hidden';
    document.body.style.overflow            = 'hidden';
  }

  window.addEventListener('resize', sageFitViewport);
  sageFitViewport();
  // ─── Pop-out console drag handler ─────────────────────────────────
  // Mousedown on `.sage-popout-handle` starts a drag of the nearest
  // `.sage-popout` ancestor. Repositions via left/top, clearing the
  // initial right/bottom anchors so the move actually applies.
  document.addEventListener('mousedown', function (e) {
    var handle = e.target.closest && e.target.closest('.sage-popout-handle');
    if (!handle) return;
    // Don't start a drag when the press lands on a button in the title bar
    // (the ✕ close / maximize). Otherwise re-anchoring the card on mousedown
    // resizes it and swallows the first click, so closing took two clicks.
    if (e.target.closest('button, .v-btn')) return;
    var card = handle.closest('.sage-popout');
    if (!card) return;
    e.preventDefault();
    var startX = e.clientX, startY = e.clientY;
    var startLeft = card.offsetLeft, startTop = card.offsetTop;
    card.style.right  = 'auto';
    card.style.bottom = 'auto';
    card.style.left   = startLeft + 'px';
    card.style.top    = startTop  + 'px';
    function mv(ev) {
      card.style.left = (startLeft + ev.clientX - startX) + 'px';
      card.style.top  = (startTop  + ev.clientY - startY) + 'px';
    }
    function up() {
      document.removeEventListener('mousemove', mv);
      document.removeEventListener('mouseup',   up);
      if (window.drawHdLabels) window.drawHdLabels();  // the key's free space moved
    }
    document.addEventListener('mousemove', mv);
    document.addEventListener('mouseup',   up);
  });

  // ─── The rail's panel: dragged by its grip ─────────────────────────
  // The panel is placed by the theme (right of the view, by the rail) with
  // !important rules, so a move sets its own left/top the same way.
  // Double-click on the grip puts it back.
  document.addEventListener('mousedown', function (e) {
    var grip = e.target.closest && e.target.closest('.sage-panel-grip');
    if (!grip) return;
    var panel = grip.closest('.sage-panel');
    if (!panel) return;
    e.preventDefault();
    var host = panel.offsetParent || document.body;
    var hr = host.getBoundingClientRect(), pr = panel.getBoundingClientRect();
    var startX = e.clientX, startY = e.clientY;
    // (Where it goes in the window, kept wholly in view so its grip can't
    // be lost off screen, then set against its container, which is
    // zero-width at the view's right edge.)
    function place(x, y) {
      x = Math.min(Math.max(x, 0), Math.max(window.innerWidth - pr.width, 0));
      y = Math.min(Math.max(y, 0), Math.max(window.innerHeight - pr.height, 0));
      panel.style.setProperty('left', (x - hr.left) + 'px', 'important');
      panel.style.setProperty('top', (y - hr.top) + 'px', 'important');
      panel.style.setProperty('right', 'auto', 'important');
    }
    place(pr.left, pr.top);
    function mv(ev) { place(pr.left + ev.clientX - startX, pr.top + ev.clientY - startY); }
    function up() {
      document.removeEventListener('mousemove', mv);
      document.removeEventListener('mouseup', up);
      if (window.drawHdLabels) window.drawHdLabels();  // the key's free space moved
    }
    document.addEventListener('mousemove', mv);
    document.addEventListener('mouseup', up);
  });
  document.addEventListener('dblclick', function (e) {
    var grip = e.target.closest && e.target.closest('.sage-panel-grip');
    if (!grip) return;
    var panel = grip.closest('.sage-panel');
    ['left', 'top', 'right'].forEach(function (k) { panel.style.removeProperty(k); });
    if (window.drawHdLabels) window.drawHdLabels();
  });

  // ─── Pop-out maximise / restore ───────────────────────────────────
  // Click on a `.sage-popout-max-btn` toggles the `sage-popout-max`
  // class on the nearest `.sage-popout`, which (via sage_theme.css)
  // pins the card to fill the VTK render area. The button glyph flips
  // between the fullscreen / fullscreen-exit icons to match.
  document.addEventListener('click', function (e) {
    var btn = e.target.closest && e.target.closest('.sage-popout-max-btn');
    if (!btn) return;
    var card = btn.closest('.sage-popout');
    if (!card) return;
    e.preventDefault();
    e.stopPropagation();
    var maxed = card.classList.toggle('sage-popout-max');
    var icon = btn.querySelector('.mdi');
    if (icon) {
      icon.classList.toggle('mdi-fullscreen', !maxed);
      icon.classList.toggle('mdi-fullscreen-exit', maxed);
    }
  }, true);  // capture phase — beat Vuetify's own click handling

  // ─── Enter-to-click ───────────────────────────────────────────────
  // Any <input> / <textarea> whose ancestor declares
  // `data-enter-click="<button-id>"` will, on Enter, trigger a click
  // on the element with that id. Reliable because it bypasses
  // Vuetify's internal event handling entirely — we just simulate
  // the user clicking the action button.
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Enter') return;
    if (e.shiftKey || e.ctrlKey || e.altKey || e.metaKey) return;
    var inp = e.target;
    if (!inp) return;
    var tag = inp.tagName;
    if (tag !== 'INPUT' && tag !== 'TEXTAREA') return;
    var el = inp;
    while (el && el !== document.body) {
      var act = el.getAttribute && el.getAttribute('data-enter-click');
      if (act) {
        var btn = document.getElementById(act);
        if (btn) {
          e.preventDefault();
          btn.click();
        }
        return;
      }
      el = el.parentElement;
    }
  }, true);  // capture phase so we beat Vuetify's listeners

  // ─── Console auto-scroll (follow output) ──────────────────────────
  // The console history (in-panel + pop-out) appends entries via Vue.
  // Keep each `.sage-console-scroll` container pinned to the bottom so
  // new output stays visible — unless the user has scrolled up to read
  // back, in which case we leave their position alone.
  var NEAR_BOTTOM_PX = 48;
  function stickToBottom(el) {
    el.scrollTop = el.scrollHeight;
  }
  function isNearBottom(el) {
    return el.scrollHeight - el.scrollTop - el.clientHeight <= NEAR_BOTTOM_PX;
  }
  // One observer per container, attached lazily as they appear/change.
  var obs = new MutationObserver(function (mutations) {
    var seen = new Set();
    mutations.forEach(function (m) {
      var el = m.target;
      while (el && el !== document.body) {
        if (el.classList && el.classList.contains('sage-console-scroll')) break;
        el = el.parentElement;
      }
      if (!el || el === document.body || seen.has(el)) return;
      seen.add(el);
      // Only follow if the user was already at/near the bottom.
      if (el.__sageStick !== false) stickToBottom(el);
    });
  });
  obs.observe(document.body, { childList: true, subtree: true });

  // Track whether the user has scrolled away from the bottom so we can
  // pause auto-follow, and resume once they return to the bottom.
  document.addEventListener('scroll', function (e) {
    var el = e.target;
    if (!el || !el.classList || !el.classList.contains('sage-console-scroll'))
      return;
    el.__sageStick = isNearBottom(el);
  }, true);

  // ─── Keyboard fly navigation (WASD / arrow keys) ──────────────────
  // Holding a key flies the camera that way continuously. Each tick
  // clicks a hidden cam-<dir> button which the server turns into a
  // view-relative translation. Movement is gated out while typing in a
  // field so console / input keys aren't hijacked.
  var FLY_KEYS = {
    'w': 'forward', 'arrowup': 'forward',
    's': 'back',    'arrowdown': 'back',
    'a': 'left',    'arrowleft': 'left',
    'd': 'right',   'arrowright': 'right',
    'q': 'up',      'e': 'down'
  };
  var heldKeys = {};      // key -> true while physically held
  var dirCount = {};      // direction -> number of held keys mapping to it
  function inEditable(el) {
    if (!el) return false;
    var t = el.tagName;
    return t === 'INPUT' || t === 'TEXTAREA' || el.isContentEditable;
  }
  function clickBtn(id) {
    var b = document.getElementById(id);
    if (b) b.click();
  }
  function pressDir(dir) {
    dirCount[dir] = (dirCount[dir] || 0) + 1;
    if (dirCount[dir] === 1) clickBtn('cam-press-' + dir);   // 0 -> 1
  }
  function releaseDir(dir) {
    dirCount[dir] = (dirCount[dir] || 1) - 1;
    if (dirCount[dir] <= 0) { dirCount[dir] = 0; clickBtn('cam-release-' + dir); }
  }
  function releaseAll() {
    for (var d in dirCount) { if (dirCount[d] > 0) clickBtn('cam-release-' + d); }
    heldKeys = {}; dirCount = {};
  }
  document.addEventListener('keydown', function (e) {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (inEditable(e.target)) return;
    var k = (e.key || '').toLowerCase();
    var dir = FLY_KEYS[k];
    if (!dir) return;
    e.preventDefault();
    e.stopPropagation();   // prevent VTK interactor from also handling WASD/arrows
    if (heldKeys[k]) return;        // ignore the OS auto-repeat
    heldKeys[k] = true;
    pressDir(dir);
  }, true);
  document.addEventListener('keyup', function (e) {
    var k = (e.key || '').toLowerCase();
    if (!heldKeys[k]) return;
    e.stopPropagation();   // prevent VTK interactor from seeing the release
    delete heldKeys[k];
    var dir = FLY_KEYS[k];
    if (dir) releaseDir(dir);
  }, true);
  window.addEventListener('blur', releaseAll);   // stop if focus leaves

  // ─── Selection browsing keys ───────────────────────────────────────
  // [ ] previous / next member of the group, C its central, N the nearest
  // galaxy, B back, Shift+B forward (the selection card's buttons).
  var SEL_KEYS = {'[': 'prev', ']': 'next', 'c': 'central', 'n': 'nearest',
                  'b': 'back', 'B': 'fwd'};
  document.addEventListener('keydown', function (e) {
    if (e.ctrlKey || e.metaKey || e.altKey || inEditable(e.target)) return;
    var name = SEL_KEYS[e.key] || SEL_KEYS[(e.key || '').toLowerCase()];
    if (e.key === 'B') name = 'fwd';
    if (!name) return;
    var st = window.trame && window.trame.state;
    if (!st || !st.get('sel_active')) return;
    e.preventDefault();
    e.stopPropagation();   // not for the VTK interactor
    clickBtn('sel-key-' + name);
  }, true);

  // ─── Frame flow control ────────────────────────────────────────────
  // After each frame the server sends a ping; answering it once this page
  // has worked through everything before it tells the server the browser
  // has caught up, so it never runs more than a frame or two ahead
  // (visage.utils.frame_delivery).
  (function watchPing() {
    var t = window.trame;
    if (!t || !t.state || !t.state.watch) { setTimeout(watchPing, 300); return; }
    t.state.watch(['visage_ping'], function (id) {
      if (id) { try { t.trigger('visage_pong', [id]); } catch (e) {} }
    });
  })();

  // ─── HD Components: numbered markers on the parts and a still key ───
  // hd_labels (from the server): {cats: [[name, colour]], items: [{t, cat,
  // text, vis}] in key order, marks: [{x, y, n}]} with x, y fractions of
  // the view (y down) and n the key numbers a marker carries.  Each part's
  // point is fixed in the model, so markers move with it; the key doesn't.
  var hdLabels = null;
  var HD_FADE = 0.65;  // share of its arc each colour holds before fading
  function hdEsc(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }
  function hdRich(s) {
    // "2.1 × 10^7 M☉" -> raised exponent; τ_V, L_X -> subscripts.
    return hdEsc(s)
      .replace(/10\^(-?[\d.]+)/g, '10<sup>$1</sup>')
      .replace(/τ_V/g, 'τ<sub>V</sub>')
      .replace(/L_X/g, 'L<sub>X</sub>');
  }
  function hdRim(colours) {
    // One colour: solid.  Several: each holds, then fades into the next.
    if (colours.length === 1) return colours[0];
    var n = colours.length, share = 360 / n, stops = [];
    colours.forEach(function (c, i) {
      stops.push(c + ' ' + (i * share).toFixed(1) + 'deg ' +
                 (i * share + HD_FADE * share).toFixed(1) + 'deg');
    });
    stops.push(colours[0] + ' 360deg');
    return 'conic-gradient(from -90deg, ' + stops.join(', ') + ')';
  }
  function hdBubble(nums, colours, rimColours, size) {
    // The card's glass, a rim in the categories' colours, each number in
    // its own.  (The rim is a ring cut from a gradient by a mask.)
    var txt = nums.map(function (k, i) {
      return '<span style="color:' + colours[i] + '">' + k + '</span>';
    }).join('<span style="color:#c8cdd4">·</span>');
    var rim = hdRim(rimColours);
    return '<span class="hd-bubble" style="height:' + size + 'px;min-width:' +
      size + 'px;font-size:' + Math.round(size * 0.6) + 'px">' +
      '<span class="hd-rim" style="background:' + rim + '"></span>' + txt + '</span>';
  }
  function hdObstacles(host) {
    // The card, the icon rail and an open panel, in the host's pixels.
    var hr = host.getBoundingClientRect(), out = [];
    var els = [document.getElementById('sel-card'), document.querySelector('.sage-rail')]
      .concat(Array.prototype.slice.call(document.querySelectorAll('.sage-panel')));
    els.forEach(function (el) {
      if (!el || !el.offsetParent) return;
      var r = el.getBoundingClientRect();
      if (r.width < 2 || r.height < 2) return;
      out.push({ l: r.left - hr.left, r: r.right - hr.left, t: r.top - hr.top, b: r.bottom - hr.top });
    });
    return out;
  }
  function drawHdLabels() {
    var host = document.getElementById('hd-labels');
    if (!host) return;
    var W = host.clientWidth, H = host.clientHeight;
    var d = hdLabels;
    if (!d || !d.items || !d.items.length || !W || !H) { host.innerHTML = ''; return; }
    var col = function (k) { return d.cats[d.items[k - 1].cat][1]; };
    var html = '';
    // Markers: a bubble up and right of its point, a tick down to it.
    d.marks.forEach(function (m) {
      var nums = m.n, colours = nums.map(col), seen = {}, rimC = [];
      colours.forEach(function (c) { if (!seen[c]) { seen[c] = 1; rimC.push(c); } });
      var x = m.x * W, y = m.y * H;
      html += '<div class="hd-mark" data-n="' + nums.join(',') + '" style="left:' + x + 'px;top:' + y + 'px">' +
        '<svg width="16" height="16" style="position:absolute;left:0;top:-16px;overflow:visible">' +
        '<line x1="0" y1="16" x2="9" y2="7" stroke="' + colours[0] + '" stroke-width="2" ' +
        'stroke-linecap="round"/></svg>' +
        '<div style="position:absolute;left:7px;bottom:7px">' + hdBubble(nums, colours, rimC, 22) + '</div></div>';
    });
    // The key: one centred block per category, in the free space between
    // the card, the rail and any open panel.
    var blocks = [];
    d.items.forEach(function (it, i) {
      var b = blocks.length && blocks[blocks.length - 1].cat === it.cat ? blocks[blocks.length - 1] : null;
      if (!b) { b = { cat: it.cat, items: [] }; blocks.push(b); }
      b.items.push({ k: i + 1, it: it });
    });
    var key = '<div id="hd-key" class="hd-key">';
    blocks.forEach(function (b) {
      var c = d.cats[b.cat][1];
      key += '<div class="hd-key-block"><div class="hd-key-cat" style="color:' + c + '">' +
        hdEsc(d.cats[b.cat][0]) + '</div>';
      b.items.forEach(function (e) {
        key += '<div class="hd-key-item' + (e.it.vis ? '' : ' hd-off') + '" data-k="' + e.k + '">' +
          '<div class="hd-key-name">' + hdBubble([e.k], [c], [c], 20) + '<span>' + hdEsc(e.it.t) + '</span></div>' +
          '<div class="hd-key-text">' + hdRich(e.it.text) + '</div></div>';
      });
      key += '</div>';
    });
    key += '</div>';
    host.innerHTML = html + key;
    // Fit the key between the obstacles in its band at the bottom.
    var el = document.getElementById('hd-key');
    var place = function () {
      var h = el.offsetHeight, top = H - 20 - h, left = 24, right = W - 24;
      hdObstacles(host).forEach(function (o) {
        if (o.b < top || o.t > H - 20) return;  // not in the key's band
        if ((o.l + o.r) / 2 < W / 2) left = Math.max(left, o.r + 24);
        else right = Math.min(right, o.l - 24);
      });
      el.style.left = left + 'px';
      el.style.width = Math.max(right - left, 200) + 'px';
      el.style.setProperty('--hd-block-w', Math.max(
        Math.min(250, Math.floor((right - left) / Math.max(blocks.length, 1))), 170) + 'px');
      return h;
    };
    var h0 = place();
    if (el.offsetHeight !== h0) place();  // its width changed its height
    // A marker under the key would sit on its text: hide it, and grey its
    // entries as for a part out of view.
    var kr = el.getBoundingClientRect();
    Array.prototype.forEach.call(host.querySelectorAll('.hd-mark'), function (m) {
      var r = m.getBoundingClientRect();
      if (r.left > kr.left - 6 && r.left < kr.right + 6 && r.top > kr.top - 6 && r.top < kr.bottom + 6) {
        m.style.display = 'none';
        m.getAttribute('data-n').split(',').forEach(function (k) {
          var it = host.querySelector('.hd-key-item[data-k="' + k + '"]');
          if (it) it.classList.add('hd-off');
        });
      }
    });
  }
  (function hdLabelStyles() {
    var css = document.createElement('style');
    css.textContent =
      '#hd-labels{font-family:Roboto,sans-serif}' +
      '.hd-mark{position:absolute;width:0;height:0}' +
      '.hd-bubble{position:relative;display:inline-flex;align-items:center;justify-content:center;' +
        'box-sizing:border-box;padding:0 6px;border-radius:999px;font-weight:500;line-height:1;' +
        'background:rgba(8,10,16,0.72);-webkit-backdrop-filter:blur(16px);backdrop-filter:blur(16px);' +
        'white-space:nowrap}' +
      '.hd-rim{position:absolute;inset:0;border-radius:999px;padding:2px;pointer-events:none;' +
        '-webkit-mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);' +
        '-webkit-mask-composite:xor;mask-composite:exclude}' +
      '.hd-key{position:absolute;bottom:20px;display:flex;flex-wrap:wrap;justify-content:center;' +
        'align-items:flex-start;gap:10px 0;text-align:center;' +
        'text-shadow:0 0 6px rgba(0,0,0,0.95),0 0 2px rgba(0,0,0,0.9)}' +
      '.hd-key-block{width:var(--hd-block-w,250px);padding:0 6px;box-sizing:border-box}' +
      '.hd-key-cat{font-size:11px;font-weight:500;letter-spacing:0.08em;text-transform:uppercase;margin-bottom:6px}' +
      '.hd-key-item{margin-bottom:8px}' +
      '.hd-key-item.hd-off{opacity:0.38}' +
      '.hd-key-name{display:flex;align-items:center;justify-content:center;gap:8px;' +
        'font-size:17px;font-weight:500;color:#f1f5f9}' +
      '.hd-key-text{font-size:13px;font-weight:400;color:#b0bac6;margin-top:3px;line-height:1.3;' +
        'display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}' +
      '.hd-key-text sup,.hd-key-text sub{font-size:0.75em;line-height:0}';
    document.head.appendChild(css);
  })();
  (function watchHdLabels() {
    var t = window.trame;
    if (!t || !t.state || !t.state.watch) { setTimeout(watchHdLabels, 300); return; }
    t.state.watch(['hd_labels'], function (labels) {
      hdLabels = labels && labels.items ? labels : null;
      drawHdLabels();
    });
    // The card, a panel opening or closing: the key's free space changes.
    t.state.watch(['sel_show', 'panel_open'], function () { setTimeout(drawHdLabels, 120); });
  })();
  window.addEventListener('resize', drawHdLabels);
  window.drawHdLabels = drawHdLabels;

  // ─── HD: Esc cancels a build or leaves HD ──────────────────────────
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape' || inEditable(e.target)) return;
    var st = window.trame && window.trame.state;
    if (!st || !(st.get('hd_active') || st.get('hd_building'))) return;
    e.preventDefault();
    clickBtn('hd-escape');
  }, true);

  // ─── Wizard terminal auto-scroll ─────────────────────────────────────
  // The wizard terminal always follows new output — no manual-scroll
  // preservation (unlike the general sage-console-scroll logic).
  // Poll until the element is in the DOM, then attach a MutationObserver
  // directly on it so every child addition scrolls to the bottom.
  (function watchWizTerminal() {
    var term = document.querySelector('.wiz-console-scroll');
    if (!term) { setTimeout(watchWizTerminal, 300); return; }
    new MutationObserver(function () {
      term.scrollTop = term.scrollHeight;
    }).observe(term, { childList: true, subtree: true });
  })();

  // Grab keyboard focus as soon as the page is up so WASD / arrow keys work
  // immediately, without the user having to click the viewport first.
  function grabKeyboardFocus() {
    if (!document.body) return;
    if (document.activeElement && inEditable(document.activeElement)) return;
    document.body.setAttribute('tabindex', '-1');
    try { window.focus(); document.body.focus(); } catch (e) {}
  }
  window.addEventListener('load', function () {
    grabKeyboardFocus();
    setTimeout(grabKeyboardFocus, 500);
    setTimeout(grabKeyboardFocus, 1500);
  });

  // ── xterm.js terminal integration ────────────────────────────────────
  (function () {
    var _xterms    = {};  // sid → { term, fit }  (console panel)
    var _xtermsOut = {};  // sid → { term, fit }  (console pop-out)
    var _lastConsoleKey = null;
    var _lastPopoutKey  = null;
    var _ptyListenerInstalled = false;

    // Wizard terminal
    var _wizTerm         = null;
    var _wizFit          = null;
    // Wizard terminal output arrives tagged with its position in the
    // stream; _wizOff is how far this terminal has written (-1: nothing
    // yet). A gap means output was missed, so ask for it (never skip:
    // programs that redraw in place scramble when bytes go missing).
    var _wizOff          = -1;
    var _wizRunWas       = false;  // a command was running at the last poll
    var _wizNeedAt       = null;  // the position last asked for
    var _wizNeedTime     = 0;
    var _wizNeedSeq      = 0;
    var _wizListenerInstalled = false;
    var _wizPending      = false;
    var _wizIniting      = false;  // a deferred start of the wizard xterm is queued
    var _relaunchWatch   = false;  // watching for the server to restart with a model
    var _lastWizActive   = null;

    // What covers the page while ViSAGE restarts on another model: trees
    // growing in from every side towards the model's name, joined by threads
    // like the cosmic web.  Plain DOM on <body>, so it outlives the app's own
    // "Connection closed" screen until the page reloads.
    function _showRelaunchCard(name) {
      if (document.getElementById('visage-relaunch')) return;
      var d = document.createElement('div');
      d.id = 'visage-relaunch';
      d.style.cssText = 'position:fixed;inset:0;z-index:100000;background:#000;' +
        'overflow:hidden;font-family:Roboto,system-ui,sans-serif;color:#fff;';
      var cv = document.createElement('canvas');
      cv.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;';
      var text = document.createElement('div');
      text.style.cssText = 'position:absolute;left:0;right:0;top:50%;' +
        'transform:translateY(-50%);padding:0 24px;text-align:center;';
      var over = document.createElement('div');
      over.style.cssText = 'font-size:0.8rem;letter-spacing:0.14em;' +
        'color:#94a3b8;margin-bottom:6px;';
      over.textContent = 'OPENING';
      var t = document.createElement('div');
      t.style.cssText = 'font-size:1.6rem;font-weight:600;word-break:break-word;';
      t.textContent = name;
      text.appendChild(over);
      text.appendChild(t);
      var line = document.createElement('div');
      line.style.cssText = 'position:absolute;left:0;right:0;bottom:0;' +
        'height:2px;overflow:hidden;';
      var run = document.createElement('i');
      run.style.cssText = 'position:absolute;height:100%;width:28%;' +
        'background:#22d3ee;animation:visage-run 1.8s ease-in-out infinite;';
      line.appendChild(run);
      var st = document.createElement('style');
      st.textContent = '@keyframes visage-run{from{left:-28%}to{left:100%}}';
      d.appendChild(st);
      d.appendChild(cv);
      d.appendChild(text);
      d.appendChild(line);
      document.body.appendChild(d);

      var COL = ['#22d3ee', '#c084fc', '#ffd700', '#fb7185', '#34d399'];
      var DEPTH = 6, CLEAR = [0.42, 0.17], GAP = 0.034, REACH = 0.16;
      var seed = 331;
      function rnd() {
        seed = (seed * 16807) % 2147483647;
        return seed / 2147483647;
      }
      var nodes = [];
      function grow(x, y, ang, len, depth, par, tree) {
        var n = {
          x: x, y: y, d: DEPTH - depth, par: par, tree: tree,
          c: par ? par.c : COL[0], b: (rnd() - 0.5) * 0.3, p: rnd() * 6,
          leaf: depth === 0, big: rnd() < 0.12, hide: false,
        };
        if (par && rnd() < 0.3) n.c = COL[Math.floor(rnd() * 5)];
        nodes.push(n);
        if (!depth) return;
        var m = rnd() < 0.14 ? 3 : rnd() < 0.2 ? 1 : 2;
        for (var i = 0; i < m; i++) {
          var a = ang + (m === 1 ? 0 : (i / (m - 1) - 0.5) * 1.0) +
            (rnd() - 0.5) * 0.4;
          var l = len * (0.76 + rnd() * 0.22);
          grow(x + Math.cos(a) * l, y + Math.sin(a) * l, a, l, depth - 1, n,
               tree);
        }
      }
      // Trunks in units of the screen's height, centred: about +-0.89 by
      // +-0.5 on a 16:9 screen.
      var UP = -Math.PI / 2;
      [
        [-0.42, -0.52, -UP + 0.15, 0.17], [0.42, -0.52, -UP - 0.15, 0.17],
        [-0.93, 0, 0, 0.2], [0.93, 0, Math.PI, 0.2],
        [-0.56, 0.52, UP + 0.2, 0.17], [0.56, 0.52, UP - 0.2, 0.17],
      ].forEach(function (k, tree) {
        var first = nodes.length;
        grow(k[0], k[1], k[2], k[3], DEPTH, null, tree);
        nodes[first].root = true;
        nodes[first].c = COL[tree % 5];
        nodes[first + 1].c = COL[(tree + 1) % 5];
      });
      // Thin crowded tips so nothing clumps, and keep the middle clear.
      var kept = [];
      nodes.forEach(function (n) {
        if ((n.par && n.par.hide) ||
            Math.pow(n.x / CLEAR[0], 2) + Math.pow(n.y / CLEAR[1], 2) < 1) {
          n.hide = true;
        } else if (n.d >= DEPTH - 2) {
          n.hide = kept.some(function (k) {
            return Math.hypot(k.x - n.x, k.y - n.y) < GAP;
          });
          if (!n.hide) kept.push(n);
        }
      });
      // Each tip gets one thread at most, and only to another tree.
      var tips = nodes.filter(function (n) {
        return !n.hide && n.d >= DEPTH - 1;
      });
      var threads = [], used = [];
      tips.forEach(function (a) {
        if (used.indexOf(a) >= 0) return;
        var best = null, near = REACH;
        tips.forEach(function (b) {
          if (a === b || a.tree === b.tree || used.indexOf(b) >= 0) return;
          var gap = Math.hypot(a.x - b.x, a.y - b.y);
          if (gap < near && gap > 0.05) { near = gap; best = b; }
        });
        if (best) {
          used.push(a, best);
          threads.push([a, best]);
        }
      });

      var c = cv.getContext('2d'), start = null;
      function dot(x, y, r, col, al) {
        c.globalAlpha = al;
        c.fillStyle = col;
        c.beginPath();
        c.arc(x, y, r, 0, 7);
        c.fill();
        c.globalAlpha = 1;
      }
      function glow(x, y, r, col, al) {
        var g = c.createRadialGradient(x, y, 0, x, y, r);
        g.addColorStop(0, col);
        g.addColorStop(1, 'transparent');
        c.globalAlpha = al;
        c.fillStyle = g;
        c.fillRect(x - r, y - r, 2 * r, 2 * r);
        c.globalAlpha = 1;
      }
      function frame(ms) {
        if (!d.isConnected) return;
        if (start === null) start = ms;
        var now = (ms - start) / 1000;
        var ratio = window.devicePixelRatio || 1;
        var w = window.innerWidth, h = window.innerHeight;
        if (cv.width !== Math.round(w * ratio)) {
          cv.width = Math.round(w * ratio);
          cv.height = Math.round(h * ratio);
        }
        c.setTransform(ratio, 0, 0, ratio, 0, 0);
        c.clearRect(0, 0, w, h);
        var zoom = 1.05 + 0.05 * Math.sin(now * 0.1);
        var dx = Math.sin(now * 0.07) * 0.02, dy = Math.cos(now * 0.06) * 0.015;
        var wide = (w / h) / 1.78;  // reach the sides of any screen
        var X = function (v) { return w / 2 + (v + dx) * h * zoom * wide; };
        var Y = function (v) { return h / 2 + (v + dy) * h * zoom; };
        var size = h / 316;  // lines and dots keep their share of the screen
        var grown = now / 1.1;
        nodes.forEach(function (n, i) {
          if (!n.par || n.hide) return;
          var a = Math.max(0, Math.min(1, grown - (n.d - 1)));
          if (a <= 0) return;
          var p = n.par;
          var mx = (p.x + n.x) / 2 + n.b * (n.y - p.y) * 4;
          var my = (p.y + n.y) / 2 - n.b * (n.x - p.x) * 4;
          var on = function (f) {
            var u = 1 - f;
            return [u * u * p.x + 2 * f * u * mx + f * f * n.x,
                    u * u * p.y + 2 * f * u * my + f * f * n.y];
          };
          c.strokeStyle = n.c;
          c.globalAlpha = 0.34;
          c.lineWidth = Math.max(0.3, 1.5 - n.d * 0.2) * size;
          c.beginPath();
          c.moveTo(X(p.x), Y(p.y));
          for (var f = 0.1; f <= a + 0.001; f += 0.1) {
            var q = on(f);
            c.lineTo(X(q[0]), Y(q[1]));
          }
          c.stroke();
          c.globalAlpha = 1;
          if (a < 1) return;
          var m = on((now * 0.16 + i * 0.31) % 1);
          dot(X(m[0]), Y(m[1]), 1.4 * size, n.c, 0.95);
          if (n.big || n.leaf) {
            var r = (n.big ? 1.5 : 1) * (9 + 3 * Math.sin(now * 0.8 + n.p));
            glow(X(n.x), Y(n.y), r * size, n.c + 'bb', 1);
            dot(X(n.x), Y(n.y), (n.big ? 2 : 1.3) * size, '#fff', 1);
          } else {
            dot(X(n.x), Y(n.y), size, n.c, 0.9);
          }
        });
        var shown = Math.max(0, Math.min(1, grown - DEPTH));
        if (shown > 0) {
          c.lineWidth = 0.4 * size;
          c.strokeStyle = 'rgba(148,163,184,' + 0.3 * shown + ')';
          threads.forEach(function (l, k) {
            var a = l[0], b = l[1];
            c.beginPath();
            c.moveTo(X(a.x), Y(a.y));
            c.lineTo(X(b.x), Y(b.y));
            c.stroke();
            var f = (now * 0.1 + k * 0.17) % 1;
            dot(X(a.x + (b.x - a.x) * f), Y(a.y + (b.y - a.y) * f),
                1.1 * size, a.c, 0.9 * shown);
          });
        }
        nodes.forEach(function (n) {
          if (!n.root) return;
          glow(X(n.x), Y(n.y), 22 * size, '#ffd700aa', Math.min(1, grown));
          dot(X(n.x), Y(n.y), 2.6 * size, '#fff', 1);
        });
        requestAnimationFrame(frame);
      }
      requestAnimationFrame(frame);
    }

    function _getState(key) {
      try { return window.trame.state.get(key); } catch (e) { return undefined; }
    }
    function _trigger(name, args) {
      try { window.trame.trigger(name, args); } catch (e) {}
    }
    function _uint8ToB64(bytes) {
      var s = '';
      for (var i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
      return btoa(s);
    }
    function _writePtyData(term, b64) {
      try {
        var raw = atob(b64);
        var bytes = new Uint8Array(raw.length);
        for (var i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
        term.write(bytes);
      } catch (e) {}
    }

    // Push a value to a hidden <input v-model="key"> via native DOM events.
    // This is the ONLY reliable path from external JS to server @state.change
    // handlers in Trame 3 — window.trame.set() only updates local client state
    // and window.trame.trigger() does not reach server triggers from external JS.
    var _nativeValueSetter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype, 'value'
    ).set;
    function _vueInput(id, value) {
      var el = document.getElementById(id);
      if (!el) return;
      _nativeValueSetter.call(el, value);
      el.dispatchEvent(new Event('input', { bubbles: true }));
    }

    var _ptyInputSeq  = 0;
    var _ptyEnsureSeq = 0;

    function _makeTerm(container, sid, isPopout) {
      if (typeof Terminal === 'undefined') return null;
      if (!container || container.offsetWidth === 0) return null;

      var term = new Terminal({
        cols: 80, rows: 24,
        theme: {
          background: '#0d1117', foreground: '#f0f6fc',
          cursor: '#58a6ff', cursorAccent: '#0d1117',
          selectionBackground: 'rgba(88,166,255,0.3)',
          black: '#484f58',   red: '#ff7b72',   green: '#3fb950',  yellow: '#d29922',
          blue: '#58a6ff',    magenta: '#bc8cff', cyan: '#39c5cf',  white: '#b1bac4',
          brightBlack: '#6e7681', brightRed: '#ffa198', brightGreen: '#56d364',
          brightYellow: '#e3b341', brightBlue: '#79c0ff', brightMagenta: '#d2a8ff',
          brightCyan: '#56d4dd', brightWhite: '#f0f6fc',
        },
        fontSize: 12,
        lineHeight: 1.0,
        letterSpacing: 0,
        fontFamily: '"Menlo", "Monaco", "Consolas", "DejaVu Sans Mono", monospace',
        fontWeight: 'normal',
        fontWeightBold: 'bold',
        scrollback: 5000, convertEol: false, allowTransparency: false,
      });
      var FitCtor = (typeof FitAddon !== 'undefined') ? FitAddon.FitAddon : null;
      var fitAddon = FitCtor ? new FitCtor() : null;
      if (fitAddon) term.loadAddon(fitAddon);
      term.open(container);
      if (fitAddon) fitAddon.fit();

      term.onData(function (data) {
        var bytes = new TextEncoder().encode(data);
        var seq = (_ptyInputSeq = (_ptyInputSeq + 1) % 1e9);
        // Format "seq:cid:b64" — single string so the state change is atomic.
        _vueInput('sage-pty-input-relay', seq + ':' + sid + ':' + _uint8ToB64(bytes));
      });
      return { term: term, fit: fitAddon };
    }

    function _initTerm(sid, attempt) {
      if (_xterms[sid]) {
        if (_xterms[sid].fit) { try { _xterms[sid].fit.fit(); } catch (e) {} }
        return;
      }
      var container = document.getElementById('sage-pty-' + sid);
      var t = _makeTerm(container, sid, false);
      if (!t) {
        // Container may not be laid out yet — retry up to 15 times (1.5 s total).
        if ((attempt || 0) < 15) {
          setTimeout(function () { _initTerm(sid, (attempt || 0) + 1); }, 100);
        }
        return;
      }
      _xterms[sid] = t;
      // Auto-focus so the user can type immediately without clicking.
      try { t.term.focus(); } catch (e) {}
      // Tell the server to start the PTY via the hidden input relay.
      _vueInput('sage-pty-ensure-relay', String((_ptyEnsureSeq = (_ptyEnsureSeq + 1) % 1e9)));
    }

    function _initPopout(sid, attempt) {
      if (_xtermsOut[sid]) {
        if (_xtermsOut[sid].fit) { try { _xtermsOut[sid].fit.fit(); } catch (e) {} }
        return;
      }
      var container = document.getElementById('sage-pty-popout-' + sid);
      var t = _makeTerm(container, sid, true);
      if (!t) {
        if ((attempt || 0) < 15) {
          setTimeout(function () { _initPopout(sid, (attempt || 0) + 1); }, 100);
        }
        return;
      }
      _xtermsOut[sid] = t;
      // Re-fit the terminal whenever the pop-out card is resized (drag-resize,
      // fullscreen toggle, etc.) so the xterm always fills the window instead
      // of leaving an empty region.
      function _fit() { if (t.fit) { try { t.fit.fit(); } catch (e) {} } }
      requestAnimationFrame(function () { _fit(); setTimeout(_fit, 200); });
      if (typeof ResizeObserver !== 'undefined' && t.fit) {
        t.ro = new ResizeObserver(function () { _fit(); });
        t.ro.observe(container);
      }
    }

    // PTY output listener — fires synchronously on every server state push so
    // no chunks are dropped between 50 ms polls.
    //
    // The listener fires mid-loop inside trame's update() (while the for..of
    // over incoming keys is still running), so pty_out_seq may not be updated
    // yet when pty_out_data fires.  Scheduling a Promise microtask defers the
    // actual read until after the entire update() loop completes, at which
    // point both keys are guaranteed to be current.
    var _lastRenderedSeq  = -1;
    var _pendingPtyWrite  = false;

    // ── Wizard xterm ─────────────────────────────────────────────────────
    // The wizard terminal lives in the run page's terminal box while a run
    // shows, and in the full-page terminal otherwise (clone, install...).
    function _wizTermContainer() {
      var id = _getState('wiz_view') === 'run' ? 'wiz-run-pty' : 'sage-wiz-pty';
      return document.getElementById(id);
    }
    var _wizRO = null;

    // SAGE26 redraws its banner and progress bar in place (cursor up 7
    // lines), and those lines are up to 138 columns wide: if they wrap,
    // the redraw lands on the wrong rows and frames pile up. So the
    // terminal is never narrower than WIZ_MIN_COLS: the font shrinks (to
    // 9px at least) to fit that many, and in a box too narrow even then
    // the ends of long lines are cut off at the edge instead of wrapping.
    var WIZ_MIN_COLS = 140;
    function _wizFontFor(box) {
      var w = box ? box.clientWidth : 0;
      if (!w) return 12;
      return Math.max(9, Math.min(12, Math.floor(w / (WIZ_MIN_COLS * 0.6))));
    }
    function _wizFitMin() {
      if (!_wizFit || !_wizTerm) return;
      // Never resize under a running command: a program redrawing in place
      // (SAGE26) loses its place when rows or columns change mid-run.
      // It fits again once the command finishes.
      if (_getState('wiz_run_active') && _wizTerm.cols >= WIZ_MIN_COLS) return;
      try {
        var d = _wizFit.proposeDimensions();
        if (!d || !d.cols || !d.rows) return;
        var cols = Math.max(d.cols, WIZ_MIN_COLS);
        if (cols !== _wizTerm.cols || d.rows !== _wizTerm.rows) {
          _wizTerm.resize(cols, d.rows);
        }
      } catch (e) {}
    }
    function _wizSetFont() {
      if (!_wizTerm || !_wizTerm.element) return;
      var fs = _wizFontFor(_wizTerm.element.parentElement);
      if (_wizTerm.options.fontSize !== fs) {
        try { _wizTerm.options.fontSize = fs; } catch (e) {}
      }
    }

    // Tell the server the terminal's size, so commands run as wide as it.
    var _wizSentSize = '';
    function _sendWizSize() {
      if (!_wizTerm) return;
      var size = _wizTerm.cols + ',' + _wizTerm.rows;
      if (size !== _wizSentSize) {
        _wizSentSize = size;
        _vueInput('wiz-term-size-relay', size);
      }
    }

    function _wizFitSoon() {
      requestAnimationFrame(function () {
        _wizSetFont();
        _wizFitMin();
        _sendWizSize();
      });
    }

    // Move the terminal into the box the current view shows (if it isn't
    // already there) and fit it to that box.
    function _placeWizTerm() {
      if (!_wizTerm || !_wizTerm.element) return;
      var target = _wizTermContainer();
      if (!target || target.offsetWidth === 0) return;
      if (_wizTerm.element.parentElement !== target) {
        target.appendChild(_wizTerm.element);
        try { _wizTerm.refresh(0, _wizTerm.rows - 1); } catch (e) {}
        if (_wizRO) { try { _wizRO.observe(target); } catch (e) {} }
        _wizFitSoon();
        setTimeout(_wizFitSoon, 150);
      }
    }

    function _initWizTerm(attempt) {
      if (_wizTerm) return;
      var container = _wizTermContainer();
      // Wait until the container has BOTH a real width AND a real height.
      // The card is flex:1 inside a column — height resolves after width,
      // so checking only offsetWidth lets us proceed with a zero-height
      // container, and fitAddon.fit() then produces a 1-row sliver.
      if (!container || container.offsetWidth === 0 || container.offsetHeight < 50) {
        if ((attempt || 0) < 50) {
          setTimeout(function () { _initWizTerm((attempt || 0) + 1); }, 100);
        }
        return;
      }
      // xterm.js is loaded from CDN — retry until it arrives rather than
      // silently giving up if the script hasn't loaded yet.
      if (typeof Terminal === 'undefined') {
        if ((attempt || 0) < 50) {
          setTimeout(function () { _initWizTerm((attempt || 0) + 1); }, 100);
        }
        return;
      }
      var term = new Terminal({
        theme: {
          background: '#000000', foreground: '#ffffff',
          cursor: '#06b6d4', selectionBackground: 'rgba(6,182,212,0.25)',
        },
        fontSize: _wizFontFor(container),
        fontFamily: '"Menlo","Monaco","Consolas","DejaVu Sans Mono",monospace',
        scrollback: 10000, convertEol: false, allowTransparency: false,
        cursorBlink: false, disableStdin: true,
      });
      var FitCtor = (typeof FitAddon !== 'undefined') ? FitAddon.FitAddon : null;
      var fitAddon = FitCtor ? new FitCtor() : null;
      if (fitAddon) term.loadAddon(fitAddon);
      term.open(container);
      if (typeof CanvasAddon !== 'undefined') {
        try { term.loadAddon(new CanvasAddon.CanvasAddon()); } catch (e) {}
      }
      _wizTerm = term;
      _wizFit  = fitAddon;
      window.visageWizTerm = term;  // for inspecting the terminal
      // The container height is now set by CSS grid (1fr row) so it always has
      // a real pixel height before open() is called.  Still defer the first
      // fit() to the next paint so xterm has measured its font metrics.
      function _doFit() {
        _wizSetFont();
        _wizFitMin();
        _sendWizSize();
      }
      requestAnimationFrame(function () {
        _doFit();
        setTimeout(_doFit, 200);
      });
      // Re-fit whenever its box is resized (window resize, view changes).
      if (typeof ResizeObserver !== 'undefined' && fitAddon) {
        _wizRO = new ResizeObserver(function () { _doFit(); });
        _wizRO.observe(container);
      }
      // Start from everything the server has kept.
      _wizOff = -1;
      _wizAsk(-1);
    }

    function _destroyWizTerm() {
      if (_wizRO) { try { _wizRO.disconnect(); } catch (e) {} }
      _wizRO = null;
      if (_wizTerm) { try { _wizTerm.dispose(); } catch (e) {} }
      _wizTerm    = null;
      _wizFit     = null;
      _wizOff     = -1;
      _wizNeedAt  = null;
    }

    function _b64Bytes(b64) {
      var raw = atob(b64 || '');
      var bytes = new Uint8Array(raw.length);
      for (var i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
      return bytes;
    }

    // Ask the server for output from position `off` (-1: all it kept);
    // asked again if no answer comes within a second.
    function _wizAsk(off) {
      var now = Date.now();
      if (_wizNeedAt === off && now - _wizNeedTime < 1000) return;
      _wizNeedAt = off;
      _wizNeedTime = now;
      _vueInput('wiz-pty-need-relay', off + ':' + (++_wizNeedSeq));
    }

    function _writeWizNow() {
      var ch = _getState('wiz_pty_chunk');
      if (!ch || !_wizTerm) return;
      var o = ch.o | 0;
      var bytes;
      try { bytes = _b64Bytes(ch.d); } catch (e) { return; }
      if (ch.full) {
        // Everything kept: start the terminal again from it.
        if (_wizOff >= 0) { try { _wizTerm.reset(); } catch (e) {} }
        _wizTerm.write(bytes);
        _wizOff = o + bytes.length;
        _wizNeedAt = null;
        return;
      }
      if (_wizOff < 0) { _wizAsk(-1); return; }      // not started yet
      if (o > _wizOff) { _wizAsk(_wizOff); return; } // missed some
      var skip = _wizOff - o;                         // already written
      if (skip < bytes.length) {
        _wizTerm.write(skip ? bytes.subarray(skip) : bytes);
        _wizOff = o + bytes.length;
      }
      if (_wizNeedAt !== null && _wizNeedAt <= o) _wizNeedAt = null;
    }

    function _installWizListener() {
      if (_wizListenerInstalled) return;
      if (!window.trame || !window.trame.state ||
          typeof window.trame.state.addListener !== 'function') return;
      _wizListenerInstalled = true;
      window.trame.state.addListener(function (ev) {
        if (!ev || ev.type !== 'dirty-state') return;
        var keys = ev.keys || [];
        for (var i = 0; i < keys.length; i++) {
          if (keys[i] === 'wiz_pty_chunk') {
            if (!_wizPending) {
              _wizPending = true;
              Promise.resolve().then(function () { _wizPending = false; _writeWizNow(); });
            }
            break;
          }
        }
      });
    }

    function _writePtyNow() {
      _pendingPtyWrite = false;
      var seq = _getState('pty_out_seq');
      if (seq === undefined || seq === _lastRenderedSeq) return;
      var b64 = _getState('pty_out_data');
      if (!b64) return;
      _lastRenderedSeq = seq;
      var sid = _getState('console_active_id');
      if (sid === undefined) return;
      if (_xterms[sid])    _writePtyData(_xterms[sid].term, b64);
      if (_xtermsOut[sid]) _writePtyData(_xtermsOut[sid].term, b64);
    }

    function _installPtyListener() {
      if (_ptyListenerInstalled) return;
      if (!window.trame || !window.trame.state ||
          typeof window.trame.state.addListener !== 'function') return;
      _ptyListenerInstalled = true;
      // Flush any output that arrived before the listener was installed.
      _writePtyNow();
      window.trame.state.addListener(function (ev) {
        if (!ev || ev.type !== 'dirty-state') return;
        var keys = ev.keys || [];
        for (var i = 0; i < keys.length; i++) {
          if (keys[i] === 'pty_out_seq' || keys[i] === 'pty_out_data') {
            if (!_pendingPtyWrite) {
              _pendingPtyWrite = true;
              Promise.resolve().then(_writePtyNow);
            }
            break;
          }
        }
      });
    }

    // Poll at 50 ms — install listeners once + detect mode/wizard/popout changes.
    setInterval(function () {
      if (!window.trame) return;

      // Install state listeners the first time trame.state is ready.
      _installPtyListener();
      _installWizListener();

      // Mount or destroy wizard xterm when wiz_active changes.
      var wizActive = _getState('wiz_active');
      if (wizActive !== _lastWizActive) {
        _lastWizActive = wizActive;
        if (wizActive) {
          setTimeout(function () { _initWizTerm(); }, 120);
        } else {
          _destroyWizTerm();
        }
      }

      // Opening a model relaunches the server: reload the page once it has
      // gone down and come back up.
      if ((_getState('wiz_loading') || _getState('relaunching')) && !_relaunchWatch) {
        _relaunchWatch = true;
        _showRelaunchCard(_getState('wiz_loading') || _getState('relaunching'));
        var _wentDown = false;
        var _probe = setInterval(function () {
          fetch(window.location.href, { cache: 'no-store' }).then(function (r) {
            if (_wentDown && r.ok) { clearInterval(_probe); window.location.reload(); }
          }).catch(function () { _wentDown = true; });
        }, 1000);
      }

      // The wizard's terminal box is hidden behind the home and mode
      // screens, so it may never have had a size to start in: start it
      // once the terminal view shows.
      var _wv = _getState('wiz_view');
      var _ra = !!_getState('wiz_run_active');
      if (_wizTerm && _wizRunWas && !_ra) _wizFitSoon();  // command finished
      _wizRunWas = _ra;
      if (_wizTerm && (_wv === 'term' || _wv === 'run')) _placeWizTerm();
      if (!_wizTerm && !_wizIniting && (_wv === 'term' || _wv === 'run')) {
        _wizIniting = true;
        setTimeout(function () { _wizIniting = false; _initWizTerm(); }, 60);
      }

      // Detect terminal mode becoming active — mount or re-focus panel terminal.
      var tab  = _getState('nav_active_tab');
      var mode = _getState('console_mode');
      var sid2 = _getState('console_active_id');
      var key  = tab + '|' + mode + '|' + sid2;
      if (key !== _lastConsoleKey) {
        _lastConsoleKey = key;
        if (tab === 'console' && mode === 'terminal' && sid2 !== undefined) {
          setTimeout(function () {
            _initTerm(sid2);
            // Re-focus when switching back to the console tab.
            var ex = _xterms[sid2];
            if (ex) { try { ex.term.focus(); } catch (e) {} }
          }, 80);
        }
      }

      // Detect pop-out opening in terminal mode — mount pop-out terminal.
      var popout = _getState('console_popout_show');
      var poKey  = mode + '|' + sid2 + '|' + popout;
      if (poKey !== _lastPopoutKey) {
        _lastPopoutKey = poKey;
        if (popout && mode === 'terminal' && sid2 !== undefined) {
          setTimeout(function () { _initPopout(sid2); }, 80);
        }
      }
    }, 50);

    window.__sageXterms    = _xterms;
    window.__sageXtermsOut = _xtermsOut;
  })();

  // ─── Labelled dropdowns: values keep clear of their label ─────────────
  // A panel dropdown's label sits inside its box on the left; the value
  // (right-aligned) starts after it, however long the label.
  function sageLabelRoom() {
    document.querySelectorAll('.sage-panel .v-select .v-field').forEach(function (f) {
      var lab = Array.prototype.find.call(
        f.querySelectorAll('.v-field-label'),
        function (l) { return l.offsetParent && l.offsetWidth; });
      if (!lab) return;
      var w = lab.offsetWidth + 8 + 'px';
      if (f.style.getPropertyValue('--sage-label-w') !== w) {
        f.style.setProperty('--sage-label-w', w);
      }
    });
  }
  (new MutationObserver(function () {
    requestAnimationFrame(sageLabelRoom);
  })).observe(document.body, { childList: true, subtree: true });

  // ─── GIF animation restart ────────────────────────────────────────────
  // The browser starts playing a GIF as soon as the <img> src is set, but
  // the card may not be visible yet (Vue render cycle + compositing delay).
  // When a new GIF <img> appears inside a .sage-popout card, wait two
  // animation frames (card is now painted) then reset the src so the
  // animation restarts from frame 0. Both assignments are synchronous so
  // no blank frame is visible between them.
  (new MutationObserver(function (mutations) {
    mutations.forEach(function (m) {
      m.addedNodes.forEach(function (node) {
        if (node.nodeType !== 1) return;
        var imgs = node.tagName === 'IMG' ? [node] : node.querySelectorAll('img');
        imgs.forEach(function (img) {
          if (!img.src || img.src.indexOf('data:image/gif') !== 0) return;
          // Only reset if this img is inside a library pop-out card.
          if (!img.closest || !img.closest('.sage-popout')) return;
          var src = img.src;
          requestAnimationFrame(function () {
            requestAnimationFrame(function () {
              img.src = '';
              img.src = src;
            });
          });
        });
      });
    });
  })).observe(document.body, { childList: true, subtree: true });

  // ─── Story Mode text / equation overlays ──────────────────────────
  // Overlays are rendered ENTIRELY by this code, not by Vue: the server ships
  // a JSON list in the hidden #sage-overlays-relay input, and we build the
  // children of #sage-overlay-root ourselves. Vue owns the container element
  // but never its children, so KaTeX's DOM writes can't corrupt Vue's vDOM.
  (function () {
    // Write a scene-selector cell's index to the hidden goto relay so Vue's
    // reactivity carries it to the server (the only external-JS → server path
    // in Trame 3). A monotonic seq forces a state change on repeat clicks.
    var _nativeSet = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype, 'value'
    ).set;
    var _gotoSeq = 0;

    // ── Fixed overlay stage ───────────────────────────────────────────
    // Every slide is authored against a fixed virtual canvas (default 16:9,
    // overridable via #sage-overlay-root's data-stage-w/h). We build all
    // overlays inside a #sage-overlay-stage of exactly that pixel size, then
    // scale it uniformly to fit the render area. Because text (rem), image
    // widths (px) and positions (% of the stage) are ALL measured against the
    // same fixed canvas, the layout is locked: it keeps its exact proportions
    // and never overlaps — the whole slide just grows/shrinks as one unit to
    // fit any window or screen size.
    var STAGE_W = 1600, STAGE_H = 900;
    var _stage = null;
    function ensureStage(root) {
      if (_stage && _stage.parentNode === root) return _stage;
      var dw = parseFloat(root.getAttribute('data-stage-w'));
      var dh = parseFloat(root.getAttribute('data-stage-h'));
      if (dw > 0) STAGE_W = dw;
      if (dh > 0) STAGE_H = dh;
      _stage = document.createElement('div');
      _stage.id = 'sage-overlay-stage';
      _stage.style.cssText =
        'position:absolute;left:0;top:0;pointer-events:none;' +
        'transform-origin:0 0;' +
        'width:' + STAGE_W + 'px;height:' + STAGE_H + 'px;';
      root.appendChild(_stage);
      return _stage;
    }
    function fitStage(root) {
      if (!_stage) return;
      var rw = root.clientWidth, rh = root.clientHeight;
      if (!rw || !rh) return;            // hidden (display:none) — nothing to fit
      // Contain: fit the whole canvas inside the render area (letterbox), so no
      // slide content is ever clipped and the layout is identical everywhere.
      var s = Math.min(rw / STAGE_W, rh / STAGE_H);
      var tx = (rw - STAGE_W * s) / 2;   // centre the scaled canvas
      var ty = (rh - STAGE_H * s) / 2;
      _stage.style.transform =
        'translate(' + tx + 'px,' + ty + 'px) scale(' + s + ')';
    }
    function _gotoScene(index) {
      var el = document.getElementById('sage-story-goto-relay');
      if (!el) return;
      _nativeSet.call(el, String(index) + ':' + (_gotoSeq++));
      el.dispatchEvent(new Event('input', { bubbles: true }));
    }

    function makeMenu(it) {
      // Clickable grid of scenes (the scene_menu overlay). The container stays
      // click-through; only the cells take pointer events so the camera below
      // is still draggable in the gaps.
      var wrap = document.createElement('div');
      wrap.style.cssText = it.style || '';
      var grid = document.createElement('div');
      grid.style.cssText =
        'display:grid;gap:14px;pointer-events:auto;' +
        'grid-template-columns:repeat(' + (it.cols || 4) + ',1fr);' +
        // % of the fixed stage width (not vw) so it scales with the stage.
        'max-width:' + ((it.max_width || 90) / 100 * STAGE_W) + 'px;';
      if (it.title) {
        var h = document.createElement('div');
        h.textContent = it.title;
        h.style.cssText =
          'grid-column:1/-1;text-align:center;color:#fff;font-weight:700;' +
          'font-size:2rem;text-shadow:0 2px 8px rgba(0,0,0,0.8);';
        grid.appendChild(h);
      }
      (it.cells || []).forEach(function (c) {
        var cell = document.createElement('div');
        cell.style.cssText =
          'cursor:pointer;border:1px solid #06b6d4;border-radius:8px;' +
          'overflow:hidden;background:rgba(8,12,20,0.72);' +
          'display:flex;flex-direction:column;transition:transform .12s;';
        cell.onmouseenter = function () { cell.style.transform = 'scale(1.04)'; };
        cell.onmouseleave = function () { cell.style.transform = 'scale(1)'; };
        if (c.thumb) {
          var im = document.createElement('img');
          im.src = c.thumb;
          im.style.cssText = 'width:100%;height:auto;display:block;';
          cell.appendChild(im);
        } else {
          var ph = document.createElement('div');
          ph.textContent = c.n;
          ph.style.cssText =
            'aspect-ratio:16/9;display:flex;align-items:center;' +
            'justify-content:center;font-size:2rem;color:#334155;' +
            'background:#0b1220;';
          cell.appendChild(ph);
        }
        var lab = document.createElement('div');
        lab.textContent = c.n + '. ' + c.label;
        lab.style.cssText =
          'padding:6px 8px;color:#e2e8f0;font-size:0.85rem;' +
          'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;';
        cell.appendChild(lab);
        cell.onclick = function () { _gotoScene(c.index); };
        grid.appendChild(cell);
      });
      wrap.appendChild(grid);
      return wrap;
    }

    function makeItem(it) {
      // Scene-selector grid (clickable thumbnails of every scene).
      if (it.menu) return makeMenu(it);
      // Video overlays (e.g. the TNG movie) carry a src + the video flag.
      // Muted is required for browsers to honour autoplay.
      if (it.video) {
        var vid = document.createElement('video');
        vid.src = it.src;
        vid.style.cssText = it.style || '';
        vid.loop = it.loop !== false;
        vid.muted = it.muted !== false;
        vid.autoplay = it.autoplay !== false;
        vid.controls = !!it.controls;
        vid.playsInline = true;
        if (vid.autoplay) {
          var p = vid.play();
          if (p && p.catch) p.catch(function () {});
        }
        return vid;
      }
      // Audio overlays (e.g. a short intro sting) carry a src + the audio flag
      // and render no visible element. They play independently of the engine,
      // so the run() loop pauses/resumes them with the show's play/pause state.
      if (it.audio) {
        var au = document.createElement('audio');
        au.src = it.src;
        au.loop = !!it.loop;
        au.muted = !!it.muted;
        au.volume = (it.volume == null) ? 1.0 : it.volume;
        au.autoplay = it.autoplay !== false;
        au.style.cssText =
          'position:absolute;width:0;height:0;opacity:0;pointer-events:none;';
        if (au.autoplay) {
          var pa = au.play();
          if (pa && pa.catch) pa.catch(function () {});
        }
        return au;
      }
      // Image overlays (logos etc.) carry a src instead of text/latex.
      if (it.src != null) {
        var img = document.createElement('img');
        img.src = it.src;
        img.style.cssText = it.style || '';
        return img;
      }
      var d = document.createElement('div');
      d.style.cssText = it.style || '';
      if (it.latex != null && window.katex) {
        try {
          window.katex.render(it.latex, d, {
            displayMode: !!it.display,
            throwOnError: false,
          });
        } catch (e) {
          d.textContent = it.latex;  // fall back to raw source
        }
      } else if (it.latex != null) {
        d.textContent = it.latex;    // KaTeX not loaded yet
      } else {
        d.textContent = it.text || '';
      }
      return d;
    }

    function run() {
      var relay = document.getElementById('sage-overlays-relay');
      var root = document.getElementById('sage-overlay-root');
      var playRelay = document.getElementById('sage-story-playing-relay');
      if (!relay || !root) { setTimeout(run, 200); return; }
      var stage = ensureStage(root);
      fitStage(root);
      // Re-fit the stage whenever the render area changes size — window resize,
      // and (via ResizeObserver) the panel showing/hiding or any layout shift.
      window.addEventListener('resize', function () { fitStage(root); });
      if (typeof ResizeObserver !== 'undefined') {
        new ResizeObserver(function () { fitStage(root); }).observe(root);
      }
      var last = null;
      var lastPlaying = null;
      function tick() {
        var v = relay.value || '[]';
        if (v !== last) {
          var items = [];
          try { items = JSON.parse(v); } catch (e) { items = []; }
          // If equations are present but KaTeX hasn't loaded yet (scripts load
          // asynchronously), retry next tick instead of caching raw LaTeX.
          var needsKatex = items.some(function (it) { return it.latex != null; });
          if (needsKatex && !window.katex) { setTimeout(tick, 100); return; }
          last = v;
          stage.innerHTML = '';
          items.forEach(function (it) { stage.appendChild(makeItem(it)); });
          fitStage(root);   // new content may mount while the area is a new size
          // Fade the fresh overlay set in so a scene change doesn't pop its
          // text/logos on. Reset opacity with transitions off, force a
          // reflow so the reset lands, then animate to visible. (Opacity only —
          // the scale transform stays instant so there's no zoom on fade-in.)
          if (items.length) {
            stage.style.transition = 'none';
            stage.style.opacity = '0';
            void stage.offsetWidth;
            stage.style.transition = 'opacity 0.35s ease';
            stage.style.opacity = '1';
          }
          // Re-apply the show's play/pause state to the rebuilt <audio> set
          // (so audio only sounds while the show is playing).
          lastPlaying = null;
        }
        // <audio> overlays play independently of the engine, so Pause must
        // silence them and Play must resume them explicitly.
        if (playRelay) {
          var pv = playRelay.value;
          if (pv !== lastPlaying) {
            lastPlaying = pv;
            var playing = (pv === 'true' || pv === 'True' || pv === '1');
            var auds = stage.getElementsByTagName('audio');
            for (var i = 0; i < auds.length; i++) {
              if (playing) {
                var pr = auds[i].play();
                if (pr && pr.catch) pr.catch(function () {});
              } else {
                auds[i].pause();
              }
            }
          }
        }
        setTimeout(tick, 150);
      }
      tick();
    }
    run();
  })();

})();

// Masses and units typeset wherever they appear: M*, Msun, yr^-1, 10^n and
// so on. A text node is kept (hidden, so Vue can still update it) beside a
// rendered copy.
(function () {
  var RULES = [
    [/\b([MZ])\*/g, '$1<sub>⋆</sub>'],
    [/\b([MLZ])☉/g, '$1<sub class="sun">☉</sub>'],
    [/\b([MRV])(vir|max)\b/g, '$1<sub>$2</sub>'],
    [/\bMsun\b/g, 'M<sub class="sun">☉</sub>'],
    [/\bLsun\b/g, 'L<sub class="sun">☉</sub>'],
    [/(\d\.\d+)e([+-])0*(\d+)/g, function (m, a, s, b) {
      return a + '×10<sup>' + (s === '-' ? '−' : '') + b + '</sup>';
    }],
    [/\b10\^(-?\d+)/g, '10<sup>$1</sup>'],
    [/\b([A-Za-z]+)\^-(\d+)/g, '$1<sup>−$2</sup>'],
    [/\b([A-Za-z]+)\^(\d+)/g, '$1<sup>$2</sup>'],
    [/\blog10\b/g, 'log<sub>10</sub>'],
    [/\bH([12])\b/g, 'H<sub>$1</sub>'],
    [/\bA_V\b/g, 'A<sub>V</sub>'],
    [/\b([MRgt])_([A-Za-z]+)/g, '$1<sub>$2</sub>'],
  ];
  var SKIP = 'script,style,textarea,input,code,svg,.xterm,.katex,.sage-rich,' +
    '[data-sage-raw]';
  function escapeHtml(s) {
    return s.replace(/[&<>]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c];
    });
  }
  function typeset(text) {
    var out = escapeHtml(text);
    RULES.forEach(function (r) { out = out.replace(r[0], r[1]); });
    return out;
  }
  function wrap(node) {
    var html = typeset(node.nodeValue);
    if (html === escapeHtml(node.nodeValue)) return;
    var rich = document.createElement('span');
    rich.className = 'sage-rich';
    rich.innerHTML = html;
    var raw = document.createElement('span');
    raw.setAttribute('data-sage-raw', '');
    raw.style.display = 'none';
    node.parentNode.insertBefore(rich, node);
    node.parentNode.insertBefore(raw, node);
    raw.appendChild(node);
  }
  function scan(root) {
    if (root.nodeType === 3) {
      var p = root.parentElement;
      if (p && !p.closest(SKIP)) wrap(root);
      return;
    }
    if (root.nodeType !== 1 || root.closest(SKIP)) return;
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    var found = [];
    while (walker.nextNode()) found.push(walker.currentNode);
    found.forEach(function (n) {
      if (!n.parentElement.closest(SKIP)) wrap(n);
    });
  }
  new MutationObserver(function (changes) {
    changes.forEach(function (c) {
      var raw = c.target.parentElement;
      if (c.type === 'characterData') {
        if (raw && raw.hasAttribute('data-sage-raw')) {
          raw.previousSibling.innerHTML = typeset(c.target.nodeValue);
        } else scan(c.target);
        return;
      }
      if (c.target.hasAttribute && c.target.hasAttribute('data-sage-raw')) {
        if (!c.target.firstChild) {
          c.target.previousSibling.remove();
          c.target.remove();
        }
        return;
      }
      c.addedNodes.forEach(scan);
    });
  }).observe(document.documentElement, {
    subtree: true, childList: true, characterData: true,
  });
  window.addEventListener('load', function () { scan(document.body); });
})();

// The animation on a long job's card, one for each kind of job.  It only
// runs while a card is on screen.
(function () {
  var W = 120, H = 80;
  var COL = ['#22d3ee', '#c084fc', '#ffd700', '#fb7185', '#34d399'];

  function dot(c, x, y, r, col, a) {
    c.globalAlpha = a === undefined ? 1 : a;
    c.fillStyle = col;
    c.beginPath();
    c.arc(x, y, r, 0, 7);
    c.fill();
    c.globalAlpha = 1;
  }
  function glow(c, x, y, r, col) {
    var g = c.createRadialGradient(x, y, 0, x, y, r);
    g.addColorStop(0, col);
    g.addColorStop(1, 'transparent');
    c.fillStyle = g;
    c.fillRect(x - r, y - r, 2 * r, 2 * r);
  }

  var nodes = [], links = [], arms = [];
  (function () {
    var i, j, seed = 7;
    function rnd() {
      seed = (seed * 16807) % 2147483647;
      return seed / 2147483647;
    }
    for (i = 0; i < 14; i++) {
      nodes.push({
        x: 8 + rnd() * 104, y: 6 + rnd() * 68,
        c: COL[i % 5], p: rnd() * 6,
      });
    }
    for (i = 0; i < 14; i++) {
      for (j = i + 1; j < 14; j++) {
        var d = Math.hypot(nodes[i].x - nodes[j].x, nodes[i].y - nodes[j].y);
        if (d < 44) links.push([i, j]);
      }
    }
    for (i = 0; i < 150; i++) {
      arms.push({
        a: (i % 2) * Math.PI + (i / 150) * 5,
        r: 2 + (i / 150) * 34, f: i / 150, j: rnd() * 2,
      });
    }
  })();

  function web(c, t, pulses) {
    c.lineWidth = 0.6;
    c.strokeStyle = 'rgba(148,163,184,0.28)';
    links.forEach(function (l, k) {
      var a = nodes[l[0]], b = nodes[l[1]];
      c.beginPath();
      c.moveTo(a.x, a.y);
      c.lineTo(b.x, b.y);
      c.stroke();
      if (pulses) {
        var f = (t * 0.35 + k * 0.13) % 1;
        dot(c, a.x + (b.x - a.x) * f, a.y + (b.y - a.y) * f, 1.2, a.c);
      }
    });
    nodes.forEach(function (n) {
      glow(c, n.x, n.y, 6 + 1.8 * Math.sin(t * 2 + n.p), n.c + 'cc');
      dot(c, n.x, n.y, 1.4, '#fff');
    });
  }

  var DRAW = {
    web: function (c, t) { web(c, t, true); },
    // One galaxy travelling the web, leaving a trail.
    track: function (c, t) {
      web(c, t, false);
      var at = function (u) {
        var n = links.length, f = u % n, i = Math.floor(f), l = links[i];
        var a = nodes[l[0]], b = nodes[l[1]], g = f - i;
        return [a.x + (b.x - a.x) * g, a.y + (b.y - a.y) * g];
      };
      for (var k = 14; k >= 0; k--) {
        var p = at(t * 1.1 - k * 0.05);
        dot(c, p[0], p[1], 2.4 - k * 0.14, '#ffd700', 1 - k / 15);
      }
    },
    orbits: function (c, t) {
      var x = W / 2, y = H / 2;
      glow(c, x, y, 14, '#ffd70099');
      dot(c, x, y, 2.6, '#fff');
      COL.forEach(function (col, i) {
        var r = 11 + i * 6.5, w = 1.6 / (1 + i * 0.45);
        for (var k = 0; k < 12; k++) {
          var a = t * w + i * 1.3 - k * 0.07;
          dot(c, x + Math.cos(a) * r, y + Math.sin(a) * r * 0.6,
              1.9 - k * 0.13, col, 1 - k / 12);
        }
      });
    },
    spiral: function (c, t) {
      var x = W / 2, y = H / 2;
      glow(c, x, y, 20, '#ffd70088');
      arms.forEach(function (s) {
        var a = s.a + t * 0.6;
        var col = s.f < 0.3 ? '#ffd700' : s.f < 0.6 ? '#fb7185'
          : s.f < 0.8 ? '#c084fc' : '#22d3ee';
        dot(c, x + Math.cos(a) * s.r + s.j - 1,
            y + Math.sin(a) * s.r * 0.55 + s.j - 1, 0.9, col, 0.9);
      });
    },
    // A spectrum: a wave running through the colours.
    wave: function (c, t) {
      for (var x = 2; x < W - 2; x += 2) {
        var f = x / W, e = Math.sin(f * Math.PI);
        var y = H / 2 + Math.sin(f * 14 - t * 3) * 22 * e;
        dot(c, x, y, 1.3, 'hsl(' + (280 - f * 280) + ',90%,65%)');
      }
    },
  };

  function frame(ms) {
    var shown = 0;
    document.querySelectorAll('canvas.sage-anim').forEach(function (cv) {
      if (cv.offsetParent === null) return;
      shown++;
      if (cv.width !== W * 3) {
        cv.width = W * 3;
        cv.height = H * 3;
      }
      var kind = (cv.className.match(/sage-anim-(\w+)/) || [])[1];
      var c = cv.getContext('2d');
      c.setTransform(3, 0, 0, 3, 0, 0);
      c.clearRect(0, 0, W, H);
      if (DRAW[kind]) DRAW[kind](c, ms / 1000);
    });
    if (shown) requestAnimationFrame(frame);
    else setTimeout(function () { requestAnimationFrame(frame); }, 300);
  }
  requestAnimationFrame(frame);
})();
