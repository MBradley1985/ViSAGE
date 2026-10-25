from __future__ import annotations

from trame.widgets import html
from trame.widgets import vuetify3 as v3

from visage.wizard.controller import WizardController, _STEPS, _MAX_PARAMS

_WIZ_CSS = """
.wiz-title { color: #06b6d4; font-weight: 700; letter-spacing: 0.08em; }
.wiz-ok    { color: #22c55e; }
.wiz-warn  { color: #f59e0b; }
.wiz-err   { color: #ef4444; font-weight: 600; }
.wiz-cmd   { color: #06b6d4; }
.wiz-out   { color: #9ca3af; }
.wiz-sep   { color: #374151; }
.wiz-info  { color: #e2e8f0; }
/* Par-file textarea: match terminal font size, override DOS-blue theme */
.wiz-par-area .v-field__input,
.wiz-par-area textarea { font-size: 0.75rem !important; line-height: 1.45 !important; }
/* Home cards and mode-screen buttons */
.wiz-big { cursor: pointer; transition: transform 0.15s ease, box-shadow 0.15s ease,
  border-color 0.15s ease, filter 0.15s ease; font-family: 'Space Grotesk',
  'Segoe UI', system-ui, -apple-system, sans-serif; }
.wiz-big:hover:not(:disabled) { transform: translateY(-3px);
  box-shadow: 0 14px 40px rgba(0, 0, 0, 0.6), 0 0 0 1px rgba(255, 255, 255, 0.25); }
.wiz-big:focus-visible { outline: 2px solid #22d3ee; outline-offset: 3px; }
.wiz-big:disabled { cursor: not-allowed; opacity: 0.4; }
.wiz-big.wiz-busy:disabled { cursor: progress; opacity: 1; }
@keyframes wiz-pulse { 0%, 100% { box-shadow: 0 0 0 0 rgba(34, 211, 238, 0.0); }
  50% { box-shadow: 0 0 0 3px rgba(34, 211, 238, 0.45), 0 0 28px rgba(34, 211, 238, 0.25); } }
.wiz-busy { animation: wiz-pulse 1.2s ease-in-out infinite; }
@keyframes wiz-spin { to { transform: rotate(360deg); } }
.wiz-spin { animation: wiz-spin 1s linear infinite; }
@media (prefers-reduced-motion: reduce) { .wiz-busy, .wiz-spin { animation: none; } }
/* SAGEswarm particles: waiting ones pulse, run ones pop in */
.wiz-dot { width: 12px; height: 12px; border-radius: 50%; border: 1.5px solid;
  box-sizing: border-box; animation: wiz-wait 1.4s ease-in-out infinite; }
.wiz-dot-on { animation: wiz-pop 0.35s ease-out; }
@keyframes wiz-wait { 0%, 100% { opacity: 0.35; } 50% { opacity: 1; } }
@keyframes wiz-pop { 0% { transform: scale(0.4); } 70% { transform: scale(1.25); }
  100% { transform: scale(1); } }
@media (prefers-reduced-motion: reduce) { .wiz-dot, .wiz-dot-on { animation: none; } }
.wiz-sans { font-family: 'Space Grotesk', 'Segoe UI', system-ui, -apple-system, sans-serif; }
/* One font on every page: Vuetify's fields, labels and buttons too; the
   terminal keeps its own. */
.wiz-sans *:not(.v-icon):not(.mdi) { font-family: inherit; }
.wiz-sans .xterm, .wiz-sans .xterm * {
  font-family: "Menlo", "Monaco", "Consolas", "DejaVu Sans Mono", monospace; }
@font-face { font-family: 'Space Grotesk'; font-style: normal;
  font-weight: 300 700; font-display: swap;
  src: url('/sage_static/fonts/SpaceGrotesk-wght.woff2') format('woff2'); }
"""


