from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple, Optional


def _normalize_ref(ref: str) -> str:
    """
    Enigma2 Service-Ref normalisieren.
    - entfernt führendes '#SERVICE'
    - trimmt spaces
    """
    ref = ref.strip()
    if ref.startswith("#SERVICE"):
        ref = ref.replace("#SERVICE", "", 1).strip()
    return ref


def _norm_sid(x: str) -> str:
    # lamedb: SID typischerweise 4-stellig Hex
    x = x.strip().upper().lstrip("0")
    return (x if x else "0").rjust(4, "0")


def _norm_ns(x: str) -> str:
    # lamedb: Namespace typischerweise 8-stellig Hex
    x = x.strip().upper().lstrip("0")
    return (x if x else "0").rjust(8, "0")


def _norm_4(x: str) -> str:
    # TSID/ONID typischerweise 4-stellig Hex
    x = x.strip().upper().lstrip("0")
    return (x if x else "0").rjust(4, "0")


def _parse_service_key(ref: str) -> Tuple[str, str, str]:
    """
    Enigma2 Ref Beispiel:
      1:0:19:SID:TSID:ONID:Namespace:0:0:0:

    Für Matching gegen lamedb nehmen wir:
      (SID, NAMESPACE, TSID)

    Warum TSID?
    Deine lamedb keys sehen aus wie: ('001F', '005A0000', '03A2')
    -> (SID, Namespace, TSID)
    """
    parts = ref.split(":")
    if len(parts) < 7:
        raise ValueError(f"Ungültige Service-Ref: {ref}")

    sid = _norm_sid(parts[3])
    tsid = _norm_4(parts[4])
    namespace = _norm_ns(parts[6])

    return sid, namespace, tsid


def load_lamedb_service_names(enigma2_dir: Path) -> Dict[Tuple[str, str, str], str]:
    """
    Liest lamedb und baut Mapping:
      (SID, NAMESPACE, TSID) -> ServiceName

    Hinweis:
    In deiner lamedb-Datei stehen in der 'services'-Sektion Zeilen wie:
      <sid>:<namespace>:<tsid>:<stype>:...
      <service name>
      <provider name>
    """
    # nur lamedb (du hast lamedb5 offenbar nicht im Testpfad)
    path = enigma2_dir / "lamedb"
    if not path.exists():
        raise FileNotFoundError(f"lamedb nicht gefunden: {path}")

    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()

    mapping: Dict[Tuple[str, str, str], str] = {}
    in_services = False
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        if line == "services":
            in_services = True
            i += 1
            continue

        if in_services:
            if line == "end":
                break

            header = line
            parts = header.split(":")
            if len(parts) >= 4:
                name = lines[i + 1].strip() if (i + 1) < len(lines) else ""

                sid = _norm_sid(parts[0])
                namespace = _norm_ns(parts[1])
                tsid = _norm_4(parts[2])

                if name:
                    mapping[(sid, namespace, tsid)] = name

                # header + name + provider überspringen
                i += 3
                continue

        i += 1

    return mapping


def resolve_service_name(
    service_line: str, lamedb_map: Dict[Tuple[str, str, str], str]
) -> Optional[str]:
    ref = _normalize_ref(service_line)

    try:
        sid, namespace, tsid = _parse_service_key(ref)
    except Exception:
        return None

    # 1) direkter Treffer
    name = lamedb_map.get((sid, namespace, tsid))
    if name:
        return name

    # DEBUG (nur wenn kein Treffer)
    print("DEBUG lamedb_map size:", len(lamedb_map))
    if lamedb_map:
        sample = list(lamedb_map.keys())[:5]
        print("DEBUG Bouquet key (SID,NS,TSID):", (sid, namespace, tsid))
        print("DEBUG lamedb sample keys:", sample)

    return None
