from collections.abc import Callable
from typing import cast

from kubescope.sdk import WRITE_MODE_CHANGED
from kubescope.sdk.errors import ClusterError
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QMessageBox, QTableWidgetItem

from kubescope.custom_resources.badge import BADGE_ROLE
from kubescope.custom_resources.crd import Definition
from kubescope.custom_resources.external_secrets_page import ExternalSecretsPage

ES = Definition(
    "external-secrets.io", "ExternalSecret", "externalsecrets", "v1", True, ()
)


def make(ctx, item, *names, **fields):
    ctx.cluster.documents["externalsecrets"] = {
        "items": [item(n, **fields) for n in names]
    }
    page = ExternalSecretsPage(ctx, ES)
    page.load()
    return page


def follow_ups(page, monkeypatch):
    """Keep the reads the page schedules after a resync, to run them by
    hand."""
    scheduled: list[tuple[int, Callable[[], None]]] = []
    monkeypatch.setattr(
        page, "after", lambda delay, call: scheduled.append((delay, call))
    )
    return scheduled


def answer(page, monkeypatch, yes=True):
    asked: list[str] = []

    def confirm(text):
        asked.append(text)
        return yes

    monkeypatch.setattr(page, "confirm", confirm)
    return asked


def cell(page, row, column) -> QTableWidgetItem:
    return cast(QTableWidgetItem, page.table.item(row, column))


def names(page):
    return [cell(page, r, 0).text() for r in range(page.table.rowCount())]


def test_it_lists_every_externalsecret_with_how_its_sync_went(ctx, item) -> None:
    ctx.cluster.documents["externalsecrets"] = {
        "items": [
            item("a", "one"),
            item("b", "two", ready="False", reason="SecretSyncedError"),
            item("c", "two", ready="Unknown", reason=""),
            item("d", "two", reason="SecretDeleted"),
        ]
    }
    page = ExternalSecretsPage(ctx, ES)

    page.load()

    assert names(page) == ["a", "b", "c", "d"]
    assert cell(page, 0, 1).text() == "ClusterSecretStore/vault"
    assert [cell(page, r, 2).text() for r in range(4)] == [
        "Synced",
        "Error",
        "Unknown",
        "Deleted",
    ]
    assert cell(page, 1, 2).toolTip() == "m"
    assert cell(page, 1, 3).text() == "SecretSyncedError"
    assert cell(page, 0, 5).text() == "1h"
    assert cell(page, 0, 2).data(BADGE_ROLE) == ("#176b58", "#e5f4eb")
    assert cell(page, 1, 2).data(BADGE_ROLE) == ("#a33d45", "#fce9ea")
    assert cell(page, 2, 2).data(BADGE_ROLE) == ("#505963", "#eff1f3")
    assert cell(page, 3, 2).data(BADGE_ROLE) == ("#985415", "#fff2de")
    assert page.rows[0].document == ctx.cluster.documents["externalsecrets"]["items"][0]


def test_a_secret_that_never_synced_and_has_no_store_reads_plainly(ctx) -> None:
    ctx.cluster.documents["externalsecrets"] = {
        "items": [{"metadata": {"name": "a"}, "spec": {}}]
    }
    page = ExternalSecretsPage(ctx, ES)
    page.load()

    assert cell(page, 0, 1).text() == ""
    assert cell(page, 0, 4).text() == "never"
    assert page.rows[0].document is not None


def test_a_definition_that_is_not_served_says_so(ctx) -> None:
    page = ExternalSecretsPage(ctx, ES)

    page.load()

    assert "does not serve" in page.notice.text()


def test_the_buttons_follow_the_selection_and_the_write_mode(ctx, item) -> None:
    page = make(ctx, item, "a")
    assert not page.resync_button.isEnabled()  # nothing selected
    assert page.resync_all.isEnabled()

    page.table.selectRow(0)
    assert page.resync_button.isEnabled()

    ctx.app.write_mode = False
    ctx.events.fire(WRITE_MODE_CHANGED, write_mode=False)
    assert not page.resync_button.isEnabled() and not page.resync_all.isEnabled()
    assert page.resync_all.toolTip() == "Turn on the write mode to resync."


def test_resync_asks_first_and_patches_the_one_selected(ctx, item, monkeypatch) -> None:
    page = make(ctx, item, "a", "b")
    asked = answer(page, monkeypatch)
    follow_ups(page, monkeypatch)
    page.table.selectRow(1)

    page.resync_button.click()

    assert asked == ["Resync b in ns?"]
    assert [p[5] for p in ctx.writes.patches] == ["b"]
    assert ctx.writes.patches[0][1:4] == (
        "external-secrets.io",
        "v1",
        "externalsecrets",
    )
    assert ctx.ui.messages == []


def test_a_refused_resync_changes_nothing(ctx, item, monkeypatch) -> None:
    page = make(ctx, item, "a")
    answer(page, monkeypatch, yes=False)
    page.table.selectRow(0)

    page.resync_button.click()

    assert ctx.writes.patches == []


def test_resync_is_not_done_without_a_selection_or_the_write_mode(
    ctx, item, monkeypatch
) -> None:
    page = make(ctx, item, "a")
    asked = answer(page, monkeypatch)

    page.ask_resync_selected()  # nothing selected
    page.table.selectRow(0)
    ctx.app.write_mode = False
    page.ask_resync_selected()
    page.ask_resync_all()

    assert asked == [] and ctx.writes.patches == []


