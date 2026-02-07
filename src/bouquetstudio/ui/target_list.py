from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QAbstractItemView
from PySide6.QtGui import QBrush, QColor


class TargetListWidget(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDropIndicatorShown(True)
        self.setDefaultDropAction(Qt.MoveAction)

    def dropEvent(self, event):
        src = event.source()

        # Wenn Drop aus einer QListWidget-Quelle kommt (unsere mittlere Liste)
        if isinstance(src, QListWidget) and src is not self:
            items = src.selectedItems()
            if not items:
                event.ignore()
                return

            # Einfügeposition bestimmen (wohin im Target)
            insert_row = self.indexAt(event.position().toPoint()).row()
            if insert_row < 0:
                insert_row = self.count()

            # Items: von Quelle -> Target (inkl. UserRole Daten!)
            for it in items:
                # Daten kopieren
                new_it = QListWidgetItem(it.text())
                new_it.setData(Qt.UserRole, it.data(Qt.UserRole))
                new_it.setData(Qt.UserRole + 1, it.data(Qt.UserRole + 1))

                self.insertItem(insert_row, new_it)
                insert_row += 1

                # aus Quelle entfernen (damit er dort verschwindet)
                row = src.row(it)
                src.takeItem(row)

            event.acceptProposedAction()
            return

        # fallback: Standardverhalten (internes Sortieren im Target)
        super().dropEvent(event)

    # ------------------------------------------------------------
    # Drag & Drop
    # ------------------------------------------------------------

    def dragEnterEvent(self, event):
        event.acceptProposedAction()

    def dragMoveEvent(self, event):
        event.acceptProposedAction()

    def dropEvent(self, event):
        """
        Items aus der Source-Liste werden hierher kopiert.
        """
        source = event.source()

        if not isinstance(source, QListWidget):
            event.ignore()
            return

        selected = source.selectedItems()
        if not selected:
            event.ignore()
            return

        insert_row = self.indexAt(event.position().toPoint()).row()
        if insert_row < 0:
            insert_row = self.count()

        for src_item in selected:
            entry = src_item.data(Qt.UserRole)
            if entry is None:
                continue

            text = src_item.text()

            it = QListWidgetItem(text)
            it.setData(Qt.UserRole, entry)

            # farbliche Kennzeichnung: "neu platziert"
            it.setBackground(QBrush(QColor("#d0ebff")))

            self.insertItem(insert_row, it)
            insert_row += 1

        event.acceptProposedAction()

    # ------------------------------------------------------------
    # Tastatur
    # ------------------------------------------------------------

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete:
            for it in self.selectedItems():
                self.takeItem(self.row(it))
            return
        super().keyPressEvent(event)
