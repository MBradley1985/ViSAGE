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
    }
    document.addEventListener('mousemove', mv);
    document.addEventListener('mouseup',   up);
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

  // ─── HD Components: labels and leader lines over the view ─────────
  // hd_labels (from the server): [{t, x, y, lx, ly, side}], positions as
  // fractions of the view, y down.  Drawn as an SVG in #hd-labels.
  var hdLabels = [];
  function drawHdLabels() {
    var host = document.getElementById('hd-labels');
    if (!host) return;
    // The leader lines live in a sibling layer blended by "difference":
    // white over the dark sky, black over the bright galaxy.  (A blend
    // only reaches the view behind from its own top-level layer.)
    var lines = document.getElementById('hd-label-lines');
    if (!lines) {
      lines = document.createElement('div');
      lines.id = 'hd-label-lines';
      lines.style.cssText = 'position:absolute;inset:0;z-index:5;' +
        'pointer-events:none;mix-blend-mode:difference;';
      host.parentNode.insertBefore(lines, host);
    }
    var W = host.clientWidth, H = host.clientHeight;
    if (!hdLabels.length || !W || !H) {
      host.innerHTML = ''; lines.innerHTML = ''; return;
    }
    var esc = function (s) {
      return String(s).replace(/[&<>"]/g, function (c) {
        return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
      });
    };
    // Keep labels off the selection card: those that would sit on it
    // move below it (left edge) or past it (top edge).
    var labels = hdLabels.map(function (l) { return Object.assign({}, l); });
    var card = document.getElementById('sel-card');
    if (card && card.offsetParent) {
      var hr = host.getBoundingClientRect(), cr = card.getBoundingClientRect();
      var cR = cr.right - hr.left + 12, cB = cr.bottom - hr.top + 14;
      var below = cB + 10;
      labels.filter(function (l) { return l.side === 'left'; })
        .sort(function (a, b) { return a.ly - b.ly; })
        .forEach(function (l) {
          if (l.ly * H < cB && l.lx * W < cR) {
            l.ly = below / H; below += 0.06 * H;
          } else if (l.ly * H < below) {
            l.ly = below / H; below += 0.06 * H;
          }
        });
      labels.filter(function (l) { return l.side === 'top'; })
        .forEach(function (l) {
          var half = 4.3 * l.t.length;
          if (l.lx * W - half < cR) l.lx = (cR + half + 8) / W;
        });
    }
    var color = window.visageLabelColor || '#FFD700';
    var head = '<svg width="' + W + '" height="' + H +
      '" style="position:absolute;left:0;top:0;overflow:visible">';
    var svg = head, lsvg = head;
    labels.forEach(function (l) {
      var ax = l.x * W, ay = l.y * H, lx = l.lx * W, ly = l.ly * H;
      var tw = 8.6 * l.t.length;  // label width, approx. (bold caps 15px)
      var pts, tx, ty, anchor;
      if (l.side === 'left' || l.side === 'right') {
        var left = l.side === 'left';
        var ex = left ? lx + tw + 8 : lx - tw - 8;  // where the line starts
        var kx = left ? Math.max(ex + 14, Math.min(ax - 20, ex + 60))
                      : Math.min(ex - 14, Math.max(ax + 20, ex - 60));
        pts = ex + ',' + ly + ' ' + kx + ',' + ly + ' ' + ax + ',' + ay;
        tx = lx; ty = ly + 5; anchor = left ? 'start' : 'end';
      } else {
        // Top / bottom: the label centred, the line dropping (rising) to
        // an elbow, then to the part.
        var top = l.side === 'top';
        var ey = top ? ly + 8 : ly - 18;
        var ky = top ? Math.max(ey + 12, Math.min(ay - 20, ey + 50))
                     : Math.min(ey - 12, Math.max(ay + 20, ey - 50));
        pts = lx + ',' + ey + ' ' + lx + ',' + ky + ' ' + ax + ',' + ay;
        tx = lx; ty = ly + 5; anchor = 'middle';
      }
      lsvg += '<polyline points="' + pts + '" fill="none" ' +
        'stroke="#fff" stroke-width="1.3"/>';
      lsvg += '<circle cx="' + ax + '" cy="' + ay + '" r="3" fill="none" ' +
        'stroke="#fff" stroke-width="1.5"/>';
      svg += '<text x="' + tx + '" y="' + ty + '" text-anchor="' + anchor +
        '" fill="' + color + '" font-size="15" font-weight="700" ' +
        'letter-spacing="0.6" ' +
        'font-family="Oswald, \'Arial Narrow\', Arial, sans-serif" ' +
        'style="paint-order:stroke;stroke:rgba(0,0,0,0.7);stroke-width:3px">' +
        esc(l.t) + '</text>';
    });
    host.innerHTML = svg + '</svg>';
    lines.innerHTML = lsvg + '</svg>';
  }
  (function watchHdLabels() {
    var t = window.trame;
    if (!t || !t.state || !t.state.watch) { setTimeout(watchHdLabels, 300); return; }
    t.state.watch(['hd_labels'], function (labels) {
      hdLabels = labels || [];
      drawHdLabels();
    });
    // The card opening or closing moves labels on or off it.
    t.state.watch(['sel_show'], function () { setTimeout(drawHdLabels, 80); });
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

    // A card that covers the page while ViSAGE restarts on another model.
    // Plain DOM on <body>, so it outlives the app's own "Connection closed"
    // screen until the page reloads.
    function _showRelaunchCard(name) {
      if (document.getElementById('visage-relaunch')) return;
      var d = document.createElement('div');
      d.id = 'visage-relaunch';
      d.style.cssText = 'position:fixed;inset:0;z-index:100000;background:#000;' +
        'display:flex;flex-direction:column;align-items:center;justify-content:center;' +
        'gap:18px;font-family:system-ui,sans-serif;color:#e2e8f0;';
      var sp = document.createElement('div');
      sp.style.cssText = 'width:46px;height:46px;border-radius:50%;' +
        'border:3px solid #1e293b;border-top-color:#22d3ee;' +
        'animation:visage-spin 0.9s linear infinite;';
      var t = document.createElement('div');
      t.style.cssText = 'font-size:1.35rem;font-weight:700;';
      t.textContent = 'Opening ' + name;
      var st = document.createElement('style');
      st.textContent = '@keyframes visage-spin{to{transform:rotate(360deg)}}';
      d.appendChild(st); d.appendChild(sp); d.appendChild(t);
      document.body.appendChild(d);
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

// Regions tab: draw a lasso or rectangle over the view, or click. The stroke
// goes to the server as 0 to 1 from the view's top left.
(function () {
  var pts = null;
  function place(host, e) {
    var r = host.getBoundingClientRect();
    return [(e.clientX - r.left) / r.width, (e.clientY - r.top) / r.height];
  }
  function draw(host, tool) {
    var svg = host.querySelector('svg');
    if (!svg) {
      svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      svg.setAttribute('viewBox', '0 0 1 1');
      svg.setAttribute('preserveAspectRatio', 'none');
      svg.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;' +
        'pointer-events:none;';
      svg.innerHTML = '<polygon fill="rgba(34,211,238,.12)" stroke="#22d3ee" ' +
        'stroke-width="1.5" vector-effect="non-scaling-stroke"/>';
      host.appendChild(svg);
    }
    var p = pts || [];
    if (tool === 'rectangle' && p.length > 1) {
      var a = p[0], b = p[p.length - 1];
      p = [a, [b[0], a[1]], b, [a[0], b[1]]];
    }
    svg.firstChild.setAttribute('points', p.map(function (q) {
      return q.join(',');
    }).join(' '));
  }
  document.addEventListener('mousedown', function (e) {
    var host = e.target.closest && e.target.closest('#region-draw');
    if (!host) return;
    pts = [place(host, e)];
    e.preventDefault();
  });
  document.addEventListener('mousemove', function (e) {
    var host = document.getElementById('region-draw');
    if (!pts || !host) return;
    pts.push(place(host, e));
    draw(host, window.trame.state.get('region_tool'));
  });
  document.addEventListener('mouseup', function () {
    var host = document.getElementById('region-draw');
    if (!pts || !host) return;
    var t = window.trame, stroke = pts;
    pts = null;
    draw(host);
    t.trigger('region_pick', [t.state.get('region_tool'), stroke]);
  });
})();
