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
.wiz-sans { font-family: 'Space Grotesk', 'Segoe UI', system-ui, -apple-system, sans-serif; }
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
            style=(
                "{flex:'1',display:'flex',alignItems:'center',"
                "justifyContent:'center',overflowX:'auto',overflowY:'hidden',"
                "padding:'24px',"
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
                    "height:'640px',maxHeight:'80vh',"
                    "width:'100%',maxWidth:'calc(100vw - 48px)',"
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
                        "max-width:${(wiz_par_show || wiz_sw_config_show "
                        "|| wiz_lc_config_show) ? '860px' : '1100px'};"
                        "background:#000000;border:2px solid #06b6d4;"
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
                                style=(
                                    "font-family:monospace;" "max-width:320px;"
                                ),
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
                                style="font-family:monospace;max-width:520px;",
                            )
                        # Cancel button — shown whenever a command is running;
                        # sends SIGINT (Ctrl+C) to the process group.
                        with html.Div(
                            v_show=(
                                "wiz_run_active || (wiz_run && wiz_run.mode)",
                            ),
                            style="display:flex;align-items:center;gap:8px;",
                        ):
                            v3.VBtn(
                                "Back to progress",
                                v_show=("wiz_run && wiz_run.mode",),
                                prepend_icon="mdi-chart-timeline-variant",
                                color="#06b6d4",
                                variant="outlined",
                                size="small",
                                click=(
                                    server.controller.wiz_choose,
                                    "['run:view']",
                                ),
                                style=(
                                    "font-family:monospace;text-transform:none;"
                                ),
                            )
                            v3.VBtn(
                                "Cancel (Ctrl+C)",
                                v_show=("wiz_run_active",),
                                prepend_icon="mdi-close-octagon",
                                color="#ef4444",
                                variant="outlined",
                                size="small",
                                click=server.controller.wiz_cancel_run,
                                style=(
                                    "font-family:monospace;text-transform:none;"
                                ),
                            )
                        with html.Div(
                            v_show=("!wiz_busy && wiz_choices.length > 0",),
                            style=(
                                "display:flex;flex-wrap:wrap;gap:8px;"
                                "max-height:120px;overflow-y:auto;"
                            ),
                        ):
                            with html.Div(
                                v_for="(ch, ci) in wiz_choices",
                                key="ci",
                            ):
                                v3.VBtn(
                                    "{{ ch.label }}",
                                    prepend_icon=("ch.icon",),
                                    color="#06b6d4",
                                    variant="outlined",
                                    size=(
                                        "wiz_choices.length > 5 ? 'x-small' : 'small'",
                                    ),
                                    disabled=("ch.disabled",),
                                    click=(
                                        server.controller.wiz_choose,
                                        "[ch.value]",
                                    ),
                                    style="font-family:monospace;text-transform:none;",
                                )

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

        # SAGE logo — pinned to bottom-right corner of the wizard screen
        html.Img(
            v_show=("wiz_view === 'term'",),
            src="/sage_static/SAGElogo.jpg",
            style=(
                "position:absolute;bottom:16px;right:16px;"
                "width:90px;"
                "pointer-events:none;"
            ),
        )


