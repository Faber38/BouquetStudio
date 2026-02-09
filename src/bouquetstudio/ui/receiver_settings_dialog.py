from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QComboBox,
    QSpinBox,
    QMessageBox,
)

from bouquetstudio.core.settings import AppSettings, ConnectionProfile
from bouquetstudio.transport.receiver_test import test_sftp, test_ftp


class ReceiverSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Receiver – Verbindungseinstellungen")
        self.resize(420, 300)

        self.settings = AppSettings()

        layout = QVBoxLayout(self)

        # Profil-Auswahl
        hl = QHBoxLayout()
        hl.addWidget(QLabel("Profil:"))
        self.profile_combo = QComboBox()
        hl.addWidget(self.profile_combo)
        self.btn_new = QPushButton("Neu")
        self.btn_delete = QPushButton("Löschen")
        hl.addWidget(self.btn_new)
        hl.addWidget(self.btn_delete)
        layout.addLayout(hl)

        # Typ
        self.type_combo = QComboBox()
        self.type_combo.addItems(["sftp", "ftp"])
        layout.addWidget(QLabel("Typ:"))
        layout.addWidget(self.type_combo)

        # Host
        self.host_edit = QLineEdit()
        layout.addWidget(QLabel("Host / IP:"))
        layout.addWidget(self.host_edit)

        # Port
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(22)
        layout.addWidget(QLabel("Port:"))
        layout.addWidget(self.port_spin)

        # User
        self.user_edit = QLineEdit()
        layout.addWidget(QLabel("Benutzer:"))
        layout.addWidget(self.user_edit)

        # Passwort
        self.pass_edit = QLineEdit()
        self.pass_edit.setEchoMode(QLineEdit.Password)
        layout.addWidget(QLabel("Passwort:"))
        layout.addWidget(self.pass_edit)

        # Remote Pfad
        self.path_edit = QLineEdit("/etc/enigma2")
        layout.addWidget(QLabel("Remote-Pfad:"))
        layout.addWidget(self.path_edit)
        self.btn_test = QPushButton("Verbindung testen")
        layout.addWidget(self.btn_test)

        # Buttons
        bl = QHBoxLayout()
        bl.addStretch()
        self.btn_save = QPushButton("Speichern")
        self.btn_close = QPushButton("Schließen")
        bl.addWidget(self.btn_save)
        bl.addWidget(self.btn_close)
        layout.addLayout(bl)

        # Signals
        self.btn_close.clicked.connect(self.reject)
        self.btn_save.clicked.connect(self.save_profile)
        self.btn_new.clicked.connect(self.new_profile)
        self.btn_delete.clicked.connect(self.delete_profile)
        self.profile_combo.currentTextChanged.connect(self.load_profile)
        self.btn_test.clicked.connect(self.test_connection)

        self.reload_profiles()

    # ---------- Logic ----------

    def reload_profiles(self):
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()

        names = self.settings.list_profile_names()
        self.profile_combo.addItems(names)

        active = self.settings.get_active_profile_name()
        if active in names:
            self.profile_combo.setCurrentText(active)

        self.profile_combo.blockSignals(False)

        if self.profile_combo.currentText():
            self.load_profile(self.profile_combo.currentText())

    def load_profile(self, name: str):
        p = self.settings.load_profile(name)
        if not p:
            return

        self.type_combo.setCurrentText(p.type)
        self.host_edit.setText(p.host)
        self.port_spin.setValue(p.port)
        self.user_edit.setText(p.user)
        self.pass_edit.setText(p.password)
        self.path_edit.setText(p.remote_path)

    def save_profile(self):
        name = self.profile_combo.currentText().strip()
        if not name:
            QMessageBox.warning(self, "Fehler", "Profilname fehlt.")
            return

        p = ConnectionProfile(
            name=name,
            type=self.type_combo.currentText(),
            host=self.host_edit.text().strip(),
            port=self.port_spin.value(),
            user=self.user_edit.text().strip(),
            password=self.pass_edit.text(),
            remote_path=self.path_edit.text().strip() or "/etc/enigma2",
        )

        self.settings.save_profile(p)
        self.settings.set_active_profile_name(name)
        self.reload_profiles()

    def new_profile(self):
        base = "Receiver"
        i = 1
        names = set(self.settings.list_profile_names())
        name = f"{base}{i}"
        while name in names:
            i += 1
            name = f"{base}{i}"

        self.profile_combo.addItem(name)
        self.profile_combo.setCurrentText(name)

    def delete_profile(self):
        name = self.profile_combo.currentText()
        if not name:
            return

        if (
            QMessageBox.question(self, "Löschen", f'Profil "{name}" wirklich löschen?')
            == QMessageBox.Yes
        ):
            self.settings.delete_profile(name)
            self.reload_profiles()

    def test_connection(self):
        host = self.host_edit.text().strip()
        port = self.port_spin.value()
        user = self.user_edit.text().strip()
        password = self.pass_edit.text()
        typ = self.type_combo.currentText()

        if not host or not user:
            QMessageBox.warning(self, "Fehler", "Host und Benutzer müssen gesetzt sein.")
            return

        try:
            if typ == "sftp":
                test_sftp(host, port, user, password)
            else:
                test_ftp(host, port, user, password)

            QMessageBox.information(self, "Verbindung OK", f"{typ.upper()}-Verbindung erfolgreich.")

        except Exception as e:
            QMessageBox.critical(
                self, "Verbindung fehlgeschlagen", f"{typ.upper()}-Test fehlgeschlagen:\n\n{e}"
            )
