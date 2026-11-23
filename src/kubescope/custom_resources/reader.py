"""Reads the cluster and asks for a resync, through the services the app lends
(`ctx.cluster` and `ctx.writes`)."""

from datetime import UTC, datetime
from typing import Any

from kubescope.sdk.errors import ClusterError

from kubescope.custom_resources.crd import Definition, parse_definitions
from kubescope.custom_resources.model import ExternalSecret

CRD_GROUP = "apiextensions.k8s.io"
CRD_VERSION = "v1"
CRD_PLURAL = "customresourcedefinitions"
EXTERNAL_SECRETS_GROUP = "external-secrets.io"
EXTERNAL_SECRETS_KIND = "ExternalSecret"
FORCE_SYNC = "force-sync"  # the annotation that makes the operator sync now
_NOT_SERVED = "could not find the requested resource"


def read_definitions_document(cluster: Any, context: str) -> dict[str, Any]:
    """The list document of the definitions of the cluster."""
    return cluster.get_custom_resources(context, CRD_GROUP, CRD_VERSION, CRD_PLURAL)


def read_definitions(cluster: Any, context: str) -> list[Definition]:
    return parse_definitions(read_definitions_document(cluster, context))


def read_resources(
    cluster: Any, context: str, definition: Definition
) -> dict[str, Any] | None:
    """The list document of the resources of a definition, in every namespace,
    or None when the cluster does not serve it (the CRD went away).

    Any other failure raises `ClusterError`.
    """
    try:
        return cluster.get_custom_resources(
            context, definition.group, definition.version, definition.plural
        )
    except ClusterError as error:
        if _NOT_SERVED not in str(error):
            raise
        return None


def is_external_secret(definition: Definition) -> bool:
    return definition.key == (EXTERNAL_SECRETS_GROUP, EXTERNAL_SECRETS_KIND)


def resync(
    writes: Any, context: str, definition: Definition, secret: ExternalSecret
) -> None:
    """Ask the operator to sync one ExternalSecret now, the way `kubectl
    annotate externalsecret NAME force-sync=...` does."""
    # in milliseconds: two resyncs in the same second must differ, or the second
    # changes nothing and the operator does not see it
    stamp = str(int(datetime.now(UTC).timestamp() * 1000))
    writes.patch_custom_resource(
        context,
        definition.group,
        definition.version,
        definition.plural,
        secret.namespace,
        secret.name,
        {"metadata": {"annotations": {FORCE_SYNC: stamp}}},
    )


def resync_all(
    writes: Any,
    context: str,
    definition: Definition,
    secrets: list[ExternalSecret],
) -> list[tuple[ExternalSecret, str]]:
    """Resync each one and go on when one fails: the ones that failed, with the
    words of the cluster."""
    failed = []
    for secret in secrets:
        try:
            resync(writes, context, definition, secret)
        except ClusterError as error:
            failed.append((secret, str(error)))
    return failed