def build_wizard_ui(server, ctrl: WizardController) -> None:
    import base64 as _b64

    css_url = (
        "data:text/css;charset=utf-8;base64,"
        + _b64.b64encode(_WIZ_CSS.encode()).decode()
    )

    with html.Div(
        style=(
            "display:flex;flex-direction:column;height:100%;"
            "background:#000000;font-family:monospace;"
            "position:relative;"
        ),
    ):
        html.Link(rel="stylesheet", href=css_url)
        # The wizard terminal asking for output it missed (visage.js).
        html.Input(
            id="wiz-pty-need-relay",
            v_model=("wiz_pty_need",),
            type="text",
            style=(
                "position:fixed;left:-9999px;width:1px;height:1px;"
                "opacity:0;pointer-events:none;"
            ),
        )
        # The wizard terminal's size, from visage.js ("cols,rows").
        html.Input(
            id="wiz-term-size-relay",
            v_model=("wiz_term_size",),
            type="text",
            style=(
                "position:fixed;left:-9999px;width:1px;height:1px;"
                "opacity:0;pointer-events:none;"
            ),
        )

        # ── Header ──────────────────────────────────────────────────────────
        with html.Div(
            style=(
                "background:#000000;border-bottom:2px solid #06b6d4;"
                "padding:10px 20px;display:flex;align-items:center;gap:12px;"
                "flex-shrink:0;"
            ),
        ):
            v3.VIcon("mdi-rocket-launch", color="#06b6d4", size="large")
            html.Span(
                "ViSAGE",
                style="font-size:1.3rem;font-weight:700;color:#06b6d4;",
            )
            html.Span(
                "Launch Mode",
                style=(
                    "font-size:1.0rem;color:#06b6d4;"
                    "border:1px solid #06b6d4;padding:2px 8px;"
                ),
            )
            v3.VSpacer()
            # Rescan button — to the left of the step chips
            v3.VBtn(
                "Rescan",
                prepend_icon="mdi-refresh",
                color="#06b6d4",
                variant="outlined",
                size="x-small",
                click=server.controller.wiz_rescan,
                style=(
                    "font-family:monospace;text-transform:none;"
                    "margin-right:10px;"
                ),
            )
            # Step indicator chips — labels come from the `wiz_steps` state var
            # so they swap per flow (SAGE26 vs SAGEswarm); count is fixed (6).
            with html.Div(style="display:flex;gap:6px;align-items:center;"):
                for i in range(len(_STEPS)):
                    v3.VChip(
                        "{{ wiz_steps[" + str(i) + "] }}",
                        size="small",
                        color=(
                            f"wiz_step === {i} ? '#06b6d4' : "
                            f"(wiz_step > {i} ? '#22c55e' : '#e2e8f0')",
                        ),
                        variant=(
                            f"wiz_step === {i} ? 'elevated' : 'outlined'",
                        ),
                        style="font-family:monospace;font-size:0.7rem;",
                    )
            # Close button — only shown when embedded in Explore Mode
            v3.VBtn(
                icon="mdi-close",
                variant="text",
                color="#9ca3af",
                size="small",
                title="Close wizard and return to Explore Mode",
                click=server.controller.wiz_close,
                v_show=("wiz_active !== undefined",),
                style="margin-left:8px;",
            )

        # ── Main area ────────────────────────────────────────────────────────
        # paddingRight reserves space for the live PSO gallery (fixed, docked
        # right) so the terminal is never hidden under it; overflowX lets the
        # user scroll horizontally if the content is still wider than the gap.
        with html.Div(
            # The home page sits centred; every other page fills the area.
            style=(
                "{flex:'1',minHeight:0,display:'flex',"
                "alignItems: wiz_view === 'home' ? 'center' : 'stretch',"
                "justifyContent:'center',overflowX:'auto',overflowY:'hidden',"
                "padding: wiz_view === 'home' ? '24px' : '28px 40px',"
                "paddingRight: pso_gallery_show "
                "? 'calc(min(46vw, 720px) + 24px)' : '24px'}",
            ),
        ):
            _home_view(server)
            _mode_view(server)
            _pick_view(server)
            _setup_view(server)
            _all_settings_view(server)
            _run_view(server)
            # Row wrapper — expands to two columns when an editor is visible.
            # Kept mounted (v-show) so the xterm terminal survives view
            # switches.
            with html.Div(
                v_show=("wiz_view === 'term'",),
                style=(
                    "{"
                    "display:'flex',gap:'16px',alignItems:'stretch',"
                    "width:'100%',maxWidth:'1240px',margin:'0 auto',"
                    "justifyContent: (wiz_par_show || wiz_sw_config_show || "
                    "wiz_lc_config_show || pso_gallery_show) "
                    "? 'flex-start' : 'center'"
                    "}",
                ),
            ):
                # ── Left: terminal card ───────────────────────────────────────
                with v3.VCard(
                    style=(
                        "`flex:1;min-width:0;"
                        "background:#000000;border-radius:14px;"
                        "display:grid;grid-template-rows:1fr auto;"
                        "overflow:hidden;position:relative;`",
                    ),
                    elevation=0,
                    rounded=False,
                ):
                    # xterm.js terminal — receives raw PTY bytes from the server.
                    # grid-template-rows:1fr auto gives this a hard pixel height
                    # (card height minus action-bar height) so fitAddon.fit()
                    # always sees the correct dimensions without JS timing tricks.
                    html.Div(
                        id="sage-wiz-pty",
                        style=(
                            "min-height:0;overflow:hidden;"
                            "background:#000000;"
                        ),
                    )

                    # Action bar
                    with html.Div(
                        classes="wiz-sans",
                        style=(
                            "border-top:1px solid #374151;"
                            "background:#000000;"
                            "padding:10px 14px;"
                            "flex-shrink:0;"
                            "display:flex;flex-direction:column;gap:8px;"
                        ),
                    ):
                        v3.VProgressLinear(
                            v_show=("wiz_busy",),
                            indeterminate=True,
                            color="#06b6d4",
                            height=3,
                            style="width:100%;",
                        )
                        # Filename input — shown when creating a new config file
                        with html.Div(
                            v_show=("wiz_filename_show",),
                            style="display:flex;align-items:center;gap:8px;",
                        ):
                            v3.VTextField(
                                v_model=("wiz_filename",),
                                label="Config file name",
                                variant="outlined",
                                density="compact",
                                color="cyan",
                                bg_color="#000000",
                                hide_details=True,
                                suffix=".par",
                                style="max-width:320px;",
                            )
                        # Clone directory input — shown before cloning SAGE26
                        with html.Div(
                            v_show=("wiz_clone_dir_show",),
                            style="display:flex;align-items:center;gap:8px;",
                        ):
                            v3.VTextField(
                                v_model=("wiz_clone_dir",),
                                label="Parent directory (SAGE26 will be created inside)",
                                variant="outlined",
                                density="compact",
                                color="cyan",
                                bg_color="#000000",
                                hide_details=True,
                                style="max-width:520px;",
                            )
                        # Cancel button — shown whenever a command is running;
                        # sends SIGINT (Ctrl+C) to the process group.
                        with html.Div(
                            v_show=("wiz_run_active",),
                            style="display:flex;align-items:center;gap:8px;",
                        ):
                            with html.Button(
                                type="button",
                                classes="wiz-big",
                                click=server.controller.wiz_cancel_run,
                                style=(
                                    "height:42px;padding:0 18px;"
                                    "border-radius:12px;border:1px solid #ef4444;"
                                    "background:transparent;color:#fca5a5;"
                                    "font-size:0.95rem;"
                                ),
                            ):
                                html.Span("Cancel")
                        with html.Div(
                            v_show=("!wiz_busy && wiz_choices.length > 0",),
                            style=(
                                "display:flex;flex-wrap:wrap;gap:10px;"
                                "justify-content:center;"
                                "max-height:120px;overflow-y:auto;"
                            ),
                        ):
                            with html.Button(
                                v_for="(ch, ci) in wiz_choices",
                                key="ci",
                                type="button",
                                classes="wiz-big",
                                disabled=("ch.disabled",),
                                click=(
                                    server.controller.wiz_choose,
                                    "[ch.value]",
                                ),
                                style=(
                                    "height:42px;padding:0 18px;border-radius:12px;"
                                    "border:1px solid #334155;background:#0b1120;"
                                    "color:#e2e8f0;font-size:0.95rem;display:flex;"
                                    "align-items:center;gap:8px;"
                                ),
                            ):
                                v3.VIcon(
                                    icon=("ch.icon",), color="#94a3b8", size=20
                                )
                                html.Span("{{ ch.label }}")

                # ── Right: editor card — SAGE26 .par / SAGEswarm run_pso.sh /
                #    LightSAGE run_lightcone.sh ─────────────────────────
                with v3.VCard(
                    v_show=(
                        "wiz_par_show || wiz_sw_config_show "
                        "|| wiz_lc_config_show",
                    ),
                    style=(
                        "flex:1;min-width:0;"
                        "background:#000000;border:2px solid #06b6d4;"
                        "display:flex;flex-direction:column;"
                    ),
                    elevation=0,
                    rounded=False,
                ):
                    with html.Div(
                        style=(
                            "padding:8px 14px;border-bottom:1px solid #374151;"
                            "flex-shrink:0;display:flex;align-items:center;gap:8px;"
                        ),
                    ):
                        v3.VIcon(
                            "mdi-file-document-outline",
                            color="#06b6d4",
                            size="small",
                        )
                        html.Span(
                            "{{ wiz_lc_config_show ? 'Lightcone Parameters' "
                            ": (wiz_sw_config_show ? 'SAGEswarm Parameters' "
                            ": 'SAGE26 Parameters') }}",
                            style="color:#06b6d4;font-size:0.82rem;",
                        )
                    # Parameter form: one labelled box per option (from the
                    # underlying .par / run_pso.sh / run_lightcone.sh).  Edited
                    # values are folded back into the file on Save & Run.
                    with v3.VSheet(
                        color="#000000",
                        style=(
                            "flex:1;min-height:0;overflow-y:auto;padding:10px 14px;"
                            "display:flex;flex-wrap:wrap;align-content:flex-start;"
                        ),
                    ):
                        # A fixed pool of rows, each bound to its OWN scalar
                        # state var (wiz_pv_<i>) so trame reliably syncs edits.
                        # Rows beyond the current parameter count stay hidden.
                        # Checkbox rows are half-width so consecutive ones
                        # (e.g. the SED filter-band picks) wrap into 2 columns;
                        # text-field rows stay full-width, one per line.
                        for i in range(_MAX_PARAMS):
                            with html.Div(
                                v_show=(f"{i} < wiz_param_count",),
                                style=(
                                    f"'display:flex;align-items:center;gap:10px;"
                                    f"margin-bottom:8px;box-sizing:border-box;' + "
                                    f"(wiz_pcb_{i} ? 'flex:0 0 calc(50% - 8px);' "
                                    f": 'flex:0 0 100%;')",
                                ),
                            ):
                                html.Div(
                                    f"{{{{ wiz_pl_{i} }}}}",
                                    title=(f"wiz_ph_{i}",),
                                    style=(
                                        f"(wiz_pcb_{i} ? "
                                        f"'min-width:120px;max-width:120px;' : "
                                        f"'min-width:200px;max-width:200px;') + "
                                        f"'text-align:right;color:#9ca3af;"
                                        f"font-family:monospace;font-size:0.78rem;"
                                        f"overflow:hidden;text-overflow:ellipsis;"
                                        f"white-space:nowrap;flex-shrink:0;'",
                                    ),
                                )
                                # *_ENABLED keys render as a checkbox
                                # (true/false mapped to text "1"/"0" so the
                                # same wiz_pv_<i> string pool + fold-back
                                # logic works unchanged); everything else is
                                # a text box.
                                v3.VCheckbox(
                                    v_if=(f"wiz_pcb_{i}",),
                                    v_model=(f"wiz_pv_{i}",),
                                    true_value="1",
                                    false_value="0",
                                    density="compact",
                                    hide_details=True,
                                    color="cyan",
                                    style="flex:0 0 auto;",
                                )
                                v3.VTextField(
                                    v_if=(f"!wiz_pcb_{i}",),
                                    v_model=(f"wiz_pv_{i}",),
                                    variant="outlined",
                                    density="compact",
                                    hide_details=True,
                                    bg_color="#000000",
                                    color="cyan",
                                    classes="wiz-par-area",
                                    style=(
                                        "font-family:monospace;color:#e2e8f0;"
                                        "flex:1;"
                                    ),
                                )
                        # Empty-state hint if no parameters were parsed.
                        html.Div(
                            "No editable parameters found.",
                            v_show=("wiz_param_count === 0",),
                            style="flex:0 0 100%;color:#9ca3af;font-size:0.8rem;",
                        )


