from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QListWidget, QLineEdit, QVBoxLayout, QLabel
)

from bouquetstudio.core.bouquets import parse_bouquets, load_bouquet_entries


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BouquetStudio – Enigma2 Bouquet Editor")
        self.resize(1100, 700)

        root = QWidget()
        self.setCentralWidget(root)
        main = QHBoxLayout(root)

        # Left
        left = QVBoxLayout()
        left.addWidget(QLabel("Bouquets"))
        self.bouquets = QListWidget()
        self.bouquets.addItems(["(Demo) Favoriten", "(Demo) Filme", "(Demo) Sport"])
        left.addWidget(self.bouquets)

        # Middle
        mid = QVBoxLayout()
        mid.addWidget(QLabel("Sender / Einträge"))
        self.entries = QListWidget()
        self.entries.setDragDropMode(QListWidget.InternalMove)  # MVP: reorder
        self.entries.addItems(["Das Erste HD", "ZDF HD", "Arte HD", "3sat HD"])
        mid.addWidget(self.entries)

        # Right
        right = QVBoxLayout()
        right.addWidget(QLabel("Suche"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Sender suchen… (kommt als nächstes)")
        right.addWidget(self.search)
        right.addStretch(1)

        main.addLayout(left, 1)
        main.addLayout(mid, 2)
        main.addLayout(right, 1)

        # ✅ TEMP: lokale Testdaten laden (muss IN __init__ stehen!)
        self.bouquets_data = []
        test_root = Path.home() / "BouquetTest" / "etc" / "enigma2"

        try:
            self.bouquets_data = parse_bouquets(test_root)
            self.bouquets.clear()
            for b in self.bouquets_data:
                self.bouquets.addItem(b.name)

            self.bouquets.currentRowChanged.connect(self._on_bouquet_selected)

        except Exception as e:
            print("Fehler beim Laden:", e)

    def _on_bouquet_selected(self, index: int):
        if index < 0 or index >= len(self.bouquets_data):
            return

        bouquet = self.bouquets_data[index]
        test_root = Path.home() / "BouquetTest" / "etc" / "enigma2"
        load_bouquet_entries(test_root, bouquet)

        self.entries.clear()
        for entry in bouquet.entries:
            text = entry.description if entry.description else entry.service_line
            self.entries.addItem(text)
