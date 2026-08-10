# Changelog

All notable changes to Glucotracker are recorded here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **Note on version numbers.** Nothing here is a release — there is one user,
> one server, and no distribution. The numbers are milestone markers
> reconstructed from git history on 2026-08-06, and the commit ranges are the
> authoritative boundary. Every manifest sat at `0.1.0` for the project's whole
> life until `0.10.0`, which is now written once in
> [`android-concept/app/build.gradle.kts`](android-concept/app/build.gradle.kts)
> and mirrored in the backend and desktop manifests. Bump it and this file
> together when a cluster of work is done.

Scope covers all three projects in the monorepo — `backend/` (FastAPI),
`desktop/` (Tauri 2 + React), `android-concept/` (Jetpack Compose) — with the
affected surface named in each entry.

External sources consulted while building are recorded in
[`docs/research-log.md`](docs/research-log.md), not here.

---

## [0.11.0] — 2026-08-07 — What actually happened, not what was projected

### Added

- **Android (gluco) / Glucotracker Bridge** — в «Ещё» добавлено
  «Автообновление»: Bridge сам запрашивает у Amazfit Helio Strap пульс, сон и
  активность каждые 15 минут, пишет результат в Health Connect, после чего
  Glucotracker без открытого экрана отправляет новые записи на сервер. Повторные
  сигналы не запускают параллельные импорты; расписание сохраняется после
  перезапуска приложения (`0b5d82c`, Bridge `2b10a6c`).

- **Android (gluco)** — в «Ещё» появилась прямая настройка Amazfit Helio Strap:
  Glucotracker показывает состояние отдельного Glucotracker Bridge, последний
  доступный пульс и запускает цепочку «подключить → получить данные → записать
  в Health Connect → отправить на сервер». Связь между APK защищена общей
  подписью; food-flavor не содержит этот код (`6e94b9e`).

- **Android** — кнопка Health Connect показывает последнюю доступную приложению
  точку пульса и время измерения. Точка читается и кэшируется на телефоне до
  отправки на сервер, поэтому не исчезает при сетевой ошибке (`394fab8`).

- **Desktop + Backend** — `/nightscout/review/analysis` now shows a 24-hour
  retrospective basal autotune table for the tested `0.8 / 0.7 / 0.8 / 1.0`
  U/h profile and ISF 3.6. Each hourly equivalent flat-background rate is
  derived only from at least three quiet normalized-CGM windows; raw CGM is
  never used as fallback, and no setting is applied automatically. A slider
  compresses the 24 hourly rates down to 4–23 contiguous windows: boundaries
  follow evidence-weighted rate similarity while the projected daily dose is
  preserved.

- **Desktop + Backend** — прогоны базального теста сохраняются на сервере:
  `/glucose/basal-tests` заводит отрезок, закрывает его как завершённый или
  прерванный и отдаёт историю. Дрейф не хранится — он пересчитывается из
  нормализованной CGM при каждом чтении, поэтому запись не может разойтись с
  трассой, по которой её мерили. Еда или болюс внутри прогона не удаляют запись,
  а снимают с неё статус результата: «не засчитан, внутри было N событий».

- **Desktop + Backend** — таблица автотюна называет один отрезок, который стоит
  измерить активно, и предлагает базальный тест голодом на него. Отрезок
  выбирается там, где межквартильный размах дрейфа целиком лежит по одну сторону
  нуля и стоит минимум на трёх разных днях; соседние такие часы с одинаковым
  знаком склеиваются, а кандидаты сравниваются по эффекту при слабейшем чтении
  наблюдений, а не по медиане. Кнопка «Начать тест» закрыта, пока есть активный
  инсулин: он исказил бы дрейф. Каждый час теперь сообщает число различных дней
  — одиннадцать окон в 20:00–22:00 могут быть пятью вечерами.

- **Backend** — `GET /glucose/episodes/breakdown` takes one episode apart into
  six blocks that are the same for every class: a −2 h/+4 h window of calibrated
  CGM sent point by point, the two or three readings the episode is read from,
  one derived figure (rise per gram, or fall per unit), everything else in the
  window with a signed offset, a class-specific interpretation, and how often
  this has happened in 30 days. What differs by class is only which readings are
  anchors and which figure is worth deriving. See
  [ADR-020](docs/adr/ADR-020-episode-breakdown.md).

- **Backend** — an episode's label now carries the named evidence behind it —
  a stable code, the sentence, and its weight — alongside the plain `reasons`
  older clients render, plus the trough the judgement was made on.