def _home_view(server) -> None:
    """Three big cards (SAGE26, LightSAGE, SAGEswarm) and a smaller Load
    button: the Launch Mode home screen."""
    choose = server.controller.wiz_choose
    with html.Div(
        v_if=("wiz_view === 'home'",),
        classes="wiz-sans",
        style=(
            "width:100%;max-width:1360px;display:flex;flex-direction:column;"
            "gap:24px;"
        ),
    ):
        with html.Div(
            style=(
                "display:grid;grid-template-columns:repeat(3,minmax(0,1fr));"
                "gap:24px;"
            ),
        ):
            with html.Button(
                v_for="c in wiz_home_cards",
                key="c.value",
                type="button",
                classes="wiz-big",
                click=(choose, "[c.value]"),
                style=(
                    "{height:'min(66vh, 560px)',borderRadius:'20px',"
                    "border:'1px solid rgba(255,255,255,0.16)',"
                    "padding:'28px',display:'flex',flexDirection:'column',"
                    "justifyContent:'flex-end',alignItems:'flex-start',"
                    "gap:'10px',textAlign:'left',color:'#fff',"
                    "overflow:'hidden',backgroundColor:'#000',"
                    "backgroundRepeat:'no-repeat',"
                    "backgroundSize: c.fit === 'contain' ? 'contain' : 'cover',"
                    "backgroundPosition: c.fit === 'contain' ? 'center 30%' : 'center',"
                    "backgroundImage:'linear-gradient(180deg, rgba(0,0,0,0) "
                    "0%, rgba(0,0,0,0.2) 45%, rgba(0,0,0,0.93) 100%), url(' "
                    "+ c.bg + ')'}",
                ),
            ):
                with html.Span(
                    style=(
                        "{display:'flex',alignItems:'center',"
                        "justifyContent:'center',width:'54px',height:'54px',"
                        "borderRadius:'14px',background:'rgba(0,0,0,0.45)',"
                        "border:'1px solid ' + c.accent}",
                    ),
                ):
                    v3.VIcon(icon=("c.icon",), color=("c.accent",), size=30)
                html.Span(
                    "{{ c.title }}",
                    style="font-size:2.4rem;font-weight:700;line-height:1.1;",
                )
                html.Span(
                    "{{ c.desc }}",
                    style="font-size:0.95rem;color:#cbd5e1;line-height:1.4;",
                )
                html.Span(
                    "{{ c.badge }}",
                    style=(
                        "{fontSize:'0.75rem',borderRadius:'999px',"
                        "padding:'3px 10px',"
                        "color: c.ok ? '#86efac' : '#fcd34d',"
                        "background: c.ok ? 'rgba(34,197,94,0.15)' "
                        ": 'rgba(245,158,11,0.15)',"
                        "border: '1px solid ' + (c.ok ? 'rgba(34,197,94,0.55)' "
                        ": 'rgba(245,158,11,0.55)')}",
                    ),
                )
        with html.Button(
            type="button",
            classes="wiz-big",
            disabled=("wiz_home_load.disabled",),
            click=(choose, "['act:all:load']"),
            style=(
                "align-self:center;width:min(520px,90%);height:60px;"
                "border-radius:14px;border:1px solid rgba(6,182,212,0.55);"
                "background:linear-gradient(90deg, rgba(6,182,212,0.10), "
                "rgba(6,182,212,0.24));color:#e2e8f0;font-size:1.05rem;"
                "font-weight:500;display:flex;align-items:center;"
                "justify-content:center;gap:12px;"
            ),
        ):
            v3.VIcon("mdi-folder-open", color="#22d3ee", size=24)
            html.Span("{{ wiz_home_load.label }}")
            html.Span(
                "{{ wiz_home_load.sub }}",
                style="font-size:0.82rem;color:#94a3b8;",
            )
        # Windows: where WSL or its build tools are missing.
        with html.Div(
            v_if=("wiz_tools_note",),
            style=(
                "align-self:center;display:flex;align-items:center;gap:12px;"
                "color:#fcd34d;font-size:0.85rem;"
            ),
        ):
            v3.VIcon("mdi-alert-outline", color="#f59e0b", size=20)
            html.Span("{{ wiz_tools_note }}")
            with html.Button(
                v_if=("wiz_tools_missing",),
                type="button",
                classes="wiz-big",
                click=(choose, "['tools']"),
                style=(
                    "height:38px;padding:0 16px;border-radius:12px;"
                    "border:1px solid #f59e0b;background:transparent;"
                    "color:#fcd34d;font-size:0.9rem;display:flex;"
                    "align-items:center;gap:8px;"
                ),
            ):
                v3.VIcon("mdi-penguin", color="#f59e0b", size=18)
                html.Span("Install Linux build tools")


