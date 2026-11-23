"""An ExternalSecret of the External Secrets Operator, as the page shows it.

Pure data and rules: no Qt and no cluster access.
"""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from kubescope.sdk.models import format_age

from kubescope.custom_resources.crd import age

SYNCED = "synced"
FAILING = "failing"
WARNING = "warning"  # synced, but the operator removed the Secret
UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ExternalSecret:
    namespace: str
    name: str
    version: str  # the API version that served it, to patch it the same way
    store: str  # the (Cluster)SecretStore it reads from
    store_kind: str
    target: str  # the Secret it keeps up to date
    ready: str  # the status of its Ready condition: True, False or Unknown
    reason: str
    message: str
    refresh_interval: str
    refresh_time: str  # of the last sync, RFC 3339; empty when it never synced

    @property
    def state(self) -> str:
        if self.reason == "SecretDeleted":
            return WARNING
        if self.ready == "True":
            return SYNCED
        if self.ready == "False":
            return FAILING
        return UNKNOWN

    @property
    def key(self) -> tuple[str, str]:
        return (self.namespace, self.name)


def parse(document: dict[str, Any], version: str) -> list[ExternalSecret]:
    """The ExternalSecrets of a list document, by namespace and name; an item
    without a name is left out."""
    found = []
    for item in document.get("items") or []:
        metadata = item.get("metadata") or {}
        spec = item.get("spec") or {}
        status = item.get("status") or {}
        name = metadata.get("name")
        if not name:
            continue
        store = spec.get("secretStoreRef") or {}
        ready = next(
            (
                condition
                for condition in status.get("conditions") or []
                if condition.get("type") == "Ready"
            ),
            {},
        )
        found.append(
            ExternalSecret(
                namespace=metadata.get("namespace") or "default",
                name=name,
                version=version,
                store=store.get("name") or "",
                store_kind=store.get("kind") or "SecretStore",
                target=(spec.get("target") or {}).get("name") or name,
                ready=ready.get("status") or "Unknown",
                reason=ready.get("reason") or "",
                message=ready.get("message") or "",
                refresh_interval=str(spec.get("refreshInterval") or ""),
                refresh_time=status.get("refreshTime") or "",
            )
        )
    return sorted(found, key=lambda secret: secret.key)


def last_sync_age(secret: ExternalSecret, now: datetime | None = None) -> str:
    """How long ago it synced, as the lists of the app say ages ("5m"), or an
    empty text when it never did or the time is not understood."""
    return age(secret.refresh_time, now)


_UNITS = {"ns": 1e-9, "us": 1e-6, "µs": 1e-6, "ms": 1e-3, "s": 1, "m": 60, "h": 3600}
_DURATION = re.compile(r"(\d+(?:\.\d+)?)(ns|us|µs|ms|s|m|h)")


def format_interval(text: str) -> str:
    """A refresh interval as the lists of the app say a time ("1d", "1h30m"):

    the cluster gives it as a Go duration, which it writes in full
    ("24h0m0s"). What is not a duration is shown as it came.
    """
    if text == "0":
        return format_age(0)
    parts = _DURATION.findall(text)
    if not parts or "".join(number + unit for number, unit in parts) != text:
        return text
    return format_age(sum(float(number) * _UNITS[unit] for number, unit in parts))
