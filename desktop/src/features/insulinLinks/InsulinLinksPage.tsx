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
import { useEffect, useState } from "react";
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

const labelText = (label: string) =>
  (
    {
      correction: "Коррекция",
      food: "Еда",
      manual: "Ручная",
      mixed: "Смешанная",
      unresolved: "Разобрать",
    } as Record<string, string>
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
      source: "manual",
      confidence: link.confidence,
      note: link.note,
    });
  }
  return result;
};

const selectedLinkCount = (links: LinkDraft[], insulinId: string) =>
  links.filter((link) => link.insulin_event_id === insulinId).length;

function DaySummary({
  data,
  links,
}: {
  data?: InsulinLinkDayResponse;
  links: LinkDraft[];
}) {
  const carbs = data?.meals.reduce((sum, meal) => sum + meal.total_carbs_g, 0) ?? 0;
  const insulin =
    data?.insulin_events.reduce(
      (sum, event) => sum + (event.insulin_units ?? 0),
      0,
    ) ?? 0;
  return (
    <div className="insulin-link-summary">
      <div>
        <span>Еда</span>
        <b className="mono">{data?.meals.length ?? 0}</b>
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
    </div>
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

  const saveMutation = useMutation({
    mutationFn: () =>
      apiClient.putTimelineInsulinLinks(config, {
        date,
        links,
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

  const applyAutoLinks = () => {
    if (!query.data) return;
    setLinks(normalizeLinks(query.data.auto_links));
  };

  const resetLinks = () => {
    setLinks(normalizeLinks(query.data?.links ?? []));
  };

  const clearLinks = () => setLinks([]);

  return (
    <div className="gt-page insulin-links-page">
      <div className="gt-page-head">
        <div>
          <div className="gt-kicker">Nightscout · дневник</div>
          <h1>Связи еды и инсулина</h1>
          <p>Ручной разбор одного дня без графиков.</p>
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

      <DaySummary data={query.data} links={links} />

      {query.isLoading ? (
        <div className="gt-empty">Загрузка…</div>
      ) : query.isError ? (
        <div className="gt-empty">
          {apiErrorMessage(query.error, "Не удалось загрузить связи.")}
        </div>
      ) : (
        <div className="insulin-link-layout">
          <section className="insulin-link-column">
            <div className="section-head">
              <span>Bolus events</span>
              <button className="btn" onClick={applyAutoLinks} type="button">
                <Sparkles size={13} />
                Применить авто
              </button>
            </div>
            <div className="insulin-event-list">
              {query.data?.insulin_events.map((event) => (
                <button
                  className={`insulin-event-card ${
                    event.id === selectedInsulinId ? "active" : ""
                  }`}
                  key={event.id}
                  onClick={() => setSelectedInsulinId(event.id)}
                  type="button"
                >
                  <div className="insulin-event-dose">
                    <b className="mono">
                      {event.insulin_units == null
                        ? "—"
                        : formatDecimal(event.insulin_units, 1)}
                    </b>
                    <span>ЕД</span>
                  </div>
                  <div>
                    <div className="insulin-event-title">
                      <span>{formatTime(event.timestamp)}</span>
                      <i className={`insulin-label ${event.context_label}`}>
                        {labelText(event.context_label)}
                      </i>
                    </div>
                    <div className="insulin-event-meta">
                      {event.raw_event_type ?? "Nightscout"} · {event.reason}
                    </div>
                    <div className="insulin-event-meta mono">
                      {selectedLinkCount(links, event.id)} связ.
                      {event.nightscout_id ? ` · ${event.nightscout_id}` : ""}
                    </div>
                  </div>
                </button>
              ))}
              {!query.data?.insulin_events.length && (
                <div className="gt-empty compact">Нет bolus events за день.</div>
              )}
            </div>
          </section>

          <section className="insulin-link-column">
            <div className="section-head">
              <span>Food events</span>
              {selectedInsulin ? (
                <span className="mono">{formatTime(selectedInsulin.timestamp)}</span>
              ) : null}
            </div>
            <div className="meal-link-list">
              {query.data?.meals.map((meal) => {
                const checked =
                  !!selectedInsulinId &&
                  links.some(
                    (link) =>
                      link.meal_id === meal.id &&
                      link.insulin_event_id === selectedInsulinId,
                  );
                const suggested =
                  selectedInsulin?.suggested_meal_ids?.includes(meal.id) ?? false;
                return (
                  <button
                    className={`meal-link-card ${checked ? "linked" : ""}`}
                    disabled={!selectedInsulinId}
                    key={meal.id}
                    onClick={() => {
                      if (selectedInsulinId) toggleLink(meal.id, selectedInsulinId);
                    }}
                    type="button"
                  >
                    <span className="meal-link-icon">
                      {checked ? <Link2 size={14} /> : <Unlink size={14} />}
                    </span>
                    <span>
                      <b>{meal.title}</b>
                      <small>
                        {formatTime(meal.eaten_at)} ·{" "}
                        <span className="mono">
                          У {formatSafeInt(meal.total_carbs_g)} · К{" "}
                          {formatSafeInt(meal.total_kcal)}
                        </span>
                      </small>
                    </span>
                    {suggested ? <i>авто</i> : null}
                  </button>
                );
              })}
              {!query.data?.meals.length && (
                <div className="gt-empty compact">Нет food events за день.</div>
              )}
            </div>
          </section>

          <aside className="insulin-link-rail">
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
                  <div className="manual-link-row" key={linkKey(link.meal_id, link.insulin_event_id)}>
                    <span>
                      <b>{meal?.title ?? "Еда"}</b>
                      <small>
                        {formatTime(meal?.eaten_at)} · {formatTime(event?.timestamp)}
                      </small>
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

            <div className="insulin-link-actions">
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
                {saveMutation.isPending ? "Сохранение…" : "Сохранить"}
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
