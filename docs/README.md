# Glucotracker Documentation

Status: source of truth
Last updated: 2026-05-13
Owner/area: project documentation

This directory is the entry point for current project knowledge. Historical notes,
prompt files, temporary specs, old screenshots, and old OpenAPI dumps live under
[`archive/`](archive/).

## Read Order

1. [`product.md`](product.md) - what the product is, product boundaries, flavors,
   and non-goals.
2. [`architecture.md`](architecture.md) - backend, desktop, Android, API, storage,
   auth, and ownership boundaries.
3. [`data-model.md`](data-model.md) - the main persisted entities and which data is
   personal vs shared.
4. [`screens.md`](screens.md) - current desktop routes and Android navigation
   surfaces.
5. [`ux.md`](ux.md) and [`ui-rulebook.md`](ui-rulebook.md) - interaction,
   loading/empty/error states, visual rules, tokens, typography, and components.
6. [`sync.md`](sync.md), [`ai.md`](ai.md), [`reports.md`](reports.md), and
   [`medical-safety.md`](medical-safety.md) - specialized behavior and safety
   boundaries.
7. [`testing.md`](testing.md) - verification commands and high-risk test areas.
8. [`adr/README.md`](adr/README.md) - accepted ADR index and known implementation
   mismatches.
9. [`doc-audit.md`](doc-audit.md) - inventory, archived material, conflicts, and
   remaining manual verification.

## API Contract

[`openapi.json`](openapi.json) is the source of truth for client-consumable API
contracts. It is generated from the FastAPI app and is used by the desktop
OpenAPI TypeScript generation.

[`openapi.yaml`](openapi.yaml) is a generated compatibility artifact currently
used by the Android OpenAPI generator. Keep it in sync with `openapi.json` via
`scripts/export-openapi.sh`.

Do not document new endpoints unless they exist in `openapi.json`.

## Archive Policy

Archived documents are not deleted because they explain past decisions, visual
experiments, and failure reports. They are not current source of truth unless a
current document links to a specific archived section as historical context.

Current archive indexes:

- [`archive/README.md`](archive/README.md)
- [`archive/2026-05-docs-cleanup/README.md`](archive/2026-05-docs-cleanup/README.md)
- [`archive/2026-05-redesign/README.md`](archive/2026-05-redesign/README.md)

## Known Open Items

Use [`doc-audit.md`](doc-audit.md) before non-trivial documentation or architecture
work. It lists source/doc conflicts and items marked `needs verification`.
