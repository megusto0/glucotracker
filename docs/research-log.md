# Research Log

Status: source of truth
Last updated: 2026-08-06
Owner/area: agent working record

Append-only record of external sources consulted while working on this repo:
documentation, specifications, standards, vendor references, forum answers,
papers. One entry per source, newest at the top.

## 2026-10-01 — Проект анализатора отклика: причинные ограничения

- **URL:** https://hsph.harvard.edu/profile/miguel-hernan/
- **Consulted for:** ограничения причинных выводов из наблюдательных данных,
  особенно при меняющихся во времени вмешательствах и смешивающих факторах.
- **Used in:** архитектурное предложение в чате Codex о разборе еды,
  инсулина и активности; реализация и параметры терапии не изменены.
- **Takeaway:** причинный вопрос и допущения должны быть заданы явно;
  обычная регрессия может быть неверна при факторах, зависящих от предыдущего
  лечения. Хороший прогноз сам по себе не доказывает причинный эффект.
- **Verdict:** applied to the proposal — отделять наблюдаемые факты,
  условные модельные сценарии и гипотезы; сначала использовать сопоставимые
  изолированные эпизоды, отдельно учитывать последующие корректировки.

## 2026-10-01 — Проект анализатора отклика: недоступный учебник

- **URL:** https://www.hsph.harvard.edu/miguel-hernan/wp-content/uploads/sites/1268/2024/04/hernanrobins_WhatIf_26apr24.pdf
- **Consulted for:** полное изложение методов для меняющихся во времени
  вмешательств; поиск вернул выдержки, открытие PDF завершилось ошибкой.
- **Used in:** только выбор источника для архитектурного предложения в чате.
- **Takeaway:** полный текст в этой сессии не проверен.
- **Verdict:** rejected as the basis for detailed algorithm claims — вместо
  него использовано доступное авторское описание на сайте Harvard; формулы
  и клинические коэффициенты из поисковых выдержек не перенесены.

## 2026-10-01 — Проект анализатора отклика: состав еды

- **URL:** https://pmc.ncbi.nlm.nih.gov/articles/PMC3836096/
- **Consulted for:** контролируемое исследование Smart et al. о влиянии жиров
  и белков при одинаковом количестве углеводов на поздний гликемический отклик.
- **Used in:** архитектурное предложение в чате Codex; без изменений COB,
  ICR, ISF или дозировочных констант.
- **Takeaway:** в исследовании детей и подростков состав еды влиял на позднюю
  кривую; одинаковые углеводы не означают одинаковый временной отклик.
- **Verdict:** applied as qualitative motivation to retain meal composition
  and the full response path. Универсальная персональная поправка к дозе,
  пересчёт жиров/белков в углеводы и точная причина отдельного эпизода из этого
  исследования не выводятся. Использован доступный индексированный текст;
  повторное открытие страницы упёрлось в проверку браузера.

## 2026-10-01 — Проект анализатора отклика: физическая активность

- **URL:** https://pmc.ncbi.nlm.nih.gov/articles/PMC11732933/
- **Mirror consulted:** https://pubmed.ncbi.nlm.nih.gov/39653802/
- **Consulted for:** позиция EASD/ISPAD о различающихся гликемических ответах
  на активность и контексте AID; применимость к анализатору дневника.
- **Used in:** архитектурное предложение в чате Codex; без изменений
  Health Connect, Nightscout или параметров терапии.
- **Takeaway:** ответ на активность зависит от контекста; один универсальный
  коэффициент «снижение сахара на шаг» не обоснован этим документом.
- **Verdict:** applied to the proposal — хранить тип, время, источник и
  полноту активности, оценивать персональный эффект по повторениям. Конкретные
  рекомендации по управлению AID не перенесены на пользователя без проверки
  его режима терапии.

## 2026-10-01 — Проект анализатора отклика: ограничения OpenAPS Autotune

