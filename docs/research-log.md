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

### 2026-08-08 — Helio Strap support in Gadgetbridge

- **URL:** https://gadgetbridge.org/basics/topics/zeppos/
- **Consulted for:** whether a Gadgetbridge fork can own the Amazfit Helio Strap connection and retrieve the records Glucotracker needs.
- **Used in:** `docs/wearable-bridge.md`, `android-concept/app/src/gluco/java/com/local/glucotracker/wearable/HelioBridgeClient.kt`, and the separate `glucotracker-gadgetbridge` fork.
- **Takeaway:** Helio Strap is a supported Zepp OS device; activity sync includes heart rate, HRV, sleep, SpO2 and stress, and real-time HR is supported. A manual phone-initiated HR measurement is not implemented.
- **Verdict:** applied — the bridge requests a recorded-data sync and never claims to force a new sensor reading.

### 2026-08-08 — Helio Strap support maturity

- **URL:** https://gadgetbridge.org/blog/release-0_89_00/
- **Consulted for:** whether to base the fork on the initial experimental release or a newer upstream with Helio-specific fixes and Health Connect.
- **Used in:** the separate `glucotracker-gadgetbridge` fork, based on upstream `0.92.2`.
- **Takeaway:** Gadgetbridge 0.89.0 added Health Connect and Helio Strap detection improvements after the initial 0.87.0 support.
- **Verdict:** applied — the fork is based on current `0.92.2`, not the initial Helio implementation.

### 2026-08-08 — Amazfit authentication-key migration

- **URL:** https://gadgetbridge.org/basics/pairing/huami-xiaomi-server/
- **Consulted for:** whether Zepp can be deleted before pairing Helio Strap with the fork and what actions invalidate the key.
- **Used in:** `docs/wearable-bridge.md` and the migration instructions shown to the user.
- **Takeaway:** newer Amazfit devices require a vendor-issued auth key; removing the device in Zepp or factory-resetting it invalidates that key, while uninstalling Zepp after extracting the key is supported.
- **Verdict:** applied — setup explicitly forbids unpairing/resetting before key extraction.

### 2026-08-08 — Companion-device background reliability

- **URL:** https://gadgetbridge.org/basics/pairing/companion-device/
- **Consulted for:** how the bridge can be available when Glucotracker requests a sync from the background.
- **Used in:** `docs/wearable-bridge.md` and the bridge pairing procedure.
- **Takeaway:** companion-device pairing grants the background execution path intended for a wearable companion on Android 8+ and is recommended on modern Android.
- **Verdict:** applied — companion pairing is a required setup step rather than relying only on an ordinary BLE bond.

### 2026-08-08 — Latest heart-rate sample from Health Connect

- **URL:** https://developer.android.com/reference/kotlin/androidx/health/connect/client/records/HeartRateRecord.Sample
- **Consulted for:** whether a heart-rate record exposes individual measurement times, so the UI can show the latest point rather than a daily average.
- **Used in:** `android-concept/app/src/gluco/java/com/local/glucotracker/healthconnect/DebugHealthConnectSync.kt`, `android-concept/app/src/gluco/java/com/local/glucotracker/ui/glucose/MoreHealthConnect.kt`.
- **Takeaway:** each `HeartRateRecord.Sample` has its own `time` and `beatsPerMinute`; the newest accessible sample can therefore be selected exactly.
- **Verdict:** applied — the Health Connect card caches and displays the newest sample returned by the provider.

### 2026-08-08 — Health Connect read-history boundary

- **URL:** https://developer.android.com/health-and-fitness/health-connect/read-data
- **Consulted for:** whether “latest” means the newest sensor measurement globally or only the newest point the app is permitted to read.
- **Used in:** `android-concept/app/src/gluco/java/com/local/glucotracker/healthconnect/DebugHealthConnectSync.kt` and the Health Connect status semantics.
- **Takeaway:** Health Connect returns only data visible under the user-granted data-type and history permissions; without history permission, third-party history is restricted to the documented 30-day window.
- **Verdict:** applied — the UI describes and shows the latest point available to this app, with its timestamp, rather than implying live watch access.

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
