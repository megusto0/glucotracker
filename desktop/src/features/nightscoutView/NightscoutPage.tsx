import { Bell, Menu, RefreshCw, Volume2 } from "lucide-react";
import {
  useMemo,
  useRef,
  useState,
  useEffect,
  type PointerEvent as ReactPointerEvent,
} from "react";
import { useNavigate } from "react-router-dom";
import type {
  GlucoseDashboardResponse,
  GlucoseMode,
} from "../../api/client";
import { useGlucoseDashboard } from "../glucose/useGlucoseDashboard";
import "./nightscout-page.css";

type DisplayMode = Extract<GlucoseMode, "raw" | "normalized">;
type DashboardPoint = GlucoseDashboardResponse["points"][number];
type HoverPoint = {
  point: DashboardPoint;
  value: number;
  x: number;
  y: number;
};
const HOUR_OPTIONS = [2, 3, 4, 6, 12, 24] as const;
const MAIN_Y_TICKS = [2, 3, 4, 6, 10, 14, 22] as const;
const REFRESH_INTERVAL_MS = 60 * 1000;

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
    ? point.normalized_value ?? point.raw_value
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

/**
 * Small horizontal fan for markers that share nearly the same clock X on one
 * rail (food or insulin). Keeps the classic Nightscout top-band layout clean.
 */
function railOffsets(
  xs: number[],
  spacing: number,
): number[] {
  const groups = new Map<number, number[]>();
  xs.forEach((x, index) => {
    const bucket = Math.round(x / Math.max(spacing, 1));
    const list = groups.get(bucket) ?? [];
    list.push(index);
    groups.set(bucket, list);
  });
  const offsets = xs.map(() => 0);
  groups.forEach((indexes) => {
    if (indexes.length < 2) return;
    indexes.forEach((index, order) => {
      offsets[index] = (order - (indexes.length - 1) / 2) * spacing;
    });
  });
  return offsets;
}

export function NightscoutPage() {
  const navigate = useNavigate();
  const [hours, setHours] = useState<(typeof HOUR_OPTIONS)[number]>(3);
  const [mode, setMode] = useState<DisplayMode>("raw");
  const [menuOpen, setMenuOpen] = useState(false);
  const [refreshAnchor, setRefreshAnchor] = useState(() => new Date());

  useEffect(() => {
    const interval = window.setInterval(
      () => setRefreshAnchor(new Date()),
      REFRESH_INTERVAL_MS,
    );
    return () => window.clearInterval(interval);
  }, []);

  const range = useMemo(() => {
    const to = refreshAnchor;
    return {
      from: toApiDateTime(new Date(to.getTime() - hours * 60 * 60 * 1000)),
      to: toApiDateTime(to),
    };
  }, [hours, refreshAnchor]);
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

  const refresh = () => setRefreshAnchor(new Date());

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
          <button aria-label="Уведомления" className="ns-icon-button" type="button">
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
                aria-pressed={hours === option}
                className={hours === option ? "active" : ""}
                key={option}
                onClick={() => setHours(option)}
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
            <span aria-label={`Тренд ${trendSymbol(delta)}`} className="ns-trend">
              {trendSymbol(delta)}
            </span>
          </div>
          <div className="ns-delta-pill">
            <b>{delta === null ? "—" : `${delta >= 0 ? "+" : ""}${formatMmol(delta)}`}</b>
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
            <small>
              {summary?.cob_minutes_remaining ?? 0} мин до усвоения
            </small>
          </div>
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
        loading={dashboard.isLoading}
        mode={mode}
        overview={overview.data}
      />
    </div>
  );
}

