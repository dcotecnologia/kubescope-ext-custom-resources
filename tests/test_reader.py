import pytest
from kubescope.sdk.errors import ClusterError

from kubescope.custom_resources import reader
from kubescope.custom_resources.crd import Definition
from kubescope.custom_resources.model import parse

ES = Definition(
    "external-secrets.io", "ExternalSecret", "externalsecrets", "v1beta1", True, ()
)


def test_the_definitions_are_read_from_the_apiextensions_api(ctx, crd) -> None:
    ctx.cluster.documents["customresourcedefinitions"] = {"items": [crd()]}

    found = reader.read_definitions(ctx.cluster, "prod")

    assert [d.kind for d in found] == ["Thing"]
    assert ctx.cluster.asked == [
        ("prod", "apiextensions.k8s.io", "v1", "customresourcedefinitions", None)
    ]


def test_the_resources_are_read_with_the_version_of_the_definition(ctx) -> None:
    ctx.cluster.documents["externalsecrets"] = {"items": []}

    assert reader.read_resources(ctx.cluster, "prod", ES) == {"items": []}

    assert ctx.cluster.asked == [
        ("prod", "external-secrets.io", "v1beta1", "externalsecrets", None)
    ]


def test_a_resource_the_cluster_does_not_serve_is_none(ctx) -> None:
    assert reader.read_resources(ctx.cluster, "prod", ES) is None


def test_another_failure_is_not_hidden(ctx) -> None:
    ctx.cluster.failure = ClusterError("externalsecrets is forbidden")

    with pytest.raises(ClusterError, match="forbidden"):
        reader.read_resources(ctx.cluster, "prod", ES)


def test_it_knows_the_externalsecret_definition(crd) -> None:
    assert reader.is_external_secret(ES)
    assert not reader.is_external_secret(
        Definition("a.io", "ExternalSecret", "x", "v1", True, ())
    )


def test_resync_stamps_the_force_sync_annotation(ctx, item) -> None:
    secret = parse({"items": [item("a", "ops")]}, "v1beta1")[0]

    reader.resync(ctx.writes, "prod", ES, secret)

    context, group, version, plural, namespace, name, patch = ctx.writes.patches[0]
    assert (context, group, version, plural, namespace, name) == (
        "prod",
        "external-secrets.io",
        "v1beta1",
        "externalsecrets",
        "ops",
        "a",
    )
    assert patch["metadata"]["annotations"][reader.FORCE_SYNC].isdigit()


def test_resync_all_goes_on_after_a_failure(ctx, item) -> None:
    secrets = parse({"items": [item("a"), item("b"), item("c")]}, "v1")
    ctx.writes.failing["b"] = ClusterError("forbidden")

    failed = reader.resync_all(ctx.writes, "prod", ES, secrets)

    assert [patch[5] for patch in ctx.writes.patches] == ["a", "c"]
    assert [(s.name, message) for s, message in failed] == [("b", "forbidden")]
