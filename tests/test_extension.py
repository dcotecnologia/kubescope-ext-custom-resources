from kubescope.sdk import CONTEXT_CHANGED
from kubescope.sdk.errors import ClusterError

import kubescope.custom_resources as package
from kubescope.custom_resources.crd import Definition
from kubescope.custom_resources.extension import KEY, MAX_RETRIES, Menu
from kubescope.custom_resources.external_secrets_page import ExternalSecretsPage
from kubescope.custom_resources.resources_page import DefinitionsPage, ResourcesPage

THING = Definition("a.io", "Thing", "things", "v1", True, ())
ES = Definition(
    "external-secrets.io", "ExternalSecret", "externalsecrets", "v1", True, ()
)


def served(ctx, crd, *definitions):
    ctx.cluster.documents["customresourcedefinitions"] = {
        "items": [crd(d.group, d.kind, d.plural) for d in definitions]
    }


def test_it_starts_with_the_definitions_entry_and_then_the_cluster(ctx, crd) -> None:
    served(ctx, crd, THING, ES)

    package.activate(ctx)

    (first_key, first), (second_key, second) = ctx.page_sets
    assert first_key == second_key == KEY
    assert [(s.group, s.title) for s in first] == [("Definitions", "CRDs")]
    assert [(s.section, s.group, s.title) for s in second] == [
        ("Custom Resources", "Definitions", "CRDs"),
        ("Custom Resources", "a.io", "Thing"),
        ("Custom Resources", "external-secrets.io", "ExternalSecret"),
    ]
    assert second[1].subtitle == "things.a.io"
    assert all(s.visible() for s in second)
    ctx.current_context = None
    assert not second[0].visible()


def test_the_pages_are_built_by_kind_and_refresh_their_own(ctx, crd) -> None:
    served(ctx, crd, THING, ES)
    ctx.cluster.documents["things"] = {"items": []}
    ctx.cluster.documents["externalsecrets"] = {"items": []}
    package.activate(ctx)
    specs = ctx.page_sets[-1][1]
    entry, thing, es = specs

    for spec in specs:
        spec.refresh()  # nothing is built yet: nothing to refresh
    definitions = entry.factory()
    thing_page = thing.factory()
    es_page = es.factory()

    assert isinstance(definitions, DefinitionsPage)
    assert type(thing_page) is ResourcesPage
    assert isinstance(es_page, ExternalSecretsPage)
    asked = len(ctx.cluster.asked)
    for spec in specs:
        spec.refresh()
    assert len(ctx.cluster.asked) == asked + 3


def test_the_menu_is_built_again_only_when_the_definitions_change(ctx) -> None:
    menu = Menu(ctx)

    menu.update([THING])
    menu.update([THING])
    menu.update([THING, ES])

    assert [len(specs) for _key, specs in ctx.page_sets] == [2, 3]


def test_the_definitions_page_updates_the_menu(ctx, crd) -> None:
    served(ctx, crd, THING)
    menu = Menu(ctx)
    page = menu.make_definitions()

    page.load()  # type: ignore[attr-defined]

    assert [len(specs) for _key, specs in ctx.page_sets] == [2]


def test_a_change_of_context_reads_the_definitions_again(ctx, crd) -> None:
    served(ctx, crd, THING)
    package.activate(ctx)
    ctx.cluster.documents["customresourcedefinitions"] = {"items": []}

    ctx.events.fire(CONTEXT_CHANGED, context="dev")

    assert [len(specs) for _key, specs in ctx.page_sets] == [1, 2, 1]


def test_without_a_context_the_menu_has_only_the_definitions_until_there_is_one(
    ctx, crd
) -> None:
    served(ctx, crd, THING)
    ctx.current_context = None
    menu = Menu(ctx)

    menu.load()

    assert [len(specs) for _key, specs in ctx.page_sets] == [1]
    assert menu.timer.isActive() and menu.attempts == 1  # it looks again

    ctx.current_context = "prod"  # the app got a context, and said nothing
    menu.timer.stop()
    menu.timer.timeout.emit()

    assert [len(specs) for _key, specs in ctx.page_sets] == [1, 2]
    assert not menu.timer.isActive() and menu.attempts == 0


def test_a_cluster_that_cannot_be_read_leaves_the_definitions_entry_and_tries_again(
    ctx, crd
) -> None:
    ctx.cluster.failure = ClusterError("forbidden")
    menu = Menu(ctx)
    menu.update([THING])

    menu.load()

    assert [len(specs) for _key, specs in ctx.page_sets] == [2, 1]
    assert menu.timer.isActive()

    ctx.cluster.failure = None
    served(ctx, crd, THING)
    menu.timer.stop()
    menu.timer.timeout.emit()  # the next look finds them

    assert [len(specs) for _key, specs in ctx.page_sets] == [2, 1, 2]
    assert not menu.timer.isActive()


def test_it_gives_up_after_a_number_of_looks_in_a_row(ctx) -> None:
    ctx.current_context = None
    menu = Menu(ctx)
    menu.load()

    for _ in range(MAX_RETRIES + 3):
        menu.timer.stop()
        menu.timer.timeout.emit()

    assert not menu.timer.isActive() and menu.attempts == MAX_RETRIES

    menu.load()  # a change of context starts it over
    assert menu.timer.isActive() and menu.attempts == 1


def test_an_answer_of_a_context_that_was_left_is_ignored(ctx) -> None:
    menu = Menu(ctx)
    menu.answered("dev", [THING])  # the window is on prod

    assert ctx.page_sets == []


def test_without_a_window_it_has_nothing_to_show(ctx) -> None:
    ctx.ui = None
    menu = Menu(ctx)

    menu.load()

    assert ctx.page_sets == []
