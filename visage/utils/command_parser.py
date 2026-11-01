"""Natural-language command parser for the Console tab.

Patterns are matched in order; the first match wins.  Each handler returns a
short string describing what it did (or an error/unknown reason), which is
shown back to the user in the console history.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from collections.abc import Callable


@dataclass
class CommandContext:
    """Bag of everything a command handler needs to act on the scene."""

    scene: object
    state: object
    ctrl: object


# A command "pattern" is a regex; the handler receives the regex match
# plus the context, and returns the response string.
Handler = Callable[[re.Match, CommandContext], str]

# Lower-cased, leading/trailing whitespace already stripped before matching.

_HELP_TEXT = """\
General:
  help                          show this list
  what's selected               summary of current state
  list models                   show discovered models
  clear / clear history         wipe console history

Show / hide (filters):
  show all  /  reset filters    reset every filter
  show only groups | clusters | isolated | field | pair
  show groups, clusters         (combine — checkboxes additive)
  hide clusters | field | isolated | group  (deselect env checkboxes)
  show centrals  /  show satellites
  hide haloes  /  show haloes
  hide galaxies  /  show galaxies
  hide everything

Navigation:
  go to halo N
  go to galaxy N            (N = GalaxyIndex)
  snap N  /  snapshot N
  redshift X  /  z X
  centre camera  /  reset camera
  focus on  /  focus off

Playback:
  play  /  pause  /  stop  /  reverse  /  loop
  speed S      (0.1, 0.25, 0.5, 0.75, 1, 2 or 5)
  rotate cw 30  /  rotate ccw 60  /  rotate off

Inspection:
  galaxy info  /  group info  /  clear indicator
  highlight galaxy  /  highlight members
  screenshot [label]

Layer controls:
  halo opacity X  /  galaxy opacity X
  colour halo by mvir|rvir|vvir
  colour galaxy by stellar_mass|sfr|ssfr|cold_gas|bt|bh_mass|ics_mass|age|density|type|structure
  halo colormap NAME  /  galaxy colormap NAME

Models:
  switch to NAME     switch primary model
  overlay NAME       toggle a compatible model overlay
"""


_HALO_MODES = {"mvir", "rvir", "vvir"}
_GAL_MODES = {
    "stellar_mass",
    "sfr",
    "ssfr",
    "cold_gas",
    "bulge_mass",
    "bt",
    "bh_mass",
    "ics_mass",
    "age",
    "density",
    "type",
    "structure",
}


# ---------------------------------------------------------------------------
# Handler implementations
# ---------------------------------------------------------------------------


def _h_help(_m, _ctx) -> str:
    return _HELP_TEXT


def _h_clear_history(_m, ctx) -> str:
    ctx.state.console_history = []
    return "(history cleared)"


def _h_reset_filters(_m, ctx) -> str:
    ctx.ctrl.reset_filters()
    return "Filters reset."


# Canonical environment classes — each maps to a state flag env_show_<class>.
_ENV_CLASSES = ("field", "isolated", "group", "cluster", "pairs")


def _h_show_only_env(m, ctx) -> str:
    """`show only groups` / `show only clusters` / ... — restrict to the named
    classes and turn every other class off (including pairs)."""
    classes = _parse_env_classes(m.group("kinds"))
    if not classes:
        return f"Unknown environment class in: {m.group('kinds')!r}"
    for c in _ENV_CLASSES:
        setattr(ctx.state, f"env_show_{c}", c in classes)
    return f"Showing: {', '.join(sorted(classes))}"


def _h_show_env_add(m, ctx) -> str:
    """`show groups` adds (rather than restricts to) the named classes."""
    classes = _parse_env_classes(m.group("kinds"))
    if not classes:
        return f"Unknown environment class in: {m.group('kinds')!r}"
    for c in classes:
        setattr(ctx.state, f"env_show_{c}", True)
    return f"Now showing: {', '.join(sorted(classes))}"


def _h_hide_env(m, ctx) -> str:
    """`hide clusters` / `hide field, isolated` — deselect env checkboxes."""
    classes = _parse_env_classes(m.group("kinds"))
    if not classes:
        return f"Unknown environment class in: {m.group('kinds')!r}"
    for c in classes:
        setattr(ctx.state, f"env_show_{c}", False)
    return f"Hidden: {', '.join(sorted(classes))}"


def _h_show_all(_m, ctx) -> str:
    ctx.ctrl.reset_filters()
    ctx.state.halos_visible = True
    ctx.state.galaxies_visible = True
    return "Showing all (filters reset, layers on)."


def _h_hide_everything(_m, ctx) -> str:
    ctx.state.halos_visible = False
    ctx.state.galaxies_visible = False
    return "Hid both layers."


def _h_layer_visibility(m, ctx) -> str:
    layer = m.group("layer")
    show = m.group("verb") in ("show",)
    if "halo" in layer:
        ctx.state.halos_visible = show
        return f"Haloes {'visible' if show else 'hidden'}."
    ctx.state.galaxies_visible = show
    return f"Galaxies {'visible' if show else 'hidden'}."


def _h_type_filter(m, ctx) -> str:
    t = m.group("type")
    ctx.state.filter_gal_type = "central" if t.startswith("c") else "satellite"
    return f"Galaxy type filter → {ctx.state.filter_gal_type}"


def _h_goto_halo(m, ctx) -> str:
    n = int(m.group("idx"))
    find = getattr(ctx.ctrl, "halo_row_for_id", None)
    row = find(n) if find is not None else n
    if row is None:
        return f"No halo {n} in this snapshot."
    ctx.state.nav_halo_idx = int(row)
    ctx.state.flush()
    ctx.ctrl.go_to_halo()
    return f"Flying to halo {n}."


def _h_goto_galaxy(m, ctx) -> str:
    """`go to galaxy N`: N is SAGE's GalaxyIndex."""
    n = int(m.group("idx"))
    find = getattr(ctx.ctrl, "galaxy_row_for_id", None)
    row = find(n) if find is not None else n
    if row is None:
        return f"No galaxy with GalaxyIndex {n} in this snapshot."
    ctx.state.nav_gal_idx = int(row)
    ctx.state.flush()
    ctx.ctrl.go_to_galaxy_enter()
    return f"Flying to galaxy {n}."