def _mode_view(server) -> None:
    """One tool's screen: its picture and status on the left, its actions
    (Run, Load existing, Install, Check for update, Clone) on the right."""
    choose = server.controller.wiz_choose
    with html.Div(
        v_if=("wiz_view === 'mode'",),
        classes="wiz-sans",
        style=("width:100%;display:flex;gap:22px;color:#e2e8f0;" + _PANEL),
    ):
        with html.Section(
            style=(
                "{width:'40%',flexShrink:0,"
                "borderRadius:'18px',padding:'28px',display:'flex',"
                "flexDirection:'column',justifyContent:'space-between',"
                "border:'1px solid ' + wiz_mode_info.accent + '66',"
                "backgroundColor:'#000',backgroundRepeat:'no-repeat',"
                "backgroundSize: wiz_mode_info.fit === 'contain' "
                "? 'contain' : 'cover',"
                "backgroundPosition: wiz_mode_info.fit === 'contain' "
                "? 'center 35%' : 'center',"
                "backgroundImage:'linear-gradient(180deg, rgba(0,0,0,0.05) "
                "0%, rgba(0,0,0,0.3) 50%, rgba(0,0,0,0.95) 100%), url(' "
                "+ wiz_mode_info.bg + ')'}",
            ),
        ):
            with html.Button(
                type="button",
                classes="wiz-big",
                click=(choose, "['home']"),
                style=(
                    "align-self:flex-start;height:40px;padding:0 16px 0 10px;"
                    "border-radius:999px;border:1px solid rgba(255,255,255,0.45);"
                    "background:rgba(0,0,0,0.55);color:#fff;font-size:0.9rem;"
                    "display:flex;align-items:center;gap:6px;"
                ),
            ):
                v3.VIcon("mdi-chevron-left", color="#fff", size=20)
                html.Span("Home")
            with html.Div(
                style=(
                    "display:flex;flex-direction:column;gap:10px;"
                    "align-items:center;text-align:center;"
                ),
            ):
                html.H1(
                    "{{ wiz_mode_info.title }}",
                    style=(
                        "margin:0;font-size:2.3rem;font-weight:700;"
                        "color:#fff;line-height:1.05;"
                    ),
                )
                html.P(
                    "{{ wiz_mode_info.desc }}",
                    style="margin:0;font-size:0.95rem;color:#cbd5e1;",
                )
                with html.Div(
                    style=(
                        "display:flex;flex-wrap:wrap;gap:8px;margin-top:4px;"
                        "justify-content:center;"
                    ),
                ):
                    html.Span(
                        "{{ ch.text }}",
                        v_for="(ch, i) in wiz_mode_info.chips",
                        key="i",
                        style=(
                            "{fontSize:'0.75rem',borderRadius:'999px',"
                            "padding:'3px 10px',background:'rgba(0,0,0,0.55)',"
                            "color: ch.ok ? '#86efac' : '#fcd34d',"
                            "border:'1px solid ' + (ch.ok ? "
                            "'rgba(34,197,94,0.6)' : 'rgba(245,158,11,0.6)')}",
                        ),
                    )
                html.Span(
                    "{{ wiz_mode_info.path }}",
                    style="font-size:0.78rem;color:#94a3b8;word-break:break-all;",
                )
        with html.Div(
            style=(
                "flex:1;min-width:0;display:flex;flex-direction:column;"
                "gap:12px;"
            ),
        ):
            with html.Button(
                v_for="a in wiz_mode_info.actions",
                key="a.value",
                type="button",
                classes=("a.busy ? 'wiz-big wiz-busy' : 'wiz-big'",),
                disabled=("a.disabled || a.busy",),
                click=(choose, "[a.value]"),
                style=(
                    "{flex: a.primary ? '1.5 1 0' : '1 1 0',minHeight:0,"
                    "borderRadius:'16px',display:'flex',alignItems:'center',"
                    "justifyContent:'center',"
                    "gap:'16px',padding:'0 24px',textAlign:'center',"
                    "border: a.primary ? 'none' "
                    ": '1px solid rgba(148,163,184,0.3)',"
                    "background: a.primary ? 'linear-gradient(90deg, ' "
                    "+ wiz_mode_info.accent + ', ' + wiz_mode_info.accent2 "
                    "+ ')' : '#0b1120',"
                    "color: a.primary ? '#0b1020' : '#e2e8f0'}",
                ),
            ):
                v3.VIcon(
                    icon=("a.busy ? 'mdi-loading' : a.icon",),
                    classes=("a.busy ? 'wiz-spin' : ''",),
                    size=("a.primary ? 32 : 24",),
                    color=("a.primary ? '#0b1020' : wiz_mode_info.accent",),
                )
                with html.Span(
                    style=(
                        "display:flex;flex-direction:column;gap:2px;"
                        "align-items:center;"
                    ),
                ):
                    html.Span(
                        "{{ a.label }}",
                        style=(
                            "{fontSize: a.primary ? '1.4rem' : '1.12rem',"
                            "fontWeight:700}",
                        ),
                    )
                    html.Span(
                        "{{ a.sub }}",
                        style=(
                            "{fontSize:'0.85rem',"
                            "color: a.primary ? '#1e293b' "
                            ": a.tone === 'ok' ? '#86efac' "
                            ": a.tone === 'warn' ? '#fcd34d' "
                            ": a.tone === 'err' ? '#fca5a5' "
                            ": a.tone === 'new' ? wiz_mode_info.accent "
                            ": '#94a3b8'}",
                        ),
                    )


