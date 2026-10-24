"""Launch Mode's setup and run screens (mixed into WizardController).

Setup: the key choices for each tool as big buttons (SAGE26: simulation
and physics; LightSAGE: model, sky and depth, surveys; SAGEswarm:
observations to match, effort, free parameters), with every value of the
file under All settings, grouped into sections.

Run: a progress dashboard read from each tool's own output (SAGE26's
progress bar, LightSAGE's stage lines and photometry steps, SAGEswarm's
particle counts and best score), with a live view of the science: the
model's stellar mass function against GAMA, the new lightcone, or the
calibration plots.
"""

from __future__ import annotations

import asyncio
import codecs
import re
import time
from collections import deque
from pathlib import Path

_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b[()][A-Za-z0-9]")

# SAGE26 physics switches shown as big toggles (their .par comments are the
# descriptions).  AGNrecipeOn chooses a recipe (1-3), so "on" restores the
# recipe it had.
_PHYSICS = [
    ("SupernovaRecipeOn", "Supernova feedback"),
    ("AGNrecipeOn", "AGN feedback"),
    ("ReionizationOn", "Reionization"),
    ("DiskInstabilityOn", "Disk instabilities"),
    ("CGMrecipeOn", "CGM"),
    ("FIREmodeOn", "FIRE mode"),
    ("EnhancedStarFormationOn", "Burst star formation"),
    ("SaveFullSFH", "Full star-formation histories"),
]

_LC_PRESETS = [
    (
        "sdss",
        "SDSS-like patch",
        "10° × 5° · z < 0.1",
        {
            "RAMIN": 0,
            "RAMAX": 10,
            "DECMIN": 0,
            "DECMAX": 5,
            "ZMIN": 0,
            "ZMAX": 0.1,
        },
    ),
    (
        "wide",
        "Wide & deeper",
        "20° × 5° · z < 0.2",
        {
            "RAMIN": 0,
            "RAMAX": 20,
            "DECMIN": 0,
            "DECMAX": 5,
            "ZMIN": 0,
            "ZMAX": 0.2,
        },
    ),
    (
        "pencil",
        "Deep pencil beam",
        "1° × 1° · z < 2",
        {
            "RAMIN": 0,
            "RAMAX": 1,
            "DECMIN": 0,
            "DECMAX": 1,
            "ZMIN": 0,
            "ZMAX": 2,
        },
    ),
]

_LC_TOGGLES = [
    ("SED_ENABLED", "Photometry", "Magnitudes in the chosen surveys"),
    ("SED_DUST_ENABLED", "Dust", "From each galaxy's own gas and metals"),
    (
        "SED_DUST_EMISSION_ENABLED",
        "Infrared glow",
        "Absorbed light re-emitted",
    ),
    ("SED_LINES_ENABLED", "Emission lines", "Star formation and AGN"),
    ("SED_DISK_BULGE_ENABLED", "Disk & bulge", "Separate magnitudes"),
]

_SW_EFFORT = [
    ("quick", "Quick look", 10, 10),
    ("standard", "Standard", 20, 30),
    ("thorough", "Thorough", 40, 50),
]