- **URL:** https://openaps.readthedocs.io/en/latest/docs/Customize-Iterate/autotune.html
- **Consulted for:** требования к журналу углеводов/инсулина и ошибки
  классификации незаписанной еды или лечения гипогликемии как недостатка базала.
- **Used in:** архитектурное предложение в чате Codex; OpenAPS не запускался,
  профили Nightscout и настройки терапии не изменены.
- **Takeaway:** неполные записи могут систематически исказить настройку;
  отсутствие события в журнале не доказывает отсутствие еды или вмешательства.
- **Verdict:** applied to the proposal — обязательный контроль полноты,
  причины исключения эпизодов и режим предложений. Прямое перенесение
  алгоритма, констант и автоматическое переключение профиля rejected.

## 2026-10-01 — Проект анализатора отклика: чтение предложений автотюна

- **URL:** https://openaps.readthedocs.io/en/dev/docs/Customize-Iterate/understanding-autotune.html
- **Consulted for:** трактовка результатов и различие короткого наблюдения
  и основания для долговременного изменения профиля.
- **Used in:** архитектурное предложение в чате Codex; без изменений сервиса
  `icr_autotune.py` и его порогов.
- **Takeaway:** вывод автотюна требует проверки исходных данных и рассмотрения
  человеком, а не слепого изменения настроек.
- **Verdict:** applied as a review boundary — выводить доказательства,
  неопределённость и проверку на последующих днях; сроки и числовые пороги
  из документа не приняты как персональные клинические правила.

## 2026-09-26 — Пищевой инсулин при низком прогнозе глюкозы

- Source: https://diabetesjournals.org/care/article/doi/10.2337/dci26-0122/172498/The-Management-of-Type-1-Diabetes-in-Adults-The
  Consulted for the distinction between meal carbohydrate coverage and glucose
  adjustment. The ADA/EASD type 1 diabetes consensus says carbohydrate intake
  should guide prandial insulin dosing. Applied to
  `application/insulin_recommendation.py`: a forecasted low reduces the meal
  calculation through the existing signed correction instead of unconditionally
  replacing the food dose with zero. It does not supply a new dose constant.
- Source: https://diabetesjournals.org/care/article/49/Supplement_1/S132/163927/6-Glycemic-Goals-Hypoglycemia-and-Hyperglycemic
  Consulted for the treatment boundary of an observed low glucose. The ADA
  Standards of Care recommend treating glucose at or below 3.9 mmol/L with
  fast-acting carbohydrate and reassessing. Applied to keep the current-low
  zero gate and to distinguish its mobile warning from a low _forecast_;
  a forecast alone is not proof that glucose is already low.

## 2026-09-24 — BK Baconizer catalogue entry

- Source: https://burgerkings.ru/menu/burgery/bekonajzer-47554
  Consulted for the Russian Burger King Baconizer's reported 335 g serving,
  50.3 g carbohydrates, 57.2 g protein, 65.7 g fat and 1021.7 kcal. Applied
  to the shared product entry as unverified third-party data; the database
  retains this URL and a manual source kind so the UI flags it for review.
  The same page provides the linked Baconizer image; its JPEG is cached in the
  local product image store and served by the product image endpoint.
- Source: https://burgerkingi.ru/menu/bekonayzer
  Independent third-party catalogue corroborates the same serving and macro
  values. Used only as a cross-check, not stored as the record's source URL.
- Source: https://www.burgerking.lt/meniu/ant-groteliu-kepti-mesainiai/bacon-king/
  Official Lithuania Bacon King page consulted as a regional comparison. Its
  nutrition differs, so it was rejected as the source for the Russian entry.

## 2026-09-24 — Retrospective insulin recommendation review

- Source: https://diabetesjournals.org/care/article/49/Supplement_1/S132/163927/6-Glycemic-Goals-Hypoglycemia-and-Hyperglycemic
  Consulted to interpret CGM outcomes after past meal boluses. The 3.9–10.0
  mmol/L range and time below 3.9 mmol/L are population-level review metrics,
  not proof that a single meal dose was correct or a mandate to change dosing.