def _pick_view(server) -> None:
    """Big buttons for each model (SAGE26) or lightcone (LightSAGE)."""
    choose = server.controller.wiz_choose
    with html.Div(
        v_if=("wiz_view === 'pick'",),
        classes="wiz-sans",
        style=(
            "width:100%;min-height:0;"
            "display:flex;flex-direction:column;gap:18px;color:#e2e8f0;"
            "position:relative;" + _PANEL
        ),
    ):
        with html.Div(style=_HEADER):
            with html.Button(
                type="button",
                classes="wiz-big",
                click=(choose, "[wiz_pick.back]"),
                style=(
                    "justify-self:start;"
                    "height:40px;padding:0 16px 0 10px;border-radius:999px;"
                    "border:1px solid rgba(255,255,255,0.45);"
                    "background:rgba(255,255,255,0.04);color:#fff;"
                    "font-size:0.9rem;display:flex;align-items:center;gap:6px;"
                ),
            ):
                v3.VIcon("mdi-chevron-left", color="#fff", size=20)
                html.Span("{{ wiz_pick.back_label }}")
            with html.Div(
                style="display:flex;align-items:baseline;gap:12px;",
            ):
                html.H1(
                    "{{ wiz_pick.title }}",
                    style="margin:0;font-size:1.6rem;font-weight:700;",
                )
                html.Span(
                    "{{ (wiz_pick.items || []).length }} found",
                    style="font-size:0.9rem;color:#94a3b8;",
                )
        html.Div(
            "{{ wiz_pick.empty }}",
            v_if=("!(wiz_pick.items || []).length",),
            style="color:#94a3b8;font-size:1rem;padding:40px 0;text-align:center;",
        )
        with html.Div(
            # Three to a row; a part-filled last row sits in the middle.
            style=(
                "flex:1;min-height:0;overflow-y:auto;display:flex;"
                "flex-wrap:wrap;justify-content:center;align-content:flex-start;"
                "gap:16px;padding:4px;"
            ),
        ):
            with html.Button(
                v_for="it in wiz_pick.items",
                key="it.value",
                type="button",
                classes="wiz-big",
                disabled=("!!wiz_loading",),
                click=(choose, "[it.value]"),
                style=(
                    "{flex:'0 1 calc(33.333% - 11px)',minHeight:'124px',"
                    "borderRadius:'16px',"
                    "border:'1px solid rgba(148,163,184,0.3)',"
                    "background:'linear-gradient(145deg, #0f172a, #020617)',"
                    "color:'#e2e8f0',display:'flex',flexDirection:'column',"
                    "alignItems:'center',gap:'10px',padding:'20px 22px',"
                    "textAlign:'center'}",
                ),
            ):
                with html.Span(
                    style="display:flex;align-items:center;gap:12px;",
                ):
                    with html.Span(
                        style=(
                            "{display:'flex',alignItems:'center',"
                            "justifyContent:'center',width:'44px',"
                            "height:'44px',borderRadius:'12px',"
                            "border:'1px solid ' + wiz_pick.accent,"
                            "background:'rgba(0,0,0,0.4)'}",
                        ),
                    ):
                        v3.VIcon(
                            icon=("it.icon",),
                            color=("wiz_pick.accent",),
                            size=24,
                        )
                    html.Span(
                        "{{ it.label }}",
                        style=(
                            "font-size:1.2rem;font-weight:700;"
                            "word-break:break-word;"
                        ),
                    )
                with html.Span(
                    style="display:flex;flex-wrap:wrap;gap:6px;justify-content:center;",
                ):
                    html.Span(
                        "{{ ch }}",
                        v_for="(ch, i) in it.chips",
                        key="i",
                        style=(
                            "font-size:0.75rem;color:#cbd5e1;"
                            "border:1px solid rgba(148,163,184,0.4);"
                            "border-radius:999px;padding:2px 9px;"
                        ),
                    )
                html.Span(
                    "{{ it.sub }}",
                    style="font-size:0.75rem;color:#64748b;word-break:break-all;",
                )
        # Opening a model relaunches ViSAGE; say so over the picker.
        with html.Div(
            v_if=("wiz_loading",),
            style=(
                "position:absolute;inset:0;display:flex;flex-direction:column;"
                "align-items:center;justify-content:center;gap:16px;"
                "background:rgba(0,0,0,0.78);border-radius:16px;"
            ),
        ):
            v3.VProgressCircular(
                indeterminate=True,
                color=("wiz_pick.accent",),
                size=56,
                width=4,
            )
            html.Div(
                "Opening {{ wiz_loading }} ...",
                style="font-size:1.6rem;font-weight:700;",
            )
            html.Div(
                "ViSAGE is restarting with it; the page reloads when it's ready.",
                style="color:#94a3b8;",
            )


# Every page past the home screen: centred, with black space around it
# (no outline: there's no "main box").
_PANEL = (
    "max-width:1240px;margin:0 auto;box-sizing:border-box;padding:6px 20px;"
)

# A page header: back button on the left, the title centred, and room on
# the right for the page's own buttons.
_HEADER = (
    "display:grid;grid-template-columns:1fr auto 1fr;align-items:center;"
    "gap:16px;"
)

_BTN_PILL = (
    "height:40px;padding:0 16px 0 10px;border-radius:999px;"
    "border:1px solid rgba(255,255,255,0.45);background:rgba(255,255,255,0.04);"
    "color:#fff;font-size:0.9rem;display:flex;align-items:center;gap:6px;"
)


