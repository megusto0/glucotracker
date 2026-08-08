import { ArrowLeft, CalendarDays } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import type { TherapyAnalysisResponse } from "../../api/client";
import { useGlucoseTherapyAnalysis } from "../glucose/useGlucoseDashboard";
import "../nightscoutView/nightscout-page.css";
import "../therapyReview/therapy-review-page.css";
import "./therapy-analysis-page.css";

type Metric = TherapyAnalysisResponse["overall_icr_g_per_unit"];
type BasalProfile = TherapyAnalysisResponse["basal_profile"];
type BasalSlot = BasalProfile["slots"][number];
type BasalCompression = NonNullable<BasalProfile["compressions"]>[number];
type IcrComparison = NonNullable<
  TherapyAnalysisResponse["icr_proposals"]
>[number];
type IsfCase = NonNullable<TherapyAnalysisResponse["isf_cases"]>[number];

const REJECTION_LABELS: Record<string, string> = {
  not_isolated: "рядом была еда или другой болюс",
  not_elevated: "глюкоза не была повышена",
  no_fall: "глюкоза не снизилась",
  glucose_missing: "нет данных CGM",
  low_confidence: "эпизод определён неуверенно",
  dose_too_large: "доза больше 15 Ед",
  implausible: "результат вне правдоподобных границ",
};
type BasalMetricKey =
  | "quiet_drift_mmol_l_per_hour"
  | "elevated_hr_drift_mmol_l_per_hour"
  | "unknown_hr_drift_mmol_l_per_hour";
type PeriodDays = 30 | 90 | 180;

const PERIODS: Array<{ days: PeriodDays; label: string }> = [
  { days: 30, label: "30 дней" },
  { days: 90, label: "90 дней" },
  { days: 180, label: "180 дней" },
];

const CONFIDENCE_LABELS: Record<Metric["confidence"], string> = {
  none: "нет данных",
  low: "низкая",
  medium: "средняя",
  high: "высокая",
};

const BASAL_SERIES: Array<{
  className: string;
  key: BasalMetricKey;
  label: string;
}> = [
  {
    className: "therapy-basal-series--quiet",
    key: "quiet_drift_mmol_l_per_hour",
    label: "Спокойные часы",
  },
  {
    className: "therapy-basal-series--elevated",
    key: "elevated_hr_drift_mmol_l_per_hour",
    label: "Повышенный пульс",
  },
  {
    className: "therapy-basal-series--unknown",
    key: "unknown_hr_drift_mmol_l_per_hour",
    label: "Нет данных пульса",
  },
];

function formatDate(value: string) {
  return new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(new Date(`${value}T12:00:00`));
}

function metricValue(metric: Metric, unit: string) {
  return metric.value == null ? "—" : `${metric.value.toFixed(2)} ${unit}`;
}

function metricRange(metric: Metric) {
  return metric.q1 == null || metric.q3 == null
    ? "Диапазон пока не определён"
    : `50% случаев: ${metric.q1.toFixed(2)}–${metric.q3.toFixed(2)}`;
}

function MetricSummary({
  label,
  metric,
  unit,
  muted,
  note,
}: {
  label: string;
  metric: Metric;
  unit: string;
  muted?: boolean;
  note?: string;
}) {
  return (
    <article
      className={`therapy-analysis-summary-card${muted ? " therapy-analysis-summary-card--muted" : ""}`}
    >
      <span>{label}</span>
      <strong>{metricValue(metric, unit)}</strong>
      <small>{metricRange(metric)}</small>
      <small>
        {metric.sample_count} чистых случаев · достоверность{" "}
        {CONFIDENCE_LABELS[metric.confidence]}
      </small>
      {note ? <small className="therapy-analysis-caveat">{note}</small> : null}
    </article>
  );
}

function ratio(value?: number | null) {
  return typeof value === "number" ? value.toFixed(1) : "—";
}

