import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ChevronLeft,
  ChevronRight,
  Link2,
  RotateCcw,
  Save,
  Sparkles,
  Unlink,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  apiClient,
  apiErrorMessage,
  type InsulinLinkDayResponse,
  type MealInsulinLinkItem,
} from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import { formatDecimal, formatSafeInt } from "../../utils/nutritionFormat";
import { useApiConfig } from "../settings/settingsStore";

type LinkDraft = Required<
  Pick<MealInsulinLinkItem, "insulin_event_id" | "meal_id" | "source">
> &
  Pick<MealInsulinLinkItem, "confidence" | "note">;

type Meal = InsulinLinkDayResponse["meals"][number];
type InsulinEvent = InsulinLinkDayResponse["insulin_events"][number];
type EpisodeKind = InsulinEvent["context_label"] | "food_only";

type Episode = {
  id: string;
  number: number;
  kind: EpisodeKind;
  title: string;
  meals: Meal[];
  insulin: InsulinEvent[];
  links: LinkDraft[];
  confidence?: number | null;
  reason: string;
  sortTime: number;
};

const pad = (value: number) => value.toString().padStart(2, "0");

const toDateInput = (date: Date) =>
  `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;

const shiftDate = (value: string, days: number) => {
  const date = new Date(`${value}T12:00:00`);
  date.setDate(date.getDate() + days);
  return toDateInput(date);
};

const formatTime = (value?: string | null) =>
  value
    ? new Intl.DateTimeFormat("ru-RU", {
        hour: "2-digit",
        minute: "2-digit",
      }).format(new Date(value))
    : "—";

const formatDayTitle = (value: string) => {
  const formatted = new Intl.DateTimeFormat("ru-RU", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(new Date(`${value}T12:00:00`));
  return formatted.charAt(0).toUpperCase() + formatted.slice(1);
};

const formatDateLabel = (value: string) => {
  const [year, month, day] = value.split("-");
  return `${day}.${month}.${year}`;
};

const labelText = (label: EpisodeKind) =>
  (
    {
      correction: "Коррекция",
      food: "Еда",
      food_only: "Без bolus",
      manual: "Ручная",
      mixed: "Смешанная",
      unresolved: "Разобрать",
    } as Record<EpisodeKind, string>
  )[label] ?? "Разобрать";

const linkKey = (mealId: string, insulinId: string) => `${mealId}:${insulinId}`;

const normalizeLinks = (links: MealInsulinLinkItem[] = []): LinkDraft[] => {
  const seen = new Set<string>();
  const result: LinkDraft[] = [];
  for (const link of links) {
    const key = linkKey(link.meal_id, link.insulin_event_id);
    if (seen.has(key)) continue;
    seen.add(key);
    result.push({
      meal_id: link.meal_id,
      insulin_event_id: link.insulin_event_id,
      source: link.source ?? "manual",
      confidence: link.confidence,
      note: link.note,
    });
  }
  return result;
};

const selectedLinkCount = (links: LinkDraft[], insulinId: string) =>
  links.filter((link) => link.insulin_event_id === insulinId).length;

const timeValue = (value?: string | null) =>
  value ? new Date(value).getTime() : Number.MAX_SAFE_INTEGER;

const episodeTitle = (meals: Meal[], insulin: InsulinEvent[], kind: EpisodeKind) => {
  if (meals.length > 1) return `${meals[0].title} + ${meals.length - 1}`;
  if (meals.length === 1) return meals[0].title;
  if (kind === "correction") return "Коррекция без еды";
  if (kind === "unresolved") return "Требует разбора";
  if (insulin.length > 1) return "Несколько bolus events";
  return "Bolus event";
};

const episodeReason = (episodeLinks: LinkDraft[], insulin: InsulinEvent[]) => {
  if (episodeLinks.some((link) => link.source === "manual")) return "Связь изменена вручную";
  const reason = insulin.find((event) => event.reason)?.reason;
  return reason || "Авторазбор по внутренним правилам";
};

const buildEpisodes = (data: InsulinLinkDayResponse, links: LinkDraft[]): Episode[] => {
  const graph = new Map<string, Set<string>>();
  const mealById = new Map(data.meals.map((meal) => [meal.id, meal]));
  const insulinById = new Map(data.insulin_events.map((event) => [event.id, event]));

  const addNode = (node: string) => {
    if (!graph.has(node)) graph.set(node, new Set());
  };
  const addEdge = (left: string, right: string) => {
    addNode(left);
    addNode(right);
    graph.get(left)?.add(right);
    graph.get(right)?.add(left);
  };

  data.meals.forEach((meal) => addNode(`m:${meal.id}`));
  data.insulin_events.forEach((event) => addNode(`i:${event.id}`));
  links.forEach((link) => {
    if (mealById.has(link.meal_id) && insulinById.has(link.insulin_event_id)) {
      addEdge(`m:${link.meal_id}`, `i:${link.insulin_event_id}`);
    }
  });

  const visited = new Set<string>();
  const components: string[][] = [];
  for (const node of graph.keys()) {
    if (visited.has(node)) continue;
    const stack = [node];
    const component: string[] = [];
    visited.add(node);
    while (stack.length) {
      const current = stack.pop();
      if (!current) continue;
      component.push(current);
      for (const next of graph.get(current) ?? []) {
        if (visited.has(next)) continue;
        visited.add(next);
        stack.push(next);
      }
    }
    components.push(component);
  }

  return components
    .map((component) => {
      const meals = component
        .filter((node) => node.startsWith("m:"))
        .map((node) => mealById.get(node.slice(2)))
        .filter((meal): meal is Meal => Boolean(meal))
        .sort((a, b) => timeValue(a.eaten_at) - timeValue(b.eaten_at));
      const insulin = component
        .filter((node) => node.startsWith("i:"))
        .map((node) => insulinById.get(node.slice(2)))
        .filter((event): event is InsulinEvent => Boolean(event))
        .sort((a, b) => timeValue(a.timestamp) - timeValue(b.timestamp));
      const episodeLinks = links.filter(
        (link) =>
          meals.some((meal) => meal.id === link.meal_id) &&
          insulin.some((event) => event.id === link.insulin_event_id),
      );
      const kind: EpisodeKind =
        episodeLinks.some((link) => link.source === "manual")
          ? "manual"
          : meals.length > 0 && insulin.length === 0
            ? "food_only"
            : insulin.length > 1
              ? "mixed"
              : (insulin[0]?.context_label ?? "unresolved");
      const confidence =
        episodeLinks.find((link) => link.confidence != null)?.confidence ??
        insulin.find((event) => event.confidence != null)?.confidence;
      const sortTime = Math.min(
        ...meals.map((meal) => timeValue(meal.eaten_at)),
        ...insulin.map((event) => timeValue(event.timestamp)),
      );

      return {
        id: component.sort().join("|"),
        number: 0,
        kind,
        title: episodeTitle(meals, insulin, kind),
        meals,
        insulin,
        links: episodeLinks,
        confidence,
        reason: episodeReason(episodeLinks, insulin),
        sortTime,
      };
    })
    .sort((a, b) => a.sortTime - b.sortTime)
    .map((episode, index) => ({ ...episode, number: index + 1 }));
};

const needsReview = (episode: Episode) => {
  if (episode.kind === "unresolved" || episode.kind === "food_only") return true;
  if (episode.meals.length > 0 && episode.insulin.length === 0) return true;
  return (
    episode.insulin.length > 0 &&
    episode.links.length === 0 &&
    episode.insulin.some((event) => event.context_label !== "correction")
  );
};

function DaySummary({
  data,
  episodes,
  links,
}: {
  data?: InsulinLinkDayResponse;
  episodes: Episode[];
  links: LinkDraft[];
}) {
  const carbs = data?.meals.reduce((sum, meal) => sum + meal.total_carbs_g, 0) ?? 0;
  const insulin =
    data?.insulin_events.reduce(
      (sum, event) => sum + (event.insulin_units ?? 0),
      0,
    ) ?? 0;
  const reviewCount = episodes.filter(needsReview).length;
  return (
    <div className="insulin-link-summary">
      <div>
        <span>Эпизоды</span>
        <b className="mono">{episodes.length}</b>
      </div>
      <div>
        <span>Углеводы</span>
        <b className="mono">{formatSafeInt(carbs)} г</b>
      </div>
      <div>
        <span>Инсулин</span>
        <b className="mono">{formatDecimal(insulin, 1)} ЕД</b>
      </div>
      <div>
        <span>Связи</span>
        <b className="mono">{links.length}</b>
      </div>
      <div>
        <span>Требуют проверки</span>
        <b className="mono">{reviewCount}</b>
      </div>
    </div>
  );
}

function EpisodeCard({
  episode,
  links,
  selectedInsulinId,
  onSelectInsulin,
  onToggleLink,
}: {
  episode: Episode;
  links: LinkDraft[];
  selectedInsulinId: string | null;
  onSelectInsulin: (id: string) => void;
  onToggleLink: (mealId: string, insulinId: string) => void;
}) {
  const carbs = episode.meals.reduce((sum, meal) => sum + meal.total_carbs_g, 0);
  const kcal = episode.meals.reduce((sum, meal) => sum + meal.total_kcal, 0);
  const units = episode.insulin.reduce(
    (sum, event) => sum + (event.insulin_units ?? 0),
    0,
  );
  const firstInsulinId = episode.insulin[0]?.id;
  const activeInsulinId =
    selectedInsulinId && episode.insulin.some((event) => event.id === selectedInsulinId)
      ? selectedInsulinId
      : firstInsulinId;
  const ratio = carbs > 0 && units > 0 ? (units / carbs) * 10 : null;

  return (
    <article className={`insulin-episode ${episode.kind}`}>
      <div className="insulin-episode-head">
        <div className="insulin-episode-num">
          <span className="mono">эпизод</span>
          <b>{episode.number}</b>
        </div>
        <div className="insulin-episode-title">
          <div>
            <span className="mono">
              {formatTime(
                episode.meals[0]?.eaten_at ?? episode.insulin[0]?.timestamp ?? null,
              )}
            </span>
            <i className={`insulin-label ${episode.kind}`}>
              {labelText(episode.kind)}
            </i>
          </div>
          <h2>{episode.title}</h2>
          <p className="mono">
            У {formatSafeInt(carbs)} г · К {formatSafeInt(kcal)} ·{" "}
            {formatDecimal(units, 1)} ЕД
            {ratio != null ? ` · ${formatDecimal(ratio, 1)} ЕД/10г` : ""}
          </p>
        </div>
        <div className="insulin-episode-meta">
          <span className="mono">{episode.links.length} связ.</span>
          {needsReview(episode) ? <b>проверить</b> : <b>авто</b>}
        </div>
      </div>

      <div className="insulin-episode-body">
        <section className="insulin-episode-col">
          <div className="insulin-episode-col-head">
            <span>Food events</span>
            <span className="mono">{episode.meals.length}</span>
          </div>
          <div className="insulin-row-list">
            {episode.meals.map((meal) => {
              const linked =
                !!activeInsulinId &&
                links.some(
                  (link) =>
                    link.meal_id === meal.id &&
                    link.insulin_event_id === activeInsulinId,
                );
              return (
                <button
                  className={`insulin-food-row ${linked ? "linked" : ""}`}
                  disabled={!activeInsulinId}
                  key={meal.id}
                  onClick={() => {
                    if (activeInsulinId) onToggleLink(meal.id, activeInsulinId);
                  }}
                  type="button"
                >
                  <span className="insulin-link-icon">
                    {linked ? <Link2 size={14} /> : <Unlink size={14} />}
                  </span>
                  <span>
                    <b>{meal.title}</b>
                    <small className="mono">
                      {formatTime(meal.eaten_at)} · У{" "}
                      {formatSafeInt(meal.total_carbs_g)} · К{" "}
                      {formatSafeInt(meal.total_kcal)}
                    </small>
                  </span>
                </button>
              );
            })}
            {!episode.meals.length && (
              <div className="gt-empty compact">Рядом нет food events.</div>
            )}
          </div>
        </section>

        <section className="insulin-episode-col">
          <div className="insulin-episode-col-head">
            <span>Bolus events</span>
            <span className="mono">{episode.insulin.length}</span>
          </div>
          <div className="insulin-row-list">
            {episode.insulin.map((event) => (
              <button
                className={`insulin-bolus-row ${
                  event.id === selectedInsulinId ? "active" : ""
                }`}
                key={event.id}
                onClick={() => onSelectInsulin(event.id)}
                type="button"
              >
                <span className="insulin-event-dose">
                  <b className="mono">
                    {event.insulin_units == null
                      ? "—"
                      : formatDecimal(event.insulin_units, 1)}
                  </b>
                  <small>ЕД</small>
                </span>
                <span>
                  <b className="mono">{formatTime(event.timestamp)}</b>
                  <small>
                    {event.raw_event_type ?? "Nightscout"} · {event.reason}
                  </small>
                  <small className="mono">
                    {selectedLinkCount(links, event.id)} связ.
                    {event.nightscout_id ? ` · ${event.nightscout_id}` : ""}
                  </small>
                </span>
                <i className={`insulin-label ${event.context_label}`}>
                  {labelText(event.context_label)}
                </i>
              </button>
            ))}
            {!episode.insulin.length && (
              <div className="gt-empty compact">Bolus не привязан.</div>
            )}
          </div>
        </section>
      </div>

      <div className="insulin-reason">
        <span>Правило</span>
        <p>{episode.reason}</p>
        <div>
          <i className="insulin-chip mono">
            {episode.confidence == null
              ? "без оценки"
              : `${Math.round(episode.confidence * 100)}%`}
          </i>
          {episode.links.some((link) => link.source === "manual") ? (
            <i className="insulin-chip mono">ручная</i>
          ) : (
            <i className="insulin-chip mono">авто</i>
          )}
        </div>
      </div>
    </article>
  );
}

export function InsulinLinksPage() {
  const config = useApiConfig();
  const queryClient = useQueryClient();
  const [date, setDate] = useState(() => toDateInput(new Date()));
  const [selectedInsulinId, setSelectedInsulinId] = useState<string | null>(null);
  const [links, setLinks] = useState<LinkDraft[]>([]);

  const query = useQuery({
    queryKey: queryKeys.timelineInsulinLinks(date),
    queryFn: () => apiClient.getTimelineInsulinLinks(config, date),
    enabled: !!config.baseUrl && !!config.token,
  });

  useEffect(() => {
    if (!query.data) return;
    setLinks(normalizeLinks(query.data.links));
    setSelectedInsulinId((current) => {
      if (current && query.data.insulin_events.some((event) => event.id === current)) {
        return current;
      }
      return query.data.insulin_events[0]?.id ?? null;
    });
  }, [query.data]);

  const episodes = useMemo(
    () => (query.data ? buildEpisodes(query.data, links) : []),
    [links, query.data],
  );

  const saveMutation = useMutation({
    mutationFn: () =>
      apiClient.putTimelineInsulinLinks(config, {
        date,
        links,
        reviewed_insulin_event_ids:
          query.data?.insulin_events.map((event) => event.id) ?? [],
      }),
    onSuccess: (data) => {
      queryClient.setQueryData(queryKeys.timelineInsulinLinks(date), data);
      setLinks(normalizeLinks(data.links));
    },
  });

  const selectedInsulin = query.data?.insulin_events.find(
    (event) => event.id === selectedInsulinId,
  );

  const toggleLink = (mealId: string, insulinId: string) => {
    setLinks((current) => {
      const key = linkKey(mealId, insulinId);
      if (current.some((link) => linkKey(link.meal_id, link.insulin_event_id) === key)) {
        return current.filter(
          (link) => linkKey(link.meal_id, link.insulin_event_id) !== key,
        );
      }
      return [
        ...current,
        {
          meal_id: mealId,
          insulin_event_id: insulinId,
          source: "manual",
        },
      ];
    });
  };

  const restoreAutoLinks = () => {
    if (!query.data) return;
    setLinks(normalizeLinks(query.data.auto_links));
  };

  const resetLinks = () => {
    setLinks(normalizeLinks(query.data?.links ?? []));
  };

  const clearLinks = () => setLinks([]);

  return (
    <div className="gt-page insulin-links-page">
      <div className="gt-page-head insulin-link-head">
        <div>
          <div className="gt-kicker">Журнал · разбор связей еды и инсулина за день</div>
          <h1>{formatDayTitle(date)}</h1>
          <p>Авторазбор по внутренним правилам с ручной правкой связей.</p>
        </div>
        <div className="insulin-link-toolbar">
          <button
            aria-label="Предыдущий день"
            className="btn icon"
            onClick={() => setDate((value) => shiftDate(value, -1))}
            type="button"
          >
            <ChevronLeft size={14} />
          </button>
          <input
            aria-label="Дата"
            className="insulin-date-input"
            onChange={(event) => setDate(event.target.value)}
            type="date"
            value={date}
          />
          <span className="insulin-date-label mono">{formatDateLabel(date)}</span>
          <button
            aria-label="Следующий день"
            className="btn icon"
            onClick={() => setDate((value) => shiftDate(value, 1))}
            type="button"
          >
            <ChevronRight size={14} />
          </button>
        </div>
      </div>

      <DaySummary data={query.data} episodes={episodes} links={links} />

      {query.isLoading ? (
        <div className="gt-empty">Загрузка...</div>
      ) : query.isError ? (
        <div className="gt-empty">
          {apiErrorMessage(query.error, "Не удалось загрузить связи.")}
        </div>
      ) : (
        <div className="insulin-link-layout">
          <main className="insulin-episode-list">
            {episodes.map((episode) => (
              <EpisodeCard
                episode={episode}
                key={episode.id}
                links={links}
                onSelectInsulin={setSelectedInsulinId}
                onToggleLink={toggleLink}
                selectedInsulinId={selectedInsulinId}
              />
            ))}
            {!episodes.length && (
              <div className="gt-empty">За день нет food и bolus events.</div>
            )}
          </main>

          <aside className="insulin-link-rail">
            <section className="insulin-rail-card">
              <div className="section-head">
                <span>Выбранный bolus</span>
                {selectedInsulin ? (
                  <span className="mono">{formatTime(selectedInsulin.timestamp)}</span>
                ) : null}
              </div>
              {selectedInsulin ? (
                <>
                  <div className="insulin-selected-bolus">
                    <span className="insulin-event-dose">
                      <b className="mono">
                        {selectedInsulin.insulin_units == null
                          ? "—"
                          : formatDecimal(selectedInsulin.insulin_units, 1)}
                      </b>
                      <small>ЕД</small>
                    </span>
                    <span>
                      <b>{labelText(selectedInsulin.context_label)}</b>
                      <small>{selectedInsulin.reason}</small>
                    </span>
                  </div>
                  <div className="insulin-rail-meals">
                    {query.data?.meals.map((meal) => {
                      const checked = links.some(
                        (link) =>
                          link.meal_id === meal.id &&
                          link.insulin_event_id === selectedInsulin.id,
                      );
                      const suggested =
                        selectedInsulin.suggested_meal_ids?.includes(meal.id) ?? false;
                      return (
                        <button
                          className={`insulin-rail-meal ${checked ? "linked" : ""}`}
                          key={meal.id}
                          onClick={() => toggleLink(meal.id, selectedInsulin.id)}
                          type="button"
                        >
                          <span>{checked ? <Link2 size={13} /> : <Unlink size={13} />}</span>
                          <b>{meal.title}</b>
                          {suggested ? <i>авто</i> : null}
                        </button>
                      );
                    })}
                  </div>
                </>
              ) : (
                <div className="gt-empty compact">Bolus не выбран.</div>
              )}
            </section>

            <section className="insulin-rail-card">
              <div className="section-head">
                <span>Текущие связи</span>
                <span className="mono">{links.length}</span>
              </div>
              <div className="manual-link-list">
                {links.map((link) => {
                  const meal = query.data?.meals.find((item) => item.id === link.meal_id);
                  const event = query.data?.insulin_events.find(
                    (item) => item.id === link.insulin_event_id,
                  );
                  return (
                    <div
                      className="manual-link-row"
                      key={linkKey(link.meal_id, link.insulin_event_id)}
                    >
                      <span>
                        <b>{meal?.title ?? "Еда"}</b>
                        <small>
                          {formatTime(meal?.eaten_at)} · {formatTime(event?.timestamp)}
                        </small>
                        <small>{link.source === "auto" ? "автоправило" : "вручную"}</small>
                      </span>
                      <button
                        aria-label="Удалить связь"
                        className="btn icon"
                        onClick={() => toggleLink(link.meal_id, link.insulin_event_id)}
                        type="button"
                      >
                        <Unlink size={13} />
                      </button>
                    </div>
                  );
                })}
                {!links.length && <div className="gt-empty compact">Связей нет.</div>}
              </div>
            </section>

            <section className="insulin-rail-card">
              <div className="section-head">
                <span>Типы</span>
              </div>
              <div className="insulin-legend">
                <span>
                  <i className="insulin-label food">{labelText("food")}</i>
                  <b>еда рядом с bolus</b>
                </span>
                <span>
                  <i className="insulin-label correction">{labelText("correction")}</i>
                  <b>без food events</b>
                </span>
                <span>
                  <i className="insulin-label manual">{labelText("manual")}</i>
                  <b>изменено вручную</b>
                </span>
              </div>
            </section>

            <div className="insulin-link-actions">
              <button className="btn" onClick={restoreAutoLinks} type="button">
                <Sparkles size={13} />
                Вернуть авто
              </button>
              <button className="btn" onClick={resetLinks} type="button">
                <RotateCcw size={13} />
                Сбросить
              </button>
              <button className="btn" onClick={clearLinks} type="button">
                <Unlink size={13} />
                Очистить
              </button>
              <button
                className="btn dark"
                disabled={saveMutation.isPending}
                onClick={() => saveMutation.mutate()}
                type="button"
              >
                <Save size={13} />
                {saveMutation.isPending ? "Сохранение..." : "Сохранить"}
              </button>
            </div>
            {saveMutation.isError ? (
              <div className="gt-error">
                {apiErrorMessage(saveMutation.error, "Не удалось сохранить связи.")}
              </div>
            ) : null}
          </aside>
        </div>
      )}
    </div>
  );
}