def _h_set_snap(m, ctx) -> str:
    n = int(m.group("n"))
    ctx.state.snap_num = n
    return f"Snapshot → {n}"


def _h_set_redshift(m, ctx) -> str:
    z = float(m.group("z"))
    snap = ctx.scene.primary.snap_table.z_to_snap(z)
    ctx.state.snap_num = snap
    actual_z = ctx.scene.primary.snap_table.snap_to_z(snap)
    return f"Closest snap to z={z:.3f} is snap {snap} (z={actual_z:.3f})."


def _h_center(_m, ctx) -> str:
    ctx.ctrl.center_camera()
    return "Camera centred on box."


def _h_reset_camera(_m, ctx) -> str:
    ctx.ctrl.reset_camera()
    return "Camera reset."


def _h_focus(m, ctx) -> str:
    new_state = m.group("verb") == "on"
    if bool(ctx.state.focus_active) != new_state:
        ctx.ctrl.toggle_focus()
    return f"Focus mode {'on' if new_state else 'off'}."


def _h_play(_m, ctx) -> str:
    ctx.ctrl.play()
    return "Playing."


def _h_pause(_m, ctx) -> str:
    ctx.ctrl.pause()
    return "Paused."


def _h_stop(_m, ctx) -> str:
    ctx.ctrl.stop()
    return "Stopped."


def _h_reverse(_m, ctx) -> str:
    ctx.ctrl.toggle_reverse()
    return f"Reverse {'on' if ctx.state.is_reverse else 'off'}."


def _h_loop(_m, ctx) -> str:
    ctx.ctrl.toggle_repeat()
    return f"Loop {'on' if ctx.state.is_repeat else 'off'}."


def _h_speed(m, ctx) -> str:
    s = float(m.group("s"))
    valid = {0.1, 0.25, 0.5, 0.75, 1.0, 2.0, 5.0}
    if s not in valid:
        return f"Speed {s} not in supported set {sorted(valid)}"
    ctx.state.play_speed = s if s != 1.0 else 1
    return f"Speed → {s}×"


def _h_rotate(m, ctx) -> str:
    direction = (m.group("dir") or "").lower()
    deg = m.group("deg")
    if direction in ("off", "stop") or not deg:
        ctx.state.rotate_mode = "off"
        return "Rotation stopped."
    deg = int(deg)
    if deg not in (15, 30, 60):
        return "Rotation speed must be 15, 30 or 60."
    ctx.state.rotate_mode = f"{direction}_{deg}"
    return f"Rotating {direction.upper()} at {deg}°/s."


def _h_screenshot(m, ctx) -> str:
    label = (m.group("label") or "").strip()
    if label:
        ctx.state.screenshot_label = label
    ctx.state.flush()
    ctx.ctrl.take_screenshot()
    return "Screenshot saved."


def _h_galaxy_info(_m, ctx) -> str:
    ctx.ctrl.show_galaxy_info()
    return "Selection card opened with all properties."


def _h_group_info(_m, ctx) -> str:
    ctx.ctrl.show_group_info()
    return "Selection card opened (its group is listed there)."


def _h_highlight_galaxy(_m, ctx) -> str:
    ctx.ctrl.highlight_galaxy()
    return "Highlight galaxy toggled."


