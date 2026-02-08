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
)

from bouquetstudio.core.bouquets import parse_bouquets, load_bouquet_entries
from bouquetstudio.core.lamedb import load_lamedb_service_names, resolve_service_name
from bouquetstudio.ui.target_list import TargetListWidget


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

        # ✅ verhindert Dirty beim programmgesteuerten Befüllen/Löschen
        self._suppress_dirty = False

        # Default-Testpfad
        self.test_root = Path.home() / "BouquetTest" / "etc" / "enigma2"

        # UI
        root = QWidget()
        self.setCentralWidget(root)
        main = QHBoxLayout(root)

        # ---------------------------------------------------------------------
        # Left (Ziel-Bouquets)
        # ---------------------------------------------------------------------
        left = QVBoxLayout()
        left.addWidget(QLabel("Bouquets (Ziel)"))
        self.bouquets = QListWidget()
        self.bouquets.setEditTriggers(
            QListWidget.EditTrigger.DoubleClicked | QListWidget.EditTrigger.EditKeyPressed
        )
        left.addWidget(self.bouquets)
        self.add_bouquet_btn = QPushButton("➕ Bouquet hinzufügen")
        self.add_bouquet_btn.setToolTip("Neues TV-Bouquet anlegen und in bouquets.tv eintragen")
        self.add_bouquet_btn.clicked.connect(self.action_add_new_bouquet)
        left.addWidget(self.add_bouquet_btn)

        # ---------------------------------------------------------------------
        # Middle (Quelle)
        # ---------------------------------------------------------------------
        mid = QVBoxLayout()
        mid.addWidget(QLabel("Sender / Einträge (Quelle)"))

        mid.addWidget(QLabel("Quelle:"))
        self.source_combo = QComboBox()
        mid.addWidget(self.source_combo)

        from bouquetstudio.ui.draggable_list import BlockMoveListWidget

        self.entries = BlockMoveListWidget()

        # Quelle: nur Drag, keine Drops (kein internes Verschieben -> Bug umgangen)
        self.entries.setDragEnabled(True)
        self.entries.setAcceptDrops(False)

        mid.addWidget(self.entries, 1)

        # ---------------------------------------------------------------------
        # Right (Ziel)
        # ---------------------------------------------------------------------
        right = QVBoxLayout()
        right.addWidget(QLabel("Suche"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Sender suchen…")
        right.addWidget(self.search)

        right.addSpacing(10)
        right.addWidget(QLabel("Neue Reihenfolge (Ziel)"))

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
        right.addWidget(self.target, 1)

        # ✅ Änderungen in der Ziel-Liste (rechts) als "dirty" markieren
        m = self.target.model()
        m.rowsInserted.connect(self._on_target_changed)
        m.rowsRemoved.connect(self._on_target_changed)
        m.rowsMoved.connect(self._on_target_changed)
        m.dataChanged.connect(self._on_target_changed)

        hint = QLabel("Tipp: Ziel-Liste sortieren per Drag&Drop • Entf löscht Einträge")
        hint.setStyleSheet("color: gray;")
        right.addWidget(hint)

        main.addLayout(left, 1)
        main.addLayout(mid, 2)
        main.addLayout(right, 2)

        self._build_menu()

        # ---------------------------------------------------------------------
        # Signals
        # ---------------------------------------------------------------------
        self.bouquets.currentRowChanged.connect(self._on_target_bouquet_selected)
        self.bouquets.itemChanged.connect(self._on_bouquet_name_changed)

        self.source_combo.currentIndexChanged.connect(self._on_source_bouquet_selected)
        self.search.textChanged.connect(self._filter_entries)

        # Initial load (Test) – nur wenn vorhanden, sonst leer starten
        if self.test_root.exists():
            self.project_dir = self.test_root
            self.open_project_dir(self.test_root)
        else:
            self._dbg("Start: kein Test-Projekt gefunden – bitte 'Datei → Projekt öffnen…' wählen")

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
        a_about = m_help.addAction("Über…")
        a_about.triggered.connect(self.action_about)

    # -------------------------------------------------------------------------
    # Dirty-Warnung beim Schließen
    # -------------------------------------------------------------------------
    def closeEvent(self, event):
        if self._dirty_bouquet_names or self._dirty_bouquet_content:
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
        self.workspace_root = self.project_dir

        self.setWindowTitle(f"BouquetStudio – {self.project_dir}")
        self._dbg(f"Projekt öffnen: {self.project_dir}")

        self.open_project_dir(self.project_dir)

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
        userbouquet_path.write_text(f"#NAME {name}\n", encoding="utf-8", errors="ignore")

        # 2) In bouquets.tv eintragen (damit parse_bouquets() es findet)
        svc_line = f'#SERVICE 1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "{filename}" ORDER BY bouquet'
        desc_line = f"#DESCRIPTION {name}"

        txt = bouquets_tv.read_text(encoding="utf-8", errors="ignore").splitlines()
        # ans Ende anhängen (mit Leerzeile dazwischen, falls Datei nicht leer ist)
        if txt and txt[-1].strip() != "":
            txt.append("")
        txt.append(svc_line)
        txt.append(desc_line)

        bouquets_tv.write_text("\n".join(txt) + "\n", encoding="utf-8", errors="ignore")

        self._dbg(f"Neues Bouquet angelegt: {name} ({filename})")

        # 3) UI/Model sauber neu laden, damit links + Quelle-Dropdown es direkt haben
        self.open_project_dir(self.workspace_root)

        # optional: direkt auswählen (Name suchen)
        for i, b in enumerate(self.bouquets_data):
            if getattr(b, "name", "") == name:
                self.bouquets.setCurrentRow(i)
                break

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

            # Auto-select
            if self.bouquets.count() > 0:
                self.bouquets.setCurrentRow(0)  # Ziel wählen -> füllt rechts/markiert state
                self.source_combo.setCurrentIndex(0)  # Quelle initial gleich
            else:
                self._dbg("Laden: keine Bouquets gefunden (Liste leer)")

        except Exception as e:
            self._dbg(f"Laden: FEHLER: {e}")
            QMessageBox.critical(self, "Projekt öffnen fehlgeschlagen", str(e))

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

        # Ziel-Reihenfolge übernehmen (wenn Ziel-Liste nicht leer)
        self._apply_target_order_to_model()

        try:
            self._dbg(
                f"Speichern: start bouquet='{getattr(self._current_bouquet, 'name', '?')}' "
                f"project_dir={self.project_dir} workspace_root={self.workspace_root}"
            )
            self._save_bouquet_file(self._current_bouquet)
            self._dbg("Speichern: OK")

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

        # ✅ nach all-save: dirty reset
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

        # ✅ #NAME immer aus dem aktuellen Model-Namen schreiben (UI -> Model -> Datei)
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

        path.write_text("\n".join(lines) + "\n", encoding="utf-8", errors="ignore")
        self._dbg(f"_save_bouquet_file: geschrieben ({len(lines)} Zeilen)")

    # -------------------------------------------------------------------------
    # Hilfe
    # -------------------------------------------------------------------------
    def action_about(self):
        QMessageBox.information(
            self,
            "Über BouquetStudio",
            "BouquetStudio\n"
            "Lokaler Enigma2 Bouquet Editor (Python / PySide6)\n"
            "Ziel: Bouquet-Editing + Save + später Receiver Upload\n",
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

        # ✅ Suche leeren (wir filtern die Quelle)
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)

        # ✅ Ziel-Liste leeren (neue Ziel-Auswahl)
        self._suppress_dirty = True
        self.target.clear()
        self._suppress_dirty = False

        # ✅ Standard: Quelle folgt dem Ziel (damit "wie früher" direkt funktioniert)
        self.source_combo.blockSignals(True)
        self.source_combo.setCurrentIndex(index)
        self.source_combo.blockSignals(False)

        # Quelle laden (füllt Mitte)
        self._on_source_bouquet_selected(index)

        # Markierung aktualisieren
        self._update_source_marks()

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
        """
        Rechtes Fenster ist die neue Wahrheit:
        - Bouquet wird EXAKT durch Target ersetzt (kein Rest anhängen!)
        """
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

    def action_add_target_line(self):
        if not self._current_bouquet:
            QMessageBox.warning(self, "Zeile hinzufügen", "Kein Bouquet (Ziel) ausgewählt.")
            return

        marker_service = "1:64:0:0:0:0:0:0:0:0:"

        entry = {
            "service_line": marker_service,
            "description": "Neue Überschrift",
        }

        # 📌 ist nur UI – gespeichert wird nur #SERVICE + #DESCRIPTION
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
    def action_receiver_connect(self):
        QMessageBox.information(
            self,
            "Receiver verbinden (kommt als nächstes)",
            "Hier kommt der Connect-Dialog (IP/User/Pass/Port, SFTP/SSH).\n"
            "Danach können wir Download/Upload/Reload aktivieren.",
        )

    def action_receiver_download(self):
        QMessageBox.information(
            self,
            "Download (kommt als nächstes)",
            "Hier laden wir später /etc/enigma2/ in ein lokales Workspace-Verzeichnis.\n"
            "Dann öffnen wir dieses Workspace automatisch als Projekt.",
        )

    def action_receiver_upload(self):
        QMessageBox.information(
            self,
            "Upload (kommt als nächstes)",
            "Hier laden wir später die geänderten Dateien zurück nach /etc/enigma2/.\n"
            "Optional: vorher Backup auf der Box anlegen.",
        )

    def action_receiver_reload(self):
        QMessageBox.information(
            self,
            "Enigma2 neu laden (kommt als nächstes)",
            "Hier senden wir später per SSH z.B.:\n"
            "killall -HUP enigma2\n"
            "oder GUI-Neustart je nach Box.",
        )
