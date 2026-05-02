import { useState, useMemo } from "react";
import type {
  DashboardDataQualityResponse,
  DashboardDayResponse,
  DashboardHeatmapResponse,
  DashboardSourceBreakdownResponse,
  DashboardTodayResponse,
  DashboardTopPatternResponse,
  KcalBalanceDay,
} from "../../api/client";
import {
  defaultDashboardRange,
  useDashboardDataQuality,
  useDashboardHeatmap,
  useDashboardRange,
  useDashboardSourceBreakdown,
  useDashboardToday,
  useDashboardTopPatterns,
  useKcalBalanceRange,
} from "./useDashboard";

const round = (value?: number | null) =>
  value === null || value === undefined ? "--" : Math.round(value).toString();

const percent = (count: number, total: number) =>
  total > 0 ? Math.round((count / total) * 100) : 0;

const range = defaultDashboardRange();

const sourceKindLabel = (value: string) =>
  ({
    label_calc: "расчет по этикетке",
    restaurant_db: "ресторанная база",
    product_db: "база продуктов",
    pattern: "шаблон",
    photo_estimate: "оценка по фото",
    manual: "вручную",
  })[value] ?? value.replace(/_/g, " ");

export function StatsPage() {
  const today = useDashboardToday();
  const rangeQuery = useDashboardRange(range.from, range.to);
  const heatmap = useDashboardHeatmap(4);
  const topPatterns = useDashboardTopPatterns(7, 10);
  const sourceBreakdown = useDashboardSourceBreakdown(7);
  const dataQuality = useDashboardDataQuality(7);
  const kcalBalance = useKcalBalanceRange(range.from, range.to);

  const noData =
    today.isSuccess &&
    rangeQuery.isSuccess &&
    heatmap.isSuccess &&
    topPatterns.isSuccess &&
    sourceBreakdown.isSuccess &&
    dataQuality.isSuccess &&
    today.data.meal_count === 0 &&
    rangeQuery.data.summary.total_meals === 0 &&
    heatmap.data.cells.length === 0 &&
    topPatterns.data.length === 0 &&
    sourceBreakdown.data.items.length === 0 &&
    dataQuality.data.total_item_count === 0;

  return (
    <div className="min-h-screen bg-[var(--bg)] px-10 py-9">
      <header className="grid gap-3">
        <p className="text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">
          сводка
        </p>
        <h1 className="font-mono text-[64px] font-normal leading-none text-[var(--fg)]">
          Статистика
        </h1>
      </header>

      {noData ? (
        <div className="grid min-h-[52vh] place-items-center text-[15px] text-[var(--muted)]">
          данных пока нет
        </div>
      ) : (
        <div className="mt-12 grid gap-14">
          <KpiRow today={today.data} />

          <section className="grid gap-12 xl:grid-cols-[minmax(0,1.4fr)_minmax(420px,0.9fr)]">
            <ChartSection
              days={rangeQuery.data?.days ?? []}
              loading={rangeQuery.isLoading}
            />
            <KcalChartSection
              dashboardDays={rangeQuery.data?.days ?? []}
              days={kcalBalance.data?.days ?? []}
              loading={kcalBalance.isLoading}
            />
            <HeatmapSection data={heatmap.data} loading={heatmap.isLoading} />
          </section>

          <section className="grid gap-12 xl:grid-cols-3">
            <TopPatterns patterns={topPatterns.data ?? []} />
            <SourceBreakdown data={sourceBreakdown.data} />
            <DataQuality data={dataQuality.data} />
          </section>
        </div>
      )}
    </div>
  );
}