- Source: https://diabetesjournals.org/care/article/49/Supplement_1/S183/163934/9-Pharmacologic-Approaches-to-Glycemic-Treatment
  Consulted for the role of bolus timing and CGM trends in interpreting
  post-meal excursions. No clinical dose constant or formula was changed;
  request-path work only removes repeated computation with equal outputs.

## 2026-09-22 — Prospective glucose forecast review and v9 implementation

- Source: https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html
  Consulted for chronological evaluation and a gap between training and test
  samples. Applied to the proposed validation design in the private, untracked
  `exports/glucose_prediction_review_2026-09-22.md` outside the repository.
  Takeaway: chronological anchor splits alone do not exclude overlapping future
  labels; the application's forecast horizon and CGM matching tolerance must
  determine a time-based purge. Subsequently applied in
  `application/glucose_prediction_experimental.py::_purge_overlapping_targets`, chronological
  audit calibration, repository outcome cutoffs and the read-only replay harness.
  No scikit-learn runtime dependency was introduced.
- Source: https://proceedings.mlr.press/v230/hallberg-szabadvary24a.html
  Consulted for adaptive interval calibration with delayed multi-step outcomes.
  Applied as a research candidate in the same private review, not as a deployed
  algorithm or a claim of clinical coverage. Takeaway: each horizon needs to
  respect when its outcome becomes available; aggregate historical coverage
  alone does not establish coverage across changing regimes.
  The implementation retains quantile/conformal intervals; adopting the paper's
  adaptive algorithm remains deferred. This change adds availability guards and
  later-day acceptance for central-forecast corrections instead.
- Source: https://proceedings.mlr.press/v162/zaffran22a.html
  Considered for adaptive conformal prediction on dependent time series.
  Deferred in the same review in favor of the more directly relevant
  multi-step/delayed-outcome formulation above. No code or constants changed.

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

### 2026-08-16 — Импорт покупок по фискальному QR

- **URL:** https://www.nalog.gov.ru/rn07/news/tax_doc_news/16632899/
- **Consulted for:** какие реквизиты требуются для получения и проверки
  электронного кассового чека вместо OCR бумажного текста.
- **Used in:** `docs/fridge-mealprep-concept.md`.
- **Takeaway:** ФН, ФД, ФП, дата и итог идентифицируют фискальный документ, а
  сервис проверки возвращает подробную информацию о покупке.
- **Verdict:** applied — фискальный QR выбран основным способом импорта, OCR
  оставлен только fallback.

### 2026-08-16 — Принтер этикеток для контейнеров

- **URLs:** https://www.xprinter.net/product/495.html,
  https://www.xprintertech.com/sdk.html
- **Consulted for:** пригодность Xprinter XP-365B для домашних этикеток с
  DataMatrix и интеграции с Android.
- **Used in:** `docs/fridge-mealprep-concept.md`.
- **Takeaway:** модель поддерживает прямую термопечать, DataMatrix, носители до
  80 мм и имеет SDK производителя.
- **Verdict:** applied — USB + Bluetooth версия XP-365B рекомендована для MVP.

### 2026-09-25 — Завтрак «Вкусно — и точка»

- **URLs:** https://vkusnoitochka.ru/menu/klassicheskiy-zavtrak/syrniki_1,
  https://tastyandpoint.com/data/vkusno-menu.json,
  https://tastyandpoint.com/categories/zavtrak/,
  https://vkusnotochkamenu.ru/zavtrak/omlet-s-syrom-48502,
  https://vkusnotochkamenu.ru/zavtrak/omlet-s-vetchinoj-48503,
  https://vkusnotochkamenu.ru/zavtrak/yaichnitsa-s-bekonom-48500,
  https://vkusnotochkamenu.ru/zavtrak/maffin-s-yajtsom-i-syrom-48486,
  https://vkusnotochkamenu.ru/zavtrak/maffin-s-yajtsom-i-bekonom-48487.
