"""The page of a list, laid out like the lists of the app: a filter bar, the
summary with the buttons of the actions, the table and a footer.

A subclass says what it lists (`fetch`) and may add buttons. The rows
are filtered by namespace and by a search, and the page reads again
every 30 seconds while it is open.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from kubescope.sdk import CONTEXT_CHANGED, Components, Context, translate
from kubescope.sdk.errors import first_line
from kubescope.sdk.models import natural_key

POLL_SECONDS = 30  # how often the page looks again while it is shown
ALL = ""  # the filter that shows every namespace
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


class TablePage:
    def __init__(
        self,
        ctx: Context,
        headers: Sequence[str],
        widths: Sequence[int],
        title: str,
        namespaced: bool = True,
    ) -> None:
        self.ctx = ctx
        self.title = title
        self.namespaced = namespaced
        self.rows: list[Row] = []
        self.shown_rows: list[Row] = []
        self.loading = False
        self.sort: tuple[int, bool] | None = None  # the header clicked
        self.error = ""
        self.info = (
            ""  # a note that is not an error, while the page waits for something
        )

        components = self.components
        self.widget = components.widget(shown=self.shown, hidden=self.hidden)
        self.namespaces = components.filter_select()
        self.namespaces.currentIndexChanged.connect(self.show_rows)
        self.search = components.search_box(
            translate("TablePage", "Search all columns...")
        )
        self.search.textChanged.connect(self.show_rows)

        self.summary = components.label(variant="summary")
        self.details = components.button(
            translate("TablePage", "Details"),
            on_click=self.show_details,
        )

        self.table = components.data_table([text.upper() for text in headers], widths)
        self.sorter = components.header_sorter(self.table, self.ordered)
        self.table.itemSelectionChanged.connect(self.show_buttons)
        components.on_context_menu(self.table, self.show_menu)

        self.notice = components.label(variant="muted", wrap=True)
        self.footer = components.label(variant="muted")
        note = components.muted_label(
            translate("TablePage", "Data fetched from the cluster API")
        )

        self.filter_label = components.label(
            translate("TablePage", "Namespace").upper(), "filter"
        )
        self.filter_label.setVisible(namespaced)
        self.namespaces.setVisible(namespaced)
        self.action_row = components.row(self.summary, None, self.details, spacing=6)
        components.page(
            self.widget,
            filters=components.row(
                self.filter_label, self.namespaces, self.search, None
            ),
            actions=self.action_row,
            notice=self.notice,
            body=self.table,
            footer=components.row(self.footer, None, note),
        )

        self.timer = components.timer(
            POLL_SECONDS * 1000, lambda: self.load(), self.widget
        )
        ctx.events.on(CONTEXT_CHANGED, lambda **_: self.load())
        ctx.on_unload(self.timer.stop)

    # what a subclass says

    def fetch(self) -> list[Row] | None:
        """The rows, read off the UI thread; None when the cluster does not
        serve what the page lists."""
        raise NotImplementedError

    def refresh_buttons(self) -> None:
        """The selection or the rows changed: enable the buttons it added."""

    def extend_menu(self, menu: Any, row: Row) -> None:
        """The menu of a row (right click) has the Details; add what else the
        page can do with it."""

    def add_button(self, text: str, handler: Callable[[], None]) -> Any:
        """Put a button of an action in the summary row, before the Details."""
        button = self.components.button(text, on_click=handler)
        self.action_row.insertWidget(self.action_row.count() - 1, button)
        return button

    # what the app calls

    def shown(self) -> None:
        """Called each time the page is opened."""
        self.load()
        self.timer.start()

    def hidden(self) -> None:
        self.timer.stop()

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
            self.error = translate(
                "TablePage", "The cluster does not serve this resource."
            )
        else:
            self.rows = rows
        self.refill_namespaces()
        self.show_rows()

    def load_failed(self, message: str) -> None:
        self.loading = False
        self.error = translate("TablePage", "Could not read the resources: {0}").format(
            first_line(message)
        )
        self.show_rows()

    # showing

    def refill_namespaces(self) -> None:
        chosen = self.namespaces.currentData()
        self.namespaces.blockSignals(True)
        self.namespaces.clear()
        self.namespaces.addItem(translate("TablePage", "All namespaces"), ALL)
        for namespace in sorted({row.namespace for row in self.rows}):
            self.namespaces.addItem(namespace, namespace)
        index = self.namespaces.findData(chosen)
        self.namespaces.setCurrentIndex(max(index, 0))
        self.namespaces.blockSignals(False)

    def visible(self) -> list[Row]:
        chosen = self.namespaces.currentData()
        needle = self.search.text().strip().casefold()
        rows = [
            row
            for row in self.rows
            if (not chosen or row.namespace == chosen)
            and (not needle or any(needle in text.casefold() for text in row.cells))
        ]
        if self.sort is not None:
            column, descending = self.sort
            rows.sort(
                key=lambda row: natural_key(
                    row.cells[column] if column < len(row.cells) else ""
                ),
                reverse=descending,
            )
        return rows

    def ordered(self, column: int, descending: bool) -> None:
        """A click on a header: the rows in that order."""
        self.sort = (column, descending)
        self.show_rows()

    @property
    def components(self) -> Components:
        """The elements of the app; a page is only built in a window."""
        ui = self.ctx.ui
        assert ui is not None
        return ui.components

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
            translate("TablePage", "{0} of {1} resources").format(
                len(rows), len(self.rows)
            )
        )
        if self.namespaced:
            namespaces = len({row.namespace for row in self.rows})
            self.footer.setText(
                translate("TablePage", "{0} resources in {1} namespaces").format(
                    len(self.rows), namespaces
                )
            )
        else:
            self.footer.setText(
                translate("TablePage", "{0} resources").format(len(self.rows))
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
            item = self.components.table_item(text)
            if column in row.badges:
                color, fill = row.badges[column]
                self.components.set_badge_colors(
                    item, self.themed(color), self.themed(fill)
                )
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

    def show_menu(self, x: int, y: int) -> None:
        """The menu of the row under the pointer, which is selected first."""
        index = self.table.rowAt(y)
        if index < 0 or index >= len(self.shown_rows):
            return
        self.table.selectRow(index)
        row = self.shown_rows[index]
        menu = self.components.menu(self.widget)
        if row.document is not None:
            menu.addAction(translate("TablePage", "Details"), self.show_details)
        self.extend_menu(menu, row)
        if not menu.isEmpty():
            self.components.show_menu(menu, self.table, x, y)
