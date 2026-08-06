import { Bell, ClipboardList, Menu, RefreshCw, Volume2, X } from "lucide-react";
import {
  useCallback,
  useMemo,
  useRef,
  useState,
  useEffect,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";
import { useNavigate } from "react-router-dom";
import type {
  BodyStatesResponse,
  DayEpisodesResponse,
  GlucoseDashboardResponse,
  GlucoseMode,
  GlucosePredictionResponse,
  HeartRateSeriesResponse,
} from "../../api/client";
import {
  useCreateNightscoutInsulin,
  useGlucoseBodyStates,
  useGlucoseDashboard,
  useGlucoseEpisodes,
  useGlucosePrediction,
  useHeartRateSeries,
  useInsulinRecommendation,
  useTopUpDose,
} from "../glucose/useGlucoseDashboard";
import "./nightscout-page.css";

type DisplayMode = Extract<GlucoseMode, "raw" | "normalized">;
type BodyState = BodyStatesResponse["states"][number];
type DashboardPoint = GlucoseDashboardResponse["points"][number];
type FoodEvent = GlucoseDashboardResponse["food_events"][number];
type SelectableFoodEvent = Omit<FoodEvent, "meal_id"> & {
  meal_id?: string;
};
type ForecastPoint = GlucosePredictionResponse["points"][number];
type DayEpisode = DayEpisodesResponse["episodes"][number];
type HoverPoint =
  | {
      kind: "history";
      point: DashboardPoint;
      value: number;
      x: number;
      y: number;
    }
  | {
      kind: "forecast";
      point: ForecastPoint;
      value: number;
      x: number;
      y: number;
    };
type ChartRange = {
  fromMs: number;
  toMs: number;
};
type OverviewDragMode = "start" | "move" | "end";
type OverviewDrag = {
  initialRange: ChartRange;
  mode: OverviewDragMode;
  pointerId: number;
  startClientX: number;
};
const HOUR_OPTIONS = [2, 3, 4, 6, 12, 24] as const;
const MAIN_Y_TICKS = [2, 3, 4, 6, 10, 14, 22] as const;
const REFRESH_INTERVAL_MS = 60 * 1000;
const MIN_CHART_WINDOW_MS = 30 * 60 * 1000;
const FOLLOW_LATEST_SNAP_MS = 15 * 60 * 1000;

const pad = (value: number) => value.toString().padStart(2, "0");

function toApiDateTime(date: Date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(
    date.getDate(),
  )}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(
    date.getSeconds(),
  )}`;
}

function formatClock(date: Date) {
  return `${date.getHours()}:${pad(date.getMinutes())}`;
}

function formatMmol(value?: number | null) {
  return typeof value === "number" && Number.isFinite(value)
    ? value.toFixed(1)
    : "—";
}

function formatOnBoard(value: number | undefined, digits: number) {
  return typeof value === "number" && Number.isFinite(value)
    ? value.toFixed(digits)
    : "0";
}

function displayValue(point: DashboardPoint, mode: DisplayMode) {
  return mode === "normalized"
    ? (point.normalized_value ?? point.raw_value)
    : point.raw_value;
}

function trendSymbol(delta: number | null) {
  if (delta === null) return "→";
  if (delta >= 0.9) return "↑↑";
  if (delta >= 0.3) return "↑";
  if (delta >= 0.1) return "↗";
  if (delta <= -0.9) return "↓↓";
  if (delta <= -0.3) return "↓";
  if (delta <= -0.1) return "↘";
  return "→";
}

function pointAgeMinutes(point?: DashboardPoint) {
  if (!point) return null;
  const timestamp = Date.parse(point.timestamp);
  if (!Number.isFinite(timestamp)) return null;
  return Math.max(0, Math.round((Date.now() - timestamp) / 60_000));
}

/** Drop near-duplicate insulin rows (same second + units from re-import). */
function dedupeInsulinEvents(
  events: GlucoseDashboardResponse["insulin_events"],
): GlucoseDashboardResponse["insulin_events"] {
  const seen = new Set<string>();
  const unique: GlucoseDashboardResponse["insulin_events"] = [];
  for (const event of events) {
    const second = Math.floor(Date.parse(event.timestamp) / 1000);
    const units =
      typeof event.insulin_units === "number"
        ? event.insulin_units.toFixed(3)
        : "null";
    const key = `${Number.isFinite(second) ? second : event.timestamp}:${units}:${event.event_type ?? ""}`;
    if (seen.has(key)) continue;
    seen.add(key);
    unique.push(event);
  }
  return unique;
}

/** Small horizontal fan for same-kind events anchored to one CGM sample. */
function markerOffsets(anchorKeys: string[], spacing: number): number[] {
  const groups = new Map<string, number[]>();
  anchorKeys.forEach((key, index) => {
    const list = groups.get(key) ?? [];
    list.push(index);
    groups.set(key, list);
  });
  const offsets = anchorKeys.map(() => 0);
  groups.forEach((indexes) => {
    if (indexes.length < 2) return;
    indexes.forEach((index, order) => {
      offsets[index] = (order - (indexes.length - 1) / 2) * spacing;
    });
  });
  return offsets;
}

function resizeOverviewRange(
  drag: OverviewDrag,
  deltaMs: number,
  overviewFrom: number,
  overviewTo: number,
): ChartRange {
  const { fromMs, toMs } = drag.initialRange;
  if (drag.mode === "start") {
    return {
      fromMs: Math.max(
        overviewFrom,
        Math.min(fromMs + deltaMs, toMs - MIN_CHART_WINDOW_MS),
      ),
      toMs,
    };
  }
  if (drag.mode === "end") {
    return {
      fromMs,
      toMs: Math.min(
        overviewTo,
        Math.max(toMs + deltaMs, fromMs + MIN_CHART_WINDOW_MS),
      ),
    };
  }

  const width = toMs - fromMs;
  const shiftedFrom = fromMs + deltaMs;
  const boundedFrom = Math.max(
    overviewFrom,
    Math.min(shiftedFrom, overviewTo - width),
  );
  return {
    fromMs: boundedFrom,
    toMs: boundedFrom + width,
  };
}

export function NightscoutPage() {
  const navigate = useNavigate();
  const [hours, setHours] = useState<(typeof HOUR_OPTIONS)[number]>(3);
  const [mode, setMode] = useState<DisplayMode>("normalized");
  const [menuOpen, setMenuOpen] = useState(false);
  const [selectedFood, setSelectedFood] = useState<SelectableFoodEvent | null>(
    null,
  );
  const [customRange, setCustomRange] = useState<ChartRange | null>(null);
  const [followWindowMs, setFollowWindowMs] = useState<number | null>(null);
  const [refreshAnchor, setRefreshAnchor] = useState(() => new Date());

  useEffect(() => {
    const interval = window.setInterval(
      () => setRefreshAnchor(new Date()),
      REFRESH_INTERVAL_MS,
    );
    return () => window.clearInterval(interval);
  }, []);

  const range = useMemo(() => {
    if (customRange) {
      return {
        from: toApiDateTime(new Date(customRange.fromMs)),
        to: toApiDateTime(new Date(customRange.toMs)),
      };
    }
    const to = refreshAnchor;
    const windowMs = followWindowMs ?? hours * 60 * 60 * 1000;
    return {
      from: toApiDateTime(new Date(to.getTime() - windowMs)),
      to: toApiDateTime(to),
    };
  }, [customRange, followWindowMs, hours, refreshAnchor]);
  const overviewRange = useMemo(() => {
    const to = refreshAnchor;
    return {
      from: toApiDateTime(new Date(to.getTime() - 24 * 60 * 60 * 1000)),
      to: toApiDateTime(to),
    };
  }, [refreshAnchor]);

  const dashboard = useGlucoseDashboard(range.from, range.to, mode);
  const overview = useGlucoseDashboard(
    overviewRange.from,
    overviewRange.to,
    mode,
  );
  const heartRate = useHeartRateSeries(
    overviewRange.from,
    overviewRange.to,
    10,
  );
  const bodyStates = useGlucoseBodyStates(
    overviewRange.from,
    overviewRange.to,
  );
  const prediction = useGlucosePrediction(mode);
  const episodes = useGlucoseEpisodes(range.from, range.to);
  const points = dashboard.data?.points ?? [];
  const latest = points[points.length - 1];
  const previous = points[points.length - 2];
  const latestValue = latest ? displayValue(latest, mode) : null;
  const previousValue = previous ? displayValue(previous, mode) : null;
  const delta =
    latestValue !== null && previousValue !== null
      ? latestValue - previousValue
      : null;
  const ageMinutes = pointAgeMinutes(latest);
  const missingPercent = dashboard.data?.quality.missing_data_pct;
  const summary = dashboard.data?.summary;
  const isUrgent = latestValue !== null && latestValue < 3.0;
  // The answer depends on IOB and COB at this instant, so it is only fetched
  // when asked for, and it is cleared as soon as new CGM arrives.
  const [topUpRequested, setTopUpRequested] = useState(false);
  const topUp = useTopUpDose(undefined, topUpRequested);
  const topUpData = topUpRequested ? topUp.data : undefined;
  useEffect(() => {
    setTopUpRequested(false);
  }, [latest?.timestamp]);
  const selectedEpisode = useMemo(
    () =>
      episodes.data?.episodes.find((episode) =>
        selectedFood ? episodeContainsFood(episode, selectedFood) : false,
      ) ?? null,
    [episodes.data, selectedFood],
  );
  const selectedFoodEvents = useMemo(
    () =>
      selectedEpisode
        ? (dashboard.data?.food_events ?? []).filter((event) =>
            episodeContainsFood(selectedEpisode, event),
          )
        : [],
    [dashboard.data, selectedEpisode],
  );

  const refresh = () => {
    setRefreshAnchor(new Date());
    void prediction.refetch();
  };
  const selectChartRange = useCallback(
    (nextRange: ChartRange) => {
      const windowMs = Math.max(
        MIN_CHART_WINDOW_MS,
        nextRange.toMs - nextRange.fromMs,
      );
      const latestGapMs = refreshAnchor.getTime() - nextRange.toMs;
      if (Math.abs(latestGapMs) <= FOLLOW_LATEST_SNAP_MS) {
        setCustomRange(null);
        setFollowWindowMs(windowMs);
        return;
      }
      setFollowWindowMs(null);
      setCustomRange(nextRange);
    },
    [refreshAnchor],
  );

  return (
    <div className={`ns-page${isUrgent ? " ns-page--urgent" : ""}`}>
      <header className="ns-toolbar">
        <button
          className="ns-brand"
          onClick={() => navigate("/glucose")}
          title="Вернуться в Glucotracker"
          type="button"
        >
          <span aria-hidden="true" className="ns-brand-mark">
            <span />
          </span>
          <span>Nightscout</span>
        </button>
        <nav aria-label="Действия Nightscout" className="ns-toolbar-actions">
          <button
            aria-label="Уведомления"
            className="ns-icon-button"
            type="button"
          >
            <Bell size={19} />
          </button>
          <button aria-label="Звук" className="ns-icon-button" type="button">
            <Volume2 size={19} />
          </button>
          <button
            aria-label="Меню"
            aria-expanded={menuOpen}
            className="ns-icon-button"
            onClick={() => setMenuOpen((current) => !current)}
            type="button"
          >
            <Menu size={21} />
          </button>
        </nav>
        {menuOpen ? (
          <div className="ns-menu">
            <button onClick={refresh} type="button">
              <RefreshCw size={15} /> Обновить
            </button>
            <button
              onClick={() => {
                setMenuOpen(false);
                navigate("/nightscout/review");
              }}
              type="button"
            >
              <ClipboardList size={15} /> Разбор по дням
            </button>
            <button onClick={() => navigate("/glucose")} type="button">
              Открыть Glucotracker
            </button>
          </div>
        ) : null}
      </header>

      <section aria-label="Текущее состояние" className="ns-status">
        <div className="ns-clock-block">
          <time className="ns-clock">{formatClock(refreshAnchor)}</time>
          <div className="ns-pills">
            <span>
              <b>{ageMinutes ?? "—"}</b> mins ago
            </span>
            {typeof missingPercent === "number" ? (
              <span>
                <b>{Math.round(missingPercent)}%</b> ◉
              </span>
            ) : null}
          </div>
          <div className="ns-hours" role="group" aria-label="Период графика">
            <span>Hours:</span>
            {HOUR_OPTIONS.map((option) => (
              <button
                aria-pressed={
                  customRange === null &&
                  followWindowMs === null &&
                  hours === option
                }
                className={
                  customRange === null &&
                  followWindowMs === null &&
                  hours === option
                    ? "active"
                    : ""
                }
                key={option}
                onClick={() => {
                  setHours(option);
                  setCustomRange(null);
                  setFollowWindowMs(null);
                }}
                type="button"
              >
                {option}
              </button>
            ))}
            <span>…</span>
          </div>
        </div>

        <div className="ns-reading-block">
          <div className="ns-current-reading">
            <strong>{formatMmol(latestValue)}</strong>
            <span
              aria-label={`Тренд ${trendSymbol(delta)}`}
              className="ns-trend"
            >
              {trendSymbol(delta)}
            </span>
          </div>
          <div className="ns-delta-pill">
            <b>
              {delta === null
                ? "—"
                : `${delta >= 0 ? "+" : ""}${formatMmol(delta)}`}
            </b>
            <span>mmol/L</span>
          </div>
        </div>

        <div aria-label="Активный инсулин и углеводы" className="ns-on-board">
          <div className="ns-board-metric">
            <span>IOB</span>
            <strong>{formatOnBoard(summary?.iob_units, 2)}</strong>
            <b>Ед</b>
            <small>
              {summary?.iob_minutes_remaining ?? 0} мин до завершения
            </small>
          </div>
          <div className="ns-board-metric">
            <span>COB</span>
            <strong>{formatOnBoard(summary?.cob_g, 1)}</strong>
            <b>г</b>
            <small>{summary?.cob_minutes_remaining ?? 0} мин до усвоения</small>
          </div>
        </div>

        <div className="ns-top-up">
          <button
            className="ns-top-up-button"
            disabled={topUp.isFetching}
            onClick={() => setTopUpRequested(true)}
            type="button"
          >
            {topUp.isFetching ? "Считаю…" : "Сколько добавить?"}
          </button>
          {topUpRequested && topUp.isError ? (
            <p className="ns-top-up-error">Расчёт сейчас недоступен.</p>
          ) : null}
          {topUpData ? (
            <div className="ns-top-up-result" role="status">
              {topUpData.status === "ready" ? (
                <>
                  <strong className="ns-top-up-units">
                    {formatDose(topUpData.units)} Ед
                  </strong>
                  <small>
                    углеводы {formatDose(topUpData.carb_units)} + коррекция{" "}
                    {formatDose(topUpData.correction_units)} − активный инсулин{" "}
                    {formatDose(topUpData.iob_units)}
                  </small>
                </>
              ) : topUpData.status === "not_needed" ? (
                <>
                  <strong className="ns-top-up-units">0 Ед</strong>
                  <small>{topUpData.note}</small>
                </>
              ) : topUpData.status === "low_or_falling" ? (
                <strong className="ns-top-up-hold">{topUpData.note}</strong>
              ) : topUpData.status === "icr_unavailable" ? (
                <small>Не задан ICR — добавку посчитать нельзя.</small>
              ) : (
                <small>Нет свежих данных CGM.</small>
              )}
              {topUpData.status === "ready" ||
              topUpData.status === "not_needed" ? (
                <small className="ns-top-up-context">
                  {formatMmol(topUpData.glucose_mmol_l)}
                  {topUpData.projection_source === "forecast"
                    ? ` → ${formatMmol(topUpData.projected_glucose_mmol_l)} (прогноз)`
                    : ""}{" "}
                  · цель {formatMmol(topUpData.target_mmol_l)} · осталось{" "}
                  {formatOnBoard(topUpData.cob_g ?? undefined, 0)} г · ICR{" "}
                  {formatOnBoard(topUpData.icr_g_per_unit ?? undefined, 1)} · ISF{" "}
                  {formatDose(topUpData.isf_mmol_l_per_unit)}
                  {topUpData.isf_source === "default" ? " (по умолчанию)" : ""}
                </small>
              ) : null}
            </div>
          ) : null}
        </div>

        <div className="ns-mode-switch" role="group" aria-label="Режим глюкозы">
          <button
            aria-pressed={mode === "raw"}
            className={mode === "raw" ? "active" : ""}
            onClick={() => setMode("raw")}
            type="button"
          >
            Стандартный
          </button>
          <button
            aria-pressed={mode === "normalized"}
            className={mode === "normalized" ? "active" : ""}
            onClick={() => setMode("normalized")}
            type="button"
          >
            Нормализованный
          </button>
        </div>
      </section>

      <NightscoutChart
        data={dashboard.data}
        error={Boolean(dashboard.error)}
        episodes={episodes.data?.episodes}
        loading={dashboard.isLoading}
        mode={mode}
        overview={overview.data}
        heartRate={heartRate.data}
        bodyStates={bodyStates.data}
        prediction={prediction.data}
        predictionError={Boolean(prediction.error)}
        onFoodSelect={setSelectedFood}
        onRangeChange={selectChartRange}
      />
      {selectedFood && !selectedEpisode ? (
        <div
          aria-label="Инсулин для приёма"
          aria-modal="false"
          className="ns-insulin-panel"
          role="dialog"
        >
          <button
            aria-label="Закрыть"
            className="ns-insulin-panel-close"
            onClick={() => setSelectedFood(null)}
            type="button"
          >
            <X size={18} />
          </button>
          <span className="ns-insulin-kicker">ПРИЁМ ПИЩИ</span>
          <p>
            {episodes.isLoading
              ? "Определяю общий приём…"
              : "Не удалось определить приём."}
          </p>
        </div>
      ) : null}
      {selectedEpisode ? (
        <EpisodePanel
          episode={selectedEpisode}
          foodEvents={selectedFoodEvents}
          key={selectedEpisode.key}
          onClose={() => setSelectedFood(null)}
        />
      ) : null}
    </div>
  );
}

function episodeContainsFood(episode: DayEpisode, food: SelectableFoodEvent) {
  if (food.meal_id && episode.meal_ids.includes(food.meal_id)) return true;
  const foodTime = Date.parse(food.timestamp);
  const startTime = Date.parse(episode.start_at);
  const endTime = Date.parse(episode.end_at);
  return (
    Number.isFinite(foodTime) &&
    Number.isFinite(startTime) &&
    Number.isFinite(endTime) &&
    foodTime >= startTime &&
    foodTime <= endTime
  );
}

function formatDose(value?: number | null) {
  return typeof value === "number" && Number.isFinite(value)
    ? value.toFixed(1)
    : "—";
}

function formatCarbs(value?: number | null) {
  return typeof value === "number" && Number.isFinite(value)
    ? `${value.toFixed(0)} г`
    : "—";
}

/**
 * The rescue reading is an opinion, so it must not be the only thing on offer.
 *
 * A carbohydrate rescue used to replace the dose panel outright, which meant a
 * plate the classifier read wrong could not be asked about at all — the one
 * screen that answers "how much insulin" simply disappeared. The rescue view
 * still leads, because when it is right it is the more useful answer, but the
 * calculation is always one click away.
 */
function EpisodePanel({
  episode,
  foodEvents,
  onClose,
}: {
  episode: DayEpisode;
  foodEvents: FoodEvent[];
  onClose: () => void;
}) {
  const [showDose, setShowDose] = useState(false);
  if (episode.therapy?.classification === "carb_correction" && !showDose) {
    return (
      <CarbCorrectionPanel
        episode={episode}
        foodEvents={foodEvents}
        onClose={onClose}
        onShowDose={() => setShowDose(true)}
      />
    );
  }
  return (
    <InsulinEpisodePanel
      episode={episode}
      foodEvents={foodEvents}
      onClose={onClose}
    />
  );
}

function CarbCorrectionPanel({
  episode,
  foodEvents,
  onClose,
  onShowDose,
}: {
  episode: DayEpisode;
  foodEvents: FoodEvent[];
  onClose: () => void;
  onShowDose: () => void;
}) {
  const therapy = episode.therapy;
  return (
    <div
      aria-label="Коррекция углеводами"
      aria-modal="false"
      className="ns-insulin-panel ns-carb-correction-panel"
      role="dialog"
    >
      <button
        aria-label="Закрыть"
        className="ns-insulin-panel-close"
        onClick={onClose}
        type="button"
      >
        <X size={18} />
      </button>
      <span className="ns-insulin-kicker">КОРРЕКЦИЯ УГЛЕВОДАМИ</span>
      <h2>Восстановление после низкой глюкозы</h2>
      <p className="ns-insulin-meal-summary">
        {foodEvents.map((event) => event.title).join(" · ")}
        <span>Фактически: {formatCarbs(episode.total_carbs_g)}</span>
      </p>

      <section className="ns-insulin-result">
        <span className="ns-insulin-kicker">ОРИЕНТИР</span>
        <div className="ns-carb-suggestion">
          <strong>{formatCarbs(therapy.suggested_carbs_g)}</strong>
          <span>быстрых углеводов</span>
        </div>
        <small>Проверить глюкозу снова через 15 минут.</small>
        <div className="ns-carb-context">
          <span>
            До: raw {formatDose(therapy.glucose_at_start_raw)} · норм.{" "}
            {formatDose(therapy.glucose_at_start_normalized)}
          </span>
          <span>
            Пик после: raw {formatDose(therapy.peak_post_event_raw)} · норм.{" "}
            {formatDose(therapy.peak_post_event_normalized)} ммоль/л
          </span>
        </div>
        {therapy.reasons?.length ? (
          <small>{therapy.reasons.join(" · ")}</small>
        ) : null}
      </section>

      <section className="ns-insulin-actual">
        <span className="ns-insulin-kicker">ФАКТИЧЕСКИ</span>
        <strong>{formatCarbs(episode.total_carbs_g)}</strong>
        {typeof therapy.suggested_carbs_g === "number" &&
        episode.total_carbs_g > therapy.suggested_carbs_g ? (
          <small>
            На {formatCarbs(episode.total_carbs_g - therapy.suggested_carbs_g)}{" "}
            больше базового ориентира.
          </small>
        ) : null}
      </section>

      <button
        className="ns-carb-show-dose"
        onClick={onShowDose}
        type="button"
      >
        Это обычный приём — показать расчёт дозы
      </button>
    </div>
  );
}

function correctionStatusText(
  status:
    | NonNullable<
        ReturnType<typeof useInsulinRecommendation>["data"]
      >["correction_status"]
    | undefined,
) {
  if (status === "target_required") return "Укажите личную цель.";
  if (status === "isf_unavailable")
    return "Нет надёжного персонального ISF: задайте его вручную в цифровом двойнике.";
  if (status === "glucose_unavailable")
    return "Нет надёжной глюкозы перед приёмом.";
  if (status === "trend_unavailable")
    return "Недостаточно точек для оценки тренда.";
  if (status === "low_or_falling")
    return "Глюкоза низкая или быстро снижается — итог не рассчитан.";
  if (status === "not_needed")
    return "Коррекция не нужна с учётом тренда и IOB.";
  if (!status) return "Для коррекции нужен обновлённый backend.";
  return null;
}

const DAYPART_LABELS: Record<"morning" | "day" | "evening", string> = {
  morning: "утро",
  day: "день",
  evening: "вечер",
};

/**
 * The ratio behind the food half, and how it was weighed against history.
 *
 * The headline is a blend of two estimators. Without this line the only way to
 * tell which one produced it is to recompute it by hand.
 */
function IcrExplanation({
  data,
}: {
  data: NonNullable<ReturnType<typeof useInsulinRecommendation>["data"]>;
}) {
  const ratio = data.icr_g_per_unit;
  if (typeof ratio !== "number") return null;
  const daypart = data.icr_daypart ? DAYPART_LABELS[data.icr_daypart] : null;
  const weight = data.history_weight;
  return (
    <small>
      ICR {ratio.toFixed(1)} г/Ед{daypart ? ` · ${daypart}` : ""}
      {data.icr_after_sleep &&
      typeof data.icr_configured_g_per_unit === "number"
        ? ` · первый после сна, обычно ${data.icr_configured_g_per_unit.toFixed(1)}`
        : ""}
      {typeof data.icr_dose_units === "number"
        ? ` · по ICR ${formatDose(data.icr_dose_units)} Ед`
        : ""}
      {typeof data.history_median_units === "number"
        ? ` · по истории ${formatDose(data.history_median_units)} Ед`
        : ""}
      {typeof weight === "number" && typeof data.icr_dose_units === "number"
        ? ` · смешано ${Math.round(weight * 100)}/${Math.round((1 - weight) * 100)}`
        : ""}
      {typeof data.implied_icr_g_per_unit === "number"
        ? ` · по факту ${data.implied_icr_g_per_unit.toFixed(1)} г/Ед`
        : ""}
    </small>
  );
}

function InsulinEpisodePanel({
  episode,
  foodEvents,
  onClose,
}: {
  episode: DayEpisode;
  foodEvents: FoodEvent[];
  onClose: () => void;
}) {
  const isSnack = episode.therapy?.classification === "snack";
  const [targetText, setTargetText] = useState("6,0");
  const [actualText, setActualText] = useState("");
  const [savedActual, setSavedActual] = useState<number | null>(null);
  const parsedTarget = Number(targetText.replace(",", "."));
  const targetIsValid =
    Number.isFinite(parsedTarget) && parsedTarget >= 3.9 && parsedTarget <= 10;
  const correctionTarget = targetIsValid ? parsedTarget : undefined;
  const recommendation = useInsulinRecommendation(
    targetIsValid ? episode.meal_ids : [],
    correctionTarget,
  );
  const createInsulin = useCreateNightscoutInsulin();
  const parsedActual = Number(actualText.replace(",", "."));
  const actualUnits =
    episode.total_insulin_units > 0 ? episode.total_insulin_units : savedActual;
  const canSubmit =
    Number.isFinite(parsedActual) && parsedActual > 0 && parsedActual <= 100;
  const carbs = foodEvents.map((event) => event.carbs_g);
  const recommendationData = recommendation.data;
  const outcomeGlucose =
    episode.therapy?.glucose_plus_2h_normalized ??
    episode.therapy?.glucose_plus_2h_raw;
  const retrospectiveCorrectionTooHigh =
    typeof actualUnits === "number" &&
    typeof recommendationData?.total_recommended_units === "number" &&
    recommendationData.total_recommended_units > actualUnits &&
    typeof outcomeGlucose === "number" &&
    outcomeGlucose < parsedTarget;
  const inRangeMatchCount =
    recommendationData?.matches.filter(
      (match) =>
        typeof match.glucose_plus_2h_mmol === "number" &&
        match.glucose_plus_2h_mmol >= 3.9 &&
        match.glucose_plus_2h_mmol <= 10,
    ).length ?? 0;
  const deferredMatchCount =
    recommendationData?.matches.filter(
      (match) => (match.deferred_insulin_units ?? 0) > 0,
    ).length ?? 0;
  const correctionMessage = correctionStatusText(
    recommendationData?.correction_status,
  );

  const submitActual = async () => {
    if (!canSubmit) return;
    const idempotencyKey =
      typeof crypto.randomUUID === "function"
        ? crypto.randomUUID()
        : `nightscout-${Date.now()}`;
    const created = await createInsulin.mutateAsync({
      insulin_units: parsedActual,
      recorded_at: episode.start_at,
      idempotency_key: idempotencyKey,
    });
    setSavedActual(created.insulin_units ?? parsedActual);
  };

  return (
    <div
      aria-label="Инсулин для приёма"
      aria-modal="false"
      className="ns-insulin-panel"
      role="dialog"
    >
      <button
        aria-label="Закрыть"
        className="ns-insulin-panel-close"
        onClick={onClose}
        type="button"
      >
        <X size={18} />
      </button>
      <span className="ns-insulin-kicker">
        {isSnack ? "ПЕРЕКУС" : "ПРИЁМ ПИЩИ"}
      </span>
      <h2>{isSnack ? "Инсулин для перекуса" : "Инсулин для приёма"}</h2>
      <p className="ns-insulin-meal-summary">
        {carbs.length
          ? carbs.map((value) => `${value.toFixed(0)} г`).join(" + ")
          : `${episode.total_carbs_g.toFixed(0)} г`}
        <span>{foodEvents.map((event) => event.title).join(" · ")}</span>
      </p>

      <section className="ns-insulin-result">
        <span className="ns-insulin-kicker">РАСЧЁТ</span>
        <label className="ns-insulin-target" htmlFor="ns-correction-target">
          <span>Личная цель глюкозы</span>
          <span>
            <input
              autoComplete="off"
              id="ns-correction-target"
              inputMode="decimal"
              onChange={(event) =>
                setTargetText(
                  event.target.value
                    .replace(/[^\d.,]/g, "")
                    .replace(".", ",")
                    .slice(0, 4),
                )
              }
              placeholder="—"
              value={targetText}
            />
            ммоль/л
          </span>
        </label>
        {!targetIsValid ? (
          <p className="ns-insulin-error">Цель должна быть от 3,9 до 10,0.</p>
        ) : recommendation.isLoading ? (
          <p>Сравниваю с прошлыми приёмами…</p>
        ) : recommendation.isError ? (
          <p className="ns-insulin-error">Расчёт сейчас недоступен.</p>
        ) : recommendationData?.status === "low_or_falling" ? (
          <div className="ns-insulin-safety-stop">
            <strong>Инсулин не рекомендуется</strong>
            <small>
              Глюкоза низкая или быстро снижается. Расчёт еды, коррекции и
              итога скрыт.
            </small>
            <small>
              Глюкоза{" "}
              {formatDose(recommendationData.correction_glucose_mmol_l)} →{" "}
              {formatDose(
                recommendationData.correction_projected_glucose_mmol_l,
              )}{" "}
              ммоль/л · IOB{" "}
              {formatDose(recommendationData.correction_iob_units)} Ед
            </small>
          </div>
        ) : recommendationData?.status === "ready" ? (
          <>
            <div className="ns-insulin-equation">
              <div>
                <span>Еда</span>
                <strong>
                  {formatDose(recommendationData.recommended_units)} Ед
                </strong>
              </div>
              <b aria-hidden="true">+</b>
              <div>
                <span>Коррекция</span>
                <strong>
                  {formatDose(recommendationData.correction_units)} Ед
                </strong>
              </div>
              {/* Insulin still working is subtracted from the total, but only
                  once the correction itself has floored at zero. Omitting it
                  published arithmetic that does not hold — a 4,9 Ед meal with
                  no correction adding up to 0. */}
              {typeof recommendationData.correction_excess_iob_units ===
                "number" &&
              recommendationData.correction_excess_iob_units > 0 &&
              (recommendationData.correction_units ?? 0) <= 0 ? (
                <>
                  <b aria-hidden="true">−</b>
                  <div>
                    <span>Активный инсулин</span>
                    <strong>
                      {formatDose(
                        recommendationData.correction_excess_iob_units,
                      )}{" "}
                      Ед
                    </strong>
                  </div>
                </>
              ) : null}
              <b aria-hidden="true">=</b>
              <div className="ns-insulin-total">
                <span>Итого</span>
                <strong>
                  {formatDose(recommendationData.total_recommended_units)} Ед
                </strong>
              </div>
            </div>
            {correctionMessage ? (
              <small>{correctionMessage}</small>
            ) : (
              <small>
                Глюкоза{" "}
                {formatDose(recommendationData.correction_glucose_mmol_l)} →{" "}
                {formatDose(
                  recommendationData.correction_projected_glucose_mmol_l,
                )}{" "}
                ммоль/л · IOB{" "}
                {formatDose(recommendationData.correction_iob_units)} Ед · ISF{" "}
                {formatDose(recommendationData.correction_isf_mmol_l_per_unit)}
                {recommendationData.correction_isf_source === "default"
                  ? " (по умолчанию)"
                  : ""}
              </small>
            )}
            <small>
              Еда: {formatDose(recommendationData.range_low_units)}–
              {formatDose(recommendationData.range_high_units)} Ед · похожих
              приёмов: {recommendationData.matched_episode_count}
            </small>
            <IcrExplanation data={recommendationData} />
            {inRangeMatchCount || deferredMatchCount ? (
              <small>
                +2 ч в диапазоне: {inRangeMatchCount}
                {deferredMatchCount
                  ? ` · с отложенным покрытием: ${deferredMatchCount}`
                  : ""}
              </small>
            ) : null}
            {retrospectiveCorrectionTooHigh ? (
              <small className="ns-insulin-retrospective-warning">
                По факту {formatDose(actualUnits)} Ед уже привели к{" "}
                {formatDose(outcomeGlucose)} ммоль/л через 2 ч. Расчёт{" "}
                {formatDose(recommendationData.total_recommended_units)} Ед был
                бы избыточным для этого эпизода.
              </small>
            ) : null}
          </>
        ) : recommendationData?.status === "meal_without_carbs" ? (
          <p>В приёме нет углеводов для расчёта.</p>
        ) : (
          <p>
            Недостаточно истории: найдено{" "}
            {recommendationData?.matched_episode_count ?? 0} из 3 приёмов.
          </p>
        )}
      </section>

      <section className="ns-insulin-actual">
        <span className="ns-insulin-kicker">ФАКТИЧЕСКИ</span>
        {typeof actualUnits === "number" ? (
          <strong>{formatDose(actualUnits)} Ед</strong>
        ) : (
          <>
            <label htmlFor="ns-actual-insulin">Введено инсулина</label>
            <div>
              <input
                autoComplete="off"
                id="ns-actual-insulin"
                inputMode="decimal"
                onChange={(event) =>
                  setActualText(
                    event.target.value
                      .replace(/[^\d.,]/g, "")
                      .replace(".", ",")
                      .slice(0, 6),
                  )
                }
                placeholder="0,0"
                value={actualText}
              />
              <span>Ед</span>
            </div>
            <button
              disabled={!canSubmit || createInsulin.isPending}
              onClick={() => void submitActual()}
              type="button"
            >
              {createInsulin.isPending ? "Записываю…" : "Записать"}
            </button>
            {createInsulin.isError ? (
              <p className="ns-insulin-error">
                Не удалось записать фактический инсулин.
              </p>
            ) : null}
          </>
        )}
      </section>
    </div>
  );
}

function bodyStateTitle(state: BodyState) {
  const kind = state.kind === "sleep" ? "Сон" : (state.label ?? "Нагрузка");
  const source = state.source === "recorded" ? "с часов" : "по пульсу";
  const clock = new Intl.DateTimeFormat("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
  });
  const span = `${clock.format(new Date(state.start_at))}–${clock.format(new Date(state.end_at))}`;
  const peak =
    state.kind === "activity" && typeof state.peak_bpm === "number"
      ? ` · пик ${state.peak_bpm.toFixed(0)} уд/мин`
      : "";
  return `${kind} · ${span} · ${state.total_minutes} мин · ${source}${peak}`;
}

function NightscoutChart({
  data,
  error,
  episodes,
  loading,
  mode,
  overview,
  heartRate,
  bodyStates,
  prediction,
  predictionError,
  onFoodSelect,
  onRangeChange,
}: {
  data?: GlucoseDashboardResponse;
  error: boolean;
  episodes?: DayEpisode[];
  loading: boolean;
  mode: DisplayMode;
  overview?: GlucoseDashboardResponse;
  heartRate?: HeartRateSeriesResponse;
  bodyStates?: BodyStatesResponse;
  prediction?: GlucosePredictionResponse;
  predictionError: boolean;
  onFoodSelect: (food: SelectableFoodEvent) => void;
  onRangeChange: (range: ChartRange) => void;
}) {
  const shellRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const overviewDragRef = useRef<OverviewDrag | null>(null);
  const draftRangeRef = useRef<ChartRange | null>(null);
  const [hover, setHover] = useState<HoverPoint | null>(null);
  const [draftRange, setDraftRange] = useState<ChartRange | null>(null);
  const [overviewDragMode, setOverviewDragMode] =
    useState<OverviewDragMode | null>(null);
  // Size SVG in real pixels so preserveAspectRatio doesn't squash dots into ovals.
  const [size, setSize] = useState(() => ({
    width: Math.max(window.innerWidth, 320),
    height: Math.max(window.innerHeight - 200, 320),
  }));

  useEffect(() => {
    const el = shellRef.current;
    if (!el) return;
    const apply = (width: number, height: number) => {
      if (width < 40 || height < 40) return;
      setSize((prev) =>
        Math.abs(prev.width - width) < 1 && Math.abs(prev.height - height) < 1
          ? prev
          : { width, height },
      );
    };
    const measure = () => {
      const rect = el.getBoundingClientRect();
      apply(rect.width, rect.height);
    };
    measure();
    let settledFrame: number | null = null;
    const animationFrame = window.requestAnimationFrame(() => {
      settledFrame = window.requestAnimationFrame(measure);
    });
    const settledLayout = window.setTimeout(measure, 350);
    const observer =
      typeof ResizeObserver === "undefined"
        ? null
        : new ResizeObserver((entries) => {
            const entry = entries[0];
            if (!entry) return;
            apply(entry.contentRect.width, entry.contentRect.height);
          });
    observer?.observe(el);
    window.addEventListener("resize", measure);
    window.visualViewport?.addEventListener("resize", measure);
    return () => {
      window.cancelAnimationFrame(animationFrame);
      if (settledFrame !== null) window.cancelAnimationFrame(settledFrame);
      window.clearTimeout(settledLayout);
      observer?.disconnect();
      window.removeEventListener("resize", measure);
      window.visualViewport?.removeEventListener("resize", measure);
    };
  }, []);

  const { width, height } = size;
  const isPortrait = height > width * 1.2;
  const left = 8;
  const right = Math.max(48, Math.min(72, width * 0.055));
  const chartWidth = Math.max(1, width - right - left);
  const labelBand = Math.max(28, Math.min(40, height * 0.045));
  const overviewHeight = isPortrait
    ? Math.max(180, Math.min(320, height * 0.28))
    : Math.max(100, Math.min(170, height * 0.2));
  const overviewGap = 8;
  const mainHeight = Math.max(
    160,
    height - overviewHeight - labelBand * 2 - overviewGap,
  );
  const chartTop = 10;
  const chartBottom = mainHeight - 6;
  const plotHeight = Math.max(1, chartBottom - chartTop);
  const overviewTop = mainHeight + labelBand + overviewGap;
  const points = data?.points ?? [];
  const fromMs = data
    ? Date.parse(data.from_datetime)
    : Date.now() - 3 * 3_600_000;
  const historicalToMs = data ? Date.parse(data.to_datetime) : Date.now();
  const predictionAnchorMs = prediction?.anchor_timestamp
    ? Date.parse(prediction.anchor_timestamp)
    : Number.NaN;
  const predictionBelongsToWindow =
    Number.isFinite(predictionAnchorMs) &&
    predictionAnchorMs >= fromMs &&
    predictionAnchorMs <= historicalToMs + 15 * 60_000;
  const forecastPoints = predictionBelongsToWindow
    ? (prediction?.points ?? [])
    : [];
  const plottedValues = [
    ...points.map((point) => displayValue(point, mode)),
    ...forecastPoints.map((point) => point.display_value),
  ].filter(Number.isFinite);
  const plottedMax = plottedValues.length ? Math.max(...plottedValues) : 10;
  const yMin = 2;
  // Discrete domains avoid visual jitter while keeping ordinary changes legible.
  const yMax = plottedMax <= 9 ? 10 : plottedMax <= 15 ? 16 : 22;
  const ySpan = yMax - yMin;
  const yTicks = MAIN_Y_TICKS.filter((tick) => tick >= yMin && tick <= yMax);
  const pointRadius = Math.max(
    3.2,
    Math.min(5.2, Math.min(width, height) * 0.0048),
  );
  const overviewRadius = Math.max(2, pointRadius * 0.55);
  const treatmentRadius = Math.max(12, Math.min(16, pointRadius * 3.1));

  const foodEvents = data?.food_events ?? [];
  const insulinEvents = dedupeInsulinEvents(data?.insulin_events ?? []);
  const overviewPoints = overview?.points ?? [];
  const heartRatePoints = heartRate?.points ?? [];
  const bodyStatePoints = bodyStates?.states ?? [];
  const forecastToMs = forecastPoints.length
    ? Date.parse(forecastPoints[forecastPoints.length - 1]!.timestamp)
    : historicalToMs;
  const toMs = Math.max(historicalToMs, forecastToMs);
  const duration = Math.max(toMs - fromMs, 1);
  const overviewFrom = overview
    ? Date.parse(overview.from_datetime)
    : heartRate
      ? Date.parse(heartRate.from_datetime)
      : Date.now() - 24 * 3_600_000;
  const overviewTo = overview
    ? Date.parse(overview.to_datetime)
    : heartRate
      ? Date.parse(heartRate.to_datetime)
      : Date.now();
  const overviewDuration = Math.max(overviewTo - overviewFrom, 1);
  const scaleX = (timestamp: string) =>
    left + ((Date.parse(timestamp) - fromMs) / duration) * chartWidth;
  const scaleY = (value: number) => {
    const clamped = Math.min(yMax, Math.max(yMin, value));
    return chartBottom - ((clamped - yMin) / ySpan) * plotHeight;
  };
  const overviewX = (timestamp: string) =>
    left +
    ((Date.parse(timestamp) - overviewFrom) / overviewDuration) * chartWidth;
  const overviewY = (value: number) => {
    const clamped = Math.min(yMax, Math.max(yMin, value));
    return (
      overviewTop + overviewHeight - ((clamped - yMin) / ySpan) * overviewHeight
    );
  };
  const heartRateBinMs = (heartRate?.bin_minutes ?? 10) * 60_000;
  const heartRateBarWidth = Math.max(
    1.5,
    Math.min(
      12,
      (heartRateBinMs / overviewDuration) * chartWidth - 0.7,
    ),
  );
  const heartRateBarHeight = (bpm: number) => {
    const clamped = Math.min(180, Math.max(35, bpm));
    return Math.max(3, ((clamped - 35) / 145) * overviewHeight * 0.82);
  };
  const xTickCount = width < 600 ? 4 : width < 900 ? 5 : 7;
  const overviewTickCount = width < 600 ? 3 : 5;
  const xTicks = Array.from(
    { length: xTickCount },
    (_, index) => fromMs + (duration * index) / (xTickCount - 1),
  );
  const overviewTicks = Array.from(
    { length: overviewTickCount },
    (_, index) =>
      overviewFrom + (overviewDuration * index) / (overviewTickCount - 1),
  );
  const selectedRange = draftRange ?? {
    fromMs,
    toMs: historicalToMs,
  };
  const selectionX =
    left +
    ((selectedRange.fromMs - overviewFrom) / overviewDuration) * chartWidth;
  const selectionWidth = Math.max(
    ((selectedRange.toMs - selectedRange.fromMs) / overviewDuration) *
      chartWidth,
    2,
  );
  const selectionRightX = selectionX + selectionWidth;
  const overviewHandleHitWidth = 44;

  useEffect(() => {
    if (overviewDragRef.current) return;
    draftRangeRef.current = null;
    setDraftRange(null);
  }, [fromMs, historicalToMs]);
  const latestHistorical = points[points.length - 1];
  const forecastPath = [
    latestHistorical
      ? `${scaleX(latestHistorical.timestamp)},${scaleY(displayValue(latestHistorical, mode))}`
      : null,
    ...forecastPoints.map(
      (point) => `${scaleX(point.timestamp)},${scaleY(point.display_value)}`,
    ),
  ]
    .filter((value): value is string => value !== null)
    .join(" ");
  const forecastAnchorX = prediction?.anchor_timestamp
    ? scaleX(prediction.anchor_timestamp)
    : null;
  const nearestPoint = (timestamp: string) => {
    if (points.length === 0) return null;
    const eventTime = Date.parse(timestamp);
    return points.reduce((best, point) =>
      Math.abs(Date.parse(point.timestamp) - eventTime) <
      Math.abs(Date.parse(best.timestamp) - eventTime)
        ? point
        : best,
    );
  };
  const fanSpacing = treatmentRadius * 2 + 6;

  const foodMarkers = foodEvents.flatMap((event, index) => {
    const anchor = nearestPoint(event.timestamp);
    const episode = episodes?.find((candidate) =>
      episodeContainsFood(candidate, event),
    );
    const therapyClass = episode?.therapy?.classification ?? "meal";
    const suggestedCarbs =
      therapyClass === "carb_correction"
        ? episode?.therapy?.suggested_carbs_g
        : null;
    return anchor
      ? [
          {
            anchor,
            ariaLabel:
              therapyClass === "carb_correction" &&
              typeof suggestedCarbs === "number"
                ? `${event.title}: коррекция углеводами, ориентир ${suggestedCarbs.toFixed(0)} г, фактически ${event.carbs_g.toFixed(1)} г`
                : `${event.title}: ${event.carbs_g.toFixed(1)} г углеводов`,
            detail:
              therapyClass === "carb_correction" &&
              typeof suggestedCarbs === "number"
                ? `${event.title} · ориентир ${suggestedCarbs.toFixed(0)} г · фактически ${event.carbs_g.toFixed(1)} г`
                : `${event.title} · ${event.carbs_g.toFixed(1)} г углеводов`,
            key: `food-${event.timestamp}-${index}`,
            kind: "food" as const,
            food: event,
            symbol:
              therapyClass === "carb_correction"
                ? "↥"
                : therapyClass === "snack"
                  ? "S"
                  : "C",
            therapyClass,
            timestamp: event.timestamp,
            // The marker reports what was eaten. It used to show the rescue
            // suggestion instead, so a 24 g pastry classified as a carb
            // correction was drawn on the chart as "~15g" — the ADA default,
            // not anything the user did. The suggestion stays in the detail
            // text, which already gives both numbers.
            valueLabel: `${event.carbs_g.toFixed(0)}g`,
          },
        ]
      : [];
  });
  const foodFan = markerOffsets(
    foodMarkers.map((marker) => `food:${marker.anchor.timestamp}`),
    fanSpacing,
  );
  const insulinMarkers = insulinEvents.flatMap((event, index) => {
    const anchor = nearestPoint(event.timestamp);
    const eventTime = Date.parse(event.timestamp);
    const episode = episodes?.find((candidate) =>
      candidate.insulin.some(
        (insulin) =>
          Math.abs(Date.parse(insulin.timestamp) - eventTime) <= 1000 &&
          insulin.insulin_units === event.insulin_units,
      ),
    );
    const therapyClass =
      episode?.therapy?.classification ?? "insulin_correction";
    return anchor
      ? [
          {
            anchor,
            ariaLabel: `Инсулин: ${event.insulin_units?.toFixed(2) ?? "—"} единиц`,
            detail: `Инсулин · ${event.insulin_units?.toFixed(2) ?? "—"} Ед${
              event.notes ? ` · ${event.notes}` : ""
            }`,
            key: `insulin-${event.timestamp}-${index}`,
            kind: "insulin" as const,
            food: null,
            symbol: "I",
            therapyClass,
            timestamp: event.timestamp,
            valueLabel:
              typeof event.insulin_units === "number"
                ? `${event.insulin_units.toFixed(1)}U`
                : "—",
          },
        ]
      : [];
  });
  const insulinFan = markerOffsets(
    insulinMarkers.map((marker) => `insulin:${marker.anchor.timestamp}`),
    fanSpacing,
  );
  const treatmentMarkers = [
    ...foodMarkers.map((marker, index) => ({
      ...marker,
      xOffset: foodFan[index] ?? 0,
    })),
    ...insulinMarkers.map((marker, index) => ({
      ...marker,
      xOffset: insulinFan[index] ?? 0,
    })),
  ];

  const beginOverviewDrag = (
    event: ReactPointerEvent<SVGElement>,
    mode: OverviewDragMode,
  ) => {
    event.preventDefault();
    event.stopPropagation();
    const initialRange = {
      fromMs: selectedRange.fromMs,
      toMs: selectedRange.toMs,
    };
    overviewDragRef.current = {
      initialRange,
      mode,
      pointerId: event.pointerId,
      startClientX: event.clientX,
    };
    draftRangeRef.current = initialRange;
    setDraftRange(initialRange);
    setOverviewDragMode(mode);
    setHover(null);
    svgRef.current?.setPointerCapture?.(event.pointerId);
  };

  const updateOverviewDrag = (
    event: ReactPointerEvent<SVGSVGElement>,
    drag: OverviewDrag,
  ) => {
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    if (rect.width <= 0) return;
    const deltaSvgX = ((event.clientX - drag.startClientX) / rect.width) * width;
    const deltaMs = (deltaSvgX / chartWidth) * overviewDuration;
    const nextRange = resizeOverviewRange(
      drag,
      deltaMs,
      overviewFrom,
      overviewTo,
    );
    draftRangeRef.current = nextRange;
    setDraftRange(nextRange);
  };

  const finishOverviewDrag = (
    event: ReactPointerEvent<SVGSVGElement>,
    commit: boolean,
  ) => {
    const drag = overviewDragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    overviewDragRef.current = null;
    setOverviewDragMode(null);
    const svg = svgRef.current;
    if (svg?.hasPointerCapture?.(event.pointerId)) {
      svg.releasePointerCapture(event.pointerId);
    }
    const nextRange = draftRangeRef.current;
    if (commit && nextRange) {
      onRangeChange(nextRange);
    } else {
      draftRangeRef.current = null;
      setDraftRange(null);
    }
  };

  const moveOverviewWithKeyboard = (
    event: ReactKeyboardEvent<SVGElement>,
    mode: OverviewDragMode,
  ) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    event.stopPropagation();
    const stepMs = (event.shiftKey ? 30 : 5) * 60_000;
    const deltaMs = event.key === "ArrowLeft" ? -stepMs : stepMs;
    const nextRange = resizeOverviewRange(
      {
        initialRange: selectedRange,
        mode,
        pointerId: -1,
        startClientX: 0,
      },
      deltaMs,
      overviewFrom,
      overviewTo,
    );
    draftRangeRef.current = nextRange;
    setDraftRange(nextRange);
    onRangeChange(nextRange);
  };

  const handlePointerMove = (event: ReactPointerEvent<SVGSVGElement>) => {
    const drag = overviewDragRef.current;
    if (drag) {
      updateOverviewDrag(event, drag);
      return;
    }
    if (!svgRef.current || points.length + forecastPoints.length === 0) return;
    const rect = svgRef.current.getBoundingClientRect();
    const svgX = ((event.clientX - rect.left) / rect.width) * width;
    const svgY = ((event.clientY - rect.top) / rect.height) * height;
    if (svgY >= overviewTop) {
      setHover(null);
      return;
    }
    const timestamp = fromMs + ((svgX - left) / chartWidth) * duration;
    const historical = points.length
      ? points.reduce((best, point) =>
          Math.abs(Date.parse(point.timestamp) - timestamp) <
          Math.abs(Date.parse(best.timestamp) - timestamp)
            ? point
            : best,
        )
      : null;
    const forecast = forecastPoints.length
      ? forecastPoints.reduce((best, point) =>
          Math.abs(Date.parse(point.timestamp) - timestamp) <
          Math.abs(Date.parse(best.timestamp) - timestamp)
            ? point
            : best,
        )
      : null;
    const useForecast =
      forecast !== null &&
      (historical === null ||
        Math.abs(Date.parse(forecast.timestamp) - timestamp) <
          Math.abs(Date.parse(historical.timestamp) - timestamp));
    if (useForecast && forecast) {
      setHover({
        kind: "forecast",
        point: forecast,
        value: forecast.display_value,
        x: scaleX(forecast.timestamp),
        y: scaleY(forecast.display_value),
      });
      return;
    }
    if (historical) {
      const value = displayValue(historical, mode);
      setHover({
        kind: "history",
        point: historical,
        value,
        x: scaleX(historical.timestamp),
        y: scaleY(value),
      });
    }
  };

  if (loading && points.length === 0 && heartRatePoints.length === 0) {
    return <div className="ns-chart-message">Загружаю CGM…</div>;
  }
  if (error && points.length === 0 && heartRatePoints.length === 0) {
    return (
      <div className="ns-chart-message">Не удалось загрузить данные CGM.</div>
    );
  }

  return (
    <div className="ns-chart-shell" ref={shellRef}>
      <svg
        aria-label="График глюкозы Nightscout"
        className={`ns-chart${overviewDragMode ? ` ns-chart--dragging-${overviewDragMode}` : ""}`}
        height={height}
        onPointerCancel={(event) => finishOverviewDrag(event, false)}
        onPointerLeave={() => setHover(null)}
        onPointerMove={handlePointerMove}
        onPointerUp={(event) => finishOverviewDrag(event, true)}
        preserveAspectRatio="none"
        ref={svgRef}
        role="img"
        viewBox={`0 0 ${width} ${height}`}
        width={width}
      >
        <rect fill="#111" height={height} width={width} />
        <rect fill="#111" height={mainHeight} width={width} />
        {yTicks.map((tick) => (
          <g key={tick}>
            <line
              className="ns-grid-line"
              x1={left}
              x2={left + chartWidth}
              y1={scaleY(tick)}
              y2={scaleY(tick)}
            />
            <text
              className="ns-axis-label"
              textAnchor="end"
              x={width - 10}
              y={scaleY(tick) + 5}
            >
              {tick}
            </text>
          </g>
        ))}
        <line
          className="ns-axis"
          x1={left}
          x2={left + chartWidth}
          y1={chartBottom}
          y2={chartBottom}
        />
        {xTicks.map((tick, index) => {
          const x = left + ((tick - fromMs) / duration) * chartWidth;
          return (
            <g key={tick}>
              <line
                className="ns-axis"
                x1={x}
                x2={x}
                y1={chartBottom}
                y2={chartBottom + 8}
              />
              <text
                className="ns-axis-label"
                textAnchor={
                  index === 0
                    ? "start"
                    : index === xTicks.length - 1
                      ? "end"
                      : "middle"
                }
                x={x}
                y={chartBottom + labelBand - 6}
              >
                {new Intl.DateTimeFormat("en-US", {
                  hour: "numeric",
                  minute: "2-digit",
                }).format(new Date(tick))}
              </text>
            </g>
          );
        })}

        {mode === "normalized"
          ? points.map((point) => (
              <circle
                className="ns-point ns-point--raw-ghost"
                cx={scaleX(point.timestamp)}
                cy={scaleY(point.raw_value)}
                key={`raw-${point.timestamp}`}
                r={pointRadius * 0.9}
              />
            ))
          : null}
        {points.map((point) => {
          const value = displayValue(point, mode);
          return (
            <circle
              className={`ns-point${mode === "normalized" ? " ns-point--normalized" : ""}`}
              cx={scaleX(point.timestamp)}
              cy={scaleY(value)}
              key={`${mode}-${point.timestamp}`}
              r={pointRadius}
            />
          );
        })}

        {forecastAnchorX !== null && forecastPoints.length ? (
          <line
            className="ns-forecast-boundary"
            x1={forecastAnchorX}
            x2={forecastAnchorX}
            y1={chartTop}
            y2={chartBottom}
          />
        ) : null}
        {forecastPoints.length ? (
          <polyline className="ns-forecast-path" points={forecastPath} />
        ) : null}
        {forecastPoints.map((point) => (
          <circle
            aria-label={`Прогноз через ${point.horizon_minutes} минут: ${formatMmol(point.display_value)} ммоль/л`}
            className={`ns-forecast-point ns-forecast-point--${point.band}`}
            cx={scaleX(point.timestamp)}
            cy={scaleY(point.display_value)}
            key={`forecast-${point.timestamp}`}
            r={pointRadius + 0.8}
            role="img"
          />
        ))}

        {treatmentMarkers.map((treatment) => {
          const anchorX = scaleX(treatment.anchor.timestamp);
          const anchorY = scaleY(displayValue(treatment.anchor, mode));
          const direction = treatment.kind === "insulin" ? -1 : 1;
          const markerGap = treatmentRadius + pointRadius + 8;
          const unclampedY = anchorY + direction * markerGap;
          const markerY = Math.max(
            chartTop + treatmentRadius + 20,
            Math.min(chartBottom - treatmentRadius - 20, unclampedY),
          );
          const connectorEndY =
            anchorY -
            markerY +
            (treatment.kind === "insulin" ? -pointRadius : pointRadius);
          return (
            <g
              aria-label={treatment.ariaLabel}
              className={`ns-treatment ns-treatment--${treatment.kind} ns-treatment--therapy-${treatment.therapyClass.replace(/_/g, "-")}`}
              onClick={
                treatment.kind === "food" && treatment.food
                  ? (event) => {
                      event.stopPropagation();
                      onFoodSelect(treatment.food);
                    }
                  : undefined
              }
              onKeyDown={
                treatment.kind === "food" && treatment.food
                  ? (event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        onFoodSelect(treatment.food);
                      }
                    }
                  : undefined
              }
              key={treatment.key}
              role={treatment.kind === "food" ? "button" : "img"}
              tabIndex={treatment.kind === "food" ? 0 : undefined}
              transform={`translate(${anchorX + treatment.xOffset} ${markerY})`}
            >
              <title>{treatment.detail}</title>
              <line
                className="ns-treatment-link"
                x1="0"
                x2={-treatment.xOffset}
                y1={
                  treatment.kind === "insulin"
                    ? treatmentRadius
                    : -treatmentRadius
                }
                y2={connectorEndY}
              />
              <circle r={treatmentRadius} />
              <text className="ns-treatment-symbol" dy="0.35em">
                {treatment.symbol}
              </text>
              <text
                className="ns-treatment-value"
                y={
                  treatment.kind === "insulin"
                    ? -treatmentRadius - 7
                    : treatmentRadius + 17
                }
              >
                {treatment.valueLabel}
              </text>
            </g>
          );
        })}

        {hover ? (
          <>
            <line
              className="ns-cursor"
              x1={hover.x}
              x2={hover.x}
              y1={chartTop}
              y2={chartBottom}
            />
            <circle
              className={`ns-hover-point${hover.kind === "forecast" ? " ns-hover-point--forecast" : ""}`}
              cx={hover.x}
              cy={hover.y}
              r={pointRadius + 2.5}
            />
          </>
        ) : null}

        <rect
          fill="#111"
          height={overviewHeight}
          width={width}
          x="0"
          y={overviewTop}
        />
        {/* Sleep fills the band behind everything; effort is a thin rule along
            its top edge. Both stay quiet enough to read the glucose over. */}
        {bodyStatePoints.map((state) => {
          const startX = Math.max(left, overviewX(state.start_at));
          const endX = Math.min(left + chartWidth, overviewX(state.end_at));
          if (!(endX > startX)) return null;
          const isSleep = state.kind === "sleep";
          const bandHeight = isSleep ? overviewHeight : 4;
          return (
            <rect
              className={`ns-body-state ns-body-state--${state.kind} ns-body-state--${state.source.replace(/_/g, "-")}`}
              height={bandHeight}
              key={`body-state-${state.kind}-${state.start_at}`}
              width={Math.max(1.5, endX - startX)}
              x={startX}
              y={overviewTop + (isSleep ? 0 : 1)}
            >
              <title>{bodyStateTitle(state)}</title>
            </rect>
          );
        })}
        {heartRatePoints.length ? (
          <g aria-label="Пульс за 24 часа" role="img">
            <text
              aria-hidden="true"
              className="ns-heart-rate-label"
              x={left + 5}
              y={overviewTop + 14}
            >
              HR
            </text>
            {heartRatePoints.map((point) => {
              const barHeight = heartRateBarHeight(point.bpm);
              const barCenterX = overviewX(
                new Date(
                  Date.parse(point.timestamp) + heartRateBinMs / 2,
                ).toISOString(),
              );
              return (
                <rect
                  aria-label={`${point.bpm.toFixed(0)} ударов в минуту, медиана за ${heartRate?.bin_minutes ?? 10} минут`}
                  className="ns-heart-rate-bar"
                  height={barHeight}
                  key={`heart-rate-${point.timestamp}`}
                  role="img"
                  width={heartRateBarWidth}
                  x={barCenterX - heartRateBarWidth / 2}
                  y={overviewTop + overviewHeight - barHeight}
                >
                  <title>
                    {`${new Intl.DateTimeFormat("ru-RU", {
                      hour: "2-digit",
                      minute: "2-digit",
                    }).format(new Date(point.timestamp))} · ${point.bpm.toFixed(0)} уд/мин · ${point.sample_count} изм.`}
                  </title>
                </rect>
              );
            })}
          </g>
        ) : null}
        {overviewPoints.map((point) => (
          <circle
            className="ns-overview-point"
            cx={overviewX(point.timestamp)}
            cy={overviewY(displayValue(point, mode))}
            key={`overview-${point.timestamp}`}
            r={overviewRadius}
          />
        ))}
        <rect
          aria-label="Сдвинуть выбранное окно"
          className="ns-overview-selection"
          height={overviewHeight}
          onKeyDown={(event) => moveOverviewWithKeyboard(event, "move")}
          onPointerDown={(event) => beginOverviewDrag(event, "move")}
          role="button"
          tabIndex={0}
          width={selectionWidth}
          x={selectionX}
          y={overviewTop}
        />
        <line
          aria-hidden="true"
          className="ns-overview-handle"
          x1={selectionX}
          x2={selectionX}
          y1={overviewTop}
          y2={overviewTop + overviewHeight}
        />
        <rect
          aria-label="Изменить левую границу окна"
          aria-orientation="horizontal"
          aria-valuemax={selectedRange.toMs - MIN_CHART_WINDOW_MS}
          aria-valuemin={overviewFrom}
          aria-valuenow={selectedRange.fromMs}
          className="ns-overview-handle-hit"
          height={overviewHeight}
          onKeyDown={(event) => moveOverviewWithKeyboard(event, "start")}
          onPointerDown={(event) => beginOverviewDrag(event, "start")}
          role="slider"
          tabIndex={0}
          width={overviewHandleHitWidth}
          x={selectionX - overviewHandleHitWidth / 2}
          y={overviewTop}
        />
        <line
          aria-hidden="true"
          className="ns-overview-handle"
          x1={selectionRightX}
          x2={selectionRightX}
          y1={overviewTop}
          y2={overviewTop + overviewHeight}
        />
        <rect
          aria-label="Изменить правую границу окна"
          aria-orientation="horizontal"
          aria-valuemax={overviewTo}
          aria-valuemin={selectedRange.fromMs + MIN_CHART_WINDOW_MS}
          aria-valuenow={selectedRange.toMs}
          className="ns-overview-handle-hit"
          height={overviewHeight}
          onKeyDown={(event) => moveOverviewWithKeyboard(event, "end")}
          onPointerDown={(event) => beginOverviewDrag(event, "end")}
          role="slider"
          tabIndex={0}
          width={overviewHandleHitWidth}
          x={selectionRightX - overviewHandleHitWidth / 2}
          y={overviewTop}
        />
        <line
          className="ns-axis"
          x1={left}
          x2={left + chartWidth}
          y1={overviewTop + overviewHeight}
          y2={overviewTop + overviewHeight}
        />
        {overviewTicks.map((tick, index) => {
          const x =
            left + ((tick - overviewFrom) / overviewDuration) * chartWidth;
          return (
            <text
              className="ns-axis-label"
              key={tick}
              textAnchor={
                index === 0
                  ? "start"
                  : index === overviewTicks.length - 1
                    ? "end"
                    : "middle"
              }
              x={x}
              y={height - 6}
            >
              {new Intl.DateTimeFormat("en-US", {
                day: "numeric",
                hour: "numeric",
                month: "short",
              }).format(new Date(tick))}
            </text>
          );
        })}
      </svg>

      {hover ? (
        <div
          className="ns-tooltip"
          style={{
            left: `${Math.min(88, Math.max(2, (hover.x / width) * 100))}%`,
            top: `${Math.max(2, (hover.y / height) * 100 - 2)}%`,
          }}
        >
          <b>BG: {formatMmol(hover.value)}</b>
          {hover.kind === "forecast" ? (
            <>
              <span>Прогноз: +{hover.point.horizon_minutes} мин</span>
              <span>
                80%: {formatMmol(hover.point.ci_low)}–
                {formatMmol(hover.point.ci_high)}
              </span>
              <span>Доверие: {Math.round(hover.point.confidence * 100)}%</span>
            </>
          ) : (
            <span>Noise: ~~~</span>
          )}
          <span>
            Time:{" "}
            {new Intl.DateTimeFormat("en-US", {
              hour: "numeric",
              minute: "2-digit",
            }).format(new Date(hover.point.timestamp))}
          </span>
          {mode === "normalized" && hover.kind === "history" ? (
            <span>Standard: {formatMmol(hover.point.raw_value)}</span>
          ) : null}
        </div>
      ) : null}

      {forecastPoints.length ? (
        <div
          aria-label="Исследовательский прогноз глюкозы"
          className="ns-forecast-summary"
        >
          <span className="ns-forecast-summary-dot" />
          <b>
            +{forecastPoints[forecastPoints.length - 1]!.horizon_minutes} мин ·{" "}
            {formatMmol(
              forecastPoints[forecastPoints.length - 1]!.display_value,
            )}
          </b>
          <small>
            {prediction?.model.confidence ?? "none"}
            {typeof prediction?.model.validation_mae_mmol === "number"
              ? ` · MAE ${prediction.model.validation_mae_mmol.toFixed(2)}`
              : ""}
            {" · справочно"}
          </small>
        </div>
      ) : predictionError ? (
        <div className="ns-forecast-summary ns-forecast-summary--error">
          Прогноз недоступен
        </div>
      ) : null}

      {points.length === 0 ? (
        <div
          className="ns-chart-empty"
          style={{ bottom: `${Math.max(0, height - overviewTop)}px` }}
        >
          {loading
            ? "Загружаю CGM…"
            : error
              ? "Не удалось загрузить данные CGM."
              : "Нет данных CGM за выбранный период."}
        </div>
      ) : null}
    </div>
  );
}
