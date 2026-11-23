"""A CustomResourceDefinition of the cluster, as the menu and the lists use it.

Pure data and rules: no Qt and no cluster access.
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from kubescope.sdk.models import format_age

CREATED = ".metadata.creationTimestamp"  # the Age, which every list shows by itself
MAX_COLUMNS = 6  # of the printer columns the CRD asks for


@dataclass(frozen=True, slots=True)
class Column:
    """A column the CRD asks the lists to show: a title and where its value is
    (a small subset of JSONPath)."""

    title: str
    path: str


@dataclass(frozen=True, slots=True)
class Definition:
    group: str
    kind: str
    plural: str
    version: str  # the one the lists read: the stored one, when it is served
    namespaced: bool
    columns: tuple[Column, ...]
    created: str = ""  # RFC 3339, for the Definitions list

    @property
    def key(self) -> tuple[str, str]:
        return (self.group, self.kind)

    @property
    def name(self) -> str:
        return f"{self.plural}.{self.group}"


def parse_definitions(document: dict[str, Any]) -> list[Definition]:
    """The definitions of a list document, by group and kind; one with no
    served version is left out."""
    found = []
    for item in document.get("items") or []:
        spec = item.get("spec") or {}
        names = spec.get("names") or {}
        served = [v for v in spec.get("versions") or [] if v.get("served")]
        if not (spec.get("group") and names.get("kind") and names.get("plural")):
            continue
        if not served:
            continue
        version = next((v for v in served if v.get("storage")), served[0])
        found.append(
            Definition(
                group=spec["group"],
                kind=names["kind"],
                plural=names["plural"],
                version=version.get("name") or "",
                namespaced=spec.get("scope") == "Namespaced",
                columns=_columns(version.get("additionalPrinterColumns") or []),
                created=(item.get("metadata") or {}).get("creationTimestamp") or "",
            )
        )
    return sorted(found, key=lambda one: (one.group, one.kind))


def _columns(printer: list[dict[str, Any]]) -> tuple[Column, ...]:
    columns = [
        Column(one.get("name") or "", one.get("jsonPath") or "")
        for one in printer
        if one.get("name")
        and one.get("jsonPath")
        and one.get("jsonPath") != CREATED
        and not one.get("priority")  # the ones above 0 are for the wide output
    ]
    return tuple(columns[:MAX_COLUMNS])


_STEP = re.compile(r"\.?(?P<name>[^.\[]+)?(?:\[(?P<bracket>[^\]]*)\])?")
_FILTER = re.compile(
    r"\?\(@\.(?P<field>[\w.]+)\s*==\s*"
    r"(?P<quote>[\"'])(?P<value>.*?)(?P=quote)\)"
)


def lookup(document: dict[str, Any], path: str) -> str:
    """The text at `path` (`.status.phase`, `.ports[0].name`,
    `.status.conditions[?(@.type=="Ready")].status`), or an empty text when it
    is not there or the path is not one of these."""
    node: Any = document
    position = 0
    while position < len(path):
        step = _STEP.match(path, position)
        if step is None or step.end() == position:
            return ""
        position = step.end()
        if step["name"]:
            node = node.get(step["name"]) if isinstance(node, dict) else None
        if step["bracket"] is not None:
            node = _pick(node, step["bracket"])
        if node is None:
            return ""
    if isinstance(node, bool):
        return "true" if node else "false"
    if isinstance(node, dict | list):
        return ""
    return str(node)


def _pick(node: Any, bracket: str) -> Any:
    """What `[0]` or `[?(@.type=="Ready")]` selects of a list."""
    if not isinstance(node, list):
        return None
    if bracket.isdigit():
        return node[int(bracket)] if int(bracket) < len(node) else None
    match = _FILTER.fullmatch(bracket)
    if match is None:
        return None
    return next(
        (
            one
            for one in node
            if isinstance(one, dict) and lookup(one, match["field"]) == match["value"]
        ),
        None,
    )


def age(created: str, now: datetime | None = None) -> str:
    """How old something created at `created` is, as the lists of the app say
    it ("5m"); an empty text when there is no time or it is not understood."""
    if not created:
        return ""
    try:
        moment = datetime.fromisoformat(created.replace("Z", "+00:00"))
    except ValueError:
        return ""
    seconds = ((now or datetime.now(UTC)) - moment).total_seconds()
    return format_age(max(seconds, 0))
