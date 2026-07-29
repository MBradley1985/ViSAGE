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
            # Row wrapper — expands to two columns when an editor is visible
            with html.Div(
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
                #    sage-lightcone run_lightcone.sh ─────────────────────────
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
                        style="flex:1;min-height:0;overflow-y:auto;padding:10px 14px;",
                    ):
                        # A fixed pool of rows, each bound to its OWN scalar
                        # state var (wiz_pv_<i>) so trame reliably syncs edits.
                        # Rows beyond the current parameter count stay hidden.
                        for i in range(_MAX_PARAMS):
                            with html.Div(
                                v_show=(f"{i} < wiz_param_count",),
                                style=(
                                    "display:flex;align-items:center;gap:12px;"
                                    "margin-bottom:8px;"
                                ),
                            ):
                                html.Div(
                                    f"{{{{ wiz_pl_{i} }}}}",
                                    title=(f"wiz_ph_{i}",),
                                    style=(
                                        "min-width:200px;max-width:200px;"
                                        "text-align:right;color:#9ca3af;"
                                        "font-family:monospace;font-size:0.78rem;"
                                        "overflow:hidden;text-overflow:ellipsis;"
                                        "white-space:nowrap;flex-shrink:0;"
                                    ),
                                )
                                v3.VTextField(
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
                            style="color:#9ca3af;font-size:0.8rem;",
                        )

        # SAGE logo — pinned to bottom-right corner of the wizard screen
        html.Img(
            src="/sage_static/SAGElogo.jpg",
            style=(
                "position:absolute;bottom:16px;right:16px;"
                "width:90px;"
                "pointer-events:none;"
            ),
        )
