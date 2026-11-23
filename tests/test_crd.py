from datetime import UTC, datetime

from kubescope.custom_resources.crd import (
    Column,
    Definition,
    age,
    lookup,
    parse_definitions,
)


def test_definitions_are_read_sorted_with_the_version_stored(crd) -> None:
    document = {
        "items": [
            crd("z.io", "Zed", "zeds", scope="Cluster"),
            crd(
                "a.io",
                "Beta",
                "betas",
                versions=[
                    {"name": "v1beta1", "served": True},
                    {"name": "v1", "served": True, "storage": True},
                    {"name": "v0", "served": False},
                ],
                creationTimestamp="2026-01-01T00:00:00Z",
            ),
            crd("a.io", "Alpha", "alphas", versions=[{"name": "v2", "served": True}]),
        ]
    }

    found = parse_definitions(document)

    assert [(d.group, d.kind, d.version) for d in found] == [
        ("a.io", "Alpha", "v2"),  # none stored: the first served
        ("a.io", "Beta", "v1"),
        ("z.io", "Zed", "v1"),
    ]
    alpha, beta, zed = found
    assert (alpha.namespaced, zed.namespaced) == (True, False)
    assert beta.name == "betas.a.io" and beta.key == ("a.io", "Beta")
    assert beta.created == "2026-01-01T00:00:00Z"


def test_a_definition_with_no_served_version_or_no_names_is_left_out(crd) -> None:
    document = {
        "items": [
            crd(versions=[{"name": "v1", "served": False}]),
            crd(versions=[]),
            {"spec": {"group": "a.io"}},
            {},
        ]
    }

    assert parse_definitions(document) == []
    assert parse_definitions({}) == []


def test_the_printer_columns_are_the_ones_of_the_default_output(crd) -> None:
    printer = [
        {"name": "Status", "jsonPath": ".status.phase"},
        {"name": "Age", "jsonPath": ".metadata.creationTimestamp"},  # its own
        {"name": "Wide", "jsonPath": ".spec.x", "priority": 1},  # the wide output
        {"name": "NoPath"},
        {"jsonPath": ".spec.y"},  # no title
        *({"name": f"C{n}", "jsonPath": f".spec.c{n}"} for n in range(8)),
    ]
    document = {
        "items": [
            crd(
                versions=[
                    {
                        "name": "v1",
                        "served": True,
                        "storage": True,
                        "additionalPrinterColumns": printer,
                    }
                ]
            )
        ]
    }

    (definition,) = parse_definitions(document)

    assert definition.columns[0] == Column("Status", ".status.phase")
    assert [c.title for c in definition.columns] == [
        "Status",
        "C0",
        "C1",
        "C2",
        "C3",
        "C4",
    ]  # at most six


DOCUMENT = {
    "name": "x",
    "status": {
        "phase": "Ok",
        "ready": False,
        "count": 3,
        "conditions": [
            {"type": "Other", "status": "No"},
            {"type": "Ready", "status": "True"},
        ],
    },
    "ports": [{"n": "a"}, {"n": "b"}],
}


def test_lookup_follows_a_path_a_filter_and_an_index() -> None:
    assert lookup(DOCUMENT, ".status.phase") == "Ok"
    assert lookup(DOCUMENT, "status.phase") == "Ok"
    assert lookup(DOCUMENT, ".status.count") == "3"
    assert lookup(DOCUMENT, ".status.ready") == "false"
    assert lookup({"a": True}, ".a") == "true"
    assert lookup(DOCUMENT, '.status.conditions[?(@.type=="Ready")].status') == "True"
    assert lookup(DOCUMENT, ".status.conditions[?(@.type=='Ready')].status") == "True"
    assert lookup(DOCUMENT, ".ports[1].n") == "b"


def test_lookup_is_empty_when_there_is_nothing_to_show() -> None:
    assert lookup(DOCUMENT, ".status.missing") == ""
    assert lookup(DOCUMENT, ".status") == ""  # an object is not a text
    assert lookup(DOCUMENT, ".ports") == ""
    assert lookup(DOCUMENT, ".ports[5].n") == ""
    assert lookup(DOCUMENT, ".status[0]") == ""  # an index of what is no list
    assert lookup(DOCUMENT, ".ports[?(@.n>1)]") == ""  # a filter it does not know
    assert lookup(DOCUMENT, '.ports[?(@.n=="zz")].n') == ""
    assert lookup(DOCUMENT, ".name.x") == ""
    assert lookup(DOCUMENT, "..") == ""  # not a path
    assert lookup(DOCUMENT, ".ports[") == ""  # a bracket that never closes


def test_age_says_how_old_in_the_words_of_the_lists() -> None:
    now = datetime(2026, 1, 1, 0, 5, tzinfo=UTC)

    assert age("2026-01-01T00:00:00Z", now) == "5m"
    assert age("2026-01-01T01:00:00Z", now) == "0s"  # a clock ahead
    assert age("", now) == ""
    assert age("yesterday", now) == ""
    assert age("2020-01-01T00:00:00Z") != ""  # now, by default


def test_a_definition_is_plain_data() -> None:
    one = Definition("a.io", "Thing", "things", "v1", True, ())

    assert one.created == "" and one.name == "things.a.io"