def _home_view(server) -> None:
    """Three big cards (SAGE26, LightSAGE, SAGEswarm) and a smaller Load
    button: the Launch Mode home screen."""
    choose = server.controller.wiz_choose
    with html.Div(
        v_if=("wiz_view === 'home'",),
        classes="wiz-sans",
        style=(
            "width:100%;max-width:1180px;display:flex;flex-direction:column;"
            "gap:22px;"
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
                    "{height:'min(58vh, 460px)',borderRadius:'18px',"
                    "border:'1px solid rgba(255,255,255,0.16)',"
                    "padding:'28px',display:'flex',flexDirection:'column',"
                    "justifyContent:'flex-end',alignItems:'flex-start',"
                    "gap:'10px',textAlign:'left',color:'#fff',"
                    "overflow:'hidden',backgroundColor:'#000',"
                    "backgroundSize:'cover',backgroundPosition:'center',"
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
                    style="font-size:2.1rem;font-weight:700;line-height:1.1;",
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
            click=(choose, "['act:sage26:load']"),
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
            v3.VBtn(
                "Install Linux build tools",
                v_if=("wiz_tools_missing",),
                prepend_icon="mdi-penguin",
                color="#f59e0b",
                variant="outlined",
                size="small",
                click=(choose, "['tools']"),
                style="text-transform:none;",
            )


def _mode_view(server) -> None:
    """One tool's screen: its picture and status on the left, its actions
    (Run, Load existing, Install, Check for update, Clone) on the right."""
    choose = server.controller.wiz_choose
    with html.Div(
        v_if=("wiz_view === 'mode'",),
        classes="wiz-sans",
        style=(
            "width:100%;max-width:1180px;height:min(620px,76vh);"
            "display:flex;gap:24px;color:#e2e8f0;"
        ),
    ):
        with html.Section(
            style=(
                "{width:'40%',maxWidth:'460px',flexShrink:0,"
                "borderRadius:'18px',padding:'28px',display:'flex',"
                "flexDirection:'column',justifyContent:'space-between',"
                "border:'1px solid ' + wiz_mode_info.accent + '66',"
                "backgroundColor:'#000',backgroundSize:'cover',"
                "backgroundPosition:'center',"
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
                style="display:flex;flex-direction:column;gap:10px;",
            ):
                html.H1(
                    "{{ wiz_mode_info.title }}",
                    style=(
                        "margin:0;font-size:2.9rem;font-weight:700;"
                        "color:#fff;line-height:1.05;"
                    ),
                )
                html.P(
                    "{{ wiz_mode_info.desc }}",
                    style="margin:0;font-size:0.95rem;color:#cbd5e1;",
                )
                with html.Div(
                    style="display:flex;flex-wrap:wrap;gap:8px;margin-top:4px;",
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
                    style=(
                        "font-family:monospace;font-size:0.75rem;"
                        "color:#94a3b8;word-break:break-all;"
                    ),
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
                    "gap:'20px',padding:'0 28px',textAlign:'left',"
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
                    size=("a.primary ? 40 : 30",),
                    color=("a.primary ? '#0b1020' : wiz_mode_info.accent",),
                )
                with html.Span(
                    style="display:flex;flex-direction:column;gap:2px;",
                ):
                    html.Span(
                        "{{ a.label }}",
                        style=(
                            "{fontSize: a.primary ? '1.75rem' : '1.35rem',"
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
            "width:100%;max-width:1180px;height:min(640px,78vh);"
            "display:flex;flex-direction:column;gap:20px;color:#e2e8f0;"
            "position:relative;"
        ),
    ):
        with html.Div(style="display:flex;align-items:center;gap:18px;"):
            with html.Button(
                type="button",
                classes="wiz-big",
                click=(choose, "[wiz_pick.back]"),
                style=(
                    "height:40px;padding:0 16px 0 10px;border-radius:999px;"
                    "border:1px solid rgba(255,255,255,0.45);"
                    "background:rgba(255,255,255,0.04);color:#fff;"
                    "font-size:0.9rem;display:flex;align-items:center;gap:6px;"
                ),
            ):
                v3.VIcon("mdi-chevron-left", color="#fff", size=20)
                html.Span("{{ wiz_pick.back_label }}")
            html.H1(
                "{{ wiz_pick.title }}",
                style="margin:0;font-size:2.1rem;font-weight:700;",
            )
            html.Span(
                "{{ (wiz_pick.items || []).length }} found",
                style="font-size:0.9rem;color:#94a3b8;",
            )
        html.Div(
            "{{ wiz_pick.empty }}",
            v_if=("!(wiz_pick.items || []).length",),
            style="color:#94a3b8;font-size:1rem;padding:40px 0;",
        )
        with html.Div(
            style=(
                "flex:1;min-height:0;overflow-y:auto;display:grid;"
                "grid-template-columns:repeat(auto-fill,minmax(320px,1fr));"
                "grid-auto-rows:min-content;gap:16px;padding:4px;"
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
                    "{minHeight:'150px',borderRadius:'16px',"
                    "border:'1px solid rgba(148,163,184,0.3)',"
                    "background:'linear-gradient(145deg, #0f172a, #020617)',"
                    "color:'#e2e8f0',display:'flex',flexDirection:'column',"
                    "alignItems:'flex-start',gap:'10px',padding:'20px 22px',"
                    "textAlign:'left'}",
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
                            "font-size:1.45rem;font-weight:700;"
                            "word-break:break-word;"
                        ),
                    )
                with html.Span(
                    style="display:flex;flex-wrap:wrap;gap:6px;",
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
                    style=(
                        "font-family:monospace;font-size:0.72rem;"
                        "color:#64748b;word-break:break-all;"
                    ),
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
            "width:100%;max-width:1220px;height:min(700px,82vh);display:flex;"
            "flex-direction:column;gap:14px;color:#e2e8f0;"
        ),
    ):
        with html.Div(style="display:flex;align-items:center;gap:16px;"):
            with html.Button(
                type="button",
                classes="wiz-big",
                click=(choose, "['mode:' + wiz_setup.mode]"),
                style=_BTN_PILL,
            ):
                v3.VIcon("mdi-chevron-left", color="#fff", size=20)
                html.Span("{{ wiz_setup.back_label }}")
            html.H1(
                "{{ wiz_setup.title }}",
                style="margin:0;font-size:2rem;font-weight:700;",
            )
            html.Span(
                "{{ wiz_setup.note }}",
                v_if=("wiz_setup.note",),
                style="color:#fcd34d;font-size:0.9rem;",
            )
        with html.Div(
            style=(
                "flex:1;min-height:0;overflow-y:auto;display:flex;"
                "flex-direction:column;gap:12px;padding:2px;"
            ),
        ):
            with html.Div(
                v_for="(g, gi) in wiz_setup.groups",
                key="gi",
                style="display:flex;flex-direction:column;gap:10px;",
            ):
                html.Div(
                    "{{ g.title }}",
                    style=(
                        "{fontSize: g.small ? '0.72rem' : '0.78rem',"
                        "letterSpacing:'0.12em',textTransform:'uppercase',"
                        "color: g.small ? '#475569' : '#64748b',"
                        "marginTop: g.small ? '0' : '6px'}",
                    ),
                )
                # Cards (pick one) and toggle tiles (switch on/off).
                with html.Div(
                    v_if=("g.kind === 'cards' || g.kind === 'toggles'",),
                    style=(
                        "display:grid;gap:12px;"
                        "grid-template-columns:repeat(auto-fill,minmax(240px,1fr));"
                    ),
                ):
                    with html.Button(
                        v_for="(it, ii) in g.items",
                        key="ii",
                        type="button",
                        classes="wiz-big",
                        click=(choose, "[it.value]"),
                        style=(
                            "{borderRadius:'14px',padding:'14px 16px',"
                            "display:'flex',flexDirection:'column',gap:'5px',"
                            "textAlign:'left',color:'#e2e8f0',"
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
                                "font-size:1.1rem;font-weight:700;"
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
                                "{fontFamily:'monospace',fontSize:'0.7rem',"
                                "color: it.on ? wiz_setup.accent : '#64748b'}",
                            ),
                        )
                # Chips (several on).
                with html.Div(
                    v_if=("g.kind === 'chips'",),
                    style="display:flex;flex-wrap:wrap;gap:8px;",
                ):
                    with html.Button(
                        v_for="(it, ii) in g.items",
                        key="ii",
                        type="button",
                        classes="wiz-big",
                        disabled=("!!g.static",),
                        click=(choose, "[it.value]"),
                        style=(
                            "{fontFamily:'monospace',fontSize:'0.8rem',"
                            "padding:'7px 13px',borderRadius:'999px',"
                            "opacity:1,"
                            "border: it.on ? '1px solid ' + wiz_setup.accent "
                            ": '1px solid #334155',"
                            "background: it.on ? wiz_setup.accent + '29' "
                            ": 'transparent',"
                            "color: it.on ? '#fff' : '#94a3b8'}",
                        ),
                    ):
                        html.Span("{{ it.label }}")
        with html.Div(style="display:flex;align-items:center;gap:14px;"):
            html.Span("Name", style="color:#94a3b8;")
            html.Input(
                id="wiz-setup-name",
                type="text",
                aria_label="Name of this run",
                v_model=("wiz_setup_name",),
                style=(
                    "width:300px;height:46px;border-radius:12px;"
                    "border:1px solid #334155;background:#020617;color:#e2e8f0;"
                    "padding:0 14px;font-family:monospace;font-size:0.95rem;"
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
            v3.VSpacer()
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


def _all_settings_view(server) -> None:
    """Every value in the file, in sections, with a search."""
    choose = server.controller.wiz_choose
    with html.Div(
        v_if=("wiz_view === 'all'",),
        classes="wiz-sans",
        style=(
            "width:100%;max-width:1220px;height:min(700px,82vh);display:flex;"
            "flex-direction:column;gap:14px;color:#e2e8f0;"
        ),
    ):
        with html.Div(style="display:flex;align-items:center;gap:14px;"):
            with html.Button(
                type="button",
                classes="wiz-big",
                click=(choose, "['su:back']"),
                style=_BTN_PILL,
            ):
                v3.VIcon("mdi-chevron-left", color="#fff", size=20)
                html.Span("{{ wiz_setup.title }}")
            html.H1(
                "All settings",
                style="margin:0;font-size:2rem;font-weight:700;",
            )
            v3.VSpacer()
            v3.VTextField(
                v_model=("wiz_param_search",),
                placeholder="Find a setting",
                prepend_inner_icon="mdi-magnify",
                variant="outlined",
                density="compact",
                hide_details=True,
                clearable=True,
                bg_color="#020617",
                style="max-width:280px;",
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
                            "margin-left:auto;font-family:monospace;"
                            "font-size:0.72rem;color:#64748b;"
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
                                    "font-family:monospace;font-size:0.85rem;"
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
                            style="font-family:monospace;",
                        )


def _run_view(server) -> None:
    """Progress while a tool runs, with a switch to the live science
    view."""
    choose = server.controller.wiz_choose
    with html.Div(
        v_if=("wiz_view === 'run'",),
        classes="wiz-sans",
        style=(
            "width:100%;max-width:1220px;height:min(700px,82vh);display:flex;"
            "flex-direction:column;gap:16px;color:#e2e8f0;"
        ),
    ):
        with html.Div(style="display:flex;align-items:center;gap:16px;"):
            html.H1(
                "{{ wiz_run.status === 'done' ? 'Finished' : "
                "(wiz_run.status === 'failed' ? 'Stopped' : wiz_run.title) }}",
                style="margin:0;font-size:2rem;font-weight:700;",
            )
            html.Span(
                "{{ wiz_run.sub }}",
                style="font-family:monospace;font-size:0.85rem;color:#94a3b8;",
            )
            v3.VSpacer()
            # Progress <-> live science view.
            with html.Div(
                style=(
                    "display:flex;border:1px solid #334155;border-radius:999px;"
                    "padding:3px;gap:3px;"
                ),
            ):
                for live, label, icon in (
                    ("false", "Progress", "mdi-chart-timeline-variant"),
                    ("true", "Live view", "mdi-eye"),
                ):
                    with html.Button(
                        type="button",
                        click=f"wiz_run_live = {live}",
                        style=(
                            "{height:'36px',padding:'0 16px',borderRadius:'999px',"
                            "border:'none',cursor:'pointer',display:'flex',"
                            "alignItems:'center',gap:'6px',fontSize:'0.9rem',"
                            f"color: wiz_run_live === {live} ? '#0b1020' : '#cbd5e1',"
                            f"background: wiz_run_live === {live} ? "
                            "wiz_run.accent : 'transparent'}",
                        ),
                    ):
                        v3.VIcon(
                            icon,
                            size=18,
                            color=(
                                f"wiz_run_live === {live} ? '#0b1020' : '#94a3b8'",
                            ),
                        )
                        html.Span(label)
            with html.Button(
                type="button",
                classes="wiz-big",
                click=(choose, "['run:term']"),
                style=(
                    "height:40px;padding:0 14px;border-radius:12px;"
                    "border:1px solid #334155;background:#0b1120;color:#e2e8f0;"
                    "font-size:0.9rem;display:flex;align-items:center;gap:6px;"
                ),
            ):
                v3.VIcon("mdi-console", size=18, color="#94a3b8")
                html.Span("Full terminal")
            v3.VBtn(
                "Cancel run",
                v_if=("wiz_run.status === 'running'",),
                color="#ef4444",
                variant="outlined",
                click=server.controller.wiz_cancel_run,
                style="text-transform:none;height:40px;",
            )
        # Stages
        with html.Div(style="display:flex;gap:12px;"):
            with html.Div(
                v_for="(st, si) in wiz_run.stages",
                key="si",
                style=(
                    "{flex:1,display:'flex',alignItems:'center',gap:'10px',"
                    "padding:'14px 16px',borderRadius:'14px',fontSize:'0.95rem',"
                    "border: st.state === 'now' ? '2px solid ' + wiz_run.accent "
                    ": (st.state === 'failed' ? '2px solid #ef4444' "
                    ": '1px solid #1e293b'),"
                    "background: st.state === 'now' ? wiz_run.accent + '1a' "
                    ": '#0b1120',"
                    "color: st.state === 'next' ? '#64748b' : '#e2e8f0'}",
                ),
            ):
                with html.Span(
                    style=(
                        "{width:'28px',height:'28px',borderRadius:'50%',"
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
        # Progress body
        with html.Div(
            v_show=("!wiz_run_live",),
            style="flex:1;min-height:0;display:flex;flex-direction:column;gap:16px;",
        ):
            with html.Div(style="display:flex;flex-direction:column;gap:8px;"):
                with html.Div(
                    style="display:flex;justify-content:space-between;font-size:0.9rem;",
                ):
                    html.Span(
                        "{{ wiz_run.error || 'Overall' }}",
                        style=(
                            "{color: wiz_run.error ? '#fca5a5' : '#cbd5e1'}",
                        ),
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
                        "height:14px;border-radius:7px;background:#1e293b;"
                        "overflow:hidden;"
                    ),
                ):
                    html.Div(
                        style=(
                            "{width: wiz_run.pct + '%',height:'100%',"
                            "borderRadius:'7px',transition:'width 0.4s',"
                            "background: wiz_run.status === 'failed' ? '#ef4444' "
                            ": 'linear-gradient(90deg, ' + wiz_run.accent + ', ' "
                            "+ wiz_run.accent2 + ')'}",
                        ),
                    )
            with html.Div(
                style=(
                    "display:grid;gap:14px;"
                    "grid-template-columns:repeat(auto-fit,minmax(200px,1fr));"
                ),
            ):
                with html.Div(
                    v_for="(s, i) in wiz_run.stats",
                    key="i",
                    style=(
                        "border-radius:14px;border:1px solid #1e293b;"
                        "background:#0b1120;padding:14px 18px;display:flex;"
                        "flex-direction:column;gap:4px;"
                    ),
                ):
                    html.Span(
                        "{{ s.k }}",
                        style=(
                            "font-size:0.72rem;color:#94a3b8;letter-spacing:0.08em;"
                            "text-transform:uppercase;"
                        ),
                    )
                    html.Span(
                        "{{ s.v }}",
                        style=(
                            "font-size:1.6rem;font-weight:700;"
                            "font-variant-numeric:tabular-nums;"
                        ),
                    )
            with html.Div(
                style=(
                    "flex:1;min-height:90px;border-radius:14px;border:1px solid "
                    "#1e293b;background:#020617;padding:10px 16px;overflow:hidden;"
                    "font-family:monospace;font-size:0.78rem;line-height:1.7;"
                    "color:#94a3b8;"
                ),
            ):
                html.Div(
                    "{{ ln }}",
                    v_for="(ln, li) in wiz_run.log",
                    key="li",
                    style="white-space:pre;overflow:hidden;text-overflow:ellipsis;",
                )
        # Live science view
        with html.Div(
            v_show=("wiz_run_live",),
            style=(
                "{flex:1,minHeight:0,borderRadius:'18px',background:'#050a14',"
                "border:'1px solid ' + wiz_run.accent + '55',display:'flex',"
                "flexDirection:'column',overflow:'hidden'}",
            ),
        ):
            with html.Div(
                style="display:flex;align-items:center;gap:10px;padding:12px 18px;",
            ):
                html.Span(
                    v_if=("wiz_run.status === 'running'",),
                    style=(
                        "width:9px;height:9px;border-radius:50%;background:#ef4444;"
                        "box-shadow:0 0 10px #ef4444;"
                    ),
                )
                html.Span(
                    "{{ wiz_run.mode === 'sageswarm' && pso_plots.length "
                    "? pso_plots[pso_plots.length - 1].name "
                    ": (wiz_run.live_caption || wiz_run.live_note) }}",
                    style="font-size:0.95rem;color:#cbd5e1;",
                )
            with html.Div(
                style=(
                    "flex:1;min-height:0;display:flex;align-items:center;"
                    "justify-content:center;padding:0 18px 18px;"
                ),
            ):
                html.Img(
                    v_if=("wiz_run.mode === 'sageswarm' && pso_plots.length",),
                    src=("pso_plots[pso_plots.length - 1].data_url",),
                    style=(
                        "max-width:100%;max-height:100%;object-fit:contain;"
                        "border-radius:10px;background:#fff;"
                    ),
                )
                html.Img(
                    v_if=("wiz_run.mode !== 'sageswarm' && wiz_run.live_img",),
                    src=("wiz_run.live_img",),
                    style="max-width:100%;max-height:100%;object-fit:contain;",
                )
                with html.Div(
                    v_if=(
                        "!(wiz_run.mode === 'sageswarm' ? pso_plots.length "
                        ": wiz_run.live_img)",
                    ),
                    style=(
                        "display:flex;flex-direction:column;align-items:center;"
                        "gap:14px;color:#94a3b8;"
                    ),
                ):
                    v3.VProgressCircular(
                        indeterminate=("wiz_run.status === 'running'",),
                        color=("wiz_run.accent",),
                        size=48,
                        width=3,
                    )
                    html.Span("{{ wiz_run.live_note }}")
        # When it's finished (or stopped)
        with html.Div(
            v_if=("wiz_run.actions && wiz_run.actions.length",),
            style="display:flex;gap:12px;justify-content:flex-end;",
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