# All-settings sections: (section, test on the key).
_PAR_SECTIONS = [
    (
        "Simulation & trees",
        lambda k: k
        in (
            "FileNameGalaxies OutputDir FirstFile LastFile NumOutputs "
            "OutputFormat TreeName TreeType NumSimulationTreeFiles "
            "SimulationDir FileWithSnapList LastSnapShotNr PartMass BoxSize "
            "SaveFullSFH ForestDistributionScheme "
            "ExponentForestDistributionScheme"
        ).split(),
    ),
    (
        "Cosmology",
        lambda k: k in ("Omega", "OmegaLambda", "BaryonFrac", "Hubble_h"),
    ),
    (
        "Star formation & feedback",
        lambda k: k.startswith(("Sfr", "SF", "Feedback", "Enhanced", "Energy"))
        or k
        in (
            "SupernovaRecipeOn ReIncorporationFactor EtaSN Yield "
            "RecycleFraction FracZleaveDisk FIREmodeOn"
        ).split(),
    ),
    (
        "Black holes & AGN",
        lambda k: k.startswith("AGN")
        or k
        in (
            "RadioModeEfficiency",
            "QuasarModeEfficiency",
            "BlackHoleGrowthRate",
        ),
    ),
    (
        "Mergers & disks",
        lambda k: k.startswith(("Thresh", "Merger", "DiskInstab")),
    ),
    (
        "Reionization & haloes",
        lambda k: k.startswith(("Reioniz", "CGM", "Concentration")),
    ),
    ("Units", lambda k: k.startswith("Unit")),
]
_LC_SECTIONS = [
    (
        "Source model",
        lambda k: k
        in (
            "LIGHTCONE_DIR",
            "SAGE_OUTPUT_DIR",
            "PARAM_FILE",
            "ALIST_FILE",
            "KDTREE_OUT",
        ),
    ),
    ("Sky & depth", lambda k: k.startswith(("RA", "DEC", "Z"))),
    ("Surveys", lambda k: k.startswith("SURVEY_")),
    (
        "Dust & lines",
        lambda k: k.startswith(("SED_DUST", "SED_LINES", "SED_DISK")),
    ),
    ("Photometry", lambda k: k.startswith(("SED_", "BAND_"))),
    ("Output", lambda k: True),
]
_SW_SECTIONS = [
    ("Model", lambda k: k in ("CONFIG_PATH", "BASE_PATH")),
    (
        "Swarm",
        lambda k: k
        in ("PARTICLES", "ITERATIONS", "TEST", "CONSTRAINTS", "SPACEFILE"),
    ),
    ("Output", lambda k: True),
]


def _readable(line: str) -> bool:
    """A log line worth showing: words, not progress bars or ASCII art."""
    text = line.strip()
    if not text or text.startswith("Progress:") or "█" in text:
        return False
    chars = [ch for ch in text if not ch.isspace()]
    return sum(ch.isalnum() for ch in chars) >= 0.4 * len(chars)


def _section(key: str, sections) -> str:
    return next((name for name, test in sections if test(key)), "Other")


def _num(v) -> float | None:
    try:
        return float(str(v).strip().strip('"'))
    except ValueError:
        return None


def _constraint_group(name: str) -> str:
    if name.startswith("SMF"):
        return "Stellar mass functions"
    if name.startswith(("BH",)):
        return "Black holes"
    if name in ("HIMF", "H2MF", "CSFRDH", "SMD"):
        return "Gas & star formation"
    return "Scaling relations"


# The live view for SAGE26 and LightSAGE: frames of a box and a lightcone
# filling up, drawn once from real outputs (Millennium box,
# microUchuu v2 lightcone).
_LIVE_NOTE = {
    "sage26": "A SAGE26 box (Millennium, z = 0) filling with galaxies as "
    "the trees are built: star-forming blue, quiescent orange",
    "sagelightcone": "A LightSAGE cone (microUchuu, z < 0.2) filling outwards "
    "from the observer: star-forming blue, quiescent orange",
    "sageswarm": "SAGEswarm's plots appear here as it makes them.",
}


