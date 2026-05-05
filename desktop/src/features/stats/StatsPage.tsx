import { useMemo, type ReactNode } from "react";
import type {
  DashboardDataQualityResponse,
  DashboardDayResponse,
  DashboardHeatmapResponse,
  DashboardSourceBreakdownResponse,
  DashboardTodayResponse,
  KcalBalanceDay,
} from "../../api/client";
import {
  defaultDashboardRange,
  useDashboardDataQuality,
  useDashboardHeatmap,
  useDashboardRange,
  useDashboardSourceBreakdown,
  useDashboardToday,
  useKcalBalanceRange,
} from "./useDashboard";
import {
  formatGlucose,
  formatKcalValue,
  formatMacroValue,
  formatPercent,
  formatWeight,
  fmtSignedInt,
} from "../../utils/nutritionFormat";
import { useGlucoseDashboard } from "../glucose/useGlucoseDashboard";

const pad2 = (n: number) => n.toString().padStart(2, "0");
const range = defaultDashboardRange();

const COLOR_BELOW = "oklch(0.72 0.035 235)";
const COLOR_IN = "oklch(0.72 0.08 145)";
const COLOR_ABOVE = "oklch(0.78 0.09 65)";
const COLOR_GRAPHITE = "oklch(0.36 0.012 260)";

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));

const average = (values: number[]) =>
  values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0;

const hasTrackedNutritionDay = (day: DashboardDayResponse) =>
  day.meal_count > 0 ||
  [day.kcal, day.carbs_g, day.protein_g, day.fat_g, day.fiber_g].some(
    (value) => Number.isFinite(value) && value > 0,
  );

const hasTrackedBalanceDay = (day: KcalBalanceDay) =>
  day.kcal_in > 0;

