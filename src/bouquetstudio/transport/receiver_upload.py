from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List
import hashlib
import socket


@dataclass
class UploadItem:
    local_path: Path
    remote_path: str
    reason: str  # "changed" / "missing_remote" / "forced (...)"


def _sha1_file_local(p: Path) -> str:
    h = hashlib.sha1()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(64 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha1_file_remote(sftp, remote_path: str) -> str:
    h = hashlib.sha1()
    with sftp.open(remote_path, "rb") as f:
        while True:
            data = f.read(64 * 1024)
            if not data:
                break
            h.update(data)
    return h.hexdigest()


def _iter_whitelist_files(local_enigma2_dir: Path) -> Iterable[Path]:
    """
    Upload-Whitelist:
      - lamedb
      - bouquets.* (bouquets.tv / bouquets.radio)
      - userbouquet.*.tv / userbouquet.*.radio
    """
    for p in sorted(local_enigma2_dir.iterdir()):
        name = p.name
        if not p.is_file():
            continue
        if name == "lamedb" or name.startswith("bouquets.") or name.startswith("userbouquet."):
            yield p


def plan_upload_sftp(
    host: str,
    port: int,
    user: str,
    password: str,
    remote_dir: str,
    local_dir: Path,
    timeout: int = 5,
) -> List[UploadItem]:
    """
    Plant den Upload:
    - Standard: Nur Dateien hochladen, die fehlen oder sich (per SHA1) unterscheiden.
    - DreamboxEdit-kompatibel (wichtig für OpenATV+ABM):
        Wenn irgendein userbouquet.* hochgeladen wird, wird bouquets.tv IMMER mit hochgeladen
        (ohne Hash-Vergleich), damit der Index sicher konsistent ist.
    """
    import paramiko

    items: List[UploadItem] = []

    sock = socket.create_connection((host, port), timeout=timeout)
    transport = paramiko.Transport(sock)
    transport.connect(username=user, password=password)
    sftp = paramiko.SFTPClient.from_transport(transport)

    try:
        for lp in _iter_whitelist_files(local_dir):
            remote_path = f"{remote_dir.rstrip('/')}/{lp.name}"

            # Existiert remote?
            try:
                sftp.stat(remote_path)
            except Exception:
                items.append(UploadItem(lp, remote_path, "missing_remote"))
                continue

            # Hash-Vergleich für "nur geänderte Dateien"
            try:
                lhash = _sha1_file_local(lp)
                rhash = _sha1_file_remote(sftp, remote_path)
                if lhash != rhash:
                    items.append(UploadItem(lp, remote_path, "changed"))
            except Exception:
                # Wenn remote lesen scheitert -> lieber hochladen
                items.append(UploadItem(lp, remote_path, "changed"))

        # --- DreamboxEdit-kompatible Regel ---
        # Wenn userbouquet.* hochgeht, muss bouquets.tv als Index sicher mit hoch.
        # UND: bouquets.tv wird dann IMMER hochgeladen (ohne Hash),
        # damit ABM/Enigma2 einen konsistenten Zustand sieht.
        any_userbouquet = any(it.local_path.name.startswith("userbouquet.") for it in items)
        if any_userbouquet:
            btv = local_dir / "bouquets.tv"
            if btv.exists():
                rp_btv = f"{remote_dir.rstrip('/')}/bouquets.tv"

                # Wenn bouquets.tv nicht bereits geplant ist, hinzufügen
                if not any(it.local_path.name == "bouquets.tv" for it in items):
                    items.append(UploadItem(btv, rp_btv, "forced (full index for userbouquet)"))
                else:
                    # Falls es schon drin ist (changed/missing), Reason auf forced anheben
                    for it in items:
                        if it.local_path.name == "bouquets.tv":
                            it.reason = "forced (full index for userbouquet)"
                            break

        return items
    finally:
        sftp.close()
        transport.close()


def upload_sftp_with_backup(
    host: str,
    port: int,
    user: str,
    password: str,
    remote_dir: str,
    local_dir: Path,
    upload_items: List[UploadItem],
    backup_suffix: str,
    timeout: int = 5,
) -> str:
    """
    Lädt nur upload_items hoch. Vorher wird jede betroffene Remote-Datei in einen Backup-Ordner kopiert:
      remote_dir/.bouquetstudio-backup-<suffix>/<filename>
    Gibt den Backup-Ordner zurück.
    """
    import paramiko

    sock = socket.create_connection((host, port), timeout=timeout)
    transport = paramiko.Transport(sock)
    transport.connect(username=user, password=password)
    sftp = paramiko.SFTPClient.from_transport(transport)

    backup_dir = f"{remote_dir.rstrip('/')}/.bouquetstudio-backup-{backup_suffix}"

    def _mkdir_if_missing(path: str) -> None:
        try:
            sftp.stat(path)
        except Exception:
            sftp.mkdir(path)

    try:
        _mkdir_if_missing(backup_dir)

        # Wichtig: bouquets.tv zuerst hochladen (Index), dann userbouquet.*
        upload_items = sorted(
            upload_items,
            key=lambda x: 0 if x.local_path.name == "bouquets.tv" else 1,
        )

        for it in upload_items:
            filename = it.local_path.name
            remote_path = it.remote_path
            backup_path = f"{backup_dir}/{filename}"

            # Backup remote -> backup_dir (stream)
            try:
                with sftp.open(remote_path, "rb") as src, sftp.open(backup_path, "wb") as dst:
                    while True:
                        data = src.read(64 * 1024)
                        if not data:
                            break
                        dst.write(data)
            except Exception:
                # wenn remote nicht existiert, ist das ok (z.B. missing_remote)
                pass

            # .del Marker entfernen, falls Enigma2 es als gelöscht markiert hat
            try:
                sftp.remove(remote_path + ".del")
            except Exception:
                pass

            # Upload (überschreibt remote)
            sftp.put(str(it.local_path), remote_path)

        return backup_dir
    finally:
        sftp.close()
        transport.close()
