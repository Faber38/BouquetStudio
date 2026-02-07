#!/usr/bin/env bash
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

echo "▶ BouquetStudio starten…"

# 1. venv anlegen, falls sie fehlt
if [ ! -d ".venv" ]; then
    echo "📦 Virtuelle Umgebung wird erstellt…"
    python3 -m venv .venv
fi

# 2. venv aktivieren
source .venv/bin/activate

# 3. Abhängigkeiten installieren (aus pyproject.toml)
echo "📦 Abhängigkeiten prüfen…"
pip install -U pip >/dev/null
pip install PySide6 paramiko >/dev/null

# 4. App starten
echo "🚀 Starte BouquetStudio"
PYTHONPATH=src python app.py