function caseTime(value: string) {
  return new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    month: "short",
  }).format(new Date(value));
}

/**
 * The corrections behind the ISF median, one row each.
 *
 * A median of seven episodes is not something to take on trust, and it was
 * previously impossible to check: the page showed the number and the count and
 * nothing else. Each row carries the fall it was measured from and the reading
 * at four hours, so a value that looks wrong can be traced to its episode.
 */
function IsfCases({
  cases,
  rejections,
  correctionCount,
}: {
  cases: IsfCase[];
  rejections: Record<string, number>;
  correctionCount: number;
}) {
  const rejected = Object.entries(rejections).filter(([, count]) => count > 0);
  if (!cases.length && !rejected.length) return null;

  return (
    <section className="therapy-analysis-isf-card">
      <header>
        <div>
          <strong>Из чего сложился ISF</strong>
          <span>
            {cases.length} из {correctionCount} коррекций за период
          </span>
        </div>
        <small>Снижение считается до минимума, а не до отметки «4 часа»</small>
      </header>

      {cases.length ? (
        <div className="therapy-analysis-isf-scroll">
          <table>
            <thead>
              <tr>
                <th>Когда</th>
                <th>Доза</th>
                <th>Глюкоза</th>
                <th>Минимум</th>
                <th>Через 4 ч</th>
                <th>ISF</th>
              </tr>
            </thead>
            <tbody>
              {cases.map((item) => (
                <tr key={item.occurred_at}>
                  <th scope="row">{caseTime(item.occurred_at)}</th>
                  <td>{item.insulin_units.toFixed(1)} Ед</td>
                  <td>{item.glucose_start.toFixed(1)}</td>
                  <td>
                    {item.glucose_nadir.toFixed(1)}
                    <small> +{item.minutes_to_nadir} мин</small>
                  </td>
                  <td className="therapy-analysis-isf-horizon">
                    {typeof item.glucose_at_horizon === "number"
                      ? item.glucose_at_horizon.toFixed(1)
                      : "—"}
                  </td>
                  <td>
                    <b>{item.isf_mmol_l_per_unit.toFixed(2)}</b>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {rejected.length ? (
        <footer>
          <span>Остальные коррекции не подошли:</span>
          <ul>
            {rejected.map(([reason, count]) => (
              <li key={reason}>
                {REJECTION_LABELS[reason] ?? reason} — {count}
              </li>
            ))}
          </ul>
        </footer>
      ) : null}
    </section>
  );
}

/**
 * Configured ratio against what outcomes imply, on the configured slots.
 *
 * The four-hour table below cannot answer "should I change anything?" — its
 * bins are not the bins the settings use, so the two numbers were never
 * comparable. These rows are.
 */
function ConfiguredVsMeasured({
  rows,
  excludedForActivity,
}: {
  rows: IcrComparison[];
  excludedForActivity: number;
}) {
  if (!rows.length) return null;
  return (
    <section className="therapy-analysis-proposal-card">
      <header>
        <div>
          <strong>Настройки против данных</strong>
          <span>ICR по вашим слотам, г/Ед</span>
        </div>
        <small>
          Предложение сдвинуто к текущему значению и ограничено по шагу
        </small>
      </header>

      <ul className="therapy-analysis-proposal-list">
        {rows.map((row) => {
          const delta =
            typeof row.proposed_icr_g_per_unit === "number" &&
            typeof row.configured_icr_g_per_unit === "number"
              ? row.proposed_icr_g_per_unit - row.configured_icr_g_per_unit
              : null;
          const meaningful = delta !== null && Math.abs(delta) >= 0.2;
          return (
            <li key={row.daypart}>
              <div className="therapy-analysis-proposal-slot">
                <strong>{row.label}</strong>
                <small>
                  {`${String(row.start_hour).padStart(2, "0")}:00–${String(row.end_hour).padStart(2, "0")}:00`}
                </small>
              </div>
              <div className="therapy-analysis-proposal-values">
                <div>
                  <span>сейчас</span>
                  <b>{ratio(row.configured_icr_g_per_unit)}</b>
                </div>
                <i aria-hidden="true">→</i>
                <div>
                  <span>по данным</span>
                  <b>{ratio(row.measured_icr_g_per_unit)}</b>
                </div>
                <div
                  className={
                    meaningful
                      ? "therapy-analysis-proposal-move"
                      : "therapy-analysis-proposal-hold"
                  }
                >
                  <span>предложение</span>
                  <b>
                    {row.proposed_icr_g_per_unit == null
                      ? "—"
                      : meaningful
                        ? `${ratio(row.proposed_icr_g_per_unit)}`
                        : "без изменений"}
                  </b>
                </div>
              </div>
              <small className="therapy-analysis-proposal-note">
                {row.note
                  ? row.note
                  : `${row.episode_count} приёмов · достоверность ${CONFIDENCE_LABELS[row.confidence]}${row.capped ? " · шаг ограничен" : ""}`}
              </small>
            </li>
          );
        })}
      </ul>

      <footer>
        {excludedForActivity ? (
          <span>
            Рядом с нагрузкой исключено приёмов: {excludedForActivity}.
          </span>
        ) : null}
        <strong>
          Ничего не применяется автоматически. Значение меняется вручную в
          цифровом двойнике.
        </strong>
      </footer>
    </section>
  );
}

/** Below this a cell is one or two episodes, and a bar makes it look solid. */
const MIN_SAMPLES_FOR_BAR = 3;

/**
 * Bars are scaled to the values present, not to a fixed domain.
 *
 * Against a fixed maximum of 40 g/U every real ratio sat in the first quarter
 * of the track, so 8.0 and 11.0 drew the same bar and the column carried no
 * information at all.
 */
function MetricCell({
  metric,
  domain,
  unit,
}: {
  metric: Metric;
  domain: { min: number; max: number };
  unit: string;
}) {
  const span = Math.max(0.1, domain.max - domain.min);
  const thin = metric.sample_count < MIN_SAMPLES_FOR_BAR;
  const width =
    metric.value == null
      ? 0
      : Math.max(4, Math.min(100, ((metric.value - domain.min) / span) * 100));
  return (
    <div
      className={`therapy-analysis-metric${thin ? " therapy-analysis-metric--thin" : ""}`}
    >
      <div>
        <strong>{metricValue(metric, unit)}</strong>
        <small>{metric.sample_count} сл.</small>
      </div>
      {metric.value != null && !thin ? (
        <div className="therapy-analysis-bar" aria-hidden="true">
          <i style={{ width: `${width}%` }} />
        </div>
      ) : null}
      <small>
        {metric.value == null
          ? CONFIDENCE_LABELS[metric.confidence]
          : thin
            ? "мало случаев"
            : metric.q1 == null || metric.q3 == null
              ? CONFIDENCE_LABELS[metric.confidence]
              : `${metric.q1.toFixed(2)}–${metric.q3.toFixed(2)} · ${CONFIDENCE_LABELS[metric.confidence]}`}
      </small>
    </div>
  );
}

/** Range across the slots that actually carry evidence, padded a little. */
function metricDomain(values: Array<number | null | undefined>) {
  const known = values.filter(
    (value): value is number => typeof value === "number",
  );
  if (!known.length) return { min: 0, max: 1 };
  const min = Math.min(...known);
  const max = Math.max(...known);
  const pad = Math.max(0.5, (max - min) * 0.25);
  return { min: Math.max(0, min - pad), max: max + pad };
}

function chartX(hour: number) {
  return 42 + (hour / 23) * 878;
}

function chartY(value: number, scale: number) {
  return 120 - (value / scale) * 90;
}

function lineSegments(
  slots: BasalSlot[],
  key: BasalMetricKey,
  scale: number,
) {
  const segments: string[] = [];
  let current: string[] = [];
  for (const slot of slots) {
    const value = slot[key].value;
    if (value == null) {
      if (current.length > 1) segments.push(current.join(" "));
      current = [];
      continue;
    }
    current.push(`${chartX(slot.hour)},${chartY(value, scale)}`);
  }
  if (current.length > 1) segments.push(current.join(" "));
  return segments;
}

function BasalProfileChart({ profile }: { profile: BasalProfile }) {
  const [windowCount, setWindowCount] = useState(24);
  const values = profile.slots.flatMap((slot) =>
    BASAL_SERIES.flatMap((series) => {
      const value = slot[series.key].value;
      return value == null ? [] : [Math.abs(value)];
    }),
  );
  const scale = Math.max(
    1,
    Math.ceil(Math.max(0, ...values) * 2) / 2,
  );
  const hasEvidence = values.length > 0;
  const hourlyFallback: BasalCompression = {
    projected_daily_basal_units: profile.projected_daily_basal_units,
    slots: profile.slots.map((slot) => ({
      autotuned_basal_u_per_hour:
        slot.autotuned_basal_u_per_hour ?? slot.configured_basal_u_per_hour,
      autotuned_hour_count:
        slot.autotuned_basal_u_per_hour == null ? 0 : 1,
      basal_adjustment_u_per_hour: slot.basal_adjustment_u_per_hour ?? 0,
      configured_basal_u_per_hour: slot.configured_basal_u_per_hour,
      end_hour: slot.hour + 1,
      equivalent_drift_mmol_l_per_hour:
        slot.quiet_drift_mmol_l_per_hour.value ?? 0,
      evidence_window_count:
        slot.quiet_drift_mmol_l_per_hour.sample_count,
      label: `${slot.label}–${(slot.hour + 1).toString().padStart(2, "0")}:00`,
      start_hour: slot.hour,
    })),
    window_count: 24,
  };
  const compression =
    profile.compressions?.find((item) => item.window_count === windowCount) ??
    hourlyFallback;

  return (
    <section className="therapy-basal-card">
      <header>
        <div>
          <strong>24 часа: фоновая стабильность</strong>
          <span>
            Медианный дрейф нормализованной глюкозы, ммоль/л за час
          </span>
        </div>
        <small>
          Окно {profile.window_minutes} мин · без еды и болюса{" "}
          {profile.washout_minutes / 60} ч
        </small>
      </header>

      <div className="therapy-basal-stats">
        <span>
          <i className="therapy-basal-dot therapy-basal-dot--quiet" />
          спокойно <strong>{profile.quiet_window_count}</strong>
        </span>
        <span>
          <i className="therapy-basal-dot therapy-basal-dot--elevated" />
          высокий пульс <strong>{profile.elevated_hr_window_count}</strong>
        </span>
        <span>
          <i className="therapy-basal-dot therapy-basal-dot--unknown" />
          пульс неизвестен <strong>{profile.unknown_hr_window_count}</strong>
        </span>
        {profile.elevated_hr_threshold_bpm != null ? (
          <small>
            высокий пульс от {profile.elevated_hr_threshold_bpm.toFixed(0)} уд/мин
            {profile.resting_reference_bpm != null
              ? ` · личный фон ${profile.resting_reference_bpm.toFixed(0)}`
              : ""}
          </small>
        ) : (
          <small>Для разделения активности пока нет данных пульса</small>
        )}
      </div>

      <section
        aria-labelledby="basal-autotune-title"
        className="therapy-basal-autotune"
      >
        <header>
          <div>
            <strong id="basal-autotune-title">
              Basal autotune для плоского фона
            </strong>
            <span>
              00–03: 0,80 · 03–12: 0,70 · 12–16: 0,80 · 16–00: 1,00 Ед/ч
            </span>
          </div>
          <small>
            ISF {profile.autotune_isf_mmol_l_per_unit.toFixed(2)} ммоль/л/Ед
          </small>
        </header>
        <div className="therapy-basal-compression-control">
          <label htmlFor="basal-window-count">
            <span>Количество временных окон</span>
            <strong>{compression.window_count}</strong>
          </label>
          <input
            aria-label="Количество временных окон"
            id="basal-window-count"
            max={24}
            min={4}
            onChange={(event) => setWindowCount(Number(event.target.value))}
            step={1}
            type="range"
            value={windowCount}
          />
          <div>
            <span>4 окна · сильное сжатие</span>
            <span>24 окна · каждый час</span>
          </div>
          <small>
            Границы выбираются по сходству ставок и числу спокойных normalized
            окон. Суточная доза сохраняется.
          </small>
        </div>
        <div className="therapy-basal-autotune-totals">
          <span>
            исходный профиль
            <strong>
              {profile.configured_daily_basal_units.toFixed(2)} Ед/сут
            </strong>
          </span>
          <span>
            рассчитано часов
            <strong>{profile.autotuned_hour_count} / 24</strong>
          </span>
          <span>
            при замене рассчитанных часов
            <strong>
              {compression.projected_daily_basal_units.toFixed(2)} Ед/сут
            </strong>
          </span>
        </div>
        <div className="therapy-basal-autotune-scroll">
          <table>
            <thead>
              <tr>
                <th>Интервал</th>
                <th>Исходно</th>
                <th>Quiet-drift normalized</th>
                <th>Поправка</th>
                <th>Для плоского фона</th>
              </tr>
            </thead>
            <tbody>
              {compression.slots.map((slot) => {
                const durationHours = slot.end_hour - slot.start_hour;
                return (
                  <tr key={slot.start_hour}>
                    <th scope="row">{slot.label}</th>
                    <td>{slot.configured_basal_u_per_hour.toFixed(2)} Ед/ч</td>
                    <td>
                      {slot.autotuned_hour_count === 0 ? (
                        "—"
                      ) : (
                        <>
                          {slot.equivalent_drift_mmol_l_per_hour > 0 ? "+" : ""}
                          {slot.equivalent_drift_mmol_l_per_hour.toFixed(2)}{" "}
                          ммоль/л/ч
                          <small>{slot.evidence_window_count} окон данных</small>
                        </>
                      )}
                    </td>
                    <td>
                      {slot.basal_adjustment_u_per_hour == null
                        ? "—"
                        : `${slot.basal_adjustment_u_per_hour > 0 ? "+" : ""}${slot.basal_adjustment_u_per_hour.toFixed(2)} Ед/ч`}
                    </td>
                    <td>
                      <strong>
                        {slot.autotuned_basal_u_per_hour.toFixed(2)} Ед/ч
                      </strong>
                      {slot.autotuned_hour_count < durationHours ? (
                        <small>
                          normalized-оценка: {slot.autotuned_hour_count} из{" "}
                          {durationHours} ч
                        </small>
                      ) : null}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p>
          Эквивалентная ретроспективная ставка = исходная + quiet-drift / ISF.
          Используется только normalized CGM; часы с повышенным или неизвестным
          пульсом не формируют расчёт.
        </p>
      </section>

      {hasEvidence ? (
        <div className="therapy-basal-chart-scroll">
          <svg
            aria-describedby="therapy-basal-chart-description"
            aria-label="Фоновое изменение глюкозы по часам суток"
            className="therapy-basal-chart"
            role="img"
            viewBox="0 0 960 250"
          >
            <title id="therapy-basal-chart-title">
              Фоновое изменение глюкозы по часам суток
            </title>
            <desc id="therapy-basal-chart-description">
              Бирюзовая линия показывает часы со спокойным пульсом, оранжевая —
              часы с повышенным пульсом, серая — часы без достаточных данных
              пульса. Значения выше нуля означают рост глюкозы.
            </desc>
            {[scale, 0, -scale].map((value) => (
              <g key={value}>
                <line
                  className={
                    value === 0
                      ? "therapy-basal-zero"
                      : "therapy-basal-grid"
                  }
                  x1="42"
                  x2="920"
                  y1={chartY(value, scale)}
                  y2={chartY(value, scale)}
                />
                <text
                  className="therapy-basal-axis-label"
                  textAnchor="end"
                  x="35"
                  y={chartY(value, scale) + 4}
                >
                  {value > 0 ? `+${value}` : value}
                </text>
              </g>
            ))}
            {profile.slots
              .filter((slot) => slot.hour % 3 === 0)
              .map((slot) => (
                <text
                  className="therapy-basal-hour-label"
                  key={slot.hour}
                  textAnchor="middle"
                  x={chartX(slot.hour)}
                  y="236"
                >
                  {slot.label}
                </text>
              ))}
            {BASAL_SERIES.map((series) => (
              <g className={series.className} key={series.key}>
                {lineSegments(profile.slots, series.key, scale).map(
                  (points) => (
                    <polyline
                      fill="none"
                      key={points}
                      points={points}
                    />
                  ),
                )}
                {profile.slots.map((slot) => {
                  const metric = slot[series.key];
                  if (metric.value == null) return null;
                  return (
                    <circle
                      cx={chartX(slot.hour)}
                      cy={chartY(metric.value, scale)}
                      key={slot.hour}
                      r="4"
                    >
                      <title>
                        {slot.label}: {series.label.toLowerCase()} ·{" "}
                        {metric.value > 0 ? "+" : ""}
                        {metric.value.toFixed(2)} ммоль/л/ч ·{" "}
                        {metric.sample_count} случаев
                      </title>
                    </circle>
                  );
                })}
              </g>
            ))}
          </svg>
        </div>
      ) : (
        <div className="therapy-basal-empty">
          За этот период не найдено часовых окон без недавней еды и болюса.
        </div>
      )}

      <footer>
        <span>
          Выше нуля — глюкоза росла; ниже нуля — падала. Оценка «стабильно»
          требует не менее трёх спокойных окон в один и тот же час.
        </span>
        <strong>
          Это проверка закономерностей, а не рекомендация менять базальный
          инсулин.
        </strong>
      </footer>
    </section>
  );
}

export function TherapyAnalysisPage() {
  const navigate = useNavigate();
  const [periodDays, setPeriodDays] = useState<PeriodDays>(90);
  const [target, setTarget] = useState(6);
  const analysis = useGlucoseTherapyAnalysis(periodDays, target);

  return (
    <div className="therapy-review-page therapy-analysis-page">
      <header className="therapy-review-toolbar">
        <button
          aria-label="Назад к разбору по дням"
          onClick={() => navigate("/nightscout/review")}
          type="button"
        >
          <ArrowLeft size={19} />
        </button>
        <div className="therapy-review-toolbar-title">
          <span>Nightscout</span>
          <strong>ICR, ISF и базал по часам</strong>
        </div>
        <button
          aria-label="Открыть разбор по дням"
          onClick={() => navigate("/nightscout/review")}
          type="button"
        >
          <CalendarDays size={18} />
        </button>
      </header>

      <main>
        <section className="therapy-analysis-controls">
          <fieldset>
            <legend>Период</legend>
            {PERIODS.map((period) => (
              <button
                aria-pressed={periodDays === period.days}
                key={period.days}
                onClick={() => setPeriodDays(period.days)}
                type="button"
              >
                {period.label}
              </button>
            ))}
          </fieldset>
          <label>
            <span>Цель для ретроспективной поправки</span>
            <input
              inputMode="decimal"
              max={10}
              min={3.9}
              onChange={(event) => {
                const next = Number(event.target.value);
                if (Number.isFinite(next) && next >= 3.9 && next <= 10)
                  setTarget(next);
              }}
              step={0.1}
              type="number"
              value={target}
            />
            <small>ммоль/л</small>
          </label>
        </section>

        <section className="therapy-review-explainer">
          <strong>Долгосрочная ретроспектива</strong>
          <p>
            ICR показывает граммы углеводов на 1 Ед, ISF — ожидаемое снижение
            глюкозы от 1 Ед. Используются медианы только из изолированных
            завершённых эпизодов; это анализ прошлого, не рекомендация дозы.
          </p>
          {analysis.data ? (
            <small>
              {formatDate(analysis.data.from_date)} —{" "}
              {formatDate(analysis.data.to_date)}
              {" · "}
              цель {analysis.data.target_mmol_l.toFixed(1)}
              {" · "}
              рассчитано{" "}
              {new Date(analysis.data.computed_at).toLocaleString("ru-RU")}
            </small>
          ) : null}
        </section>

        {analysis.isLoading ? (
          <div className="therapy-review-state">
            Собираю чистые эпизоды за выбранный период…
          </div>
        ) : analysis.isError || !analysis.data ? (
          <div className="therapy-review-state therapy-review-state--error">
            Не удалось собрать долгосрочный анализ.
          </div>
        ) : (
          <>
            <section
              aria-label="Общие показатели"
              className="therapy-analysis-summary"
            >
              <MetricSummary
                label="Общий ICR"
                metric={analysis.data.overall_icr_g_per_unit}
                unit="г/Ед"
              />
              <MetricSummary
                label="Общий ISF"
                metric={analysis.data.overall_isf_mmol_l_per_unit}
                muted={analysis.data.isf_identifiability !== "identified"}
                note={analysis.data.isf_note || undefined}
                unit="ммоль/л/Ед"
              />
            </section>

            <ConfiguredVsMeasured
              excludedForActivity={
                analysis.data.icr_excluded_for_activity ?? 0
              }
              rows={analysis.data.icr_proposals ?? []}
            />

            <IsfCases
              cases={analysis.data.isf_cases ?? []}
              correctionCount={analysis.data.isf_correction_count ?? 0}
              rejections={analysis.data.isf_rejections ?? {}}
            />

            <section className="therapy-analysis-table-card">
              <header>
                <div>
                  <strong>Зависимость от времени суток</strong>
                  <span>Локальное время</span>
                </div>
                <small>
                  ICR: исход через {analysis.data.icr_horizon_minutes / 60} ч
                  {" · "}
                  ISF: через {analysis.data.isf_horizon_minutes / 60} ч
                </small>
              </header>
              <div className="therapy-analysis-table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Время</th>
                      <th>ICR, г/Ед</th>
                      <th>ISF, ммоль/л/Ед</th>
                    </tr>
                  </thead>
                  <tbody>
                    {analysis.data.slots.map((slot) => (
                      <tr key={slot.start_hour}>
                        <th scope="row">{slot.label}</th>
                        <td>
                          <MetricCell
                            domain={metricDomain(
                              analysis.data.slots.map(
                                (row) => row.icr_g_per_unit.value,
                              ),
                            )}
                            metric={slot.icr_g_per_unit}
                            unit="г/Ед"
                          />
                        </td>
                        <td>
                          <MetricCell
                            domain={metricDomain(
                              analysis.data.slots.map(
                                (row) => row.isf_mmol_l_per_unit.value,
                              ),
                            )}
                            metric={slot.isf_mmol_l_per_unit}
                            unit="ммоль/л/Ед"
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            <BasalProfileChart profile={analysis.data.basal_profile} />

            <section className="therapy-review-method">
              <strong>Какие случаи вошли</strong>
              {(analysis.data.notes ?? []).map((note) => (
                <span key={note}>{note}</span>
              ))}
            </section>
          </>
        )}
      </main>
    </div>
  );
}
