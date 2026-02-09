from __future__ import annotations

from pathlib import Path
import socket


def download_enigma2_dir(
    host: str,
    port: int,
    user: str,
    password: str,
    remote_dir: str,
    local_dir: Path,
    timeout: int = 5,
):
    import paramiko

    local_dir.mkdir(parents=True, exist_ok=True)

    sock = socket.create_connection((host, port), timeout=timeout)
    transport = paramiko.Transport(sock)
    transport.connect(username=user, password=password)
    sftp = paramiko.SFTPClient.from_transport(transport)

    try:
        for fname in sftp.listdir(remote_dir):
            if not (
                fname == "lamedb"
                or fname.startswith("bouquets.")
                or fname.startswith("userbouquet.")
            ):
                continue

            remote_path = f"{remote_dir.rstrip('/')}/{fname}"
            local_path = local_dir / fname

            sftp.get(remote_path, str(local_path))
    finally:
        sftp.close()
        transport.close()
