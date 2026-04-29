import {
  useInfiniteQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  apiClient,
  type FoodEpisodeResponse,
  type MealResponse,
  type TimelineResponse,
} from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import { Button } from "../../design/primitives/Button";
import {
  EmptyLog,
  MealRow,
  RightPanel,
  SelectedMealPanel,
} from "../meals/MealLedger";
import {
  useImportNightscoutContext,
  useNightscoutSettings,
  useResyncMealToNightscout,
  useSyncMealToNightscout,
  useTimeline,
} from "../nightscout/useNightscout";
import { useApiConfig } from "../settings/settingsStore";
import {
  buildFeedMealQuery,
  duplicateMeal,
  FEED_PAGE_SIZE,
  type FeedFilters,
  nextCursorBefore,
} from "./feedService";

type DayGroup = {
  key: string;
  label: string;
  items: FeedItem[];
};

type FeedItem =
  | { kind: "episode"; id: string; startAt: string; episode: FoodEpisodeResponse }
  | { kind: "meal"; id: string; startAt: string; meal: MealResponse }
  | {
      kind: "insulin";
      id: string;
      startAt: string;
      event: NonNullable<TimelineResponse["ungrouped_insulin"]>[number];
    };

type MealItem = NonNullable<MealResponse["items"]>[number];

const isRememberableLabelItem = (item: MealItem) =>
  item.source_kind === "label_calc" ||
  (item.calculation_method ?? "").startsWith("label_");

const pad = (value: number) => value.toString().padStart(2, "0");

