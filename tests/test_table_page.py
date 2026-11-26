import pytest
from kubescope.extensions import testing
from kubescope.sdk import CONTEXT_CHANGED
from kubescope.sdk.errors import ClusterError

from kubescope.custom_resources.table_page import Row, TablePage


class Page(TablePage):
    """A list of what the test says."""

    def __init__(self, ctx, rows, namespaced=True) -> None:
        super().__init__(
            ctx, ["Namespace", "Name", "Phase"], [100, 100], "Thing", namespaced
        )
        self.answer = rows
        self.buttons = 0

    def fetch(self):
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer

    def refresh_buttons(self) -> None:
        self.buttons += 1


def row(name, namespace="ns", **fields):
    return Row(namespace, name, (namespace, name, "Ok"), {"name": name}, **fields)


def cell(page, index, column):
    return page.table.item(index, column)


def names(page):
    return [cell(page, i, 1).text() for i in range(page.table.rowCount())]


def test_a_page_lists_what_it_fetches_with_the_summary_and_footer(ctx) -> None:
    page = Page(ctx, [row("a", "one"), row("b", "two")])

    page.shown()

    assert page.timer.isActive()
    assert names(page) == ["a", "b"]
    assert page.summary.text() == "2 of 2 resources"
    assert page.footer.text() == "2 resources in 2 namespaces"
    assert page.notice.isHidden()
    assert page.table.verticalHeader().defaultSectionSize() == 46
    assert [page.table.horizontalHeaderItem(i).text() for i in range(3)] == [  # type: ignore[union-attr]
        "NAMESPACE",
        "NAME",
        "PHASE",
    ]


def test_a_list_with_no_namespace_hides_the_filter(ctx) -> None:
    page = Page(ctx, [row("a", "")], namespaced=False)

    page.load()

    assert page.namespaces.isHidden() and page.filter_label.isHidden()
    assert page.footer.text() == "1 resources"


def test_badges_and_tips_go_to_the_cells(ctx) -> None:
    page = Page(ctx, [row("a", badges={2: ("#176b58", "#e5f4eb")}, tips={2: "why"})])

    page.load()

    assert testing.badge_of(cell(page, 0, 2)) == ("#176b58", "#e5f4eb")
    assert cell(page, 0, 2).toolTip() == "why"
    assert testing.badge_of(cell(page, 0, 1)) is None


def test_the_filters_narrow_the_list_and_keep_the_choice(ctx) -> None:
    page = Page(ctx, [row("api", "one"), row("web", "two"), row("worker", "two")])
    page.load()

    page.namespaces.setCurrentIndex(page.namespaces.findData("two"))
    assert names(page) == ["web", "worker"]
    assert page.summary.text() == "2 of 3 resources"

    page.search.setText("WOR")
    assert names(page) == ["worker"]

    page.load()  # the choice stays after a new read
    assert names(page) == ["worker"]
    assert page.namespaces.currentData() == "two"


def test_it_says_when_the_cluster_does_not_serve_it(ctx) -> None:
    page = Page(ctx, None)

    page.load()

    assert page.table.rowCount() == 0
    assert page.notice.text() == "The cluster does not serve this resource."
    assert not page.notice.isHidden()


def test_it_says_why_it_could_not_read(ctx) -> None:
    page = Page(ctx, ClusterError("forbidden\nmore"))

    page.load()

    assert page.notice.text() == "Could not read the resources: forbidden"
    assert page.loading is False


def test_it_waits_for_a_context_a_window_and_the_last_read(ctx) -> None:
    page = Page(ctx, [row("a")])
    ctx.current_context = None
    page.load()
    ctx.current_context = "prod"
    page.loading = True
    page.load()
    page.loading = False
    ui, ctx.ui = ctx.ui, None
    page.load()
    ctx.ui = ui

    assert page.table.rowCount() == 0


def test_it_reads_again_on_a_context_and_stops_when_hidden(ctx) -> None:
    page = Page(ctx, [row("a")])
    page.shown()
    page.rows = []

    ctx.events.fire(CONTEXT_CHANGED, context="dev")
    assert names(page) == ["a"]

    page.hidden()
    assert not page.timer.isActive()


def test_the_selection_survives_a_new_read_and_feeds_the_buttons(ctx) -> None:
    page = Page(ctx, [row("a"), row("b")])
    page.load()
    before = page.buttons

    page.table.selectRow(1)
    page.load()

    selected = page.selected()
    assert selected is not None and selected.name == "b"
    assert page.buttons > before
    assert page.details.isEnabled()


def test_a_page_has_no_selection_without_one_and_no_details_without_a_document(
    ctx,
) -> None:
    page = Page(ctx, [Row("ns", "a", ("ns", "a", "Ok"))])
    page.load()
    assert page.selected() is None and not page.details.isEnabled()

    page.table.selectRow(0)
    assert not page.details.isEnabled()  # nothing to show of it
    page.show_details()  # and nothing happens


