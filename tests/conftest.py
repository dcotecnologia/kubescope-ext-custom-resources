"""Fixtures of the tests of the External Secrets."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication, QWidget


@pytest.fixture(autouse=True)
def delete_the_windows():
    """Delete what a test shows before the application goes away: a window that
    outlives it crashes the run when it ends."""
    if QApplication.instance() is None:
        QApplication([])
    before = set(QApplication.topLevelWidgets())
    yield
    for widget in set(QApplication.topLevelWidgets()) - before:
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


class FakeUi:
    """`ctx.ui`: runs an action at once and remembers what was shown."""

    def __init__(self) -> None:
        self.window = QWidget()
        self.messages: list[tuple] = []
        self.quiet: list[bool] = []  # of each action, in order

    def themed(self, color, text=False):
        return color

    def style_box(self, box) -> None:
        pass

    def show_message(self, icon, title, text) -> None:
        self.messages.append((icon, title, text))

    def run_action(self, function, on_success, *arguments, on_error=None, quiet=False):
        self.quiet.append(quiet)
        try:
            answer = function(*arguments)
        except Exception as error:
            if on_error is None:
                raise
            on_error(str(error))
            return
        on_success(answer)


class FakeCluster:
    def __init__(self) -> None:
        self.documents: dict[str, dict] = {}  # by plural; absent: not served
        self.failure: Exception | None = None
        self.asked: list[tuple] = []

    def get_custom_resources(self, context, group, version, plural, namespace=None):
        self.asked.append((context, group, version, plural, namespace))
        if self.failure is not None:
            raise self.failure
        if plural not in self.documents:
            from kubescope.sdk.errors import ClusterError

            raise ClusterError("the server could not find the requested resource")
        return self.documents[plural]


class FakeWrites:
    def __init__(self) -> None:
        self.patches: list[tuple] = []
        self.failing: dict[str, Exception] = {}  # by name of the ExternalSecret

    def patch_custom_resource(
        self, context, group, version, plural, namespace, name, patch
    ):
        if name in self.failing:
            raise self.failing[name]
        self.patches.append((context, group, version, plural, namespace, name, patch))


class FakeEvents:
    def __init__(self) -> None:
        self.handlers: dict[str, list] = {}

    def on(self, event, handler):
        self.handlers.setdefault(event, []).append(handler)
        return lambda: None

    def fire(self, event, **arguments):
        for handler in self.handlers.get(event, []):
            handler(**arguments)


class FakeApp:
    write_mode = True


class FakeCtx:
    """What the app gives the extension, in the hands of the test."""

    id = "kubescope.custom-resources"

    def __init__(self) -> None:
        self.ui: FakeUi | None = FakeUi()
        self.cluster = FakeCluster()
        self.writes = FakeWrites()
        self.events = FakeEvents()
        self.app = FakeApp()
        self.current_context: str | None = "prod"
        self.pages: list[dict] = []
        self.page_sets: list[tuple[str, list]] = []
        self.cleanups: list = []

    def add_page(self, section, group, title, factory, **options):
        self.pages.append(
            {"section": section, "group": group, "title": title, "factory": factory}
            | options
        )

    def set_pages(self, key, pages) -> None:
        self.page_sets.append((key, list(pages)))

    def on_unload(self, callback) -> None:
        self.cleanups.append(callback)


@pytest.fixture
def ctx():
    return FakeCtx()


def make_item(name, namespace="ns", ready="True", reason="SecretSynced", **fields):
    """An ExternalSecret as the cluster lists it."""
    item = {
        "metadata": {"name": name, "namespace": namespace},
        "spec": {
            "secretStoreRef": {"name": "vault", "kind": "ClusterSecretStore"},
            "refreshInterval": "1h",
            "target": {"name": f"{name}-secret"},
        },
        "status": {
            "refreshTime": "2020-01-01T00:00:00Z",
            "conditions": [
                {"type": "Ready", "status": ready, "reason": reason, "message": "m"}
            ],
        },
    }
    item.update(fields)
    return item


@pytest.fixture
def item():
    return make_item


def make_crd(
    group="a.io",
    kind="Thing",
    plural="things",
    scope="Namespaced",
    versions=None,
    **metadata,
):
    """A CustomResourceDefinition as the cluster lists it."""
    return {
        "metadata": {"name": f"{plural}.{group}", **metadata},
        "spec": {
            "group": group,
            "scope": scope,
            "names": {"kind": kind, "plural": plural},
            "versions": versions
            if versions is not None
            else [{"name": "v1", "served": True, "storage": True}],
        },
    }


@pytest.fixture
def crd():
    return make_crd
