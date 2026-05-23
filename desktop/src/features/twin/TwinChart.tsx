import type { TwinCurveResponse } from "../../api/client";
import { formatMmol } from "../../utils/nutritionFormat";

type TwinPoint = TwinCurveResponse["points"][number];

const VIEW_WIDTH = 920;
const VIEW_HEIGHT = 360;
const PAD_LEFT = 56;
const PAD_RIGHT = 24;
const PAD_TOP = 24;
const PAD_BOTTOM = 48;

const formatTime = (value: string) =>
  new Intl.DateTimeFormat("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));

function linePath(points: TwinPoint[], xFor: (iso: string) => number, yFor: (v: number) => number) {
  return points
    .map((point, index) => {
      const command = index === 0 ? "M" : "L";
      return `${command}${xFor(point.timestamp).toFixed(1)},${yFor(point.mmol).toFixed(1)}`;
    })
    .join(" ");
}

function bandPath(points: TwinPoint[], xFor: (iso: string) => number, yFor: (v: number) => number) {
  if (!points.length) return "";
  const upper = points
    .map((point, index) => {
      const command = index === 0 ? "M" : "L";
      return `${command}${xFor(point.timestamp).toFixed(1)},${yFor(point.ci_high).toFixed(1)}`;
    })
    .join(" ");
  const lower = points
    .slice()
    .reverse()
    .map((point) => `L${xFor(point.timestamp).toFixed(1)},${yFor(point.ci_low).toFixed(1)}`)
    .join(" ");
  return `${upper} ${lower} Z`;
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

export function TwinChart({ data }: { data: TwinCurveResponse | undefined }) {
  const points = data?.points ?? [];
  const anchors = data?.anchors ?? [];
  const food = data?.food_events ?? [];
  const insulin = data?.insulin_events ?? [];

  if (!data || (!points.length && !anchors.length)) {
    return (
      <div className="twin-chart-empty" data-testid="twin-chart-empty">
        Нет точек для графика.
      </div>
    );
  }

  const fromMs = Date.parse(data.from_datetime);
  const toMs = Date.parse(data.to_datetime);
  const duration = Math.max(toMs - fromMs, 1);
  const chartWidth = VIEW_WIDTH - PAD_LEFT - PAD_RIGHT;
  const chartHeight = VIEW_HEIGHT - PAD_TOP - PAD_BOTTOM;
  const values = [
    ...points.flatMap((point) => [point.ci_low, point.ci_high, point.mmol]),
    ...anchors.map((anchor) => anchor.mmol),
  ];
  const min = Math.min(...values, 3.5);
  const max = Math.max(...values, 12);
  const pad = Math.max((max - min) * 0.12, 0.8);
  const low = min - pad;
  const high = max + pad;
  const xFor = (iso: string) =>
    PAD_LEFT + clamp((Date.parse(iso) - fromMs) / duration, 0, 1) * chartWidth;
  const yFor = (value: number) =>
    PAD_TOP + chartHeight - ((value - low) / (high - low)) * chartHeight;

  const interpolation = points.filter((point) => point.mode === "interpolation");
  const forecast = points.filter((point) => point.mode === "forecast");
  const boundary = points.filter((point) => point.mode === "boundary");
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((ratio) => fromMs + duration * ratio);
  const yTicks = [low, (low + high) / 2, high];

  return (
    <div className="twin-chart-shell">
      <svg
        aria-label="График цифрового двойника"
        className="twin-chart"
        preserveAspectRatio="xMidYMid meet"
        role="img"
        viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`}
      >
        <rect
          fill="var(--surface-2)"
          height={chartHeight}
          stroke="var(--hairline)"
          width={chartWidth}
          x={PAD_LEFT}
          y={PAD_TOP}
        />
        {yTicks.map((tick) => (
          <g key={tick}>
            <line
              stroke="var(--hairline)"
              strokeDasharray="3 5"
              x1={PAD_LEFT}
              x2={VIEW_WIDTH - PAD_RIGHT}
              y1={yFor(tick)}
              y2={yFor(tick)}
            />
            <text
              className="mono"
              fill="var(--ink-3)"
              fontSize="11"
              textAnchor="end"
              x={PAD_LEFT - 10}
              y={yFor(tick) + 4}
            >
              {formatMmol(tick)}
            </text>
          </g>
        ))}
        {ticks.map((tick) => (
          <g key={tick}>
            <line
              stroke="var(--hairline)"
              x1={xFor(new Date(tick).toISOString())}
              x2={xFor(new Date(tick).toISOString())}
              y1={PAD_TOP}
              y2={PAD_TOP + chartHeight}
            />
            <text
              className="mono"
              fill="var(--ink-3)"
              fontSize="11"
              textAnchor="middle"
              x={xFor(new Date(tick).toISOString())}
              y={VIEW_HEIGHT - 18}
            >
              {formatTime(new Date(tick).toISOString())}
            </text>
          </g>
        ))}
        {points.length ? (
          <path
            d={bandPath(points, xFor, yFor)}
            data-testid="twin-ci-band"
            fill="var(--info, var(--ink-3))"
            opacity="0.15"
          />
        ) : null}
        {boundary.length ? (
          <path
            d={linePath(boundary, xFor, yFor)}
            fill="none"
            stroke="var(--ink-3)"
            strokeDasharray="2 6"
            strokeLinecap="round"
            strokeWidth="2"
          />
        ) : null}
        {interpolation.length ? (
          <path
            d={linePath(interpolation, xFor, yFor)}
            data-testid="twin-interpolation-line"
            fill="none"
            stroke="var(--ink)"
            strokeLinejoin="round"
            strokeWidth="2.2"
          />
        ) : null}
        {forecast.length ? (
          <path
            d={linePath(forecast, xFor, yFor)}
            data-testid="twin-forecast-line"
            fill="none"
            stroke="var(--ink)"
            strokeDasharray="7 6"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="2.2"
          />
        ) : null}
        {food.map((event, index) => (
          <g key={`food-${event.timestamp}-${index}`}>
            <title>{`${formatTime(event.timestamp)} ${event.title}: ${event.carbs_g} г углеводов`}</title>
            <circle
              cx={xFor(event.timestamp)}
              cy={PAD_TOP + 18}
              fill="var(--accent)"
              r="4"
            />
          </g>
        ))}
        {insulin.map((event, index) => (
          <g key={`insulin-${event.timestamp}-${index}`}>
            <title>{`${formatTime(event.timestamp)} инсулин из Nightscout: ${event.insulin_units} ЕД`}</title>
            <line
              stroke="var(--ink-2)"
              strokeLinecap="round"
              strokeWidth="2"
              x1={xFor(event.timestamp)}
              x2={xFor(event.timestamp)}
              y1={PAD_TOP + 30}
              y2={PAD_TOP + 46}
            />
          </g>
        ))}
        {anchors.map((anchor) => {
          const x = xFor(anchor.timestamp);
          const y = yFor(anchor.mmol);
          return (
            <g key={`${anchor.source}-${anchor.timestamp}`}>
              <title>{`${formatTime(anchor.timestamp)} из пальца: ${formatMmol(anchor.mmol)} ммоль/л`}</title>
              <polygon
                data-testid="twin-anchor"
                fill="var(--surface)"
                points={`${x},${y - 7} ${x + 7},${y} ${x},${y + 7} ${x - 7},${y}`}
                stroke="var(--ink)"
                strokeWidth="1.6"
              />
            </g>
          );
        })}
        <g className="twin-chart-legend" transform={`translate(${VIEW_WIDTH - 380},${VIEW_HEIGHT - 18})`}>
          <line stroke="var(--ink)" strokeWidth="2" x1="0" x2="26" y1="-4" y2="-4" />
          <text fill="var(--ink-3)" fontSize="11" x="34" y="0">
            реконструкция
          </text>
          <line
            stroke="var(--ink)"
            strokeDasharray="7 6"
            strokeWidth="2"
            x1="132"
            x2="158"
            y1="-4"
            y2="-4"
          />
          <text fill="var(--ink-3)" fontSize="11" x="166" y="0">
            прогноз
          </text>
          <polygon
            fill="var(--surface)"
            points="260,-11 267,-4 260,3 253,-4"
            stroke="var(--ink)"
            strokeWidth="1.2"
          />
          <text fill="var(--ink-3)" fontSize="11" x="276" y="0">
            из пальца
          </text>
        </g>
      </svg>
    </div>
  );
}
