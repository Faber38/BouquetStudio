from __future__ import annotations

from pathlib import Path
from datetime import datetime
import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QListWidget,
    QLineEdit,
    QVBoxLayout,
    QLabel,
    QMessageBox,
    QFileDialog,
    QApplication,
    QListWidgetItem,
    QPushButton,
    QComboBox,
    QInputDialog,
    QDialog,
    QTextBrowser,
    QFrame,
)

from bouquetstudio.core.bouquets import parse_bouquets, load_bouquet_entries
from bouquetstudio import __app_name__, __version__, __author__
from bouquetstudio.core.lamedb import load_lamedb_service_names, resolve_service_name
from bouquetstudio.ui.target_list import TargetListWidget
from bouquetstudio.ui.receiver_settings_dialog import ReceiverSettingsDialog
from bouquetstudio.transport.receiver_download import download_enigma2_dir
from bouquetstudio.core.settings import AppSettings
from bouquetstudio.transport.receiver_upload import plan_upload_sftp, upload_sftp_with_backup
from bouquetstudio.transport.receiver_reload import reload_enigma2
from bouquetstudio.ui.help_text import HELP_TEXT

# Optional: simples Logging-Setup (Konsole)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("BouquetStudio")


def _is_marker_service(service_line: str) -> bool:
    s = (service_line or "").strip()
    if s.startswith("#SERVICE"):
        s = s.replace("#SERVICE", "", 1).strip()

    parts = s.split(":")
    if len(parts) < 2:
        return False

    service_type = parts[1]
    return service_type in ("64", "832")