def _fill_frame(mode: str, pct: float) -> str:
    if mode == "sagelightcone":
        pct = pct / 0.55  # the cone is cut by 55%; photometry follows
    step = int(min(max(pct, 0.0), 100.0) // 5 * 5)
    name = "box" if mode == "sage26" else "cone"
    return f"/sage_static/wizard/fill/{name}_{step:03d}.webp"


class SetupRunMixin:
    """Setup (essentials + All settings) and run (dashboard + live view)."""

    # ── config text helpers ──────────────────────────────────────────────

    def _cfg(self, mode: str) -> tuple[str, str, str]:
        """(state var holding the text, 'par'|'sh', pool target)."""
        return {
            "sage26": ("wiz_par_text", "par", "par"),
            "sagelightcone": ("wiz_lc_script_text", "sh", "lc"),
            "sageswarm": ("wiz_sw_script_text", "sh", "sw"),
        }[mode]

    def _cfg_values(self, mode: str) -> dict:
        from visage.wizard.controller import _parse_params

        var, kind, _ = self._cfg(mode)
        return {
            p["key"]: p for p in _parse_params(str(self._st[var] or ""), kind)
        }

    def _cfg_set(self, mode: str, values: dict) -> None:
        from visage.wizard.controller import _apply_params

        var, kind, _ = self._cfg(mode)
        self._st[var] = _apply_params(
            str(self._st[var] or ""),
            [{"key": k, "value": str(v)} for k, v in values.items()],
            kind,
        )

    def _refresh_pool(self, mode: str) -> None:
        """Fill the All-settings slots from the current text, each tagged
        with its section."""
        var, kind, target = self._cfg(mode)
        self._show_params(str(self._st[var] or ""), kind, target)
        sections = {
            "sage26": _PAR_SECTIONS,
            "sagelightcone": _LC_SECTIONS,
            "sageswarm": _SW_SECTIONS,
        }[mode]
        vals = self._cfg_values(mode)
        counts: dict[str, int] = {}
        for i, key in enumerate(self._param_keys):
            sec = _section(key, sections)
            self._st[f"wiz_pg_{i}"] = sec
            counts[sec] = counts.get(sec, 0) + 1
            if key.endswith("On") or key == "SaveFullSFH":
                v = str(vals.get(key, {}).get("value", "")).strip()
                self._st[f"wiz_pcb_{i}"] = v in ("0", "1")
        order = [s for s, _ in sections] + ["Other"]
        self._st.wiz_sections = [
            {"name": s, "count": counts[s]} for s in order if s in counts
        ]
        if self._st.wiz_section not in counts:
            self._st.wiz_section = self._st.wiz_sections[0]["name"]
        self._st.flush()

    # ── setup: load, render, choose ──────────────────────────────────────

    async def _show_setup(self, mode: str) -> None:
        """Load the tool's config (as the old editor steps did) and show
        its essentials screen."""
        self._setup_mode = mode
        self._st.wiz_section = ""
        if mode == "sage26":
            pars = self._find_par_files()
            if self._par_path is None or self._par_path not in pars:
                # The .par used most recently.
                self._par_path = (
                    max(pars, key=lambda q: q.stat().st_mtime)
                    if pars
                    else None
                )
            if self._par_path is not None:
                self._st.wiz_par_text = self._read_text(self._par_path)
        elif mode == "sagelightcone":
            await self._step_lc_config()
            self._st.wiz_lc_config_show = False
        else:
            await self._step_sw_config()
            self._st.wiz_sw_config_show = False
            self._st.pso_gallery_show = False
        self._render_setup()
        self._st.wiz_view = "setup"
        self._st.wiz_mode = mode
        self._st.wiz_step = 3
        self._set_choices([])

    def _render_setup(self) -> None:
        mode = self._setup_mode
        from visage.wizard.controller import _MODE_META

        meta = _MODE_META[mode]
        vals = self._cfg_values(mode)
        groups: list[dict] = []
        note = ""
        if mode == "sage26":
            name = self._par_path.stem if self._par_path else "my_run"
            sims = []
            for p in self._find_par_files():
                from visage.wizard.controller import _parse_params

                try:
                    pv = {
                        q["key"]: q["value"].split(";")[0].strip()
                        for q in _parse_params(self._read_text(p), "par")
                    }
                except OSError:
                    continue
                bits = []
                if "BoxSize" in pv:
                    bits.append(f"{pv['BoxSize']} Mpc/h box")
                if "LastSnapShotNr" in pv:
                    bits.append(
                        f"{int(_num(pv['LastSnapShotNr']) or 0) + 1} snapshots"
                    )
                if "TreeType" in pv:
                    bits.append(pv["TreeType"])
                sims.append(
                    {
                        "label": p.stem,
                        "sub": " · ".join(bits),
                        "value": f"su:sim:{p}",
                        "on": p == self._par_path,
                    }
                )
            groups.append(
                {"title": "Which simulation", "kind": "cards", "items": sims}
            )
            tiles = []
            for key, label in _PHYSICS:
                if key not in vals:
                    continue
                v = _num(vals[key]["value"]) or 0
                tiles.append(
                    {
                        "label": label,
                        "sub": vals[key]["hint"],
                        "code": f"{key} = {vals[key]['value']}",
                        "value": f"su:tog:{key}",
                        "on": v != 0,
                    }
                )
            groups.append(
                {"title": "Physics", "kind": "toggles", "items": tiles}
            )
            if not self._status.get("sage26", {}).get("ready"):
                note = "SAGE26 isn't compiled yet: use Install first."
            run_label = "Run SAGE26"
        elif mode == "sagelightcone":
            name = Path(
                str(vals.get("OUTFILE", {}).get("value", "lightcone.h5"))
            ).stem
            cur_out = str(vals.get("SAGE_OUTPUT_DIR", {}).get("value", ""))
            models = []
            for m in self._models:
                out = Path(m["hdf5"]).parent
                sfh = self._has_sfh(Path(m["hdf5"]))
                models.append(
                    {
                        "label": m["name"],
                        "sub": (
                            "star-formation histories saved"
                            if sfh
                            else "no star-formation histories: no photometry"
                        ),
                        "value": f"su:lcm:{m['name']}",
                        "on": self._tc_path(out).rstrip("/")
                        == cur_out.rstrip("/"),
                        "dim": not sfh,
                    }
                )
            groups.append(
                {
                    "title": "From which SAGE26 model",
                    "kind": "cards",
                    "items": models,
                }
            )
            cur = {
                k: _num(vals.get(k, {}).get("value"))
                for k in _LC_PRESETS[0][3]
            }
            presets = []
            for pid, label, sub, pv in _LC_PRESETS:
                presets.append(
                    {
                        "label": label,
                        "sub": sub,
                        "value": f"su:preset:{pid}",
                        "on": all(cur[k] == float(v) for k, v in pv.items()),
                    }
                )
            custom = not any(p["on"] for p in presets)
            presets.append(
                {
                    "label": "Custom",
                    "sub": (
                        f"RA {cur['RAMIN']:g}–{cur['RAMAX']:g}°, Dec "
                        f"{cur['DECMIN']:g}–{cur['DECMAX']:g}°, z "
                        f"{cur['ZMIN']:g}–{cur['ZMAX']:g}"
                        if None not in cur.values()
                        else "set RA, Dec and z in All settings"
                    ),
                    "value": "su:custom",
                    "on": custom,
                }
            )
            groups.append(
                {
                    "title": "How much sky, how deep",
                    "kind": "cards",
                    "items": presets,
                }
            )
            from visage.sed.filters import SURVEYS

            chips = []
            for key, label, _f, _d in SURVEYS:
                k = f"SURVEY_{key}_ENABLED"
                if k in vals:
                    chips.append(
                        {
                            "label": label,
                            "value": f"su:tog:{k}",
                            "on": str(vals[k]["value"]).strip() == "1",
                        }
                    )
            groups.append(
                {"title": "Observe it with", "kind": "chips", "items": chips}
            )
            tiles = [
                {
                    "label": label,
                    "sub": sub,
                    "value": f"su:tog:{key}",
                    "on": str(vals[key]["value"]).strip() == "1",
                }
                for key, label, sub in _LC_TOGGLES
                if key in vals
            ]
            groups.append(
                {"title": "Light", "kind": "toggles", "items": tiles}
            )
            run_label = "Build lightcone"
        else:
            name = Path(
                str(vals.get("OUTPUT_PATH", {}).get("value", "pso"))
            ).name
            on = self._sw_constraints(vals)
            avail = self._sw_available_constraints() or sorted(on)
            by_group: dict[str, list] = {}
            for c in avail:
                by_group.setdefault(_constraint_group(c), []).append(
                    {"label": c, "value": f"su:con:{c}", "on": c in on}
                )
            for title, items in by_group.items():
                groups.append(
                    {
                        "title": title,
                        "kind": "chips",
                        "items": items,
                        "small": True,
                    }
                )
            groups.insert(
                0,
                {
                    "title": f"Match these observations ({len(on)} chosen)",
                    "kind": "heading",
                    "items": [],
                },
            )
            s = _num(vals.get("PARTICLES", {}).get("value"))
            it = _num(vals.get("ITERATIONS", {}).get("value"))
            effort = [
                {
                    "label": label,
                    "sub": f"{p} particles × {n} iterations · {p * (n + 1):,} SAGE26 runs",
                    "value": f"su:effort:{eid}",
                    "on": s == p and it == n,
                }
                for eid, label, p, n in _SW_EFFORT
            ]
            groups.append(
                {
                    "title": "How hard to search",
                    "kind": "cards",
                    "items": effort,
                }
            )
            free = [
                {"label": f"{n}  {lo} – {hi}", "value": "", "on": True}
                for n, lo, hi in self._sw_space(vals)
            ]
            groups.append(
                {
                    "title": "Free parameters (space file)",
                    "kind": "chips",
                    "items": free,
                    "static": True,
                }
            )
            run_label = "Start calibration"
        self._st.wiz_setup_name = name
        self._st.wiz_setup = {
            "mode": mode,
            "title": {
                "sage26": "Run SAGE26",
                "sagelightcone": "Build a lightcone",
                "sageswarm": "Calibrate SAGE26",
            }[mode],
            "back_label": meta["title"],
            "accent": meta["accent"],
            "accent2": meta["accent2"],
            "groups": groups,
            "run_label": run_label,
            "note": note,
        }
        self._st.flush()

    def _has_sfh(self, hdf5: Path) -> bool:
        try:
            import h5py

            with h5py.File(hdf5, "r") as h:
                snaps = [k for k in h.keys() if k.startswith("Snap_")]
                return bool(snaps) and "SFHMassDisk" in h[snaps[0]]
        except Exception:
            return False

    def _sw_constraints(self, vals: dict) -> dict[str, str]:
        """Chosen constraint name -> its full token (keeping any range or
        weight suffix)."""
        raw = str(vals.get("CONSTRAINTS", {}).get("value", ""))
        out = {}
        for tok in [t.strip() for t in raw.split(",") if t.strip()]:
            out[re.split(r"[(*]", tok, maxsplit=1)[0]] = tok
        return out

    def _sw_space(self, vals: dict) -> list[tuple[str, str, str]]:
        raw = str(vals.get("SPACEFILE", {}).get("value", "")).strip()
        if not raw or not self._sw_dir:
            return []
        p = self._toolchain.native(raw)
        p = p if p.is_absolute() else self._sw_dir / p
        rows = []
        try:
            for line in p.read_text().splitlines():
                parts = [x.strip() for x in line.split(",")]
                if len(parts) >= 5 and not line.lstrip().startswith("#"):
                    rows.append((parts[0], parts[3], parts[4]))
        except OSError:
            pass
        return rows

    async def _setup_choose(self, what: str) -> None:
        mode = self._setup_mode
        vals = self._cfg_values(mode)
        if what.startswith("sim:"):
            self._par_path = Path(what[len("sim:") :])
            self._st.wiz_par_text = self._read_text(self._par_path)
        elif what.startswith("tog:"):
            key = what[len("tog:") :]
            v = str(vals.get(key, {}).get("value", "0")).strip()
            if key == "AGNrecipeOn":
                if _num(v):
                    self._agn_recipe = v
                    new = "0"
                else:
                    new = getattr(self, "_agn_recipe", "2")
            else:
                new = "0" if _num(v) else "1"
            self._cfg_set(mode, {key: new})
        elif what.startswith("lcm:"):
            m = next(
                (x for x in self._models if x["name"] == what[len("lcm:") :]),
                None,
            )
            if m is not None:
                self._cfg_set(mode, self._lc_model_paths(m))
        elif what.startswith("preset:"):
            pv = next(
                p[3] for p in _LC_PRESETS if p[0] == what[len("preset:") :]
            )
            self._cfg_set(mode, {k: f"{v:g}" for k, v in pv.items()})
        elif what == "custom":
            await self._show_all_settings(section="Sky & depth")
            return
        elif what.startswith("con:"):
            name = what[len("con:") :]
            on = self._sw_constraints(vals)
            if name in on:
                if len(on) > 1:
                    on.pop(name)
            else:
                on[name] = name
            self._cfg_set(mode, {"CONSTRAINTS": ",".join(on.values())})
        elif what.startswith("effort:"):
            _, _, p, n = next(
                e for e in _SW_EFFORT if e[0] == what[len("effort:") :]
            )
            self._cfg_set(mode, {"PARTICLES": p, "ITERATIONS": n})
        elif what == "all":
            await self._show_all_settings()
            return
        elif what == "back":
            self._sync_params_to_text()
            self._render_setup()
            self._st.wiz_view = "setup"
            self._set_choices([])
            return
        elif what == "run":
            await self._setup_run()
            return
        self._render_setup()
        self._set_choices([])

    def _lc_model_paths(self, m: dict) -> dict:
        """run_lightcone.sh paths for a SAGE26 model: its output folder,
        .par, a_list (from the .par) and a KD-tree named after it."""
        from visage.wizard.controller import _parse_params

        out = Path(m["hdf5"]).parent
        par = Path(m["par"])
        vals = {
            "SAGE_OUTPUT_DIR": self._tc_path(out),
            "PARAM_FILE": self._tc_path(par),
        }
        try:
            pv = {
                q["key"]: q["value"].split(";")[0].strip()
                for q in _parse_params(self._read_text(par), "par")
            }
            alist = Path(pv.get("FileWithSnapList", ""))
            if alist and not alist.is_absolute() and self._sage26_dir:
                alist = self._sage26_dir / alist
            if str(alist):
                vals["ALIST_FILE"] = self._tc_path(alist)
        except OSError:
            pass
        vals["KDTREE_OUT"] = f"./{m['name']}-kdtree.h5"
        return vals

    async def _show_all_settings(self, section: str | None = None) -> None:
        self._refresh_pool(self._setup_mode)
        if section and any(
            s["name"] == section for s in self._st.wiz_sections
        ):
            self._st.wiz_section = section
        self._st.wiz_param_search = ""
        self._st.wiz_view = "all"
        self._set_choices([])

    def _apply_setup_name(self) -> None:
        """The run name: SAGE26 -> a .par of that name (OutputDir
        output/<name>/, so ViSAGE pairs model and .par); LightSAGE ->
        OUTDIR/OUTFILE; SAGEswarm -> its output folder."""
        mode = self._setup_mode
        name = re.sub(
            r"[^\w.-]+", "_", str(self._st.wiz_setup_name or "").strip()
        )
        if not name:
            return
        vals = self._cfg_values(mode)
        if mode == "sage26" and self._par_path is not None:
            if name != self._par_path.stem:
                self._par_path = self._par_path.with_name(f"{name}.par")
            od = str(vals.get("OutputDir", {}).get("value", ""))
            if od:
                trail = "/" if od.endswith("/") else ""
                parent = (
                    od.rstrip("/").rsplit("/", 1)[0]
                    if "/" in od.rstrip("/")
                    else ""
                )
                self._cfg_set(
                    mode,
                    {
                        "OutputDir": (
                            f"{parent}/{name}{trail}"
                            if parent
                            else f"{name}{trail}"
                        )
                    },
                )
        elif mode == "sagelightcone":
            od = str(vals.get("OUTDIR", {}).get("value", ""))
            parent = od.rstrip("/").rsplit("/", 1)[0] if "/" in od else od
            self._cfg_set(
                mode, {"OUTDIR": f"{parent}/{name}", "OUTFILE": f"{name}.h5"}
            )
        elif mode == "sageswarm":
            self._cfg_set(
                mode,
                {"OUTPUT_PATH": f"./{name}", "CSVOUTPUT": f"./{name}/pso.csv"},
            )

    # ── run: dashboard + live view ───────────────────────────────────────

    def _run_init(self, mode: str) -> None:
        from visage.wizard.controller import _MODE_META

        meta = _MODE_META[mode]
        vals = self._cfg_values(mode)
        stages = {
            "sage26": [
                "Read parameters",
                "Build galaxies",
                "Write output",
                "Open in Explore",
            ],
            "sagelightcone": [
                "Index the box",
                "Cut the cone",
                "Photometry",
                "Open in Lightcone view",
            ],
            "sageswarm": ["Start the swarm", "Search", "Best fit"],
        }[mode]
        self._run = {
            "mode": mode,
            "t0": time.time(),
            "stage": 0,
            "pct": 0.0,
            "eta": "",
            "lines": deque(maxlen=400),
            "partial": "",
            "decoder": codecs.getincrementaldecoder("utf-8")("replace"),
            "last_push": 0.0,
            "best": None,
            "iter": 0,
            "parts": "",
            "S": _num(vals.get("PARTICLES", {}).get("value")) or 0,
            "M": _num(vals.get("ITERATIONS", {}).get("value")) or 0,
            "photometry": str(
                vals.get("SED_ENABLED", {}).get("value", "0")
            ).strip()
            == "1",
        }
        sub = {
            "sage26": self._par_path.name if self._par_path else "",
            "sagelightcone": str(self._st.wiz_setup_name or ""),
            "sageswarm": ", ".join(self._sw_constraints(vals)),
        }[mode]
        self._st.wiz_run = {
            "mode": mode,
            "title": {
                "sage26": "Running SAGE26",
                "sagelightcone": "Building a lightcone",
                "sageswarm": "Calibrating SAGE26",
            }[mode],
            "sub": sub,
            "accent": meta["accent"],
            "accent2": meta["accent2"],
            "stages": [{"label": s, "state": "next"} for s in stages],
            "pct": 0,
            "stats": [],
            "log": [],
            "status": "running",
            "live_img": "",
            "live_note": "",
            "actions": [],
        }
        self._st.wiz_run_live = False
        self._run_publish(force=True)

    def _run_output(self, data: bytes) -> None:
        """Every chunk a run prints: keep the readable lines and read the
        progress out of them."""
        run = getattr(self, "_run", None)
        if not run or self._st.wiz_view not in ("run", "term"):
            return
        # Decode across chunk edges (multi-byte characters split between
        # reads).
        text = _ANSI.sub("", run["decoder"].decode(data))
        text = run["partial"] + text
        parts = text.split("\n")
        run["partial"] = parts.pop()
        for raw in parts:
            # A terminal ends lines with \r\n; a bare \r redraws the line.
            line = raw.rstrip("\r").split("\r")[-1].rstrip()
            self._run_parse(line)
            if _readable(line):
                run["lines"].append(line)
        tail = [t for t in run["partial"].split("\r") if t.strip()]
        if tail:  # a line still being redrawn (progress bars)
            self._run_parse(tail[-1])
        self._run_publish()

    def _run_parse(self, line: str) -> None:
        run = self._run
        mode = run["mode"]
        if mode == "sage26":
            if "reading parameter file" in line:
                run["stage"] = max(run["stage"], 0)
            m = re.search(
                r"Progress:.*?(\d+)%\s*\|\s*ETA:\s*(\d+):(\d+):(\d+)", line
            )
            if m:
                run["stage"] = max(run["stage"], 1)
                run["pct"] = float(m.group(1))
                h, mi, s = (int(m.group(i)) for i in (2, 3, 4))
                run["eta"] = f"{h}:{mi:02d}:{s:02d}" if h else f"{mi}:{s:02d}"
            if "done processing all forests" in line:
                run["stage"], run["pct"] = 2, 100.0
        elif mode == "sagelightcone":
            if "==> Stage 1" in line:
                run["stage"] = 0
            elif "==> Stage 2" in line:
                run["stage"], run["pct"] = 1, 25.0
            elif "==> Lightcone written" in line:
                run["stage"], run["pct"] = 2, 55.0
                path = line.split("==> Lightcone written to", 1)[-1].strip()
                asyncio.ensure_future(self._run_live_cone(path))
            m = re.search(r"\[(\d+)/(\d+)\]\s+snap=", line)
            if m:
                run["stage"] = 2
                run["pct"] = 55.0 + 45.0 * int(m.group(1)) / max(
                    int(m.group(2)), 1
                )
        else:
            m = re.search(
                r"(Init|Iter (\d+))\s+\[[^\]]*\]\s+(\d+)/(\d+) particles", line
            )
            if m:
                run["stage"] = 1
                it = int(m.group(2) or 0)
                done, tot = int(m.group(3)), int(m.group(4))
                run["iter"], run["parts"] = it, f"{done} / {tot}"
                total = tot * (run["M"] + 1) if run["M"] else tot
                run["pct"] = 100.0 * (it * tot + done) / max(total, 1)
            m = re.search(r"swarm best=\s*([-\d.eE+]+)", line) or re.search(
                r"New swarm best:\s*([-\d.eE+]+)", line
            )
            if m:
                run["best"] = m.group(1)
            if "Stopping search" in line:
                run["stage"], run["pct"] = 2, 100.0

    def _run_publish(self, force: bool = False) -> None:
        run = self._run
        now = time.time()
        if not force and now - run["last_push"] < 0.3:
            return
        run["last_push"] = now
        info = dict(self._st.wiz_run)
        status = info["status"]
        stages = []
        for i, s in enumerate(info["stages"]):
            if status == "done":
                state = "done"
            elif i < run["stage"]:
                state = "done"
            elif i == run["stage"]:
                state = "failed" if status == "failed" else "now"
            else:
                state = "next"
            stages.append({**s, "state": state})
        el = int(now - run["t0"])
        elapsed = (
            f"{el // 3600}:{el // 60 % 60:02d}:{el % 60:02d}"
            if el >= 3600
            else f"{el // 60}:{el % 60:02d}"
        )
        mode = run["mode"]
        stats = [{"k": "Elapsed", "v": elapsed}]
        if mode == "sage26":
            stats.append({"k": "Time left", "v": run["eta"] or "—"})
            stats.append(
                {"k": "Galaxies built", "v": f"{run['pct']:.0f}% of trees"}
            )
        elif mode == "sagelightcone":
            stats.append(
                {
                    "k": "Stage",
                    "v": (
                        "Done"
                        if status == "done"
                        else stages[min(run["stage"], 2)]["label"]
                    ),
                }
            )
            if run.get("ngal"):
                stats.append(
                    {"k": "Galaxies in the cone", "v": f"{run['ngal']:,}"}
                )
        else:
            m_tot = int(run["M"]) if run["M"] else "?"
            stats.append({"k": "Iteration", "v": f"{run['iter']} / {m_tot}"})
            stats.append({"k": "Particles", "v": run["parts"] or "—"})
            stats.append({"k": "Best score", "v": run["best"] or "—"})
        pct = 100.0 if status == "done" else run["pct"]
        info.update(
            stages=stages,
            pct=round(pct, 1),
            stats=stats,
            log=list(run["lines"])[-6:],
        )
        if mode != "sageswarm":
            info["live_img"] = _fill_frame(mode, pct)
        self._st.wiz_run = info
        self._st.flush()

    async def _run_live_cone(self, path: str) -> None:
        """How many galaxies the new cone holds (for the stats)."""
        cone = self._toolchain.native(path.strip().strip('"'))
        if not cone.is_absolute():
            cone = self._lc_script_path().parent / cone
        try:
            import h5py

            with h5py.File(cone, "r") as h:
                self._run["ngal"] = int(h["ra"].shape[0])
        except Exception:
            return
        self._run_publish(force=True)

    async def _setup_run(self) -> None:
        """Save the config and run it on the progress screen."""
        mode = self._setup_mode
        if self._st.wiz_view == "all":
            self._sync_params_to_text()
        self._apply_setup_name()
        self._refresh_pool(mode)  # keep the slots in step with the text
        self._run_init(mode)
        self._st.wiz_view = "run"
        self._wiz_buf = bytearray()
        self._push_bytes(b"\x1b[2J\x1b[3J\x1b[H")
        self._last_rc = None
        info = dict(self._st.wiz_run)
        info["live_note"] = _LIVE_NOTE[mode]
        self._st.wiz_run = info
        self._st.flush()
        step = {
            "sage26": self._step_run_sage26,
            "sagelightcone": self._step_lc_run,
            "sageswarm": self._step_sw_run,
        }[mode]
        await step()
        self._st.pso_gallery_show = False
        await self._run_finish(mode)

    async def _run_finish(self, mode: str) -> None:
        from visage.wizard.controller import _MODE_META

        rc = self._last_rc
        info = dict(self._st.wiz_run)
        back = {
            "label": f"Back to {_MODE_META[mode]['title']}",
            "value": f"mode:{mode}",
            "icon": "mdi-arrow-left",
        }
        if rc is None and info["status"] == "running":
            info["status"] = "failed"
            info["error"] = "It didn't start: see the full terminal."
        elif rc not in (0, None):
            info["status"] = "failed"
            info["error"] = (
                f"It stopped with an error (exit code {rc}): see the full terminal."
            )
        else:
            info["status"] = "done"
        actions = []
        if info["status"] == "done":
            self._run["stage"] = len(info["stages"])
            if mode == "sage26":
                out = self._sage26_output_dir()
                name = out.name if out else ""
                self._models = self._find_models()
                if any(m["name"] == name for m in self._models):
                    actions.append(
                        {
                            "label": "Open in Explore",
                            "value": f"model:{name}",
                            "icon": "mdi-play",
                            "primary": True,
                        }
                    )
            elif mode == "sagelightcone":
                actions.append(
                    {
                        "label": "Open in Lightcone view",
                        "value": "lc_visualize",
                        "icon": "mdi-telescope",
                        "primary": True,
                    }
                )
            else:
                self._st.wiz_run_live = True
        else:
            actions.append(
                {
                    "label": "Change settings",
                    "value": "su:reopen",
                    "icon": "mdi-tune",
                }
            )
        actions.append(back)
        info["actions"] = actions
        self._st.wiz_run = info
        self._run_publish(force=True)
        self._set_choices([])

    def _sage26_output_dir(self) -> Path | None:
        vals = self._cfg_values("sage26")
        od = str(vals.get("OutputDir", {}).get("value", "")).strip()
        if not od:
            return None
        p = self._toolchain.native(od)
        if not p.is_absolute() and self._sage26_dir:
            p = self._sage26_dir / p
        return p
