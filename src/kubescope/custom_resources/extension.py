"""Wires the custom resources into the app: the side menu has the definitions
of the cluster and, for each API group, a page for each of its kinds (the way
Lens lists them), built again when the cluster or its definitions change."""

from typing import Any

from kubescope.sdk import CONTEXT_CHANGED, Context, PageSpec, translate

from kubescope.custom_resources import reader
from kubescope.custom_resources.crd import Definition
from kubescope.custom_resources.external_secrets_page import ExternalSecretsPage
from kubescope.custom_resources.resources_page import (
    DefinitionsPage,
    ResourcesPage,
)
from kubescope.custom_resources.table_page import TablePage

KEY = "custom-resources"  # what `set_pages` calls the pages of the cluster
RETRY_MS = 3000  # to look again while there is no context, or the read failed
MAX_RETRIES = 20  # and no more than this many times in a row


class Menu:
    def __init__(self, ctx: Context) -> None:
        self.ctx = ctx
        self.definitions: list[Definition] | None = None  # None: not read yet
        self.pages: dict[tuple[str, str], Any] = {}
        self.attempts = 0  # looks in a row that found no context or failed
        # The app may not have a context yet when the extension starts, and tells
        # nothing when it gets one: look again until there is one.
        self._timer: Any = None
        ctx.on_unload(self.stop_timer)

    @property
    def timer(self) -> Any:
        """The timer that looks again, made when it is first needed."""
        if self._timer is None:
            ui = self.ctx.ui
            assert ui is not None  # nothing is looked for without a window
            self._timer = ui.components.timer(RETRY_MS, self.retry, single_shot=True)
        return self._timer

    def stop_timer(self) -> None:
        if self._timer is not None:
            self._timer.stop()

    def has_context(self) -> bool:
        return self.ctx.current_context is not None

    def load(self) -> None:
        """Read the definitions of the context and show them in the menu."""
        self.attempts = 0
        self.stop_timer()
        self.read()

    def retry(self) -> None:
        """Look again, as the timer says."""
        self.read()

    def read(self) -> None:
        context = self.ctx.current_context
        ui = self.ctx.ui
        if ui is None:
            return
        if context is None:
            self.update([])
            self.look_again()
            return
        ui.run_action(
            reader.read_definitions,
            lambda definitions: self.answered(context, definitions),
            self.ctx.cluster,
            context,
            on_error=lambda _message: self.failed(context),
            quiet=True,
        )

    def failed(self, context: str) -> None:
        """The definitions could not be read: the menu has only its own entry,
        and the read is tried again."""
        if context == self.ctx.current_context:
            self.update([])
        self.look_again()

    def look_again(self) -> None:
        if self.attempts < MAX_RETRIES:
            self.attempts += 1
            self.timer.start()

    def answered(self, context: str, definitions: list[Definition]) -> None:
        if context == self.ctx.current_context:  # not one of a context left
            self.attempts = 0
            self.update(definitions)

    def update(self, definitions: list[Definition]) -> None:
        """Give the menu these definitions; the menu is built again only when
        they differ from the ones it has."""
        if definitions == self.definitions:
            return
        self.definitions = definitions
        self.pages = {}
        self.ctx.set_pages(KEY, self.specs(definitions))

    def specs(self, definitions: list[Definition]) -> list[PageSpec]:
        section = translate("CustomResourcesExtension", "Custom Resources")
        specs = [
            PageSpec(
                section,
                translate("CustomResourcesExtension", "Definitions"),
                "CRDs",
                self.make_definitions,
                subtitle=translate(
                    "CustomResourcesExtension",
                    "The custom resource definitions of the cluster",
                ),
                visible=self.has_context,
                refresh=self.refresh_definitions,
            )
        ]
        for definition in definitions:
            specs.append(
                PageSpec(
                    section,
                    definition.group,
                    definition.kind,
                    lambda one=definition: self.make(one),
                    subtitle=definition.name,
                    visible=self.has_context,
                    refresh=lambda one=definition: self.refresh(one),
                )
            )
        return specs

    def make_definitions(self) -> Any:
        page = DefinitionsPage(self.ctx, self.update)
        self.pages[("", "")] = page
        return page.widget

    def refresh_definitions(self) -> None:
        page = self.pages.get(("", ""))
        if isinstance(page, DefinitionsPage):
            page.reload()

    def make(self, definition: Definition) -> Any:
        page: TablePage
        if reader.is_external_secret(definition):
            page = ExternalSecretsPage(self.ctx, definition)
        else:
            page = ResourcesPage(self.ctx, definition)
        self.pages[definition.key] = page
        return page.widget

    def refresh(self, definition: Definition) -> None:
        page = self.pages.get(definition.key)
        if isinstance(page, ResourcesPage | ExternalSecretsPage):
            page.reload()


def activate(ctx: Context) -> None:
    menu = Menu(ctx)
    ctx.events.on(CONTEXT_CHANGED, lambda **_: menu.load())
    menu.update([])  # the Definitions entry, until the cluster is read
    menu.load()