def _setup_view(server) -> None:
    """A tool's key choices as big buttons; everything else under All
    settings."""
    choose = server.controller.wiz_choose
    with html.Div(
        v_if=("wiz_view === 'setup'",),
        classes="wiz-sans",
        style=(
            "width:100%;min-height:0;display:flex;"
            "flex-direction:column;gap:12px;color:#e2e8f0;" + _PANEL
        ),
    ):
        with html.Div(style=_HEADER):
            with html.Button(
                type="button",
                classes="wiz-big",
                click=(choose, "['mode:' + wiz_setup.mode]"),
                style=_BTN_PILL + "justify-self:start;",
            ):
                v3.VIcon("mdi-chevron-left", color="#fff", size=20)
                html.Span("{{ wiz_setup.back_label }}")
            html.H1(
                "{{ wiz_setup.title }}",
                style="margin:0;font-size:1.6rem;font-weight:700;",
            )
            html.Span(
                "{{ wiz_setup.note }}",
                v_if=("wiz_setup.note",),
                style="color:#fcd34d;font-size:0.9rem;justify-self:end;",
            )
        with html.Div(
            style=(
                "flex:1;min-height:0;overflow-y:auto;display:flex;"
                "flex-direction:column;gap:8px;padding:2px;"
            ),
        ):
            with html.Div(
                v_for="(g, gi) in wiz_setup.groups",
                key="gi",
                style="display:flex;flex-direction:column;gap:7px;",
            ):
                html.Div(
                    "{{ g.title }}",
                    style=(
                        "{fontSize: g.small ? '0.72rem' : '0.78rem',"
                        "textAlign:'center',"
                        "letterSpacing:'0.12em',textTransform:'uppercase',"
                        "color: g.small ? '#475569' : '#64748b',"
                        "marginTop: g.small ? '0' : '6px'}",
                    ),
                )
                # Cards (pick one) and toggle tiles (switch on/off).
                with html.Div(
                    v_if=("g.kind === 'cards' || g.kind === 'toggles'",),
                    style=(
                        "display:flex;flex-wrap:wrap;gap:10px;"
                        "justify-content:center;"
                    ),
                ):
                    with html.Button(
                        v_for="(it, ii) in g.items",
                        key="ii",
                        type="button",
                        classes="wiz-big",
                        click=(choose, "[it.value]"),
                        style=(
                            "{flex:'0 1 228px',"
                            "borderRadius:'14px',padding:'10px 14px',"
                            "display:'flex',flexDirection:'column',gap:'3px',"
                            "alignItems:'center',"
                            "textAlign:'center',color:'#e2e8f0',"
                            "opacity: it.dim ? 0.55 : 1,"
                            "border: it.on ? '2px solid ' + wiz_setup.accent "
                            ": '1px solid #1e293b',"
                            "background: it.on ? 'linear-gradient(145deg, ' + "
                            "wiz_setup.accent + '29, #0b1120)' : '#0b1120'}",
                        ),
                    ):
                        with html.Span(
                            style=(
                                "display:flex;align-items:center;gap:8px;"
                                "font-size:1.02rem;font-weight:700;"
                            ),
                        ):
                            v3.VIcon(
                                v_if=("g.kind === 'toggles'",),
                                icon=(
                                    "it.on ? 'mdi-toggle-switch' "
                                    ": 'mdi-toggle-switch-off-outline'",
                                ),
                                color=(
                                    "it.on ? wiz_setup.accent : '#64748b'",
                                ),
                                size=26,
                            )
                            html.Span("{{ it.label }}")
                        html.Span(
                            "{{ it.sub }}",
                            v_if=("it.sub",),
                            style="font-size:0.8rem;color:#94a3b8;",
                        )
                        html.Span(
                            "{{ it.code }}",
                            v_if=("it.code",),
                            style=(
                                "{fontSize:'0.75rem',"
                                "color: it.on ? wiz_setup.accent : '#64748b'}",
                            ),
                        )
                # Chips (several on).
                with html.Div(
                    v_if=("g.kind === 'chips'",),
                    style="display:flex;flex-wrap:wrap;gap:6px;justify-content:center;",
                ):
                    with html.Button(
                        v_for="(it, ii) in g.items",
                        key="ii",
                        type="button",
                        classes="wiz-big",
                        disabled=("!!g.static",),
                        click=(choose, "[it.value]"),
                        style=(
                            "{fontSize:'0.82rem',"
                            "padding:'5px 12px',borderRadius:'999px',"
                            "opacity:1,"
                            "border: it.on ? '1px solid ' + wiz_setup.accent "
                            ": '1px solid #334155',"
                            "background: it.on ? wiz_setup.accent + '29' "
                            ": 'transparent',"
                            "color: it.on ? '#fff' : '#94a3b8'}",
                        ),
                    ):
                        html.Span("{{ it.label }}")
        with html.Div(
            style=(
                "display:flex;align-items:center;justify-content:center;"
                "gap:14px;padding-top:4px;"
            ),
        ):
            html.Span("Name", style="color:#94a3b8;")
            html.Input(
                id="wiz-setup-name",
                type="text",
                aria_label="Name of this run",
                v_model=("wiz_setup_name",),
                style=(
                    "width:300px;height:46px;border-radius:12px;"
                    "border:1px solid #334155;background:#020617;color:#e2e8f0;"
                    "padding:0 14px;font-size:1rem;"
                ),
            )
            with html.Button(
                type="button",
                classes="wiz-big",
                click=(choose, "['su:all']"),
                style=(
                    "height:46px;padding:0 18px;border-radius:12px;"
                    "border:1px solid #334155;background:#0b1120;color:#e2e8f0;"
                    "font-size:0.95rem;display:flex;align-items:center;gap:6px;"
                ),
            ):
                v3.VIcon("mdi-tune-variant", color="#94a3b8", size=20)
                html.Span("All settings")
            with html.Button(
                type="button",
                classes="wiz-big",
                click=(choose, "['su:run']"),
                style=(
                    "{height:'58px',padding:'0 34px',borderRadius:'16px',"
                    "border:'none',color:'#0b1020',fontSize:'1.25rem',"
                    "fontWeight:700,display:'flex',alignItems:'center',"
                    "gap:'10px',background:'linear-gradient(90deg, ' + "
                    "wiz_setup.accent + ', ' + wiz_setup.accent2 + ')'}",
                ),
            ):
                v3.VIcon("mdi-play", color="#0b1020", size=28)
                html.Span("{{ wiz_setup.run_label }}")
        html.Div(
            "{{ wiz_setup_name }} already exists: running replaces its "
            "output{{ wiz_setup.mode === 'sage26' ? ' (and its .par)' : '' }}. "
            "Give this run a new name to keep it.",
            v_if=(
                "(wiz_setup.taken || []).includes("
                "(wiz_setup_name || '').trim().replace(/[^\\w.-]+/g, '_'))",
            ),
            style="text-align:center;color:#fcd34d;font-size:0.85rem;",
        )


def _all_settings_view(server) -> None:
    """Every value in the file, in sections, with a search."""
    choose = server.controller.wiz_choose
    with html.Div(
        v_if=("wiz_view === 'all'",),
        classes="wiz-sans",
        style=(
            "width:100%;min-height:0;display:flex;"
            "flex-direction:column;gap:12px;color:#e2e8f0;" + _PANEL
        ),
    ):
        with html.Div(style=_HEADER):
            with html.Button(
                type="button",
                classes="wiz-big",
                click=(choose, "['su:back']"),
                style=_BTN_PILL + "justify-self:start;",
            ):
                v3.VIcon("mdi-chevron-left", color="#fff", size=20)
                html.Span("{{ wiz_setup.title }}")
            html.H1(
                "All settings",
                style="margin:0;font-size:1.6rem;font-weight:700;",
            )
            with html.Div(
                style=(
                    "justify-self:end;display:flex;align-items:center;gap:12px;"
                ),
            ):
                v3.VTextField(
                    v_model=("wiz_param_search",),
                    placeholder="Find a setting",
                    prepend_inner_icon="mdi-magnify",
                    variant="outlined",
                    density="compact",
                    hide_details=True,
                    clearable=True,
                    bg_color="#020617",
                    style="width:260px;flex:0 0 260px;",
                )
                with html.Button(
                    type="button",
                    classes="wiz-big",
                    click=(choose, "['su:run']"),
                    style=(
                        "{height:'46px',padding:'0 22px',borderRadius:'12px',"
                        "border:'none',color:'#0b1020',fontSize:'1rem',"
                        "fontWeight:700,display:'flex',alignItems:'center',"
                        "gap:'8px',background:'linear-gradient(90deg, ' + "
                        "wiz_setup.accent + ', ' + wiz_setup.accent2 + ')'}",
                    ),
                ):
                    v3.VIcon("mdi-play", color="#0b1020", size=22)
                    html.Span("{{ wiz_setup.run_label }}")
        with html.Div(style="flex:1;min-height:0;display:flex;gap:20px;"):
            with html.Nav(
                style=(
                    "width:240px;flex-shrink:0;display:flex;flex-direction:column;"
                    "gap:4px;padding:10px;border-radius:16px;background:#050a14;"
                    "border:1px solid #1e293b;overflow-y:auto;"
                ),
            ):
                with html.Button(
                    v_for="sec in wiz_sections",
                    key="sec.name",
                    type="button",
                    click="wiz_section = sec.name; wiz_param_search = ''",
                    style=(
                        "{display:'flex',alignItems:'center',gap:'10px',"
                        "padding:'10px 12px',borderRadius:'10px',fontSize:'0.9rem',"
                        "textAlign:'left',cursor:'pointer',"
                        "color: wiz_section === sec.name ? '#fff' : '#cbd5e1',"
                        "border: wiz_section === sec.name ? '1px solid ' + "
                        "wiz_setup.accent : '1px solid transparent',"
                        "background: wiz_section === sec.name ? "
                        "wiz_setup.accent + '1f' : 'transparent'}",
                    ),
                ):
                    html.Span("{{ sec.name }}")
                    html.Span(
                        "{{ sec.count }}",
                        style=(
                            "margin-left:auto;"
                            "font-size:0.75rem;color:#64748b;"
                        ),
                    )
            with html.Div(
                style=(
                    "flex:1;min-width:0;overflow-y:auto;display:flex;"
                    "flex-direction:column;gap:8px;padding-right:4px;"
                ),
            ):
                for i in range(_MAX_PARAMS):
                    show = (
                        f"{i} < wiz_param_count && (wiz_param_search ? "
                        f"(wiz_pl_{i} + ' ' + wiz_ph_{i}).toLowerCase()"
                        f".includes(wiz_param_search.toLowerCase()) "
                        f": wiz_pg_{i} === wiz_section)"
                    )
                    with html.Div(
                        v_show=(show,),
                        style=(
                            "display:grid;grid-template-columns:300px minmax(0,1fr);"
                            "align-items:center;gap:18px;padding:10px 16px;"
                            "border-radius:12px;border:1px solid #1e293b;"
                            "background:#0b1120;"
                        ),
                    ):
                        with html.Div(
                            style="display:flex;flex-direction:column;gap:2px;min-width:0;"
                        ):
                            html.Span(
                                f"{{{{ wiz_pl_{i} }}}}",
                                style=(
                                    "font-size:0.92rem;font-weight:600;"
                                    "color:#e2e8f0;word-break:break-all;"
                                ),
                            )
                            html.Span(
                                f"{{{{ wiz_ph_{i} }}}}",
                                v_if=(f"wiz_ph_{i}",),
                                style="font-size:0.75rem;color:#94a3b8;",
                            )
                        v3.VSwitch(
                            v_if=(f"wiz_pcb_{i}",),
                            v_model=(f"wiz_pv_{i}",),
                            true_value="1",
                            false_value="0",
                            color=("wiz_setup.accent",),
                            density="compact",
                            hide_details=True,
                            inset=True,
                        )
                        v3.VTextField(
                            v_if=(f"!wiz_pcb_{i}",),
                            v_model=(f"wiz_pv_{i}",),
                            variant="outlined",
                            density="compact",
                            hide_details=True,
                            bg_color="#020617",
                        )


