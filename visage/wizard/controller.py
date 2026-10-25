from __future__ import annotations

import asyncio
import base64 as _b64
import os
import sys
from pathlib import Path

from visage import system
from visage.utils import terminal
from visage.wizard import toolchain as _toolchain
from visage.wizard.install import InstallMixin
from visage.wizard.screens import SetupRunMixin

_SAGE26_REPO = "https://github.com/MBradley1985/SAGE26.git"
_SAGESWARM_REPO = "https://github.com/MBradley1985/SAGEswarm.git"
# LightSAGE (upstream repo: sage-home/sage-lightcone) is a third-party
# package (not ours) — we only clone, build, and run it; we never modify
# anything inside the checkout.  "LightSAGE" is ViSAGE's display name for
# it; the clone URL below is the real, unrenameable upstream repo.
_LIGHTSAGE_REPO = "https://github.com/sage-home/sage-lightcone"

import html as _html_mod
import re as _re

# ANSI SGR codes for each wizard message kind — used when writing directly to
# the xterm.js terminal instead of the old HTML line list.
_KIND_ANSI: dict[str, str] = {
    "title": "\x1b[1;36m",  # bold cyan
    "ok": "\x1b[32m",  # green
    "warn": "\x1b[33m",  # yellow
    "err": "\x1b[1;31m",  # bold red
    "cmd": "\x1b[36m",  # cyan
    "out": "",  # white (default)
    "sep": "",  # white (default)
    "info": "",  # default
}

# ── legacy ANSI → HTML converter (kept for reference, no longer used) ─────────
_ANSI_CSI = _re.compile(r"\x1b\[([0-9;]*)([A-Za-z])")  # all CSI sequences
_ANSI_OTHER = _re.compile(r"\x1b[^[]")  # ESC + non-[

_ANSI_FG = {
    "30": "#4a4a4a",
    "31": "#ef4444",
    "32": "#22c55e",
    "33": "#f59e0b",
    "34": "#60a5fa",
    "35": "#a855f7",
    "36": "#06b6d4",
    "37": "#e2e8f0",
    "90": "#6b7280",
    "91": "#f87171",
    "92": "#4ade80",
    "93": "#fbbf24",
    "94": "#93c5fd",
    "95": "#c084fc",
    "96": "#67e8f9",
    "97": "#f9fafb",
}


def _ansi_to_html(text: str) -> str:
    """Convert ANSI SGR codes to HTML spans; escape all other HTML."""
    # Strip non-SGR control sequences (cursor movement, clear, etc.)
    text = _ANSI_OTHER.sub("", text)

    out: list[str] = []
    in_span = False
    pos = 0

    for m in _ANSI_CSI.finditer(text):
        # Emit plain text before this escape sequence (HTML-escaped)
        out.append(_html_mod.escape(text[pos : m.start()]))
        pos = m.end()

        cmd = m.group(2)
        if cmd != "m":
            continue  # not a colour code — skip

        codes = m.group(1).split(";") if m.group(1) else ["0"]
        if in_span:
            out.append("</span>")
            in_span = False

        bold = "1" in codes
        color = next((c for c in codes if c in _ANSI_FG), None)
        reset = "0" in codes or "" in codes

        if not reset and color:
            style = f"color:{_ANSI_FG[color]}"
            if bold:
                style += ";font-weight:700"
            out.append(f'<span style="{style}">')
            in_span = True

    out.append(_html_mod.escape(text[pos:]))
    if in_span:
        out.append("</span>")
    return "".join(out)


# The three tools on the Launch Mode home screen, in order: card text,
# background (visage/static/wizard/), icon and accent colours.
_MODE_META = {
    "sage26": {
        "title": "SAGE26",
        "desc": "Run the semi-analytic model on dark-matter merger trees",
        "bg": "/sage_static/wizard/sage26.jpg",
        "icon": "mdi-orbit",
        "accent": "#22d3ee",
        "accent2": "#a78bfa",
    },
    "sagelightcone": {
        "title": "LightSAGE",
        "desc": "Build lightcones and see galaxies as a telescope would",
        "bg": "/sage_static/wizard/lightsage.jpg",
        "icon": "mdi-telescope",
        "accent": "#60a5fa",
        "accent2": "#f59e0b",
    },
    "sageswarm": {
        "title": "SAGEswarm",
        "desc": "Calibrate SAGE26 against observations with a particle swarm",
        "bg": "/sage_static/wizard/sageswarm.jpg",
        "icon": "mdi-chart-bubble",
        "accent": "#2dd4bf",
        "accent2": "#f59e0b",
    },
}

# Each mode screen's buttons -> the flow step they start.
_MODE_ACTIONS = {
    "sage26": {
        "run": "run_sage26",
        "load": "load",
        "install": "compile_sage26",
        "update": "check_update",
        "clone": "clone_sage26",
    },
    "sagelightcone": {
        "run": "lc_configure",
        "load": "lc_load",
        "install": "lc_build",
        "update": "check_update",
        "clone": "lc_clone",
    },
    "sageswarm": {
        "run": "sw_configure",
        "install": "sw_install",
        "update": "check_update",
        "clone": "sw_clone",
    },
}

_UPDATE_VALUE = {
    "sage26": "update_sage26",
    "sagelightcone": "lc_update",
    "sageswarm": "sw_update",
}

_STEPS = [
    "Scan Environment",
    "Choose Action",
    "Setup SAGE26",
    "Configure Run",
    "Run SAGE26",
    "Launch Explore",
]

# SAGEswarm flow — same chip count (6) so the header renders identically; only
# the labels differ. Selected per-flow into the `wiz_steps` state var.
_STEPS_SAGESWARM = [
    "Scan",
    "Clone SAGEswarm",
    "Install deps",
    "Configure",
    "Run PSO",
    "View plots",
]

# LightSAGE flow — same chip count (6). Clone → build the C++ tools →
# edit a run script → run the two-stage pipeline → done.
_STEPS_SAGELIGHTCONE = [
    "Scan",
    "Clone",
    "Build",
    "Configure",
    "Run",
    "Done",
]

# SAGE26 is compiled from a ViSAGE-managed helper (kept in ~/.visage, like
# the LightSAGE one below) so the build can use every core and cope with
# machines that lack MPI or keep HDF5 somewhere the Makefile doesn't look.
_SAGE26_BUILD_SCRIPT = "build_sage26.sh"

_SAGE26_BUILD_SCRIPT_TEMPLATE = """\
#!/bin/bash
# ViSAGE-managed build for SAGE26: `make` on every core, falling back to a
# serial (non-MPI) build when there is no MPI compiler.
set -e

cd "{sage_dir}"

NJOBS="$(sysctl -n hw.ncpu 2>/dev/null || nproc 2>/dev/null || echo 4)"
MAKE_ARGS=""
# SAGE26's Makefile enables MPI by default, which needs mpicc.
if ! command -v mpicc >/dev/null 2>&1; then
    echo "ViSAGE: mpicc not found -- building serial SAGE26 (USE-MPI=)."
    MAKE_ARGS="USE-MPI="
fi
# Debian/Ubuntu (and so WSL) keep the HDF5 headers in a multiarch folder
# that the Makefile's `which h5ls` guess (/usr) misses.
if [ -z "$HDF5_DIR" ] && [ "$(uname)" = "Linux" ]; then
    for d in /usr/lib/*-linux-gnu/hdf5/serial; do
        if [ -f "$d/include/hdf5.h" ]; then
            export HDF5_DIR="$d"
            echo "ViSAGE: using HDF5 from $d"
            break
        fi
    done
fi

echo "==> make -j$NJOBS $MAKE_ARGS"
make -j"$NJOBS" $MAKE_ARGS
"""

# The SAGEswarm run is driven by editing its run_pso.sh script (all options —
# constraints, PSO params, bounds file, sim settings — are shell vars in there),
# mirroring how the SAGE26 flow edits the .par file.
_SW_RUN_SCRIPT = "run_pso.sh"

# Seed used only when a checkout ships no run_pso.sh (the user edits the paths).
_SW_RUN_SCRIPT_TEMPLATE = """\
#!/bin/bash

CONFIG_PATH="../SAGE26/input/millennium.par"
BASE_PATH="../SAGE26/sage"
OUTPUT_PATH="./millennium_pso"
PARTICLES=25
ITERATIONS=100
TEST="chi2"
CONSTRAINTS="SMF_z0"
BOXSIZE=62.5
SIM=1
VOL_FRAC=1.0
OMEGA0=0.25
H0=0.73
CSVOUTPUT="./millennium_pso/pso.csv"
SPACEFILE="./space.txt"

python3 ./main.py \\
  -c "$CONFIG_PATH" \\
  -b "$BASE_PATH" \\
  -o "$OUTPUT_PATH" \\
  -s "$PARTICLES" \\
  -m "$ITERATIONS" \\
  -t "$TEST" \\
  -x "$CONSTRAINTS" \\
  -csv "$CSVOUTPUT" \\
  --sim "$SIM" \\
  --boxsize "$BOXSIZE" \\
  --vol-frac "$VOL_FRAC" \\
  --Omega0 "$OMEGA0" \\
  --h0 "$H0" \\
  -S "$SPACEFILE"
"""

# The LightSAGE repo is third-party, so ViSAGE keeps its editable run
# script OUTSIDE the checkout (in ~/.visage). The script only *calls* the
# repo's wrapper scripts (scripts/sage2kdtree.sh, scripts/lightcone.sh) — it
# never writes into the repo. Both pipeline stages live in the one script.
_LC_RUN_SCRIPT = "run_lightcone.sh"

# ViSAGE builds ONLY the two lightcone C++ tools (sage2kdtree, cli_lightcone).
# The repo's own build_platform_aware.sh additionally clones and compiles SAGE
# (sage-model) to generate test data — we don't want that: ViSAGE already
# manages SAGE (SAGE26) and feeds its HDF5 output into the pipeline. So we run
# a leaner, tools-only cmake build from this ViSAGE-managed helper (kept in
# ~/.visage, never written into the repo).
#
# Fixes ViSAGE needs in the tools ship as patches (visage/wizard/patches/
# lightsage/*.patch). The build applies each one that still applies, builds,
# and always takes them back out, so the checkout stays as upstream has it
# and only the built tools carry the fixes. A patch upstream has already
# made (or that no longer fits) is skipped with a note.
_LC_BUILD_SCRIPT = "build_lightcone_tools.sh"
_LC_PATCH_DIR = Path(__file__).resolve().parent / "patches" / "lightsage"

_LC_BUILD_SCRIPT_TEMPLATE = """\
#!/bin/bash
# ViSAGE-managed build for the LightSAGE C++ tools ONLY.
# Builds: sage2kdtree, cli_lightcone  (NOT SAGE — ViSAGE uses SAGE26 output).
# Never modifies the LightSAGE repository (bin/ is gitignored build output).
set -e

LC_DIR="{lc_dir}"
PATCH_DIR="{patch_dir}"
cd "$LC_DIR"

# ViSAGE's fixes to the tools: in for the build, out again afterwards.
APPLIED=()
unpatch() {{
    for ((i=${{#APPLIED[@]}}-1; i>=0; i--)); do
        git apply -R "${{APPLIED[$i]}}" && echo "==> Removed ViSAGE patch: $(basename "${{APPLIED[$i]}}")"
    done
}}
trap unpatch EXIT
for P in "$PATCH_DIR"/*.patch; do
    [ -e "$P" ] || continue
    if git apply --check "$P" 2>/dev/null; then
        git apply "$P"
        APPLIED+=("$P")
        echo "==> Applied ViSAGE patch: $(basename "$P")"
    elif git apply -R --check "$P" 2>/dev/null; then
        echo "==> Already in LightSAGE: $(basename "$P")"
    else
        echo "==> WARNING: ViSAGE patch no longer fits LightSAGE, skipped: $(basename "$P")"
    fi
done

EXTRA=""
if [[ "$OSTYPE" == "darwin"* ]]; then
    # Pull in the repo's env (HDF5/Boost paths, venv) WITHOUT building SAGE.
    source setup_mac.sh >/dev/null 2>&1 || true
    HDF5_PREFIX="$(brew --prefix hdf5 2>/dev/null)"
    EXTRA="-DCMAKE_OSX_ARCHITECTURES=arm64 -DHDF5_PREFER_PARALLEL=OFF"
    [ -n "$HDF5_PREFIX" ] && EXTRA="$EXTRA -DHDF5_ROOT=$HDF5_PREFIX"

    # macOS SDK guard: Apple clang < 17 cannot parse the macOS 26 SDK's libc++
    # (<bit> uses __builtin_ctzg, absent before LLVM 19). If the active compiler
    # chokes on the default SDK, fall back to an installed 15.x SDK.
    if ! printf '#include <algorithm>\\n#include <vector>\\nint main(){{std::vector<int> v{{3,1,2}};std::sort(v.begin(),v.end());return v[0];}}' \\
         | "${{CXX:-clang++}}" -std=c++17 -x c++ -fsyntax-only - >/dev/null 2>&1; then
        for S in MacOSX15.sdk MacOSX15.4.sdk MacOSX15.0.sdk MacOSX14.sdk; do
            for BASE in "/Library/Developer/CommandLineTools/SDKs" \\
                        "$(xcode-select -p 2>/dev/null)/Platforms/MacOSX.platform/Developer/SDKs"; do
                CAND="$BASE/$S"
                if [ -d "$CAND" ]; then
                    EXTRA="$EXTRA -DCMAKE_OSX_SYSROOT=$CAND"
                    echo "ViSAGE: using compatible macOS SDK -> $CAND"
                    break 2
                fi
            done
        done
    fi
else
    # HPC/Linux: modules provide HDF5/Boost; no SDK override needed.
    source setup.sh >/dev/null 2>&1 || true
fi

NJOBS="$(sysctl -n hw.ncpu 2>/dev/null || nproc 2>/dev/null || echo 4)"
echo "==> Configuring (tools only, USE_MPI=OFF) ..."
cmake -B bin -DCMAKE_BUILD_TYPE=Release -DUSE_MPI=OFF $EXTRA .
echo "==> Building sage2kdtree + cli_lightcone ..."
make -C bin -j"$NJOBS" sage2kdtree cli_lightcone
echo "==> Done: $(ls bin/sage2kdtree bin/cli_lightcone 2>/dev/null)"
"""


def _survey_blocks() -> dict:
    """The run script's survey checkboxes and the bash that turns the
    ticked ones into the --bands list (visage.sed.filters.SURVEYS)."""
    from visage.sed.filters import SURVEYS

    flags = [
        "# Surveys to compute magnitudes for -- each ticks its whole filter",
        "# set; any FSPS filter can also be passed to visage.sed.photometry.",
    ]
    bands = []
    for key, label, filters, on in SURVEYS:
        var = f"SURVEY_{key}_ENABLED"
        flags.append(f"{var}={int(on)}".ljust(39) + f"# {label}")
        bands.append(
            f'  [ "${var}" = "1" ] && sed_bands="$sed_bands {" ".join(filters)}"'
        )
    return {
        "survey_flags": "\n".join(flags) + "\n",
        "survey_bands": "\n".join(bands) + "\n",
    }


