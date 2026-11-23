"""The lists of the custom resources: the objects of one definition, and the
definitions themselves."""

from collections.abc import Callable
from typing import Any

from kubescope.sdk import Context
from PySide6.QtCore import QCoreApplication

from kubescope.custom_resources import reader
from kubescope.custom_resources.crd import (
    Definition,
    age,
    lookup,
    parse_definitions,
)
from kubescope.custom_resources.table_page import Row, TablePage


class ResourcesPage(TablePage):
    """The objects of a definition, with the columns the CRD asks for."""

    def __init__(self, ctx: Context, definition: Definition) -> None:
        self.definition = definition
        headers = [
            QCoreApplication.translate("ResourcesPage", "Name"),
            *(column.title for column in definition.columns),
            QCoreApplication.translate("ResourcesPage", "Age"),
        ]
        widths = [
            320,
            *([150] * len(definition.columns)),
        ]
        super().__init__(
            ctx, headers, widths, definition.kind, namespaced=definition.namespaced
        )

    def fetch(self) -> list[Row] | None:
        document = reader.read_resources(
            self.ctx.cluster, self.ctx.current_context or "", self.definition
        )
        if document is None:
            return None
        return self.rows_of(document)

    def rows_of(self, document: dict[str, Any]) -> list[Row]:
        rows = []
        for item in document.get("items") or []:
            metadata = item.get("metadata") or {}
            name = metadata.get("name")
            if not name:
                continue
            namespace = metadata.get("namespace") or ""
            cells = (
                name,
                *(lookup(item, column.path) for column in self.definition.columns),
                age(metadata.get("creationTimestamp") or ""),
            )
            rows.append(Row(namespace, name, cells, item))
        return sorted(rows, key=lambda row: row.key)


class DefinitionsPage(TablePage):
    """The definitions of the cluster, which are the entries of the menu; the
    menu is built again when they change."""

    def __init__(
        self,
        ctx: Context,
        on_loaded: Callable[[list[Definition]], None],
    ) -> None:
        headers = [
            QCoreApplication.translate("DefinitionsPage", "Name"),
            QCoreApplication.translate("DefinitionsPage", "Group"),
            QCoreApplication.translate("DefinitionsPage", "Kind"),
            QCoreApplication.translate("DefinitionsPage", "Scope"),
            QCoreApplication.translate("DefinitionsPage", "Version"),
            QCoreApplication.translate("DefinitionsPage", "Age"),
        ]
        super().__init__(
            ctx,
            headers,
            [340, 220, 180, 110, 90],
            QCoreApplication.translate("DefinitionsPage", "Definitions"),
            namespaced=False,
        )
        self.on_loaded = on_loaded

    def fetch(self) -> list[Row] | None:
        document = reader.read_definitions_document(
            self.ctx.cluster, self.ctx.current_context or ""
        )
        items = {
            (one.get("metadata") or {}).get("name"): one
            for one in document.get("items") or []
        }
        rows = []
        for definition in parse_definitions(document):
            scope = (
                self.tr("Namespaced") if definition.namespaced else self.tr("Cluster")
            )
            rows.append(
                Row(
                    "",
                    definition.name,
                    (
                        definition.name,
                        definition.group,
                        definition.kind,
                        scope,
                        definition.version,
                        age(definition.created),
                    ),
                    items.get(definition.name),
                    payload=definition,
                )
            )
        return rows

    def loaded(self, rows: list[Row] | None) -> None:
        super().loaded(rows)
        self.on_loaded([row.payload for row in rows or []])