def test_resync_all_covers_what_the_filters_show(ctx, item, monkeypatch) -> None:
    ctx.cluster.documents["externalsecrets"] = {
        "items": [item("a", "one"), item("b", "two"), item("c", "two")]
    }
    page = ExternalSecretsPage(ctx, ES)
    page.load()
    page.namespaces.setCurrentIndex(page.namespaces.findData("two"))
    asked = answer(page, monkeypatch)

    page.resync_all.click()

    assert asked == ["Resync the 2 resources shown?"]
    assert [p[5] for p in ctx.writes.patches] == ["b", "c"]


def test_resync_all_with_nothing_shown_does_nothing(ctx, monkeypatch) -> None:
    ctx.cluster.documents["externalsecrets"] = {"items": []}
    page = ExternalSecretsPage(ctx, ES)
    page.load()
    asked = answer(page, monkeypatch)

    page.ask_resync_all()

    assert asked == []


def test_resync_all_says_which_failed_and_goes_on(ctx, item, monkeypatch) -> None:
    page = make(ctx, item, "a", "b", "c")
    answer(page, monkeypatch)
    scheduled = follow_ups(page, monkeypatch)
    ctx.writes.failing["b"] = ClusterError("forbidden\nsecond line")

    page.resync_all.click()

    assert [p[5] for p in ctx.writes.patches] == ["a", "c"]
    ((icon, _title, text),) = ctx.ui.messages
    assert icon == "warning"
    assert text == "1 of 3 could not be resynced:\nns/b: forbidden"
    assert "Resync asked for 2" in page.notice.text()  # of the ones that went
    assert len(scheduled) == 3


def test_a_failure_of_the_whole_resync_is_shown(ctx, item, monkeypatch) -> None:
    page = make(ctx, item, "a")
    answer(page, monkeypatch)
    scheduled = follow_ups(page, monkeypatch)
    ctx.writes.failing["a"] = RuntimeError("boom\nmore")
    page.table.selectRow(0)

    page.resync_button.click()

    assert ctx.ui.messages == [("critical", "Resync", "boom")]
    assert scheduled == []


def test_nothing_is_done_without_a_window(ctx, item, monkeypatch) -> None:
    page = make(ctx, item, "a")
    answer(page, monkeypatch)
    page.table.selectRow(0)
    ctx.ui = None

    page.ask_resync_selected()
    page.tell("warning", "x")

    assert ctx.writes.patches == []


def test_the_context_menu_offers_the_resync_of_the_row_in_the_write_mode(
    ctx, item, monkeypatch
) -> None:
    page = make(ctx, item, "a")
    page.resize(900, 500)
    page.show()
    shown: list[list[str]] = []
    monkeypatch.setattr(
        page,
        "open_menu",
        lambda menu, _at: shown.append([a.text() for a in menu.actions()]),
    )
    on_row = QPoint(10, page.table.rowViewportPosition(0) + 5)

    page.show_menu(on_row)  # the write mode is on
    ctx.app.write_mode = False
    page.show_menu(on_row)  # without it: the Details only

    assert shown == [["Details", "Resync"], ["Details"]]


def test_the_confirmation_is_a_yes_no_question(ctx, item, monkeypatch) -> None:
    page = make(ctx, item, "a")
    seen: list = []
    monkeypatch.setattr(
        QMessageBox,
        "exec",
        lambda box: seen.append(box.text()) or QMessageBox.StandardButton.Yes,
    )

    assert page.confirm("Sure?") is True
    assert seen == ["Sure?"]
    ctx.ui = None
    assert page.confirm("Sure?") is True


def test_nothing_is_waited_for_when_every_resync_failed(ctx, item, monkeypatch) -> None:
    page = make(ctx, item, "a")
    answer(page, monkeypatch)
    scheduled = follow_ups(page, monkeypatch)
    ctx.writes.failing["a"] = ClusterError("forbidden")
    page.table.selectRow(0)

    page.resync_button.click()

    assert scheduled == []
    assert page.notice.isHidden()


def test_after_a_resync_it_waits_for_the_operator_and_reads_until_it_shows(
    ctx, item, monkeypatch
) -> None:
    page = make(ctx, item, "a")
    answer(page, monkeypatch)
    scheduled = follow_ups(page, monkeypatch)
    page.table.selectRow(0)
    page.resync_button.click()

    assert [delay for delay, _call in scheduled] == [1000, 4000, 10000]
    assert page.notice.text() == "Resync asked for 1; waiting for the operator..."
    assert not page.notice.isHidden()

    asked = len(ctx.cluster.asked)
    ctx.cluster.documents["externalsecrets"] = {
        "items": [item("a", reason="SecretSynced")]
    }
    ctx.cluster.documents["externalsecrets"]["items"][0]["status"]["refreshTime"] = (
        "2099-01-01T00:00:00Z"
    )
    scheduled[0][1]()  # the first look
    assert len(ctx.cluster.asked) == asked + 1
    assert cell(page, 0, 4).text() == "0s"  # the sync shows
    assert page.notice.text() != ""  # still waiting for the others

    page.loading = True  # a read that was on its way does not stop the next
    scheduled[1][1]()
    scheduled[2][1]()  # the last look: the note goes
    assert len(ctx.cluster.asked) == asked + 3
    assert page.notice.isHidden()


def test_a_look_is_scheduled_on_the_page_itself(ctx, item, monkeypatch) -> None:
    from PySide6.QtCore import QTimer

    page = make(ctx, item, "a")
    seen: list[tuple] = []
    monkeypatch.setattr(QTimer, "singleShot", lambda *args: seen.append(args))

    def call() -> None: ...

    page.after(500, call)

    assert seen == [(500, page, call)]