function KpiRow({ today }: { today?: DashboardTodayResponse }) {
  const mealLabel = today?.meal_count === 1 ? "запись" : "записей";
  const hours =
    today?.hours_since_last_meal === null ||
    today?.hours_since_last_meal === undefined
      ? "--"
      : today.hours_since_last_meal < 1
        ? "<1"
        : Math.round(today.hours_since_last_meal).toString();

  return (
    <section className="grid grid-cols-2 gap-8 xl:grid-cols-4">
      <KpiTile
        label="углеводы сегодня"
        value={round(today?.carbs_g)}
        unit="г"
        compare={`среднее за неделю ${round(today?.week_avg_carbs)} г`}
      />
      <KpiTile
        label="ккал сегодня"
        value={round(today?.kcal)}
        compare={`среднее за неделю ${round(today?.week_avg_kcal)} ккал`}
      />
      <KpiTile
        label="записей сегодня"
        value={round(today?.meal_count)}
        compare={mealLabel}
      />
      <KpiTile
        label="часов с последней еды"
        value={hours}
        compare={today?.last_meal_at ? "последняя запись есть" : "сегодня нет еды"}
      />
    </section>
  );
}

function KpiTile({
  compare,
  label,
  unit,
  value,
}: {
  compare: string;
  label: string;
  unit?: string;
  value: string;
}) {
  return (
    <div className="border-y border-[var(--hairline)] py-5">
      <div className="text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">
        {label}
      </div>
      <div className="mt-5 font-mono text-[48px] leading-none text-[var(--fg)]">
        {value}
        {unit ? (
          <span className="ml-2 text-[13px] lowercase tracking-normal">
            {unit}
          </span>
        ) : null}
      </div>
      <div className="mt-4 text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">
        {compare}
      </div>
    </div>
  );
}

function ChartSection({
  days,
  loading,
}: {
  days: DashboardDayResponse[];
  loading: boolean;
}) {
  return (
    <section className="grid gap-5">
      <SectionHeader eyebrow="30 дней" title="Углеводы по дням" />
      {loading ? (
        <MutedLine>загружаю период</MutedLine>
      ) : days.length ? (
        <DailyCarbsChart days={days} />
      ) : (
        <MutedLine>нет данных за период</MutedLine>
      )}
    </section>
  );
}

function DailyCarbsChart({ days }: { days: DashboardDayResponse[] }) {
  const max = Math.max(...days.map((day) => day.carbs_g), 1);
  const width = 900;
  const height = 260;
  const chartTop = 18;
  const chartBottom = 218;
  const step = width / days.length;
  const barWidth = Math.max(4, step * 0.56);

  return (
    <svg
      aria-label="Углеводы по дням за последние 30 дней"
      className="h-[280px] w-full border-y border-[var(--hairline)] py-5"
      role="img"
      viewBox={`0 0 ${width} ${height}`}
    >
      <line
        stroke="var(--hairline)"
        x1="0"
        x2={width}
        y1={chartBottom}
        y2={chartBottom}
      />
      {days.map((day, index) => {
        const valueHeight = (day.carbs_g / max) * (chartBottom - chartTop);
        const x = index * step + (step - barWidth) / 2;
        const y = chartBottom - valueHeight;
        return (
          <rect
            data-testid="range-bar"
            fill="var(--accent)"
            height={Math.max(1, valueHeight)}
            key={day.date}
            opacity={0.82}
            width={barWidth}
            x={x}
            y={y}
          />
        );
      })}
      <text fill="var(--muted)" fontSize="11" x="0" y="250">
        {days[0]?.date.slice(5)}
      </text>
      <text
        fill="var(--muted)"
        fontSize="11"
        textAnchor="end"
        x={width}
        y="250"
      >
        {days[days.length - 1]?.date.slice(5)}
      </text>
    </svg>
  );
}

