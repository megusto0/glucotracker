import { useInfiniteQuery } from "@tanstack/react-query";
import { Syringe } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  apiClient,
  type FoodEpisodeResponse,
  type MealResponse,
} from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import { Button } from "../../design/primitives/Button";
import {
  EmptyLog,
  MealRow,
  mealTitle,
  RightPanel,
  SelectedMealPanel,
} from "../meals/MealLedger";
import {
  useDuplicateMeal,
  useUpdateMealName,
  useUpdateMealTime,
} from "../meals/useMealMutations";
import {
  useImportNightscoutContext,
  useNightscoutSettings,
  useResyncMealToNightscout,
  useSyncMealToNightscout,
  useTimeline,
} from "../nightscout/useNightscout";
import { useApiConfig } from "../settings/settingsStore";
import { DaySummaryBar } from "./DaySummaryBar";
import { FeedFiltersBar } from "./FeedFiltersBar";
import type { DayGroup, FeedItem } from "./FeedPage.types";
import { QuickFilterChips, useQuickFilterChips } from "./QuickFilterChips";
import {
  buildFeedMealQuery,
  FEED_PAGE_SIZE,
  type FeedFilters,
  nextCursorBefore,
} from "./feedService";

const pad = (value: number) => value.toString().padStart(2, "0");

const localDayKey = (iso: string) => {
  const date = new Date(iso);
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
};

const dayLabel = (iso: string) =>
  new Intl.DateTimeFormat("ru-RU", {
    weekday: "long",
    day: "numeric",
    month: "long",
  })
    .format(new Date(iso))
    .toLowerCase();

const groupFeedItemsByDay = (items: FeedItem[]): DayGroup[] => {
  const groups = new Map<string, DayGroup>();
  items.forEach((item) => {
    const key = localDayKey(item.startAt);
    const existing = groups.get(key);
    if (existing) {
      existing.items.push(item);
      return;
    }
    groups.set(key, { key, label: dayLabel(item.startAt), items: [item] });
  });
  return Array.from(groups.values());
};