- **Consulted for:** ассортимент завтрака, порции, БЖУ и фотографии отдельных
  позиций; официальный сайт использован для сверки названий вариантов.
- **Used in:** `backend/catalog_seeds/vit_breakfast.json`; исходные снимки
  сохранены в `runtime/catalog_seeds/vit_breakfast_images/`, рабочие копии —
  в `runtime/pattern_images/`.
- **Takeaway:** у комбо состав и пищевая ценность зависят от выбранных
  компонентов, поэтому в базу внесены только продукты с отдельной порцией.
  Источники БЖУ и снимков — сторонние каталоги, а не подтверждённая таблица
  производителя; 35 записей оставлены с `is_verified=false`.
- **Verdict:** applied — картинки скачаны и хранятся локально, а не зависят
  от доступности сторонних сайтов во время поиска.

### 2026-10-01 — Hermes Codex token renewal and service synchronization

- **Source:** https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions#refreshing-tokens
- **Consulted for:** access-token renewal, rotating refresh tokens and concurrent
  consumers of one OAuth session.
- **Landed in:** `deploy/ubuntu/bin/glucotracker-hermes-auth-sync.py`, the matching
  systemd service/timer and deployment README.
- **Takeaway:** renew near expiry, persist the replacement credentials and
  serialize renewal for the same session. The installed Hermes resolver already
  locks and updates its canonical store, so Glucotracker calls that resolver as
  the Hermes owner and atomically publishes only the access token. The backend
  does not independently rotate a copied refresh token. Official Sign in with
  ChatGPT flow lifetimes are not assumed for the existing Hermes Codex session;
  the sync validates the actual token expiry.
- **Verdict:** applied.

### 2026-10-01 — Huami/Zepp OS activity fetch timestamps (Helio Strap mis-dating)

- **Source:** https://codeberg.org/Freeyourgadget/Gadgetbridge/issues/3091
- **Consulted for:** how Gadgetbridge dates Zepp OS activity samples, while
  investigating Helio Strap rows stored up to 2026-10-09 in the Bridge database.
- **Landed in:** Bridge fork `glucotracker/SampleTimeGuards.kt`,
  `FetchActivityOperation.java`, `AbstractFetchOperation.java` and
  `HealthConnectUtils.kt`.
- **Takeaway:** Gadgetbridge requests "since X", the band answers "N samples since
  Y", and each sample is dated Y + i minutes; the maintainer notes Gadgetbridge
  "just accepts the date and data that the band reports". Any record in the
  band's stream that is not one real minute (Helio sent 3 022 all-0xFF filler
  records from 2026-09-27 02:35) shifts every later sample and is persisted into
  `lastSyncTimeMillis`. Fetching from an intermediate date is the documented
  manual recovery.
- **Verdict:** applied — a stream whose minute-by-minute dating would end after
  now is refused rather than stored, filler records are skipped, and stored
  fetch positions are clamped to now.

### 2026-10-01 — Gadgetbridge issue search for future-dated samples

- **Source:** web search over codeberg.org/Freeyourgadget/Gadgetbridge issues;
  the issue list page itself answered HTTP 429 and was not retried.
- **Consulted for:** whether upstream knows future-dated samples and their effect
  on the Health Connect export.
- **Landed in:** the diagnosis given to the user.
- **Takeaway:** search results show an open upstream issue saying the Health
  Connect sync silently stops when the database holds samples with a future
  timestamp, with no in-app way to remove them. Its number and text could not
  be opened, so it is treated as a lead, not a verified fact.
- **Verdict:** confirmed in the fork: `HealthConnectUtils.kt` takes the export
  end boundary from the latest sample in the database, not capped at now, so
  future-dated rows are exported and the per-type cursor jumps past them.

