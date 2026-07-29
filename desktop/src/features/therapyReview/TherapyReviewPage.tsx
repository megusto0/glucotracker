import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
} from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import type { TherapyReviewDayResponse } from "../../api/client";
import {
  useGlucoseTherapyReview,
  useRecalculateGlucoseTherapyReview,
} from "../glucose/useGlucoseDashboard";
import "../nightscoutView/nightscout-page.css";
import "./therapy-review-page.css";

type ReviewItem = TherapyReviewDayResponse["items"][number];

const CLASS_LABELS: Record<ReviewItem["classification"], string> = {
  meal: "Приём пищи",
  snack: "Перекус",
  carb_correction: "Коррекция углеводами",
  insulin_correction: "Коррекция инсулином",
  mixed: "Смешанный эпизод",
  unresolved: "Требует разбора",
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
  const outcomeInRange =
    typeof after === "number" && after >= 3.9 && after <= 10;
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
          className={`therapy-review-outcome${outcomeInRange ? " therapy-review-outcome--range" : ""}`}
        >
          {typeof after === "number"
            ? outcomeInRange
              ? "в диапазоне"
              : after < 3.9
                ? "низко"
                : "высоко"
            : "нет исхода"}
        </span>
      </header>

      <h2>{item.title}</h2>
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
  const isRefreshing = review.isFetching || recalculation.isPending;

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
        <div>
          <span>Nightscout</span>
          <strong>Разбор терапии по дням</strong>
        </div>
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
                : date < today
                  ? "Расчёт выполнен и сохранён"
                  : "Текущий день пересчитывается"}
              {" · "}
              {new Date(review.data.computed_at).toLocaleString("ru-RU")}
            </small>
          ) : null}
        </section>

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