const toLocalDateTimeString = (date: Date) =>
  `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;

const eventRange = (filters: FeedFilters) => {
  const now = new Date();
  const from = filters.from
    ? new Date(`${filters.from}T00:00:00`)
    : new Date(now.getTime() - 24 * 60 * 60 * 1000);
  const to = filters.to ? new Date(`${filters.to}T23:59:59`) : now;
  return { from: toLocalDateTimeString(from), to: toLocalDateTimeString(to) };
};

const uniqueSortedMeals = (pages: MealResponse[][]) => {
  const byId = new Map<string, MealResponse>();
  pages.flat().forEach((meal) => {
    if (!byId.has(meal.id)) byId.set(meal.id, meal);
  });
  return Array.from(byId.values()).sort(
    (a, b) => Date.parse(b.eaten_at) - Date.parse(a.eaten_at),
  );
};

const applyQuickFilters = (items: FeedItem[], active: Set<string>) => {
  if (active.size === 0) return items;
  return items.filter((item) => {
    if (active.has("hasCGM")) {
      if (item.kind === "episode" && (item.episode.glucose ?? []).length > 0) return true;
      if (item.kind !== "episode") return false;
      return false;
    }
    if (active.has("hasInsulin")) {
      if (item.kind === "insulin") return true;
      if (item.kind === "episode" && (item.episode.insulin ?? []).length > 0) return true;
      return false;
    }
    return true;
  });
};

export function FeedPage() {
  const config = useApiConfig();
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  const [selectedMealId, setSelectedMealId] = useState<string | null>(null);
  const [filters, setFilters] = useState<FeedFilters>({
    from: "",
    q: "",
    status: "active",
    to: "",
  });
  const { active: activeChips, toggle: toggleChip } = useQuickFilterChips();
  const range = useMemo(() => eventRange(filters), [filters.from, filters.to]);
  const nightscoutSettings = useNightscoutSettings();
  const timelineEnabled = Boolean(nightscoutSettings.data?.configured);
  const timeline = useTimeline(range.from, range.to, timelineEnabled);
  const importNightscout = useImportNightscoutContext(range.from, range.to);
  const syncMealNightscout = useSyncMealToNightscout();
  const resyncMealNightscout = useResyncMealToNightscout();

  const feed = useInfiniteQuery({
    queryKey: queryKeys.feedMeals(filters),
    queryFn: ({ pageParam }) =>
      apiClient.listMeals(config, buildFeedMealQuery(filters, pageParam as string | undefined)),
    enabled: Boolean(config.token.trim()),
    getNextPageParam: (lastPage) => {
      if (lastPage.items.length < FEED_PAGE_SIZE) return undefined;
      const lastMeal = lastPage.items[lastPage.items.length - 1];
      return lastMeal ? nextCursorBefore(lastMeal) : undefined;
    },
    initialPageParam: undefined as string | undefined,
  });

  const meals = useMemo(() => {
    const sorted = uniqueSortedMeals(feed.data?.pages.map((p) => p.items) ?? []);
    if (filters.status !== "active") return sorted;
    return sorted.filter((m) => m.status !== "discarded");
  }, [feed.data, filters.status]);

  const feedItems = useMemo(() => {
    const episodes = timeline.data?.episodes ?? [];
    const episodeMealIds = new Set(
      episodes.flatMap((ep) => ep.meals.map((m) => m.id)),
    );
    const episodeItems: FeedItem[] = episodes.map((ep) => ({
      kind: "episode",
      id: ep.id,
      startAt: ep.start_at,
      episode: ep,
    }));
    const mealItems: FeedItem[] = meals
      .filter((m) => !episodeMealIds.has(m.id))
      .map((m) => ({ kind: "meal" as const, id: m.id, startAt: m.eaten_at, meal: m }));
    const insulinItems: FeedItem[] = (timeline.data?.ungrouped_insulin ?? []).map((ev) => ({
      kind: "insulin" as const,
      id: ev.nightscout_id ?? ev.timestamp,
      startAt: ev.timestamp,
      event: ev,
    }));
    return [...episodeItems, ...mealItems, ...insulinItems].sort(
      (a, b) => Date.parse(b.startAt) - Date.parse(a.startAt),
    );
  }, [meals, timeline.data]);

  const filteredItems = useMemo(
    () => applyQuickFilters(feedItems, activeChips),
    [feedItems, activeChips],
  );

  const groups = useMemo(() => groupFeedItemsByDay(filteredItems), [filteredItems]);
  const selectedMeal = meals.find((m) => m.id === selectedMealId) ?? null;

  useEffect(() => {
    const settings = nightscoutSettings.data;
    if (!settings?.configured) return;
    if (!settings.sync_glucose && !settings.import_insulin_events) return;
    importNightscout.mutate({
      sync_glucose: settings.sync_glucose,
      import_insulin_events: settings.import_insulin_events,
    });
  }, [
    importNightscout.mutate,
    nightscoutSettings.data?.configured,
    nightscoutSettings.data?.import_insulin_events,
    nightscoutSettings.data?.sync_glucose,
    range.from,
    range.to,
  ]);

  useEffect(() => {
    if (selectedMealId && !selectedMeal) setSelectedMealId(null);
  }, [selectedMeal, selectedMealId]);

  const duplicate = useDuplicateMeal();
  const updateMealTime = useUpdateMealTime();
  const updateMealName = useUpdateMealName();

  useEffect(() => {
    const target = sentinelRef.current;
    if (!target || !feed.hasNextPage || feed.isFetchingNextPage || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(
      ([entry]) => { if (entry?.isIntersecting) void feed.fetchNextPage(); },
      { rootMargin: "560px" },
    );
    observer.observe(target);
    return () => observer.disconnect();
  }, [feed.fetchNextPage, feed.hasNextPage, feed.isFetchingNextPage]);

  return (
    <div className="min-h-screen bg-[var(--bg)]">
      <div className={`min-h-screen px-14 py-12 transition-[padding] duration-200 ease-out ${selectedMeal ? "pr-[404px]" : ""}`}>
        <header className="grid gap-3">
          <p className="text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">история</p>
          <h1 className="text-[56px] font-normal leading-none text-[var(--fg)]">История</h1>
        </header>

        <FeedFiltersBar filters={filters} onChange={setFilters} />
        <QuickFilterChips active={activeChips} onToggle={toggleChip} />

        <section className="mt-10 grid gap-10">
          {!config.token.trim() ? <EmptyLog message="Укажите адрес backend и токен в настройках." /> : null}
          {config.token.trim() && feed.isLoading ? <EmptyLog message="Загружаю записи." /> : null}
          {config.token.trim() && feed.isError ? <EmptyLog message="Не удалось загрузить записи." /> : null}
          {config.token.trim() && feed.isSuccess && !meals.length ? <EmptyLog message="записей пока нет" /> : null}

          {groups.map((group) => (
            <section className="grid gap-0" key={group.key}>
              <div className="sticky top-0 z-10 border-b border-[var(--hairline)] bg-[var(--bg)]">
                <h2 className="py-4 text-[40px] font-normal leading-none text-[var(--fg)]">
                  {group.label}
                </h2>
                <DaySummaryBar items={group.items} />
              </div>
              {group.items.map((item) => {
                if (item.kind === "episode") {
                  return (
                    <FoodEpisodeCard
                      episode={item.episode}
                      key={item.id}
                      selectedMealId={selectedMealId}
                      onMealToggle={(mealId) =>
                        setSelectedMealId((cur) => cur === mealId ? null : mealId)
                      }
                    />
                  );
                }
                if (item.kind === "insulin") {
                  return <UngroupedInsulinRow event={item.event} key={item.id} />;
                }
                return (
                  <MealRow
                    key={item.id}
                    meal={item.meal}
                    selected={selectedMealId === item.meal.id}
                    onToggle={() =>
                      setSelectedMealId((cur) => cur === item.meal.id ? null : item.meal.id)
                    }
                  />
                );
              })}
            </section>
          ))}
        </section>

        <div className="py-10" ref={sentinelRef}>
          {feed.hasNextPage ? (
            <Button disabled={feed.isFetchingNextPage} onClick={() => feed.fetchNextPage()}>
              {feed.isFetchingNextPage ? "Загружаю" : "Загрузить еще"}
            </Button>
          ) : null}
        </div>
      </div>

      <RightPanel open={Boolean(selectedMeal)}>
        {selectedMeal ? (
          <SelectedMealPanel
            duplicatePending={duplicate.isPending}
            meal={selectedMeal}
            onDuplicate={(meal) => duplicate.mutate(meal)}
            onUpdateName={(meal, name) => updateMealName.mutate({ meal, name })}
            onSyncNightscout={(meal) => syncMealNightscout.mutate(meal.id)}
            onResyncNightscout={(meal) => resyncMealNightscout.mutate(meal.id)}
            onUpdateTime={(meal, eatenAt) => updateMealTime.mutate({ eatenAt, mealId: meal.id })}
            syncNightscoutPending={syncMealNightscout.isPending || resyncMealNightscout.isPending}
            updateNamePending={updateMealName.isPending}
            updateTimePending={updateMealTime.isPending}
          />
        ) : null}
      </RightPanel>
    </div>
  );
}

const formatTime = (iso: string) =>
  new Intl.DateTimeFormat("ru-RU", { hour: "2-digit", minute: "2-digit" }).format(new Date(iso));

const formatEpisodeRange = (startAt: string, endAt: string) => {
  const s = formatTime(startAt);
  const e = formatTime(endAt);
  return s === e ? s : `${s}–${e}`;
};

function glucosePeakSummary(
  entries: NonNullable<FoodEpisodeResponse["glucose"]>,
  meals: FoodEpisodeResponse["meals"],
) {
  if (entries.length < 2 || !meals.length) return null;
  const firstMealTs = Math.min(...meals.map((m) => new Date(m.eaten_at).getTime()));
  const afterMeal = entries.filter((e) => new Date(e.timestamp).getTime() >= firstMealTs);
  if (afterMeal.length < 2) return null;

  const beforeValue = entries.find(
    (e) => new Date(e.timestamp).getTime() <= firstMealTs,
  )?.value;
  if (beforeValue === undefined) return null;

  let peakEntry = afterMeal[0];
  for (const entry of afterMeal) {
    if (entry.value > peakEntry.value) peakEntry = entry;
  }

  const minutesToPeak = Math.round(
    (new Date(peakEntry.timestamp).getTime() - firstMealTs) / 60000,
  );
  return `${beforeValue.toFixed(1)} → пик ${peakEntry.value.toFixed(1)} через ${minutesToPeak} мин`;
}

function FoodEpisodeCard({
  episode,
  onMealToggle,
  selectedMealId,
}: {
  episode: FoodEpisodeResponse;
  onMealToggle: (mealId: string) => void;
  selectedMealId: string | null;
}) {
  const glucose = episode.glucose ?? [];
  const insulin = episode.insulin ?? [];
  const eventCount = episode.meals.length + insulin.length;
  const insulinLabel = insulin.length === 1 ? "запись инсулина" : insulin.length < 5 ? "записи инсулина" : "записей инсулина";
  const peakSummary = glucosePeakSummary(glucose, episode.meals);

  return (
    <section className="border border-[var(--hairline)] bg-[rgba(255,255,255,0.34)]">
      <div className="grid gap-4 p-5 lg:grid-cols-[72px_1fr_260px]">
        <div className="font-mono text-[13px] leading-6">
          <div>{formatTime(episode.start_at)}</div>
          <div>{formatTime(episode.end_at)}</div>
        </div>
        <div className="grid gap-2">
          <div className="flex flex-wrap items-center gap-3">
            <h3 className="text-[22px] font-normal">Приём пищи</h3>
            <span className="border border-[var(--hairline)] bg-[var(--bg)] px-2 py-1 text-[11px] font-mono">
              {formatEpisodeRange(episode.start_at, episode.end_at)}
            </span>
          </div>
          <p className="text-[11px] uppercase tracking-[0.04em] text-[var(--muted)]">
            Сгруппировано: события рядом по времени
          </p>
          <p className="text-[13px] text-[var(--muted)]">
            {eventCount} события · {Math.round(episode.total_kcal)} ккал · {episode.total_carbs_g} г углеводов
            {insulin.length ? ` · ${insulin.length} ${insulinLabel}` : ""}
          </p>
        </div>
        <div className="grid gap-1">
          <div className="flex items-center justify-between text-[11px] text-[var(--muted)]">
            <span>Глюкоза (CGM)</span>
            <span className="font-mono">
              {episode.glucose_summary.min_value ?? "--"}–{episode.glucose_summary.max_value ?? "--"} ммоль/л
            </span>
          </div>
          <MiniGlucoseChart entries={glucose} meals={episode.meals} />
          {peakSummary ? (
            <p className="text-[10px] text-[var(--muted)]">{peakSummary}</p>
          ) : null}
        </div>
      </div>

      <div className="grid">
        {episode.meals.map((meal) => (
          <EpisodeMealLine
            key={meal.id}
            meal={meal}
            selected={selectedMealId === meal.id}
            onToggle={() => onMealToggle(meal.id)}
          />
        ))}
        {insulin.map((event) => (
          <EpisodeInsulinRow event={event} key={event.nightscout_id ?? event.timestamp} />
        ))}
      </div>
    </section>
  );
}

function EpisodeMealLine({
  meal,
  onToggle,
  selected,
}: {
  meal: MealResponse;
  onToggle: () => void;
  selected: boolean;
}) {
  const title = mealTitle(meal);
  return (
    <button
      className={`grid grid-cols-[72px_44px_1fr_auto] items-center gap-4 border-t border-[var(--hairline)] px-5 py-3 text-left text-[14px] transition hover:bg-[var(--surface)] ${
        selected ? "border-l-2 border-l-[var(--accent)] bg-[var(--surface)]" : ""
      }`}
      onClick={onToggle}
      type="button"
    >
      <span className="font-mono text-[13px]">{formatTime(meal.eaten_at)}</span>
      <span className="text-[13px]">{title}</span>
      <span className="text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">
        еда / {meal.status === "accepted" ? "принято" : meal.status === "draft" ? "черновик" : meal.status}
      </span>
      <span className="grid grid-cols-[64px_72px] gap-4 text-right font-mono text-[13px]">
        <span>{meal.total_carbs_g} г</span>
        <span>{Math.round(meal.total_kcal)} ккал</span>
      </span>
    </button>
  );
}

function EpisodeInsulinRow({
  event,
}: {
  event: NonNullable<FoodEpisodeResponse["insulin"]>[number];
}) {
  return (
    <div className="grid grid-cols-[72px_28px_1fr_auto] items-center border-t border-[var(--hairline)] bg-[rgba(246,244,238,0.5)] px-5 py-3 text-[14px] text-[var(--muted)]">
      <span className="font-mono text-[13px]">{formatTime(event.timestamp)}</span>
      <Syringe size={14} strokeWidth={1.4} className="text-[var(--muted)]" />
      <span className="grid gap-0.5">
        <span className="text-[13px]">Инсулин из Nightscout</span>
        <span className="text-[10px] uppercase tracking-[0.06em]">инсулин / ns · только чтение</span>
      </span>
      <span className="font-mono text-[13px]">{event.insulin_units ?? "--"} ЕД</span>
    </div>
  );
}

function UngroupedInsulinRow({
  event,
}: {
  event: NonNullable<{ timestamp: string; insulin_units?: number | null; nightscout_id?: string | null }>;
}) {
  return (
    <div className="grid grid-cols-[72px_28px_1fr_auto] items-center border-b border-[var(--hairline)] py-4 text-[14px] text-[var(--muted)]">
      <span className="font-mono text-[13px]">{formatTime(event.timestamp)}</span>
      <Syringe size={14} strokeWidth={1.4} />
      <span className="grid gap-0.5">
        <span className="text-[13px]">Инсулин из Nightscout</span>
        <span className="text-[10px] uppercase tracking-[0.06em]">инсулин / ns · только чтение</span>
      </span>
      <span className="font-mono text-[13px]">{event.insulin_units ?? "--"} ЕД</span>
    </div>
  );
}

function MiniGlucoseChart({
  entries,
  meals,
}: {
  entries: NonNullable<FoodEpisodeResponse["glucose"]>;
  meals?: FoodEpisodeResponse["meals"];
  episodeStart?: string;
  episodeEnd?: string;
}) {
  if (entries.length < 2) {
    return (
      <div className="grid h-[80px] place-items-center border border-[var(--hairline)] text-[11px] text-[var(--muted)]">
        CGM нет за этот период
      </div>
    );
  }

  const viewBoxW = 260;
  const viewBoxH = 80;
  const padLeft = 24;
  const padRight = 4;
  const padTop = 8;
  const padBottom = 16;
  const chartW = viewBoxW - padLeft - padRight;
  const chartH = viewBoxH - padTop - padBottom;

  const values = entries.map((e) => e.value);
  const timestamps = entries.map((e) => new Date(e.timestamp).getTime());
  const tMin = timestamps[0];
  const tMax = timestamps[timestamps.length - 1];
  const tSpan = Math.max(tMax - tMin, 1);
  const vMin = Math.min(...values);
  const vMax = Math.max(...values);
  const vPad = (vMax - vMin) * 0.1 || 0.5;
  const vLo = vMin - vPad;
  const vHi = vMax + vPad;
  const vSpan = vHi - vLo;

  const xForTime = (ts: number) => padLeft + ((ts - tMin) / tSpan) * chartW;
  const yForValue = (v: number) => padTop + chartH - ((v - vLo) / vSpan) * chartH;

  const interpolateY = (ts: number) => {
    if (ts <= tMin) return yForValue(entries[0].value);
    if (ts >= tMax) return yForValue(entries[entries.length - 1].value);
    for (let i = 0; i < timestamps.length - 1; i++) {
      if (ts >= timestamps[i] && ts <= timestamps[i + 1]) {
        const ratio = (ts - timestamps[i]) / (timestamps[i + 1] - timestamps[i]);
        const v = entries[i].value + ratio * (entries[i + 1].value - entries[i].value);
        return yForValue(v);
      }
    }
    return yForValue(entries[entries.length - 1].value);
  };

  const points = entries
    .map((entry, i) => `${xForTime(timestamps[i])},${yForValue(entry.value)}`)
    .join(" ");

  const fmtMin = (ts: number) => {
    const d = new Date(ts);
    return `${d.getHours().toString().padStart(2, "0")}:${d.getMinutes().toString().padStart(2, "0")}`;
  };

  const tickCount = Math.min(entries.length, 4);
  const tickIndices = Array.from(
    { length: tickCount },
    (_, i) => Math.round((i / (tickCount - 1)) * (entries.length - 1)),
  );

  const mealPoints = (meals ?? []).map((m) => {
    const ts = new Date(m.eaten_at).getTime();
    return { label: fmtMin(ts), ts, x: xForTime(ts), y: interpolateY(ts) };
  });

  return (
    <svg
      aria-label="Мини-график глюкозы вокруг пищевого эпизода"
      className="h-[80px] w-full border border-[var(--hairline)] bg-[var(--bg)]"
      preserveAspectRatio="xMidYMid meet"
      role="img"
      viewBox={`0 0 ${viewBoxW} ${viewBoxH}`}
    >
      <text fill="var(--muted)" fontSize="6" textAnchor="end" x={padLeft - 2} y={yForValue(vHi) + 2}>
        {vMax.toFixed(1)}
      </text>
      <text fill="var(--muted)" fontSize="6" textAnchor="end" x={padLeft - 2} y={yForValue(vLo) + 2}>
        {vMin.toFixed(1)}
      </text>
      <polyline
        fill="none"
        points={points}
        stroke="var(--fg)"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1"
      />
      {mealPoints.map((mp, i) => (
        <circle cx={mp.x} cy={mp.y} fill="var(--accent)" key={`d-${i}`} r="2.5" stroke="var(--bg)" strokeWidth="1" />
      ))}
      {tickIndices.map((idx) => (
        <text fill="var(--muted)" fontSize="6" key={`t-${idx}`} textAnchor="middle" x={xForTime(timestamps[idx])} y={viewBoxH - 2}>
          {fmtMin(timestamps[idx])}
        </text>
      ))}
      {mealPoints.map((mp, i) => (
        <text fill="var(--accent)" fontSize="6" fontWeight="600" key={`ml-${i}`} textAnchor="middle" x={mp.x} y={viewBoxH - 2}>
          {mp.label}
        </text>
      ))}
    </svg>
  );
}
