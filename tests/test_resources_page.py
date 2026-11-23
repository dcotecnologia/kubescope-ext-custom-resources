from kubescope.custom_resources.crd import Column, Definition
from kubescope.custom_resources.resources_page import DefinitionsPage, ResourcesPage

THING = Definition(
    "a.io", "Thing", "things", "v1", True, (Column("Phase", ".status.phase"),)
)
CLUSTER = Definition("a.io", "Global", "globals", "v1", False, ())


def item(name, namespace="ns", phase="Ok"):
    return {
        "metadata": {
            "name": name,
            "namespace": namespace,
            "creationTimestamp": "2020-01-01T00:00:00Z",
        },
        "status": {"phase": phase},
    }


def test_the_objects_of_a_definition_are_listed_with_its_printer_columns(ctx) -> None:
    ctx.cluster.documents["things"] = {
        "items": [item("b", "two"), item("a", "one", "Failed"), {"metadata": {}}]
    }
    page = ResourcesPage(ctx, THING)

    page.load()

    assert [
        page.table.horizontalHeaderItem(c).text()  # type: ignore[union-attr]
        for c in range(page.table.columnCount())
    ] == ["NAME", "PHASE", "AGE"]  # no column for the namespace: the filter has it
    assert [page.table.item(r, c).text() for r in range(2) for c in range(2)] == [  # type: ignore[union-attr]
        "a",
        "Failed",
        "b",
        "Ok",
    ]
    assert page.rows[0].namespace == "one" and page.rows[0].cells[2] != ""  # the age
    assert page.rows[0].document is not None
    assert ctx.cluster.asked == [("prod", "a.io", "v1", "things", None)]


def test_a_cluster_wide_definition_has_no_namespace_column(ctx) -> None:
    ctx.cluster.documents["globals"] = {"items": [{"metadata": {"name": "g"}}]}
    page = ResourcesPage(ctx, CLUSTER)

    page.load()

    assert page.table.columnCount() == 2
    assert page.rows[0].cells == ("g", "")
    assert page.namespaces.isHidden()


def test_a_definition_that_went_away_is_not_served(ctx) -> None:
    page = ResourcesPage(ctx, THING)

    page.load()

    assert "does not serve" in page.notice.text()


def test_the_definitions_are_listed_and_handed_to_the_menu(ctx, crd) -> None:
    ctx.cluster.documents["customresourcedefinitions"] = {
        "items": [crd("b.io", "Two", "twos", scope="Cluster"), crd()]
    }
    handed: list = []
    page = DefinitionsPage(ctx, handed.append)

    page.load()

    assert [row.cells[:5] for row in page.rows] == [
        ("things.a.io", "a.io", "Thing", "Namespaced", "v1"),
        ("twos.b.io", "b.io", "Two", "Cluster", "v1"),
    ]
    assert page.rows[0].document is not None
    assert [d.kind for d in handed[0]] == ["Thing", "Two"]
    assert page.namespaces.isHidden()


def test_a_failed_read_of_the_definitions_leaves_the_menu_as_it_is(ctx) -> None:
    ctx.cluster.failure = RuntimeError("boom")
    handed: list = []
    page = DefinitionsPage(ctx, handed.append)

    page.load()

    assert handed == []
    assert "boom" in page.notice.text()
