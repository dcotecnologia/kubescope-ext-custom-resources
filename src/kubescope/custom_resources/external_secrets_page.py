"""The list of the ExternalSecrets: how the last sync of each went, a resync of
the one selected and a resync of all the ones shown."""

from collections.abc import Callable

from kubescope.sdk import WRITE_MODE_CHANGED, Context
from kubescope.sdk.errors import first_line
from PySide6.QtCore import QCoreApplication, QTimer
from PySide6.QtWidgets import QMenu, QMessageBox

from kubescope.custom_resources import reader
from kubescope.custom_resources.crd import Definition
from kubescope.custom_resources.model import (
    FAILING,
    SYNCED,
    WARNING,
    ExternalSecret,
    format_interval,
    last_sync_age,
    parse,
)
from kubescope.custom_resources.table_page import Row, TablePage

# the (text, fill) colors of the badge of each state, as the app draws its own
BADGES = {
    SYNCED: ("#176b58", "#e5f4eb"),
    FAILING: ("#a33d45", "#fce9ea"),
    WARNING: ("#985415", "#fff2de"),
}
UNKNOWN_BADGE = ("#505963", "#eff1f3")
WIDTHS = (320, 260, 110, 170, 110)  # the last column takes what is left
# when to read again after a resync, in ms: the operator answers a moment later
FOLLOW_UP = (1000, 4000, 10000)


class ExternalSecretsPage(TablePage):
    def __init__(self, ctx: Context, definition: Definition) -> None:
        headers = [
            QCoreApplication.translate("ExternalSecretsPage", "Name"),
            QCoreApplication.translate("ExternalSecretsPage", "Store"),
            QCoreApplication.translate("ExternalSecretsPage", "Status"),
            QCoreApplication.translate("ExternalSecretsPage", "Reason"),
            QCoreApplication.translate("ExternalSecretsPage", "Last sync"),
            QCoreApplication.translate("ExternalSecretsPage", "Refresh"),
        ]
        super().__init__(ctx, headers, WIDTHS, definition.kind)
        self.definition = definition
        self.resync_button = self.add_button(
            self.tr("Resync"), self.ask_resync_selected
        )
        self.resync_all = self.add_button(self.tr("Resync All"), self.ask_resync_all)
        ctx.events.on(WRITE_MODE_CHANGED, lambda **_: self.show_buttons())

    # reading

    def fetch(self) -> list[Row] | None:
        document = reader.read_resources(
            self.ctx.cluster, self.ctx.current_context or "", self.definition
        )
        if document is None:
            return None
        return [
            self.row_of(secret, document)
            for secret in parse(document, self.definition.version)
        ]

    def row_of(self, secret: ExternalSecret, document: dict) -> Row:
        item = next(
            (
                one
                for one in document.get("items") or []
                if (one.get("metadata") or {}).get("name") == secret.name
                and (one.get("metadata") or {}).get("namespace", "default")
                == secret.namespace
            ),
            None,
        )
        cells = (
            secret.name,
            f"{secret.store_kind}/{secret.store}" if secret.store else "",
            self.state_label(secret),
            secret.reason,
            last_sync_age(secret) or self.tr("never"),
            format_interval(secret.refresh_interval),
        )
        return Row(
            secret.namespace,
            secret.name,
            cells,
            item,
            badges={2: BADGES.get(secret.state, UNKNOWN_BADGE)},
            tips={2: secret.message},
            payload=secret,
        )

    def state_label(self, secret: ExternalSecret) -> str:
        return {
            SYNCED: self.tr("Synced"),
            FAILING: self.tr("Error"),
            WARNING: self.tr("Deleted"),
        }.get(secret.state, self.tr("Unknown"))

    # the buttons

    def writable(self) -> bool:
        return bool(self.ctx.app.write_mode)

    def refresh_buttons(self) -> None:
        writable = self.writable()
        tip = "" if writable else self.tr("Turn on the write mode to resync.")
        self.resync_button.setEnabled(writable and self.selected() is not None)
        self.resync_all.setEnabled(writable and bool(self.shown_rows))
        self.resync_button.setToolTip(tip)
        self.resync_all.setToolTip(tip)
        # what changes the cluster is out of sight while the app is read-only
        self.resync_button.setVisible(writable)
        self.resync_all.setVisible(writable)

    def extend_menu(self, menu: QMenu, row: Row) -> None:
        if self.writable():
            menu.addAction(self.tr("Resync"), self.ask_resync_selected)

    # resync

    def confirm(self, text: str) -> bool:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(self.tr("Resync"))
        box.setText(text)
        box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if self.ctx.ui is not None:
            self.ctx.ui.style_box(box)
        return box.exec() == QMessageBox.StandardButton.Yes

    def secrets_of(self, rows: list[Row]) -> list[ExternalSecret]:
        return [row.payload for row in rows]

    def ask_resync_selected(self) -> None:
        row = self.selected()
        if row is None or not self.writable():
            return
        if self.confirm(self.tr("Resync {0} in {1}?").format(row.name, row.namespace)):
            self.run(self.secrets_of([row]))

    def ask_resync_all(self) -> None:
        rows = self.shown_rows
        if not rows or not self.writable():
            return
        if self.confirm(self.tr("Resync the {0} resources shown?").format(len(rows))):
            self.run(self.secrets_of(rows))

    def resync_these(
        self, secrets: list[ExternalSecret]
    ) -> list[tuple[ExternalSecret, str]]:
        return reader.resync_all(
            self.ctx.writes,
            self.ctx.current_context or "",
            self.definition,
            secrets,
        )

    def run(self, secrets: list[ExternalSecret]) -> None:
        ui = self.ctx.ui
        if ui is None:
            return
        ui.run_action(
            self.resync_these,
            lambda failed: self.resynced(len(secrets), failed),
            secrets,
            on_error=self.resync_failed,
        )

    def resynced(self, total: int, failed: list[tuple[ExternalSecret, str]]) -> None:
        if failed:
            lines = [
                f"{secret.namespace}/{secret.name}: {first_line(message)}"
                for secret, message in failed[:10]
            ]
            self.tell(
                "warning",
                self.tr("{0} of {1} could not be resynced:").format(len(failed), total)
                + "\n"
                + "\n".join(lines),
            )
        done = total - len(failed)
        if done:
            self.follow_up(done)

    def follow_up(self, count: int) -> None:
        """The operator syncs a moment after it is asked: say so, and read the
        cluster again a few times until the status shows it."""
        self.info = self.tr("Resync asked for {0}; waiting for the operator...").format(
            count
        )
        self.show_rows()
        for number, delay in enumerate(FOLLOW_UP):
            last = number == len(FOLLOW_UP) - 1
            self.after(delay, lambda last=last: self.read_again(last))

    def after(self, delay: int, callback: Callable[[], None]) -> None:
        """Call `callback` in `delay` ms, unless the page is gone by then."""
        QTimer.singleShot(delay, self, callback)

    def read_again(self, last: bool) -> None:
        if last:
            self.info = ""
        self.loading = False  # a read that is on its way would show the old status
        self.load()

    def resync_failed(self, message: str) -> None:
        self.tell("critical", first_line(message))

    def tell(self, icon: str, text: str) -> None:
        if self.ctx.ui is not None:
            self.ctx.ui.show_message(icon, self.tr("Resync"), text)