def _run_view(server) -> None:
    """A run's progress: stages, a bar and numbers, then the terminal
    (2/3) beside what the run is making (1/3): a box or a lightcone
    filling up, or SAGEswarm's plots."""
    choose = server.controller.wiz_choose
    with html.Div(
        v_if=("wiz_view === 'run'",),
        classes="wiz-sans",
        style=(
            "width:100%;display:flex;flex-direction:column;gap:12px;"
            "color:#e2e8f0;min-height:0;" + _PANEL
        ),
    ):
        with html.Div(style=_HEADER):
            html.Span()
            with html.Div(
                style="display:flex;align-items:baseline;gap:12px;",
            ):
                html.H1(
                    "{{ wiz_run.status === 'done' ? 'Finished' : "
                    "(wiz_run.status === 'failed' ? 'Stopped' : wiz_run.title) }}",
                    style="margin:0;font-size:1.6rem;font-weight:700;",
                )
                html.Span(
                    "{{ wiz_run.sub }}",
                    style="font-size:0.9rem;color:#94a3b8;",
                )
            with html.Button(
                v_if=("wiz_run.status === 'running'",),
                type="button",
                classes="wiz-big",
                click=server.controller.wiz_cancel_run,
                style=(
                    "justify-self:end;height:42px;padding:0 18px;"
                    "border-radius:12px;border:1px solid #ef4444;"
                    "background:transparent;color:#fca5a5;font-size:0.95rem;"
                ),
            ):
                html.Span("Cancel run")
        # Stages
        with html.Div(style="display:flex;gap:12px;"):
            with html.Div(
                v_for="(st, si) in wiz_run.stages",
                key="si",
                style=(
                    "{flex:1,display:'flex',alignItems:'center',gap:'10px',"
                    "justifyContent:'center',"
                    "padding:'9px 14px',borderRadius:'14px',fontSize:'0.88rem',"
                    "border: st.state === 'now' ? '2px solid ' + wiz_run.accent "
                    ": (st.state === 'failed' ? '2px solid #ef4444' "
                    ": '2px solid #1e293b'),"
                    "background: st.state === 'now' ? wiz_run.accent + '1a' "
                    ": '#0b1120',"
                    "color: st.state === 'next' ? '#64748b' : '#e2e8f0'}",
                ),
            ):
                with html.Span(
                    style=(
                        "{width:'24px',height:'24px',borderRadius:'50%',"
                        "display:'flex',alignItems:'center',"
                        "justifyContent:'center',flexShrink:0,"
                        "background: st.state === 'done' ? '#22c55e' "
                        ": (st.state === 'now' ? wiz_run.accent "
                        ": (st.state === 'failed' ? '#ef4444' : 'transparent')),"
                        "border: st.state === 'next' ? '1.5px solid #334155' "
                        ": 'none'}",
                    ),
                ):
                    v3.VIcon(
                        icon=(
                            "st.state === 'done' ? 'mdi-check' "
                            ": (st.state === 'failed' ? 'mdi-close' "
                            ": (st.state === 'now' ? 'mdi-loading' : ''))",
                        ),
                        classes=("st.state === 'now' ? 'wiz-spin' : ''",),
                        size=18,
                        color="#0b1020",
                    )
                html.Span("{{ st.label }}")
        # Overall progress
        with html.Div(style="display:flex;flex-direction:column;gap:6px;"):
            with html.Div(
                style="display:flex;justify-content:space-between;font-size:0.9rem;",
            ):
                html.Span(
                    "{{ wiz_run.error || 'Overall' }}",
                    style=("{color: wiz_run.error ? '#fca5a5' : '#cbd5e1'}",),
                )
                html.Span(
                    "{{ Math.round(wiz_run.pct) }}%",
                    style=(
                        "{color: wiz_run.accent,fontWeight:700,"
                        "fontVariantNumeric:'tabular-nums'}",
                    ),
                )
            with html.Div(
                style=(
                    "height:12px;border-radius:6px;background:#1e293b;"
                    "overflow:hidden;"
                ),
            ):
                html.Div(
                    style=(
                        "{width: wiz_run.pct + '%',height:'100%',"
                        "borderRadius:'6px',transition:'width 0.4s',"
                        "background: wiz_run.status === 'failed' ? '#ef4444' "
                        ": 'linear-gradient(90deg, ' + wiz_run.accent + ', ' "
                        "+ wiz_run.accent2 + ')'}",
                    ),
                )
        # Numbers
        with html.Div(
            style=(
                "display:grid;gap:12px;"
                "grid-template-columns:repeat(auto-fit,minmax(180px,1fr));"
            ),
        ):
            with html.Div(
                v_for="(s, i) in wiz_run.stats",
                key="i",
                style=(
                    "border-radius:14px;border:1px solid #1e293b;"
                    "background:#0b1120;padding:9px 16px;display:flex;"
                    "align-items:center;justify-content:center;gap:14px;"
                    "min-width:0;"
                ),
            ):
                with html.Div(
                    style=(
                        "{flex: s.kind === 'tree' ? '0 0 auto' : '1',minWidth:0,"
                        "display:'flex',flexDirection:'column',gap:'3px',"
                        "alignItems: s.kind === 'tree' ? 'flex-start' : 'center',"
                        "textAlign: s.kind === 'tree' ? 'left' : 'center'}",
                    ),
                ):
                    html.Span(
                        "{{ s.k }}",
                        style=(
                            "font-size:0.68rem;color:#94a3b8;"
                            "letter-spacing:0.08em;text-transform:uppercase;"
                        ),
                    )
                    html.Span(
                        "{{ s.v }}",
                        style=(
                            "font-size:1.25rem;font-weight:700;"
                            "font-variant-numeric:tabular-nums;"
                        ),
                    )
                    # SAGEswarm: one segment per round, filling.
                    with html.Div(
                        v_if=("s.kind === 'iters'",),
                        style="display:flex;gap:3px;margin-top:3px;width:100%;",
                    ):
                        with html.Div(
                            v_for="(f, fi) in s.segs",
                            key="fi",
                            style=(
                                "flex:1;height:8px;border-radius:3px;"
                                "background:#1e293b;overflow:hidden;"
                            ),
                        ):
                            html.Div(
                                style=(
                                    "{width: (f * 100) + '%',height:'100%',"
                                    "transition:'width 0.4s',"
                                    "background:'linear-gradient(90deg, ' + "
                                    "wiz_run.accent + ', ' + wiz_run.accent2 + ')'}",
                                ),
                            )
                    # SAGEswarm: one circle per particle, filled once run.
                    with html.Div(
                        v_if=("s.kind === 'particles'",),
                        style=(
                            "display:flex;flex-wrap:wrap;gap:4px;margin-top:3px;"
                            "justify-content:center;"
                        ),
                    ):
                        html.Span(
                            v_for="(d, di) in s.dots",
                            key="di",
                            classes=("d ? 'wiz-dot wiz-dot-on' : 'wiz-dot'",),
                            style=(
                                "{background: d ? wiz_run.accent : 'transparent',"
                                "borderColor: d ? wiz_run.accent : '#475569'}",
                            ),
                        )
                # SAGE26: a merger-tree branch across the rest of the tile,
                # filling from its early-time tips to its root.
                html.Img(
                    v_if=("s.kind === 'tree'",),
                    src=("s.img",),
                    alt="",
                    style="flex:1;min-width:60px;height:40px;",
                )
        # Terminal (2/3) and what the run is making (1/3): one black
        # panel.
        with html.Div(
            style=(
                "flex:1;min-height:0;display:flex;background:#000;"
                "border-radius:14px;overflow:hidden;"
            ),
        ):
            # The wizard's xterm moves in here (visage.js) while the run
            # page shows.
            html.Div(
                id="wiz-run-pty",
                style="flex:2;min-width:0;min-height:0;overflow:hidden;padding:6px 8px;",
            )
            with html.Section(
                style=(
                    "flex:1;min-width:0;background:#000;display:flex;"
                    "flex-direction:column;overflow:hidden;"
                ),
            ):
                with html.Div(
                    style=(
                        "flex:1;min-height:0;display:flex;align-items:center;"
                        "justify-content:center;padding:8px;position:relative;"
                    ),
                ):
                    # Fitted to the box, so its own size never stretches
                    # the page.
                    html.Img(
                        v_if=(
                            "wiz_run.mode !== 'sageswarm' && wiz_run.live_img",
                        ),
                        src=("wiz_run.live_img",),
                        style=(
                            "position:absolute;inset:8px;width:calc(100% - 16px);"
                            "height:calc(100% - 16px);object-fit:contain;"
                        ),
                    )
                    # SAGEswarm: the newest figure of each constraint,
                    # sharing the panel.
                    with html.Div(
                        v_if=(
                            "wiz_run.mode === 'sageswarm' && wiz_run_plots.length",
                        ),
                        style=(
                            "{width:'100%',height:'100%',minHeight:0,"
                            "display:'grid',gap:'8px',"
                            "gridTemplateColumns: wiz_run_plots.length > 3 "
                            "? 'repeat(2, minmax(0, 1fr))' : 'minmax(0, 1fr)',"
                            "gridAutoRows:'minmax(0, 1fr)'}",
                        ),
                    ):
                        with html.Div(
                            v_for="pl in wiz_run_plots",
                            key="pl.name",
                            style=(
                                "min-height:0;display:flex;flex-direction:column;"
                                "align-items:center;gap:2px;"
                            ),
                        ):
                            html.Span(
                                "{{ pl.group }}",
                                style="font-size:0.72rem;color:#94a3b8;",
                            )
                            # The figure fits its share of the panel.
                            with html.Div(
                                style=(
                                    "flex:1;min-height:0;width:100%;"
                                    "position:relative;"
                                ),
                            ):
                                html.Img(
                                    src=("pl.data_url",),
                                    title=("pl.name",),
                                    style=(
                                        "position:absolute;inset:0;width:100%;"
                                        "height:100%;object-fit:contain;"
                                    ),
                                )
                    with html.Div(
                        v_if=(
                            "wiz_run.mode === 'sageswarm' ? !wiz_run_plots.length "
                            ": !wiz_run.live_img",
                        ),
                        style=(
                            "display:flex;flex-direction:column;align-items:center;"
                            "gap:12px;color:#94a3b8;text-align:center;"
                        ),
                    ):
                        v3.VProgressCircular(
                            indeterminate=("wiz_run.status === 'running'",),
                            color=("wiz_run.accent",),
                            size=44,
                            width=3,
                        )
                        html.Span("Plots appear here as SAGEswarm makes them.")
        # When it's finished (or stopped)
        with html.Div(
            v_if=("wiz_run.actions && wiz_run.actions.length",),
            style="display:flex;gap:12px;justify-content:center;",
        ):
            with html.Button(
                v_for="(a, ai) in wiz_run.actions",
                key="ai",
                type="button",
                classes="wiz-big",
                click=(choose, "[a.value]"),
                style=(
                    "{height: a.primary ? '58px' : '48px',padding:'0 26px',"
                    "borderRadius:'14px',display:'flex',alignItems:'center',"
                    "gap:'10px',fontSize: a.primary ? '1.2rem' : '1rem',"
                    "fontWeight: a.primary ? 700 : 500,"
                    "border: a.primary ? 'none' : '1px solid #334155',"
                    "color: a.primary ? '#0b1020' : '#e2e8f0',"
                    "background: a.primary ? 'linear-gradient(90deg, ' + "
                    "wiz_run.accent + ', ' + wiz_run.accent2 + ')' : '#0b1120'}",
                ),
            ):
                v3.VIcon(
                    icon=("a.icon",),
                    color=("a.primary ? '#0b1020' : '#94a3b8'",),
                )
                html.Span("{{ a.label }}")