### 2026-10-04 — Размеры картошки и меню Rostic's, «Вкусно — и точка», Burger King

- **URLs:** https://rostics.ru/api/menu/getMenuPassport/74015171/ru/clickcollect,
  https://vkusnoitochka.ru/api/nutrition/search, https://vkusnoitochka.ru/menu,
  https://burger-king.by/menu/zakuski/king-fri-xl/,
  https://bkmenu.ru/fries/kartofel-king-fri-bolshoi, https://burgerkingrus.ru/.
- **Consulted for:** официальные размеры картофеля фри и по-деревенски в каждой
  сети, недостающие блюда и напитки, КБЖУ порций.
- **Used in:** `backend/catalog_seeds/restaurant_menus_2026_10.json`,
  `backend/scripts/organize_restaurant_menus.py`; линейка размеров в
  `android-concept/.../capture/RestaurantVariants.kt`.
- **Takeaway:** паспорт меню Rostic's даёт КБЖУ на 100 г и вес; размеры там
  называются «Малый / Средний / Баскет» (фри) и «Малый / Средний»
  (по-деревенски). Напитки идут без веса — объём взят из названия, 1 мл = 1 г.
  API «Вкусно — и точка» отвечает только на точное название: фри маленький
  76 г, средний, большой 147 г, двойной 220 г; по-деревенски средний 165 г,
  большой 220 г, двойной 330 г; наггетсы 4/6/9/18 шт. Для среднего фри API
  пишет 160 г, но 318 ккал при общих для всех размеров 289 ккал/100 г дают
  110 г — записано 110 г с `source_confidence=official_api_weight_corrected`.
  Официальный сайт Burger King России закрыт антибот-защитой; «Кинг Фри XL»
  есть только у белорусской сети (160 г), российский самый большой размер —
  «Большой».
- **Verdict:** applied — Rostic's и «Вкусно — и точка» по официальным API.
  Rejected — белорусские значения XL и неофициальные каталоги BK (bkmenu.ru):
  у BK остаются значения официального российского PDF, а «XL» добавлен
  поисковым синонимом к «Кинг Фри Большой».

### 2026-10-04 — Актуальное меню Burger King

- **URLs:** https://eda.yandex.ru/api/v2/menu/retrieve/burger_king_argpz,
  https://s3.burgerkingrus.ru/default/0001/76/63751da2ff388af43630c54add8491b8f2df7568.pdf,
  https://chibbis.ru/smol/restaurant/burger-king-dostavka/menu,
  https://orderapp.burgerkingrus.ru (API приложения BK).
- **Consulted for:** блюда текущего меню BK (Биг Кинг, Кинг Фри MAXX, Ангус 4
  Сыра и т. д.) с весом и КБЖУ.
- **Used in:** `backend/catalog_seeds/restaurant_menus_2026_10_bk.json`,
  `backend/scripts/cache_restaurant_images.py` (хост `eda.yandex.ru`), токен
  размера `maxx` в `android-concept/.../capture/RestaurantVariants.kt`.
- **Takeaway:** официальный PDF BK датирован августом 2024 и не знает половины
  меню. Сайт и API приложения BK закрыты антибот-защитой; обходить её не стали.
  Витрина ресторана в Яндекс Еде — та, на которую ссылается приложение BK, —
  отдаёт вес и КБЖУ на 100 г от ресторана. Кинг Фри малый и MAXX там не
  продаются: их вес (67 и 250 г) взят из меню доставки BK на chibbis.ru, КБЖУ
  посчитано по «Кинг Фри стандартный» той же витрины. «Острый Кинг Фри» — та же
  картошка плюс пакетик «Острая Штука» 7 г.
- **Verdict:** applied — витрина Яндекс Еды (`restaurant_partner_menu`) и
  производные размеры (`derived_from_partner_menu`). Rejected — PDF 2024 года
  как устаревший; chibbis.ru только для веса, КБЖУ там нет.

