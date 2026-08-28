#!/bin/bash
# One-time setup to run the EMCCD GUI on macOS.
#
# This app depends on two sibling packages that live in separate git repos
# (InstsAndQt and hsganalysis), which on the lab Windows PC are just sitting
# on PYTHONPATH somewhere. This script clones them next to this repo,
# builds a venv, installs pinned dependencies, and patches a handful of
# leftover PyQt4->PyQt5 references that break on any modern PyQt5 install.
#
# No real camera or GPIB hardware is required: the app already has fallback
# fake-device modes for both, which this setup relies on.
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARENT="$(dirname "$DIR")"

INSTLIB="$PARENT/InstrumentLibrary-yolo"
HSGTURBO="$PARENT/HSG-turbo"

if [ ! -d "$INSTLIB" ]; then
    echo "Cloning InstsAndQt (InstrumentLibrary-yolo)..."
    git clone https://github.com/SherwinGroup/InstrumentLibrary-yolo.git "$INSTLIB"
else
    echo "Found existing $INSTLIB, leaving it as-is."
fi

if [ ! -d "$HSGTURBO" ]; then
    echo "Cloning hsganalysis (HSG-turbo)..."
    git clone https://github.com/SherwinGroup/HSG-turbo.git "$HSGTURBO"
else
    echo "Found existing $HSGTURBO, leaving it as-is."
fi

echo "Creating virtualenv at $DIR/.venv..."
python3 -m venv "$DIR/.venv"
"$DIR/.venv/bin/pip" install --upgrade pip -q
"$DIR/.venv/bin/pip" install -r "$DIR/requirements.txt" -q

echo "Adding legacy 'import visa' shim (modern PyVISA only ships 'pyvisa')..."
SITE=$("$DIR/.venv/bin/python" -c "import site; print(site.getsitepackages()[0])")
cat > "$SITE/visa.py" <<'PYEOF'
"""Compatibility shim: old code does `import visa`, modern PyVISA only ships `pyvisa`."""
from pyvisa import *
from pyvisa import errors
PYEOF

echo "Patching leftover PyQt4->PyQt5 references in the two sibling repos..."
"$DIR/.venv/bin/python" "$DIR/tools/patch_pyqt5_compat.py" "$INSTLIB" "$HSGTURBO"

echo ""
echo "Setup complete. Launch the app with:"
echo "  ./EMCCD.command"
