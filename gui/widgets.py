"""Small reusable Qt building blocks shared by every tab."""

from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout,
)


class PrimaryButton(QPushButton):
    def __init__(self, text="", parent=None, **kwargs):
        super().__init__(text, parent)
        self.setProperty("variant", "primary")
        self.setCursor(Qt.PointingHandCursor)


class SecondaryButton(QPushButton):
    def __init__(self, text="", parent=None, **kwargs):
        super().__init__(text, parent)
        self.setProperty("variant", "secondary")
        self.setCursor(Qt.PointingHandCursor)


class DangerButton(QPushButton):
    def __init__(self, text="", parent=None, **kwargs):
        super().__init__(text, parent)
        self.setProperty("variant", "danger")
        self.setCursor(Qt.PointingHandCursor)


class PillButton(QPushButton):
    """A checkable, pill-shaped filter button (All/Unused/Used/Trash)."""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setProperty("variant", "pill")
        self.setCursor(Qt.PointingHandCursor)

    def set_active(self, active: bool):
        self.setProperty("active", "true" if active else "false")
        self.style().unpolish(self)
        self.style().polish(self)


def make_label(text="", variant=None, parent=None):
    lbl = QLabel(text, parent)
    if variant:
        lbl.setProperty("variant", variant)
    return lbl


class Card(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")


class PromptDialog(QDialog):
    """Small modal for editing a single line of text (e.g. a label), used
    for both single-row and bulk edits. Calls on_submit(value) once the
    user confirms; does nothing on cancel/close."""

    def __init__(self, parent, title, message, initial="", on_submit=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setFixedSize(420, 180)
        self._on_submit = on_submit

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        msg = QLabel(message)
        msg.setProperty("variant", "secondary")
        msg.setWordWrap(True)
        layout.addWidget(msg)

        self.entry = QLineEdit(initial)
        self.entry.returnPressed.connect(self._submit)
        layout.addWidget(self.entry)
        layout.addStretch()

        btn_row = QHBoxLayout()
        save_btn = PrimaryButton("Save")
        save_btn.clicked.connect(self._submit)
        cancel_btn = SecondaryButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.entry.setFocus()
        self.entry.selectAll()

    def _submit(self):
        value = self.entry.text().strip()
        self.accept()
        if self._on_submit is not None:
            self._on_submit(value)


class DictTableModel(QAbstractTableModel):
    """A model backed by a plain list of dicts — genuinely virtualized (Qt
    only ever asks for the rows currently on screen), replacing the old
    CustomTkinter SimpleTable that had to build/destroy real widgets for
    every row on every refresh.

    columns: list of (key, heading) tuples.
    row_id_key: dict key used to identify a row uniquely (e.g. "email"),
      needed to track checked state / selection across a fresh set_rows().
    checkable_key: if set, that column renders as a checkbox instead of text.
    formatters: {key: fn(value, row_dict) -> display string}
    """

    def __init__(self, columns, row_id_key=None, checkable_key=None, formatters=None, parent=None):
        super().__init__(parent)
        self.columns = columns
        self.row_id_key = row_id_key
        self.checkable_key = checkable_key
        self.formatters = formatters or {}
        self._rows = []
        self._checked = set()

    def set_rows(self, rows):
        checked_ids = self._checked if self.row_id_key else set()
        self.beginResetModel()
        self._rows = rows
        if self.row_id_key:
            valid_ids = {r.get(self.row_id_key) for r in rows}
            self._checked = checked_ids & valid_ids
        self.endResetModel()

    def row_at(self, row_index):
        return self._rows[row_index]

    def all_rows(self):
        return list(self._rows)

    def checked_ids(self):
        return set(self._checked)

    def set_checked_ids(self, ids):
        self._checked = set(ids)
        if self._rows:
            col = self._column_index(self.checkable_key)
            if col is not None:
                self.dataChanged.emit(
                    self.index(0, col), self.index(len(self._rows) - 1, col), [Qt.CheckStateRole]
                )

    def _column_index(self, key):
        for i, (k, _) in enumerate(self.columns):
            if k == key:
                return i
        return None

    # -- QAbstractTableModel overrides --
    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.columns)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.columns[section][1]
        return None

    def flags(self, index):
        base = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        key = self.columns[index.column()][0]
        if key == self.checkable_key:
            base |= Qt.ItemIsUserCheckable
        return base

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        key = self.columns[index.column()][0]

        if role == Qt.CheckStateRole and key == self.checkable_key:
            row_id = row.get(self.row_id_key)
            return Qt.Checked if row_id in self._checked else Qt.Unchecked

        if role == Qt.DisplayRole:
            if key == self.checkable_key:
                return ""
            value = row.get(key, "")
            fmt = self.formatters.get(key)
            if fmt:
                return fmt(value, row)
            return str(value) if value is not None else ""

        return None

    def setData(self, index, value, role=Qt.EditRole):
        if role == Qt.CheckStateRole:
            key = self.columns[index.column()][0]
            if key != self.checkable_key or not self.row_id_key:
                return False
            row = self._rows[index.row()]
            row_id = row.get(self.row_id_key)
            if value == Qt.Checked.value or value == Qt.Checked:
                self._checked.add(row_id)
            else:
                self._checked.discard(row_id)
            self.dataChanged.emit(index, index, [role])
            return True
        return False
