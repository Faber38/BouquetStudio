from __future__ import annotations

from typing import List

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QAbstractItemView


class BlockMoveListWidget(QListWidget):
    """
    QListWidget, das mehrere selektierte Items als Block verschieben kann.
    Wichtig:
      - Wir verschieben die Items selbst (takeItem/insertItem)
      - Wir berechnen target_row korrekt anhand dropIndicatorPosition()
      - Danach emitten wir itemsMoved, damit MainWindow das Model syncen kann
    """

    itemsMoved = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)

        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setDragDropOverwriteMode(False)

    def dropEvent(self, event):
        # Wir machen den kompletten Move selbst:
        event.setDropAction(Qt.MoveAction)

        # --- Zielposition bestimmen (entscheidend!) ---
        pos = event.position().toPoint()  # Qt6
        idx = self.indexAt(pos)
        target_row = idx.row()

        dip = self.dropIndicatorPosition()
        if dip == QAbstractItemView.OnViewport or target_row < 0:
            target_row = self.count()
        elif dip == QAbstractItemView.BelowItem:
            target_row += 1
        # AboveItem / OnItem => target_row bleibt wie idx.row()

        # --- Auswahl holen (in UI-Reihenfolge) ---
        selected_items = self.selectedItems()
        if not selected_items:
            super().dropEvent(event)
            return

        selected_rows: List[int] = sorted(self.row(it) for it in selected_items)

        # Drop innerhalb des Blocks -> nichts tun
        # (target_row kann auch direkt hinter dem Block liegen => +1)
        if selected_rows[0] <= target_row <= selected_rows[-1] + 1:
            event.ignore()
            return

        before = self.count()

        # --- Items nehmen (von unten nach oben, damit Indizes stabil bleiben) ---
        taken: List[QListWidgetItem] = []
        for r in reversed(selected_rows):
            it = self.takeItem(r)
            if it is not None:
                taken.append(it)

        taken.reverse()  # ursprüngliche Reihenfolge wiederherstellen

        # --- target_row korrigieren (weil wir oberhalb evtl. Items entfernt haben) ---
        removed_above = sum(1 for r in selected_rows if r < target_row)
        target_row -= removed_above

        if target_row < 0:
            target_row = 0
        if target_row > self.count():
            target_row = self.count()

        # --- Einfügen ---
        insert_at = target_row
        for it in taken:
            self.insertItem(insert_at, it)
            insert_at += 1

        # --- Auswahl wiederherstellen ---
        self.clearSelection()
        for it in taken:
            it.setSelected(True)

        after = self.count()

        # Debug optional:
        # print(f"[DND] before={before} after={after} selected_rows={selected_rows} target_row={target_row} taken={len(taken)}")

        event.accept()

        # ✅ Caller informieren (MainWindow sync)
        self.itemsMoved.emit()
