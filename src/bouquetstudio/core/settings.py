from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, Optional

from PySide6.QtCore import QSettings
from pathlib import Path


@dataclass
class ConnectionProfile:
    name: str
    type: str = "sftp"  # "ftp" oder "sftp"
    host: str = ""
    port: int = 22
    user: str = ""
    password: str = ""  # optional (später ggf. keyring)
    remote_path: str = "/etc/enigma2"

    def to_dict(self) -> Dict:
        d = asdict(self)
        # name steht zusätzlich im Key, aber ist praktisch als Anzeige
        return d

    @staticmethod
    def from_dict(d: Dict) -> "ConnectionProfile":
        return ConnectionProfile(
            name=str(d.get("name", "")),
            type=str(d.get("type", "sftp")),
            host=str(d.get("host", "")),
            port=int(d.get("port", 22)),
            user=str(d.get("user", "")),
            password=str(d.get("password", "")),
            remote_path=str(d.get("remote_path", "/etc/enigma2")),
        )


class AppSettings:
    """
    Speichert pro User in QSettings (INI/Native, je nach OS).
    Unter Linux typischerweise ~/.config/BouquetStudio/BouquetStudio.conf
    """

    ORG = "BouquetStudio"
    APP = "BouquetStudio"

    def __init__(self) -> None:
        self._s = QSettings(AppSettings.ORG, AppSettings.APP)

    def get_last_project_dir(self) -> str:
        return str(self._s.value("project/last_dir", "", type=str))

    def set_last_project_dir(self, path: Path | str) -> None:
        p = Path(path).expanduser()
        self._s.setValue("project/last_dir", str(p))

    # -------- Active profile --------
    def get_active_profile_name(self) -> str:
        return str(self._s.value("connections/active", "", type=str))

    def set_active_profile_name(self, name: str) -> None:
        self._s.setValue("connections/active", name)

    # -------- Profiles CRUD --------
    def list_profile_names(self) -> list[str]:
        self._s.beginGroup("connections/profiles")
        names = list(self._s.childGroups())
        self._s.endGroup()
        names.sort(key=lambda x: x.lower())
        return names

    def load_profile(self, name: str) -> Optional[ConnectionProfile]:
        if not name:
            return None
        base = f"connections/profiles/{name}"
        if not self._s.contains(f"{base}/type") and not self._s.contains(f"{base}/host"):
            return None

        data = {
            "name": name,
            "type": self._s.value(f"{base}/type", "sftp", type=str),
            "host": self._s.value(f"{base}/host", "", type=str),
            "port": int(self._s.value(f"{base}/port", 22)),
            "user": self._s.value(f"{base}/user", "", type=str),
            "password": self._s.value(f"{base}/password", "", type=str),
            "remote_path": self._s.value(f"{base}/remote_path", "/etc/enigma2", type=str),
        }
        return ConnectionProfile.from_dict(data)

    def save_profile(self, p: ConnectionProfile) -> None:
        if not p.name:
            raise ValueError("Profile name must not be empty")

        base = f"connections/profiles/{p.name}"
        self._s.setValue(f"{base}/type", p.type)
        self._s.setValue(f"{base}/host", p.host)
        self._s.setValue(f"{base}/port", int(p.port))
        self._s.setValue(f"{base}/user", p.user)
        self._s.setValue(f"{base}/password", p.password)
        self._s.setValue(f"{base}/remote_path", p.remote_path)

    def delete_profile(self, name: str) -> None:
        if not name:
            return
        self._s.beginGroup(f"connections/profiles/{name}")
        self._s.remove("")  # entfernt komplette Gruppe
        self._s.endGroup()

        # falls aktiv -> leeren
        if self.get_active_profile_name() == name:
            self.set_active_profile_name("")

    def rename_profile(self, old_name: str, new_name: str) -> None:
        if not old_name or not new_name or old_name == new_name:
            return

        p = self.load_profile(old_name)
        if p is None:
            return

        # Ziel darf nicht existieren (sonst überschreiben wir unabsichtlich)
        if self.load_profile(new_name) is not None:
            raise ValueError(f'Profile "{new_name}" already exists')

        p.name = new_name
        self.save_profile(p)
        self.delete_profile(old_name)

        if self.get_active_profile_name() == old_name:
            self.set_active_profile_name(new_name)
