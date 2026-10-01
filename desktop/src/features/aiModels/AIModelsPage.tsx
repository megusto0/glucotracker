import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  GripVertical,
  ArrowUp,
  ArrowDown,
  Plus,
  RefreshCw,
} from "lucide-react";
import { useState } from "react";
import {
  apiClient,
  apiErrorMessage,
  type AIModelChoice,
} from "../../api/client";
import { Button } from "../../design/primitives/Button";
import { useApiConfig, useSettingsStore } from "../settings/settingsStore";
import "./ai-models.css";

const keyOf = (model: AIModelChoice) => `${model.provider}:${model.model}`;
const providers = { gemini: "Gemini", grok: "Grok", "openai-codex": "OpenAI" };
const errors: Record<string, string> = {
  timeout: "Время ожидания истекло",
  quota: "Лимит запросов",
  overload: "Перегрузка сервиса",
  parse: "Неверный формат ответа",
  invalid_request: "Запрос или модель не поддерживаются",
  authentication: "Ошибка доступа",
  unknown: "Другая ошибка провайдера",
};
const percent = (value: number | null | undefined) =>
  value == null
    ? "—"
    : new Intl.NumberFormat("ru-RU", {
        style: "percent",
        maximumFractionDigits: 0,
      }).format(value);
const time = (value: string) =>
  new Date(value).toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });

export function moveModel(models: AIModelChoice[], from: number, to: number) {
  if (from < 0 || to < 0 || from >= models.length || to >= models.length)
    return models;
  const next = [...models];
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}

export function AIModelsPage() {
  const config = useApiConfig();
  const owner = useSettingsStore((s) => s.currentUser?.id);
  return <AIModelsContent key={`${config.baseUrl}:${owner}`} />;
}