def _get_bouquet_file_path(enigma2_dir: Path, bouquet) -> Path:
    """
    Robust: versucht mehrere mögliche Attribute aus parse_bouquets().
    Passe ggf. an deine Bouquet-Klasse an (name, filename, path, file, etc.).
    """
    for attr in ("path", "file_path", "filename", "file", "fname"):
        if hasattr(bouquet, attr):
            val = getattr(bouquet, attr)
            if val:
                p = Path(val)
                if not p.is_absolute():
                    p = enigma2_dir / p
                return p

    raise RuntimeError(
        "Bouquet hat keinen Dateipfad (path/filename/...) – bitte parse_bouquets prüfen."
    )


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BouquetStudio – Enigma2 Bouquet Editor")
        self.resize(1200, 700)

        # Workspace
        self.workspace_root: Path | None = None
        self.project_dir: Path | None = None  # ✅ stabiler Projektanker

        self.bouquets_data = []
        self.lamedb_map = {}

        # ✅ Ziel / Quelle getrennt
        self._current_bouquet = None  # Ziel-Bouquet (rechts / wird gespeichert)
        self._source_bouquet = None  # Quelle-Bouquet (Mitte)

        # ✅ Dirty tracking
        self._dirty_bouquet_names: set[int] = set()
        self._dirty_bouquet_content: set[int] = set()
        self._dirty_bouquet_order = False

        # ✅ verhindert Dirty beim programmgesteuerten Befüllen/Löschen
        self._suppress_dirty = False

        # Default-Testpfad
        self.test_root = Path.home() / "BouquetTest" / "etc" / "enigma2"

        # UI
        root = QWidget()
        self.setCentralWidget(root)
        self.setStyleSheet(
            self.styleSheet()
            + """
        /* Menüleiste */
        QMenuBar {
            background: #eef3ff;
            border-bottom: 1px solid #b8c6e6;
            padding: 4px;
        }
        QMenuBar::item {
            background: transparent;
            padding: 6px 10px;
            border-radius: 6px;
            margin: 0px 2px;
        }
        QMenuBar::item:selected {
            background: #d7e3ff;
        }
        QMenuBar::item:pressed {
            background: #c6d8ff;
        }

        /* Dropdown-Menüs */
        QMenu {
            background: white;
            border: 1px solid #b8c6e6;
            border-radius: 8px;
            padding: 6px;
        }
        QMenu::item {
            padding: 7px 24px;
            border-radius: 6px;
        }
        QMenu::item:selected {
            background: #2b6cff;
            color: white;
        }
        QMenu::separator {
            height: 1px;
            background: #e0e6f5;
            margin: 6px 10px;
        }
        """
        )

        main = QHBoxLayout(root)

        # ---------------------------------------------------------------------
        # Left (Ziel-Bouquets)
        # ---------------------------------------------------------------------
        left_panel = QFrame()
        left_panel.setObjectName("leftPanel")

        left_panel.setStyleSheet(
            """
            QFrame#leftPanel {
                background-color: #eef3ff;          /* leichtes blau-grau */
                border-right: 1px solid #b8c6e6;     /* passend zur Fläche */
            }
        """
        )

        left = QVBoxLayout(left_panel)
        left.setContentsMargins(8, 8, 8, 8)
        left.setSpacing(6)

        left_title = QLabel("Bouquets (Ziel)")
        left_title.setStyleSheet(
            """
            QLabel {
                font-weight: bold;
                padding: 6px 8px;
                background-color: #d7e3ff;   /* Kopfzeile */
                border: 1px solid #b8c6e6;
                border-radius: 6px;
            }
        """
        )

        left.addWidget(left_title)

        self.bouquets = QListWidget()
        self.bouquets.setStyleSheet(
            """
            QListWidget {
                background: white;
                border: 1px solid #c9d3ea;
                border-radius: 6px;
                padding: 4px;
                outline: 0;
            }
            QListWidget::item {
                padding: 6px;
                border-radius: 4px;
            }
            QListWidget::item:hover {
                background: #e6ecff;   /* dezentes Hover-Blau */
            }
            QListWidget::item:selected {
                background: #2b6cff;
                color: white;
            }
        """
        )

        self.bouquets.setFrameShape(QFrame.NoFrame)
        self.bouquets.setEditTriggers(
            QListWidget.EditTrigger.DoubleClicked | QListWidget.EditTrigger.EditKeyPressed
        )
        # Bouquets links: Reihenfolge per Drag&Drop ändern
        self.bouquets.setDragEnabled(True)
        self.bouquets.setAcceptDrops(True)
        self.bouquets.setDropIndicatorShown(True)
        self.bouquets.setDragDropMode(QListWidget.DragDropMode.InternalMove)

        # ✅ Mehrfachauswahl (Ctrl/Shift)
        self.bouquets.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)

        self.bouquets.model().rowsMoved.connect(self._on_bouquet_order_changed)

        left.addWidget(self.bouquets)

        self.add_bouquet_btn = QPushButton("➕ Bouquet hinzufügen")
        self.add_bouquet_btn.setObjectName("primaryButton")
        self.add_bouquet_btn.setStyleSheet(
            """
            QPushButton#primaryButton {
                background-color: #e6f6ea;
                border: 1px solid #b9e3c4;
                color: #1f5a2e;
                border-radius: 6px;
                padding: 6px 10px;
                font-weight: bold;
            }
            QPushButton#primaryButton:hover {
                background-color: #d6f0dd;
            }
            """
        )

        self.add_bouquet_btn.setToolTip("Neues TV-Bouquet anlegen und in bouquets.tv eintragen")
        self.add_bouquet_btn.clicked.connect(self.action_add_new_bouquet)
        left.addWidget(self.add_bouquet_btn)

        # ✅ NEU: Bouquet entfernen
        self.remove_bouquet_btn = QPushButton("🗑️ Bouquet entfernen")
        self.remove_bouquet_btn.setObjectName("dangerButton")
        self.remove_bouquet_btn.setStyleSheet(
            """
            QPushButton#dangerButton {
                background-color: #fde8e8;
                border: 1px solid #e29a9a;
                color: #8a1f1f;
                border-radius: 6px;
                padding: 6px 10px;
                font-weight: bold;
            }
            QPushButton#dangerButton:hover {
                background-color: #fbd6d6;
            }
            """
        )

        left.addWidget(self.remove_bouquet_btn)

        # ✅ WICHTIG: Button mit Action verbinden
        self.remove_bouquet_btn.clicked.connect(self.action_remove_bouquet)

        # ---------------------------------------------------------------------
        # Middle (Quelle)
        # ---------------------------------------------------------------------
        mid = QVBoxLayout()
        mid_title = QLabel("Sender / Einträge (Quelle)")
        mid_title.setStyleSheet(
            """
            QLabel {
                font-weight: bold;
                padding: 6px 8px;
                background-color: #eeeeee;
                border: 1px solid #d0d0d0;
                border-radius: 6px;
                color: #333333;
            }
            """
        )
        mid.addWidget(mid_title)

        mid.addWidget(QLabel("Quelle:"))
        self.source_combo = QComboBox()
        mid.addWidget(self.source_combo)

        from bouquetstudio.ui.draggable_list import BlockMoveListWidget

        self.entries = BlockMoveListWidget()
        self.entries.setStyleSheet(
            """
            QListWidget {
                background: #f7f7f7;
                border: 1px solid #d0d0d0;
                border-radius: 6px;
                padding: 4px;
            }
            QListWidget::item {
                padding: 6px;
            }
            QListWidget::item:selected {
                background: #e0e0e0;
                color: black;
            }
            """
        )

        # Quelle: nur Drag, keine Drops (kein internes Verschieben -> Bug umgangen)
        self.entries.setDragEnabled(True)
        self.entries.setAcceptDrops(False)

        mid.addWidget(self.entries, 1)

        # ---------------------------------------------------------------------
        # Right (Ziel)
        # ---------------------------------------------------------------------
        right_panel = QFrame()
        right_panel.setObjectName("rightPanel")
        right_panel.setStyleSheet(
            """
            QFrame#rightPanel {
                background-color: #eef3ff;
                border-left: 1px solid #b8c6e6;
            }
            """
        )

        right = QVBoxLayout(right_panel)
        right.setContentsMargins(8, 8, 8, 8)
        right.setSpacing(6)
        right_title_search = QLabel("Suche")
        right_title_search.setStyleSheet(
            """
            QLabel {
                font-weight: bold;
                padding: 6px 8px;
                background-color: #eeeeee;
                border: 1px solid #d0d0d0;
                border-radius: 6px;
                color: #333333;
            }
            """
        )
        right.addWidget(right_title_search)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Sender suchen…")
        right.addWidget(self.search)

        right.addSpacing(10)
        right_title_target = QLabel("Neue Reihenfolge (Ziel)")
        right_title_target.setStyleSheet(
            """
            QLabel {
                font-weight: bold;
                padding: 6px 8px;
                background-color: #eeeeee;
                border: 1px solid #d0d0d0;
                border-radius: 6px;
                color: #333333;
            }
            """
        )
        right.addWidget(right_title_target)

        # 💾 Speichern-Button
        self.save_target_btn = QPushButton("💾 Bouquet speichern")
        self.save_target_btn.setToolTip("Aktuelles Ziel-Bouquet speichern")
        self.save_target_btn.clicked.connect(self.action_save_project)
        right.addWidget(self.save_target_btn, alignment=Qt.AlignRight)

        # ➕ Marker / Zeile hinzufügen (Überschrift)
        self.add_line_btn = QPushButton("➕ Zeile hinzufügen")
        self.add_line_btn.setToolTip(
            "Fügt einen Marker (Überschrift/Trenner) in die Ziel-Liste ein"
        )
        self.add_line_btn.clicked.connect(self.action_add_target_line)
        right.addWidget(self.add_line_btn, alignment=Qt.AlignRight)
        self.target = TargetListWidget()
        self.target.setStyleSheet(
            """
            QListWidget {
                background: white;
                border: 1px solid #c9d3ea;
                border-radius: 6px;
                padding: 4px;
                outline: 0;
            }
            QListWidget::item {
                padding: 6px;
                border-radius: 4px;
            }
            QListWidget::item:hover {
                background: #e6ecff;
            }
            QListWidget::item:selected {
                background: #2b6cff;
                color: white;
            }
            """
        )

        right.addWidget(self.target, 1)
        # 📌 Doppelklick: Marker/Überschrift per Dialog ändern
        self.target.itemDoubleClicked.connect(self._edit_target_marker_dialog)

        # ✅ Änderungen in der Ziel-Liste (rechts) als "dirty" markieren
        m = self.target.model()
        m.rowsInserted.connect(self._on_target_changed)
        m.rowsRemoved.connect(self._on_target_changed)
        m.rowsMoved.connect(self._on_target_changed)
        m.dataChanged.connect(self._on_target_changed)

        hint = QLabel("Tipp: Ziel-Liste sortieren per Drag&Drop • Entf löscht Einträge")
        hint.setStyleSheet("color: gray;")
        right.addWidget(hint)

        main.addWidget(left_panel, 1)
        main.addLayout(mid, 2)
        main.addWidget(right_panel, 2)

        self._build_menu()

        # Statusbar: Receiver-Profil + Projektpfad
        self._receiver_label = QLabel("")
        self._receiver_label.setStyleSheet("color: gray; font-weight: bold;")
        self.statusBar().addPermanentWidget(self._receiver_label)

        self._path_label = QLabel("")
        self._path_label.setStyleSheet("color: gray;")
        self.statusBar().addPermanentWidget(self._path_label, 1)
        from bouquetstudio import __version__

        self._version_label = QLabel(f"v{__version__}")
        self._version_label.setStyleSheet("color: gray;")
        self.statusBar().addPermanentWidget(self._version_label)
        self.setWindowTitle(f"BouquetStudio v{__version__} – {self.project_dir}")

        # ---------------------------------------------------------------------
        # Signals
        # ---------------------------------------------------------------------
        self.bouquets.currentRowChanged.connect(self._on_target_bouquet_selected)
        self.bouquets.itemChanged.connect(self._on_bouquet_name_changed)

        self.source_combo.currentIndexChanged.connect(self._on_source_bouquet_selected)
        self.search.textChanged.connect(self._filter_entries)

        # Initial load: zuletzt verwendetes Projekt, sonst Test-Pfad, sonst leer
        s = AppSettings()
        last = Path(s.get_last_project_dir()) if s.get_last_project_dir() else None

        if last and last.exists():
            self.project_dir = last
            self.open_project_dir(last)
        elif self.test_root.exists():
            self.project_dir = self.test_root
            self.open_project_dir(self.test_root)
        else:
            self._dbg("Start: kein Projekt gefunden – bitte 'Datei → Projekt öffnen…' wählen")

    # -------------------------------------------------------------------------
    # Debug
    # -------------------------------------------------------------------------
    def _dbg(self, msg: str):
        log.info(msg)
        print(f"[BouquetStudio] {msg}")
        try:
            self.statusBar().showMessage(msg, 5000)
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # Menü
    # -------------------------------------------------------------------------
    def _build_menu(self):
        menubar = self.menuBar()

        # Datei
        m_file = menubar.addMenu("Datei")

        a_open = m_file.addAction("Projekt öffnen…")
        a_open.setShortcut("Ctrl+O")
        a_open.triggered.connect(self.action_open_project)

        a_save = m_file.addAction("Aktuelles Bouquet speichern")
        a_save.setShortcut("Ctrl+S")
        a_save.triggered.connect(self.action_save_project)

        a_save_all = m_file.addAction("Alle Bouquets speichern")
        a_save_all.setShortcut("Ctrl+Shift+S")
        a_save_all.triggered.connect(self.action_save_all_bouquets)

        m_file.addSeparator()

        a_exit = m_file.addAction("Beenden")
        a_exit.setShortcut("Ctrl+Q")
        a_exit.triggered.connect(QApplication.instance().quit)

        # Receiver (Platzhalter-Menü)
        m_rx = menubar.addMenu("Receiver")

        a_rx_settings = m_rx.addAction("Verbindungseinstellungen…")
        a_rx_settings.triggered.connect(self.action_receiver_settings)

        a_rx_connect = m_rx.addAction("Verbinden…")
        a_rx_connect.triggered.connect(self.action_receiver_connect)

        m_rx.addSeparator()

        a_rx_download = m_rx.addAction("Bouquets herunterladen")
        a_rx_download.triggered.connect(self.action_receiver_download)

        a_rx_upload = m_rx.addAction("Bouquets hochladen")
        a_rx_upload.triggered.connect(self.action_receiver_upload)

        m_rx.addSeparator()

        a_rx_reload = m_rx.addAction("Enigma2 neu laden / GUI restart")
        a_rx_reload.triggered.connect(self.action_receiver_reload)

        # Hilfe
        m_help = menubar.addMenu("Hilfe")

        a_help = m_help.addAction("Bedienung")
        a_help.triggered.connect(self.action_show_help)

        m_help.addSeparator()

        a_about = m_help.addAction("Über…")
        a_about.triggered.connect(self.action_about)

    # -------------------------------------------------------------------------
    # Dirty-Warnung beim Schließen
    # -------------------------------------------------------------------------
    def closeEvent(self, event):
        if self._dirty_bouquet_names or self._dirty_bouquet_content or self._dirty_bouquet_order:

            res = QMessageBox.question(
                self,
                "Ungespeicherte Änderungen",
                "Es gibt ungespeicherte Änderungen.\n\nTrotzdem beenden?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if res != QMessageBox.Yes:
                event.ignore()
                return
        event.accept()

    # -------------------------------------------------------------------------
    # Datei-Aktionen
    # -------------------------------------------------------------------------
    def action_open_project(self):
        # ✅ wenn dirty -> nachfragen
        if self._dirty_bouquet_names or self._dirty_bouquet_content:
            res = QMessageBox.question(
                self,
                "Ungespeicherte Änderungen",
                "Es gibt ungespeicherte Änderungen.\n\nProjekt trotzdem wechseln?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if res != QMessageBox.Yes:
                self._dbg("Projekt öffnen: abgebrochen (ungespeicherte Änderungen)")
                return

        start_dir = str(self.workspace_root) if self.workspace_root else str(Path.home())
        folder = QFileDialog.getExistingDirectory(
            self,
            "Enigma2 Projektordner wählen (enthält lamedb, bouquets.tv, userbouquet.*)",
            start_dir,
        )
        if not folder:
            self._dbg("Projekt öffnen: abgebrochen")
            return

        self.project_dir = Path(folder)
        self._set_path_in_statusbar(self.project_dir)

        self.workspace_root = self.project_dir
        AppSettings().set_last_project_dir(self.project_dir)

        self.setWindowTitle(f"BouquetStudio – {self.project_dir}")
        self._dbg(f"Projekt öffnen: {self.project_dir}")

        self.open_project_dir(self.project_dir)

    def action_show_help(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("BouquetStudio – Bedienung")
        dlg.resize(800, 600)

        layout = QVBoxLayout(dlg)

        view = QTextBrowser()
        view.setHtml(HELP_TEXT)
        view.setOpenExternalLinks(True)
        layout.addWidget(view)

        btn_close = QPushButton("Schließen")
        btn_close.clicked.connect(dlg.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignRight)

        dlg.setLayout(layout)
        dlg.exec()

    def action_add_new_bouquet(self):
        if not self.workspace_root:
            QMessageBox.warning(self, "Bouquet hinzufügen", "Kein Projektordner geöffnet.")
            return

        name, ok = QInputDialog.getText(self, "Bouquet hinzufügen", "Name des neuen Bouquets:")
        if not ok:
            return

        name = (name or "").strip()
        if not name:
            QMessageBox.warning(self, "Bouquet hinzufügen", "Name darf nicht leer sein.")
            return

        # Ziel-Dateiname (stabil, ohne Sonderzeichen)
        def slugify(s: str) -> str:
            s = s.strip().lower()
            s = s.replace(" ", "_")
            s = "".join(ch for ch in s if ch.isalnum() or ch in ("_", "-"))
            return s or "bouquet"

        slug = slugify(name)
        filename = f"userbouquet.bouquetstudio_{slug}.tv"
        userbouquet_path = self.workspace_root / filename

        # Kollisionen vermeiden
        n = 2
        while userbouquet_path.exists():
            filename = f"userbouquet.bouquetstudio_{slug}_{n}.tv"
            userbouquet_path = self.workspace_root / filename
            n += 1

        bouquets_tv = self.workspace_root / "bouquets.tv"
        if not bouquets_tv.exists():
            QMessageBox.critical(self, "Bouquet hinzufügen", f"Nicht gefunden: {bouquets_tv}")
            return

        # 1) userbouquet-Datei anlegen (minimal, Enigma2-konform)
        with open(userbouquet_path, "w", encoding="utf-8", errors="ignore", newline="\r\n") as f:
            f.write(f"#NAME {name}\n")

        # 2) In bouquets.tv eintragen
        svc_line = f'#SERVICE 1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "{filename}" ORDER BY bouquet'
        desc_line = f"#DESCRIPTION {name}"

        txt = bouquets_tv.read_text(encoding="utf-8", errors="ignore").splitlines()
        if txt and txt[-1].strip() != "":
            txt.append("")
        txt.append(svc_line)
        txt.append(desc_line)

        with open(bouquets_tv, "w", encoding="utf-8", errors="ignore", newline="\r\n") as f:
            f.write("\n".join(txt) + "\n")

        self._dbg(f"Neues Bouquet angelegt: {name} ({filename})")

        # 3) UI/Model sauber neu laden
        self.open_project_dir(self.workspace_root)

        # optional: direkt auswählen (Name suchen)
        for i, b in enumerate(self.bouquets_data):
            if getattr(b, "name", "") == name:
                self.bouquets.setCurrentRow(i)
                break

    def _set_path_in_statusbar(self, p: Path | None):
        if not hasattr(self, "_path_label"):
            return
        self._path_label.setText(str(p) if p else "")

    def _set_receiver_in_statusbar(self, name: str | None):
        if not hasattr(self, "_receiver_label"):
            return
        if name:
            self._receiver_label.setText(f"Receiver: {name}")
        else:
            self._receiver_label.setText("")

    def action_remove_bouquet(self):
        """
        Entfernt ein oder mehrere links ausgewählte Bouquets:
        - Eintrag(e) aus bouquets.tv entfernen
        - userbouquet.*.tv (nach Backup) löschen
        """
        if not self.workspace_root:
            QMessageBox.warning(self, "Bouquet entfernen", "Kein Projektordner geöffnet.")
            return

        selected = self.bouquets.selectedItems()
        if not selected:
            QMessageBox.warning(self, "Bouquet entfernen", "Kein Bouquet ausgewählt.")
            return

        # Indizes aus selektierten Items
        indices = sorted({self.bouquets.row(it) for it in selected})
        indices = [i for i in indices if 0 <= i < len(self.bouquets_data)]
        if not indices:
            QMessageBox.warning(self, "Bouquet entfernen", "Auswahl ungültig.")
            return

        bouquets_tv = self.workspace_root / "bouquets.tv"
        if not bouquets_tv.exists():
            QMessageBox.critical(self, "Bouquet entfernen", f"Nicht gefunden: {bouquets_tv}")
            return

        # Daten vorbereiten (Name + Path)
        items = []
        blocked = []
        for idx in indices:
            b = self.bouquets_data[idx]
            name = (getattr(b, "name", "") or "<unbekannt>").strip()
            try:
                path = _get_bouquet_file_path(self.workspace_root, b)
            except Exception as e:
                blocked.append(f"- {name}: Dateipfad nicht ermittelbar ({e})")
                continue

            filename = path.name
            if not filename.startswith("userbouquet."):
                blocked.append(f"- {name}: kein userbouquet.* ({filename})")
                continue

            items.append((idx, name, path, filename))

        if not items:
            QMessageBox.warning(
                self,
                "Bouquet entfernen",
                "Keines der ausgewählten Bouquets kann gelöscht werden.\n\n"
                + ("\n".join(blocked) if blocked else ""),
            )
            return

        # Bestätigung (ein Dialog für alle)
        list_text = "\n".join([f"• {name}  ({fn})" for (_, name, _, fn) in items])
        extra = ""
        if blocked:
            extra = "\n\nNicht löschbar (Schutz):\n" + "\n".join(blocked)

        res = QMessageBox.question(
            self,
            "Bouquets entfernen",
            f"Folgende Bouquets wirklich entfernen?\n\n{list_text}\n\n"
            f"• Einträge werden aus bouquets.tv entfernt\n"
            f"• Dateien werden gelöscht (nach Backup)\n\n"
            f"Diese Aktion kann nicht rückgängig gemacht werden." + extra,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if res != QMessageBox.Yes:
            self._dbg("Bouquet entfernen: abgebrochen")
            return

        ts = datetime.now().strftime("%Y%m%d-%H%M%S")

        try:
            # 1) Backup bouquets.tv (einmal)
            backup_tv = bouquets_tv.with_suffix(bouquets_tv.suffix + f".bak.{ts}")
            backup_tv.write_bytes(bouquets_tv.read_bytes())
            self._dbg(f"Bouquet entfernen: backup bouquets.tv={backup_tv}")

            # 2) Backup + löschen der userbouquet-Dateien
            for _, name, path, _ in items:
                if path.exists():
                    backup_b = path.with_suffix(path.suffix + f".bak.{ts}")
                    backup_b.write_bytes(path.read_bytes())
                    self._dbg(f"Bouquet entfernen: backup bouquet={backup_b}")
                    path.unlink()
                    self._dbg(f"Bouquet entfernen: gelöscht {path}")
                else:
                    self._dbg(f"Bouquet entfernen: Datei fehlt (übersprungen): {path} ({name})")

            # 3) bouquets.tv bereinigen: alle entsprechenden SERVICE + direkt folgende DESCRIPTION entfernen
            lines = bouquets_tv.read_text(encoding="utf-8", errors="ignore").splitlines()
            needles = {f'FROM BOUQUET "{fn}"' for (_, _, _, fn) in items}

            new_lines: list[str] = []
            skip_next_desc = False
            removed = 0

            for line in lines:
                if skip_next_desc:
                    if line.strip().startswith("#DESCRIPTION"):
                        removed += 1
                        skip_next_desc = False
                        continue
                    skip_next_desc = False

                if any(n in line for n in needles):
                    removed += 1
                    skip_next_desc = True
                    continue

                new_lines.append(line)

            with open(bouquets_tv, "w", encoding="utf-8", errors="ignore", newline="\r\n") as f:
                f.write("\n".join(new_lines) + "\n")

            self._dbg(f"Bouquet entfernen: bouquets.tv bereinigt (removed_lines={removed})")

            # 4) UI neu laden (einmal)
            self.open_project_dir(self.workspace_root)

        except Exception as e:
            self._dbg(f"Bouquet entfernen: FEHLER: {e}")
            QMessageBox.critical(self, "Bouquet entfernen", str(e))

    def open_project_dir(self, enigma2_dir: Path):
        self._dbg(f"Laden: Start aus {enigma2_dir}")

        try:
            if not enigma2_dir.exists():
                raise FileNotFoundError(f"Ordner existiert nicht: {enigma2_dir}")

            lamedb_path = enigma2_dir / "lamedb"
            if not lamedb_path.exists():
                raise FileNotFoundError(f"lamedb nicht gefunden: {lamedb_path}")

            self.workspace_root = enigma2_dir
            if self.project_dir is None:
                self.project_dir = enigma2_dir

            # Laden
            self.bouquets_data = parse_bouquets(enigma2_dir)
            self.lamedb_map = load_lamedb_service_names(enigma2_dir)

            self._current_bouquet = None
            self._source_bouquet = None

            self.search.blockSignals(True)
            self.search.clear()
            self.search.blockSignals(False)

            # Links füllen (Ziel)
            self.bouquets.clear()
            for b in self.bouquets_data:
                item = QListWidgetItem(b.name)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)

                # filename für Reihenfolge speichern (stabil, unabhängig vom Namen)
                try:
                    p = _get_bouquet_file_path(enigma2_dir, b)
                    item.setData(Qt.UserRole + 10, p.name)  # z.B. userbouquet.xyz.tv
                except Exception:
                    pass

                self.bouquets.addItem(item)

            # Quelle-Dropdown füllen
            self.source_combo.blockSignals(True)
            self.source_combo.clear()
            for b in self.bouquets_data:
                self.source_combo.addItem(b.name, b)  # userData=bouquet
            self.source_combo.blockSignals(False)

            # Listen leeren
            self.entries.clear()
            self._suppress_dirty = True
            self.target.clear()
            self._suppress_dirty = False

            # dirty reset
            self._dirty_bouquet_names.clear()
            self._dirty_bouquet_content.clear()

            self._dbg(f"Laden: fertig, bouquets={len(self.bouquets_data)}")
            self._set_path_in_statusbar(enigma2_dir)

            # Auto-select
            if self.bouquets.count() > 0:
                self.bouquets.setCurrentRow(0)
                self.source_combo.setCurrentIndex(0)
            else:
                self._dbg("Laden: keine Bouquets gefunden (Liste leer)")

        except Exception as e:
            self._dbg(f"Laden: FEHLER: {e}")
            QMessageBox.critical(self, "Projekt öffnen fehlgeschlagen", str(e))

            self._set_path_in_statusbar(enigma2_dir)

            # Receiver-Profil anzeigen (falls vorhanden)
            from bouquetstudio.core.settings import AppSettings

            s = AppSettings()
            rx = s.get_active_profile_name()
            self._set_receiver_in_statusbar(rx if rx else None)

    def _bouquet_order_from_listwidget(self) -> list[str]:
        """Bouquet-Filenames in der Reihenfolge der linken Liste."""
        order: list[str] = []
        for i in range(self.bouquets.count()):
            item = self.bouquets.item(i)
            fn = item.data(Qt.UserRole + 10)  # dort speichern wir gleich den filename
            if fn:
                order.append(str(fn))
        return order

    def _rewrite_bouquets_tv_in_ui_order(self):
        if not self.workspace_root:
            return

        bouquets_tv = self.workspace_root / "bouquets.tv"
        if not bouquets_tv.exists():
            return

        lines = bouquets_tv.read_text(encoding="utf-8", errors="ignore").splitlines()

        # Blocks: SERVICE + direkt folgende DESCRIPTION
        blocks: dict[str, list[str]] = {}
        prefix: list[str] = []  # alles, was kein Bouquet-Block ist (z.B. #NAME …)
        i = 0
        while i < len(lines):
            line = lines[i]
            if line.strip().startswith("#SERVICE") and 'FROM BOUQUET "' in line:
                q1 = line.find('"')
                q2 = line.find('"', q1 + 1)
                if q1 != -1 and q2 != -1:
                    fn = line[q1 + 1 : q2].strip()
                    block = [line]
                    if i + 1 < len(lines) and lines[i + 1].strip().startswith("#DESCRIPTION"):
                        block.append(lines[i + 1])
                        i += 1
                    blocks[fn] = block
                else:
                    prefix.append(line)
            else:
                prefix.append(line)
            i += 1

        order = self._bouquet_order_from_listwidget()

        new_lines: list[str] = []
        new_lines.extend(prefix)

        for fn in order:
            if fn in blocks:
                new_lines.extend(blocks[fn])

        # falls etwas in bouquets.tv existiert, aber nicht in der UI-Liste: hinten anhängen
        for fn, block in blocks.items():
            if fn not in order:
                new_lines.extend(block)

        with open(bouquets_tv, "w", encoding="utf-8", errors="ignore", newline="\r\n") as f:
            f.write("\n".join(new_lines) + "\n")

        self._dirty_bouquet_order = False
        self._dbg("Bouquet-Reihenfolge in bouquets.tv gespeichert")

    def action_save_project(self):
        if not self.workspace_root:
            QMessageBox.warning(self, "Speichern", "Kein Projektordner geöffnet.")
            return
        if not self._current_bouquet:
            QMessageBox.warning(self, "Speichern", "Kein Bouquet (Ziel) ausgewählt.")
            return
        if self.search.text().strip():
            QMessageBox.warning(
                self,
                "Speichern",
                "Bitte Suche leeren, bevor du speicherst.\n"
                "Im Suchmodus ist die Liste gefiltert.",
            )
            return
        if self.target.count() == 0:
            QMessageBox.warning(self, "Speichern", "Rechte Liste ist leer – nichts zu speichern.")
            return

        # Ziel-Reihenfolge übernehmen
        self._apply_target_order_to_model()

        try:
            self._dbg(
                f"Speichern: start bouquet='{getattr(self._current_bouquet, 'name', '?')}' "
                f"project_dir={self.project_dir} workspace_root={self.workspace_root}"
            )
            self._save_bouquet_file(self._current_bouquet)
            self._dbg("Speichern: OK")
            if self._dirty_bouquet_order:
                self._rewrite_bouquets_tv_in_ui_order()

            idx = self.bouquets.currentRow()
            if idx >= 0:
                self._dirty_bouquet_names.discard(idx)
                self._dirty_bouquet_content.discard(idx)

        except Exception as e:
            self._dbg(f"Speichern: FEHLER: {e}")
            QMessageBox.critical(self, "Speichern fehlgeschlagen", str(e))

    def action_save_all_bouquets(self):
        if not self.workspace_root:
            QMessageBox.warning(self, "Speichern", "Kein Projektordner geöffnet.")
            return
        if not self.bouquets_data:
            QMessageBox.warning(self, "Speichern", "Keine Bouquets geladen.")
            return
        if self.search.text().strip():
            QMessageBox.warning(
                self,
                "Speichern",
                "Bitte Suche leeren, bevor du 'Alle Bouquets speichern' nutzt.\n"
                "Im Suchmodus ist die Liste gefiltert.",
            )
            return

        root = self.workspace_root
        ok = 0
        failed: list[str] = []

        self._dbg(f"Alle speichern: start ({len(self.bouquets_data)}) root={root}")
        if self._dirty_bouquet_order:
            self._rewrite_bouquets_tv_in_ui_order()

        for b in self.bouquets_data:
            try:
                load_bouquet_entries(root, b)
                self._save_bouquet_file(b)
                ok += 1
            except Exception as e:
                name = getattr(b, "name", "<unbekannt>")
                failed.append(f"{name}: {e}")

        if failed:
            self._dbg(f"Alle speichern: fertig ok={ok}, failed={len(failed)}")
            QMessageBox.warning(
                self,
                "Alle Bouquets speichern",
                f"Fertig: {ok} gespeichert, {len(failed)} fehlgeschlagen.\n\n"
                + "\n".join(failed[:20])
                + ("" if len(failed) <= 20 else "\n…"),
            )
        else:
            self._dbg(f"Alle speichern: fertig ok={ok}, failed=0")
            self.statusBar().showMessage(f"Alle Bouquets gespeichert ✓ ({ok})", 6000)

        self._dirty_bouquet_names.clear()
        self._dirty_bouquet_content.clear()

    def _save_bouquet_file(self, bouquet):
        root = getattr(self, "project_dir", None) or self.workspace_root
        assert root is not None

        path = _get_bouquet_file_path(root, bouquet)
        self._dbg(f"_save_bouquet_file: ziel={path}")

        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = path.with_suffix(path.suffix + f".bak.{ts}")

        if path.exists():
            backup.write_bytes(path.read_bytes())
            self._dbg(f"_save_bouquet_file: backup={backup}")
        else:
            self._dbg("_save_bouquet_file: backup entfällt (Datei existierte vorher nicht)")

        lines: list[str] = []

        bn = (getattr(bouquet, "name", "Bouquet") or "Bouquet").strip()
        lines.append(f"#NAME {bn}")

        for entry in bouquet.entries:
            if isinstance(entry, dict):
                svc_raw = (entry.get("service_line") or "").strip()
                desc = (entry.get("description") or "").strip()
            else:
                svc_raw = (entry.service_line or "").strip()
                desc = (entry.description or "").strip()

            svc = svc_raw
            if not svc.startswith("#SERVICE"):
                svc = "#SERVICE " + svc.lstrip()
            lines.append(svc)

            if desc:
                lines.append(f"#DESCRIPTION {desc}")

        with open(path, "w", encoding="utf-8", errors="ignore", newline="\r\n") as f:
            f.write("\n".join(lines) + "\n")

        self._dbg(f"_save_bouquet_file: geschrieben ({len(lines)} Zeilen)")

    # -------------------------------------------------------------------------
    # Hilfe
    # -------------------------------------------------------------------------
    def action_about(self):
        QMessageBox.information(
            self,
            f"Über {__app_name__}",
            f"{__app_name__}\n"
            f"Enigma2 Bouquet Editor\n\n"
            f"Version: {__version__}\n"
            f"Autor: {__author__}\n\n"
            "Lokaler Editor für Enigma2-Bouquets.\n"
            "Bearbeiten, Sortieren und Übertragen von Bouquets\n"
            "per SFTP – ohne Cloud, ohne externe Dienste.\n\n"
            "© 2026 Holger Mangold",
        )

    # -------------------------------------------------------------------------
    # Ziel-Bouquet (links) auswählen
    # -------------------------------------------------------------------------
    def _on_target_bouquet_selected(self, index: int):
        if index < 0 or index >= len(self.bouquets_data):
            return

        bouquet = self.bouquets_data[index]
        self._current_bouquet = bouquet

        root = self.workspace_root if self.workspace_root else self.test_root
        self._dbg(f"Ziel gewählt: idx={index} name='{getattr(bouquet, 'name', '?')}' root={root}")

        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)

        self._suppress_dirty = True
        self.target.clear()
        self._suppress_dirty = False

        # Quelle folgt dem Ziel
        self.source_combo.blockSignals(True)
        self.source_combo.setCurrentIndex(index)
        self.source_combo.blockSignals(False)

        self._on_source_bouquet_selected(index)
        self._update_source_marks()

    def _on_bouquet_order_changed(self, *args):
        self._dirty_bouquet_order = True
        self._dbg("Bouquet-Reihenfolge geändert -> dirty")

    # -------------------------------------------------------------------------
    # Quelle (Dropdown) auswählen
    # -------------------------------------------------------------------------
    def _on_source_bouquet_selected(self, index: int):
        if index < 0 or index >= len(self.bouquets_data):
            self._source_bouquet = None
            self.entries.clear()
            return

        src = self.bouquets_data[index]
        self._source_bouquet = src

        root = self.workspace_root if self.workspace_root else self.test_root
        self._dbg(f"Quelle gewählt: idx={index} name='{getattr(src, 'name', '?')}' root={root}")

        load_bouquet_entries(root, src)
        self._populate_entries(src)
        self._update_source_marks()

    # -------------------------------------------------------------------------
    # Umbenennen links (Ziel-Liste)
    # -------------------------------------------------------------------------
    def _on_bouquet_name_changed(self, item: QListWidgetItem):
        idx = self.bouquets.row(item)
        if idx < 0 or idx >= len(self.bouquets_data):
            return

        new_name = (item.text() or "").strip()
        if not new_name:
            old_name = getattr(self.bouquets_data[idx], "name", "Bouquet")
            item.setText(old_name)
            QMessageBox.warning(self, "Ungültiger Name", "Bouquet-Name darf nicht leer sein.")
            return

        old_name = getattr(self.bouquets_data[idx], "name", "")
        if new_name == old_name:
            return

        self.bouquets_data[idx].name = new_name
        self._dirty_bouquet_names.add(idx)

        if self._current_bouquet is self.bouquets_data[idx]:
            self._dbg(f"Bouquet umbenannt: '{old_name}' -> '{new_name}' (nur intern)")

    # -------------------------------------------------------------------------
    # Anzeige-Text
    # -------------------------------------------------------------------------
    def _display_text_for_entry(self, entry) -> str:
        if _is_marker_service(entry.service_line):
            label = entry.description.strip() if entry.description else "—"
            return f"📌 {label}"

        text = entry.description.strip() if entry.description else ""
        if not text:
            name = resolve_service_name(entry.service_line, self.lamedb_map)
            if name:
                text = name
        if not text:
            text = (entry.service_line or "").strip()
        return text

    def _entry_key(self, entry) -> str:
        return (entry.service_line or "").strip()

    def _populate_entries(self, bouquet):
        self.entries.clear()

        for entry in bouquet.entries:
            shown = self._display_text_for_entry(entry)
            it = QListWidgetItem(shown)
            it.setData(Qt.UserRole, entry)  # Objekt
            it.setData(Qt.UserRole + 1, self._entry_key(entry))  # Key
            self.entries.addItem(it)

        self.entries.setDragEnabled(True)
        self.entries.setAcceptDrops(False)

    # -------------------------------------------------------------------------
    # Suche filtert immer die QUELLE
    # -------------------------------------------------------------------------
    def _filter_entries(self, text: str):
        if self._source_bouquet is None:
            return

        needle = text.lower().strip()
        self.entries.clear()

        for entry in self._source_bouquet.entries:
            shown = self._display_text_for_entry(entry)
            if (not needle) or (needle in shown.lower()):
                it = QListWidgetItem(shown)
                it.setData(Qt.UserRole, entry)
                it.setData(Qt.UserRole + 1, self._entry_key(entry))
                self.entries.addItem(it)

        self.entries.setDragEnabled(True)
        self.entries.setAcceptDrops(False)

        self._update_source_marks()

    # -------------------------------------------------------------------------
    # Ziel-Liste / Markierung / Übernahme
    # -------------------------------------------------------------------------
    def _update_source_marks(self):
        target_keys = set()
        for i in range(self.target.count()):
            it = self.target.item(i)
            k = it.data(Qt.UserRole + 1)
            if k:
                target_keys.add(k)

        for i in range(self.entries.count()):
            it = self.entries.item(i)
            if not it:
                continue
            k = it.data(Qt.UserRole + 1)

            if k and k in target_keys:
                it.setForeground(QBrush(Qt.gray))
                if not it.text().startswith("✅ "):
                    it.setText("✅ " + it.text())
            else:
                it.setForeground(QBrush(Qt.black))
                if it.text().startswith("✅ "):
                    it.setText(it.text()[2:].lstrip())

    def _apply_target_order_to_model(self):
        if not self._current_bouquet:
            return
        if self.target.count() == 0:
            return

        target_entries = []

        for i in range(self.target.count()):
            it = self.target.item(i)
            entry = it.data(Qt.UserRole)
            if entry is None:
                continue

            # Custom-Marker: Text aus dem Item übernehmen (UI -> description)
            if isinstance(entry, dict):
                text = (it.text() or "").strip()
                if text.startswith("📌"):
                    text = text[1:].strip()
                entry["description"] = text or "Marker"

            target_entries.append(entry)

        if not target_entries:
            return

        self._current_bouquet.entries = target_entries

    def _on_target_changed(self, *args):
        if self._suppress_dirty:
            return
        idx = self.bouquets.currentRow()
        if idx < 0:
            return
        self._dirty_bouquet_content.add(idx)
        self._dbg(f"Ziel-Liste geändert -> dirty (idx={idx})")

    def _edit_target_marker_dialog(self, item: QListWidgetItem):
        """
        Doppelklick im Ziel (rechts):
        - Nur für Marker (Service-Typ 64/832)
        - Öffnet Dialog und schreibt Text in item + entry["description"]
        """
        if item is None:
            return

        entry = item.data(Qt.UserRole)
        if not isinstance(entry, dict):
            return

        svc = (entry.get("service_line") or "").strip()
        if not _is_marker_service(svc):
            return

        # Aktuellen Text holen (ohne 📌)
        current = (item.text() or "").strip()
        if current.startswith("📌"):
            current = current[1:].strip()

        new_text, ok = QInputDialog.getText(
            self,
            "Überschrift ändern",
            "Text:",
            text=current,
        )
        if not ok:
            return

        new_text = (new_text or "").strip()
        if not new_text:
            QMessageBox.warning(self, "Ungültig", "Überschrift darf nicht leer sein.")
            return

        # UI aktualisieren
        item.setText(f"📌 {new_text}")
        # Model-Entry aktualisieren (wichtig fürs Speichern)
        entry["description"] = new_text
        item.setData(Qt.UserRole, entry)

        # Dirty markieren (sicher, auch wenn model.dataChanged mal nicht feuert)
        idx = self.bouquets.currentRow()
        if idx >= 0:
            self._dirty_bouquet_content.add(idx)
        self._dbg(f"Marker geändert: '{new_text}'")

    def action_add_target_line(self):
        if not self._current_bouquet:
            QMessageBox.warning(self, "Zeile hinzufügen", "Kein Bouquet (Ziel) ausgewählt.")
            return

        marker_service = "1:64:0:0:0:0:0:0:0:0:"

        entry = {
            "service_line": marker_service,
            "description": "Neue Überschrift",
        }

        it = QListWidgetItem("📌 Neue Überschrift")
        it.setData(Qt.UserRole, entry)
        it.setData(Qt.UserRole + 1, marker_service)
        it.setFlags(it.flags() | Qt.ItemFlag.ItemIsEditable)

        self.target.addItem(it)
        self.target.setCurrentItem(it)
        self.target.editItem(it)

    # -------------------------------------------------------------------------
    # Receiver-Aktionen (Platzhalter)
    # -------------------------------------------------------------------------
    def action_receiver_settings(self):
        dlg = ReceiverSettingsDialog(self)
        dlg.exec()

    def action_receiver_connect(self):
        QMessageBox.information(
            self,
            "Receiver verbinden (kommt als nächstes)",
            "Hier kommt der Connect-Dialog (IP/User/Pass/Port, SFTP/SSH).\n"
            "Danach können wir Download/Upload/Reload aktivieren.",
        )

    def action_receiver_download(self):
        settings = AppSettings()
        name = settings.get_active_profile_name()
        if not name:
            QMessageBox.warning(self, "Download", "Kein Receiver-Profil aktiv.")
            return

        p = settings.load_profile(name)
        self._set_receiver_in_statusbar(name)
        if not p:
            QMessageBox.warning(self, "Download", "Receiver-Profil nicht gefunden.")
            return

        from pathlib import Path
        import shutil

        # Fester Workspace pro Receiver-Profil (kein Timestamp mehr)
        receiver_ws_root = Path.home() / ".local" / "share" / "BouquetStudio" / "workspaces" / name

        workspace = receiver_ws_root / "etc" / "enigma2"

        # Workspace immer sauber neu aufsetzen (damit keine Altlasten bleiben)
        if receiver_ws_root.exists():
            shutil.rmtree(receiver_ws_root)

        workspace.mkdir(parents=True, exist_ok=True)

        try:
            self._dbg(f"Download: start {p.host} -> {workspace}")
            download_enigma2_dir(
                host=p.host,
                port=p.port,
                user=p.user,
                password=p.password,
                remote_dir=p.remote_path,
                local_dir=workspace,
            )
            self._dbg("Download: OK")

            # Workspace automatisch öffnen
            self.project_dir = workspace
            self.open_project_dir(workspace)
            AppSettings().set_last_project_dir(workspace)

            QMessageBox.information(
                self,
                "Download abgeschlossen",
                f"Bouquets wurden heruntergeladen nach:\n{workspace}",
            )

        except Exception as e:
            QMessageBox.critical(
                self,
                "Download fehlgeschlagen",
                str(e),
            )

    def action_receiver_upload(self):
        settings = AppSettings()
        prof_name = settings.get_active_profile_name()
        if not prof_name:
            QMessageBox.warning(self, "Upload", "Kein Receiver-Profil aktiv.")
            return

        p = settings.load_profile(prof_name)
        if not p:
            QMessageBox.warning(self, "Upload", "Receiver-Profil nicht gefunden.")
            return

        if p.type != "sftp":
            QMessageBox.warning(self, "Upload", "Aktuell ist nur SFTP-Upload umgesetzt.")
            return

        local_dir = self.workspace_root or self.project_dir
        if not local_dir or not Path(local_dir).exists():
            QMessageBox.warning(self, "Upload", "Kein lokales Projektverzeichnis geöffnet.")
            return

        local_dir = Path(local_dir)

        try:
            self._dbg(f"Upload: Planung ({p.host}) …")
            items = plan_upload_sftp(
                host=p.host,
                port=p.port,
                user=p.user,
                password=p.password,
                remote_dir=p.remote_path,
                local_dir=local_dir,
            )

            if not items:
                QMessageBox.information(
                    self, "Upload", "Keine Änderungen gefunden – nichts hochzuladen."
                )
                return

            # Hinweis / Bestätigung (was wird überschrieben)
            lines = []
            for it in items:
                reason = "geändert" if it.reason == "changed" else "fehlt auf Receiver"
                lines.append(f"- {it.local_path.name} ({reason})")

            msg = (
                "Achtung: Auf dem Receiver werden Dateien überschrieben.\n\n"
                "Folgende Dateien werden hochgeladen:\n"
                + "\n".join(lines)
                + "\n\nVorher wird automatisch ein Backup auf dem Receiver angelegt."
            )

            res = QMessageBox.question(
                self,
                "Upload bestätigen",
                msg,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if res != QMessageBox.Yes:
                self._dbg("Upload: abgebrochen")
                return

            from datetime import datetime

            suffix = datetime.now().strftime("%Y%m%d-%H%M%S")

            self._dbg("Upload: starte (mit Backup) …")
            backup_dir = upload_sftp_with_backup(
                host=p.host,
                port=p.port,
                user=p.user,
                password=p.password,
                remote_dir=p.remote_path,
                local_dir=local_dir,
                upload_items=items,
                backup_suffix=suffix,
            )

            # danach Bouquets neu einlesen (DreamboxEdit-Style)
            try:
                reload_enigma2(
                    host=p.host,
                    port=p.port,
                    user=p.user,
                    password=p.password,
                    webif_port=getattr(p, "webif_port", 80),
                )
            except Exception:
                pass

            QMessageBox.information(
                self,
                "Upload abgeschlossen",
                f"Upload erfolgreich.\n\nBackup auf Receiver:\n{backup_dir}",
            )
            self._dbg("Upload: OK")

        except Exception as e:
            QMessageBox.critical(self, "Upload fehlgeschlagen", str(e))
            self._dbg(f"Upload: FEHLER: {e}")

    def action_receiver_reload(self):
        settings = AppSettings()
        prof_name = settings.get_active_profile_name()
        if not prof_name:
            QMessageBox.warning(self, "Reload", "Kein Receiver-Profil aktiv.")
            return

        p = settings.load_profile(prof_name)
        if not p:
            QMessageBox.warning(self, "Reload", "Receiver-Profil nicht gefunden.")
            return

        try:
            # Für OpenWebif ist Port normalerweise 80 (oder 83 / 8080 je nach Setup)
            webif_port = getattr(p, "webif_port", 80)

            self._dbg(f"Reload: starte auf {p.host} (WebIF:{webif_port})")

            # reload_enigma2 gibt bei dir (wie vorher) einen String zurück
            # port = p.port (SSH/SFTP Port) lassen wir drin, damit Signatur passt
            result = reload_enigma2(
                host=p.host,
                port=p.port,
                user=p.user,
                password=p.password,
                timeout=5,
                webif_port=webif_port,
            )

            self._dbg(f"Reload: OK ({result})")
            QMessageBox.information(self, "Bouquets neu geladen", str(result))

        except Exception as e:
            self._dbg(f"Reload: FEHLER: {e}")
            QMessageBox.critical(self, "Reload fehlgeschlagen", str(e))
