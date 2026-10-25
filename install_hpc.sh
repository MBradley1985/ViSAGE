#!/usr/bin/env bash
# install_hpc.sh — create a Python venv and install ViSAGE into it.
#
# Usage:
#   ./install_hpc.sh [VENV_DIR]
#
# VENV_DIR defaults to .venv inside the repo.
# On clusters with a module system, load Python before running:
#
#   module load python/3.12.0        # adjust to your cluster's module name
#   ./install_hpc.sh /scratch/$USER/visage-env
#
# Subsequent sessions only need:
#   source <VENV_DIR>/bin/activate
#   visage --par /path/to/millennium.par
#
# Or without activating:
#   <VENV_DIR>/bin/visage --par /path/to/millennium.par

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${1:-$SCRIPT_DIR/.venv}"
PYTHON="${PYTHON:-python3}"

# ── 1. Locate Python ───────────────────────────────────────────────────────
if ! command -v "$PYTHON" &>/dev/null; then
    echo "ERROR: '$PYTHON' not found."
    echo "       Load a Python module first, e.g.:"
    echo "         module load python/3.12.0"
    echo "       or set PYTHON=/path/to/python3 before running this script."
    exit 1
fi

PY_MAJOR=$("$PYTHON" -c "import sys; print(sys.version_info.major)")
PY_MINOR=$("$PYTHON" -c "import sys; print(sys.version_info.minor)")
PY_VER="${PY_MAJOR}.${PY_MINOR}"

if [[ "$PY_MAJOR" -lt 3 || ( "$PY_MAJOR" -eq 3 && "$PY_MINOR" -lt 11 ) ]]; then
    echo "ERROR: Python >= 3.11 required (found $PY_VER)."
    exit 1
fi

echo "Python $PY_VER — $("$PYTHON" -c 'import sys; print(sys.executable)')"

# ── 2. Create venv ─────────────────────────────────────────────────────────
if [[ ! -d "$VENV_DIR" ]]; then
    echo "Creating venv at $VENV_DIR ..."
    "$PYTHON" -m venv "$VENV_DIR"
else
    echo "Venv already exists at $VENV_DIR — reusing."
fi

# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"

# ── 3. Upgrade pip ─────────────────────────────────────────────────────────
echo "Upgrading pip ..."
pip install --quiet --upgrade pip

# ── 4. Install ViSAGE (editable so git pull = instant update) ─────────
echo "Installing ViSAGE from $SCRIPT_DIR ..."
pip install -e "$SCRIPT_DIR"

# ── 5. Check for ffmpeg (MOV recording only) ───────────────────────────────
echo ""
if command -v ffmpeg &>/dev/null; then
    echo "ffmpeg found: $(command -v ffmpeg)"
else
    echo "NOTE: ffmpeg not found — MOV recording will be unavailable."
    echo "      Load it if needed:  module load ffmpeg"
fi

# ── 6. Summary ─────────────────────────────────────────────────────────────
echo ""
echo "Done.  To use ViSAGE:"
echo ""
echo "  # Activate the environment:"
echo "  source $VENV_DIR/bin/activate"
echo "  visage --par /path/to/millennium.par"
echo ""
echo "  # Or run directly without activating:"
echo "  $VENV_DIR/bin/visage --par /path/to/millennium.par"
echo ""
echo "  # To update after a git pull:"
echo "  git pull && pip install -e $SCRIPT_DIR   # re-run only if pyproject.toml changed"
