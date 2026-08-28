#!/bin/bash
# macOS equivalent of EMCCD.bat. Double-click in Finder, or run ./EMCCD.command
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

PARENT="$(dirname "$DIR")"
INSTLIB="$PARENT/InstrumentLibrary-yolo"
HSGTURBO="$PARENT/HSG-turbo"

if [ ! -x "$DIR/.venv/bin/python" ] || [ ! -d "$INSTLIB" ] || [ ! -d "$HSGTURBO" ]; then
    echo "Setup hasn't been run yet."
    echo "Run ./setup_mac.sh once first, then re-run this script."
    read -n 1 -s -r -p "Press any key to close..."
    echo ""
    exit 1
fi

export PYTHONPATH="$INSTLIB:$HSGTURBO"
"$DIR/.venv/bin/python" "$DIR/__main__.py"

read -n 1 -s -r -p "Press any key to close..."
echo ""
