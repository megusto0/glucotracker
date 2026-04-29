import {
  useInfiniteQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { apiClient, type MealResponse } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import { Button } from "../../design/primitives/Button";
import {
  EmptyLog,
  MealRow,
  RightPanel,
  SelectedMealPanel,
} from "../meals/MealLedger";
import {
  useNightscoutEvents,
  useNightscoutSettings,
  useResyncMealToNightscout,
  useSyncMealToNightscout,
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
  meals: MealResponse[];
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

const groupMealsByDay = (meals: MealResponse[]): DayGroup[] => {
  const groups = new Map<string, DayGroup>();
  meals.forEach((meal) => {
    const key = localDayKey(meal.eaten_at);
    const existing = groups.get(key);
    if (existing) {
      existing.meals.push(meal);
      return;
    }
    groups.set(key, {
      key,
      label: dayLabel(meal.eaten_at),
      meals: [meal],
    });
  });
  return Array.from(groups.values());
};

const eventRange = (filters: FeedFilters) => {
  const now = new Date();
  const from = filters.from
    ? new Date(`${filters.from}T00:00:00`)
    : new Date(now.getTime() - 24 * 60 * 60 * 1000);
  const to = filters.to ? new Date(`${filters.to}T23:59:59`) : now;
  return { from: from.toISOString(), to: to.toISOString() };
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
  const nightscoutEvents = useNightscoutEvents(
    range.from,
    range.to,
    Boolean(nightscoutSettings.data?.configured),
  );
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
  const groups = useMemo(() => groupMealsByDay(meals), [meals]);
  const selectedMeal = meals.find((meal) => meal.id === selectedMealId) ?? null;

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
          {nightscoutEvents.data &&
          (nightscoutEvents.data.insulin.length ||
            nightscoutEvents.data.glucose.length) ? (
            <NightscoutEpisodeBlock events={nightscoutEvents.data} />
          ) : null}

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
              {group.meals.map((meal) => (
                <MealRow
                  key={meal.id}
                  meal={meal}
                  selected={selectedMealId === meal.id}
                  onToggle={() =>
                    setSelectedMealId((current) =>
                      current === meal.id ? null : meal.id,
                    )
                  }
                />
              ))}
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

function NightscoutEpisodeBlock({
  events,
}: {
  events: {
    glucose: Array<{ timestamp: string; value: number; unit: string }>;
    insulin: Array<{
      timestamp: string;
      insulin_units?: number | null;
      eventType?: string | null;
    }>;
  };
}) {
  const glucoseValues = events.glucose.map((entry) => entry.value);
  const minGlucose = glucoseValues.length ? Math.min(...glucoseValues) : null;
  const maxGlucose = glucoseValues.length ? Math.max(...glucoseValues) : null;
  const formatTime = (iso: string) =>
    new Intl.DateTimeFormat("ru-RU", {
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(iso));

  return (
    <section className="border border-[var(--hairline)] bg-[rgba(255,255,255,0.35)] p-5">
      <div className="grid gap-1 border-b border-[var(--hairline)] pb-4">
        <h2 className="text-[24px] font-normal">Пищевой эпизод</h2>
        <p className="text-[12px] text-[var(--muted)]">
          Связанные события показаны по времени, без назначения доз.
        </p>
      </div>
      <div className="mt-4 grid gap-3">
        {events.insulin.slice(0, 4).map((event) => (
          <div
            className="grid grid-cols-[64px_1fr_auto] border-b border-[var(--hairline)] py-2 text-[13px]"
            key={`${event.timestamp}-${event.eventType}`}
          >
            <span className="font-mono">{formatTime(event.timestamp)}</span>
            <span>Инсулин рядом по времени · Nightscout</span>
            <span className="font-mono">
              {event.insulin_units ?? "--"} Ед
            </span>
          </div>
        ))}
        {minGlucose !== null && maxGlucose !== null ? (
          <div className="grid grid-cols-[64px_1fr_auto] py-2 text-[13px]">
            <span className="font-mono">CGM</span>
            <span>Глюкоза вокруг события</span>
            <span className="font-mono">
              {minGlucose}–{maxGlucose} mmol/L
            </span>
          </div>
        ) : null}
      </div>
    </section>
  );
}