function KcalChartSection({
  dashboardDays,
  days,
  loading,
}: {
  dashboardDays: DashboardDayResponse[];
  days: KcalBalanceDay[];
  loading: boolean;
}) {
  const summary = useMemo(() => {
    if (!days.length) return null;
    const foodDays = dashboardDays.filter((d) => d.meal_count > 0);
    const hasFoodMap = new Set(foodDays.map((d) => d.date));

    let totalFoodBalance = 0;
    let balanceDaysCount = 0;
    let todayBalance: number | null = null;

    const todayStr = days[days.length - 1]?.date;

    let activityDays = 0;
    days.forEach((d) => {
      if (d.tdee && d.tdee > 0) activityDays++;
      if (hasFoodMap.has(d.date) && d.net_balance != null) {
        totalFoodBalance += d.net_balance;
        balanceDaysCount++;
        if (d.date === todayStr) {
          todayBalance = d.net_balance;
        }
      }
    });

    return {
      todayBalance,
      avgBalance:
        balanceDaysCount > 0
          ? Math.round(totalFoodBalance / balanceDaysCount)
          : null,
      foodDays: hasFoodMap.size,
      activityDays,
      totalDays: days.length,
    };
  }, [days, dashboardDays]);

  return (
    <section className="grid gap-5">
      <SectionHeader eyebrow="7 дней" title="Калорийный баланс" />
      {loading ? (
        <MutedLine>загружаю период</MutedLine>
      ) : days.length ? (
        <div className="grid gap-3">
          {summary && (
            <div className="flex flex-wrap gap-x-6 gap-y-2 text-[13px] text-[var(--muted)]">
              {summary.todayBalance != null && (
                <div>
                  сегодня:{" "}
                  <span
                    className={`font-mono ${
                      summary.todayBalance > 0 ? "text-[var(--accent)]" : ""
                    }`}
                  >
                    {summary.todayBalance > 0
                      ? `+${summary.todayBalance}`
                      : summary.todayBalance}
                  </span>{" "}
                  ккал
                </div>
              )}
              {summary.avgBalance != null && (
                <div>
                  в среднем:{" "}
                  <span className="font-mono">
                    {summary.avgBalance > 0
                      ? `+${summary.avgBalance}`
                      : summary.avgBalance}
                  </span>{" "}
                  ккал
                </div>
              )}
              <div>
                данные: еда {summary.foodDays}/{summary.totalDays} дн ·
                активность {summary.activityDays}/{summary.totalDays} дн
              </div>
            </div>
          )}
          <KcalChart dashboardDays={dashboardDays} days={days} />
        </div>
      ) : (
        <MutedLine>нет данных за период</MutedLine>
      )}
    </section>
  );
}