_LC_RUN_SCRIPT_TEMPLATE = """\
#!/bin/bash
# ViSAGE-managed LightSAGE run script.
# Edit the paths and parameters below, then click 'Save & Run Lightcone'.
# This script only CALLS the LightSAGE wrapper scripts — it never
# modifies the LightSAGE repository itself.
set -e

# Location of the LightSAGE checkout (auto-filled by ViSAGE).
LIGHTCONE_DIR="{lightcone_dir}"

# -- Stage 1: sage2kdtree -- SAGE HDF5 output -> KD-tree indexed HDF5 --------
SAGE_OUTPUT_DIR="{sage_output_dir}"   # directory holding model_N.hdf5 files
PARAM_FILE="{param_file}"             # SAGE .par file (cosmology/sim settings)
ALIST_FILE="{alist_file}"             # expansion-factor (a_list) file
KDTREE_OUT="./millennium-kdtree.h5"   # KD-tree output file

# -- Stage 2: cli_lightcone -- KD-tree HDF5 -> flat lightcone HDF5 -----------
RAMIN=0                    # right ascension min (degrees)
RAMAX=10                   # right ascension max (degrees)
DECMIN=0                   # declination min (degrees)
DECMAX=10                  # declination max (degrees)
ZMIN=0                     # redshift min
ZMAX=1                     # redshift max
OUTDIR="{outdir}"          # ViSAGE's standard output folder (see docs)
OUTFILE="lightcone.h5"

# -- Stage 3: synthetic photometry (what observers would measure) -----------
# Forward-models AB magnitudes per galaxy from its star-formation history
# using FSPS. Requires: pip install "sage-viewer[sed]"
SED_ENABLED=1                          # 1 = compute synthetic photometry after the lightcone is built
SED_FRAME="both"                       # rest | obs | both
# Use each galaxy's own mass-weighted stellar metallicity
# (MetalsStellarMass/StellarMass); uncheck to force solar for everyone.
SED_METALLICITY_ENABLED=1
# Dust attenuation (dims and reddens galaxies, as observed).
SED_DUST_ENABLED=1
# charlot_fall: each galaxy's own dust, from its cold gas, metals and H2
#   (Dusty-SAGE physics), in birth clouds and a disk seen at its
#   inclination (Charlot & Fall 2000).  calzetti: one fixed screen for
#   every galaxy (Calzetti 2000), of V-band optical depth SED_DUST2.
SED_DUST_MODEL="charlot_fall"          # charlot_fall | calzetti
SED_DUST2=0.3                          # calzetti only: V-band optical depth
# Re-emit the light the dust absorbs in the infrared (Draine & Li 2007,
# energy balance) -- makes the mid/far-IR bands (WISE, Spitzer, Herschel)
# physical. Only has an effect when dust (above) is on.
SED_DUST_EMISSION_ENABLED=1
# Also write the disk's and the bulge's own magnitudes (disk_mag_*,
# bulge_mag_*); the totals are their sum.
SED_DISK_BULGE_ENABLED=1
# Nebular emission from star-forming regions: lines and continuum in the
# magnitudes, and each galaxy's H-alpha, H-beta, [OII], [OIII], [NII] and
# [SII] luminosities and fluxes, through its dust.
SED_LINES_ENABLED=1
{survey_flags}
echo "==> Stage 1/2: sage2kdtree"
"$LIGHTCONE_DIR/scripts/sage2kdtree.sh" \\
  -s "$SAGE_OUTPUT_DIR" \\
  -p "$PARAM_FILE" \\
  -a "$ALIST_FILE" \\
  -o "$KDTREE_OUT"

echo "==> Stage 2/2: cli_lightcone"
mkdir -p "$OUTDIR"
"$LIGHTCONE_DIR/scripts/lightcone.sh" \\
  -d "$KDTREE_OUT" \\
  --ramin "$RAMIN"   --ramax "$RAMAX" \\
  --decmin "$DECMIN" --decmax "$DECMAX" \\
  --zmin "$ZMIN"     --zmax "$ZMAX" \\
  --outdir "$OUTDIR" \\
  -o "$OUTFILE"

echo "==> Lightcone written to $OUTDIR/$OUTFILE"

if [ "$SED_ENABLED" = "1" ]; then
  echo "==> Stage 3: synthetic photometry (SED synthesis)"
  # Lowercase on purpose: internal/computed, never re-parsed as an editable
  # wizard parameter (only UPPERCASE VAR=value assignments are, so a user's
  # edit here can never desync the checkboxes above from what actually runs).
  sed_bands=""
{survey_bands}  if [ -z "$sed_bands" ]; then
    echo "No surveys checked — skipping SED synthesis."
  else
    bands_csv="$(echo "$sed_bands" | tr -s ' ' ',' | sed 's/^,//')"
    sed_extra=""
    [ "$SED_METALLICITY_ENABLED" != "1" ] && sed_extra="$sed_extra --no-metallicity"
    if [ "$SED_DUST_ENABLED" = "1" ]; then
      if [ "$SED_DUST_MODEL" = "calzetti" ]; then
        sed_extra="$sed_extra --dust --dust2 $SED_DUST2"
      else
        sed_extra="$sed_extra --dust-model charlot_fall"
      fi
    fi
    [ "$SED_DUST_ENABLED" = "1" ] && [ "$SED_DUST_EMISSION_ENABLED" = "1" ] && sed_extra="$sed_extra --dust-emission"
    [ "$SED_DISK_BULGE_ENABLED" = "1" ] && sed_extra="$sed_extra --disk-bulge"
    [ "$SED_LINES_ENABLED" = "1" ] && sed_extra="$sed_extra --lines"
    "{python_exe}" -m visage.sed.photometry \\
      --input "$OUTDIR/$OUTFILE" \\
      --bands "$bands_csv" \\
      --frame "$SED_FRAME" \\
      --alist "$ALIST_FILE" $sed_extra
  fi
fi
"""
# (The survey checkboxes are generated from visage.sed.filters.SURVEYS.)
_LC_RUN_SCRIPT_TEMPLATE = _LC_RUN_SCRIPT_TEMPLATE.replace(
    "{survey_flags}", _survey_blocks()["survey_flags"]
).replace("{survey_bands}", _survey_blocks()["survey_bands"])

_MILLENNIUM_PAR_TEMPLATE = """\
%------------------------------------------
%----- SAGE output file information -------
%------------------------------------------

FileNameGalaxies   model
%OutputDir         /<absolute>/<path>/SAGE26/output/millennium/
OutputDir   {output_dir}

FirstFile         0
LastFile          7

%------------------------------------------
%----- Snapshot output list ---------------
%------------------------------------------

NumOutputs        -1  % sets the desired number of galaxy outputs; use -1 for all outputs

% List your output snapshots after the arrow, highest to lowest (ignored when NumOutputs=-1).
-> 63 37 32 27 23 20 18 16

OutputFormat      sage_hdf5 % sets the desired output format. Either 'sage_binary' or 'sage_hdf5'.

%------------------------------------------
%----- Simulation information  ------------
%------------------------------------------

TreeName              trees_063   % assumes the trees are named TreeName.n where n is the file number
TreeType              lhalo_binary % 'genesis_lhalo_hdf5', 'lhalo_binary', 'consistentrees_ascii', 'consistentrees_hdf5', 'lhalo_ascii', 'lhalo_hdf5'
NumSimulationTreeFiles 8 % Number of files the trees are split over. This can be different to `FirstFile` -> `LastFile` range.

%SimulationDir      /<absolute>/<path>/SAGE26/input/millennium/trees/
SimulationDir   {sim_dir}
%FileWithSnapList   /<absolute>/<path>/SAGE26/input/millennium/trees/millennium.a_list
FileWithSnapList {snaplist}
LastSnapShotNr        63

Omega           0.25
OmegaLambda     0.75
BaryonFrac      0.17
Hubble_h        0.73
PartMass        0.086
BoxSize         62.5 % Size of the simulation box in Mpc/h.

%------------------------------------------
%----- SAGE recipe options ----------------
%------------------------------------------

SFprescription              1   %0: original Croton et al. 2006; 1: BR06 H2 Stars; 2: Somerville et al. 2025 SFR; 3: Somerville et al. 2025 SFR + H2; 4: KD12 H2 Stars; 5: KMT09; 6: K13; 7: GD14
AGNrecipeOn                 2   %0: switch off; 1: empirical model; 2: Bondi-Hoyle model; 3: cold cloud accretion model
SupernovaRecipeOn           1   %0: switch off; 1: original Croton et al. 2016
ReionizationOn              1   %0: switch off
DiskInstabilityOn           1   %0: switch off; 1: bulge and BH growth through instabilities w. instability starbursts

CGMrecipeOn                 1   %0: switch off
FIREmodeOn                  1   %0: switch off

ConcentrationOn             3   %0: off; 1: Ishiyama+21 lookup table; 2: Vmax/Vvir from simulation; 3: Vmax/Vvir + infall freeze for satellites
FeedbackFreeModeOn          1   %0: off; 1: Li+24 sigmoid; 2: BK25 (Ishiyama+21 conc); 3: BK25 (ConcentrationOn method); 4: BK25 + log-normal c scatter; 5: Li+24 sharp; 6: Li+24 sigmoid + H2 SF; 7: BK25 log-normal c scatter + H2 SF

SaveFullSFH                 1   %0: switch off
TrackICSAssembly            1   %0: switch off; 1: track ICS_disrupt and ICS_accrete

%------------------------------------------
%----- SAGE model parameters --------------
%------------------------------------------

SfrEfficiency               0.05    %efficiency of SF; unused for SFprescription=3,6
FFBMaxEfficiency            0.2     %0.2 fits observations best, 1.0 is theoretical maximum

FeedbackReheatingEpsilon    2.9     %mass of cold gas reheated due to SF (see Martin 1999) (SupernovaRecipeOn=1)
FeedbackEjectionEfficiency  0.3     %mixing efficiency of SN energy with hot gas to unbind and eject some (SupernovaRecipeOn=1)

ReIncorporationFactor       0.15    %fraction of ejected mass reincorporated per dynamical time to hot

RadioModeEfficiency         0.08    %AGN radio mode efficiency (AGNrecipeOn=2)
QuasarModeEfficiency        0.005   %AGN quasar mode wind heating efficiency (AGNrecipeOn>0)
BlackHoleGrowthRate         0.015   %fraction of cold gas added to the BH during mergers (AGNrecipeOn>0)

ThreshMajorMerger           0.3     %major merger when mass ratio greater than this
ThresholdSatDisruption      1.0     %Mvir-to-baryonic mass ratio threshold for satellite merger or disruption

Yield                       0.025   %fraction of SF mass produced as metals
RecycleFraction             0.43    %fraction of SF mass instantaneously recycled back to cold
FracZleaveDisk              0.0     %fraction of metals produced directly to hot component

Reionization_z0             8.0     %these parameter choices give the best fit to Genedin (2000)...
Reionization_zr             7.0     %using the analytic fit of Kravtsov et al. 2004 (ReionizationOn=1)

EnergySN                    1.0e51  %energy per supernova
EtaSN                       5.0e-3  %supernova efficiency

%------------------------------------------
%----- Other code-related information -----
%------------------------------------------

%% The following two parameters determine how forests are distributed over MPI tasks
%% The scheme determines the computing cost for processing each forest
%% uniform_in_forests -> every forest has the same cost, regardless of the size of the forest
%% linear_in_nhalos -> the cost scales linearly with the forest size
%% quadratic_in_nhalos -> the cost scales quadratically with forest size
%% exponent_in_nhalos -> the cost scales to some (integer) power of forest size, the exponent is given by the (integral) value of 'ExponentForestDistributionScheme'
%% generic_power_in_nhalos -> the cost is directly scaled by  pow(forest size, 'ExponentForestDistributionScheme')
ForestDistributionScheme                    generic_power_in_nhalos  % options are 'uniform_in_forests', 'linear_in_nhalos',
ExponentForestDistributionScheme            0.7 % only relevant for the last two schemes


UnitLength_in_cm          3.08568e+24 %WATCH OUT: Mpc/h
UnitMass_in_g             1.989e+43   %WATCH OUT: 10^10Msun
UnitVelocity_in_cm_per_s  100000      %WATCH OUT: km/s
"""

# ── Config → parameter-form parsing ──────────────────────────────────────
# The wizard shows editable configs (SAGE26 .par, run_pso.sh, run_lightcone.sh)
# as a list of labelled boxes rather than raw text.  We parse the file into an
# ordered [{key, label, value, hint}] list for the form, and write edited
# values back into the ORIGINAL text (preserving comments, layout, and any
# non-parameter lines) so the on-disk format is unchanged apart from values.

# Max parameters the form can show (enough for the SAGE26 .par, ~51 entries).
# Each slot is a dedicated top-level state var so trame syncs edits reliably.
_MAX_PARAMS = 64

_PAR_LINE = _re.compile(r"^(\s*)([A-Za-z]\w*)(\s+)([^%\n]*?)\s*(?:%\s*(.*))?$")
_PAR_APPLY = _re.compile(r"^(\s*)([A-Za-z]\w*)(\s+)([^%\n]*?)(\s*%.*)?$")
# Shell assignment token: VAR="..." | VAR='...' | VAR=bare.  Matched anywhere
# on a line so multi-assignment lines (VAR=0; VAR2=10) all parse.  References
# like "$VAR" and flags like -c/--opt have no `NAME=` so they're never matched.
_SH_ASSIGN = _re.compile(r"""([A-Z_][A-Z0-9_]*)=("[^"]*"|'[^']*'|[^\s;#]*)""")


def _sh_split_comment(line: str) -> tuple[str, str]:
    """Split a shell line into (code, comment-including-#).  Naive '#' handling
    is fine for our run scripts, which never use '#' inside a value."""
    i = line.find("#")
    return (line, "") if i < 0 else (line[:i], line[i:])


def _sh_unquote(raw: str) -> tuple[str, str]:
    if len(raw) >= 2 and raw[0] in "\"'" and raw[-1] == raw[0]:
        return raw[1:-1], raw[0]
    return raw, ""


def _parse_params(text: str, kind: str) -> list[dict]:
    """Parse a .par ('par') or shell run-script ('sh') into an ordered list of
    {key, label, value, hint} — one entry per KEY VALUE / VAR=value option."""
    params: list[dict] = []
    seen: set[str] = set()
    for line in text.splitlines():
        if kind == "par":
            if not line.strip() or line.lstrip().startswith("%"):
                continue
            m = _PAR_LINE.match(line)
            if not m:
                continue
            key, val = m.group(2), m.group(4).strip()
            if not val or key in seen:
                continue
            seen.add(key)
            params.append(
                {
                    "key": key,
                    "label": key,
                    "value": val,
                    "hint": (m.group(5) or "").strip(),
                }
            )
        else:  # shell — scan every VAR=value assignment (any per line)
            code, comment = _sh_split_comment(line)
            hint = comment.lstrip("# ").strip()
            for m in _SH_ASSIGN.finditer(code):
                key = m.group(1)
                if key in seen:
                    continue
                seen.add(key)
                val, _q = _sh_unquote(m.group(2))
                params.append(
                    {"key": key, "label": key, "value": val, "hint": hint}
                )
    return params


def _apply_params(text: str, params: list[dict], kind: str) -> str:
    """Write edited param values back into the original text, preserving
    indentation, key spacing, quoting and trailing comments."""
    vals = {p["key"]: str(p["value"]) for p in params}
    out: list[str] = []
    for line in text.splitlines():
        if kind == "par":
            if line.strip() and not line.lstrip().startswith("%"):
                m = _PAR_APPLY.match(line)
                if m and m.group(2) in vals:
                    out.append(
                        f"{m.group(1)}{m.group(2)}{m.group(3)}"
                        f"{vals[m.group(2)]}{m.group(5) or ''}"
                    )
                    continue
            out.append(line)
        else:
            code, comment = _sh_split_comment(line)

            def _repl(m: _re.Match) -> str:
                key = m.group(1)
                if key not in vals:
                    return m.group(0)
                nv = vals[key]
                _old, q = _sh_unquote(m.group(2))
                if not q and any(ch.isspace() for ch in nv):
                    q = '"'  # quote a value that gained spaces
                return f"{key}={q}{nv}{q}"

            out.append(_SH_ASSIGN.sub(_repl, code) + comment)
    tail = "\n" if text.endswith("\n") else ""
    return "\n".join(out) + tail


