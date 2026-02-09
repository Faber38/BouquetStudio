from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import socket
import xml.etree.ElementTree as ET


@dataclass
class ReloadResult:
    ok: bool
    method: str
    detail: str


def _parse_openwebif_simplexml(xml_text: str) -> tuple[bool, str]:
    """
    Erwartet OpenWebif XML:
      <e2simplexmlresult>
        <e2state>True/False</e2state>
        <e2statetext>...</e2statetext>
      </e2simplexmlresult>
    """
    try:
        root = ET.fromstring(xml_text)
        state = (root.findtext("e2state") or "").strip().lower()
        text = (root.findtext("e2statetext") or "").strip()
        ok = state == "true"
        return ok, (text or ("ok" if ok else "failed"))
    except Exception:
        # Wenn OpenWebif mal HTML oder was anderes liefert
        return False, "Ungültige OpenWebif-Antwort (kein XML)"


def reload_enigma2(
    host: str,
    port: int,
    user: str,
    password: str,
    timeout: int = 5,
    *,
    webif_port: int = 80,
    prefer_webif: bool = True,
) -> ReloadResult:
    """
    Enigma2 "Reload" – BouquetStudio-Style (DreamboxEdit-kompatibel)

    1) Bevorzugt: OpenWebif /web/servicelistreload?mode=0
       -> lädt bouquets + lamedb neu, ohne harten GUI-Restart.
       -> Das ist bei OpenATV wichtig, weil SSH-Restarts .del erzeugen können.

    2) Fallback: SSH (killall -HUP / systemctl / init)
       -> Kann bei manchen Images/Setups dazu führen, dass bouquets.tv neu generiert wird.
    """
    # --- 1) OpenWebif (empfohlen) ---
    if prefer_webif:
        try:
            import requests

            url = f"http://{host}:{webif_port}/web/servicelistreload"
            r = requests.get(
                url,
                params={"mode": "0"},
                auth=(user, password) if user and password else None,
                timeout=timeout,
            )
            r.raise_for_status()

            ok, text = _parse_openwebif_simplexml(r.text)
            if ok:
                return ReloadResult(
                    ok=True,
                    method=f"OpenWebif servicelistreload mode=0 ({host}:{webif_port})",
                    detail=text,
                )
            else:
                # OpenWebif antwortet, aber sagt "False" oder liefert Mist
                return ReloadResult(
                    ok=False,
                    method=f"OpenWebif servicelistreload mode=0 ({host}:{webif_port})",
                    detail=text,
                )

        except Exception as e:
            # OpenWebif nicht erreichbar -> wir fallen auf SSH zurück
            webif_err = str(e)
        # weiter zu SSH-Fallback

    else:
        webif_err = "prefer_webif=False"

    # --- 2) SSH Fallback (kann bei OpenATV .del auslösen) ---
    import paramiko

    sock = socket.create_connection((host, port), timeout=timeout)
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=host,
        port=port,
        username=user,
        password=password,
        timeout=timeout,
    )

    try:
        # 2.1) Soft-Reload
        stdin, stdout, stderr = client.exec_command("killall -HUP enigma2")
        err = stderr.read().decode(errors="ignore").strip()
        if not err:
            return ReloadResult(
                ok=True,
                method="SSH Soft-Reload (killall -HUP enigma2)",
                detail=f"OK (OpenWebif vorher fehlgeschlagen: {webif_err})",
            )

        # 2.2) systemd Restart
        stdin, stdout, stderr = client.exec_command("systemctl restart enigma2")
        err2 = stderr.read().decode(errors="ignore").strip()
        if not err2:
            return ReloadResult(
                ok=True,
                method="SSH GUI-Restart (systemctl restart enigma2)",
                detail=f"OK (OpenWebif vorher fehlgeschlagen: {webif_err})",
            )

        # 2.3) Fallback (SysV)
        client.exec_command("init 4; sleep 2; init 3")
        return ReloadResult(
            ok=True,
            method="SSH GUI-Restart (init 4 / init 3)",
            detail=f"OK (OpenWebif vorher fehlgeschlagen: {webif_err})",
        )

    finally:
        client.close()