const localDayKey = (iso: string) => {
  const date = new Date(iso);
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(
    date.getDate(),
  )}`;
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
    groups.set(key, {
      key,
      label: dayLabel(item.startAt),
      items: [item],
    });
  });
  return Array.from(groups.values());
};

const toLocalDateTimeString = (date: Date) =>
  `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(
    date.getDate(),
  )}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(
    date.getSeconds(),
  )}`;

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
    if (!byId.has(meal.id)) {
      byId.set(meal.id, meal);
    }
  });
  return Array.from(byId.values()).sort(
    (a, b) => Date.parse(b.eaten_at) - Date.parse(a.eaten_at),
  );
};

export function FeedPage() {
  const config = useApiConfig();
  const queryClient = useQueryClient();
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  const [selectedMealId, setSelectedMealId] = useState<string | null>(null);
  const [filters, setFilters] = useState<FeedFilters>({
    from: "",
    q: "",
    status: "active",
    to: "",
  });
  const range = useMemo(() => eventRange(filters), [filters.from, filters.to]);
  const nightscoutSettings = useNightscoutSettings();
  const timelineEnabled = Boolean(nightscoutSettings.data?.configured);
  const timeline = useTimeline(
    range.from,
    range.to,
    timelineEnabled,
  );
  const importNightscout = useImportNightscoutContext(range.from, range.to);
  const syncMealNightscout = useSyncMealToNightscout();
  const resyncMealNightscout = useResyncMealToNightscout();

  const feed = useInfiniteQuery({
    queryKey: queryKeys.feedMeals(filters),
    queryFn: ({ pageParam }) =>
      apiClient.listMeals(
        config,
        buildFeedMealQuery(filters, pageParam as string | undefined),
      ),
    enabled: Boolean(config.token.trim()),
    getNextPageParam: (lastPage) => {
      if (lastPage.items.length < FEED_PAGE_SIZE) {
        return undefined;
      }
      const lastMeal = lastPage.items[lastPage.items.length - 1];
      return lastMeal ? nextCursorBefore(lastMeal) : undefined;
    },
    initialPageParam: undefined as string | undefined,
  });

  const meals = useMemo(() => {
    const sortedMeals = uniqueSortedMeals(
      feed.data?.pages.map((page) => page.items) ?? [],
    );
    if (filters.status !== "active") {
      return sortedMeals;
    }
    return sortedMeals.filter((meal) => meal.status !== "discarded");
  }, [feed.data, filters.status]);
  const feedItems = useMemo(() => {
    const episodes = timeline.data?.episodes ?? [];
    const episodeMealIds = new Set(
      episodes.flatMap((episode) => episode.meals.map((meal) => meal.id)),
    );
    const episodeItems: FeedItem[] = episodes.map((episode) => ({
      kind: "episode",
      id: episode.id,
      startAt: episode.start_at,
      episode,
    }));
    const mealItems: FeedItem[] = meals
      .filter((meal) => !episodeMealIds.has(meal.id))
      .map((meal) => ({
        kind: "meal",
        id: meal.id,
        startAt: meal.eaten_at,
        meal,
      }));
    const insulinItems: FeedItem[] = (
      timeline.data?.ungrouped_insulin ?? []
    ).map((event) => ({
      kind: "insulin",
      id: event.nightscout_id ?? event.timestamp,
      startAt: event.timestamp,
      event,
    }));

    return [...episodeItems, ...mealItems, ...insulinItems].sort(
      (first, second) => Date.parse(second.startAt) - Date.parse(first.startAt),
    );
  }, [meals, timeline.data]);
  const groups = useMemo(() => groupFeedItemsByDay(feedItems), [feedItems]);
  const selectedMeal = meals.find((meal) => meal.id === selectedMealId) ?? null;

  useEffect(() => {
    const settings = nightscoutSettings.data;
    if (!settings?.configured) {
      return;
    }
    if (!settings.sync_glucose && !settings.import_insulin_events) {
      return;
    }
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
    if (selectedMealId && !selectedMeal) {
      setSelectedMealId(null);
    }
  }, [selectedMeal, selectedMealId]);

  const duplicate = useMutation({
    mutationFn: (meal: MealResponse) => duplicateMeal(config, meal),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["feed-meals"] });
      queryClient.invalidateQueries({ queryKey: ["meals"] });
    },
  });

  const updateMealTime = useMutation({
    mutationFn: ({ eatenAt, mealId }: { eatenAt: string; mealId: string }) =>
      apiClient.updateMeal(config, mealId, { eaten_at: eatenAt }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["feed-meals"] });
      queryClient.invalidateQueries({ queryKey: ["meals"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });

  const updateMealName = useMutation({
    mutationFn: async ({ meal, name }: { meal: MealResponse; name: string }) => {
      const updatedMeal = await apiClient.updateMeal(config, meal.id, {
        title: name,
      });
      const onlyItem = meal.items?.length === 1 ? meal.items[0] : null;
      if (onlyItem) {
        await apiClient.updateMealItem(config, onlyItem.id, { name });
        if (onlyItem.product_id) {
          await apiClient.updateProduct(config, onlyItem.product_id, { name });
        } else if (isRememberableLabelItem(onlyItem)) {
          const product = await apiClient.rememberProductFromMealItem(
            config,
            onlyItem.id,
            [],
          );
          await apiClient.updateProduct(config, product.id, { name });
        }
      }
      return updatedMeal;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["feed-meals"] });
      queryClient.invalidateQueries({ queryKey: ["meals"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["autocomplete"] });
      queryClient.invalidateQueries({ queryKey: ["database"] });
      queryClient.invalidateQueries({ queryKey: ["database-items"] });
    },
  });

  useEffect(() => {
    const target = sentinelRef.current;
    if (
      !target ||
      !feed.hasNextPage ||
      feed.isFetchingNextPage ||
      typeof IntersectionObserver === "undefined"
    ) {
      return;
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) {
          void feed.fetchNextPage();
        }
      },
      { rootMargin: "560px" },
    );
    observer.observe(target);
    return () => observer.disconnect();
  }, [feed.fetchNextPage, feed.hasNextPage, feed.isFetchingNextPage]);

  return (
    <div className="min-h-screen bg-[var(--bg)]">
      <div
        className={`min-h-screen px-14 py-12 transition-[padding] duration-200 ease-out ${
          selectedMeal ? "pr-[404px]" : ""
        }`}
      >
        <header className="grid gap-3">
          <p className="text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">
            история
          </p>
          <h1 className="text-[56px] font-normal leading-none text-[var(--fg)]">
            История
          </h1>
        </header>

        <section className="mt-10 grid grid-cols-[minmax(260px,1fr)_160px_160px_160px] gap-3 border-y border-[var(--hairline)] py-4">
          <label className="grid gap-2">
            <span className="text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">
              поиск
            </span>
            <input
              aria-label="Поиск по еде"
              className="h-11 border-0 border-b border-[var(--hairline)] bg-transparent px-0 text-[20px] outline-none focus:border-[var(--fg)]"
              onChange={(event) =>
                setFilters((current) => ({
                  ...current,
                  q: event.target.value,
                }))
              }
              placeholder="еда, заметка, позиция"
              value={filters.q}
            />
          </label>
          <label className="grid gap-2">
            <span className="text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">
              от
            </span>
            <input
              aria-label="Дата от"
              className="h-11 border-0 border-b border-[var(--hairline)] bg-transparent px-0 font-mono text-[14px] outline-none focus:border-[var(--fg)]"
              onChange={(event) =>
                setFilters((current) => ({
                  ...current,
                  from: event.target.value,
                }))
              }
              type="date"
              value={filters.from}
            />
          </label>
          <label className="grid gap-2">
            <span className="text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">
              до
            </span>
            <input
              aria-label="Дата до"
              className="h-11 border-0 border-b border-[var(--hairline)] bg-transparent px-0 font-mono text-[14px] outline-none focus:border-[var(--fg)]"
              onChange={(event) =>
                setFilters((current) => ({
                  ...current,
                  to: event.target.value,
                }))
              }
              type="date"
              value={filters.to}
            />
          </label>
          <label className="grid gap-2">
            <span className="text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">
              статус
            </span>
            <select
              aria-label="Фильтр статуса"
              className="h-11 border-0 border-b border-[var(--hairline)] bg-transparent px-0 text-[14px] uppercase tracking-[0.06em] outline-none focus:border-[var(--fg)]"
              onChange={(event) =>
                setFilters((current) => ({
                  ...current,
                  status: event.target.value as FeedFilters["status"],
                }))
              }
              value={filters.status}
            >
              <option value="active">активные</option>
              <option value="accepted">принятые</option>
              <option value="draft">черновики</option>
              <option value="discarded">отмененные</option>
            </select>
          </label>
        </section>

        <section className="mt-12 grid gap-12">
          {!config.token.trim() ? (
            <EmptyLog message="Укажите адрес backend и токен в настройках." />
          ) : null}
          {config.token.trim() && feed.isLoading ? (
            <EmptyLog message="Загружаю записи." />
          ) : null}
          {config.token.trim() && feed.isError ? (
            <EmptyLog message="Не удалось загрузить записи." />
          ) : null}
          {config.token.trim() && feed.isSuccess && !meals.length ? (
            <EmptyLog message="записей пока нет" />
          ) : null}

          {groups.map((group) => (
            <section className="grid gap-0" key={group.key}>
              <h2 className="sticky top-0 z-10 border-y border-[var(--hairline)] bg-[var(--bg)] py-4 text-[40px] font-normal leading-none text-[var(--fg)]">
                {group.label}
              </h2>
              {group.items.map((item) => {
                if (item.kind === "episode") {
                  return (
                    <FoodEpisodeCard
                      episode={item.episode}
                      key={item.id}
                      selectedMealId={selectedMealId}
                      onMealToggle={(mealId) =>
                        setSelectedMealId((current) =>
                          current === mealId ? null : mealId,
                        )
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
                      setSelectedMealId((current) =>
                        current === item.meal.id ? null : item.meal.id,
                      )
                    }
                  />
                );
              })}
            </section>
          ))}
        </section>

        <div className="py-10" ref={sentinelRef}>
          {feed.hasNextPage ? (
            <Button
              disabled={feed.isFetchingNextPage}
              onClick={() => feed.fetchNextPage()}
            >
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
            onUpdateName={(meal, name) =>
              updateMealName.mutate({ meal, name })
            }
            onSyncNightscout={(meal) => syncMealNightscout.mutate(meal.id)}
            onResyncNightscout={(meal) => resyncMealNightscout.mutate(meal.id)}
            onUpdateTime={(meal, eatenAt) =>
              updateMealTime.mutate({ eatenAt, mealId: meal.id })
            }
            syncNightscoutPending={
              syncMealNightscout.isPending || resyncMealNightscout.isPending
            }
            updateNamePending={updateMealName.isPending}
            updateTimePending={updateMealTime.isPending}
          />
        ) : null}
      </RightPanel>
    </div>
  );
}

const formatTime = (iso: string) =>
  new Intl.DateTimeFormat("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(iso));

const formatEpisodeRange = (startAt: string, endAt: string) => {
  const start = formatTime(startAt);
  const end = formatTime(endAt);
  return start === end ? start : `${start}-${end}`;
};

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

  return (
    <section className="border border-[var(--hairline)] bg-[rgba(255,255,255,0.34)]">
      <div className="grid gap-4 border-b border-[var(--hairline)] p-5 lg:grid-cols-[72px_1fr_260px]">
        <div className="font-mono text-[13px] leading-6">
          <div>{formatTime(episode.start_at)}</div>
          <div>{formatTime(episode.end_at)}</div>
        </div>
        <div className="grid gap-2">
          <div className="flex flex-wrap items-center gap-3">
            <h3 className="text-[24px] font-normal">Пищевой эпизод</h3>
            <span className="border border-[var(--hairline)] bg-[var(--bg)] px-2 py-1 text-[11px]">
              {formatEpisodeRange(episode.start_at, episode.end_at)}
            </span>
          </div>
          <p className="text-[13px] text-[var(--muted)]">
            {eventCount} события · {Math.round(episode.total_kcal)} ккал ·{" "}
            {episode.total_carbs_g} г углеводов
          </p>
        </div>
        <div className="grid gap-2">
          <div className="flex items-center justify-between text-[12px] text-[var(--muted)]">
            <span>Глюкоза (CGM)</span>
            <span>
              {episode.glucose_summary.min_value ?? "--"}-
              {episode.glucose_summary.max_value ?? "--"} ммоль/л
            </span>
          </div>
          <MiniGlucoseChart entries={glucose} />
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
          <div
            className="grid grid-cols-[72px_1fr_auto] items-center border-t border-[var(--hairline)] px-5 py-3 text-[14px]"
            key={event.nightscout_id ?? event.timestamp}
          >
            <span className="font-mono">{formatTime(event.timestamp)}</span>
            <span>Инсулин из Nightscout</span>
            <span className="font-mono">{event.insulin_units ?? "--"} ЕД</span>
          </div>
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
  const title = meal.title || meal.items?.[0]?.name || "Приём пищи";
  return (
    <button
      className={`grid grid-cols-[72px_1fr_auto] items-center border-t border-[var(--hairline)] px-5 py-3 text-left text-[14px] transition hover:bg-[var(--surface)] ${
        selected ? "bg-[var(--surface)]" : ""
      }`}
      onClick={onToggle}
      type="button"
    >
      <span className="font-mono">{formatTime(meal.eaten_at)}</span>
      <span className="grid gap-1">
        <span>{title}</span>
        <span className="text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">
          еда / принято
        </span>
      </span>
      <span className="grid grid-cols-[64px_72px] gap-4 text-right font-mono">
        <span>{meal.total_carbs_g} г</span>
        <span>{Math.round(meal.total_kcal)} ккал</span>
      </span>
    </button>
  );
}

function UngroupedInsulinRow({
  event,
}: {
  event: NonNullable<TimelineResponse["ungrouped_insulin"]>[number];
}) {
  return (
    <div className="grid grid-cols-[96px_1fr_auto] items-center border-b border-[var(--hairline)] py-4 text-[14px]">
      <span className="font-mono">{formatTime(event.timestamp)}</span>
      <span>Инсулин из Nightscout</span>
      <span className="font-mono">{event.insulin_units ?? "--"} ЕД</span>
    </div>
  );
}

function MiniGlucoseChart({
  entries,
}: {
  entries: NonNullable<FoodEpisodeResponse["glucose"]>;
}) {
  if (entries.length < 2) {
    return (
      <div className="grid h-20 place-items-center border border-[var(--hairline)] text-[12px] text-[var(--muted)]">
        нет локальных точек CGM
      </div>
    );
  }
  const values = entries.map((entry) => entry.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = Math.max(max - min, 0.1);
  const points = entries
    .map((entry, index) => {
      const x = (index / (entries.length - 1)) * 100;
      const y = 64 - ((entry.value - min) / span) * 52;
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <svg
      aria-label="Мини-график глюкозы вокруг пищевого эпизода"
      className="h-20 w-full border border-[var(--hairline)] bg-[var(--bg)]"
      role="img"
      viewBox="0 0 100 72"
    >
      <line
        stroke="var(--hairline)"
        strokeWidth="0.5"
        x1="0"
        x2="100"
        y1="36"
        y2="36"
      />
      <polyline
        fill="none"
        points={points}
        stroke="var(--fg)"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.5"
      />
    </svg>
  );
}
