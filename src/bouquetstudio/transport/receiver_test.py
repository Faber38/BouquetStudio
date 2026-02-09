from __future__ import annotations

import socket


def test_sftp(host: str, port: int, user: str, password: str, timeout: int = 5) -> None:
    import paramiko

    sock = socket.create_connection((host, port), timeout=timeout)
    transport = paramiko.Transport(sock)
    transport.connect(username=user, password=password)
    transport.close()


def test_ftp(host: str, port: int, user: str, password: str, timeout: int = 5) -> None:
    from ftplib import FTP

    ftp = FTP()
    ftp.connect(host, port, timeout=timeout)
    ftp.login(user, password)
    ftp.quit()
