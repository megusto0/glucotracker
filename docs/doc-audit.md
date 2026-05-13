# Documentation Audit

Status: source of truth
Last updated: 2026-05-13
Owner/area: documentation inventory and unresolved issues

This audit was produced from `docs/`, root README/docs-like files, ADR files,
OpenAPI artifacts, and code inspection across backend, desktop, and Android.

## Current Source-Of-Truth Documents

- [`README.md`](README.md) - documentation map.
- [`architecture.md`](architecture.md) - current architecture and ownership.
- [`product.md`](product.md) - product scope and invariants.
- [`screens.md`](screens.md) - routes/screens.
- [`ux.md`](ux.md) - UX states and copy rules.
- [`ui-rulebook.md`](ui-rulebook.md) - visual system.
- [`data-model.md`](data-model.md) - main data entities.
- [`sync.md`](sync.md) - outbox, photo sync, Nightscout.
- [`ai.md`](ai.md) - Gemini and deterministic boundaries.
- [`medical-safety.md`](medical-safety.md) - medical and feature-gating boundary.
- [`reports.md`](reports.md) - PDF/TXT reports.
- [`testing.md`](testing.md) - verification commands.
- [`adr/README.md`](adr/README.md) - ADR index.
- [`openapi.json`](openapi.json) - API source of truth.
- [`openapi.yaml`](openapi.yaml) - generated Android codegen input.

## Archived During Cleanup

Moved to [`archive/2026-05-docs-cleanup/`](archive/2026-05-docs-cleanup/):

- `agent-context.md`
- `android-photo-estimate-flow.txt`
- `journal-redesign-ux.md`
- `migration-2026-multiuser.md`
- `tarelka-brand.md`
- root note/log files under `root-notes/`: `task.txt`, `suggestion.txt`,
  `report.txt`, `this.txt`, `outputs.txt`, `gb-sync.txt`, `errors.txt`

Reason: these were useful but duplicated or conflicted with the current
source-of-truth set. Their current content was folded into product,
architecture, screens, sync, UI, and safety docs where confirmed by code.

## ADR Cleanup

Moved root `docs/ADR-*.md` files into [`adr/`](adr/). Two filenames were cleaned:

- `ADR-005-single-call-photo-capture (3).md` -> `adr/ADR-005-single-call-photo-capture.md`
- `ADR-007-meal-categorization (1).md` -> `adr/ADR-007-meal-categorization.md`

The ADR text itself was not rewritten.

## Duplicates Or Documents Worth Merging

- `agent-context.md` duplicated architecture, UX, testing, and product rules.
- `migration-2026-multiuser.md` duplicated current auth/scoping/feature-gating
  docs but was a migration checklist, not steady-state documentation.
- `tarelka-brand.md` duplicated product/UI/safety rules and included screenshot
  links that are better treated as test artifacts.
- `android-photo-estimate-flow.txt` is now summarized in `sync.md` and `ai.md`.
- `journal-redesign-ux.md` was a temporary redesign note and no longer belongs in
  root `docs/`.

## Conflicts And Needs Verification

1. `CONCEPT.md` §3 says mobile has five tabs plus FAB. Current Android has four
   tabs per flavor plus FAB, with Stats inside Today. Current code wins, but the
   concept file is now historical until updated.
2. Prompt-level architecture says scoped reads must be enforced in repositories.
   Current backend often scopes directly in routers/application services. This is
   a multi-user hardening mismatch, not a docs issue.
3. `backend/glucotracker/api/openapi.py` marks many scoped endpoints, but
   `/me/goals`, `/me/schedule*`, and `/stats/insights` are not marked
   `x-glucotracker-scoped` in the generated OpenAPI even though they use current
   user data. This should be reviewed before relying on OpenAPI meta-tests for
   those endpoints.
4. ADR-011 described a dedicated server lookup by idempotency key. Current
   endpoint inventory does not expose a clear `GET /meals?idempotency_key=...`
   contract. Android reconciliation appears to use cached meals with
   `photoIdempotencyKey`. Verify before documenting a server lookup as shipped.
5. The prompt-level invariant says restaurants are shared. Current backend code
   has restaurant importers and product metadata, but no first-class Restaurant
   model was found. Treat a future restaurant table as `needs verification`.
6. Root-level visual concept files (`CONCEPT.md`, `tokens.css`,
   `glucotacker mobile.html`, `screens.jsx`, `design-canvas.jsx`,
   `ios-frame.jsx`) remain outside `docs/` because they are still referenced by
   active agent instructions or local visual prototypes. Current docs quote their
   stable rules and mark route differences where code diverges.
7. `mockup/` and `mockup-prototype/` remain outside `docs/archive/` because they
   are runnable/historical prototype folders rather than standalone docs. Treat
   them as historical references only.

## Missing Documents Created

- `product.md`
- `data-model.md`
- `sync.md`
- `ai.md`
- `medical-safety.md`
- `reports.md`
- `doc-audit.md`
- `adr/README.md`
- `archive/README.md`
- `archive/2026-05-docs-cleanup/README.md`

## Link Check

PowerShell check for relative Markdown links inside docs:

```powershell
$docs = Resolve-Path docs
Get-ChildItem docs -Recurse -Filter *.md | ForEach-Object {
  $file = $_.FullName
  Select-String -Path $file -Pattern '\]\(([^)#]+)(#[^)]+)?\)' -AllMatches |
    ForEach-Object {
      foreach ($m in $_.Matches) {
        $target = $m.Groups[1].Value
        if ($target -match '^[a-z]+:|^/|^mailto:') { continue }
        $path = Join-Path (Split-Path $file) $target
        if (-not (Test-Path $path)) { "$file -> $target" }
      }
    }
}
```