function KcalChart({
  dashboardDays,
  days,
}: {
  dashboardDays: DashboardDayResponse[];
  days: KcalBalanceDay[];
}) {
  const [hovered, setHovered] = useState<string | null>(null);

  const width = 900;
  const height = 260;
  const chartTop = 28;
  const chartBottom = 218;
  const step = width / days.length;
  const barWidth = Math.max(10, step * 0.4);
  const maxKcal = Math.max(
    ...days.map((d) => Math.max(d.kcal_in, d.tdee ?? 0)),
    1,
  );

  const mealCountByDate = new Map(
    dashboardDays.map((d) => [d.date, d.meal_count]),
  );

  return (
    <div className="relative">
      <svg
        aria-label="Калории: съедено и расход за последние 7 дней"
        className="h-[280px] w-full border-y border-[var(--hairline)] py-5"
        role="img"
        viewBox={`0 0 ${width} ${height}`}
        onMouseLeave={() => setHovered(null)}
      >
        <line
          stroke="var(--hairline)"
          x1="0"
          x2={width}
          y1={chartBottom}
          y2={chartBottom}
        />
        {/* Draw balance background first so it sits behind */}
        {days.map((day, index) => {
          const mealCount = mealCountByDate.get(day.date) ?? 0;
          if (mealCount === 0 || day.net_balance == null) return null;
          const groupX = index * step + (step - barWidth) / 2;
          const balanceHeight =
            (Math.abs(day.net_balance) / maxKcal) * (chartBottom - chartTop);
          const isSurplus = day.net_balance > 0;

          return (
            <rect
              key={`bal-${day.date}`}
              fill={isSurplus ? "var(--accent)" : "var(--muted)"}
              height={Math.max(1, balanceHeight)}
              opacity={0.15}
              width={barWidth + 20}
              x={groupX - 10}
              y={
                isSurplus
                  ? chartBottom - balanceHeight
                  : chartBottom - balanceHeight
              }
            />
          );
        })}

        {/* Draw intake and expenditure */}
        {days.map((day, index) => {
          const groupX = index * step + (step - barWidth) / 2;
          const mealCount = mealCountByDate.get(day.date) ?? 0;

          const inHeight = (day.kcal_in / maxKcal) * (chartBottom - chartTop);
          const inY = chartBottom - inHeight;

          const tdeeVal = day.tdee ?? 0;
          const tdeeHeight = (tdeeVal / maxKcal) * (chartBottom - chartTop);
          const tdeeY = chartBottom - tdeeHeight;

          return (
            <g key={day.date}>
              {/* Interactive invisible rect for hover */}
              <rect
                fill="transparent"
                height={chartBottom}
                width={step}
                x={index * step}
                y={0}
                onMouseEnter={() => setHovered(day.date)}
              />
              {/* Intake Bar */}
              {mealCount > 0 && day.kcal_in > 0 && (
                <rect
                  fill="var(--accent)"
                  height={Math.max(1, inHeight)}
                  opacity={0.9}
                  width={barWidth}
                  x={groupX}
                  y={inY}
                  style={{ pointerEvents: "none" }}
                />
              )}
              {/* Expenditure Line */}
              {tdeeVal > 0 && (
                <line
                  stroke="var(--muted)"
                  strokeWidth="2"
                  x1={index * step + step * 0.1}
                  x2={index * step + step * 0.9}
                  y1={tdeeY}
                  y2={tdeeY}
                  style={{ pointerEvents: "none" }}
                />
              )}
            </g>
          );
        })}

        {/* Legend */}
        <rect
          fill="var(--accent)"
          height="10"
          opacity={0.9}
          width="14"
          x="0"
          y={chartTop - 24}
        />
        <text fill="var(--fg)" fontSize="12" x="20" y={chartTop - 14}>
          съедено
        </text>
        <line
          stroke="var(--muted)"
          strokeWidth="2"
          x1="90"
          x2="104"
          y1={chartTop - 19}
          y2={chartTop - 19}
        />
        <text fill="var(--fg)" fontSize="12" x="110" y={chartTop - 14}>
          расход
        </text>
        <rect
          fill="var(--accent)"
          height="10"
          opacity={0.15}
          width="14"
          x="170"
          y={chartTop - 24}
        />
        <text fill="var(--fg)" fontSize="12" x="190" y={chartTop - 14}>
          профицит
        </text>
        <rect
          fill="var(--muted)"
          height="10"
          opacity={0.15}
          width="14"
          x="270"
          y={chartTop - 24}
        />
        <text fill="var(--fg)" fontSize="12" x="290" y={chartTop - 14}>
          дефицит
        </text>

        <text fill="var(--muted)" fontSize="11" x="0" y="250">
          {days[0]?.date.slice(5)}
        </text>
        <text
          fill="var(--muted)"
          fontSize="11"
          textAnchor="end"
          x={width}
          y="250"
        >
          {days[days.length - 1]?.date.slice(5)}
        </text>
      </svg>

      {/* Tooltip Overlay */}
      {hovered && (
        <ChartTooltip
          day={days.find((d) => d.date === hovered)!}
          mealCount={mealCountByDate.get(hovered) ?? 0}
        />
      )}
    </div>
  );
}