- **Android** — «разбор эпизода» opens from a sitting's kind on Today: the CGM
  window as points rather than a line, the anchor readings with their times, the
  per-gram or per-unit figure, what else happened nearby with signed offsets,
  the probable cause, and how often it has happened in 30 days. Same sheet for a
  rescue, a meal, a snack and a correction — only the anchors and the derived
  figure change.
- **Android** — the two breakdown goldens render the real composable instead of
  the snapshot suite's fake surface, so a change to a glucose surface finally
  shows up in a diff. Every other gluco golden renders a stub that returns
  nothing for each glucose section.
- **Android** — «разбор болюса» opens from a sitting's «РАСЧЁТ ›»: every dose of
  the sitting with what it was for in words, the state at the moment of the one
  you pick — glucose, IOB, COB, ICR, ISF, target — the arithmetic one term to a
  line beside its own formula, and how far your dose sat from it. Mockup screen
  G. The follow-up endpoint already computed every term as of a supplied moment;
  only the endpoint was pinned to the present.
- **Backend** — `GET /glucose/top-up-dose` takes `at`, so the follow-up
  arithmetic can be asked about a past moment. Two terms do not travel backwards
  and the response says so: `projection_source` degrades to `none` once the
  stored forecast has aged out, and ICR/ISF come from current parameters.

### Changed

- **Desktop + Backend** — нормализация CGM больше не ослабляет валидный замер из
  пальца только из-за первых 12 или 48 часов сенсора. Каждый замер, прошедший
  проверки стабильности, близости по времени и отсутствия артефакта, становится
  полновесным локальным якорем; новые замеры уточняют соседние участки, но не
  обесценивают прежний. Фаза первых 48 часов остаётся только диагностикой
  возраста сенсора и не выбирает отдельную формулу коррекции.

- **Android (gluco)** — первичная рекомендация инсулина теперь использует общий
  с разбором введённого болюса блок «состояние → слагаемые → итог», сохраняя ввод
  фактической дозы. Удалены default-параметры из flavor-контракта Compose,
  из-за которых gluco APK падал при открытии Today с `AbstractMethodError`
  (`77b74e3`).

- **Android (gluco)** — строки сна и активности в дневной ленте теперь называются
  просто «Сон» и «Активность», без технического названия источника Health Connect;
  доза инсулина убрана из правой части заголовка приёма и остаётся в его нижнем
  блоке расчёта (`44ab0bc`).

- **Glucotracker Bridge** — the companion refresh now requests only Helio's
  minute activity stream, which already contains continuous heart rate,
  steps/activity, and sleep stages. It no longer waits for unrelated GPS,
  SpO2, stress, PAI, HRV, temperature, and summary operations; the measured
  phone cycle fell from more than two minutes to about ten seconds (`2a09627`).

- **Android + Backend** — разбор эпизода связывает ключевые точки графика со
  строками номерами 1–3, а соседние события — буквами A–Z. Для еды и коррекции
  блок больше не называется «вероятной причиной»: он показывает наблюдаемый
  результат без причинного утверждения о действии болюса.
- **Backend** — a carbohydrate correction is decided from the lowest calibrated
  reading around the plate, not from the slope at it. Food eaten while glucose
  fell steeply *toward a perfectly ordinary number* was filed as hypoglycaemia
  treatment — a descent from a meal peak satisfies "falling fast" exactly — which
  is where the diary's spurious orange rows came from. The label now requires a
  reading at or below 4.5 mmol/L in the window around the food; a steep slope,
  fast carbohydrate and a reversal only move confidence. With no CGM covering the
  moment the label is withheld rather than guessed.


- **Android** — History draws the assembly Today has: a card per episode, a
  sitting header whose time is the control, the episode's real type, and one
  footer link. It had been wrapping a whole day in one card and separating
  sittings with a hairline, which left every time in a left gutter, nothing to
  say what a sitting was, and «СРАВНИТЬ С РАСЧЁТОМ» clipped to «СРАВНИТЬ С» —
  the clipping that made a second action impossible on this screen in `bdc662f`.
  The footer's short «РАСЧЁТ ›» fits where the sentence did not.
- **Android** — a sitting header states what the episode actually was —
  «ПЕРЕКУС», «УГЛЕВОДНАЯ КОРРЕКЦИЯ», «КОРРЕКЦИЯ ИНСУЛИНОМ» — instead of «ПРИЁМ»
  whatever the backend classified it as. On both Today and History.
