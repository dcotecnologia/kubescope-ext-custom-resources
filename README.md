# KubeScope Custom Resources

[![CI](https://github.com/dcotecnologia/kubescope-ext-custom-resources/actions/workflows/ci.yml/badge.svg)](https://github.com/dcotecnologia/kubescope-ext-custom-resources/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.15](https://img.shields.io/badge/python-3.15-3776AB.svg?logo=python&logoColor=white)](pyproject.toml)
[![KubeScope extension](https://img.shields.io/badge/KubeScope-extension-326CE5.svg?logo=kubernetes&logoColor=white)](https://github.com/dcotecnologia/kubescope)

Custom Resources for [KubeScope](https://github.com/dcotecnologia/kubescope): browse the **custom resources** of the
cluster by API group, the way Lens does, and for the **ExternalSecrets** of the
[External Secrets Operator](https://external-secrets.io) follow how their last sync went and **resync** one or all.

It is an **extension** written against the [KubeScope SDK](https://github.com/dcotecnologia/kubescope-sdk)
and nothing else of the app. Install it in **Settings → Extensions**.

## What it does

- **A Custom Resources section in the side menu.** **Definitions** lists the CRDs of the cluster (name, group,
  kind, scope, version, age). Under it there is a group for each API group (`external-secrets.io`,
  `monitoring.coreos.com`, ...) and in it a page for each kind. The menu follows the context you are on.
- **A list for every kind.** Namespace and name, the columns the CRD asks for in its printer columns (`kubectl get`
  shows them too) and the age. A namespace filter and a search over every column narrow it, and **Details** shows
  the object. It reads again every 30 seconds while it is open.
- **ExternalSecrets, with the sync.** The status of the last sync as a badge (synced, error, or deleted when the
  operator removed the Secret), the reason, how long ago it synced, the store and the refresh interval; hover the
  status for the operator's message.
- **Resync.** Select an ExternalSecret and press **Resync** (or right-click it) to ask the operator to sync it now,
  by setting its `force-sync` annotation, what `kubectl annotate externalsecret NAME force-sync=...` does.
  **Resync All** does it for every ExternalSecret the list shows (the namespace and search you chose) after you
  confirm the number. One that fails does not stop the others, and the failures are listed at the end. Both need the
  write mode.

## Permissions

| Permission | Why |
| ---------- | --- |
| `cluster.read` | Reads the definitions and the custom resources of the cluster (never a Secret) |
| `cluster.write` | Sets the `force-sync` annotation of an ExternalSecret, only in the write mode and after you confirm |
| `ui.page` | Adds its pages to the side menu |
| `ui.window` | Shows the confirmation, the messages and the Details |

## Requirements

KubeScope 2.5 or newer (the extension API `0`) and the SDK 1.5 or newer, which the app brings. Your account must be
allowed to list the CRDs and the resources you open, and to patch ExternalSecrets to resync them.

## Develop

```sh
make setup
make test FILE=tests/test_table_page.py   # one file, without coverage
make lint
```

See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).

## License

MIT
