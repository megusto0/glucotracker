import {
  ArrowLeft,
  ChartNoAxesCombined,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
} from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { TherapyReviewDayResponse } from "../../api/client";
import {
  useGlucoseTherapyReview,
  usePrefetchGlucoseTherapyReview,
  useRecalculateGlucoseTherapyReview,
} from "../glucose/useGlucoseDashboard";
import "../nightscoutView/nightscout-page.css";
import "./therapy-review-page.css";

type ReviewItem = TherapyReviewDayResponse["items"][number];
type BodyState = NonNullable<TherapyReviewDayResponse["body_states"]>[number];
type BodyContext = NonNullable<ReviewItem["body_context"]>[number];

const CLASS_LABELS: Record<ReviewItem["classification"], string> = {
  meal: "Приём пищи",
  snack: "Перекус",
  carb_correction: "Коррекция углеводами",
  insulin_correction: "Коррекция инсулином",
  mixed: "Смешанный эпизод",
  unresolved: "Требует разбора",
};

const BODY_CONTEXT_LABELS: Record<BodyContext, string> = {
  after_sleep: "первый после сна",
  during_sleep: "во сне",
  near_activity: "рядом с нагрузкой",
};

const HORIZONS = [
  { minutes: 60, label: "через 1 час" },
  { minutes: 120, label: "через 2 часа" },
  { minutes: 180, label: "через 3 часа" },
  { minutes: 240, label: "через 4 часа" },
] as const;

function localDateKey(value: Date) {
  const year = value.getFullYear();
  const month = `${value.getMonth() + 1}`.padStart(2, "0");
  const day = `${value.getDate()}`.padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function shiftDate(date: string, amount: number) {
  const value = new Date(`${date}T12:00:00`);
  value.setDate(value.getDate() + amount);
  return localDateKey(value);
}

function displayDate(date: string) {
  return new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "long",
    weekday: "long",
    year: "numeric",
  }).format(new Date(`${date}T12:00:00`));
}

function displayTime(timestamp: string) {
  const match = timestamp.match(/T(\d{2}:\d{2})/);
  return match?.[1] ?? "—";
}

function value(value?: number | null, unit?: ReviewItem["value_unit"]) {
  const displayUnit = unit === "U" ? "Ед" : unit;
  return typeof value === "number"
    ? `${value.toFixed(1)} ${displayUnit ?? ""}`
    : "—";
}

function glucose(value?: number | null) {
  return typeof value === "number" ? value.toFixed(1) : "—";
}

function primaryGlucose(
  normalized?: number | null,
  raw?: number | null,
) {
  return typeof normalized === "number" ? normalized : raw;
}

function calculationMessage(item: ReviewItem) {
  if (item.calculation_status === "low_or_falling")
    return "Скрыто: глюкоза низкая или быстро снижается";
  if (item.calculation_status === "insufficient_history")
    return "Недостаточно похожих эпизодов";
  if (item.calculation_status === "glucose_unavailable")
    return "Нет глюкозы перед эпизодом";
  if (item.calculation_status === "trend_unavailable")
    return "Недостаточно данных о тренде";
  if (item.calculation_status === "calculation_withheld")
    return "Расчёт не применим";
  return null;
}

/** Fraction of the day, so a state can be drawn on a 24-hour strip. */
function dayFraction(timestamp: string, date: string) {
  const dayStart = new Date(`${date}T00:00:00`).getTime();
  const value = new Date(timestamp).getTime();
  if (!Number.isFinite(value) || !Number.isFinite(dayStart)) return 0;
  return Math.min(1, Math.max(0, (value - dayStart) / 86_400_000));
}

function duration(minutes: number) {
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (hours && rest) return `${hours} ч ${rest} мин`;
  if (hours) return `${hours} ч`;
  return `${rest} мин`;
}

function stateTitle(state: BodyState) {
  const kind = state.kind === "sleep" ? "Сон" : (state.label ?? "Нагрузка");
  const source =
    state.source === "recorded" ? "с часов" : "по пульсу";
  const peak =
    state.kind === "activity" && typeof state.peak_bpm === "number"
      ? ` · пик ${state.peak_bpm.toFixed(0)} уд/мин`
      : "";
  return `${kind} · ${displayTime(state.start_at)}–${displayTime(state.end_at)} · ${duration(state.total_minutes)} · ${source}${peak}`;
}

/**
 * A 24-hour strip of the day's sleep and hard effort.
 *
 * The dosing model still ignores exercise entirely, so a meal that landed
 * beside a session has numbers that should not be read the same way as the
 * rest. Showing the day's shape is what makes that visible.
 */
