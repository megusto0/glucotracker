# Research Log

Status: source of truth
Last updated: 2026-08-06
Owner/area: agent working record

Append-only record of external sources consulted while working on this repo:
documentation, specifications, standards, vendor references, forum answers,
papers. One entry per source, newest at the top.

## Why this exists

Glucotracker encodes clinical and pharmacokinetic assumptions — IOB and COB
curves, ICR and ISF estimation, CGM normalization, Health Connect and Nightscout
semantics. When a number or an algorithm comes from outside the repo, the origin
has to stay auditable. Six months later "why is the biphasic peak at that
minute?" must have an answer that is not "an agent decided".

It also keeps API behavior traceable: when Nightscout, Health Connect, or Gemini
change, the entries below say which page the current implementation was written
against.

## When to add an entry

Add an entry when an external source influenced code, a constant, a schema, or a
documented decision. That includes sources that turned out to be wrong or
unusable — record them with `Verdict: rejected` and why, so the same dead end is
not walked twice.

Do not log: routine syntax lookups, general language or framework reference that
left no trace in a decision, or anything already captured by a link in the source
file itself.

## Entry format

```markdown
### YYYY-MM-DD — <short topic>

- **URL:** <full url>
- **Consulted for:** <the concrete question being answered>
- **Used in:** <file path, ADR, or changelog version — where the influence landed>
- **Takeaway:** <one or two lines: what the source actually established>
- **Verdict:** applied | partially applied | rejected — <reason if not applied>
```

Multiple sources for one question get one entry each, sharing the same
**Used in** target.

## Related records

- [`../CHANGELOG.md`](../CHANGELOG.md) — what changed, per version.
- [`adr/README.md`](adr/README.md) — accepted architecture decisions. If a source
  drove an architectural choice, cite it in the ADR too; this log is the index,
  not a replacement.
- [`iob-cob-models.md`](iob-cob-models.md) and [`ai.md`](ai.md) — the two areas
  most likely to need sourcing.

---

## Log

### 2026-08-08 — Разделение IOB еды и коррекции в расчёте болюса

- **URL:** https://pmc.ncbi.nlm.nih.gov/articles/PMC8783627/
- **Consulted for:** должен ли активный инсулин уменьшать пищевую часть нового
  болюса, если этот инсулин уже покрывает ранее съеденные углеводы.
- **Used in:** `backend/glucotracker/application/insulin_recommendation.py`,
  `desktop/src/features/nightscoutView/NightscoutPage.tsx`,
  `android-concept/app/src/gluco/java/com/local/glucotracker/ui/feature/insulin/HistoricalInsulinSheet.kt`.
- **Takeaway:** в проверенном калькуляторе пищевой и коррекционный IOB разделены;
  пищевой IOB не вычитается из пищевой части нового болюса.
- **Verdict:** partially applied — в Glucotracker нет разметки назначения каждой
  введённой дозы, поэтому уже существующий расчёт обязательства IOB перед прежним
  COB сохранён, а свободный остаток учитывается только в коррекционной части.

### 2026-08-08 — IOB в ретроспективном разборе болюса

- **URL:** https://pubmed.ncbi.nlm.nih.gov/24876553/
- **Consulted for:** какое состояние IOB должен показывать разбор уже введённого
  болюса и допустимо ли включать выбранную дозу в её собственный расчёт.
- **Used in:** `backend/glucotracker/application/top_up_dose.py`,
  `backend/glucotracker/api/routers/glucose.py`,
  `android-concept/app/src/gluco/java/com/local/glucotracker/ui/glucose/BolusBreakdown.kt`.
- **Takeaway:** IOB — остаток ранее введённого инсулина, который нужен для защиты
  от наложения доз; выбранный болюс не может быть частью предшествующего ему IOB.
- **Verdict:** applied — API принимает идентификатор разбираемой дозы и исключает
  её из owner-scoped пересчёта IOB на этот момент; параметры действия инсулина не
  менялись.

_Started 2026-08-06. Entries before this date were not recorded; sources behind
earlier decisions are documented, where they exist, in the relevant ADR or model
document._