def _h_highlight_members(_m, ctx) -> str:
    ctx.ctrl.highlight_group_members()
    return "Highlight members toggled."


def _h_clear_indicator(_m, ctx) -> str:
    ctx.ctrl.clear_indicator()
    return "Indicators cleared."


def _h_opacity(m, ctx) -> str:
    layer = m.group("layer")
    val = float(m.group("v"))
    val = max(0.0, min(1.0, val))
    if "halo" in layer:
        ctx.state.halo_opacity = val
        return f"Halo opacity → {val:.2f}"
    ctx.state.galaxy_opacity = val
    return f"Galaxy opacity → {val:.2f}"


def _h_color_by(m, ctx) -> str:
    layer = m.group("layer")
    mode = m.group("mode").strip().lower().replace(" ", "_")
    aliases = {
        "m*": "stellar_mass",
        "stellar": "stellar_mass",
        "mass": "stellar_mass" if "gal" in layer else "mvir",
        "bulge/total": "bt",
        "b/t": "bt",
        "bh": "bh_mass",
        "ics": "ics_mass",
        "cold": "cold_gas",
        "bulge": "bulge_mass",
    }
    mode = aliases.get(mode, mode)
    if "halo" in layer:
        if mode not in _HALO_MODES:
            return f"Unknown halo colour mode: {mode}. Allowed: {sorted(_HALO_MODES)}"
        ctx.state.halo_color_mode = mode
        return f"Halo colour-by → {mode}"
    if mode not in _GAL_MODES:
        return f"Unknown galaxy colour mode: {mode}. Allowed: {sorted(_GAL_MODES)}"
    ctx.state.galaxy_color_mode = mode
    return f"Galaxy colour-by → {mode}"


def _h_colormap(m, ctx) -> str:
    layer = m.group("layer")
    name = m.group("name").strip()
    if "halo" in layer:
        ctx.state.halo_colormap = name
        return f"Halo colormap → {name}"
    ctx.state.galaxy_colormap = name
    return f"Galaxy colormap → {name}"


def _h_switch_model(m, ctx) -> str:
    name = m.group("name").strip()
    try:
        ctx.ctrl.switch_model(name)
        return f"Switching primary model to {name!r}…"
    except Exception as e:
        return f"Couldn't switch to {name!r}: {e}"


def _h_overlay(m, ctx) -> str:
    name = m.group("name").strip()
    try:
        ctx.ctrl.toggle_overlay(name)
        return f"Toggled overlay for {name}."
    except Exception as e:
        return f"Couldn't overlay {name}: {e}"


def _h_list_models(_m, ctx) -> str:
    names = [m.name for m in ctx.scene.list_models()]
    primary = ctx.scene.primary_name
    lines = []
    for n in names:
        tag = (
            " (primary)"
            if n == primary
            else " (overlay)" if ctx.scene._models[n].visible else ""
        )
        lines.append(f"  • {n}{tag}")
    return (
        "Loaded models:\n" + "\n".join(lines) if lines else "No models loaded."
    )


def _h_whats_selected(_m, ctx) -> str:
    gal = "none"
    if ctx.state.nav_gal_idx is not None:
        try:
            from visage.utils.group_info import galaxy_label

            model = ctx.scene.active_model
            _, g = model.loader.get(model.current_snap)
            gal = galaxy_label(g, int(ctx.state.nav_gal_idx))
        except Exception:
            gal = "?"
    parts = [
        f"snap          = {ctx.scene.current_snap}",
        f"primary model = {ctx.scene.primary_name}",
        f"GalaxyIndex   = {gal}",
        f"nav_halo_idx  = {ctx.state.nav_halo_idx}",
        f"focus_active  = {bool(ctx.state.focus_active)}",
        f"is_playing    = {bool(ctx.state.is_playing)}",
    ]
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_env_classes(text: str) -> set:
    """`groups, clusters and field` → {'group', 'cluster', 'field'}"""
    text = text.lower()
    out = set()
    if "field" in text:
        out.add("field")
    if "isolat" in text:
        out.add("isolated")
    if "group" in text:
        out.add("group")
    if "cluster" in text:
        out.add("cluster")
    if "pair" in text:
        out.add("pairs")
    return out


# ---------------------------------------------------------------------------
# Command table — order matters
# ---------------------------------------------------------------------------

# Environment-class words, as a reusable regex fragment.  Used so "show only X"
# only matches real env classes and doesn't shadow e.g. "show only centrals".
_ENV_KIND = r"(?:field|isolated|groups?|clusters?|pairs?)"
_ENV_LIST = rf"{_ENV_KIND}(?:\s*,?\s*(?:and\s+)?{_ENV_KIND})*"

