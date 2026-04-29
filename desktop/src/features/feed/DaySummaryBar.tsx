import type { FeedItem } from "./FeedPage.types";

export function DaySummaryBar({ items }: { items: FeedItem[] }) {
  const stats = computeDayStats(items);
  if (!stats.totalMeals && !stats.totalInsulin) return null;

  const cells: { label: string; value: string }[] = [];
  if (stats.totalMeals) {
    cells.push({ label: "приёмов", value: String(stats.totalMeals) });
  }
  if (stats.totalCarbs > 0) {
    cells.push({ label: "углеводы", value: `${Math.round(stats.totalCarbs)} г` });
  }
  if (stats.totalKcal > 0) {
    cells.push({ label: "ккал", value: String(Math.round(stats.totalKcal)) });
  }
  if (stats.totalInsulin) {
    cells.push({ label: "NS-события", value: String(stats.totalInsulin) });
  }

  return (
    <div className="flex items-stretch border-b border-[var(--hairline)]">
      {cells.map((cell, i) => (
        <div
          className="flex items-baseline gap-2 border-r border-[var(--hairline)] px-4 py-2 last:border-r-0"
          key={i}
        >
          <span className="font-mono text-[18px] leading-none text-[var(--fg)]">{cell.value}</span>
          <span className="text-[10px] uppercase tracking-[0.06em] text-[var(--muted)]">{cell.label}</span>
        </div>
      ))}
      {stats.hasCGM ? (
        <div className="flex items-center px-4 py-2 text-[10px] uppercase tracking-[0.06em] text-[var(--ok)]">
          CGM
        </div>
      ) : null}
    </div>
  );
}

function computeDayStats(items: FeedItem[]) {
  let totalMeals = 0;
  let totalCarbs = 0;
  let totalKcal = 0;
  let totalInsulin = 0;
  let hasCGM = false;

  for (const item of items) {
    if (item.kind === "meal") {
      totalMeals++;
      totalCarbs += item.meal.total_carbs_g;
      totalKcal += item.meal.total_kcal;
    } else if (item.kind === "episode") {
      totalMeals += item.episode.meals.length;
      totalCarbs += item.episode.total_carbs_g;
      totalKcal += item.episode.total_kcal;
      totalInsulin += (item.episode.insulin ?? []).length;
      if ((item.episode.glucose ?? []).length > 0) hasCGM = true;
    } else if (item.kind === "insulin") {
      totalInsulin++;
    }
  }

  return { totalMeals, totalCarbs, totalKcal, totalInsulin, hasCGM };
}
