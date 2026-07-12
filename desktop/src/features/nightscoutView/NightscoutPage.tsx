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
  const svgRef = useRef<SVGSVGElement>(null);
  const [hover, setHover] = useState<HoverPoint | null>(null);
  const width = 1280;
  const mainHeight = 650;
  const overviewTop = 690;
  const overviewHeight = 180;
  const height = 900;
  const left = 0;
  const right = 72;
  const chartWidth = width - right;
  const chartTop = 12;
  const chartBottom = mainHeight;
  const points = data?.points ?? [];
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
  const scaleY = (value: number) =>
    chartBottom - ((value - 2) / 20) * (chartBottom - chartTop);
  const overviewX = (timestamp: string) =>
    ((Date.parse(timestamp) - overviewFrom) / overviewDuration) * chartWidth;
  const overviewY = (value: number) =>
    overviewTop + overviewHeight - ((value - 2) / 20) * overviewHeight;
  const xTicks = Array.from({ length: 7 }, (_, index) => fromMs + (duration * index) / 6);
  const overviewTicks = Array.from(
    { length: 5 },
    (_, index) => overviewFrom + (overviewDuration * index) / 4,
  );
  const selectionX =
    ((fromMs - overviewFrom) / overviewDuration) * chartWidth;
  const selectionWidth = Math.max((duration / overviewDuration) * chartWidth, 2);

  const handlePointerMove = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (!svgRef.current || points.length === 0) return;
    const rect = svgRef.current.getBoundingClientRect();
    const svgX = ((event.clientX - rect.left) / rect.width) * width;
    const timestamp = fromMs + (svgX / chartWidth) * duration;
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
    <div className="ns-chart-shell">
      <svg
        aria-label="График глюкозы Nightscout"
        className="ns-chart"
        onPointerLeave={() => setHover(null)}
        onPointerMove={handlePointerMove}
        preserveAspectRatio="none"
        ref={svgRef}
        role="img"
        viewBox={`0 0 ${width} ${height}`}
      >
        <rect fill="#111" height={mainHeight} width={width} />
        {MAIN_Y_TICKS.map((tick) => (
          <g key={tick}>
            <line
              className="ns-grid-line"
              x1="0"
              x2={chartWidth}
              y1={scaleY(tick)}
              y2={scaleY(tick)}
            />
            <text className="ns-axis-label" textAnchor="end" x={width - 8} y={scaleY(tick) + 7}>
              {tick}
            </text>
          </g>
        ))}
        <line className="ns-axis" x1="0" x2={chartWidth} y1={chartBottom} y2={chartBottom} />
        {xTicks.map((tick) => {
          const x = ((tick - fromMs) / duration) * chartWidth;
          return (
            <g key={tick}>
              <line className="ns-axis" x1={x} x2={x} y1={chartBottom} y2={chartBottom + 10} />
              <text className="ns-axis-label" textAnchor="middle" x={x} y={chartBottom + 34}>
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
                r="4"
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
              r="4.3"
            />
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
            <circle className="ns-hover-point" cx={hover.x} cy={hover.y} r="7" />
          </>
        ) : null}

        <rect fill="#111" height={overviewHeight} width={width} x="0" y={overviewTop} />
        {overviewPoints.map((point) => (
          <circle
            className="ns-overview-point"
            cx={overviewX(point.timestamp)}
            cy={overviewY(displayValue(point, mode))}
            key={`overview-${point.timestamp}`}
            r="2.5"
          />
        ))}
        <rect
          className="ns-overview-selection"
          height={overviewHeight}
          width={selectionWidth}
          x={selectionX}
          y={overviewTop}
        />
        <line className="ns-axis" x1="0" x2={chartWidth} y1={overviewTop + overviewHeight} y2={overviewTop + overviewHeight} />
        {overviewTicks.map((tick) => {
          const x = ((tick - overviewFrom) / overviewDuration) * chartWidth;
          return (
            <text className="ns-axis-label" key={tick} textAnchor="middle" x={x} y={height - 4}>
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