- **Android** — the pre-meal calculator states its terms one to a line instead of
  «еда 5,8 +0 коррекция −1,3 активный инсулин = 4,5 ЕД», where the signs belong
  to the values and the labels sit between them. The verdict on a dose already
  given has left this card for the bolus breakdown: one was a prospective
  calculator and the other a retrospective audit, sharing a widget.
- **Android** — a bolus is called a bolus. Both dose counters were also a bare
  «%d укола», right only for two through four, and are plurals now.
- **Android** — the collapsed insulin line closes again, keeps the total on
  screen while the doses are open, and carries a mark saying it opens at all.

### Fixed

- **Backend** — сон и пульс из Health Connect теперь читаются по встроенным
  абсолютным `Instant`, отдельно от метаданных часового пояса. Это возвращает
  записанный сон, утренний ICR и пульсовый минимум на их настоящее время, даже
  если старые колонки импорта были сдвинуты на `+04:00`; эвристика расстояния до
  интервала сохраняет совместимость с прежним writer, записывавшим wall time.

- **Desktop** — полупрозрачные полосы сна и активности на графике Nightscout
  больше не перехватывают наведение и клики у точек глюкозы под ними.

- **Backend, Android (gluco)** — разбор первого пищевого болюса снова берёт
  исходный расчёт приёма: пищевая часть остаётся видна без CGM, а недоступной
  помечается только коррекция по глюкозе. Для первого приёма после сна доза на
  еду теперь считается непосредственно по скорректированному ICR; обычные
  похожие приёмы остаются справкой с нулевым весом и больше не могут изменить
  показанную формулу (например, 77 г / 7,6 г/ЕД = 10,1 ЕД). В листе явно показаны
  формула и изменение ICR. Значок первого приёма после сна появляется до
  добавления инсулина (`ed946f7`, `9c0a36f`).

- **Android (gluco)** — a malformed Health Connect changes page no longer
  leaves its record type permanently stuck on the same cursor. Glucotracker
  performs one recoverable full read, uploads the valid rows around unreadable
  spans, and continues from a fresh cursor on later runs (`9891d18`).

- **Android (gluco) + Glucotracker Bridge** — a long Helio Strap full-sync no
  longer discards heart-rate, sleep, and activity rows that the bridge has
  already stored: on the bounded wait it exports the available snapshot to
  Health Connect. Missing writer permissions are reported explicitly and the
  Glucotracker action opens the bridge's exact Health Connect setup screen
  (`595dc2b`, `fee5853`).

- **Android** — «Мой ритм» теперь показывает пять непересекающихся частей суток:
  «Конец дня» завершается в момент начала типичного сна, а сон занимает отдельный
  следующий сегмент со своей луной. Значки стоят в центрах собственных интервалов,
  времена в легенде совпадают со шкалой, названия приведены к единому регистру
  (`55adb8b`, `b0c428a`).

- **Backend, Android, Desktop** — новый приём больше не уменьшается на весь IOB:
  инсулин, уже обязанный прежнему COB, не расходуется второй раз, а свободный IOB
  влияет только на коррекционную часть. Ретроспективный разбор также исключает
  выбранный болюс из его собственного состояния «IOB до», поэтому введённые
  6 ЕД больше не превращают расчёт 6 ЕД в ноль или заниженную дозу. Момент с
  часовым поясом теперь приводится к локальным часам до расчёта, а ошибка API
  показывается в Android явно вместо пустого листа.
- **Android** — a photographed meal's status updates while you sit on Today.
  The server draft row was hidden for the whole life of its outbox item, so once
  the upload confirmed the entry rendered from a record that carries no
  `estimate_status` — and the refresh loop, which only runs while some row says
  an estimate is in progress, never started. Measured on the device: twenty-two
  minutes in the foreground with an estimate pending and not one refetch; the
  estimate had in fact been ready on the server almost the whole time. The row
  now changes hands when the upload lands, and the loop keys off the server's
  own field rather than a UI enum that two row builders computed differently.
- **Backend** — a dose given between two sittings goes to the one that caused
  the rise, not to the one that happens to be nearer on the clock. A unit given
  at 19:38 to chase an 18:44 dinner landed on a croissant eaten at 20:03,
  because 25 minutes ahead beats 54 behind — and the croissant then read as 29 g
  on 3 U, a carbohydrate ratio of 9.7 g/U where the same evening with the same
  doses gives 14.5 if the snack falls an hour later. The tie now breaks on
  whether glucose was climbing, the same measured test the catch-up label
  already used. See [ADR-019 §7](docs/adr/ADR-019-episode-grouping.md).