function DayContext({
  date,
  states,
}: {
  date: string;
  states: BodyState[];
}) {
  const sleepMinutes = states
    .filter((state) => state.kind === "sleep")
    .reduce((total, state) => total + state.minutes, 0);
  const activity = states.filter((state) => state.kind === "activity");

  return (
    <section className="therapy-review-context">
      <header>
        <strong>Контекст дня</strong>
        <span>
          {sleepMinutes ? `сон ${duration(sleepMinutes)}` : "сон не найден"}
          {activity.length
            ? ` · нагрузок: ${activity.length}`
            : " · нагрузок нет"}
        </span>
      </header>

      {states.length ? (
        <>
          <div
            aria-label="Сон и нагрузки за сутки"
            className="therapy-review-context-strip"
            role="img"
          >
            {states.map((state) => (
              <span
                className={`therapy-review-context-band therapy-review-context-band--${state.kind} therapy-review-context-band--${state.source.replace(/_/g, "-")}`}
                key={`${state.kind}-${state.start_at}`}
                style={{
                  left: `${dayFraction(state.start_at, date) * 100}%`,
                  width: `${Math.max(
                    0.6,
                    (dayFraction(state.end_at, date) -
                      dayFraction(state.start_at, date)) *
                      100,
                  )}%`,
                }}
                title={stateTitle(state)}
              />
            ))}
            {[6, 12, 18].map((hour) => (
              <span
                aria-hidden="true"
                className="therapy-review-context-tick"
                key={hour}
                style={{ left: `${(hour / 24) * 100}%` }}
              />
            ))}
          </div>
          <ul className="therapy-review-context-list">
            {states.map((state) => (
              <li key={`row-${state.kind}-${state.start_at}`}>
                <b
                  className={`therapy-review-context-dot therapy-review-context-dot--${state.kind}`}
                />
                <span>{stateTitle(state)}</span>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <p>
          Нет ни сессий с часов, ни пульса, по которому их можно было бы
          восстановить.
        </p>
      )}
    </section>
  );
}

const QUALITY_LABELS: Record<ReviewItem["outcome_quality"], string> = {
  in_range: "без выхода за диапазон",
  spike: "был пик",
  low: "был провал",
  spike_and_low: "пик и провал",
  unknown: "нет данных о ходе",
};

/**
 * The episode's glucose curve across the horizon.
 *
 * Two endpoints cannot tell a flat landing apart from a spike that came back
 * down by the time anyone looked, and those need different answers — the first
 * is a dose that worked, the second a dose that arrived too late.
 */
function Trajectory({ item, target }: { item: ReviewItem; target: number }) {
  const values = item.trajectory ?? [];
  const known = values.filter((value): value is number => value !== null);
  if (known.length < 2) return null;

  const step = item.trajectory_step_minutes ?? 10;
  const width = 100;
  const height = 34;
  const low = Math.min(3.0, ...known);
  const high = Math.max(11.0, ...known);
  const span = Math.max(1, high - low);
  const x = (index: number) => (index / (values.length - 1)) * width;
  const y = (value: number) => height - ((value - low) / span) * height;
  const path = values
    .map((value, index) =>
      value === null ? null : `${x(index).toFixed(1)},${y(value).toFixed(1)}`,
    )
    .filter((point): point is string => point !== null)
    .join(" ");
  const bandTop = y(Math.min(high, 10));
  const bandBottom = y(Math.max(low, 3.9));

  return (
    <div className="therapy-review-trajectory">
      <svg
        aria-label={`Ход глюкозы за ${Math.round(((values.length - 1) * step) / 60)} ч`}
        preserveAspectRatio="none"
        role="img"
        viewBox={`0 0 ${width} ${height}`}
      >
        <rect
          className="therapy-review-trajectory-band"
          height={Math.max(1, bandBottom - bandTop)}
          width={width}
          x="0"
          y={bandTop}
        />
        <line
          className="therapy-review-trajectory-target"
          x1="0"
          x2={width}
          y1={y(target)}
          y2={y(target)}
        />
        <polyline className="therapy-review-trajectory-line" points={path} />
      </svg>
      <div className="therapy-review-trajectory-marks">
        {typeof item.peak_mmol_l === "number" ? (
          <span
            className={
              item.peak_mmol_l > 10 ? "therapy-review-mark--high" : undefined
            }
          >
            пик {item.peak_mmol_l.toFixed(1)}
            {typeof item.peak_after_minutes === "number"
              ? ` · +${item.peak_after_minutes} мин`
              : ""}
          </span>
        ) : null}
        {typeof item.nadir_mmol_l === "number" ? (
          <span
            className={
              item.nadir_mmol_l < 3.9 ? "therapy-review-mark--low" : undefined
            }
          >
            минимум {item.nadir_mmol_l.toFixed(1)}
            {typeof item.nadir_after_minutes === "number"
              ? ` · +${item.nadir_after_minutes} мин`
              : ""}
          </span>
        ) : null}
        {item.minutes_above_high ? (
          <span className="therapy-review-mark--high">
            выше 10: {item.minutes_above_high} мин
          </span>
        ) : null}
        {item.minutes_below_low ? (
          <span className="therapy-review-mark--low">
            ниже 3,9: {item.minutes_below_low} мин
          </span>
        ) : null}
      </div>
    </div>
  );
}

function ReviewCard({
  item,
  target,
}: {
  item: ReviewItem;
  target: number;
}) {
  const start = primaryGlucose(
    item.glucose_start_normalized,
    item.glucose_start_raw,
  );
  const after = primaryGlucose(
    item.glucose_after_normalized,
    item.glucose_after_raw,
  );
  const quality = item.outcome_quality ?? "unknown";
  const outcomeInRange =
    typeof after === "number" && after >= 3.9 && after <= 10;
  // An endpoint in range with a spike behind it is not a clean episode, and
  // the badge is the first thing read on this card.
  const clean = outcomeInRange && quality === "in_range";
  const calculationNote = calculationMessage(item);

  return (
    <article
      className={`therapy-review-card therapy-review-card--${item.classification.replace(/_/g, "-")}`}
    >
      <header>
        <div>
          <time>{displayTime(item.start_at)}</time>
          <span>{CLASS_LABELS[item.classification]}</span>
        </div>
        <span
          className={`therapy-review-outcome${clean ? " therapy-review-outcome--range" : ""}${quality === "low" || quality === "spike_and_low" ? " therapy-review-outcome--low" : ""}`}
        >
          {typeof after === "number"
            ? clean
              ? "чисто"
              : quality === "unknown"
                ? outcomeInRange
                  ? "в диапазоне"
                  : after < 3.9
                    ? "низко"
                    : "высоко"
                : QUALITY_LABELS[quality]
            : "нет исхода"}
        </span>
      </header>

      <h2>{item.title}</h2>
      {item.body_context?.length ? (
        <div className="therapy-review-context-tags">
          {item.body_context.map((context) => (
            <span
              className={`therapy-review-context-tag therapy-review-context-tag--${context.replace(/_/g, "-")}`}
              key={context}
            >
              {BODY_CONTEXT_LABELS[context]}
            </span>
          ))}
        </div>
      ) : null}
      <div className="therapy-review-glucose">
        <div>
          <span>Глюкоза до</span>
          <strong>{glucose(start)}</strong>
          <small>
            raw {glucose(item.glucose_start_raw)} · norm{" "}
            {glucose(item.glucose_start_normalized)}
          </small>
        </div>
        <b aria-hidden="true">→</b>
        <div>
          <span>Через {item.horizon_minutes / 60} ч</span>
          <strong>{glucose(after)}</strong>
          <small>
            raw {glucose(item.glucose_after_raw)} · norm{" "}
            {glucose(item.glucose_after_normalized)}
          </small>
        </div>
      </div>

      <Trajectory item={item} target={target} />

      <div className="therapy-review-values">
        <div>
          <span>Фактически</span>
          <strong>{value(item.actual_value, item.value_unit)}</strong>
        </div>
        <div>
          <span>Рассчитано</span>
          <strong>{value(item.calculated_value, item.value_unit)}</strong>
        </div>
        <div className="therapy-review-adjusted">
          <span>С поправкой по факту</span>
          <strong>{value(item.adjusted_actual_value, item.value_unit)}</strong>
        </div>
      </div>

      <footer>
        {calculationNote ? <span>{calculationNote}</span> : null}
        <span>
          Цель {target.toFixed(1)}
          {typeof item.isf_mmol_l_per_unit === "number"
            ? ` · ISF ${item.isf_mmol_l_per_unit.toFixed(1)}`
            : ""}
        </span>
        {item.notes?.length ? <small>{item.notes.join(" · ")}</small> : null}
      </footer>
    </article>
  );
}

export function TherapyReviewPage() {
  const navigate = useNavigate();
  const today = localDateKey(new Date());
  const [date, setDate] = useState(today);
  const [target, setTarget] = useState(6);
  const [horizon, setHorizon] = useState(120);
  const review = useGlucoseTherapyReview(date, target, horizon);
  const recalculation = useRecalculateGlucoseTherapyReview();
  const prefetchReview = usePrefetchGlucoseTherapyReview();
  const isRefreshing = review.isFetching || recalculation.isPending;

  // Stepping day by day is how this page is read, so the neighbours are built
  // while the current day is on screen.
  useEffect(() => {
    const neighbours = [shiftDate(date, -1), shiftDate(date, -2)];
    if (date < today) neighbours.push(shiftDate(date, 1));
    const timer = window.setTimeout(
      () => prefetchReview(neighbours, target, horizon),
      600,
    );
    return () => window.clearTimeout(timer);
  }, [date, horizon, prefetchReview, target, today]);

  return (
    <div className="therapy-review-page">
      <header className="therapy-review-toolbar">
        <button
          aria-label="Назад к графику"
          onClick={() => navigate("/nightscout")}
          type="button"
        >
          <ArrowLeft size={19} />
        </button>
        <div className="therapy-review-toolbar-title">
          <span>Nightscout</span>
          <strong>Разбор терапии по дням</strong>
        </div>
        <nav aria-label="Разделы разбора" className="therapy-review-toolbar-actions">
          <button
            aria-label="Анализ ICR и ISF"
            onClick={() => navigate("/nightscout/review/analysis")}
            type="button"
          >
            <ChartNoAxesCombined size={18} />
          </button>
          <button
            aria-label="Обновить разбор"
            disabled={isRefreshing}
            onClick={() =>
              recalculation.mutate({
                date,
                targetMmolL: target,
                horizonMinutes: horizon,
              })
            }
            type="button"
          >
            <RefreshCw size={18} />
          </button>
        </nav>
      </header>

      <main>
        <section className="therapy-review-controls">
          <div className="therapy-review-day-picker">
            <button
              aria-label="Предыдущий день"
              onClick={() => setDate((current) => shiftDate(current, -1))}
              type="button"
            >
              <ChevronLeft size={19} />
            </button>
            <label>
              <span>{displayDate(date)}</span>
              <input
                max={today}
                onChange={(event) => setDate(event.target.value)}
                type="date"
                value={date}
              />
            </label>
            <button
              aria-label="Следующий день"
              disabled={date >= today}
              onClick={() => setDate((current) => shiftDate(current, 1))}
              type="button"
            >
              <ChevronRight size={19} />
            </button>
          </div>

          <label>
            <span>Цель</span>
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

          <label>
            <span>Исход</span>
            <select
              onChange={(event) => setHorizon(Number(event.target.value))}
              value={horizon}
            >
              {HORIZONS.map((option) => (
                <option key={option.minutes} value={option.minutes}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        </section>

        <section className="therapy-review-explainer">
          <strong>Ретроспективный разбор</strong>
          <p>
            «С поправкой по факту» использует уже известную последующую
            глюкозу. Это объяснение прошлого эпизода, не рекомендация для новой
            дозы.
          </p>
          {review.data ? (
            <small>
              {review.data.cached
                ? "Загружен сохранённый расчёт"
                : "Расчёт выполнен и сохранён"}
              {" · "}
              {new Date(review.data.computed_at).toLocaleString("ru-RU")}
            </small>
          ) : null}
        </section>

        {review.data ? (
          <DayContext date={date} states={review.data.body_states ?? []} />
        ) : null}

        {review.isLoading ||
        (review.isFetching && !review.data?.items.length) ? (
          <div className="therapy-review-state">
            Собираю эпизоды, расчёты и исходы…
          </div>
        ) : review.isError ? (
          <div className="therapy-review-state therapy-review-state--error">
            Не удалось собрать разбор. Попробуйте обновить.
          </div>
        ) : review.data?.items.length ? (
          <section
            aria-label="Эпизоды за день"
            className="therapy-review-list"
          >
            {isRefreshing ? (
              <div className="therapy-review-updating">Обновляю…</div>
            ) : null}
            {review.data.items.map((item) => (
              <ReviewCard item={item} key={item.key} target={target} />
            ))}
          </section>
        ) : (
          <div className="therapy-review-state">
            За этот день эпизодов не найдено.
          </div>
        )}

        <section className="therapy-review-method">
          <strong>Как считается поправка</strong>
          <span>
            Инсулин: факт + (глюкоза после − цель) ÷ ISF.
          </span>
          <span>
            Коррекция углеводами: факт + (цель − глюкоза после) × 4 г.
          </span>
        </section>
      </main>
    </div>
  );
}
