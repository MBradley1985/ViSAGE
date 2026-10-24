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
                            v_show=("wiz_run_active",),
                            style="display:flex;align-items:center;gap:8px;",
                        ):
                            v3.VBtn(
                                "Cancel (Ctrl+C)",
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
                classes="wiz-big",
                disabled=("a.disabled",),
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
                    icon=("a.icon",),
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
                            "color: a.primary ? '#1e293b' : '#94a3b8'}",
                        ),
                    )