- **Backend** — the catch-up label could not fire in a sitting of more than one
  dish. Its "a later plate makes this ambiguous" test matched any meal after the
  first, and this owner photographs a meal dish by dish, so a sitting
  disqualified its own catch-up. It now means a plate from a later sitting.
- **Backend** — the postprandial analyzer read raw sensor values against
  absolute thresholds. A drink at a calibrated 5.5 arrived as a raw 3.2, was
  recorded as hypo treatment, and was then dropped from the IOB/COB fits as an
  outlier — the mislabel was deleting real training data. It now reads the same
  calibrated series as the dashboard and the classifier.
- **Backend** — anchor searches inside a breakdown stop at the next episode. A
  53 g biscuit 75 minutes after a 12 g rescue drove glucose higher than the
  rescue did, and an uncapped search billed that rise to twelve grams of juice.

---

## [0.10.0] — 2026-08-06 — Measured signals over proxies

### Added

- **Android, Backend, Desktop** — the version is a real number again, written
  once in `android-concept/app/build.gradle.kts` and mirrored in the backend and
  desktop manifests. Every build ever produced declared `0.1.0`, so nothing on a
  device or a server could say what it was (`aec4911`).
- **Backend, Android** — «Мой ритм» shows the nights it read: the typical sleep
  window, how many nights are behind it, and a strip under the rhythm bar on the
  same scale, so a wrong anchor is visible rather than merely wrong (`aec4911`).
- **Backend, Android** — the day anchor behind «Мой ритм» comes from real sleep,
  recorded or heart-rate-inferred, taking one wake per day from the longest night
  ending that day. It was a weighted median of each day's first meal, a proxy for
  waking that fails on any day breakfast is late or skipped. Falls back to the
  meal estimate below five nights in ten, so a user with no watch — and the food
  flavor, which has no sleep at all — keeps the previous behaviour. Meal-window
  offsets were tuned against a first-meal anchor and are not retuned, so window
  boundaries shift earlier by the usual wake-to-first-plate gap (`19a7d00`).
- **Android** — a whole sitting's time can be moved at once, every dish by the
  same amount rather than collapsing onto one instant; the spacing inside a
  sitting is what the backend measures grouping and absorption from (`19a7d00`).
- **Backend** — the food half of a dose calculation is stored per sitting and
  reused, keyed by method and grouping version and guarded by a fingerprint of
  the meals and therapy parameters behind it. The correction half is never
  stored, because it reads glucose and insulin on board at the moment of asking
  (`dae21c4`).
- **Android** — the calculation is offered on past days, on History rows, and
  after a dose, where it reads as a comparison against what was actually given
  (`dae21c4`).
- **Backend, Android** — a bolus given 20 minutes to 3 hours after a sitting
  while glucose was rising is classified `catch_up` rather than counted as
  ordinary meal insulin, and shown as «догоняющий». Previously anything inside
  90 minutes was recorded as meal coverage with no flag, so a meal covered with
  8 U and chased with 4 U read as food that needed 12 U. Classification only —
  no dose or ratio changes (`c4cdb9c`).
- **Android** — manual Health Connect sync from Settings, with a visible success
  status instead of a silent background-only refresh (`9a64b98`).
- **Android** — history rows report the glucose response recorded for each meal
  in place of a metadata line that repeated the row's own time, and day headings
  carry the share of the day spent in range (`f622447`).

### Changed

- **Android** — a sitting states its time once instead of on every row; Today
  repeated it in the gutter and again under the title, so three plates
  photographed together printed the same minute six times. A plate eaten at a
  different minute still says so (`19a7d00`).
- **Android** — the word «фото» is dropped where the row's own thumbnail already
  says it; sources with no picture keep their label (`19a7d00`).
- **Android** — meal names wrap instead of truncating. Photo-estimated titles put
  what distinguishes them at the end, so «…с шоколадной кро…» cut off exactly the
  part that said which one it was (`19a7d00`).
- **Android** — a standalone insulin correction is drawn on a card like every
  other record instead of a bare line between two cards, and a single dish gets
  the same card shape a sitting of several gets (`19a7d00`).