function ChartTooltip({
  day,
  mealCount,
}: {
  day: KcalBalanceDay;
  mealCount: number;
}) {
  // Since real BMR/Active breakdown isn't currently provided by KcalBalanceDay,
  // we do not show the breakdown unless it's available. If it becomes available,
  // it would be added here.
  return (
    <div className="pointer-events-none absolute right-0 top-0 z-10 grid min-w-[260px] gap-1 border border-[var(--hairline)] bg-[var(--surface)] p-4 text-[13px] shadow-lg">
      <div className="mb-1 font-bold">{day.date}</div>
      {mealCount === 0 ? (
        <div className="text-[var(--muted)]">нет записей еды</div>
      ) : (
        <>
          <div>
            Съедено:{" "}
            <span className="font-mono text-[var(--accent)]">
              {Math.round(day.kcal_in)}
            </span>{" "}
            ккал
          </div>
          <div>
            Расход:{" "}
            <span className="font-mono">
              {day.tdee ? Math.round(day.tdee) : "--"}
            </span>{" "}
            ккал
            {day.bmr_available && (
              <span className="ml-1 text-[var(--muted)]">
                (базовый учтен)
              </span>
            )}
          </div>
          {day.net_balance != null && (
            <div>
              Баланс:{" "}
              <span className="font-mono">
                {day.net_balance > 0
                  ? `+${Math.round(day.net_balance)}`
                  : Math.round(day.net_balance)}
              </span>{" "}
              ккал
            </div>
          )}
        </>
      )}
      <div className="mt-2 border-t border-[var(--hairline)] pt-2 text-[11px] text-[var(--muted)]">
        Данные: еда {mealCount > 0 ? "есть" : "нет"} · записей: {mealCount}
      </div>
    </div>
  );
}

function HeatmapSection({
  data,
  loading,
}: {
  data?: DashboardHeatmapResponse;
  loading: boolean;
}) {
  return (
    <section className="grid gap-5">
      <SectionHeader eyebrow="4 недели" title="Тепловая карта еды" />
      {loading ? (
        <MutedLine>загружаю тепловую карту</MutedLine>
      ) : (
        <HeatmapGrid cells={data?.cells ?? []} />
      )}
    </section>
  );
}

function HeatmapGrid({ cells }: { cells: DashboardHeatmapResponse["cells"] }) {
  const width = 520;
  const height = 230;
  const left = 34;
  const top = 18;
  const cell = 17;
  const gap = 3;
  const max = Math.max(...cells.map((entry) => entry.avg_carbs_g), 1);
  const byKey = new Map(
    cells.map((entry) => [`${entry.day_of_week}-${entry.hour}`, entry]),
  );
  const days = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"];

  return (
    <svg
      aria-label="Тепловая карта еды по дням и часам"
      className="h-[250px] w-full border-y border-[var(--hairline)] py-5"
      role="img"
      viewBox={`0 0 ${width} ${height}`}
    >
      {[0, 6, 12, 18, 23].map((hour) => (
        <text
          fill="var(--muted)"
          fontSize="10"
          key={hour}
          textAnchor="middle"
          x={left + hour * (cell + gap) + cell / 2}
          y="10"
        >
          {hour}
        </text>
      ))}
      {days.map((day, index) => (
        <text
          fill="var(--muted)"
          fontSize="11"
          key={`${day}-${index}`}
          textAnchor="end"
          x="24"
          y={top + index * (cell + gap) + 12}
        >
          {day}
        </text>
      ))}
      {Array.from({ length: 7 }, (_, day) =>
        Array.from({ length: 24 }, (_, hour) => {
          const entry = byKey.get(`${day}-${hour}`);
          const opacity = entry
            ? 0.16 + (entry.avg_carbs_g / max) * 0.72
            : 0.06;
          return (
            <rect
              data-testid="heatmap-cell"
              fill="var(--accent)"
              height={cell}
              key={`${day}-${hour}`}
              opacity={opacity}
              width={cell}
              x={left + hour * (cell + gap)}
              y={top + day * (cell + gap)}
            />
          );
        }),
      )}
    </svg>
  );
}