_COMMANDS: list[tuple[re.Pattern, Handler]] = [
    (re.compile(r"^(help|\?|commands)$"), _h_help),
    (re.compile(r"^(clear history|clear console)$"), _h_clear_history),
    (re.compile(r"^what'?s selected|where am i|status$"), _h_whats_selected),
    (re.compile(r"^list models$"), _h_list_models),
    # Filter / visibility
    (re.compile(r"^(show all|show everything|reset filters)$"), _h_show_all),
    (re.compile(r"^hide everything$"), _h_hide_everything),
    (re.compile(rf"^show only (?P<kinds>{_ENV_LIST})$"), _h_show_only_env),
    (re.compile(rf"^show (?P<kinds>{_ENV_LIST})$"), _h_show_env_add),
    (re.compile(rf"^hide (?P<kinds>{_ENV_LIST})$"), _h_hide_env),
    (
        re.compile(
            r"^(?P<verb>show|hide) (?P<layer>haloe?s?|galax(?:y|ies))$"
        ),
        _h_layer_visibility,
    ),
    (
        re.compile(
            r"^(?:show only |show |only )?(?P<type>centrals?|satellites?)$"
        ),
        _h_type_filter,
    ),
    # Navigation
    (
        re.compile(r"^(?:go to|goto|fly to)\s+halo\s+(?P<idx>\d+)$"),
        _h_goto_halo,
    ),
    (
        re.compile(r"^(?:go to|goto|fly to)\s+galaxy\s+(?P<idx>\d+)$"),
        _h_goto_galaxy,
    ),
    (re.compile(r"^(?:snap|snapshot)\s+(?P<n>\d+)$"), _h_set_snap),
    (re.compile(r"^(?:redshift|z)\s+(?P<z>[\d.+-eE]+)$"), _h_set_redshift),
    (re.compile(r"^(?:centre|center)(?:\s+camera)?$"), _h_center),
    (re.compile(r"^reset(?:\s+camera)?$"), _h_reset_camera),
    (re.compile(r"^focus\s+(?P<verb>on|off)$"), _h_focus),
    # Playback
    (re.compile(r"^play$"), _h_play),
    (re.compile(r"^pause$"), _h_pause),
    (re.compile(r"^stop$"), _h_stop),
    (re.compile(r"^reverse$"), _h_reverse),
    (re.compile(r"^(loop|repeat)$"), _h_loop),
    (re.compile(r"^speed\s+(?P<s>[\d.]+)x?$"), _h_speed),
    (re.compile(r"^rotate\s+(?P<dir>off|stop)$"), _h_rotate),
    (re.compile(r"^rotate\s+(?P<dir>cw|ccw)\s+(?P<deg>\d+)$"), _h_rotate),
    # Inspection
    (re.compile(r"^(galaxy info|show galaxy)$"), _h_galaxy_info),
    (re.compile(r"^(group info|show group)$"), _h_group_info),
    (re.compile(r"^highlight\s+(?:the\s+)?galaxy$"), _h_highlight_galaxy),
    (
        re.compile(r"^highlight\s+(?:the\s+)?(?:group\s+)?members$"),
        _h_highlight_members,
    ),
    (re.compile(r"^clear(?:\s+indicator)?$"), _h_clear_indicator),
    (re.compile(r"^screenshot(?:\s+(?P<label>\S.*))?$"), _h_screenshot),
    # Layer controls
    (
        re.compile(
            r"^(?:set\s+)?(?P<layer>halo|galax(?:y|ies))\s+opacity\s+(?P<v>[\d.]+)$"
        ),
        _h_opacity,
    ),
    (
        re.compile(
            r"^colou?r\s+(?P<layer>halo|galax(?:y|ies))\s+by\s+(?P<mode>.+)$"
        ),
        _h_color_by,
    ),
    (
        re.compile(
            r"^(?P<layer>halo|galax(?:y|ies))\s+colou?r\s+by\s+(?P<mode>.+)$"
        ),
        _h_color_by,
    ),
    (
        re.compile(
            r"^(?P<layer>halo|galax(?:y|ies))\s+colou?rmap\s+(?P<name>.+)$"
        ),
        _h_colormap,
    ),
    # Models
    (re.compile(r"^switch(?:\s+to)?\s+(?P<name>.+)$"), _h_switch_model),
    (re.compile(r"^overlay\s+(?P<name>.+)$"), _h_overlay),
]


def execute_command(cmd: str, ctx: CommandContext) -> str:
    """Match `cmd` against the command table and run the first matching handler."""
    text = " ".join(cmd.strip().split()).lower()
    if not text:
        return ""
    for pat, handler in _COMMANDS:
        m = pat.match(text)
        if m is not None:
            try:
                return handler(m, ctx)
            except Exception as e:
                return f"Error executing: {e}"
    return f"Unknown command: {cmd!r}.  Type 'help' for the full list."