- **Android** — the rhythm setting names its basis in words instead of printing
  the raw backend value; the screen read `weighted_7d` (`19a7d00`).
- **Android** — the History day summary counts «блюда» rather than «приёмы»;
  «приём» means one sitting everywhere else in the app, so eleven photographed
  dishes reading as "11 приёмов" contradicted the Today grouping (`dae21c4`).
- **Backend** — a sitting is the meals within 30 minutes of its own first meal,
  instead of chaining to the previous meal with nothing bounding the total span;
  three eating events 75 minutes apart used to become one episode. Changes
  episode grouping everywhere it is consumed, and therefore the numbers derived
  from it ([ADR-019](docs/adr/ADR-019-episode-grouping.md), `de82c3d`).
- **Backend** — outcome horizons are named by the question they answer rather
  than guessed per module; the ISF horizon moves from 4 h to 4.5 h, where
  insulin action actually ends (`de82c3d`).
- **Android** — a sitting is grouped into one block in History with its insulin
  stated once, instead of appearing as unrelated rows with the dose attached to
  whichever item happened to be anchored (`9da0b97`).
- **Android** — snacks, carbohydrate rescues and standalone insulin corrections
  are distinguished in History by a hairline rail and a named kind; ordinary
  meals stay untinted (`9da0b97`).
- **Android** — the About screen reports the commit and build time next to the
  version, which had read `0.1.0` in every binary ever produced (`9da0b97`).
- **Android** — carbohydrates are spelled one way across History and Today;
  rows previously read "49,7 У" beside a day summary reading "356,7 углев" for
  the same quantity (`f622447`).
- **Android** — the history hour scale moved from a single pinned header above
  the whole list onto each day's own timeline, which is what it labels
  (`f622447`).

### Fixed

- **Android** — Health Connect steps have never synced. The androidx converter
  rejects a zero-duration `StepsRecord` the provider is happy to store, and the
  read threw before returning a row; the changes token is only saved once that
  read succeeds, so every run retried the same page and reported partial data
  forever. The range is now halved around the failure, so everything either side
  of an unreadable record goes up and only the hour around it is given up
  (`aec4911`).
- **Backend** — `client_record_version` accepts Health Connect's `-1`, which it
  writes when a record's author set no version. The schema required `>= 0` and
  rejected the whole batch of 500 over it (`aec4911`).
- **Android** — a 4xx from the server no longer abandons the rest of the sync;
  it will never succeed on retry, and it was taking the other forty record types
  with it. The rejected body is logged instead of being thrown away, which had
  left `HTTP 422` as the only evidence (`aec4911`).
- **Android** — the Health Connect sync button reports what is actually
  happening. The running flag was raised inside the coroutine, after a suspend,
  so a caller polling in that gap saw "not running", redrew the previous run's
  numbers, and the button appeared to do nothing. A long sync now shows its
  running total instead of one frozen line (`aec4911`).
- **Android** — settings rows can put a wide control on its own line, so
  «Health Connect» stopped rendering as "Health ..." above "Часть данных н..."
  (`aec4911`).
- **Backend** — episode classification reads calibrated glucose instead of
  `min(raw, normalized)`, a safety floor borrowed from alarms. Raw sits 1.0–2.8
  mmol/L low for this sensor, so an ordinary 5.5 arrived as a raw 3.5 and the
  plate that followed was filed as a carbohydrate rescue. Both raw figures stay
  in the response; only the judgement changed (`19a7d00`).
- **Backend** — a sitting is not called a rescue while a bolus could still be
  attributed to it. "Food, no insulin, small carbs, drifting down" is also what a
  lunch still being photographed looks like. Being genuinely below range is its
  own evidence and still classifies immediately (`19a7d00`).
- **Android** — grouping and classification are re-pulled whenever the day's food
  changes — a new photo, a shifted time, a landed estimate, a deletion — instead
  of only when an insulin outbox item changed state. A dish added beside an
  existing one stayed its own card until the app was restarted (`19a7d00`).
- **Desktop, Android** — leftover active insulin appears in the dose breakdown.
  It is subtracted from the total but was not shown, so a 4,9 U meal with no
  correction published as «еда 4,9 +0 коррекция = 0 ЕД» (`19a7d00`).
- **Desktop** — a carbohydrate rescue no longer replaces the dose panel outright;
  a plate the classifier read wrong could not be asked about at all. The rescue
  view still leads and the calculation is one click away (`19a7d00`).
