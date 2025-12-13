# BouquetStudio

BouquetStudio ist ein Desktop-Editor für Enigma2-Bouquets  
(Linux-first, später Windows-Build).

## Features (Work in Progress)
- Anzeige von Enigma2-Bouquets
- Parser für `bouquets.tv` und `userbouquet.*`
- Anzeige von Sendernamen (`#DESCRIPTION`)
- Qt-Desktop-UI (PySide6)

## Development
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=src python app.py
