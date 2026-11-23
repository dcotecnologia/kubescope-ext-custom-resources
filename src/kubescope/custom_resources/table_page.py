"""The page of a list, laid out like the lists of the app: a filter bar, the
summary with the buttons of the actions, the table and a footer.

A subclass says what it lists (`fetch`) and may add buttons. The rows
are filtered by namespace and by a search, and the page reads again
every 30 seconds while it is open.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from kubescope.sdk import CONTEXT_CHANGED, Context
from kubescope.sdk.errors import first_line
from PySide6.QtCore import QCoreApplication, QPoint, Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from kubescope.custom_resources.badge import BADGE_ROLE, BadgeDelegate

POLL_SECONDS = 30  # how often the page looks again while it is shown
ALL = ""  # the filter that shows every namespace
TEXT_COLOR = "#242a33"
ROW_HEIGHT = 46  # as the rows of the Pods


@dataclass(frozen=True, eq=False)
class Row:
    """One line of a list: what its cells say, and what the page needs to act
    on it."""

    namespace: str
    name: str
    cells: tuple[str, ...]
    document: dict[str, Any] | None = None  # the object, for the Details
    badges: dict[int, tuple[str, str]] = field(default_factory=dict)  # (text, fill)
    tips: dict[int, str] = field(default_factory=dict)
    payload: Any = None  # whatever the subclass keeps of the object

    @property
    def key(self) -> tuple[str, str]:
        return (self.namespace, self.name)


class TablePage(QWidget):
    def __init__(
        self,
        ctx: Context,
        headers: Sequence[str],
        widths: Sequence[int],
        title: str,
        namespaced: bool = True,
    ) -> None:
        super().__init__()
        self.ctx = ctx
        self.title = title
        self.namespaced = namespaced
        self.rows: list[Row] = []
        self.shown_rows: list[Row] = []
        self.loading = False
        self.error = ""
        self.info = (
            ""  # a note that is not an error, while the page waits for something
        )

        self.namespaces = QComboBox()
        self.namespaces.setProperty("variant", "filter")
        self.namespaces.setMinimumSize(170, 38)
        self.namespaces.currentIndexChanged.connect(self.show_rows)
        self.search = QLineEdit()
        self.search.setObjectName("searchInput")
        self.search.setMinimumSize(240, 38)
        self.search.setMaximumWidth(300)
        self.search.setPlaceholderText(
            QCoreApplication.translate("TablePage", "Search all columns...")
        )
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.show_rows)

        self.summary = QLabel()
        self.summary.setObjectName("summaryLabel")
        self.details = QPushButton(QCoreApplication.translate("TablePage", "Details"))
        self.details.setProperty("variant", "secondary")
        self.details.clicked.connect(self.show_details)

        self.table = QTableWidget(0, len(headers))
        self.table.setProperty("variant", "data")
        self.table.setHorizontalHeaderLabels([text.upper() for text in headers])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
        self.table.setShowGrid(False)  # the rows draw their own divider
        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        for column, width in enumerate(widths):
            self.table.setColumnWidth(column, width)
        self.table.setItemDelegate(BadgeDelegate(self.table))
        self.table.itemSelectionChanged.connect(self.show_buttons)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_menu)

        self.notice = QLabel()
        self.notice.setProperty("variant", "muted")
        self.notice.setWordWrap(True)
        self.footer = QLabel()
        self.footer.setProperty("variant", "muted")
        note = QLabel(
            QCoreApplication.translate("TablePage", "Data fetched from the cluster API")
        )
        note.setProperty("variant", "muted")

        filters = QHBoxLayout()
        filters.setSpacing(12)
        self.filter_label = QLabel(
            QCoreApplication.translate("TablePage", "Namespace").upper()
        )
        self.filter_label.setObjectName("filterLabel")
        filters.addWidget(self.filter_label)
        filters.addWidget(self.namespaces)
        filters.addWidget(self.search)
        filters.addStretch(1)
        self.filter_label.setVisible(namespaced)
        self.namespaces.setVisible(namespaced)
        self.action_row = QHBoxLayout()
        self.action_row.addWidget(self.summary)
        self.action_row.addStretch(1)
        self.action_row.addWidget(self.details)
        footer = QHBoxLayout()
        footer.addWidget(self.footer)
        footer.addStretch(1)
        footer.addWidget(note)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 22)
        layout.setSpacing(14)
        layout.addLayout(filters)
        layout.addLayout(self.action_row)
        layout.addWidget(self.notice)
        layout.addWidget(self.table, 1)
        layout.addLayout(footer)

        self.timer = QTimer(self)
        self.timer.setInterval(POLL_SECONDS * 1000)
        self.timer.timeout.connect(lambda: self.load())
        ctx.events.on(CONTEXT_CHANGED, lambda **_: self.load())
        ctx.on_unload(self.timer.stop)

    # what a subclass says

    def fetch(self) -> list[Row] | None:
        """The rows, read off the UI thread; None when the cluster does not
        serve what the page lists."""
        raise NotImplementedError

    def refresh_buttons(self) -> None:
        """The selection or the rows changed: enable the buttons it added."""

    def extend_menu(self, menu: QMenu, row: Row) -> None:
        """The menu of a row (right click) has the Details; add what else the
        page can do with it."""

    def add_button(self, text: str, handler: Callable[[], None]) -> QPushButton:
        """Put a button of an action in the summary row, before the Details."""
        button = QPushButton(text)
        button.setProperty("variant", "secondary")
        button.clicked.connect(handler)
        self.action_row.insertWidget(self.action_row.count() - 1, button)
        return button

    # what the app calls

    def shown(self) -> None:
        """Called each time the page is opened."""
        self.load()
        self.timer.start()

    def hideEvent(self, event) -> None:
        self.timer.stop()
        super().hideEvent(event)

    # reading

    def load(self, quiet: bool = True) -> None:
        """Read the rows.

        The reads in the background are quiet; the one the person asks
        for (the refresh button) is not, so the button spins.
        """
        if self.ctx.current_context is None or self.ctx.ui is None or self.loading:
            return
        self.loading = True
        self.ctx.ui.run_action(
            self.fetch, self.loaded, on_error=self.load_failed, quiet=quiet
        )

    def reload(self) -> None:
        """The refresh button of the header."""
        self.load(quiet=False)

    def loaded(self, rows: list[Row] | None) -> None:
        self.loading = False
        self.error = ""
        if rows is None:
            self.rows = []
            self.error = QCoreApplication.translate(
                "TablePage", "The cluster does not serve this resource."
            )
        else:
            self.rows = rows
        self.refill_namespaces()
        self.show_rows()

    def load_failed(self, message: str) -> None:
        self.loading = False
        self.error = QCoreApplication.translate(
            "TablePage", "Could not read the resources: {0}"
        ).format(first_line(message))
        self.show_rows()

    # showing

    def refill_namespaces(self) -> None:
        chosen = self.namespaces.currentData()
        self.namespaces.blockSignals(True)
        self.namespaces.clear()
        self.namespaces.addItem(
            QCoreApplication.translate("TablePage", "All namespaces"), ALL
        )
        for namespace in sorted({row.namespace for row in self.rows}):
            self.namespaces.addItem(namespace, namespace)
        index = self.namespaces.findData(chosen)
        self.namespaces.setCurrentIndex(max(index, 0))
        self.namespaces.blockSignals(False)

    def visible(self) -> list[Row]:
        chosen = self.namespaces.currentData()
        needle = self.search.text().strip().casefold()
        return [
            row
            for row in self.rows
            if (not chosen or row.namespace == chosen)
            and (not needle or any(needle in text.casefold() for text in row.cells))
        ]

    def selected(self) -> Row | None:
        rows = self.table.selectionModel().selectedRows()
        return self.shown_rows[rows[0].row()] if rows else None

    def themed(self, color: str) -> str:
        ui = self.ctx.ui
        return str(ui.themed(color)) if ui is not None else color

    def show_rows(self, *_: object) -> None:
        kept = self.selected()
        rows = self.visible()
        self.shown_rows = rows
        self.notice.setText(self.error or self.info)
        self.notice.setVisible(bool(self.error or self.info))
        self.summary.setText(
            QCoreApplication.translate("TablePage", "{0} of {1} resources").format(
                len(rows), len(self.rows)
            )
        )
        if self.namespaced:
            namespaces = len({row.namespace for row in self.rows})
            self.footer.setText(
                QCoreApplication.translate(
                    "TablePage", "{0} resources in {1} namespaces"
                ).format(len(self.rows), namespaces)
            )
        else:
            self.footer.setText(
                QCoreApplication.translate("TablePage", "{0} resources").format(
                    len(self.rows)
                )
            )
        self.table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            self.fill_row(index, row)
        keys = [row.key for row in rows]
        if kept is not None and kept.key in keys:
            self.table.selectRow(keys.index(kept.key))
        self.show_buttons()

    def fill_row(self, index: int, row: Row) -> None:
        for column, text in enumerate(row.cells):
            item = QTableWidgetItem(text)
            item.setForeground(QColor(self.themed(TEXT_COLOR)))
            if column in row.badges:
                color, fill = row.badges[column]
                item.setData(BADGE_ROLE, (self.themed(color), self.themed(fill)))
            if column in row.tips:
                item.setToolTip(row.tips[column])
            self.table.setItem(index, column, item)

    def show_buttons(self) -> None:
        row = self.selected()
        self.details.setEnabled(row is not None and row.document is not None)
        self.refresh_buttons()

    def show_details(self) -> None:
        row = self.selected()
        if row is None or row.document is None or self.ctx.ui is None:
            return
        self.ctx.ui.show_json(f"{self.title} {row.name}", row.document)

    def show_menu(self, position: QPoint) -> None:
        """The menu of the row under the pointer, which is selected first."""
        index = self.table.rowAt(position.y())
        if index < 0 or index >= len(self.shown_rows):
            return
        self.table.selectRow(index)
        row = self.shown_rows[index]
        menu = QMenu(self)
        if row.document is not None:
            menu.addAction(
                QCoreApplication.translate("TablePage", "Details"), self.show_details
            )
        self.extend_menu(menu, row)
        if not menu.isEmpty():
            self.open_menu(menu, self.table.viewport().mapToGlobal(position))

    def open_menu(self, menu: QMenu, position: QPoint) -> None:
        menu.exec(position)