### 2026-10-04 — Расход и нагрузка по пульсу

- **URLs:** https://www.researchgate.net/publication/7777759_Prediction_of_energy_expenditure_from_heart_rate_monitoring_during_submaximal_exercise
  (Keytel et al. 2005),
  https://support.hexoskin.com/how-is-the-energy-expenditure-calculated,
  https://fellrnr.com/wiki/TRIMP, https://www.trainingimpulse.com/banisters-trimp-0
  (Banister TRIMP),
  https://www.researchgate.net/publication/12175294_Age-Predicted_Maximal_Heart_Rate_Revisited
  (Tanaka, Monahan & Seals 2001).
- **Consulted for:** расход энергии на тренировке по пульсу, когда браслет не
  пишет калории в Health Connect; шкала нагрузки, которая отличает час во 2-й
  зоне от короткой тяжёлой работы; максимальный пульс для зон.
- **Used in:** `backend/glucotracker/application/activity_energy.py`,
  `backend/glucotracker/domain/energy.py` (`keypoint_kcal_per_min`),
  `glucotracker-gadgetbridge/.../glucotracker/ui/data/BridgeEffort.kt`.
- **Takeaway:** Keytel без VO2max, кДж/мин: мужчины −55,0969 + 0,6309·ЧСС +
  0,1988·кг + 0,2017·возраст; женщины −20,4022 + 0,4472·ЧСС − 0,1263·кг +
  0,074·возраст. Уравнение подобрано на субмаксимальной нагрузке; Hexoskin
  применяет его только выше ~60 % ЧССmax и плавно смешивает с обменом покоя
  ниже — у нас вклад так же сходит на нет от порога нагрузки (max(100, покой +
  30)) к flex-точке (покой + 15). В коде женская формула была ошибочной (мужские
  коэффициенты при ЧСС и возрасте) — исправлено. TRIMP Банистера: минуты ×
  ΔЧСС-резерва × 0,64·e^(1,92·Δ) (мужчины), 0,86·e^(1,67·Δ) (женщины). ЧССmax =
  208 − 0,7·возраст.
- **Verdict:** applied — Keytel для расхода на сервере и в Bridge, TRIMP и
  Tanaka для нагрузки и зон в Bridge. Rejected — варианты TRIMP без множителя
  0,64 и с 0,64 для женщин (встречаются на калькуляторах, не совпадают с
  оригиналом); hrTSS — нужен лактатный порог, которого нет.

### 2026-10-05 — Huami "fetch data" refusal after the start date (Helio Strap stall)

- **Source:** https://codeberg.org/Freeyourgadget/Gadgetbridge/issues/3249,
  https://codeberg.org/Freeyourgadget/Gadgetbridge/issues/2327
- **Consulted for:** the meaning of the strap's `10 02 04` answer to the fetch
  command, after Helio syncs saved nothing for 27 hours.
- **Landed in:** Bridge fork `FetchActivityOperation.java`,
  `AbstractFetchOperation.java` (`acceptAnnouncedTransfer`,
  `onFetchDataRejected`) and `glucotracker/SampleTimeGuards.kt`.
- **Takeaway:** in these logs `0x10` marks a response, the second byte is the
  step (`0x01` start date, `0x02` fetch data) and the third the status, `0x01`
  meaning success. `10 02 04` is therefore a refusal of the transfer after an
  accepted start date. No source documents status `0x04`. The fix itself rests
  on probing the strap: "since 10-04 09:41" announced 6 669 records and was
  refused, "since 10:11" was served with exactly the real minutes.
- **Verdict:** applied — an impossible announced count or a refused transfer
  steps the start forward 15 minutes at a time. Rejected: the suggestion in the
  same search results to turn off "Truncate fetch operation timestamps", which
  concerns sub-minute activities and did not match the observed counts.

_Started 2026-08-06. Entries before this date were not recorded; sources behind
earlier decisions are documented, where they exist, in the relevant ADR or model
document._