def test_the_details_show_the_document_of_the_row(ctx) -> None:
    shown: list = []
    ctx.ui.show_json = lambda title, document: shown.append((title, document))
    page = Page(ctx, [row("a")])
    page.load()
    page.show_details()  # nothing selected
    page.table.selectRow(0)

    page.show_details()
    ui, ctx.ui = ctx.ui, None
    page.show_details()  # no window
    ctx.ui = ui

    assert shown == [("Thing a", {"name": "a"})]
    assert page.themed("#fff") == "#fff"


def test_a_subclass_adds_a_button_before_the_details(ctx) -> None:
    page = Page(ctx, [])
    called: list[int] = []

    button = page.add_button("Do", lambda: called.append(1))
    button.click()

    assert called == [1]
    testing.settle()  # a newer app takes the button into its bar
    row = page.action_row
    if row.indexOf(page.details) < 0:  # the buttons are in the bar of the app
        bar = page.details.parentWidget()
        assert bar is not None
        row = bar.layout()
    assert row.indexOf(button) < row.indexOf(page.details)


def test_the_base_page_does_not_know_what_it_lists(ctx) -> None:
    with pytest.raises(NotImplementedError):
        TablePage(ctx, ["A"], [10], "T").fetch()
    TablePage(ctx, ["A"], [10], "T").refresh_buttons()


def test_the_refresh_button_reads_out_loud_and_the_background_reads_quietly(
    ctx,
) -> None:
    page = Page(ctx, [row("a")])

    page.load()
    page.reload()
    page.timer.timeout.emit()

    assert ctx.ui.quiet == [True, False, True]


def test_the_context_menu_of_a_row_has_the_details_and_selects_the_row(
    ctx, monkeypatch
) -> None:
    page = Page(ctx, [row("a"), row("b")])
    page.widget.resize(900, 500)
    page.widget.show()
    page.load()
    shown: list[tuple[list[str], str]] = []

    def open_menu(menu, _table, _x, _y):
        selected = page.selected()
        assert selected is not None
        shown.append(([a.text() for a in menu.actions()], selected.name))
        menu.actions()[0].trigger()

    monkeypatch.setattr(page.components, "show_menu", open_menu)
    opened: list[str] = []
    ctx.ui.show_json = lambda title, document: opened.append(title)

    page.show_menu(10, page.table.rowViewportPosition(1) + 5)
    page.show_menu(10, 5000)  # below the rows: no menu

    assert shown == [(["Details"], "b")]
    assert opened == ["Thing b"]


def test_a_row_with_nothing_to_show_has_no_menu(ctx, monkeypatch) -> None:
    page = Page(ctx, [Row("ns", "a", ("ns", "a", "Ok"))])
    page.widget.resize(900, 500)
    page.widget.show()
    page.load()
    opened: list = []
    monkeypatch.setattr(page.components, "show_menu", lambda *_: opened.append(1))

    page.show_menu(10, page.table.rowViewportPosition(0) + 5)

    assert opened == []


def test_a_click_on_a_header_sorts_the_list_and_a_second_one_reverses_it(ctx) -> None:
    page = Page(ctx, [row("b"), row("a"), row("c")])
    page.shown()
    assert names(page) == ["b", "a", "c"]

    page.sorter.clicked(1)
    assert names(page) == ["a", "b", "c"]
    assert page.table.horizontalHeader().sortIndicatorSection() == 1  # type: ignore[union-attr]

    page.sorter.clicked(1)
    assert names(page) == ["c", "b", "a"]

    page.sorter.clicked(2)  # the same phase everywhere: the order it was read in
    assert names(page) == ["b", "a", "c"]

    page.sorter.clicked(1)
    page.loaded([row("z"), row("y")])  # read again: the sort stays
    assert names(page) == ["y", "z"]


def test_a_cell_the_row_does_not_have_sorts_as_empty(ctx) -> None:
    page = Page(ctx, [Row("ns", "short", ("ns",)), row("a")])
    page.shown()
    page.sorter.clicked(2)
    assert [shown.name for shown in page.shown_rows] == ["a", "short"]


def test_the_icons_of_the_buttons_and_of_the_menu_are_the_ones_of_the_app(ctx) -> None:
    page = Page(ctx, [])
    assert not page.details.icon().isNull()  # the info icon of the app

    button = page.add_button("Do", lambda: None, "refresh")
    assert not button.icon().isNull()
    assert page.add_button("Plain", lambda: None).icon().isNull()  # none asked for

    menu = page.components.menu(page.widget)
    page.add_action(menu, "With", lambda: None, "refresh")
    page.add_action(menu, "Without", lambda: None)
    entries = {action.text(): action for action in menu.actions()}
    assert not entries["With"].icon().isNull()
    assert entries["Without"].icon().isNull()


def test_an_icon_that_an_older_app_does_not_have_is_left_out(ctx, monkeypatch) -> None:
    page = Page(ctx, [])

    def missing(*_args, **_options):
        raise KeyError("refresh")

    monkeypatch.setattr(page.components, "icon", missing)
    assert page.icon("refresh") is None
    assert page.add_button("Do", lambda: None, "refresh").icon().isNull()
    menu = page.components.menu(page.widget)
    page.add_action(menu, "Do", lambda: None, "refresh")  # the entry is there, bare
    assert [action.text() for action in menu.actions()] == ["Do"]