function NightscoutChart({
  data,
  error,
  loading,
  mode,
  overview,
}: {
  data?: GlucoseDashboardResponse;
  error: boolean;
  loading: boolean;
  mode: DisplayMode;
  overview?: GlucoseDashboardResponse;
}) {
  const shellRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const [hover, setHover] = useState<HoverPoint | null>(null);
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
  const yMin = 2;
  const yMax = 16; // tighter than 22 so typical 3–10 mmol/L isn't a thin strip
  const ySpan = yMax - yMin;
  const yTicks = MAIN_Y_TICKS.filter((tick) => tick >= yMin && tick <= yMax);
  const pointRadius = Math.max(3.2, Math.min(5.2, Math.min(width, height) * 0.0048));
  const overviewRadius = Math.max(2, pointRadius * 0.55);
  const treatmentRadius = Math.max(8, Math.min(11, pointRadius * 2.25));

  const points = data?.points ?? [];
  const foodEvents = data?.food_events ?? [];
  const insulinEvents = dedupeInsulinEvents(data?.insulin_events ?? []);
  const overviewPoints = overview?.points ?? [];
  const fromMs = data ? Date.parse(data.from_datetime) : Date.now() - 3 * 3_600_000;
  const toMs = data ? Date.parse(data.to_datetime) : Date.now();
  const duration = Math.max(toMs - fromMs, 1);
  const overviewFrom = overview
    ? Date.parse(overview.from_datetime)
    : Date.now() - 24 * 3_600_000;
  const overviewTo = overview ? Date.parse(overview.to_datetime) : Date.now();
  const overviewDuration = Math.max(overviewTo - overviewFrom, 1);
  const scaleX = (timestamp: string) =>
    left + ((Date.parse(timestamp) - fromMs) / duration) * chartWidth;
  const scaleY = (value: number) => {
    const clamped = Math.min(yMax, Math.max(yMin, value));
    return chartBottom - ((clamped - yMin) / ySpan) * plotHeight;
  };
  const overviewX = (timestamp: string) =>
    left + ((Date.parse(timestamp) - overviewFrom) / overviewDuration) * chartWidth;
  const overviewY = (value: number) => {
    const clamped = Math.min(yMax, Math.max(yMin, value));
    return (
      overviewTop +
      overviewHeight -
      ((clamped - yMin) / ySpan) * overviewHeight
    );
  };
  const xTicks = Array.from({ length: 7 }, (_, index) => fromMs + (duration * index) / 6);
  const overviewTicks = Array.from(
    { length: 5 },
    (_, index) => overviewFrom + (overviewDuration * index) / 4,
  );
  const selectionX =
    left + ((fromMs - overviewFrom) / overviewDuration) * chartWidth;
  const selectionWidth = Math.max((duration / overviewDuration) * chartWidth, 2);
  // Classic Nightscout layout: food and insulin on separate top rails.
  // Do NOT glue markers to the CGM curve — that caused piles and "drift".
  const foodRailY = chartTop + treatmentRadius + 4;
  const insulinRailY = chartTop + treatmentRadius * 3.6 + 10;
  const fanSpacing = treatmentRadius * 2 + 6;

  const foodMarkers = foodEvents.map((event, index) => ({
    ariaLabel: `${event.title}: ${event.carbs_g.toFixed(1)} г углеводов`,
    detail: `${event.title} · ${event.carbs_g.toFixed(1)} г углеводов`,
    key: `food-${event.timestamp}-${index}`,
    kind: "food" as const,
    timestamp: event.timestamp,
    valueLabel: `${event.carbs_g.toFixed(0)}g`,
    x: scaleX(event.timestamp),
    y: foodRailY,
  }));
  const foodFan = railOffsets(
    foodMarkers.map((marker) => marker.x),
    fanSpacing,
  );
  const insulinMarkers = insulinEvents.map((event, index) => ({
    ariaLabel: `Инсулин: ${event.insulin_units?.toFixed(2) ?? "—"} единиц`,
    detail: `Инсулин · ${event.insulin_units?.toFixed(2) ?? "—"} Ед${
      event.notes ? ` · ${event.notes}` : ""
    }`,
    key: `insulin-${event.timestamp}-${index}`,
    kind: "insulin" as const,
    timestamp: event.timestamp,
    valueLabel:
      typeof event.insulin_units === "number"
        ? `${event.insulin_units.toFixed(1)}U`
        : "—",
    x: scaleX(event.timestamp),
    y: insulinRailY,
  }));
  const insulinFan = railOffsets(
    insulinMarkers.map((marker) => marker.x),
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

  const handlePointerMove = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (!svgRef.current || points.length === 0) return;
    const rect = svgRef.current.getBoundingClientRect();
    const svgX = ((event.clientX - rect.left) / rect.width) * width;
    const timestamp = fromMs + ((svgX - left) / chartWidth) * duration;
    const nearest = points.reduce((best, point) =>
      Math.abs(Date.parse(point.timestamp) - timestamp) <
      Math.abs(Date.parse(best.timestamp) - timestamp)
        ? point
        : best,
    );
    const value = displayValue(nearest, mode);
    setHover({ point: nearest, value, x: scaleX(nearest.timestamp), y: scaleY(value) });
  };

  if (loading && points.length === 0) {
    return <div className="ns-chart-message">Загружаю CGM…</div>;
  }
  if (error && points.length === 0) {
    return <div className="ns-chart-message">Не удалось загрузить данные CGM.</div>;
  }

  return (
    <div className="ns-chart-shell" ref={shellRef}>
      <svg
        aria-label="График глюкозы Nightscout"
        className="ns-chart"
        height={height}
        onPointerLeave={() => setHover(null)}
        onPointerMove={handlePointerMove}
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
        {xTicks.map((tick) => {
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
                textAnchor="middle"
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

        {treatmentMarkers.map((treatment) => {
          const x = treatment.x + treatment.xOffset;
          return (
            <g
              aria-label={treatment.ariaLabel}
              className={`ns-treatment ns-treatment--${treatment.kind}`}
              key={treatment.key}
              role="img"
              transform={`translate(${x} ${treatment.y})`}
            >
              <title>{treatment.detail}</title>
              <circle r={treatmentRadius} />
              <text className="ns-treatment-symbol" dy="0.35em">
                {treatment.kind === "food" ? "C" : "I"}
              </text>
              <text
                className="ns-treatment-value"
                y={treatmentRadius + 13}
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
              className="ns-hover-point"
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
          className="ns-overview-selection"
          height={overviewHeight}
          width={selectionWidth}
          x={selectionX}
          y={overviewTop}
        />
        <line
          className="ns-axis"
          x1={left}
          x2={left + chartWidth}
          y1={overviewTop + overviewHeight}
          y2={overviewTop + overviewHeight}
        />
        {overviewTicks.map((tick) => {
          const x = left + ((tick - overviewFrom) / overviewDuration) * chartWidth;
          return (
            <text
              className="ns-axis-label"
              key={tick}
              textAnchor="middle"
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
          <span>Noise: ~~~</span>
          <span>
            Time: {new Intl.DateTimeFormat("en-US", {
              hour: "numeric",
              minute: "2-digit",
            }).format(new Date(hover.point.timestamp))}
          </span>
          {mode === "normalized" ? (
            <span>Standard: {formatMmol(hover.point.raw_value)}</span>
          ) : null}
        </div>
      ) : null}

      {points.length === 0 && !loading ? (
        <div className="ns-chart-empty">Нет данных CGM за выбранный период.</div>
      ) : null}
    </div>
  );
}