_KIND_COLORS = {
    "title": "#06b6d4",
    "ok": "#22c55e",
    "warn": "#f59e0b",
    "err": "#ef4444",
    "cmd": "#06b6d4",
    "out": "#9ca3af",
    "sep": "#374151",
    "info": "#e2e8f0",
}


def _latest_per_constraint(plots: list[dict]) -> list[dict]:
    """SAGEswarm's newest figure of each constraint (its file names start
    with the constraint, e.g. SMF_z0_iter3_all.png), for the run page."""
    best: dict[str, dict] = {}
    for it in plots:
        stem = Path(it["name"]).stem
        group = stem.split("_iter")[0].split("_all")[0] or stem
        if group not in best or it.get("mtime", 0) >= best[group].get(
            "mtime", 0
        ):
            best[group] = {**it, "group": group}
    return [best[g] for g in sorted(best)]


class WizardController(InstallMixin, SetupRunMixin):
    def __init__(
        self,
        server,
        port: int,
        *,
        scene=None,
        on_model_loaded=None,
        auto_start: bool = True,
        standalone: bool = False,
    ) -> None:
        self._sv = server
        self._st = server.state
        self._port = port
        self._standalone = standalone
        self._scene = scene  # None in Launch Mode
        self._on_model_loaded = (
            on_model_loaded  # called on completion in Explore Mode
        )

        self._sage26_dir: Path | None = None
        self._par_path: Path | None = None
        self._models: list[dict] = []
        self._wiz_seq: int = 0
        self._wiz_buf: bytearray = (
            bytearray()
        )  # replay buffer for late-mounting xterm
        self._back: str = (
            "back_sage26_menu"  # Back target for par/compile steps
        )

        # SAGEswarm (PSO calibration) flow state
        self._flow: str = "sage26"  # "sage26" | "sageswarm" | "sagelightcone"
        self._sw_dir: Path | None = None
        self._sw_sage_bin: Path | None = None
        # LightSAGE flow state
        self._lc_dir: Path | None = None
        self._plot_task = None  # asyncio task watching for PSO plots
        self._plot_watch_stop = True
        self._plot_seen: dict[str, int] = {}  # plot name → last-seen mtime
        self._run_proc = None  # currently-running _run_cmd TerminalProcess
        self._inline = None  # an Install / Clone running on its button
        self._job_results: dict = {}  # mode -> (act, ok, text), last run
        # Where the SAGE tools run (native, or WSL on Windows) — detected on
        # the first scan; Rescan re-probes so a fresh WSL install is seen.
        self._tc: _toolchain.Toolchain | None = None
        self._tc_refresh = False
        self._missing_tools: list[str] = []

        self._st.wiz_step = 0
        self._st.wiz_steps = list(_STEPS)  # header chip labels (per-flow)
        # Which screen fills the main box: the home cards, a tool's mode
        # screen, or the terminal while an action runs.
        self._st.wiz_view = "home"  # "home" | "mode" | "term"
        self._st.wiz_mode = ""
        self._st.wiz_home_cards = []
        self._st.wiz_home_load = {}
        self._st.wiz_mode_info = {}
        self._st.wiz_tools_note = ""
        self._st.wiz_tools_missing = False
        self._st.wiz_pick = {}  # model / lightcone picker screen
        # Setup (essentials + All settings) and run screens (screens.py).
        self._st.wiz_setup = {}
        self._st.wiz_setup_name = ""
        self._st.wiz_sections = []
        self._st.wiz_section = ""
        self._st.wiz_param_search = ""
        self._st.wiz_run = {}
        self._st.wiz_run_plots = []
        self._setup_mode = "sage26"
        self._run = None
        self._last_rc = None
        self._st.wiz_loading = ""  # name of the model being opened
        self._status: dict = {}
        self._st.wiz_lines = []  # kept for compat; no longer populated
        self._st.wiz_choices = []
        self._st.wiz_busy = True
        self._st.wiz_par_show = False
        self._st.wiz_par_text = ""
        self._st.wiz_filename_show = False
        self._st.wiz_filename = "millennium"
        self._st.wiz_kind_colors = _KIND_COLORS
        self._st.wiz_pty_data = ""  # base64 PTY chunk → xterm.js
        self._st.wiz_pty_seq = 0  # monotonically increasing
        self._st.wiz_pty_buf = ""  # base64 full replay buffer
        self._st.wiz_clone_dir_show = False
        self._st.wiz_clone_dir = str(Path.home())
        # SAGEswarm config (run_pso.sh editor) + live plot gallery
        self._st.wiz_sw_config_show = False
        self._st.wiz_sw_script_text = ""  # editable run_pso.sh contents
        self._st.wiz_run_active = False  # a _run_cmd subprocess is live
        self._st.pso_plots = []  # [{name, data_url, mtime}]
        self._st.pso_gallery_show = False
        # LightSAGE config (run_lightcone.sh editor, lives in ~/.visage)
        self._st.wiz_lc_config_show = False
        self._st.wiz_lc_script_text = ""  # editable run_lightcone.sh contents
        # Parameter form (labelled boxes) shown in place of the raw config
        # text.  Each option binds to its OWN top-level scalar state var
        # (wiz_pv_<i>) — trame reliably syncs those back, unlike nested edits
        # to a single list-of-dicts var.
        self._param_keys: list[str] = []  # ordered keys, index-aligned to pool
        self._st.wiz_params_kind = "par"  # "par" | "sh"
        self._st.wiz_params_target = ""  # "par" | "sw" | "lc"
        self._st.wiz_param_count = 0
        self._init_param_pool()

        server.controller.set("wiz_choose")(self._on_choice)
        server.controller.set("wiz_close")(self._on_close)
        server.controller.set("wiz_rescan")(self._on_rescan)
        server.controller.set("wiz_cancel_run")(self._on_cancel_run)
        # The terminal's size in the browser (visage.js), so commands run in
        # a terminal as wide as the one showing them.
        self._term_size = (24, 220)
        self._st.wiz_term_size = ""
        change = getattr(server.state, "change", None)
        if callable(change):
            change("wiz_term_size")(self._on_term_size)

        if auto_start:
            asyncio.ensure_future(self._step_scan())

    def reset_and_start(self, flow: str | None = None) -> None:
        """Clear terminal and restart — used when (re-)opening the wizard.

        ``flow`` selects the tool (``"sage26"``, ``"sagelightcone"`` or
        ``"sageswarm"``) whose screen opens; none opens the home screen.
        """
        self._flow = flow if flow in _MODE_META else "sage26"
        self._sage26_dir = None
        self._par_path = None
        self._models = []
        self._sw_dir = None
        self._sw_sage_bin = None
        self._lc_dir = None
        self._stop_plot_watch()
        self._wiz_buf = bytearray()
        self._back = "back_sage26_menu"
        self._st.wiz_step = 0
        if self._flow == "sageswarm":
            self._st.wiz_steps = list(_STEPS_SAGESWARM)
        elif self._flow == "sagelightcone":
            self._st.wiz_steps = list(_STEPS_SAGELIGHTCONE)
        else:
            self._st.wiz_steps = list(_STEPS)
        self._st.wiz_lines = []
        self._st.wiz_choices = []
        self._st.wiz_busy = True
        self._st.wiz_par_show = False
        self._st.wiz_par_text = ""
        self._st.wiz_filename_show = False
        self._st.wiz_filename = "millennium"
        self._st.wiz_pty_buf = ""
        self._st.wiz_clone_dir_show = False
        self._st.wiz_clone_dir = str(Path.home())
        self._st.wiz_sw_config_show = False
        self._st.wiz_sw_script_text = ""
        self._st.wiz_lc_config_show = False
        self._st.wiz_lc_script_text = ""
        self._param_keys = []
        self._st.wiz_params_target = ""
        self._init_param_pool()
        self._st.pso_plots = []
        self._st.wiz_run_plots = []
        self._st.pso_gallery_show = False
        # Push a clear sequence as the first "chunk" so a late-mounting xterm
        # clears itself before replaying buffered output.
        self._push_bytes(b"\x1b[2J\x1b[H")
        self._st.flush()
        if flow in _MODE_META:
            asyncio.ensure_future(self._enter(flow))
        else:
            asyncio.ensure_future(self._go_home())

    def _on_close(self, **_) -> None:
        self._stop_plot_watch()
        self._st.pso_gallery_show = False
        if self._standalone:
            asyncio.ensure_future(self._sv.stop())
        else:
            self._st.wiz_active = False
            self._st.flush()

    def _on_rescan(self, **_) -> None:
        self._tc_refresh = True
        view, mode = self._st.wiz_view, self._st.wiz_mode
        self.reset_and_start(flow=mode if view != "home" else None)

    def _on_term_size(self, wiz_term_size="", **_) -> None:
        try:
            cols, rows = (int(v) for v in str(wiz_term_size).split(","))
        except ValueError:
            return
        if cols < 20 or rows < 5:
            return
        self._term_size = (rows, cols)
        if self._run_proc is not None:
            try:
                self._run_proc.resize(rows, cols)
            except Exception:
                pass

    def _on_cancel_run(self, **_) -> None:
        """Interrupt the running command — equivalent to pressing Ctrl+C.

        The interrupt reaches the whole job (the command runs in its own
        session / console), so the PSO driver and any SAGE instances it
        spawned all receive it.
        """
        proc = self._run_proc
        if proc is None or proc.poll() is not None:
            return
        try:
            proc.interrupt()
            self._emit("^C  — interrupt sent to the running process", "warn")
        except (ProcessLookupError, OSError) as exc:
            self._emit(f"Could not interrupt process: {exc}", "err")

    # ── helpers ──────────────────────────────────────────────────────────────

    _WIZ_BUF_CAP = 512 * 1024  # 512 KB replay buffer cap

    def _push_bytes(self, data: bytes) -> None:
        """Push raw bytes to the wizard xterm.js terminal.

        Maintains a rolling replay buffer (wiz_pty_buf) so a late-mounting
        xterm can reconstruct the full session history on first paint.
        """
        self._wiz_buf.extend(data)
        if len(self._wiz_buf) > self._WIZ_BUF_CAP:
            # Keep the most recent half so the display stays coherent.
            self._wiz_buf = self._wiz_buf[len(self._wiz_buf) // 2 :]
        self._wiz_seq = (self._wiz_seq + 1) % 10**9
        self._st.wiz_pty_data = _b64.b64encode(data).decode()
        self._st.wiz_pty_seq = self._wiz_seq
        self._st.wiz_pty_buf = _b64.b64encode(bytes(self._wiz_buf)).decode()
        self._st.flush()

    def _emit(self, text: str, kind: str = "info") -> None:
        code = _KIND_ANSI.get(kind, "")
        line = (code + text + ("\x1b[0m" if code else "") + "\r\n").encode()
        self._push_bytes(line)

    def _set_choices(self, choices: list[dict]) -> None:
        self._st.wiz_choices = choices
        self._st.wiz_busy = False
        self._st.flush()

    def _busy(self) -> None:
        self._st.wiz_choices = []
        self._st.wiz_busy = True
        self._st.wiz_par_show = False
        self._st.wiz_filename_show = False
        self._st.wiz_clone_dir_show = False
        self._st.wiz_sw_config_show = False
        self._st.wiz_lc_config_show = False
        self._st.flush()

    @staticmethod
    def _pretty_param_label(key: str) -> str:
        """Shorter checkbox label for a ``BAND_<FILTER>_ENABLED`` param — the
        raw key overflows the label column's fixed width once params are
        half-width (2-column checkbox layout). Shows the literal FSPS filter
        name (e.g. "sdss_g"), which also matches what --bands expects.
        Every other key (including plain ``SED_ENABLED``) is left as-is."""
        if key.startswith("BAND_") and key.endswith("_ENABLED"):
            return key[len("BAND_") : -len("_ENABLED")].lower()
        if key.startswith("SURVEY_") and key.endswith("_ENABLED"):
            from visage.sed.filters import SURVEYS

            k = key[len("SURVEY_") : -len("_ENABLED")]
            return next((lab for sk, lab, _, _ in SURVEYS if sk == k), k)
        return key

    def _init_param_pool(self) -> None:
        """Clear all parameter-form slots (label/value/hint per index)."""
        for i in range(_MAX_PARAMS):
            self._st[f"wiz_pl_{i}"] = ""
            self._st[f"wiz_pv_{i}"] = ""
            self._st[f"wiz_ph_{i}"] = ""
            self._st[f"wiz_pcb_{i}"] = False
            self._st[f"wiz_pg_{i}"] = ""
        self._st.wiz_param_count = 0

    def _show_params(self, text: str, kind: str, target: str) -> None:
        """Populate the parameter form (labelled boxes) from a config's text.
        Each option fills its own wiz_pl/pv/ph_<i> slot. Keys named
        ``*_ENABLED`` render as a checkbox (true_value "1" / false_value "0")
        instead of a text box — see ui.py."""
        params = _parse_params(text, kind)
        if len(params) > _MAX_PARAMS:
            self._emit(
                f"Note: showing the first {_MAX_PARAMS} of {len(params)} "
                "parameters; edit the rest by hand if needed.",
                "warn",
            )
            params = params[:_MAX_PARAMS]
        self._param_keys = [p["key"] for p in params]
        self._st.wiz_params_kind = kind
        self._st.wiz_params_target = target
        for i in range(_MAX_PARAMS):
            if i < len(params):
                self._st[f"wiz_pl_{i}"] = self._pretty_param_label(
                    params[i]["label"]
                )
                self._st[f"wiz_pv_{i}"] = params[i]["value"]
                self._st[f"wiz_ph_{i}"] = params[i]["hint"]
                self._st[f"wiz_pcb_{i}"] = params[i]["key"].endswith(
                    "_ENABLED"
                )
            else:
                self._st[f"wiz_pl_{i}"] = ""
                self._st[f"wiz_pv_{i}"] = ""
                self._st[f"wiz_ph_{i}"] = ""
                self._st[f"wiz_pcb_{i}"] = False
        self._st.wiz_param_count = len(params)
        self._st.flush()

    def _sync_params_to_text(self) -> None:
        """Write the form's edited values back into the config's raw text
        (called just before saving to disk).  Reads each slot's live value."""
        keys = self._param_keys
        if not keys:
            return
        params = [
            {"key": k, "value": self._st[f"wiz_pv_{i}"]}
            for i, k in enumerate(keys)
        ]
        kind = self._st.wiz_params_kind
        target = self._st.wiz_params_target
        if target == "par":
            self._st.wiz_par_text = _apply_params(
                str(self._st.wiz_par_text or ""), params, kind
            )
        elif target == "sw":
            self._st.wiz_sw_script_text = _apply_params(
                str(self._st.wiz_sw_script_text or ""), params, kind
            )
        elif target == "lc":
            self._st.wiz_lc_script_text = _apply_params(
                str(self._st.wiz_lc_script_text or ""), params, kind
            )

    # ------------------------------------------------------------------
    # Git helpers — shared by every repo flow (SAGE26 / SAGEswarm /
    # LightSAGE), so all three report and update the same way.
    # ------------------------------------------------------------------

    async def _git_capture(
        self, args: list[str], cwd: Path
    ) -> tuple[int, str]:
        """Run a git command quietly and return (returncode, stdout)."""
        tc = self._toolchain
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, lambda: tc.capture(["git", *args], cwd)
        )

    async def _git_status(self, repo: Path | None) -> dict:
        """Where a checkout stands against its remote.

        Returns {"repo": bool, "branch": str, "short": str, "behind": int,
        "ahead": int, "offline": bool}.  `repo` False means the directory
        isn't a git checkout (a tarball copy, say) — nothing to update.
        """
        info = {
            "repo": False,
            "branch": "",
            "short": "",
            "behind": 0,
            "ahead": 0,
            "offline": False,
            "upstream": False,
        }
        if repo is None or not (Path(repo) / ".git").exists():
            return info
        repo = Path(repo)
        info["repo"] = True
        _, info["branch"] = await self._git_capture(
            ["rev-parse", "--abbrev-ref", "HEAD"], repo
        )
        _, info["short"] = await self._git_capture(
            ["rev-parse", "--short", "HEAD"], repo
        )
        rc, _ = await self._git_capture(["fetch", "--quiet"], repo)
        if rc != 0:
            info["offline"] = True
            return info
        rc, counts = await self._git_capture(
            ["rev-list", "--left-right", "--count", "HEAD...@{u}"], repo
        )
        if rc != 0 or not counts:
            # No upstream configured for this branch.
            return info
        try:
            ahead, behind = counts.split()
            info["ahead"], info["behind"] = int(ahead), int(behind)
            info["upstream"] = True
        except ValueError:
            pass
        return info

    async def _report_git_status(self, name: str, repo: Path | None) -> dict:
        """Emit a one-line update report and return the status."""
        st = await self._git_status(repo)
        if not st["repo"]:
            if repo is not None:
                self._emit(f"  {name} updates   : not a git checkout", "warn")
            return st
        where = f"{st['branch']} @ {st['short']}" if st["short"] else "HEAD"
        if st["offline"]:
            self._emit(
                f"  {name} updates   : {where} — could not reach remote",
                "warn",
            )
        elif st["behind"]:
            self._emit(
                f"  {name} updates   : {st['behind']} behind "
                f"({where}) — update available",
                "warn",
            )
        elif not st["upstream"]:
            self._emit(
                f"  {name} updates   : {where} — no upstream branch to "
                f"compare against",
                "warn",
            )
        elif st["ahead"]:
            self._emit(
                f"  {name} updates   : up to date, {st['ahead']} local "
                f"commit(s) ahead ({where})",
                "ok",
            )
        else:
            self._emit(f"  {name} updates   : up to date ({where})", "ok")
        return st

    async def _git_update(self, name: str, repo: Path | None) -> None:
        """Fast-forward a checkout to its remote, submodules included."""
        if repo is None or not (Path(repo) / ".git").exists():
            self._emit(
                f"{name} is not a git checkout — nothing to pull.", "err"
            )
            return
        self._emit(f"Updating {name} at {repo} ...", "info")
        rc = await self._run_cmd(
            ["git", "pull", "--ff-only", "--recurse-submodules"], cwd=repo
        )
        if rc != 0:
            self._emit(
                "Update failed — the checkout has local commits or changes "
                "that block a fast-forward. Commit, stash or re-clone.",
                "err",
            )
            return
        self._emit(f"{name} updated.", "ok")

    @staticmethod
    def _move_aside(target: Path) -> Path:
        """Rename an existing checkout out of the way, and say where to.

        Re-cloning must never delete someone's edited par files or output,
        so the old tree is kept next to the new one with a timestamp.
        """
        import time

        stamp = time.strftime("%Y%m%d-%H%M%S")
        backup = target.with_name(f"{target.name}.backup-{stamp}")
        i = 1
        while backup.exists():
            backup = target.with_name(f"{target.name}.backup-{stamp}-{i}")
            i += 1
        target.rename(backup)
        return backup

    async def _run_cmd(
        self,
        cmd: list,
        cwd: Path | None = None,
        *,
        env: dict | None = None,
        as_root: bool = False,
    ) -> int:
        """Run a command in a terminal so ANSI colors and \\r progress bars
        work, streaming its output into the wizard terminal.

        Path items in ``cmd`` (and ``cwd``) are translated for the
        toolchain, so on Windows the same call runs inside WSL.
        """
        tc = self._toolchain
        self._push_bytes(
            ("\x1b[36m$ " + tc.display(cmd) + "\x1b[0m\r\n").encode()
        )
        try:
            argv, run_cwd, extra = tc.wrap(cmd, cwd, env=env, as_root=as_root)
        except _toolchain.ToolchainUnavailable as exc:
            self._emit(str(exc), "err")
            return 1
        try:
            proc = terminal.spawn(
                argv,
                cwd=run_cwd,
                env={**os.environ, **extra} if extra else None,
                rows=self._term_size[0],
                cols=self._term_size[1],
            )
        except Exception as exc:
            self._push_bytes(f"\x1b[1;31mError: {exc}\x1b[0m\r\n".encode())
            return 1

        # Expose the process so the Cancel button (Ctrl+C) can signal it.
        self._run_proc = proc
        self._st.wiz_run_active = True
        self._st.flush()
        loop = asyncio.get_running_loop()
        try:
            while True:
                data = await loop.run_in_executor(None, proc.read, 1.0)
                if data is None:
                    if proc.poll() is not None:
                        break
                    continue
                if not data:
                    break
                self._push_bytes(data)
                self._run_output(data)
                self._inline_output(data)
            self._last_rc = await loop.run_in_executor(None, proc.wait) or 0
            return self._last_rc
        except Exception as exc:
            self._push_bytes(f"\x1b[1;31mError: {exc}\x1b[0m\r\n".encode())
            self._last_rc = 1
            return 1
        finally:
            self._run_proc = None
            self._st.wiz_run_active = False
            self._st.flush()
            proc.close()

    # ── platform helpers ─────────────────────────────────────────────────────

    @property
    def _toolchain(self) -> _toolchain.Toolchain:
        if self._tc is None:
            self._tc = _toolchain.detect()
        return self._tc

    def _tc_path(self, p) -> str:
        """A path as the SAGE tools see it (/mnt/c/... under WSL)."""
        return self._toolchain.path(p)

    async def _detect_toolchain(self) -> None:
        """Find where the SAGE tools run (natively, or in WSL on Windows)
        and, under WSL, which Linux build tools are missing."""
        loop = asyncio.get_running_loop()
        refresh, self._tc_refresh = self._tc_refresh, False
        self._tc = await loop.run_in_executor(None, _toolchain.detect, refresh)
        self._missing_tools = []
        if self._tc.kind == "wsl":
            self._missing_tools = await loop.run_in_executor(
                None, self._tc.missing_tools
            )

    async def _step_install_linux_tools(self) -> None:
        """apt-get the compilers and libraries all three flows need, inside
        WSL as root (no password prompt), then restart the current flow."""
        self._emit(
            "Installing the Linux build tools inside WSL (apt, as root) ...",
            "info",
        )
        self._emit("  " + " ".join(_toolchain.LINUX_PACKAGES), "out")
        self._emit(
            "This downloads a few hundred MB; allow a few minutes.", "info"
        )
        rc = await self._run_cmd(
            self._toolchain.install_command(), as_root=True
        )
        if rc != 0:
            self._emit("Install failed — see the output above.", "err")
        else:
            self._emit("Linux build tools installed.", "ok")
        self._emit("", "info")
        self._set_choices(
            [
                {
                    "label": "Back to home",
                    "value": "home",
                    "icon": "mdi-arrow-left",
                    "disabled": False,
                }
            ]
        )

    @staticmethod
    def _read_text(path: Path) -> str:
        return Path(path).read_text(encoding="utf-8", errors="replace")

    @staticmethod
    def _write_unix_text(path: Path, text: str) -> None:
        """Write a file a Unix tool will read: UTF-8 with LF line endings.
        Plain write_text() on Windows writes CRLF, and bash then fails on
        every line with "$'\\r': command not found"."""
        Path(path).write_text(text, encoding="utf-8", newline="\n")

    def _warn_crlf(self, paths: list[Path]) -> None:
        """Warn when a checkout's scripts have Windows line endings — a
        clone made with Git for Windows (core.autocrlf) — since bash in WSL
        can't run them.  The wizard's own clones run inside WSL and never
        have this problem."""
        if self._toolchain.kind != "wsl":
            return
        bad = []
        for p in paths:
            try:
                if b"\r\n" in Path(p).read_bytes():
                    bad.append(Path(p).name)
            except OSError:
                pass
        if bad:
            self._emit(
                f"Warning: {', '.join(bad)} has Windows (CRLF) line endings, "
                "so bash in WSL will fail on it. The checkout was probably "
                "cloned with Git for Windows; re-clone it from this wizard "
                "(which clones inside WSL).",
                "warn",
            )

    # ── discovery ────────────────────────────────────────────────────────────

    def _find_sage26(self) -> Path | None:
        search_roots = [Path.cwd().parent, Path.cwd(), Path.home()]
        names = ["SAGE26", "sage26", "sage-model", "SAGE", "sage"]
        for root in search_roots:
            for name in names:
                candidate = root / name
                if candidate.is_dir() and (candidate / "src").is_dir():
                    return candidate
        return None

    def _sage26_compiled(self, sage26: Path) -> tuple[bool, int]:
        o_files = list(sage26.glob("src/*.o"))
        binary = sage26 / "bin" / "sage"
        return (len(o_files) > 0 or binary.is_file()), len(o_files)

    def _find_models(self, verbose: bool = False) -> list[dict]:
        from visage.utils.discover import find_models

        results: list[dict] = []
        checked: set[Path] = set()

        # Candidate (output_dir, par_dir) pairs to scan
        pairs: list[tuple[Path, Path]] = []

        # If SAGE26 is known, its output/ + input/ is the primary pair
        if self._sage26_dir:
            sage_out = self._sage26_dir / "output"
            sage_par = self._sage26_dir / "input"
            if sage_out.is_dir():
                pairs.append((sage_out, sage_par))

        # Also scan common names relative to cwd and parent
        roots = [Path.cwd(), Path.cwd().parent]
        if self._sage26_dir:
            roots.append(self._sage26_dir.parent)
        for root in roots:
            for out_name in ("sage_outputs", "output", "outputs"):
                out_d = root / out_name
                if out_d in checked or not out_d.is_dir():
                    continue
                checked.add(out_d)
                for par_name in ("input", "input/millennium", "."):
                    par_d = root / par_name
                    if par_d.is_dir():
                        pairs.append((out_d, par_d))

        for out_d, par_d in pairs:
            if verbose:
                self._emit(f"  scanning {out_d}", "out")
                self._emit(f"  par dir  {par_d}", "out")
            for m in find_models(out_d, par_dir=par_d):
                if not any(r["par"] == m["par"] for r in results):
                    results.append(m)
        return results

    def _find_par_files(self) -> list[Path]:
        pars: list[Path] = []
        if self._sage26_dir:
            inp = self._sage26_dir / "input"
            if inp.is_dir():
                pars.extend(sorted(inp.glob("*.par")))
        inp_local = Path.cwd() / "input"
        if inp_local.is_dir():
            for p in sorted(inp_local.glob("*.par")):
                if p not in pars:
                    pars.append(p)
        return pars

    # ── state machine ────────────────────────────────────────────────────────

    async def _step_scan(self) -> None:
        await self._go_home()

    async def _step_main_choice(self) -> None:
        await self._go_home()

    # ── home and mode screens ────────────────────────────────────────────

    async def _refresh_status(self) -> None:
        """Quietly find each tool's checkout and what's built (no output)."""
        await self._detect_toolchain()
        self._sage26_dir = self._find_sage26()
        self._models = self._find_models()
        self._sw_dir = self._find_sageswarm()
        self._sw_sage_bin = self._locate_sage_bin()
        self._lc_dir = self._find_sagelightcone()
        compiled = (
            self._sage26_compiled(self._sage26_dir)[0]
            if self._sage26_dir
            else False
        )
        built = self._lc_built(self._lc_dir)[0] if self._lc_dir else False
        self._status = {
            "sage26": {
                "dir": self._sage26_dir,
                "ready": compiled,
                "n": len(self._models),
            },
            "sagelightcone": {
                "dir": self._lc_dir,
                "ready": built,
                "n": len(self._discover_lightcones()),
            },
            "sageswarm": {
                "dir": self._sw_dir,
                "ready": self._sw_sage_bin is not None,
                "n": 0,
            },
        }
        note = ""
        if self._tc.kind == "missing":
            note = (
                "WSL not found: install it to build and run the SAGE tools "
                "(existing models and lightcones still open)."
            )
        elif self._missing_tools:
            note = "Missing Linux build tools: " + ", ".join(
                self._missing_tools
            )
        self._st.wiz_tools_note = note
        self._st.wiz_tools_missing = bool(self._missing_tools)

    def _badge(self, mode: str) -> tuple[str, bool]:
        st = self._status[mode]
        if not st["dir"]:
            return "Not installed", False
        if mode == "sage26":
            return (
                ("Installed", True) if st["ready"] else ("Not compiled", False)
            )
        if mode == "sagelightcone":
            return ("Installed", True) if st["ready"] else ("Not built", False)
        return "Installed", True

    def _show_home(self) -> None:
        self._st.wiz_view = "home"
        self._st.wiz_mode = ""
        self._st.wiz_step = 0
        self._st.wiz_steps = list(_STEPS)
        cards = []
        for mode, meta in _MODE_META.items():
            badge, ok = self._badge(mode)
            cards.append(
                {**meta, "value": f"mode:{mode}", "badge": badge, "ok": ok}
            )
        self._st.wiz_home_cards = cards
        n = len(self._models) + self._status.get("sagelightcone", {}).get(
            "n", 0
        )
        self._st.wiz_home_load = {
            "label": "Load a previous model",
            "sub": f"{n} found" if n else "none found yet",
            "disabled": n == 0,
        }
        self._set_choices([])

    def _show_mode(self, mode: str) -> None:
        meta, st = _MODE_META[mode], self._status[mode]
        found = st["dir"] is not None
        chips = []
        badge, ok = self._badge(mode)
        chips.append({"text": badge, "ok": ok})
        if mode == "sage26":
            chips.append({"text": f"{st['n']} models", "ok": st["n"] > 0})
        elif mode == "sagelightcone":
            chips.append({"text": f"{st['n']} lightcones", "ok": st["n"] > 0})
        else:
            chips.append(
                {
                    "text": (
                        "SAGE binary found"
                        if st["ready"]
                        else "No SAGE binary"
                    ),
                    "ok": st["ready"],
                }
            )
        subs = {
            "sage26": {
                "run": "Pick or create a parameter file, then run",
                "load": "Open a model you have already run",
                "install": "Download the Millennium trees and compile",
            },
            "sagelightcone": {
                "run": "Configure and build a lightcone",
                "load": "Open an existing lightcone",
                "install": "Libraries, photometry (FSPS) and the two tools",
            },
            "sageswarm": {
                "run": "Configure and run a calibration",
                "install": "Install its Python packages",
            },
        }[mode]
        labels = {
            "run": ("Run", "mdi-play"),
            "load": ("Load existing", "mdi-folder-open"),
            "install": ("Install", "mdi-hammer-wrench"),
            "update": ("Check for update", "mdi-update"),
            "clone": ("Re-clone" if found else "Clone", "mdi-source-branch"),
        }
        subs["update"] = "Compare with GitHub"
        subs["clone"] = (
            "Fresh copy from GitHub, then Install; the old one is kept"
            if found
            else "Download it from GitHub, then Install"
        )
        actions = []
        for act in ("run", "load", "install", "update", "clone"):
            if act not in _MODE_ACTIONS[mode]:
                continue
            label, icon = labels[act]
            actions.append(
                {
                    "label": label,
                    "sub": subs[act],
                    "icon": icon,
                    "value": f"act:{mode}:{act}",
                    "primary": act == "run",
                    "busy": False,
                    "tone": "",
                    "disabled": (
                        act in ("run", "install", "update") and not found
                    ),
                }
            )
        self._st.wiz_mode_info = {
            **meta,
            "mode": mode,
            "path": str(st["dir"]) if found else "Not installed",
            "chips": chips,
            "actions": actions,
        }
        self._st.wiz_view = "mode"
        self._st.wiz_mode = mode
        self._st.wiz_step = 1
        self._set_choices([])
        self._apply_job_result(mode)

    def _set_flow(self, mode: str) -> None:
        self._flow = mode
        self._st.wiz_steps = list(
            {
                "sageswarm": _STEPS_SAGESWARM,
                "sagelightcone": _STEPS_SAGELIGHTCONE,
            }.get(mode, _STEPS)
        )

    def _close_panels(self) -> None:
        self._stop_plot_watch()
        self._st.pso_gallery_show = False
        self._st.wiz_par_show = False
        self._st.wiz_sw_config_show = False
        self._st.wiz_lc_config_show = False
        self._st.wiz_clone_dir_show = False
        self._st.wiz_filename_show = False

    async def _go_home(self) -> None:
        self._close_panels()
        await self._refresh_status()
        self._show_home()

    async def _enter(self, mode: str) -> None:
        self._close_panels()
        self._set_flow(mode)
        await self._refresh_status()
        self._show_mode(mode)

    async def _menu_return(self, mode: str) -> None:
        """A flow step finished: offer the way back to its mode screen,
        leaving its output in view."""
        if self._st.wiz_view != "term":
            await self._enter(mode)
            return
        self._emit("", "info")
        self._set_choices([self._mode_back_choice(mode)])

    def _mode_back_choice(self, mode: str) -> dict:
        return {
            "label": f"Back to {_MODE_META[mode]['title']}",
            "value": f"mode:{mode}",
            "icon": "mdi-arrow-left",
            "disabled": False,
        }

    # ── in-place update check, and the model / lightcone picker ──────────

    def _set_action(self, mode: str, act: str, **fields) -> None:
        """Change one button on the mode screen (a fresh dict, so the
        browser sees the change)."""
        info = dict(self._st.wiz_mode_info)
        if info.get("mode") != mode:
            return
        info["actions"] = [
            {**a, **fields} if a["value"].endswith(f":{act}") else a
            for a in info["actions"]
        ]
        self._st.wiz_mode_info = info
        self._st.wiz_busy = False
        self._st.flush()

    def _repo_of(self, mode: str) -> Path | None:
        return {
            "sage26": self._sage26_dir,
            "sagelightcone": self._lc_dir,
            "sageswarm": self._sw_dir,
        }[mode]

    async def _check_update_inline(self, mode: str) -> None:
        """Check for update on the button itself: it spins while checking
        GitHub, then says what it found (and becomes Update if behind)."""
        self._set_action(mode, "update", busy=True, sub="Checking GitHub ...")
        st = await self._git_status(self._repo_of(mode))
        where = f"{st['branch']} @ {st['short']}" if st["short"] else ""
        if not st["repo"]:
            self._set_action(
                mode,
                "update",
                busy=False,
                sub="Not a git checkout",
                tone="warn",
            )
        elif st["offline"]:
            self._set_action(
                mode,
                "update",
                busy=False,
                sub="Could not reach GitHub",
                tone="warn",
            )
        elif st["behind"]:
            n = st["behind"]
            self._set_action(
                mode,
                "update",
                busy=False,
                label="Update",
                icon="mdi-download",
                sub=f"{n} new commit{'s' if n > 1 else ''} on GitHub "
                f"({where}) — click to update",
                tone="new",
                value=f"act:{mode}:pull",
            )
        elif not st["upstream"]:
            self._set_action(
                mode,
                "update",
                busy=False,
                sub=f"No upstream branch to compare ({where})",
                tone="warn",
            )
        else:
            self._set_action(
                mode,
                "update",
                busy=False,
                sub=f"Up to date ({where})",
                tone="ok",
            )

    async def _pull_inline(self, mode: str) -> None:
        repo = self._repo_of(mode)
        self._set_action(
            mode, "pull", busy=True, sub="Updating from GitHub ..."
        )
        rc, _ = await self._git_capture(
            ["pull", "--ff-only", "--recurse-submodules"], repo
        )
        if rc != 0:
            self._set_action(
                mode,
                "pull",
                busy=False,
                sub="Update blocked by local changes — commit, stash or "
                "re-clone",
                tone="warn",
            )
            return
        _, short = await self._git_capture(
            ["rev-parse", "--short", "HEAD"], repo
        )
        rebuild = {
            "sage26": " — Install to recompile",
            "sagelightcone": " — Install to rebuild",
            "sageswarm": "",
        }[mode]
        self._set_action(
            mode,
            "pull",
            busy=False,
            label="Check for update",
            icon="mdi-update",
            sub=f"Updated to {short}{rebuild}",
            tone="ok",
            value=f"act:{mode}:update",
        )

    @staticmethod
    def _file_meta(paths: list[Path]) -> list[str]:
        import datetime as _dt

        paths = [q for q in paths if q.exists()]
        if not paths:
            return []
        size = sum(q.stat().st_size for q in paths)
        when = max(q.stat().st_mtime for q in paths)
        units = (("TB", 1e12), ("GB", 1e9), ("MB", 1e6), ("KB", 1e3))
        unit, div = next(((u, d) for u, d in units if size >= d), ("B", 1))
        return [
            f"{size / div:.1f} {unit}",
            _dt.datetime.fromtimestamp(when).strftime("%d %b %Y"),
        ]

    def _model_items(self) -> list[dict]:
        self._models = self._find_models()
        items = []
        for m in self._models:
            out = Path(m["hdf5"]).parent
            files = sorted(out.glob("model_*.hdf5")) or [Path(m["hdf5"])]
            chips = self._file_meta(files)
            if len(files) > 1:
                chips.insert(0, f"{len(files)} files")
            items.append(
                {
                    "label": m["name"],
                    "sub": str(out),
                    "chips": chips + [Path(m["par"]).name],
                    "value": f"model:{m['name']}",
                    "icon": "mdi-database",
                }
            )
        return items

    def _lightcone_items(self) -> list[dict]:
        items = []
        for f in self._discover_lightcones():
            chips = self._file_meta([f])
            try:
                import h5py

                with h5py.File(f, "r") as h:
                    key = "ra" if "ra" in h else "Posx"
                    chips.insert(0, f"{h[key].shape[0]:,} galaxies")
            except Exception:
                pass
            items.append(
                {
                    "label": f.parent.name,
                    "sub": str(f),
                    "chips": chips,
                    "value": f"lc_open:{f}",
                    "icon": "mdi-telescope",
                }
            )
        return items

    async def _show_pick(self, mode: str) -> None:
        """Big buttons for each model (SAGE26), lightcone (LightSAGE), or
        both ("all": the home screen's Load a previous model)."""
        if mode == "sage26":
            items = self._model_items()
            title, empty = "Load a model", (
                "No SAGE26 models found yet. Run SAGE26 first."
            )
        elif mode == "sagelightcone":
            items = self._lightcone_items()
            title, empty = "Load a lightcone", (
                "No lightcones found yet. Run LightSAGE first."
            )
        else:
            items = self._model_items() + self._lightcone_items()
            title, empty = "Load a previous model", (
                "No models or lightcones found yet."
            )
        meta = _MODE_META.get(mode, _MODE_META["sage26"])
        back = "home" if mode == "all" else f"mode:{mode}"
        self._st.wiz_pick = {
            "title": title,
            "empty": empty,
            "accent": meta["accent"],
            "back": back,
            "back_label": "Home" if back == "home" else meta["title"],
            "items": items,
        }
        self._st.wiz_loading = ""
        self._st.wiz_view = "pick"
        self._st.wiz_mode = "" if mode == "all" else mode
        self._set_choices([])

    async def _start_action(self, mode: str, act: str) -> None:
        """A mode-screen button: open the terminal and start that step."""
        value = _MODE_ACTIONS.get(mode, {}).get(act)
        if value is None:
            return
        self._set_flow(mode)
        self._st.wiz_view = "term"
        self._st.wiz_mode = mode
        self._wiz_buf = bytearray()
        self._push_bytes(b"\x1b[2J\x1b[3J\x1b[H")
        self._emit(f"ViSAGE  ::  {_MODE_META[mode]['title']}", "title")
        self._emit("=" * 52, "sep")
        await self._handle_choice(value)

    def _on_choice(self, value: str, **_) -> None:
        asyncio.ensure_future(self._handle_choice(value))

    async def _handle_choice(self, value: str) -> None:
        self._busy()

        # Screen navigation (home / mode screens) and mode-screen buttons.
        back_to_mode = {
            "back_sage26_menu": "sage26",
            "sw_back_scan": "sageswarm",
            "sw_done": "sageswarm",
            "lc_back_scan": "sagelightcone",
            "lc_done": "sagelightcone",
        }
        if value.startswith("mode:"):
            await self._enter(value[len("mode:") :])
            return
        if value.startswith("act:"):
            _, mode, act = value.split(":", 2)
            if act == "update":
                await self._check_update_inline(mode)
            elif act == "pull":
                await self._pull_inline(mode)
            elif act == "load":
                await self._show_pick(mode)
            elif act == "run":
                await self._show_setup(mode)
            elif act == "install":
                await self._install_inline(mode)
            elif act == "clone":
                await self._clone_inline(mode)
            elif act == "log":
                self._show_log(mode)
            else:
                await self._start_action(mode, act)
            return
        if value.startswith("model:") or value.startswith("lc_open:"):
            self._st.wiz_loading = (
                value[len("model:") :]
                if value.startswith("model:")
                else Path(value[len("lc_open:") :]).parent.name
            )
            self._st.flush()
            await asyncio.sleep(0.8)  # let "Opening ..." show before relaunch
        if value in ("home", "back_main", "back_sage26"):
            await self._go_home()
            return
        if value in back_to_mode:
            await self._enter(back_to_mode[value])
            return
        if value == "su:reopen":
            await self._show_setup(self._setup_mode)
            return
        if value.startswith("su:"):
            await self._setup_choose(value[len("su:") :])
            return
        if value == "tools":
            self._st.wiz_view = "term"
            self._wiz_buf = bytearray()
            self._push_bytes(b"\x1b[2J\x1b[3J\x1b[H")
            await self._step_install_linux_tools()
            return

        if value == "load":
            await self._step_select_model()

        elif value == "run_sage26":
            await self._step_run_sage26_existing()

        elif value.startswith("model:"):
            name = value[6:]
            model = next((m for m in self._models if m["name"] == name), None)
            if model:
                await self._launch_explore(model["par"], model_name=name)

        elif value == "clone_sage26":
            await self._step_clone()

        elif value == "confirm_clone":
            await self._do_clone()

        elif value == "compile_sage26":
            await self._step_compile()

        elif value == "create_par":
            await self._step_create_par()

        elif value == "do_create_par":
            await self._do_create_par()

        elif value.startswith("par:"):
            self._par_path = Path(value[4:])
            await self._step_par_edit()

        elif value == "save_run_sage26":
            await self._step_run_sage26()

        elif value == "update_sage26":
            await self._git_update("SAGE26", self._sage26_dir)
            await self._step_sage26_menu()

        elif value == "sw_update":
            await self._git_update("SAGEswarm", self._sw_dir)
            await self._step_sw_scan()

        elif value == "lc_update":
            await self._git_update("LightSAGE", self._lc_dir)
            await self._step_lc_scan()

        elif value == "sw_clone":
            await self._step_sw_clone()

        elif value == "confirm_sw_clone":
            await self._do_sw_clone()

        elif value == "sw_install":
            await self._step_sw_install()

        elif value == "sw_configure":
            await self._step_sw_config()

        elif value == "sw_run":
            await self._step_sw_run()

        elif value == "lc_clone":
            await self._step_lc_clone()

        elif value == "confirm_lc_clone":
            await self._do_lc_clone()

        elif value == "lc_build":
            await self._step_lc_build()

        elif value == "lc_configure":
            await self._step_lc_config()

        elif value == "lc_run":
            await self._step_lc_run()

        elif value == "lc_visualize":
            await self._launch_lightcone_viewer()

        elif value == "lc_load":
            await self._step_lc_load()

        elif value.startswith("lc_open:"):
            await self._launch_lightcone_viewer(value[len("lc_open:") :])

        elif value == "install_linux_tools":
            await self._step_install_linux_tools()

    async def _step_run_sage26_existing(self) -> None:
        """Run SAGE26 with the existing local installation — no clone step."""
        self._back = "back_sage26_menu"
        self._st.wiz_step = 2
        if not self._sage26_dir:
            self._emit("SAGE26 not found locally.", "err")
            self._emit("Clone it from GitHub first.", "info")
            self._set_choices(
                [
                    {
                        "label": "Back",
                        "value": "back_sage26_menu",
                        "icon": "mdi-arrow-left",
                        "disabled": False,
                    }
                ]
            )
            return

        compiled, n_obj = self._sage26_compiled(self._sage26_dir)
        if compiled:
            self._emit(
                f"SAGE26 found at {self._sage26_dir}  ({n_obj} object files)",
                "ok",
            )
            self._emit("Select a parameter file to run:", "info")
            self._emit("", "info")
            await self._step_pick_par()
        else:
            self._emit(f"SAGE26 found at {self._sage26_dir}", "ok")
            self._emit(
                "Not yet compiled — compile it first, then select a par file.",
                "warn",
            )
            self._set_choices(
                [
                    {
                        "label": "Compile SAGE26",
                        "value": "compile_sage26",
                        "icon": "mdi-cog-outline",
                        "disabled": False,
                    },
                    {
                        "label": "Back",
                        "value": "back_sage26_menu",
                        "icon": "mdi-arrow-left",
                        "disabled": False,
                    },
                ]
            )

    async def _step_select_model(self) -> None:
        self._st.wiz_step = 1
        self._emit("Select a model to load:", "info")
        self._emit("", "info")
        choices = [
            {
                "label": m["name"],
                "value": f"model:{m['name']}",
                "icon": "mdi-database",
                "disabled": False,
            }
            for m in self._models
        ]
        choices.append(
            {
                "label": "Back",
                "value": "back_main",
                "icon": "mdi-arrow-left",
                "disabled": False,
            }
        )
        self._set_choices(choices)

    async def _step_sage26_menu(self) -> None:
        await self._menu_return("sage26")

    async def _step_clone(self) -> None:
        self._st.wiz_step = 2
        self._emit("Choose where to clone SAGE26:", "info")
        self._emit(
            "  A 'SAGE26' folder will be created inside the chosen directory.",
            "info",
        )
        self._emit("", "info")
        self._st.wiz_clone_dir = str(Path.home())
        self._st.wiz_clone_dir_show = True
        self._st.flush()
        self._set_choices(
            [
                {
                    "label": "Clone Here",
                    "value": "confirm_clone",
                    "icon": "mdi-git",
                    "disabled": False,
                },
                {
                    "label": "Back",
                    "value": self._back,
                    "icon": "mdi-arrow-left",
                    "disabled": False,
                },
            ]
        )

    async def _do_clone(self) -> None:
        self._st.wiz_step = 2
        raw_dir = str(self._st.wiz_clone_dir or "").strip() or str(Path.home())
        parent = Path(raw_dir).expanduser().resolve()
        if not parent.is_dir():
            self._emit(f"Directory not found: {parent}", "err")
            self._emit("Please enter a valid directory path.", "info")
            self._st.wiz_clone_dir_show = True
            self._st.flush()
            self._set_choices(
                [
                    {
                        "label": "Clone Here",
                        "value": "confirm_clone",
                        "icon": "mdi-git",
                        "disabled": False,
                    },
                    {
                        "label": "Back",
                        "value": self._back,
                        "icon": "mdi-arrow-left",
                        "disabled": False,
                    },
                ]
            )
            return
        target = parent / "SAGE26"
        # A re-clone lands on an existing folder: git refuses to clone into
        # one, so move it aside first (never delete — it may hold edited
        # configs or output) and say where it went.
        if target.exists():
            try:
                backup = self._move_aside(target)
            except OSError as exc:
                self._emit(f"Could not move {target} aside: {exc}", "err")
                self._set_choices(
                    [
                        {
                            "label": "Back",
                            "value": self._back,
                            "icon": "mdi-arrow-left",
                            "disabled": False,
                        }
                    ]
                )
                return
            self._emit(f"Existing checkout moved to {backup}", "warn")
        self._emit(f"Cloning SAGE26 into {target} ...", "info")
        rc = await self._run_cmd(
            ["git", "clone", _SAGE26_REPO, target],
            cwd=parent,
        )
        if rc != 0:
            self._emit(
                "Clone failed. Check internet connection and try again.", "err"
            )
            self._set_choices(
                [
                    {
                        "label": "Back",
                        "value": self._back,
                        "icon": "mdi-arrow-left",
                        "disabled": False,
                    }
                ]
            )
            return
        self._sage26_dir = target
        await self._step_compile()

    async def _step_compile(self) -> None:
        self._st.wiz_step = 2
        if not self._sage26_dir:
            return
        first_run = self._sage26_dir / "first_run.sh"
        if first_run.is_file():
            self._warn_crlf([first_run])
            self._emit("Running first_run.sh ...", "info")
            await self._run_cmd(["bash", "first_run.sh"], cwd=self._sage26_dir)
        build_script = Path.home() / ".visage" / _SAGE26_BUILD_SCRIPT
        try:
            build_script.parent.mkdir(parents=True, exist_ok=True)
            self._write_unix_text(
                build_script,
                _SAGE26_BUILD_SCRIPT_TEMPLATE.format(
                    sage_dir=self._tc_path(self._sage26_dir)
                ),
            )
        except OSError as exc:
            self._emit(f"Could not write build helper: {exc}", "err")
            self._set_choices([self._back_choice(self._back)])
            return
        self._emit(
            "Compiling SAGE26 on every CPU core (may take a minute) ...",
            "info",
        )
        rc = await self._run_cmd(["bash", build_script], cwd=self._sage26_dir)
        if rc != 0:
            self._emit("Compilation failed. See output above.", "err")
            self._set_choices(
                [
                    {
                        "label": "Back",
                        "value": self._back,
                        "icon": "mdi-arrow-left",
                        "disabled": False,
                    }
                ]
            )
            return
        self._emit("Compilation complete!", "ok")
        await self._step_pick_par()

    async def _step_pick_par(self) -> None:
        self._st.wiz_step = 3
        par_files = self._find_par_files()
        _create_choice = {
            "label": "Create config file",
            "value": "create_par",
            "icon": "mdi-file-plus-outline",
            "disabled": False,
        }
        if not par_files:
            self._emit("No .par files found.", "warn")
            self._emit(
                "Use 'Create config file' below, or add a .par file "
                "to SAGE26/input/ and rescan.",
                "info",
            )
            self._emit("", "info")
            self._set_choices(
                [
                    _create_choice,
                    {
                        "label": "Back",
                        "value": self._back,
                        "icon": "mdi-arrow-left",
                        "disabled": False,
                    },
                ]
            )
            return
        if len(par_files) == 1:
            self._par_path = par_files[0]
            await self._step_par_edit()
        else:
            self._emit("Multiple parameter files found. Select one:", "info")
            self._emit("", "info")
            choices = [
                {
                    "label": p.name,
                    "value": f"par:{p}",
                    "icon": "mdi-file-cog",
                    "disabled": False,
                }
                for p in par_files
            ]
            choices.append(_create_choice)
            choices.append(
                {
                    "label": "Back",
                    "value": self._back,
                    "icon": "mdi-arrow-left",
                    "disabled": False,
                }
            )
            self._set_choices(choices)

    async def _step_create_par(self) -> None:
        """Show filename input then wait for the user to confirm."""
        self._st.wiz_step = 3
        self._emit("Enter a name for the new config file:", "info")
        self._st.wiz_filename_show = True
        self._st.wiz_filename = "millennium"
        self._st.flush()
        self._set_choices(
            [
                {
                    "label": "Create",
                    "value": "do_create_par",
                    "icon": "mdi-check",
                    "disabled": False,
                },
                {
                    "label": "Back",
                    "value": self._back,
                    "icon": "mdi-arrow-left",
                    "disabled": False,
                },
            ]
        )

    async def _do_create_par(self) -> None:
        """Create the par file using the user-supplied filename."""
        raw = (
            str(self._st.wiz_filename or "millennium").strip() or "millennium"
        )
        name = raw if raw.endswith(".par") else raw + ".par"
        self._st.wiz_filename_show = False
        self._st.flush()
        if self._sage26_dir:
            inp_dir = self._sage26_dir / "input"
        else:
            inp_dir = Path.cwd() / "input"
        inp_dir.mkdir(parents=True, exist_ok=True)
        dest = inp_dir / name
        self._emit(f"Creating config file: {dest}", "info")
        sage26 = self._sage26_dir or Path.cwd()
        # Paths as SAGE will see them (/mnt/c/... when it runs in WSL).
        content = _MILLENNIUM_PAR_TEMPLATE.format(
            output_dir=self._tc_path(sage26 / "output" / "millennium"),
            sim_dir=self._tc_path(sage26 / "input" / "millennium" / "trees"),
            snaplist=self._tc_path(
                sage26 / "input" / "millennium" / "trees" / "millennium.a_list"
            ),
        )
        self._write_unix_text(dest, content)
        self._par_path = dest
        self._emit(
            "Template written. Edit the paths to the right, then Save & Run.",
            "ok",
        )
        self._emit("", "info")
        await self._step_par_edit()

    async def _step_par_edit(self) -> None:
        self._st.wiz_step = 3
        if not self._par_path:
            return
        self._emit(f"Parameter file : {self._par_path}", "info")
        self._emit(
            "Edit the file to the right, then click Save & Run.", "info"
        )
        self._emit("", "info")
        try:
            text = self._read_text(self._par_path)
        except Exception as exc:
            self._emit(f"Could not read par file: {exc}", "err")
            return
        self._st.wiz_par_text = text
        self._show_params(text, "par", "par")
        self._st.wiz_par_show = True
        self._st.flush()
        self._set_choices(
            [
                {
                    "label": "Save & Run SAGE26",
                    "value": "save_run_sage26",
                    "icon": "mdi-play",
                    "disabled": False,
                },
                {
                    "label": "Back",
                    "value": self._back,
                    "icon": "mdi-arrow-left",
                    "disabled": False,
                },
            ]
        )

    async def _step_run_sage26(self) -> None:
        self._st.wiz_step = 4
        self._sync_params_to_text()  # fold edited form values into the .par text
        self._st.wiz_par_show = False
        self._st.flush()

        if self._par_path:
            if self._toolchain.kind == "wsl":
                self._st.wiz_par_text = self._par_paths_for_toolchain(
                    str(self._st.wiz_par_text or "")
                )
            try:
                self._write_unix_text(self._par_path, self._st.wiz_par_text)
                self._emit(f"Saved {self._par_path.name}", "ok")
            except Exception as exc:
                self._emit(f"Could not save par file: {exc}", "err")
                return

            # Create OutputDir before SAGE26 runs — it won't create it itself.
            try:
                from visage.io.par_reader import parse_par

                cfg = parse_par(self._par_path)
                cfg.output_dir.mkdir(parents=True, exist_ok=True)
                self._emit(f"Output dir ready: {cfg.output_dir}", "ok")
            except Exception as exc:
                self._emit(
                    f"Warning: could not create OutputDir — {exc}", "warn"
                )

        # Find binary
        sage_bin: Path | None = None
        if self._sage26_dir:
            for candidate in (
                self._sage26_dir / "bin" / "sage",
                self._sage26_dir / "sage",
            ):
                if candidate.is_file():
                    sage_bin = candidate
                    break
        if sage_bin is None:
            self._emit("SAGE26 binary not found (expected bin/sage).", "err")
            self._set_choices(
                [
                    {
                        "label": "Back",
                        "value": self._back,
                        "icon": "mdi-arrow-left",
                        "disabled": False,
                    }
                ]
            )
            return

        self._emit("", "info")
        self._emit("Running SAGE26 — output follows.", "info")
        self._emit("This may take a while for large simulations.", "info")
        self._emit("", "info")
        rc = await self._run_cmd(
            [sage_bin, self._par_path], cwd=self._sage26_dir
        )
        if rc != 0:
            self._emit(
                f"SAGE26 exited with code {rc}. See output above.", "err"
            )
            self._set_choices(
                [
                    {
                        "label": "Back",
                        "value": self._back,
                        "icon": "mdi-arrow-left",
                        "disabled": False,
                    }
                ]
            )
            return

        self._emit("", "info")
        self._emit("SAGE26 run complete!", "ok")
        if self._st.wiz_view in ("run", "term") and self._run is not None:
            return
        self._models = self._find_models()
        if not self._models:
            self._emit(
                "No models found after run. Check OutputDir in the par file.",
                "err",
            )
            self._set_choices(
                [
                    {
                        "label": "Back",
                        "value": self._back,
                        "icon": "mdi-arrow-left",
                        "disabled": False,
                    }
                ]
            )
            return
        if len(self._models) == 1:
            m = self._models[0]
            await self._launch_explore(m["par"], model_name=m["name"])
        else:
            await self._step_select_model()

    def _par_paths_for_toolchain(self, text: str) -> str:
        """Rewrite Windows absolute paths in a .par (C:\\...) into the form
        SAGE sees inside WSL (/mnt/c/...).  ViSAGE reads both forms."""
        changes = [
            {"key": p["key"], "value": self._tc_path(p["value"])}
            for p in _parse_params(text, "par")
            if _re.match(r"^[A-Za-z]:[\\/]", p["value"])
        ]
        if not changes:
            return text
        self._emit(
            f"Converted {len(changes)} Windows path(s) in the .par to the "
            "form SAGE sees inside WSL (/mnt/...).",
            "info",
        )
        return _apply_params(text, changes, "par")

    # ── SAGEswarm (PSO calibration) flow ─────────────────────────────────────

    def _find_sageswarm(self) -> Path | None:
        roots = [Path.cwd().parent, Path.cwd(), Path.home()]
        names = ["SAGEswarm", "sageswarm"]
        for root in roots:
            for name in names:
                c = root / name
                if c.is_dir() and (c / "main.py").is_file():
                    return c
        return None

    def _locate_sage_bin(self) -> Path | None:
        cands: list[Path] = []
        if self._sage26_dir:
            cands += [
                self._sage26_dir / "bin" / "sage",
                self._sage26_dir / "sage",
            ]
        if self._sw_dir:
            cands += [self._sw_dir / "sage", self._sw_dir / "bin" / "sage"]
        for c in cands:
            if c.is_file():
                return c
        return None

    def _sw_script_path(self) -> Path | None:
        """Path to the SAGEswarm run script (run_pso.sh) in the checkout."""
        return (self._sw_dir / _SW_RUN_SCRIPT) if self._sw_dir else None

    def _sw_output_dir(self) -> Path | None:
        """Where the PSO writes its plots — parsed from the edited run_pso.sh
        (OUTPUT_PATH=… or a literal -o …), resolved relative to the SAGEswarm
        dir. Falls back to the SAGEswarm dir itself."""
        if not self._sw_dir:
            return None
        text = str(self._st.wiz_sw_script_text or "")
        val = None
        m = _re.search(
            r'^\s*OUTPUT_PATH\s*=\s*["\']?([^"\'\n#]+)', text, _re.MULTILINE
        )
        if m:
            val = m.group(1).strip()
        else:
            m = _re.search(r'-o\s+["\']?([^"\'\s]+)', text)
            if m:
                val = m.group(1).strip()
        if not val or val.startswith("$"):
            return self._sw_dir
        p = self._toolchain.native(val)
        return p if p.is_absolute() else (self._sw_dir / p)

    def _back_choice(self, value: str = "sw_back_scan") -> dict:
        return {
            "label": "Back",
            "value": value,
            "icon": "mdi-arrow-left",
            "disabled": False,
        }

    def _sw_available_constraints(self) -> list[str]:
        """Valid -x names, read from the checkout's src/constraints.py registry."""
        if not self._sw_dir:
            return []
        try:
            text = (self._sw_dir / "src" / "constraints.py").read_text()
        except OSError:
            return []
        m = _re.search(r"_constraints\s*=\s*\{(.*?)\}", text, _re.DOTALL)
        if not m:
            return []
        return _re.findall(r"['\"]([A-Za-z0-9_]+)['\"]\s*:", m.group(1))

    async def _step_sw_scan(self) -> None:
        await self._menu_return("sageswarm")

    async def _step_sw_clone(self) -> None:
        self._st.wiz_step = 1
        self._emit("Choose where to clone SAGEswarm:", "info")
        self._emit(
            "  A 'SAGEswarm' folder will be created inside the chosen "
            "directory.",
            "info",
        )
        self._emit("", "info")
        self._st.wiz_clone_dir = str(Path.home())
        self._st.wiz_clone_dir_show = True
        self._st.flush()
        self._set_choices(
            [
                {
                    "label": "Clone Here",
                    "value": "confirm_sw_clone",
                    "icon": "mdi-git",
                    "disabled": False,
                },
                self._back_choice(),
            ]
        )

    async def _do_sw_clone(self) -> None:
        self._st.wiz_step = 1
        raw = str(self._st.wiz_clone_dir or "").strip() or str(Path.home())
        parent = Path(raw).expanduser().resolve()
        if not parent.is_dir():
            self._emit(f"Directory not found: {parent}", "err")
            self._st.wiz_clone_dir_show = True
            self._st.flush()
            self._set_choices(
                [
                    {
                        "label": "Clone Here",
                        "value": "confirm_sw_clone",
                        "icon": "mdi-git",
                        "disabled": False,
                    },
                    self._back_choice(),
                ]
            )
            return
        target = parent / "SAGEswarm"
        # A re-clone lands on an existing folder: git refuses to clone into
        # one, so move it aside first (never delete — it may hold edited
        # configs or output) and say where it went.
        if target.exists():
            try:
                backup = self._move_aside(target)
            except OSError as exc:
                self._emit(f"Could not move {target} aside: {exc}", "err")
                self._set_choices([self._back_choice()])
                return
            self._emit(f"Existing checkout moved to {backup}", "warn")
        self._emit(f"Cloning SAGEswarm into {target} ...", "info")
        rc = await self._run_cmd(
            ["git", "clone", _SAGESWARM_REPO, target], cwd=parent
        )
        if rc != 0:
            self._emit(
                "Clone failed. Check internet connection and try again.", "err"
            )
            self._set_choices([self._back_choice()])
            return
        self._sw_dir = target
        await self._step_sw_install()

    async def _step_sw_install(self) -> None:
        self._st.wiz_step = 2
        if not self._sw_dir:
            self._emit("SAGEswarm not found — clone it first.", "err")
            self._set_choices([self._back_choice()])
            return
        req = self._sw_dir / "requirements.txt"
        if req.is_file():
            self._emit("Installing SAGEswarm requirements ...", "info")
            # Use python3 to match run_pso.sh's `python3 ./main.py`, so deps
            # land in the interpreter the run will actually use.
            cmd = ["python3", "-m", "pip", "install", "-r", "requirements.txt"]
            if self._toolchain.kind == "wsl":
                # Ubuntu's python3 refuses system-wide pip installs
                # (PEP 668), so install for the user.  Older pips lack
                # --break-system-packages but don't need it either.
                cmd = [
                    "bash",
                    "-c",
                    "python3 -m pip install --user --break-system-packages "
                    "-r requirements.txt || "
                    "python3 -m pip install --user -r requirements.txt",
                ]
            rc = await self._run_cmd(cmd, cwd=self._sw_dir)
            if rc != 0:
                self._emit("pip install failed. See output above.", "err")
                self._set_choices(
                    [
                        {
                            "label": "Continue anyway",
                            "value": "sw_configure",
                            "icon": "mdi-arrow-right",
                            "disabled": False,
                        },
                        self._back_choice(),
                    ]
                )
                return
            self._emit("Requirements installed.", "ok")
        else:
            self._emit("No requirements.txt found — skipping install.", "warn")
        await self._step_sw_config()

    async def _step_sw_config(self) -> None:
        """Edit run_pso.sh (all run options live in it), then run it — mirrors
        the SAGE26 .par editor."""
        self._st.wiz_step = 3
        script = self._sw_script_path()
        if script is None:
            self._emit("SAGEswarm not found — clone it first.", "err")
            self._set_choices([self._back_choice()])
            return

        if script.is_file():
            try:
                self._st.wiz_sw_script_text = self._read_text(script)
                self._emit(
                    f"Loaded {script.name} — edit it on the right.", "ok"
                )
            except OSError as exc:
                self._emit(f"Could not read {script.name}: {exc}", "err")
                self._set_choices([self._back_choice()])
                return
        else:
            # No script shipped — seed a template the user can fill in.
            self._st.wiz_sw_script_text = _SW_RUN_SCRIPT_TEMPLATE
            self._emit(
                f"No {script.name} found — starting from a template.", "warn"
            )

        avail = self._sw_available_constraints()
        if avail:
            self._emit("Valid constraints (-x): " + ", ".join(avail), "info")
        self._emit(
            "Set BASE_PATH (the compiled ./sage) and CONFIG_PATH (.par); "
            "bounds live in the -S space file.",
            "info",
        )
        self._emit("", "info")

        self._show_params(str(self._st.wiz_sw_script_text or ""), "sh", "sw")
        self._st.wiz_sw_config_show = True
        self._st.flush()
        self._set_choices(
            [
                {
                    "label": "Save & Run PSO",
                    "value": "sw_run",
                    "icon": "mdi-play",
                    "disabled": False,
                },
                self._back_choice(),
            ]
        )

    async def _step_sw_run(self) -> None:
        self._st.wiz_step = 4
        self._sync_params_to_text()  # fold edited form values into run_pso.sh
        self._st.wiz_sw_config_show = False
        self._st.flush()
        script = self._sw_script_path()
        if script is None or not self._sw_dir:
            self._emit("SAGEswarm directory not set.", "err")
            self._set_choices([self._back_choice()])
            return

        # Save the edited run_pso.sh back to the checkout (like the .par editor).
        try:
            self._write_unix_text(
                script, str(self._st.wiz_sw_script_text or "")
            )
            self._emit(f"Saved {script.name}", "ok")
        except OSError as exc:
            self._emit(f"Could not save {script.name}: {exc}", "err")
            self._set_choices([self._back_choice()])
            return

        self._emit("", "info")
        self._emit(
            "Running SAGEswarm PSO — plots appear live in the gallery.", "info"
        )
        self._emit("This can take a long time.  Use Cancel to stop.", "info")
        self._emit("", "info")

        # Watch the PSO output directory (from run_pso.sh) for plot PNGs.
        watch_dir = self._sw_output_dir()
        self._start_plot_watch(watch_dir)
        rc = await self._run_cmd(["bash", _SW_RUN_SCRIPT], cwd=self._sw_dir)
        # Final sweep to catch plots written just before exit, then stop.
        self._scan_plots(watch_dir)
        self._stop_plot_watch()

        if rc != 0:
            self._emit(f"SAGEswarm exited with code {rc}.", "err")
            self._set_choices(
                [
                    {
                        "label": "Run again",
                        "value": "sw_run",
                        "icon": "mdi-replay",
                        "disabled": False,
                    },
                    self._back_choice(),
                ]
            )
            return
        self._st.wiz_step = 5
        self._emit("", "info")
        self._emit("PSO run complete. Final plots are in the gallery.", "ok")
        self._set_choices(
            [
                {
                    "label": "Run again",
                    "value": "sw_run",
                    "icon": "mdi-replay",
                    "disabled": False,
                },
                {
                    "label": "Done",
                    "value": "sw_done",
                    "icon": "mdi-check",
                    "disabled": False,
                },
            ]
        )

    # ── live PSO plot gallery ────────────────────────────────────────────────

    _PSO_PLOT_CAP = 60  # max plots shown in the gallery
    # Subdirectories that hold bundled observational data / VCS junk, never the
    # PSO's own diagnostic plots — skipped so we don't surface stale PNGs.
    _PLOT_SKIP_DIRS = {
        ".git",
        "__pycache__",
        ".ipynb_checkpoints",
        "data",
        "obs",
        "observations",
        "node_modules",
    }

    def _start_plot_watch(self, main_dir: Path | None) -> None:
        self._stop_plot_watch()
        self._plot_seen = {}
        self._st.pso_plots = []
        self._st.wiz_run_plots = []
        self._st.pso_gallery_show = self._st.wiz_view != "run"
        self._st.flush()
        if main_dir is None:
            return
        self._emit(f"  [gallery] watching {Path(main_dir)} for *.png", "out")
        self._plot_watch_stop = False
        self._plot_task = asyncio.ensure_future(
            self._watch_pso_plots(Path(main_dir))
        )

    def _stop_plot_watch(self) -> None:
        self._plot_watch_stop = True
        task = self._plot_task
        if task is not None and not task.done():
            task.cancel()
        self._plot_task = None

    async def _watch_pso_plots(self, main_dir: Path) -> None:
        try:
            while not self._plot_watch_stop:
                self._scan_plots(main_dir)
                await asyncio.sleep(2.0)
        except asyncio.CancelledError:
            pass
        except Exception as exc:  # keep the run alive; just report
            self._emit(f"  [gallery] watcher error: {exc}", "err")

    def _scan_plots(self, main_dir: Path | None) -> None:
        """Scan the PSO main folder (recursively) for PNGs; re-encode changed
        ones. Recursive so plots land wherever SAGEswarm writes them under the
        run cwd; skip dirs that only hold bundled obs data."""
        if main_dir is None:
            return
        root = Path(main_dir)
        pngs: list[Path] = []
        try:
            for p in root.rglob("*.png"):
                parts = p.relative_to(root).parts[:-1]
                if any(seg in self._PLOT_SKIP_DIRS for seg in parts):
                    continue
                pngs.append(p)
        except OSError:
            return
        pngs = sorted(pngs)[: self._PSO_PLOT_CAP]
        current = list(self._st.pso_plots or [])
        by_name = {it["name"]: it for it in current}
        changed = False
        for p in pngs:
            # Forward slashes on every OS, so gallery labels read the same.
            rel = p.relative_to(root).as_posix()
            try:
                mtime = int(p.stat().st_mtime)
            except OSError:
                continue
            if self._plot_seen.get(rel) == mtime and rel in by_name:
                continue
            try:
                raw = p.read_bytes()
            except OSError:
                continue
            fresh = rel not in by_name
            self._plot_seen[rel] = mtime
            by_name[rel] = {
                "name": rel,
                "data_url": "data:image/png;base64,"
                + _b64.b64encode(raw).decode(),
                "mtime": mtime,
            }
            changed = True
            if fresh:
                self._emit(f"  [gallery] + {rel}", "ok")
        if changed:
            self._st.pso_plots = [by_name[k] for k in sorted(by_name)]
            self._st.wiz_run_plots = _latest_per_constraint(self._st.pso_plots)
            self._st.flush()

    # ── LightSAGE (lightcone extraction) flow ────────────────────────────────

    def _find_sagelightcone(self) -> Path | None:
        """Locate an existing LightSAGE checkout by its wrapper scripts.

        "LightSAGE" is the folder name ViSAGE clones into; the other names are
        back-compat aliases for checkouts made under the upstream repo's own
        name (sage-lightcone) or manually renamed."""
        roots = [Path.cwd().parent, Path.cwd(), Path.home()]
        names = [
            "LightSAGE",
            "sage-lightcone",
            "sage_lightcone",
            "tao-lightcone-cli",
            "lightcone",
        ]
        for root in roots:
            for name in names:
                c = root / name
                if c.is_dir() and (c / "scripts" / "sage2kdtree.sh").is_file():
                    return c
        return None

    def _lc_built(self, lc: Path) -> tuple[bool, list[str]]:
        """Which of the two executables are present in the checkout's bin/."""
        tools = [
            name
            for name in ("sage2kdtree", "cli_lightcone")
            if (lc / "bin" / name).is_file()
        ]
        return (len(tools) > 0, tools)

    def _lc_script_path(self) -> Path:
        """Editable run script — kept in ~/.visage, never inside the repo."""
        return Path.home() / ".visage" / _LC_RUN_SCRIPT

    def _lc_build_script_path(self) -> Path:
        """Tools-only build helper — kept in ~/.visage, never in the repo."""
        return Path.home() / ".visage" / _LC_BUILD_SCRIPT

    def _lc_output_file(self) -> Path | None:
        """The lightcone HDF5 the run produced — parsed from OUTDIR/OUTFILE in
        the edited run script, resolved relative to the script's dir."""
        text = str(self._st.wiz_lc_script_text or "")
        script_dir = self._lc_script_path().parent

        def _var(name: str, default: str) -> str:
            m = _re.search(
                rf'^\s*{name}\s*=\s*["\']?([^"\'\n#]+)',
                text,
                _re.MULTILINE,
            )
            return m.group(1).strip() if m else default

        outdir = _var("OUTDIR", str(Path.cwd() / "sage_outputs" / "lightcone"))
        outfile = _var("OUTFILE", "lightcone.h5")
        p = self._toolchain.native(outdir)
        if not p.is_absolute():
            p = script_dir / p
        return p / outfile

    def _discover_lightcones(self) -> list[Path]:
        """Existing lightcone HDF5 files the user could open — ViSAGE's
        standard output folder, the legacy run dir, and any lightcones in the
        session-models registry. De-duplicated, most-obvious first."""
        seen: set[Path] = set()
        out: list[Path] = []

        def _add(pth: Path) -> None:
            try:
                rp = pth.expanduser().resolve()
            except OSError:
                return
            if rp.is_file() and rp not in seen:
                seen.add(rp)
                out.append(rp)

        def _is_cone(f: Path) -> bool:
            # A lightcone, not the KD-tree index LightSAGE builds beside it.
            if "kdtree" in f.name:
                return False
            try:
                import h5py

                with h5py.File(f, "r") as h:
                    return "ra" in h or "Posx" in h
            except Exception:
                return False

        for d in (
            Path.cwd() / "sage_outputs" / "lightcone",
            Path.home() / ".visage" / "lightcone_output",
        ):
            if d.is_dir():
                for f in sorted(d.glob("*.h5")):
                    _add(f)
        # Other runs' output folders (sage_outputs/<name>/), and wherever
        # the run script currently writes.
        outs = Path.cwd() / "sage_outputs"
        if outs.is_dir():
            for f in sorted(outs.glob("*/*.h5")):
                if _is_cone(f):
                    _add(f)
        try:
            cur = self._lc_output_file()
            if cur is not None and _is_cone(cur):
                _add(cur)
        except Exception:
            pass
        try:
            from visage.utils import recent_models

            for e in recent_models.load():
                if e.get("kind") == "lightcone":
                    _add(Path(e.get("path", "")))
        except Exception:
            pass
        return out

    async def _step_lc_load(self) -> None:
        """Offer any already-created lightcone HDF5 files to open directly —
        no build/run needed."""
        self._emit("", "info")
        self._emit("Looking for existing lightcone files...", "info")
        found = self._discover_lightcones()
        if not found:
            self._emit(
                "  None found in sage_outputs/lightcone/ or "
                "~/.visage/lightcone_output/. Build & run one first, or place "
                "a cli_lightcone .h5 there.",
                "warn",
            )
            self._set_choices([self._back_choice("lc_back_scan")])
            return
        self._emit(f"  Found {len(found)} lightcone file(s).", "ok")
        choices = [
            {
                # Show the containing folder so same-named files are distinct.
                "label": f"{f.parent.name}/{f.name}",
                "value": f"lc_open:{f}",
                "icon": "mdi-telescope",
                "disabled": False,
            }
            for f in found
        ]
        choices.append(self._back_choice("lc_back_scan"))
        self._set_choices(choices)

    async def _launch_lightcone_viewer(self, path: Path | str | None = None):
        """Relaunch ViSAGE in Lightcone Mode on a produced/existing HDF5 —
        mirrors the Explore-mode launch (os.execv), but with --lightcone.
        With no path, uses the output the current run script points at."""
        out = Path(path) if path is not None else self._lc_output_file()
        if out is None or not out.is_file():
            self._emit(
                f"Lightcone output not found (looked for {out}).", "err"
            )
            self._set_choices(
                [
                    {
                        "label": "Run again",
                        "value": "lc_run",
                        "icon": "mdi-replay",
                        "disabled": False,
                    },
                    self._back_choice("lc_back_scan"),
                ]
            )
            return
        self._emit("", "info")
        self._emit(f"Opening lightcone in ViSAGE: {out}", "title")
        # The page shows "Opening ..." and reloads itself once the new
        # ViSAGE is up (visage.js watches wiz_loading).
        self._st.wiz_loading = self._st.wiz_loading or out.parent.name
        self._st.flush()
        await asyncio.sleep(1.0)

        system.relaunch_visage(
            ["--lightcone", str(out), "--port", str(self._port)]
        )

    def _lc_seed_script(self) -> str:
        """Seed run_lightcone.sh, pre-filling paths from discovered dirs."""
        # Every path is written as the pipeline sees it (/mnt/c/... when it
        # runs in WSL); the SED stage's python is ViSAGE's own interpreter,
        # which WSL can launch even when it is a Windows python.exe.
        tp = self._tc_path
        lc = tp(self._lc_dir) if self._lc_dir else "/path/to/LightSAGE"
        sage = self._sage26_dir
        if sage:
            sage_out = tp(sage / "output" / "millennium")
            par = tp(sage / "input" / "millennium.par")
            alist = tp(
                sage / "input" / "millennium" / "trees" / "millennium.a_list"
            )
        else:
            sage_out = "../SAGE26/output/millennium"
            par = "../SAGE26/input/millennium.par"
            alist = "../SAGE26/input/millennium/trees/millennium.a_list"
        # ViSAGE's standard output folder (same convention as screenshots,
        # recordings, and exported catalogues — see docs/user_guide/launch_mode.md).
        outdir = Path.cwd() / "sage_outputs" / "lightcone"
        return _LC_RUN_SCRIPT_TEMPLATE.format(
            lightcone_dir=lc,
            sage_output_dir=sage_out,
            param_file=par,
            alist_file=alist,
            outdir=tp(outdir),
            python_exe=tp(sys.executable),
        )

    # Canonical (BAND_KEY, fsps filter name) pairs — used only to translate
    # an old-format script's space-separated SED_BANDS list onto the current
    # per-band checkboxes when migrating (see _lc_migrate_script below).
    _LC_BAND_KEYS = [
        ("BAND_GALEX_FUV_ENABLED", "galex_fuv"),
        ("BAND_GALEX_NUV_ENABLED", "galex_nuv"),
        ("BAND_SDSS_U_ENABLED", "sdss_u"),
        ("BAND_SDSS_G_ENABLED", "sdss_g"),
        ("BAND_SDSS_R_ENABLED", "sdss_r"),
        ("BAND_SDSS_I_ENABLED", "sdss_i"),
        ("BAND_SDSS_Z_ENABLED", "sdss_z"),
        ("BAND_2MASS_J_ENABLED", "2mass_j"),
        ("BAND_2MASS_H_ENABLED", "2mass_h"),
        ("BAND_2MASS_KS_ENABLED", "2mass_ks"),
        ("BAND_WISE_W1_ENABLED", "wise_w1"),
        ("BAND_WISE_W2_ENABLED", "wise_w2"),
        ("BAND_WISE_W3_ENABLED", "wise_w3"),
        ("BAND_WISE_W4_ENABLED", "wise_w4"),
    ]

    def _lc_migrate_script(self, text: str) -> str:
        """Upgrade a run_lightcone.sh saved by an older ViSAGE version to the
        current template's structure.

        The script is regenerated from scratch (correct structure, current
        defaults) and every value the user could actually have customized —
        paths, ra/dec/z, SED settings — is carried forward from the old
        text. The old space-separated SED_BANDS list (pre-checkbox) maps
        onto the new per-band checkboxes; OUTDIR only carries forward if the
        user changed it away from the old hardcoded default, since ViSAGE's
        own output-folder convention moved to sage_outputs/lightcone.

        A no-op (returns text unchanged) once the script already has every
        structural feature of the current template. Each canary marks a
        feature added over time: BAND_*_ENABLED (per-band checkboxes) and
        ``--alist`` (explicit scale-factor list passed to the SED stage, so
        relative header paths like microUchuu's still resolve). A script
        missing any of them is regenerated, carrying the user's values over.
        """
        if (
            "SURVEY_SDSS_ENABLED" in text
            and "--alist" in text
            and "SED_DUST_MODEL" in text
        ):
            return text

        old = {p["key"]: p["value"] for p in _parse_params(text, "sh")}
        fresh = self._lc_seed_script()

        carry = {
            k: old[k]
            for k in (
                "SAGE_OUTPUT_DIR",
                "PARAM_FILE",
                "ALIST_FILE",
                "KDTREE_OUT",
                "RAMIN",
                "RAMAX",
                "DECMIN",
                "DECMAX",
                "ZMIN",
                "ZMAX",
                "OUTFILE",
                "SED_ENABLED",
                "SED_FRAME",
                # SED physics switches (may be absent in older scripts).
                "SED_METALLICITY_ENABLED",
                "SED_DUST_ENABLED",
                "SED_DUST_MODEL",
                "SED_DUST2",
                "SED_DUST_EMISSION_ENABLED",
                "SED_DISK_BULGE_ENABLED",
                "SED_LINES_ENABLED",
            )
            if k in old
        }
        old_outdir = old.get("OUTDIR")
        if old_outdir and old_outdir != "./lightcone_output":
            carry["OUTDIR"] = old_outdir

        # Bands the old script asked for: a space-separated SED_BANDS list
        # (pre-checkbox) or per-band BAND_*_ENABLED checkboxes. A survey is
        # ticked if any of its bands was; surveys the old script never knew
        # keep the fresh defaults.
        from visage.sed.filters import SURVEYS

        old_bands = None
        if "SED_BANDS" in old:
            old_bands = set(old["SED_BANDS"].split())
        elif any(k in old for k, _ in self._LC_BAND_KEYS):
            old_bands = {
                f for k, f in self._LC_BAND_KEYS if old.get(k, "1") == "1"
            }
        known = {f for _, f in self._LC_BAND_KEYS}
        for key, _, filters, _ in SURVEYS:
            var = f"SURVEY_{key}_ENABLED"
            if var in old:
                carry[var] = old[var]
            elif old_bands is not None and set(filters) <= known:
                carry[var] = "1" if old_bands & set(filters) else "0"

        params = [{"key": k, "value": v} for k, v in carry.items()]
        return _apply_params(fresh, params, "sh")

    async def _step_lc_scan(self) -> None:
        await self._menu_return("sagelightcone")

    async def _step_lc_clone(self) -> None:
        self._st.wiz_step = 1
        self._emit("Choose where to clone LightSAGE:", "info")
        self._emit(
            "  A 'LightSAGE' folder will be created inside the chosen "
            "directory.",
            "info",
        )
        self._emit("", "info")
        self._st.wiz_clone_dir = str(Path.home())
        self._st.wiz_clone_dir_show = True
        self._st.flush()
        self._set_choices(
            [
                {
                    "label": "Clone Here",
                    "value": "confirm_lc_clone",
                    "icon": "mdi-git",
                    "disabled": False,
                },
                self._back_choice("lc_back_scan"),
            ]
        )

    async def _do_lc_clone(self) -> None:
        self._st.wiz_step = 1
        raw = str(self._st.wiz_clone_dir or "").strip() or str(Path.home())
        parent = Path(raw).expanduser().resolve()
        if not parent.is_dir():
            self._emit(f"Directory not found: {parent}", "err")
            self._st.wiz_clone_dir_show = True
            self._st.flush()
            self._set_choices(
                [
                    {
                        "label": "Clone Here",
                        "value": "confirm_lc_clone",
                        "icon": "mdi-git",
                        "disabled": False,
                    },
                    self._back_choice("lc_back_scan"),
                ]
            )
            return
        target = parent / "LightSAGE"
        # A re-clone lands on an existing folder: git refuses to clone into
        # one, so move it aside first (never delete — it may hold edited
        # configs or output) and say where it went.
        if target.exists():
            try:
                backup = self._move_aside(target)
            except OSError as exc:
                self._emit(f"Could not move {target} aside: {exc}", "err")
                self._set_choices([self._back_choice("lc_back_scan")])
                return
            self._emit(f"Existing checkout moved to {backup}", "warn")
        self._emit(f"Cloning LightSAGE into {target} ...", "info")
        # --recurse-submodules per the LightSAGE README (it vendors SAGE).
        rc = await self._run_cmd(
            [
                "git",
                "clone",
                "--recurse-submodules",
                _LIGHTSAGE_REPO,
                target,
            ],
            cwd=parent,
        )
        if rc != 0:
            self._emit(
                "Clone failed. Check internet connection and try again.", "err"
            )
            self._set_choices([self._back_choice("lc_back_scan")])
            return
        self._lc_dir = target
        await self._step_lc_build()

    async def _step_lc_build(self) -> None:
        self._st.wiz_step = 2
        if not self._lc_dir:
            self._emit("LightSAGE not found — clone it first.", "err")
            self._set_choices([self._back_choice("lc_back_scan")])
            return

        # Build ONLY the two tools — NOT SAGE. The repo's build_platform_aware.sh
        # would clone + compile sage-model to make test data, but ViSAGE already
        # manages SAGE (SAGE26) and feeds its HDF5 output in, so we skip it and
        # run a leaner cmake build from a ViSAGE-managed helper in ~/.visage.
        build_script = self._lc_build_script_path()
        try:
            build_script.parent.mkdir(parents=True, exist_ok=True)
            self._write_unix_text(
                build_script,
                _LC_BUILD_SCRIPT_TEMPLATE.format(
                    lc_dir=self._tc_path(self._lc_dir),
                    patch_dir=self._tc_path(_LC_PATCH_DIR),
                ),
            )
        except OSError as exc:
            self._emit(f"Could not write build helper: {exc}", "err")
            self._set_choices([self._back_choice("lc_back_scan")])
            return
        self._emit(
            "Building the LightSAGE tools only (sage2kdtree, "
            "cli_lightcone) — SAGE is not rebuilt; ViSAGE feeds SAGE26 output "
            "into the pipeline.",
            "info",
        )
        self._warn_crlf(
            [self._lc_dir / "setup.sh", self._lc_dir / "install.sh"]
        )
        self._emit("C++/CMake build — this can take a few minutes ...", "info")
        rc = await self._run_cmd(["bash", build_script], cwd=self._lc_dir)
        if rc != 0:
            self._emit(
                "Build failed. See output above (check Boost/HDF5/CMake).",
                "err",
            )
            self._set_choices(
                [
                    {
                        "label": "Configure anyway",
                        "value": "lc_configure",
                        "icon": "mdi-arrow-right",
                        "disabled": False,
                    },
                    self._back_choice("lc_back_scan"),
                ]
            )
            return
        built, tools = self._lc_built(self._lc_dir)
        if built:
            self._emit(f"Build complete!  ({', '.join(tools)})", "ok")
        else:
            self._emit(
                "Build finished but no executables found in bin/. "
                "Check the output above.",
                "warn",
            )
        await self._step_lc_config()

    async def _step_lc_config(self) -> None:
        """Edit run_lightcone.sh (both pipeline stages live in it), then run —
        mirrors the SAGE26 .par / SAGEswarm run_pso.sh editors, but the script
        is stored in ~/.visage so the LightSAGE repo is never touched."""
        self._st.wiz_step = 3
        if not self._lc_dir:
            self._emit("LightSAGE not found — clone it first.", "err")
            self._set_choices([self._back_choice("lc_back_scan")])
            return
        built, _ = self._lc_built(self._lc_dir)
        if not built:
            self._emit(
                "Note: executables not built yet — the run will fail until "
                "you build. You can still edit the script now.",
                "warn",
            )

        script = self._lc_script_path()
        try:
            script.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self._emit(f"Could not create {script.parent}: {exc}", "err")
            self._set_choices([self._back_choice("lc_back_scan")])
            return

        if script.is_file():
            try:
                self._st.wiz_lc_script_text = self._read_text(script)
                self._emit(f"Loaded {script} — edit it on the right.", "ok")
            except OSError as exc:
                self._emit(f"Could not read {script}: {exc}", "err")
                self._set_choices([self._back_choice("lc_back_scan")])
                return
            # A script saved by an older ViSAGE version can predate features
            # this one adds (e.g. per-band SED checkboxes replacing a single
            # SED_BANDS text field, or the sage_outputs/ output-folder
            # default) — regenerate its structure while carrying every
            # value the user could have customized forward. No-op once the
            # script already matches the current template.
            migrated = self._lc_migrate_script(
                str(self._st.wiz_lc_script_text)
            )
            if migrated != self._st.wiz_lc_script_text:
                self._st.wiz_lc_script_text = migrated
                self._emit(
                    "Upgraded the saved run script to the current ViSAGE "
                    "format (per-band SED checkboxes, sage_outputs/ output "
                    "folder) — your paths, ranges, and SED choices were "
                    "carried forward.",
                    "info",
                )
            # LIGHTCONE_DIR isn't a user preference like the ra/dec/z ranges —
            # it's an environment fact with exactly one correct answer. A
            # saved script can point at a checkout that no longer exists
            # (moved, deleted, or cloned under an older ViSAGE version's
            # folder-naming convention), so always resync it to the checkout
            # THIS session actually found and verified, rather than trusting
            # whatever was on disk.
            self._st.wiz_lc_script_text = _apply_params(
                str(self._st.wiz_lc_script_text),
                [
                    {
                        "key": "LIGHTCONE_DIR",
                        "value": self._tc_path(self._lc_dir),
                    }
                ],
                "sh",
            )
        else:
            self._st.wiz_lc_script_text = self._lc_seed_script()
            self._emit(f"Seeded a new run script at {script}.", "info")

        self._emit(
            "Set the SAGE output/param/a_list paths (stage 1) and the "
            "ra/dec/z ranges (stage 2), then Save & Run.",
            "info",
        )
        self._emit("", "info")
        self._show_params(str(self._st.wiz_lc_script_text or ""), "sh", "lc")
        self._st.wiz_lc_config_show = True
        self._st.flush()
        self._set_choices(
            [
                {
                    "label": "Save & Run Lightcone",
                    "value": "lc_run",
                    "icon": "mdi-play",
                    "disabled": False,
                },
                self._back_choice("lc_back_scan"),
            ]
        )

    async def _step_lc_run(self) -> None:
        self._st.wiz_step = 4
        self._sync_params_to_text()  # fold edited form values into run_lightcone.sh
        self._st.wiz_lc_config_show = False
        self._st.flush()
        if not self._lc_dir:
            self._emit("LightSAGE directory not set.", "err")
            self._set_choices([self._back_choice("lc_back_scan")])
            return

        script = self._lc_script_path()
        try:
            script.parent.mkdir(parents=True, exist_ok=True)
            self._write_unix_text(
                script, str(self._st.wiz_lc_script_text or "")
            )
            self._emit(f"Saved {script}", "ok")
        except OSError as exc:
            self._emit(f"Could not save {script}: {exc}", "err")
            self._set_choices([self._back_choice("lc_back_scan")])
            return

        self._emit("", "info")
        self._emit(
            "Running the lightcone pipeline (sage2kdtree → cli_lightcone).",
            "info",
        )
        self._emit("This can take a while.  Use Cancel to stop.", "info")
        self._emit("", "info")

        self._warn_crlf(
            [
                self._lc_dir / "scripts" / "sage2kdtree.sh",
                self._lc_dir / "scripts" / "lightcone.sh",
            ]
        )
        # Run from the script's own dir (~/.visage) so its relative outputs
        # (KDTREE_OUT, OUTDIR) land there, not inside the LightSAGE repo.
        rc = await self._run_cmd(["bash", script], cwd=script.parent)
        if rc != 0:
            self._emit(f"Lightcone pipeline exited with code {rc}.", "err")
            self._set_choices(
                [
                    {
                        "label": "Run again",
                        "value": "lc_run",
                        "icon": "mdi-replay",
                        "disabled": False,
                    },
                    self._back_choice("lc_back_scan"),
                ]
            )
            return

        self._st.wiz_step = 5
        self._emit("", "info")
        self._emit("Lightcone pipeline complete!", "ok")
        out = self._lc_output_file()
        if out is not None and out.is_file():
            self._emit(f"Lightcone written: {out}", "ok")
        self._emit(
            f"Outputs are under {script.parent} "
            "(see KDTREE_OUT / OUTDIR in the script).",
            "info",
        )
        self._set_choices(
            [
                {
                    "label": "Visualize lightcone",
                    "value": "lc_visualize",
                    "icon": "mdi-telescope",
                    "disabled": False,
                },
                {
                    "label": "Run again",
                    "value": "lc_run",
                    "icon": "mdi-replay",
                    "disabled": False,
                },
                {
                    "label": "Done",
                    "value": "lc_done",
                    "icon": "mdi-check",
                    "disabled": False,
                },
            ]
        )

    async def _launch_explore(
        self, par_path: Path, model_name: str | None = None
    ) -> None:
        name = model_name or par_path.stem
        self._st.wiz_step = 5
        self._emit("", "info")
        self._emit(f"Loading model: {name}", "title")
        # The page shows "Opening ..." and reloads itself once the new
        # ViSAGE is up (visage.js watches wiz_loading).
        self._st.wiz_loading = self._st.wiz_loading or name
        self._st.flush()
        await asyncio.sleep(1.0)

        system.relaunch_visage(
            ["--par", str(par_path), "--port", str(self._port)]
        )