const localDateKey = (date = new Date()) =>
  `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;

const isCurrentLocalDay = (date: string) => date === localDateKey();

const averageTdee = (days: KcalBalanceDay[]) => {
  const values = days
    .map((day) => day.tdee)
    .filter((value): value is number => Number.isFinite(value) && (value ?? 0) > 0);
  return values.length ? average(values) : 2200;
};

const balanceValue = (day: KcalBalanceDay, fallbackTdee: number) =>
  day.net_balance ?? day.kcal_in - (day.tdee ?? fallbackTdee);

const shortDay = (date: string) =>
  new Intl.DateTimeFormat("ru-RU", { day: "2-digit", month: "short" }).format(new Date(date));

const weekdayShort = (date: string) =>
  new Intl.DateTimeFormat("ru-RU", { weekday: "short" }).format(new Date(date)).slice(0, 2);

function heatColor(v: number) {
  if (v < 0.05) return "var(--shade)";
  return `oklch(${0.94 - v * 0.18} ${0.015 + v * 0.085} 78 / ${0.35 + v * 0.65})`;
}

type DaypartSummary = {
  key: string;
  range: string;
  avg: number | null;
  tir: number | null;
  count: number;
};

export function StatsPage() {
  const today = useDashboardToday();
  const rangeQuery = useDashboardRange(range.from, range.to);
  const heatmap = useDashboardHeatmap(4);
  const sourceBreakdown = useDashboardSourceBreakdown(7);
  const dataQuality = useDashboardDataQuality(7);
  const kcalBalance = useKcalBalanceRange(range.from, range.to);

  const glucoseFrom = useMemo(() => {
    const d = new Date();
    d.setDate(d.getDate() - 8);
    d.setHours(0, 0, 0, 0);
    return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}T00:00`;
  }, []);
  const glucoseTo = useMemo(() => {
    const d = new Date();
    return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}T23:59`;
  }, []);
  const glucoseDashboard = useGlucoseDashboard(glucoseFrom, glucoseTo, "raw");

  const noData =
    today.isSuccess &&
    rangeQuery.isSuccess &&
    heatmap.isSuccess &&
    sourceBreakdown.isSuccess &&
    dataQuality.isSuccess &&
    today.data?.meal_count === 0 &&
    rangeQuery.data?.summary.total_meals === 0 &&
    heatmap.data?.cells.length === 0 &&
    sourceBreakdown.data?.items.length === 0 &&
    dataQuality.data?.total_item_count === 0;

  const dateTitle = useMemo(() => {
    const d = new Date();
    return new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long", year: "numeric" }).format(d);
  }, []);

  const daysData = rangeQuery.data?.days ?? [];
  const kcalDays = kcalBalance.data?.days ?? [];
  const trackedKcalDays = kcalDays.filter(hasTrackedBalanceDay);
  const completedKcalDays = trackedKcalDays.filter((day) => !isCurrentLocalDay(day.date));
  const fallbackTdee = averageTdee(kcalDays);
  const cumDeficit = completedKcalDays.reduce((sum, day) => sum + balanceValue(day, fallbackTdee), 0);
  const periodBalanceLabel = cumDeficit > 0 ? "Профицит" : "Дефицит";
  const avgIntake = average(completedKcalDays.map((day) => day.kcal_in));
  const todayBalanceDay = kcalDays.find((day) => isCurrentLocalDay(day.date));
  const todayIntake = today.data?.kcal ?? todayBalanceDay?.kcal_in ?? 0;
  const todayBal = todayIntake > 0
    ? todayBalanceDay ? balanceValue(todayBalanceDay, fallbackTdee) : todayIntake - fallbackTdee
    : 0;
  const cgmPoints = glucoseDashboard.data?.points ?? [];

  const tirDays = useMemo(() => {
    const byDay = new Map<string, { below: number; inRange: number; above: number; total: number }>();
    cgmPoints.forEach((point) => {
      const day = point.timestamp.slice(0, 10);
      if (!byDay.has(day)) byDay.set(day, { below: 0, inRange: 0, above: 0, total: 0 });
      const entry = byDay.get(day)!;
      if (point.raw_value < 3.9) entry.below++;
      else if (point.raw_value <= 7.8) entry.inRange++;
      else entry.above++;
      entry.total++;
    });
    return Array.from(byDay.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .slice(-8)
      .map(([date, value]) => {
        const below = value.total ? Math.round(value.below / value.total * 100) : 0;
        const inRange = value.total ? Math.round(value.inRange / value.total * 100) : 0;
        return {
          date,
          d: shortDay(date),
          below,
          inRange,
          above: clamp(100 - below - inRange, 0, 100),
        };
      });
  }, [cgmPoints]);

  const dayparts: DaypartSummary[] = useMemo(() => {
    const groups = [
      { key: "00", range: "00–04", hStart: 0, hEnd: 4 },
      { key: "04", range: "04–08", hStart: 4, hEnd: 8 },
      { key: "08", range: "08–12", hStart: 8, hEnd: 12 },
      { key: "12", range: "12–16", hStart: 12, hEnd: 16 },
      { key: "16", range: "16–20", hStart: 16, hEnd: 20 },
      { key: "20", range: "20–24", hStart: 20, hEnd: 24 },
    ];
    return groups.map((group) => {
      const pts = cgmPoints.filter((point) => {
        const hour = new Date(point.timestamp).getHours();
        return hour >= group.hStart && hour < group.hEnd;
      });
      if (!pts.length) return { ...group, avg: null, tir: null, count: 0 };
      const avg = average(pts.map((point) => point.raw_value));
      const inRange = pts.filter((point) => point.raw_value >= 3.9 && point.raw_value <= 7.8).length;
      return {
        ...group,
        avg: Math.round(avg * 10) / 10,
        tir: Math.round(inRange / pts.length * 100),
        count: pts.length,
      };
    });
  }, [cgmPoints]);

  return (
    <div style={{ padding: "28px 40px 56px", minHeight: "100%" }}>
      {noData ? (
        <div style={{ display: "grid", minHeight: "52vh", placeItems: "center", fontSize: 15, color: "var(--ink-3)" }}>
          данных пока нет
        </div>
      ) : (
        <div>
          <div style={{ marginBottom: 24 }}>
            <div style={{ fontSize: 9, letterSpacing: "0.18em", textTransform: "uppercase", color: "var(--ink-4)", marginBottom: 6, fontWeight: 500 }}>
              статистика
            </div>
            <h1 style={{ fontFamily: "var(--serif)", fontSize: 30, fontWeight: 400, margin: 0, lineHeight: 1.1 }}>
              {dateTitle}
            </h1>
            <h2 style={{ fontFamily: "var(--serif)", fontSize: 26, fontWeight: 400, margin: "4px 0 6px", lineHeight: 1.2 }}>
              {periodBalanceLabel} <span style={{ fontFamily: "var(--mono)", color: "var(--ink)" }}>{formatKcalValue(Math.abs(cumDeficit))}</span> ккал за завершённые дни
            </h2>
            <div style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--ink-3)", display: "flex", gap: 18, flexWrap: "wrap" }}>
              <span><span style={{ color: "var(--ink-4)" }}>среднее</span> <b style={{ color: "var(--ink)" }}>{formatKcalValue(avgIntake)}</b> ккал/день</span>
              <span style={{ color: "var(--hairline-2)" }}>·</span>
              <span><span style={{ color: "var(--ink-4)" }}>сегодня</span> <b style={{ color: "var(--ink)" }}>{formatKcalValue(todayIntake)}</b></span>
              <span style={{ color: "var(--hairline-2)" }}>·</span>
              <span><span style={{ color: "var(--ink-4)" }}>баланс</span> <b style={{ color: "var(--ink)" }}>{fmtSignedInt(todayBal)}</b></span>
              <span style={{ color: "var(--hairline-2)" }}>·</span>
              <span><span style={{ color: "var(--ink-4)" }}>расчётно</span> <b style={{ color: "var(--ink)" }}>{formatWeight(Math.abs(cumDeficit) / 7700)} кг</b></span>
            </div>
          </div>

          <KpiCards today={today.data} kcalDays={kcalDays} />

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginBottom: 14 }}>
            <CarbsCard days={daysData} />
            <BalanceCard kcalDays={kcalDays} />
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginBottom: 14 }}>
            <TirCard tirDays={tirDays} />
            <DaypartCard dayparts={dayparts} />
          </div>

          <HeatmapCard data={heatmap.data} loading={heatmap.isLoading} />

          <FooterRow
            sourceBreakdown={sourceBreakdown.data}
            dataQuality={dataQuality.data}
            hoursSinceLastMeal={today.data?.hours_since_last_meal}
            mealCount={today.data?.meal_count}
          />
        </div>
      )}
    </div>
  );
}

function Card({
  title,
  headerRight,
  children,
  bodyPad = "14px 18px 18px",
}: {
  title: ReactNode;
  headerRight?: ReactNode;
  children: ReactNode;
  bodyPad?: string;
}) {
  return (
    <div style={{ background: "var(--surface-2)", border: "1px solid var(--hairline)", borderRadius: "var(--radius-lg)", display: "flex", flexDirection: "column" }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", padding: "12px 18px 0", gap: 12 }}>
        <div style={{ fontFamily: "var(--serif)", fontSize: 14, fontWeight: 500, color: "var(--ink)" }}>{title}</div>
        {headerRight ? (
          <div style={{ fontFamily: "var(--mono)", fontSize: 9, letterSpacing: "0.14em", textTransform: "uppercase", color: "var(--ink-4)" }}>{headerRight}</div>
        ) : null}
      </div>
      <div style={{ padding: bodyPad }}>{children}</div>
    </div>
  );
}

function SummaryMetric({ label, value, tone = "ink" }: { label: string; value: string; tone?: "ink" | "warn" | "good" }) {
  return (
    <div style={{ border: "1px solid var(--hairline)", background: "var(--surface)", borderRadius: 6, padding: "10px 12px" }}>
      <div className="mono" style={{ fontSize: 19, lineHeight: 1, color: tone === "warn" ? "var(--warn)" : tone === "good" ? "var(--good)" : "var(--ink)" }}>
        {value}
      </div>
      <div style={{ fontSize: 10, color: "var(--ink-3)", marginTop: 5 }}>{label}</div>
    </div>
  );
}

function KpiCards({ today, kcalDays }: { today?: DashboardTodayResponse; kcalDays: KcalBalanceDay[] }) {
  const todayCarbs = today?.carbs_g ?? 0;
  const todayKcal = today?.kcal ?? 0;
  const weekAvgCarbs = today?.week_avg_carbs ?? 0;
  const tdee = averageTdee(kcalDays);
  const protein = today?.protein_g ?? 0;
  const fat = today?.fat_g ?? 0;
  const fiber = today?.fiber_g ?? 0;
  const hasMacros = [todayCarbs, protein, fat, fiber].some((value) => value > 0);

  const kpis = [
    {
      lbl: "Углеводы",
      val: formatMacroValue(todayCarbs),
      u: "г",
      sub: `сред. за 7 дн. ${formatMacroValue(weekAvgCarbs)} г · лим. 312 г`,
      pct: todayCarbs / 312,
      color: "var(--accent)",
    },
    {
      lbl: "Ккал",
      val: formatKcalValue(todayKcal),
      u: "",
      sub: `цель: 2200 · TDEE ${formatKcalValue(tdee)}`,
      pct: todayKcal / 2200,
      color: "var(--good)",
    },
    {
      lbl: "ГН",
      val: "38",
      u: "",
      sub: "норма < 100 / день · сред. 72",
      pct: 38 / 100,
      color: "var(--ink)",
    },
    {
      lbl: "БЖУ-баланс",
      val: hasMacros ? `Б ${formatMacroValue(protein)} · Ж ${formatMacroValue(fat)}` : "нет цели",
      u: "",
      sub: hasMacros
        ? `У ${formatMacroValue(todayCarbs)} г · клетч. ${formatMacroValue(fiber)} г`
        : "цели макросов не заданы",
      pct: null,
      color: "var(--ink)",
      valueSize: hasMacros ? 17 : 18,
    },
  ];

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 16 }}>
      {kpis.map((kpi) => (
        <div key={kpi.lbl} style={{ background: "var(--surface-2)", border: "1px solid var(--hairline)", borderRadius: "var(--radius-lg)", padding: "12px 16px 14px" }}>
          <div style={{ fontSize: 9, letterSpacing: "0.16em", textTransform: "uppercase", color: "var(--ink-4)", fontWeight: 500, marginBottom: 6 }}>{kpi.lbl}</div>
          <div style={{ fontFamily: "var(--mono)", fontSize: kpi.valueSize ?? 30, fontWeight: 500, lineHeight: 1, color: kpi.color }}>
            {kpi.val}{kpi.u ? <span style={{ fontSize: 11, color: "var(--ink-3)", marginLeft: 3 }}>{kpi.u}</span> : null}
          </div>
          <div style={{ height: 2, background: "var(--hairline)", marginTop: 10, marginBottom: 10 }}>
            {kpi.pct !== null ? <div style={{ height: "100%", width: `${clamp(kpi.pct * 100, 0, 100)}%`, background: kpi.color }} /> : null}
          </div>
          <div style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--ink-3)", lineHeight: 1.5 }}>{kpi.sub}</div>
        </div>
      ))}
    </div>
  );
}

function CarbsCard({ days }: { days: DashboardDayResponse[] }) {
  const validDays = days.filter(hasTrackedNutritionDay);
  const chartDays = validDays.length < 14 ? validDays : days;
  const carbsAvg = average(validDays.map((day) => day.carbs_g));
  const maxCarbs = Math.max(...validDays.map((day) => day.carbs_g), 0);

  if (validDays.length < 3) {
    return (
      <Card title="Углеводы (г) по дням" headerRight={`${validDays.length} дн.`}>
        {validDays.length === 0 ? (
          <div style={{ fontSize: 13, color: "var(--ink-3)", padding: "18px 0" }}>Нет дней с питанием за период</div>
        ) : (
          <div style={{ display: "grid", gap: 14 }}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10 }}>
              <SummaryMetric label="дней с едой" value={formatKcalValue(validDays.length)} />
              <SummaryMetric label="сред. углеводы" value={`${formatMacroValue(carbsAvg)} г`} />
              <SummaryMetric label="макс. углеводы" value={`${formatMacroValue(maxCarbs)} г`} />
            </div>
            <div style={{ display: "grid", gap: 7 }}>
              {validDays.map((day) => (
                <div key={day.date} style={{ display: "grid", gridTemplateColumns: "72px 1fr auto", alignItems: "center", gap: 10, fontSize: 12 }}>
                  <span className="mono" style={{ color: "var(--ink-3)" }}>{shortDay(day.date)}</span>
                  <span style={{ height: 3, background: "var(--hairline)", borderRadius: 2, overflow: "hidden" }}>
                    <span style={{ display: "block", height: "100%", width: `${maxCarbs ? Math.max(4, day.carbs_g / maxCarbs * 100) : 0}%`, background: "oklch(0.82 0.08 78)" }} />
                  </span>
                  <span className="mono">{formatMacroValue(day.carbs_g)} г</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </Card>
    );
  }

  const W = 480, H = 200;
  const pL = 32, pR = 12, pT = 16, pB = 28;
  const iW = W - pL - pR, iH = H - pT - pB;
  const N = chartDays.length;
  const bw = iW / Math.max(N, 1);
  const yMax = Math.max(100, Math.ceil(Math.max(...chartDays.map((day) => day.carbs_g), carbsAvg, 1) / 50) * 50);
  const ticks = [0, yMax / 2, yMax];
  const avgY = pT + iH - (carbsAvg / yMax) * iH;

  return (
    <Card title="Углеводы (г) по дням" headerRight={validDays.length < 14 ? "дни с едой" : "период"}>
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} style={{ display: "block", width: "100%", height: "auto" }}>
        {ticks.map((tick) => {
          const y = pT + iH - (tick / yMax) * iH;
          return (
            <g key={tick}>
              <line x1={pL} x2={W - pR} y1={y} y2={y} stroke="var(--hairline)" strokeWidth="1" strokeDasharray={tick === 0 ? undefined : "2 3"} opacity={tick === 0 ? 1 : 0.6} />
              <text x={pL - 6} y={y + 3} textAnchor="end" fontFamily="var(--mono)" fontSize="9" fill="var(--ink-4)">{formatMacroValue(tick)}</text>
            </g>
          );
        })}
        {chartDays.map((day, index) => {
          const value = day.carbs_g;
          const height = value === 0 ? 0 : Math.max(1.5, (value / yMax) * iH);
          const barW = Math.min(26, bw * 0.62);
          const x = pL + index * bw + bw / 2 - barW / 2;
          const isToday = index === N - 1;
          const fill = value === 0 ? "var(--hairline)" : isToday ? "oklch(0.78 0.10 75)" : "oklch(0.85 0.07 78)";
          return <rect key={day.date} x={x} y={pT + iH - height} width={barW} height={height} fill={fill} />;
        })}
        <line x1={pL} x2={W - pR} y1={avgY} y2={avgY} stroke="var(--accent)" strokeDasharray="4 4" strokeWidth="1" />
        {chartDays.length > 0 ? (
          <>
            <text x={pL + 6} y={pT + iH + 18} fontFamily="var(--mono)" fontSize="9" fill="var(--ink-4)">{shortDay(chartDays[0]!.date)}</text>
            <text x={W - pR - 4} y={pT + iH + 18} textAnchor="end" fontFamily="var(--mono)" fontSize="9" fill="var(--ink-4)">{shortDay(chartDays[chartDays.length - 1]!.date)}</text>
          </>
        ) : null}
      </svg>
    </Card>
  );
}

function BalanceCard({ kcalDays }: { kcalDays: KcalBalanceDay[] }) {
  const validDays = kcalDays.filter(hasTrackedBalanceDay);
  const completedDays = validDays.filter((day) => !isCurrentLocalDay(day.date));
  const todayDay = validDays.find((day) => isCurrentLocalDay(day.date));
  const fallbackTdee = averageTdee(kcalDays);
  const balances = completedDays.map((day) => balanceValue(day, fallbackTdee));

  if (completedDays.length < 3) {
    const total = balances.reduce((sum, value) => sum + value, 0);
    return (
      <Card title="Баланс калорий (ккал)" headerRight="без сегодня · TDEE">
        {completedDays.length === 0 ? (
          <div style={{ display: "grid", gap: 10, fontSize: 13, color: "var(--ink-3)", padding: "18px 0" }}>
            <span>Нет завершённых дней с калориями за период</span>
            {todayDay ? <span className="mono">Сегодня: {formatKcalValue(todayDay.kcal_in)} ккал, не входит в расчёт</span> : null}
          </div>
        ) : (
          <div style={{ display: "grid", gap: 14 }}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10 }}>
              <SummaryMetric label="завершённых дней" value={formatKcalValue(completedDays.length)} />
              <SummaryMetric label="итог" value={`${fmtSignedInt(total)} ккал`} tone={total > 0 ? "warn" : "good"} />
              <SummaryMetric label="сред. TDEE" value={formatKcalValue(fallbackTdee)} />
            </div>
            <div style={{ display: "grid", gap: 7 }}>
              {completedDays.map((day) => {
                const balance = balanceValue(day, fallbackTdee);
                return (
                  <div key={day.date} style={{ display: "grid", gridTemplateColumns: "72px 1fr auto", alignItems: "center", gap: 10, fontSize: 12 }}>
                    <span className="mono" style={{ color: "var(--ink-3)" }}>{shortDay(day.date)}</span>
                    <span style={{ color: "var(--ink-3)" }}>относительно TDEE</span>
                    <span className="mono" style={{ color: balance > 0 ? "var(--warn)" : "var(--good)" }}>{fmtSignedInt(balance)} ккал</span>
                  </div>
                );
              })}
              {todayDay ? (
                <div style={{ display: "grid", gridTemplateColumns: "72px 1fr auto", alignItems: "center", gap: 10, fontSize: 12, color: "var(--ink-3)" }}>
                  <span className="mono">{shortDay(todayDay.date)}</span>
                  <span>сегодня · не входит в расчёт</span>
                  <span className="mono">{formatKcalValue(todayDay.kcal_in)} ккал</span>
                </div>
              ) : null}
            </div>
          </div>
        )}
      </Card>
    );
  }

  const chartDays = validDays.length < 14 ? validDays : validDays.slice(-7);
  const chartBalances = chartDays.map((day) => balanceValue(day, fallbackTdee));
  const scaleBalances = chartDays.filter((day) => !isCurrentLocalDay(day.date)).map((day) => balanceValue(day, fallbackTdee));
  const absValues = (scaleBalances.length ? scaleBalances : chartBalances).map(Math.abs).sort((a, b) => a - b);
  const softCap = Math.max(350, (absValues[Math.max(0, Math.floor((absValues.length - 1) * 0.75))] ?? 0) * 1.45);
  const rawMax = Math.max(...absValues, 1);
  const maxAbs = Math.max(350, Math.ceil(Math.min(rawMax, softCap) / 250) * 250);
  const W = 480, H = 200;
  const pL = 34, pR = 12, pT = 18, pB = 32;
  const iW = W - pL - pR, iH = H - pT - pB;
  const zeroY = pT + iH / 2;
  const bw = iW / Math.max(chartDays.length, 1);
  const halfH = iH / 2 - 16;

  return (
    <Card title="Баланс калорий (ккал)" headerRight="относительно TDEE">
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} style={{ display: "block", width: "100%", height: "auto" }}>
        <line x1={pL} x2={W - pR} y1={zeroY} y2={zeroY} stroke="var(--ink-3)" strokeWidth="1" />
        <text x={pL - 6} y={zeroY - 4} textAnchor="end" fontFamily="var(--mono)" fontSize="9" fill="var(--ink-3)">TDEE</text>
        {chartDays.map((day, index) => {
          const balance = balanceValue(day, fallbackTdee);
          const displayBalance = clamp(balance, -maxAbs, maxAbs);
          const height = Math.max(1.5, Math.abs(displayBalance) / maxAbs * halfH);
          const barW = Math.min(34, bw * 0.48);
          const cx = pL + index * bw + bw / 2;
          const x = cx - barW / 2;
          const y = balance >= 0 ? zeroY - height : zeroY;
          const isToday = index === chartDays.length - 1;
          const fill = isToday ? COLOR_GRAPHITE : balance < 0 ? "oklch(0.78 0.05 145)" : "oklch(0.78 0.06 60)";
          const labelInside = height > 18;
          const labelY = balance >= 0
            ? labelInside ? y + 12 : Math.max(pT + 9, y - 4)
            : labelInside ? y + height - 5 : Math.min(pT + iH - 2, y + height + 11);
          const labelFill = labelInside && isToday ? "var(--ink-fg)" : "var(--ink-2)";
          const clipped = Math.abs(balance) > maxAbs;
          return (
            <g key={day.date}>
              <rect x={x} y={y} width={barW} height={height} fill={fill}>
                <title>{shortDay(day.date)} · {fmtSignedInt(balance)} ккал относительно TDEE</title>
              </rect>
              {clipped ? <line x1={x} x2={x + barW} y1={balance >= 0 ? y - 4 : y + height + 4} y2={balance >= 0 ? y - 4 : y + height + 4} stroke={fill} strokeWidth="1.5" /> : null}
              <text x={cx} y={labelY} textAnchor="middle" fontFamily="var(--mono)" fontSize="10" fill={labelFill} fontWeight={500}>
                {fmtSignedInt(balance)}
              </text>
              <text x={cx} y={H - 10} textAnchor="middle" fontFamily="var(--sans)" fontSize="11" fill={isToday ? COLOR_GRAPHITE : "var(--ink-3)"} fontWeight={isToday ? 600 : 400}>
                {weekdayShort(day.date)}
              </text>
            </g>
          );
        })}
      </svg>
    </Card>
  );
}

function TirCard({ tirDays }: { tirDays: Array<{ date: string; d: string; below: number; inRange: number; above: number }> }) {
  const W = 520, H = 280;
  const pL = 36, pR = 12, pT = 14, pB = 28;
  const iW = W - pL - pR, iH = H - pT - pB;
  const bw = iW / Math.max(tirDays.length, 1);
  const ticks = [0, 50, 100];

  if (!tirDays.length) {
    return (
      <Card title="Время в диапазоне (TIR)" bodyPad="14px 18px 18px">
        <div style={{ fontSize: 13, color: "var(--ink-3)" }}>Нет данных глюкозы за период</div>
      </Card>
    );
  }

  return (
    <Card title="Время в диапазоне (TIR)" bodyPad="6px 18px 14px">
      <div style={{ fontSize: 11, color: "var(--ink-3)", lineHeight: 1.4, marginBottom: 10 }}>
        Последние дни · шкала 0–100%.
      </div>
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} style={{ display: "block", width: "100%", height: "auto" }}>
        {ticks.map((tick) => {
          const y = pT + iH - (tick / 100) * iH;
          return (
            <g key={tick}>
              <line x1={pL} x2={W - pR} y1={y} y2={y} stroke="var(--hairline)" strokeWidth="1" opacity={tick === 0 ? 1 : 0.55} />
              <text x={pL - 6} y={y + 3} textAnchor="end" fontFamily="var(--mono)" fontSize="9" fill="var(--ink-4)">{tick}%</text>
            </g>
          );
        })}
        {tirDays.map((day, index) => {
          const cx = pL + index * bw + bw / 2;
          const barW = Math.min(34, bw * 0.55);
          const x = cx - barW / 2;
          const belowH = day.below / 100 * iH;
          const inH = day.inRange / 100 * iH;
          const aboveH = day.above / 100 * iH;
          const belowY = pT + iH - belowH;
          const inY = belowY - inH;
          const aboveY = inY - aboveH;
          const showLabel = tirDays.length <= 5 || index % 2 === 0 || index === tirDays.length - 1;
          const tip = `${day.d}\nв диапазоне ${formatPercent(day.inRange)}% · ниже ${formatPercent(day.below)}% · выше ${formatPercent(day.above)}%`;
          return (
            <g key={day.date}>
              <rect x={x} y={belowY} width={barW} height={belowH} fill={COLOR_BELOW}><title>{tip}</title></rect>
              <rect x={x} y={inY} width={barW} height={inH} fill={COLOR_IN}><title>{tip}</title></rect>
              <rect x={x} y={aboveY} width={barW} height={aboveH} fill={COLOR_ABOVE}><title>{tip}</title></rect>
              <rect x={x} y={pT} width={barW} height={iH} fill="transparent" style={{ cursor: "help" }}><title>{tip}</title></rect>
              {showLabel ? <text x={cx} y={pT + iH + 14} textAnchor="middle" fontFamily="var(--mono)" fontSize="9" fill="var(--ink-4)">{day.d}</text> : null}
            </g>
          );
        })}
        <line x1={pL} x2={W - pR} y1={pT + iH - 70 / 100 * iH} y2={pT + iH - 70 / 100 * iH} stroke="var(--good)" strokeDasharray="4 3" strokeWidth="1" opacity="0.7" />
        <text x={W - pR - 4} y={pT + iH - 70 / 100 * iH - 3} textAnchor="end" fontFamily="var(--mono)" fontSize="9" fill="var(--good)">цель ≥70%</text>
      </svg>
      <div style={{ display: "flex", gap: 18, marginTop: 6, fontSize: 11, color: "var(--ink-3)", flexWrap: "wrap" }}>
        <LegendDot color={COLOR_BELOW} label="Ниже диапазона" />
        <LegendDot color={COLOR_IN} label="В диапазоне" />
        <LegendDot color={COLOR_ABOVE} label="Выше диапазона" />
      </div>
    </Card>
  );
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
      <span style={{ width: 8, height: 8, borderRadius: "50%", background: color, display: "inline-block" }} />
      {label}
    </span>
  );
}

function DaypartCard({ dayparts }: { dayparts: DaypartSummary[] }) {
  return (
    <Card title="Профиль по времени суток (ср. за 7 дней)">
      <div style={{ display: "grid", gridTemplateColumns: "repeat(6, minmax(0, 1fr))", gap: 8 }}>
        {dayparts.map((daypart) => {
          const hasData = daypart.avg !== null;
          const warm = hasData && (daypart.tir ?? 0) < 60;
          const bg = !hasData ? "var(--surface)" : warm ? "oklch(0.96 0.03 75)" : "oklch(0.96 0.025 145)";
          const border = !hasData ? "var(--hairline)" : warm ? "oklch(0.88 0.045 75)" : "oklch(0.88 0.04 145)";
          return (
            <div key={daypart.key} style={{ background: bg, border: `1px solid ${border}`, borderRadius: "var(--radius-lg)", padding: "10px 8px 12px", textAlign: "center", minWidth: 0 }}>
              <div style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--ink-3)", marginBottom: 6, letterSpacing: "0.02em" }}>{daypart.range}</div>
              <div style={{ fontFamily: "var(--mono)", fontSize: 22, fontWeight: 500, lineHeight: 1, color: hasData ? "var(--ink)" : "var(--ink-4)" }}>
                {hasData ? formatGlucose(daypart.avg) : "—"}
              </div>
              <div style={{ fontSize: 10, color: "var(--ink-3)", marginTop: 2 }}>{hasData ? "ммоль/л" : "нет данных"}</div>
              <div style={{ fontFamily: "var(--mono)", fontSize: 10, color: hasData ? warm ? "var(--warn)" : "var(--good)" : "var(--ink-4)", marginTop: 6, fontWeight: 500 }}>
                {hasData ? `TIR ${formatPercent(daypart.tir)}%` : `${daypart.count} точек`}
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

function HeatmapCard({ data, loading }: { data?: DashboardHeatmapResponse; loading: boolean }) {
  const cells = data?.cells ?? [];
  const cols = ["00–04", "04–08", "08–12", "12–16", "16–20", "20–24"];
  const rows = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
  const cellMap = new Map(cells.map((cell) => [`${cell.day_of_week}:${cell.hour}`, cell.avg_carbs_g]));
  const heatmap6x7: number[][] = Array.from({ length: 7 }, (_, rowIndex) =>
    Array.from({ length: 6 }, (_, colIndex) => {
      let sum = 0;
      for (let hour = colIndex * 4; hour < (colIndex + 1) * 4; hour++) {
        sum += cellMap.get(`${rowIndex}:${hour}`) ?? 0;
      }
      return sum;
    }),
  );
  const maxVal = Math.max(...heatmap6x7.flat(), 1);

  return (
    <Card title="Тепловая карта питания (6×7)" bodyPad="6px 18px 18px">
      <div style={{ fontSize: 11, color: "var(--ink-3)", marginBottom: 12, lineHeight: 1.4 }}>
        Каждая ячейка: один 4-часовой блок.
      </div>
      {loading ? (
        <div style={{ fontSize: 13, color: "var(--ink-3)", padding: "20px 0" }}>загружаю тепловую карту</div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 220px", gap: 28, alignItems: "start" }}>
          <div>
            <div style={{ display: "grid", gridTemplateColumns: "28px repeat(6, 1fr)", gap: 4, marginBottom: 4 }}>
              <div />
              {cols.map((col) => <div key={col} style={{ fontFamily: "var(--mono)", fontSize: 9, color: "var(--ink-4)", textAlign: "center", letterSpacing: "0.04em" }}>{col}</div>)}
            </div>
            {rows.map((row, rowIndex) => {
              const isWeekend = rowIndex >= 5;
              return (
                <div key={row} style={{ display: "grid", gridTemplateColumns: "28px repeat(6, 1fr)", gap: 4, marginBottom: 4 }}>
                  <div style={{ fontFamily: "var(--mono)", fontSize: 10, color: isWeekend ? "var(--accent)" : "var(--ink-4)", fontStyle: isWeekend ? "italic" : "normal", display: "flex", alignItems: "center" }}>{row}</div>
                  {heatmap6x7[rowIndex]!.map((value, colIndex) => {
                    const normV = value / maxVal;
                    return (
                      <div
                        key={cols[colIndex]}
                        style={{ height: 22, background: heatColor(normV), borderRadius: 2, cursor: "help" }}
                        title={`${row} · ${cols[colIndex]}\n~${formatMacroValue(value)} г углеводов`}
                      />
                    );
                  })}
                </div>
              );
            })}
          </div>
          <div>
            <div style={{ fontSize: 11, color: "var(--ink-2)", fontWeight: 500, marginBottom: 8 }}>Интенсивность приёмов пищи</div>
            <div style={{ height: 10, borderRadius: 2, background: `linear-gradient(90deg, ${heatColor(0.05)}, ${heatColor(0.5)}, ${heatColor(0.95)})`, marginBottom: 6 }} />
            <div style={{ display: "flex", justifyContent: "space-between", fontFamily: "var(--mono)", fontSize: 10, color: "var(--ink-4)", marginBottom: 14 }}>
              <span>низкая</span><span>высокая</span>
            </div>
            <div style={{ fontSize: 10, color: "var(--ink-3)", lineHeight: 1.5 }}>
              Больше цвета = больше еды или углеводов в этот 4-часовой блок.
            </div>
          </div>
        </div>
      )}
    </Card>
  );
}

function FooterRow({
  sourceBreakdown,
  dataQuality,
  hoursSinceLastMeal,
  mealCount,
}: {
  sourceBreakdown?: DashboardSourceBreakdownResponse;
  dataQuality?: DashboardDataQualityResponse;
  hoursSinceLastMeal?: number | null;
  mealCount?: number;
}) {
  const total = sourceBreakdown?.items.reduce((sum, item) => sum + item.count, 0) ?? 0;
  const lowConfCount = dataQuality?.low_confidence_count ?? 0;

  return (
    <div style={{ marginTop: 18, paddingTop: 14, borderTop: "1px solid var(--hairline)", display: "grid", gridTemplateColumns: "1fr 1fr", gap: 36 }}>
      <FooterGroup title="Качество и полнота данных" items={[
        { v: total > 0 ? `${formatPercent((total - lowConfCount) / total * 100)}%` : "—", l: "с этикеткой", tone: "ink" as const },
        { v: `${dataQuality?.product_db_count ?? 0} из 18`, l: "баз заполнено", tone: "ink" as const },
        { v: `${dataQuality?.manual_count ?? 0}`, l: "вручную добавлено", tone: "ink" as const },
        { v: `${lowConfCount}`, l: "низкой уверенности", tone: "warn" as const },
      ]} />
      <FooterGroup title="Контекст дня и поведение" items={[
        { v: hoursSinceLastMeal != null ? (hoursSinceLastMeal < 1 ? "<1 ч" : `${formatKcalValue(hoursSinceLastMeal)} ч`) : "—", l: "с последней еды", tone: "ink" as const },
        { v: `${mealCount ?? "—"}`, l: "записей сегодня", tone: "ink" as const },
      ]} />
    </div>
  );
}

function FooterGroup({ title, items }: { title: string; items: Array<{ v: string; l: string; tone: "ink" | "warn" }> }) {
  return (
    <div>
      <div style={{ fontSize: 9, letterSpacing: "0.16em", textTransform: "uppercase", color: "var(--ink-4)", marginBottom: 10, fontWeight: 500 }}>{title}</div>
      <div style={{ display: "flex", gap: 20, flexWrap: "wrap" }}>
        {items.map((item, index) => (
          <div key={`${item.l}-${index}`} style={{ display: "flex", flexDirection: "column", paddingRight: 18, borderRight: index === items.length - 1 ? "none" : "1px solid var(--hairline)", minWidth: 78 }}>
            <div style={{ fontFamily: "var(--mono)", fontSize: 14, fontWeight: 500, color: item.tone === "warn" ? "var(--warn)" : "var(--ink)" }}>{item.v}</div>
            <div style={{ fontSize: 10, color: "var(--ink-3)", marginTop: 2, lineHeight: 1.4 }}>{item.l}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