function AIModelsContent() {
  const config = useApiConfig();
  const owner = useSettingsStore((s) => s.currentUser?.id);
  const queryClient = useQueryClient();
  const [days, setDays] = useState(30);
  const [historyOffset, setHistoryOffset] = useState(0);
  const queryKey = ["ai-models", config.baseUrl, owner, days, historyOffset];
  const query = useQuery({
    queryKey,
    queryFn: () => apiClient.getAIModels(config, days, historyOffset),
    enabled: !!config.baseUrl && !!config.token,
    refetchInterval: 15000,
  });
  const [draft, setDraft] = useState<{
    revision: number;
    models: AIModelChoice[];
  } | null>(null);
  const [dragging, setDragging] = useState<string | null>(null);
  const [provider, setProvider] = useState<AIModelChoice["provider"]>("gemini");
  const [model, setModel] = useState("");
  const [notice, setNotice] = useState("");
  const data = query.data;
  const models =
    draft?.models ??
    data?.models
      .filter((m) => m.in_routing)
      .map(({ provider, model, enabled }) => ({ provider, model, enabled })) ??
    [];
  const mutation = useMutation({
    mutationFn: () =>
      apiClient.updateAIModels(
        config,
        { revision: draft!.revision, models: draft!.models },
        days,
        historyOffset,
      ),
    onSuccess: (response) => {
      queryClient.setQueryData(queryKey, response);
      setDraft(null);
      setNotice(
        "Порядок сохранён. Он применяется к следующим автоматическим оценкам.",
      );
      void queryClient.invalidateQueries({
        queryKey: ["ai-models", config.baseUrl, owner],
      });
    },
  });
  function edit(next: AIModelChoice[]) {
    if (!data || mutation.isPending) return;
    setDraft({ revision: draft?.revision ?? data.revision, models: next });
    setNotice("");
    mutation.reset();
  }
  function add() {
    const name = model.trim();
    if (!/^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$/.test(name)) {
      setNotice("Укажите идентификатор модели без пробелов и URL.");
      return;
    }
    if (provider === "gemini" && name.toLowerCase().includes("pro")) {
      setNotice("Автоматическое использование Gemini Pro отключено.");
      return;
    }
    if (models.some((m) => m.provider === provider && m.model === name)) {
      setNotice("Модель уже есть в списке.");
      return;
    }
    edit([...models, { provider, model: name, enabled: true }]);
    setModel("");
  }
  function renderRow(choice: AIModelChoice, index: number, historical = false) {
    const key = keyOf(choice);
    const stats = data?.models.find((m) => keyOf(m) === key);
    const cooldown =
      stats?.cooldown_until && Date.parse(stats.cooldown_until) > Date.now();
    const state = historical
      ? "Вне очереди"
      : !choice.enabled
        ? "Выключена"
        : stats && !stats.available
          ? "Нет доступа"
          : cooldown
            ? `Пауза до ${time(stats!.cooldown_until!)}`
            : stats
              ? "Готова к вызову"
              : "Доступ проверится после сохранения";
    return (
      <article
        className={`ai-model-row ${dragging === key ? "ai-model-dragging" : ""}`}
        key={key}
        aria-label={`${providers[choice.provider]} ${choice.model}`}
        onDragOver={(event) => {
          if (dragging && !historical) event.preventDefault();
        }}
        onDrop={(event) => {
          event.preventDefault();
          if (!historical && dragging)
            edit(
              moveModel(
                models,
                models.findIndex((m) => keyOf(m) === dragging),
                index,
              ),
            );
          setDragging(null);
        }}
      >
        <div className="ai-model-title">
          {!historical && (
            <span
              className="ai-model-grip"
              draggable={!mutation.isPending}
              onDragStart={(event) => {
                setDragging(key);
                event.dataTransfer.effectAllowed = "move";
                event.dataTransfer.setData("text/plain", key);
              }}
              onDragEnd={() => setDragging(null)}
              title="Перетащить для изменения приоритета"
            >
              <GripVertical size={18} />
              <span className="mono">{index + 1}</span>
            </span>
          )}
          <div className="ai-model-name">
            <strong>{choice.model}</strong>
            <small>{providers[choice.provider]}</small>
          </div>
          <span
            className={`ai-model-state ${cooldown ? "ai-model-paused" : ""}`}
          >
            {state}
          </span>
          {!historical && (
            <div className="ai-model-actions">
              <Button
                aria-label={`Поднять ${choice.model}`}
                disabled={index === 0 || mutation.isPending}
                onClick={() => edit(moveModel(models, index, index - 1))}
              >
                <ArrowUp size={14} />
              </Button>
              <Button
                aria-label={`Опустить ${choice.model}`}
                disabled={index === models.length - 1 || mutation.isPending}
                onClick={() => edit(moveModel(models, index, index + 1))}
              >
                <ArrowDown size={14} />
              </Button>
              <label>
                <input
                  type="checkbox"
                  checked={choice.enabled ?? true}
                  disabled={mutation.isPending}
                  onChange={(event) =>
                    edit(
                      models.map((m, i) =>
                        i === index
                          ? { ...m, enabled: event.target.checked }
                          : m,
                      ),
                    )
                  }
                />{" "}
                Включена
              </label>
              <Button
                disabled={mutation.isPending || models.length === 1}
                onClick={() => edit(models.filter((_, i) => i !== index))}
                aria-label={`Убрать ${choice.model}`}
              >
                Убрать
              </Button>
            </div>
          )}
        </div>
        <dl className="ai-model-metrics">
          <div>
            <dt>Попыток</dt>
            <dd>{stats?.attempts ?? 0}</dd>
          </div>
          <div>
            <dt>Успешных</dt>
            <dd>
              {stats?.successes ?? 0}{" "}
              <small>· {percent(stats?.success_rate)}</small>
            </dd>
          </div>
          <div>
            <dt>Ошибок</dt>
            <dd>{stats?.failures ?? 0}</dd>
          </div>
          <div>
            <dt>Среднее время оценки</dt>
            <dd>
              {stats?.average_request_latency_ms == null
                ? "Нет данных"
                : `${(stats.average_request_latency_ms / 1000).toLocaleString("ru-RU", { maximumFractionDigits: 1 })} с`}
            </dd>
            <small>Вся цепочка · {stats?.timed_requests ?? 0} оценок</small>
          </div>
          <div>
            <dt>Уверенность модели</dt>
            <dd>{percent(stats?.average_confidence)}</dd>
            <small>{stats?.confidence_samples ?? 0} ответов</small>
          </div>
        </dl>
        <div className="ai-model-details">
          <span>
            Последний вызов:{" "}
            {stats?.last_called_at ? time(stats.last_called_at) : "нет данных"}
          </span>
          <span>Пропущено: {stats?.skipped ?? 0}</span>
          <span>
            Среднее ожидание ответа модели:{" "}
            {stats?.average_response_latency_ms == null
              ? "появится после новых запросов"
              : `${(stats.average_response_latency_ms / 1000).toLocaleString("ru-RU", { maximumFractionDigits: 1 })} с · ${stats.timed_responses} ответов`}
          </span>
          {stats?.average_latency_ms != null && (
            <span>
              Среднее время отдельного вызова:{" "}
              {(stats.average_latency_ms / 1000).toLocaleString("ru-RU", {
                maximumFractionDigits: 1,
              })}{" "}
              с · {stats.timed_attempts} измерений
            </span>
          )}
        </div>
        {!!stats?.errors?.length && (
          <ul className="ai-model-errors" aria-label={`Ошибки ${choice.model}`}>
            {stats.errors!.map((error) => (
              <li key={error.category}>
                {errors[error.category] ?? "Другая ошибка"}{" "}
                <b className="mono">{error.count}</b>
                <small> · последняя {time(error.last_at)}</small>
              </li>
            ))}
          </ul>
        )}
      </article>
    );
  }
  return (
    <main className="ai-models-page">
      <header className="ai-models-header">
        <div>
          <h1>Модели оценки еды</h1>
          <p>Приоритет и история вызовов для вашего аккаунта</p>
        </div>
        <Button
          icon={<RefreshCw size={14} />}
          disabled={query.isFetching}
          onClick={() => void query.refetch()}
        >
          Обновить
        </Button>
      </header>
      <div className="ai-models-toolbar">
        <label>
          Период{" "}
          <select
            disabled={mutation.isPending}
            aria-label="Период статистики"
            value={days}
            onChange={(e) => {
              setDays(Number(e.target.value));
              setHistoryOffset(0);
            }}
          >
            <option value={1}>24 часа</option>
            <option value={7}>7 дней</option>
            <option value={30}>30 дней</option>
            <option value={90}>90 дней</option>
          </select>
        </label>
        <span>{data ? `Обновлено ${time(data.generated_at)}` : ""}</span>
      </div>
      <p className="ai-models-help">
        Перетащите модель выше, чтобы вызывать её раньше. При ошибке
        используется следующая доступная модель. Низкая уверенность может
        вызвать дополнительную оценку. Порядок действует для автоматических
        оценок, включая запросы с телефона.
      </p>
      <p className="ai-models-help">
        Успех означает корректный ответ, а уверенность — собственную оценку
        модели, не проверенную точность питания. Среднее время оценки включает
        всю цепочку вызовов и показано у итоговой модели; отдельные вызовы
        измеряются только в новых записях.
      </p>
      {query.isPending && <p role="status">Загружаю модели…</p>}
      {query.error && <p role="alert">{apiErrorMessage(query.error)}</p>}
      {data?.history_truncated && (
        <p role="status">
          Показана статистика последних 5000 оценок за выбранный период.
        </p>
      )}
      {data && (
        <>
          {!data.custom_routing && !draft && (
            <p className="ai-models-help">
              Сейчас используется серверный порядок. Сохранение создаст ваш
              собственный список.
            </p>
          )}
          <section aria-label="Приоритет моделей">
            {models.map((choice, index) => renderRow(choice, index))}
          </section>
          <form
            className="ai-model-add"
            onSubmit={(e) => {
              e.preventDefault();
              add();
            }}
          >
            <label>
              Провайдер
              <select
                value={provider}
                onChange={(e) =>
                  setProvider(e.target.value as AIModelChoice["provider"])
                }
                disabled={mutation.isPending}
              >
                {Object.entries(providers).map(([key, value]) => (
                  <option key={key} value={key}>
                    {value}
                  </option>
                ))}
              </select>
            </label>
            <label className="ai-model-input">
              Идентификатор модели
              <input
                value={model}
                onChange={(e) => setModel(e.target.value)}
                placeholder="Название модели у провайдера"
                maxLength={120}
                disabled={mutation.isPending}
              />
            </label>
            <Button
              type="submit"
              icon={<Plus size={14} />}
              disabled={
                !model.trim() || models.length >= 30 || mutation.isPending
              }
            >
              Добавить модель
            </Button>
          </form>
          <p className="ai-models-help">
            Добавление использует уже настроенный на сервере доступ к
            провайдеру. Ключи и подключение новых провайдеров на этой странице
            не меняются.
          </p>
          <div className="ai-model-save">
            <Button
              variant="primary"
              disabled={
                !draft || mutation.isPending || !models.some((m) => m.enabled)
              }
              onClick={() => mutation.mutate()}
            >
              {mutation.isPending ? "Сохраняю…" : "Сохранить порядок"}
            </Button>
            <Button
              disabled={!draft || mutation.isPending}
              onClick={() => {
                setDraft(null);
                mutation.reset();
                setNotice("");
              }}
            >
              Отменить изменения
            </Button>
            {draft && (
              <span>
                {models.some((m) => m.enabled)
                  ? "Есть несохранённые изменения"
                  : "Оставьте хотя бы одну включённую модель"}
              </span>
            )}
          </div>
          {mutation.error && (
            <p role="alert">{apiErrorMessage(mutation.error)}</p>
          )}
          {notice && <p role="status">{notice}</p>}
          {!!data.models.filter(
            (m) => !models.some((c) => keyOf(c) === keyOf(m)) && m.attempts > 0,
          ).length && (
            <section aria-label="История остальных моделей">
              <h2>Остальные модели в истории</h2>
              {data.models
                .filter(
                  (m) =>
                    !models.some((c) => keyOf(c) === keyOf(m)) &&
                    m.attempts > 0,
                )
                .map((m, i) => renderRow(m, i, true))}
            </section>
          )}
          <section className="ai-request-history" aria-label="История запросов">
            <div className="ai-request-history-header">
              <h2>История запросов</h2>
              <span>{data.history_total} за выбранный период</span>
            </div>
            {data.history.length === 0 ? (
              <p className="ai-models-help">Запросов пока нет.</p>
            ) : (
              <div className="ai-request-list">
                {data.history.map((request) => (
                  <details key={request.id} className="ai-request-row">
                    <summary>
                      <time dateTime={request.created_at}>
                        {time(request.created_at)}
                      </time>
                      <span>
                        {request.request_type === "reestimate"
                          ? "Повторная оценка"
                          : request.request_type === "initial_estimate"
                            ? "Первичная оценка"
                            : "Оценка еды"}
                      </span>
                      <strong
                        className={
                          request.status === "success"
                            ? "ai-request-success"
                            : "ai-request-error"
                        }
                      >
                        {request.status === "success" ? "Успешно" : "Ошибка"}
                      </strong>
                      <span className="ai-request-model">
                        {request.model_used ?? request.model_requested ?? "—"}
                      </span>
                      <span>
                        {request.latency_ms == null
                          ? "Время не записано"
                          : `${(request.latency_ms / 1000).toLocaleString("ru-RU", { maximumFractionDigits: 1 })} с`}
                      </span>
                    </summary>
                    <div className="ai-request-details">
                      <p>
                        Запрошена:{" "}
                        {request.model_requested ?? "автоматический выбор"}.
                        Использована: {request.model_used ?? "—"}.
                        {request.fallback_used
                          ? " Был переход к резервной модели."
                          : ""}
                      </p>
                      {request.attempts.length > 0 ? (
                        <ol>
                          {request.attempts.map((attempt, index) => (
                            <li
                              key={`${index}:${attempt.provider}:${attempt.model}`}
                            >
                              <span>
                                {providers[attempt.provider]} · {attempt.model}
                              </span>
                              <span>
                                {attempt.status === "success"
                                  ? "Успешно"
                                  : attempt.status === "skipped"
                                    ? "Пропущена"
                                    : (errors[
                                        attempt.error_category ?? "unknown"
                                      ] ?? "Ошибка")}
                              </span>
                              <span>
                                Ответ модели:{" "}
                                {attempt.response_latency_ms == null
                                  ? "нет замера"
                                  : `${(attempt.response_latency_ms / 1000).toLocaleString("ru-RU", { maximumFractionDigits: 1 })} с`}
                              </span>
                              <span>
                                Вызов целиком:{" "}
                                {attempt.latency_ms == null
                                  ? "нет замера"
                                  : `${(attempt.latency_ms / 1000).toLocaleString("ru-RU", { maximumFractionDigits: 1 })} с`}
                              </span>
                            </li>
                          ))}
                        </ol>
                      ) : (
                        <p>Подробности попыток не записаны.</p>
                      )}
                    </div>
                  </details>
                ))}
              </div>
            )}
            {data.history_total > 30 && (
              <nav
                className="ai-request-pagination"
                aria-label="Страницы истории запросов"
              >
                <Button
                  disabled={historyOffset === 0}
                  onClick={() =>
                    setHistoryOffset(Math.max(0, historyOffset - 30))
                  }
                >
                  Назад
                </Button>
                <span>
                  {historyOffset + 1}–
                  {Math.min(historyOffset + 30, data.history_total)} из{" "}
                  {data.history_total}
                </span>
                <Button
                  disabled={historyOffset + 30 >= data.history_total}
                  onClick={() => setHistoryOffset(historyOffset + 30)}
                >
                  Далее
                </Button>
              </nav>
            )}
          </section>
        </>
      )}
    </main>
  );
}