- **Backend** — stats insights, time-in-range shares and low-episode counts are
  computed from the calibrated CGM series instead of raw sensor values, which
  sit 1.0–2.8 mmol/L low and pushed every band and threshold the same way
  (`9da0b97`).
- **Android** — a confirmed photo row now stays in the "estimating" state until
  the accepted meal actually appears, instead of briefly showing an empty row
  (`a905f96`).
- **Android** — the photo-processing state test no longer depends on the wall
  clock; its pinned fixture date had aged past the estimate deadline, so the
  test passed only near the date it was written (`f622447`).

---

## [0.9.0] — 2026-08-04 — Normalized model space and the dosing engine

The largest single arc in the project: every fitted model moved into normalized
CGM space, and dose recommendation became a real per-daypart engine fitted to how
meals actually landed rather than a fixed ratio.

### Added

- **Backend** — prediction, digital twin and on-board models now train in
  normalized CGM space via a shared `GlucoseNormalizationService`, so raw sensor
  bias no longer leaks into fitted parameters (`8a633fd`).
- **Backend** — historical replay harness for the glucose predictor, letting a
  model be scored against real past days (`2498e9a`).
- **Backend** — per-daypart ICR estimated from how meals actually landed, instead
  of one global ratio (`73b290c`).
- **Backend** — tighter insulin ratio for the first meal after a long fasting
  break (`beb2a20`), confirmed against recorded sleep (`a5b53d2`) and against a
  heart-rate wake-up signal (`67a131b`).
- **Backend** — follow-up bolus calculation surfaced on the Nightscout page
  (`1f50303`).
- **Backend** — cached daily review with body context (`66270e9`).
- **Backend** — product memory now remembers items that came from photo estimates
  (`bb73942`).
- **Desktop** — an episode's dose is shown as what it actually worked out to
  (`25b8dcb`); the historical calculation stays visible after a dose exists
  (`3fc9967`).
- **Scripts** — Health Connect record export for diagnostics (`c7f151b`).
- **Docs** — handover note covering the glucose model and dosing work
  (`43bc58c`, `docs/HANDOVER-2026-08-03-glucose-models.md`).

### Changed

- **Backend** — glucose is projected forward with the forecast model rather than
  a straight-line extrapolation (`9791525`).
- **Backend** — a fall is judged by where it lands, not by how fast it moves
  (`95378f8`).
- **Backend** — dose questions are scoped to a single sitting rather than the
  whole episode (`9b41bef`).
- **Backend** — leftover active insulin now reduces the meal total (`79a017f`).
- **Backend (perf)** — replay hides the future with a rolled-back transaction
  instead of copying the database file (`d4dc026`).

### Fixed

- **Backend** — ISF is measured by the fall a correction actually caused, not by
  the rebound that followed it (`51726a5`).
- **Backend** — follow-up boluses are no longer discarded from the training label
  (`97e2402`).
- **Backend** — cached days are invalidated after dosing changes (`e01a72d`).
- **Backend** — a carb correction is labelled with what was actually eaten
  (`61fbde3`).
- **Backend** — Nightscout treatment updates use the supported route (`65973e6`).
- **Backend** — replay preparation creates the empty `cgm_calibration_models`
  table (`d31a460`).
- **Android** — meal time rolls back correctly across midnight rollover
  (`9c47093`); mobile dose calculation corrected (`66270e9`).
- **Desktop** — Today no longer spends layout width on text that says nothing
  (`e0880ac`).

Range: `65973e6..51726a5`

---

## [0.8.0] — 2026-07-31 — Prediction audit, Gemini 3.6, historical dosing

### Added

- **Backend** — 90-minute prediction audit (`1c4a2d5`).
- **Backend** — historical meal dose recommendation (`8aa635b`).
- **Backend** — photo estimates routed through Gemini 3.6 (`8ded12f`).
- **Backend/Android** — expanded glucose insights and restaurant capture
  (`128c61e`); therapy review and Nightscout context improvements (`ab07c8d`).
- **Android** — sensor codes can be scanned and auto-started (`b315fdc`).
- **Catalog** — Rostics items added to mobile restaurants (`f6b6a22`).

### Changed

- Medical "do not recommend insulin" warnings and disclaimers removed from the
  product surface (`61728eb`).

### Fixed

- **Android** — photo processing rows stay visible (`670938b`); active photo
  estimates are preserved across recomposition (`0e4bd78`).
- **Android** — focus is restored after backing out of a capture variant
  (`87a32ec`).

