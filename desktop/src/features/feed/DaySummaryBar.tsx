import type { FeedItem } from "./FeedPage.types";

export function DaySummaryBar({ items }: { items: FeedItem[] }) {
  const stats = computeDayStats(items);
  if (!stats.totalMeals && !stats.totalInsulin) return null;

  const parts: string[] = [];
  if (stats.totalMeals) {
    const word = stats.totalMeals === 1 ? "приём" : stats.totalMeals < 5 ? "приёма" : "приёмов";
    parts.push(`${stats.totalMeals} ${word}`);
  }
  if (stats.totalCarbs > 0) {
    parts.push(`${Math.round(stats.totalCarbs)} г углеводов`);
  }
  if (stats.totalKcal > 0) {
    parts.push(`${Math.round(stats.totalKcal)} ккал`);
  }
  if (stats.totalInsulin) {
    const word = stats.totalInsulin === 1 ? "событие" : stats.totalInsulin < 5 ? "события" : "событий";
    parts.push(`${stats.totalInsulin} NS-${word}`);
  }
  if (stats.hasCGM) {
    parts.push("CGM есть");
  }

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-[var(--hairline)] px-0 py-2 text-[12px] text-[var(--muted)]">
      {parts.map((part, i) => (
        <span key={i}>
          {i > 0 ? <span className="mr-4 text-[var(--hairline)]">·</span> : null}
          {part}
        </span>
      ))}
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