function TopPatterns({
  patterns,
}: {
  patterns: DashboardTopPatternResponse[];
}) {
  return (
    <section className="grid content-start gap-4 border-t border-[var(--hairline)] pt-5">
      <SectionHeader eyebrow="7 дней" title="Частые шаблоны" />
      {patterns.length ? (
        <div className="grid gap-0">
          {patterns.map((pattern) => (
            <div
              className="grid grid-cols-[1fr_auto] border-b border-[var(--hairline)] py-3"
              key={pattern.pattern_id}
            >
              <div>
                <div className="text-[15px] text-[var(--fg)]">
                  {pattern.display_name}
                </div>
                <div className="mt-1 font-mono text-[11px] uppercase text-[var(--muted)]">
                  {pattern.token}
                </div>
              </div>
              <div className="font-mono text-[20px]">{pattern.count}</div>
            </div>
          ))}
        </div>
      ) : (
        <MutedLine>шаблонов пока нет</MutedLine>
      )}
    </section>
  );
}

function SourceBreakdown({
  data,
}: {
  data?: DashboardSourceBreakdownResponse;
}) {
  const total = data?.items.reduce((sum, item) => sum + item.count, 0) ?? 0;

  return (
    <section className="grid content-start gap-4 border-t border-[var(--hairline)] pt-5">
      <SectionHeader eyebrow="7 дней" title="Источники данных" />
      {data?.items.length ? (
        <div className="grid gap-0">
          {data.items.map((item) => (
            <div
              className="grid grid-cols-[1fr_auto_auto] gap-4 border-b border-[var(--hairline)] py-3"
              key={item.source_kind}
            >
              <div className="text-[15px] text-[var(--fg)]">
                {sourceKindLabel(item.source_kind)}
              </div>
              <div className="font-mono text-[15px]">{item.count}</div>
              <div className="font-mono text-[15px] text-[var(--muted)]">
                {percent(item.count, total)}%
              </div>
            </div>
          ))}
        </div>
      ) : (
        <MutedLine>нет данных по источникам</MutedLine>
      )}
    </section>
  );
}

function DataQuality({ data }: { data?: DashboardDataQualityResponse }) {
  const rows = [
    ["точная этикетка", data?.exact_label_count ?? 0],
    ["этикетка с допущением", data?.assumed_label_count ?? 0],
    ["ресторанная база", data?.restaurant_db_count ?? 0],
    ["база продуктов", data?.product_db_count ?? 0],
    ["шаблон", data?.pattern_count ?? 0],
    ["оценка по фото", data?.visual_estimate_count ?? 0],
    ["вручную", data?.manual_count ?? 0],
    ["низкая уверенность", data?.low_confidence_count ?? 0],
  ] as const;

  return (
    <section className="grid content-start gap-4 border-t border-[var(--hairline)] pt-5">
      <SectionHeader eyebrow="7 дней" title="Качество данных" />
      <div className="grid grid-cols-2 gap-x-5 gap-y-3">
        {rows.map(([label, value]) => (
          <div
            className="grid grid-cols-[1fr_auto] border-b border-[var(--hairline)] pb-2"
            key={label}
          >
            <span className="text-[13px] text-[var(--fg)]">{label}</span>
            <span className="font-mono text-[15px]">{value}</span>
          </div>
        ))}
      </div>
      {data?.low_confidence_items.length ? (
        <div className="mt-2 grid gap-2">
          <div className="text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">
            позиции с низкой уверенностью
          </div>
          {data.low_confidence_items.map((item) => (
            <div
              className="grid grid-cols-[1fr_auto] border-b border-[var(--hairline)] py-2"
              key={item.item_id}
            >
              <span className="text-[13px]">{item.name}</span>
              <span className="font-mono text-[13px] text-[var(--muted)]">
                {item.confidence === null || item.confidence === undefined
                  ? "--"
                  : item.confidence.toFixed(2)}
              </span>
            </div>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function SectionHeader({ eyebrow, title }: { eyebrow: string; title: string }) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">
        {eyebrow}
      </div>
      <h2 className="mt-2 text-[22px] font-normal leading-none text-[var(--fg)]">
        {title}
      </h2>
    </div>
  );
}

function MutedLine({ children }: { children: string }) {
  return (
    <div className="border-y border-[var(--hairline)] py-6 text-[14px] text-[var(--muted)]">
      {children}
    </div>
  );
}