Range: `1c4a2d5..87a32ec`

---

## [0.7.0] — 2026-07-15 — Nightscout web view and the IOB/COB models

### Added

- **Desktop** — Nightscout-style web view (`2475cb9`) with on-board context
  (`9edb9eb`).
- **Backend** — data-calibrated biphasic IOB and macro COB profiles (`4203142`),
  then personalized IOB/COB timing (`ce9dc00`). See `docs/iob-cob-models.md`.
- **Backend/Android** — `InsulinManagementSheet` plus insulin and sensor UI
  updates, backend glucose/Nightscout/model work, and two-user isolation tests
  (`9004334`).
- **Backend** — sensor quality management (`af79842`).
- **Android** — raw Health Connect records synced (`2cce601`).
- **Backend** — photo model provenance persisted, with resilient fallbacks
  (`99c7161`).

### Fixed

- **Backend** — CORS, dashboard local-time filters and Nightscout layout
  (`4890c86`).
- **Backend** — postprandial sweeps persisted and Nightscout markers cleaned
  (`653b677`); treatment markers anchored to CGM points (`f0674e2`); treatments
  anchored in portrait view (`9bae2f2`).
- **Android** — glucose cache migration schema aligned (`19ee861`); nullable
  postprandial payloads tolerated (`30a5072`).

Range: `af79842..99c7161`

---

## [0.6.0] — 2026-06-15 — Episodes engine, telemetry, auth hardening

### Added

- **Backend/Android** — unified meal/insulin grouping engine with mobile
  attribution (`829ceed`), the basis for every later episode surface.
- **Backend** — time-below-range and daily TIR, with corrected day-window labels
  (`d0ed588`).
- **App** — reworked settings and stats (`e7408ca`); telemetry and manual insulin
  entry (`025a7f7`).
- **Android** — captured photo review with Send / Retake / Close (`5593662`).
- **Android** — one-episode meals grouped into a single card (`7d77065`); delete
  entry and add-to-favorite quick-add on meal detail (`2c12a9c`).
- **Android** — new insulin and meal records appear instantly (`d2afb33`).

### Fixed

- **Android** — manual meal outbox stabilized (`a6f208f`); insulin outbox entries
  synced (`b9a45ed`); saved outbox items pruned (`33a8cbb`).
- **Backend** — photo capture time returned as a UTC instant (`a446b46`);
  postprandial CGM timestamps normalized (`c03c8ba`); duplicate photo estimate
  saves avoided (`af6b7e3`).
- **Auth** — a fresh bearer token is used after login (`1565368`); expired
  sessions are cleared on refresh failure (`1e8495a`); refresh sessions made
  long-lived (`fa68a69`).
- **Backend** — label estimates preserved when facts are incomplete (`b6cf298`).
- **Android** — photo estimate shown after upload (`73e3c6c`).
- **Deploy** — storage host paths documented (`b1ef8df`).

Range: `a6f208f..2c12a9c`

---

## [0.5.0] — 2026-05-29 — Insulin day links, digital twin, sensor quality

### Added

- **Desktop** — insulin review day links (`a84a627`), defaulting to auto rules
  (`cee379d`), aligned with the mockup (`8a5254f`), grouping nearby food-only
  events (`cd1bedd`).
- **Desktop** — digital twin page (`b9c38ad`) and its fit workflow (`001107b`).
- **Backend** — episode glucose snapshots saved on insulin links (`77381bd`).
- **Android** — Health Connect calorie sync (`f2645e1`), tolerating partial
  grants (`11df288`) and using Health Connect estimated goals (`e5c9d31`).

### Fixed

- **Backend** — disconnected sensor detection (`edd9cc5`); corrupt sensor data
  excluded (`e2bb814`); excluded CGM hidden everywhere (`1540611`); sensor
  duration display capped (`6c44315`).
- **Backend** — incomplete Health Connect activity totals rejected (`7f32250`),
  with observed-activity fallback (`ceb1388`) and a sedentary baseline
  (`bdada9f`).
- **Backend** — glucose points compared in wall time in stats (`8a39a9f`);
  imported Nightscout timestamp instants preserved (`1936ea9`).
- **Backend** — proxy config and local timeline events handled (`dff370e`).

Range: `dff370e..1540611`

---

## [0.4.0] — 2026-05-19 — Mobile meal stack and the wall-clock rule

The release where local wall-clock meal time became a hard invariant rather than
an incidental behavior (now AGENTS.md Product Invariant 4).

