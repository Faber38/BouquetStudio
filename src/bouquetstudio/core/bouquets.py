from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List


@dataclass
class BouquetEntry:
    service_line: str  # z.B. "#SERVICE 1:0:1:..."
    description: str = ""  # z.B. "Das Erste HD"


@dataclass
class Bouquet:
    name: str
    filename: str  # userbouquet.*.tv
    entries: List[BouquetEntry] = field(default_factory=list)


def _read_text(path: Path) -> List[str]:
    return path.read_text(encoding="utf-8", errors="ignore").splitlines()


def parse_bouquets(root: Path) -> List[Bouquet]:
    """
    Liest bouquets.tv und ermittelt die userbouquet-Dateien.
    Den Anzeigenamen holen wir aus der jeweiligen userbouquet-Datei (#NAME).
    """
    bouquets_file = root / "bouquets.tv"
    if not bouquets_file.exists():
        raise FileNotFoundError(f"bouquets.tv nicht gefunden unter: {root}")

    bouquets: List[Bouquet] = []

    for line in _read_text(bouquets_file):
        line = line.strip()
        if not line.startswith("#SERVICE"):
            continue

        # Meist: ... FROM BOUQUET "userbouquet.xyz.tv" ORDER BY ...
        if "FROM BOUQUET" not in line:
            continue

        q1 = line.find('"')
        q2 = line.find('"', q1 + 1)
        if q1 == -1 or q2 == -1:
            continue

        filename = line[q1 + 1 : q2].strip()
        if not filename.startswith("userbouquet"):
            continue

        name = _read_bouquet_name(root / filename) or filename
        bouquets.append(Bouquet(name=name, filename=filename))

    return bouquets


def _read_bouquet_name(path: Path) -> str:
    if not path.exists():
        return ""
    for line in _read_text(path):
        line = line.strip()
        if line.startswith("#NAME"):
            return line.replace("#NAME", "", 1).strip()
    return ""


def load_bouquet_entries(root: Path, bouquet: Bouquet) -> None:
    """
    Liest die userbouquet-Datei und koppelt #SERVICE mit optionalem #DESCRIPTION (Folgezeile).
    """
    path = root / bouquet.filename
    bouquet.entries.clear()

    if not path.exists():
        return

    lines = _read_text(path)
    i = 0
    while i < len(lines):
        line = lines[i].strip()

        if line.startswith("#SERVICE"):
            desc = ""
            if i + 1 < len(lines) and lines[i + 1].strip().startswith("#DESCRIPTION"):
                desc = lines[i + 1].strip().replace("#DESCRIPTION", "", 1).strip()
                i += 1  # DESCRIPTION konsumieren

            bouquet.entries.append(BouquetEntry(service_line=line, description=desc))

        i += 1
