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

### 2026-08-10 — Health Connect instants are independent of zone offsets

- **URL:** https://developer.android.com/health-and-fitness/health-connect/write-data
- **Consulted for:** deciding whether embedded sleep/session and heart-rate
  sample timestamps should be interpreted as UTC instants or shifted by the
  accompanying user-experienced zone offset.
- **Used in:** `backend/glucotracker/application/health_connect_samples.py`,
  `backend/glucotracker/application/body_states.py`, and
  `backend/glucotracker/application/insulin_recommendation.py`.
- **Takeaway:** Health Connect models record boundaries and series-sample times
  as `Instant`; `startZoneOffset`/`endZoneOffset` are separate metadata about
  the user's experienced zone. The official examples pass absolute instants to
  both records and samples while calculating offsets independently.
- **Verdict:** applied — payload timestamps are treated as candidate true UTC
  instants, while a span-distance check still recovers legacy rows whose writer
  placed local wall time in the instant field.

### 2026-08-09 — Fingerstick calibration is a current reference, not weaker early evidence

- **URL:** https://www.dexcom.com/faqs/bg-meter-vs-cgm-reading
- **Consulted for:** whether a valid fingerstick entered early in a sensor session
  should be mathematically weakened only because later calibrations may differ.
- **Used in:** `backend/glucotracker/application/glucose_dashboard.py` and its
  dashboard calibration tests.
- **Takeaway:** Dexcom says an accepted calibration should bring CGM readings
  closer to the contemporaneous meter value; it separately requires a clean,
  timely fingerstick during stable glucose and rejects pressure-affected sensor
  readings. Sensor age is not presented as a reason to scale an otherwise valid
  meter value toward zero.
- **Verdict:** applied — existing stability, timing, compression and jump checks
  remain, but a fingerstick that passes them now has full weight at every sensor
  age. Later readings influence their own nearby times instead of retroactively
  making the earlier reference less true.

### 2026-08-08 — Current Zepp authentication-key extractor

- **URL:** https://codeberg.org/argrento/huami-token
- **Consulted for:** retrieving the already-issued Amazfit Helio Strap Bluetooth authentication key without root access or reading Zepp's private Android database.
- **Used in:** the one-time local Helio Strap migration to Glucotracker Bridge; no extractor code or credentials were added to this repository.
- **Takeaway:** current `huami-token` encrypts the credential exchange expected by Zepp's v2 token endpoint and retrieves the bound device's 128-bit `auth_key` from the account device list.
- **Verdict:** applied — the key was stored outside the repository in the user's protected local application-data directory and was never printed to the task output.

### 2026-08-08 — Legacy Huafetcher Zepp login

- **URL:** https://codeberg.org/vanous/huafetcher
- **Consulted for:** a non-root Android/desktop fallback for retrieving the Helio Strap key.
- **Used in:** evaluation only; no code or credentials were retained.
- **Takeaway:** its embedded legacy Amazfit login posts directly to the old registration endpoint and the live server rejected the attempt with HTTP 429.
- **Verdict:** rejected — no retry was made; the maintained encrypted `huami-token` flow was used instead.

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

### 2026-08-10 — Signed-коррекция по CGM и текущий итог болюса

- **URL:** https://pmc.ncbi.nlm.nih.gov/articles/PMC7780381/
- **Consulted for:** можно ли отрицательной поправкой по текущей/прогнозной CGM
  уменьшать пищевой болюс вместо состояния «расчёт недоступен».
- **Used in:** `backend/glucotracker/application/insulin_recommendation.py`,
  `android-concept/app/src/gluco/java/com/local/glucotracker/ui/feature/insulin/HistoricalInsulinSheet.kt`.
- **Takeaway:** при интерпретации стрелок тренда расчёт еды, коррекция, активный
  инсулин и недавняя еда рассматриваются вместе; падающий тренд может уменьшать
  дозу, но требует явного учёта риска гипогликемии.
- **Verdict:** applied conservatively — поправка по прогнозу теперь signed, а
  прогноз ниже 3,9 ограничивает числовой итог нулём. Значения ISF, ICR, DIA и
  порог гипогликемии не менялись.

### 2026-08-10 — Прозрачная формула `еда + коррекция − свободный IOB`

- **URL:** https://pmc.ncbi.nlm.nih.gov/articles/PMC9294569/
- **Consulted for:** базовую структуру современного калькулятора пищевого
  болюса и место IOB в формуле.
- **Used in:** `backend/glucotracker/application/insulin_recommendation.py`,
  `android-concept/app/src/gluco/java/com/local/glucotracker/ui/glucose/BolusBreakdown.kt`.
- **Takeaway:** опубликованная стандартная структура складывает углеводную и
  глюкозную части и вычитает IOB; контекст активности может дополнительно
  модифицировать результат.
- **Verdict:** partially applied — Glucotracker вычитает не весь IOB, а только
  остаток после обязательства перед прежним COB, и показывает его отдельной
  строкой. Нагрузка остаётся явно неучтённым фактором, а не скрытой поправкой.

### 2026-08-10 — Различия калькуляторов в обработке IOB

- **URL:** https://pmc.ncbi.nlm.nih.gov/articles/PMC8655273/
- **Consulted for:** допустимо ли считать одну конкретную схему вычета IOB
  универсальной и скрывать промежуточные члены.
- **Used in:** контракте `/glucose/insulin-recommendation` и пояснениях Android.
- **Takeaway:** коммерческие калькуляторы существенно различаются именно в
  обработке IOB, особенно ниже цели; промежуточные члены важны для проверки
  результата пользователем.
- **Verdict:** applied as a transparency constraint — backend остаётся
  источником итогового числа, но API и UI отдельно раскрывают signed-коррекцию,
  общий IOB, COB-обязательство и вычитаемый свободный IOB.

### 2026-08-10 — Ночные артефакты сдавливания CGM

- **URL:** https://pmc.ncbi.nlm.nih.gov/articles/PMC3879750/
- **Consulted for:** можно ли считать резкие ночные провалы CGM следствием
  давления на сенсор и безопасно ли скрывать их из расчётов разбора сна.
- **Used in:** `android-concept/app/src/gluco/java/com/local/glucotracker/ui/glucose/BodyStateBreakdown.kt`.
- **Takeaway:** в исследовании внезапные отклонения отдельных сенсоров во сне
  коррелировали с положением тела и давлением на область сенсора, но один
  график не позволяет доказать, что конкретная точка является артефактом.
- **Verdict:** applied only to presentation — ночная линия получает явно
  подписанное тяжёлое сглаживание, а исходные нормализованные точки продолжают
  определять TIR, минуты ниже диапазона и текст вывода. Сглаживание не меняет
  данные и не участвует в расчёте терапии.

_Started 2026-08-06. Entries before this date were not recorded; sources behind
earlier decisions are documented, where they exist, in the relevant ADR or model
document._