### Added

- **Android** — meal detail card stack (`2253baf`), with swipe-down easing
  (`6ce0b96`), photos kept loaded while paging (`1552369`), layout polish
  (`af502ed`) and tuned edit-sheet drag physics (`2e0bfed`).
- **Android** — history circle timeline (`851218a`); tarelka summary polish
  (`535aea8`); a broader mobile polish pass (`7311aca`, `2bebd8a`).
- **Deploy** — Ubuntu self-hosting support (`62168fd`, see
  `ADR-027-self-hosted-on-ubuntu.md`).

### Fixed

- **Backend** — meal wall-clock timestamps preserved through the pipeline
  (`8e1302d`); dashboard timestamps normalized (`4108bf3`).
- **Android** — photo capture wall time preserved (`d640eeb`).

Range: `2253baf..d640eeb`

---

## [0.3.0] — 2026-05-13 — Multi-user backend and product flavors

Introduced the multi-user model and the gluco/food split that the AGENTS.md
multi-user and feature-gating invariants now govern.

### Added

- **Backend** — multi-user scoping across owned data (`9681566`).
- **Android** — `gluco` and `food` product flavors (`bf3edd2`).
- **App** — multi-user food and gluco flows synchronized end to end (`f6e8848`).

### Fixed

- **Backend** — photo estimates auto-saved (`4710b30`); Nightscout dashboard data
  refresh (`0d40518`).

Range: `4710b30..f6e8848`

---

## [0.2.0] — 2026-05-05 — Design system and documentation baseline

### Added

- **Docs** — UI redesign documented and older docs archived (`14e1bfd`,
  merged in PR #1 `4f3adcf`); the origin of `docs/archive/2026-05-redesign/`.
- **Mockups** — mockup prototypes added alongside nutrient logic work
  (`a22db28`, `2c7d2e6`).

### Changed

- **Backend** — glucose dashboard and meal workflows updated (`6492651`);
  Nightscout sync and activity tracking updated (`bf7e83b`).
- **Desktop** — glucose sync copy and sidebar spacing refined (`dbcaa4e`).

Range: `6492651..dbcaa4e`

---

## [0.1.0] — 2026-04-30 — Monorepo bootstrap

First working end-to-end system: nutrition pipeline, Nightscout sync, glucose
dashboard, and the endocrinologist report.

### Added

- Initial Glucotracker monorepo — backend, desktop and Android concept in one
  repository (`ad4599e`).
- **Backend** — Nightscout sync and the nutrition pipeline (`25dd174`);
  Nightscout timeline episodes (`34a04a5`); glucose dashboard (`2ae1318`).
- **Desktop** — endocrinologist report flow (`ecdceda`).
- **Desktop** — history page redesign: quick filter chips, day summary, episode
  cards, insulin rows, glucose peak summary (`53e9c54`), then inline meal rows
  and a cleaner day summary (`e9ce6b0`).
- **Docs** — screens document added alongside shared meal mutation extraction
  (`86f7ced`).

### Fixed

- **Backend** — CGM values below 2.4 mmol/L filtered out as broken across all
  displays (`89802b4`) — the first version of what is now the sensor-quality
  layer.
- **Desktop** — feed page scrolling and the mini glucose chart (`893408f`).
- **Backend** — default timeline range widened to 7 days so episode grouping has
  enough context (`532d1fb`).

Range: `ad4599e..2ae1318`

---

[0.10.0]: https://github.com/megusto0/glucotracker/compare/51726a5...HEAD
[0.9.0]: https://github.com/megusto0/glucotracker/compare/87a32ec...51726a5
[0.8.0]: https://github.com/megusto0/glucotracker/compare/99c7161...87a32ec
[0.7.0]: https://github.com/megusto0/glucotracker/compare/2c12a9c...99c7161
[0.6.0]: https://github.com/megusto0/glucotracker/compare/1540611...2c12a9c
[0.5.0]: https://github.com/megusto0/glucotracker/compare/d640eeb...1540611
[0.4.0]: https://github.com/megusto0/glucotracker/compare/f6e8848...d640eeb
[0.3.0]: https://github.com/megusto0/glucotracker/compare/dbcaa4e...f6e8848
[0.2.0]: https://github.com/megusto0/glucotracker/compare/2ae1318...dbcaa4e
[0.1.0]: https://github.com/megusto0/glucotracker/commits/ad4599e
