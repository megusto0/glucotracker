import { useEffect, useState } from "react";
import { apiClient, type KcalBalanceResponse } from "../../api/client";
import { useApiConfig } from "../settings/settingsStore";
import type { FeedItem } from "./FeedPage.types";
import { isValidCGM } from "./cgmUtils";

export function DaySummaryBar({
  date,
  items,
}: {
  date: string;
  items: FeedItem[];
}) {
  const stats = computeDayStats(items);
  if (!stats.totalMeals && !stats.totalInsulin) return null;

  const config = useApiConfig();
  const [balance, setBalance] = useState<KcalBalanceResponse | null>(null);

  useEffect(() => {
    if (!config.token.trim() || !date) return;
    apiClient
      .getKcalBalance(config, date)
      .then(setBalance)
      .catch(() => setBalance(null));
  }, [config.token, config.baseUrl, date]);

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

  const netBalance = balance?.net_balance;
  const tdee = balance?.tdee;
  const steps = balance?.steps ?? 0;

  return (
    <div className="flex items-stretch border-b border-[var(--hairline)]">
      {cells.map((cell, i) => (
        <div
          className="flex items-baseline gap-2 border-r border-[var(--hairline)] px-4 py-2 last:border-r-0"
          key={i}
        >
          <span className="font-mono text-[18px] leading-none text-[var(--fg)]">
            {cell.value}
          </span>
          <span className="text-[10px] uppercase tracking-[0.06em] text-[var(--muted)]">
            {cell.label}
          </span>
        </div>
      ))}
      {balance?.bmr_available && netBalance != null ? (
        <div className="flex items-stretch">
          <div className="flex items-baseline gap-2 border-r border-[var(--hairline)] px-4 py-2">
            <span className="font-mono text-[14px] leading-none text-[var(--muted)]">
              TDEE {tdee ?? "—"}
            </span>
          </div>
          <div className="flex items-baseline gap-2 border-r border-[var(--hairline)] px-4 py-2">
            <span className="text-[10px] uppercase tracking-[0.06em] text-[var(--muted)]">
              шаги
            </span>
            <span className="font-mono text-[14px] leading-none text-[var(--fg)]">
              {steps}
            </span>
          </div>
          <div className="flex items-baseline gap-2 px-4 py-2">
            <span className="text-[10px] uppercase tracking-[0.06em] text-[var(--muted)]">
              баланс
            </span>
            <span
              className={`font-mono text-[18px] leading-none ${
                netBalance > 0 ? "text-[var(--danger)]" : "text-[var(--ok)]"
              }`}
            >
              {netBalance > 0 ? "+" : ""}
              {Math.round(netBalance)}
            </span>
          </div>
        </div>
      ) : null}
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
      if ((item.episode.glucose ?? []).some((e) => isValidCGM(e.value))) hasCGM = true;
    } else if (item.kind === "insulin") {
      totalInsulin++;
    }
  }

  return { totalMeals, totalCarbs, totalKcal, totalInsulin, hasCGM };
}
