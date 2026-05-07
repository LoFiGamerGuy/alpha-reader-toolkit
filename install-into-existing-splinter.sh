#!/bin/bash
# install-into-existing-splinter.sh
#
# Refresh toolkit-canonical files in an existing splinter project.
# Copies orchestrator + analyzer + auth_probe + personas-snapshot.
# Does NOT touch: book_config.yaml, manuscript/, runs/, kickoffs/, .env, CLAUDE.md
#
# Usage: bash install-into-existing-splinter.sh /path/to/existing-splinter

set -e

if [ -z "$1" ]; then
    echo "Usage: $0 <path-to-existing-splinter>"
    echo ""
    echo "Refreshes toolkit-canonical files in an existing splinter project:"
    echo "  - orchestrator/run-alpha-reader.py"
    echo "  - orchestrator/readability_analyzer.py"
    echo "  - orchestrator/auth_probe.py"
    echo "  - references/personas-snapshot-v0.4.md"
    echo ""
    echo "Does NOT touch: book_config.yaml, manuscript/, runs/, kickoffs/, .env, CLAUDE.md"
    exit 1
fi

SPLINTER="$1"
TOOLKIT_ROOT="$(cd "$(dirname "$0")" && pwd)"

if [ ! -d "$SPLINTER" ]; then
    echo "[FAIL] splinter dir does not exist: $SPLINTER"
    exit 2
fi

if [ ! -f "$SPLINTER/book_config.yaml" ]; then
    echo "[WARN] $SPLINTER/book_config.yaml does not exist."
    echo "       This splinter may have been scaffolded with the pre-toolkit pattern (hardcoded BOOK in orchestrator)."
    echo "       After install, you'll need to write book_config.yaml manually — see toolkit's templates/book_config.yaml.template"
    echo ""
    read -p "Continue? [y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "[abort]"
        exit 0
    fi
fi

mkdir -p "$SPLINTER/orchestrator" "$SPLINTER/references"

echo "[install] $TOOLKIT_ROOT/orchestrator/run-alpha-reader.py"
cp "$TOOLKIT_ROOT/orchestrator/run-alpha-reader.py" "$SPLINTER/orchestrator/run-alpha-reader.py"

echo "[install] $TOOLKIT_ROOT/orchestrator/readability_analyzer.py"
cp "$TOOLKIT_ROOT/orchestrator/readability_analyzer.py" "$SPLINTER/orchestrator/readability_analyzer.py"

echo "[install] $TOOLKIT_ROOT/orchestrator/auth_probe.py"
cp "$TOOLKIT_ROOT/orchestrator/auth_probe.py" "$SPLINTER/orchestrator/auth_probe.py"

echo "[install] $TOOLKIT_ROOT/references/personas-snapshot-v0.4.md"
cp "$TOOLKIT_ROOT/references/personas-snapshot-v0.4.md" "$SPLINTER/references/personas-snapshot-v0.4.md"

echo ""
echo "INSTALL COMPLETE."
echo ""
echo "  Splinter: $SPLINTER"
echo "  Toolkit:  $TOOLKIT_ROOT"
echo ""
echo "Next steps:"
echo "  - If book_config.yaml does not exist, create it from $TOOLKIT_ROOT/templates/book_config.yaml.template"
echo "  - Verify with: cd $SPLINTER && py -3.14 orchestrator/auth_probe.py"
echo ""
