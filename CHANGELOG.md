# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project follows
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.1.0] - 2026-11-24

### Fixed

- **Resync** and **Resync All** are out of sight while the app is read-only, and come back with the write mode by @danilogco

### Added

- A click on the header of a list sorts it, and a second one reverses it, by what the cells mean (ages, numbers, versions), as the lists of the app do; it needs the SDK 1.8 by @danilogco

## [1.0.0] - 2026-11-23

### Added

- A **Custom Resources** section in the side menu, the way Lens has it: a **Definitions** page with the CRDs of the cluster and, for each API group, a page for each of its kinds by @danilogco
- The list of a kind has the columns its CRD asks for (the printer columns), a namespace filter, a search over every column and **Details**, which shows the object by @danilogco
- The lists have no namespace column, like the Pods: the filter has it by @danilogco
- Right-clicking a row of any list offers **Details** (and **Resync** on an ExternalSecret, in the write mode) by @danilogco
- The refresh interval of an ExternalSecret is said like the ages of the lists ("1d", not "24h0m0s") by @danilogco
- After a **Resync** the page says it is waiting for the operator and reads the cluster again a few times, so the new status shows by @danilogco
- The ExternalSecrets of the External Secrets Operator show how their last sync went (a badge, the reason, how long ago and the refresh interval) with a **Resync** button for the one selected and a **Resync All** for the ones shown, both only in the write mode and after a confirmation by @danilogco
- The menu looks for the definitions again, every few seconds, while the app has no context yet or a read failed, so it is not left empty after a restart by @danilogco
- The menu is built again when the context or the definitions change, and a list reads again every 30 seconds while it is open by @danilogco

[Unreleased]: https://github.com/dcotecnologia/kubescope-ext-custom-resources/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/dcotecnologia/kubescope-ext-custom-resources/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/dcotecnologia/kubescope-ext-custom-resources/releases/tag/v1.0.0
