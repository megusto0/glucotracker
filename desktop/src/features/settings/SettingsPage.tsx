import {
  Activity,
  ExternalLink,
  FileJson,
  RefreshCw,
  Trash2,
  Wifi,
} from "lucide-react";
import { StatusText } from "../../components/StatusText";
import { Button } from "../../design/primitives/Button";
import {
  useConnectionTest,
  useNightscoutStatus,
  useRecalculateTotals,
} from "./useSettingsChecks";
import { useSettingsStore } from "./settingsStore";

const openApiHref = (baseUrl: string) =>
  `${baseUrl.trim().replace(/\/+$/, "") || "http://127.0.0.1:8000"}/openapi.json`;

export function SettingsPage() {
  const baseUrl = useSettingsStore((state) => state.baseUrl);
  const token = useSettingsStore((state) => state.token);
  const clearUiSettings = useSettingsStore((state) => state.clearUiSettings);
  const setBackendUrl = useSettingsStore((state) => state.setBackendUrl);
  const setToken = useSettingsStore((state) => state.setToken);
  const connection = useConnectionTest();
  const nightscout = useNightscoutStatus();
  const recalculate = useRecalculateTotals();
  const connectionError =
    connection.error instanceof Error ? connection.error.message : null;

  return (
    <div className="min-h-screen bg-[var(--bg)] px-14 py-12">
      <header className="grid gap-3 border-b border-[var(--hairline)] pb-10">
        <p className="text-[12px] uppercase tracking-[0.06em] text-[var(--muted)]">
          локальная среда
        </p>
        <h1 className="text-[56px] font-normal leading-none text-[var(--fg)]">
          Настройки
        </h1>
      </header>

      <section className="grid max-w-[980px] gap-12 border-b border-[var(--hairline)] py-12 xl:grid-cols-[minmax(420px,1fr)_320px]">
        <div className="grid gap-7">
          <label className="grid gap-2">
            <span className="text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">
              Адрес backend
            </span>
            <input
              className="h-12 border-0 border-b border-[var(--hairline)] bg-transparent px-0 text-[20px] outline-none focus:border-[var(--fg)]"
              onChange={(event) => setBackendUrl(event.target.value)}
              value={baseUrl}
            />
          </label>

          <label className="grid gap-2">
            <span className="text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">
              Bearer-токен
            </span>
            <input
              className="h-12 border-0 border-b border-[var(--hairline)] bg-transparent px-0 font-mono text-[20px] outline-none focus:border-[var(--fg)]"
              onChange={(event) => setToken(event.target.value)}
              type="password"
              value={token}
            />
          </label>

          <div className="flex flex-wrap gap-3 pt-1">
            <Button
              disabled={connection.isPending}
              icon={<Wifi size={18} />}
              onClick={() => connection.mutate()}
              variant="primary"
            >
              Проверить подключение
            </Button>
            <Button
              disabled={recalculate.isPending}
              icon={<RefreshCw size={18} />}
              onClick={() => recalculate.mutate()}
            >
              Пересчитать итоги
            </Button>
            <Button
              icon={<Trash2 size={18} />}
              onClick={() => clearUiSettings()}
              variant="danger"
            >
              Очистить настройки UI
            </Button>
          </div>
        </div>

        <div className="grid content-start gap-4 xl:border-l xl:border-[var(--hairline)] xl:pl-8">
          <p className="text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">
            состояние подключения
          </p>
          <div className="flex items-center justify-between gap-4">
            <span className="text-[15px]">Backend</span>
            {connection.data ? (
              <StatusText tone="ok">
                {connection.data.health.status} / v
                {connection.data.health.version}
              </StatusText>
            ) : (
              <StatusText tone={connection.isError ? "danger" : "muted"}>
                {connection.isError ? "ошибка" : "не проверено"}
              </StatusText>
            )}
          </div>
          <div className="flex items-center justify-between gap-4">
            <span className="text-[15px]">База данных</span>
            <StatusText tone={connection.data ? "ok" : "muted"}>
              {connection.data?.health.db ?? "неизвестно"}
            </StatusText>
          </div>
          <div className="flex items-center justify-between gap-4">
            <span className="text-[15px]">OpenAPI</span>
            <StatusText
              tone={connection.data?.openapiAvailable ? "ok" : "muted"}
            >
              {connection.data?.openapiAvailable ? "доступен" : "неизвестно"}
            </StatusText>
          </div>
          <div className="flex items-center justify-between gap-4">
            <span className="text-[15px]">HTTP-среда</span>
            <StatusText tone={connection.data?.runtime ? "ok" : "muted"}>
              {connection.data?.runtime ?? "неизвестно"}
            </StatusText>
          </div>
        </div>
      </section>

      <section className="grid max-w-[980px] gap-12 border-b border-[var(--hairline)] py-12 xl:grid-cols-[1fr_1fr]">
        <div className="grid content-start gap-5">
          <div className="flex items-start justify-between gap-8">
            <div>
              <p className="text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">
                Nightscout
              </p>
              <h2 className="mt-3 text-[32px] font-normal leading-none">
                Опциональная синхронизация
              </h2>
            </div>
            <StatusText tone={nightscout.data?.configured ? "ok" : "muted"}>
              {nightscout.data?.configured ? "настроен" : "не настроен"}
            </StatusText>
          </div>
          <div className="grid gap-3 border-y border-[var(--hairline)] py-4">
            <div className="flex items-center justify-between gap-4">
              <span className="text-[15px]">Настроен</span>
              <StatusText tone={nightscout.data?.configured ? "ok" : "muted"}>
                {nightscout.data?.configured ? "да" : "нет"}
              </StatusText>
            </div>
            <div className="flex items-center justify-between gap-4">
              <span className="text-[15px]">Статус</span>
              <StatusText tone={nightscout.isError ? "danger" : "muted"}>
                {nightscout.isFetching
                  ? "проверяю"
                  : nightscout.isError
                    ? "ошибка"
                    : nightscout.data?.configured
                      ? "доступен"
                      : "не настроен"}
              </StatusText>
            </div>
          </div>
          <Button
            disabled={nightscout.isFetching}
            icon={<Activity size={18} />}
            onClick={() => void nightscout.refetch()}
          >
            Проверить Nightscout
          </Button>
        </div>

        <div className="grid content-start gap-5">
          <div>
            <p className="text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">
              контракт API
            </p>
            <h2 className="mt-3 text-[32px] font-normal leading-none">
              OpenAPI
            </h2>
          </div>
          <div className="grid gap-2 border-y border-[var(--hairline)] py-4">
            <span className="font-mono text-[13px] text-[var(--fg)]">
              docs/openapi.json
            </span>
            <span className="text-[13px] leading-5 text-[var(--muted)]">
              Сгенерированные клиенты нужно обновлять из этого контракта или
              backend-эндпоинта /openapi.json.
            </span>
          </div>
          <a
            className="inline-flex h-10 w-fit items-center justify-center gap-2 border border-[var(--hairline)] bg-[var(--surface)] px-3 text-[13px] font-medium uppercase tracking-[0.06em] text-[var(--fg)] transition duration-200 ease-out hover:border-[var(--fg)]"
            href={openApiHref(baseUrl)}
            rel="noreferrer"
            target="_blank"
          >
            <FileJson size={18} />
            Открыть OpenAPI backend
            <ExternalLink size={14} />
          </a>
        </div>
      </section>

      <section className="max-w-[980px] py-8">
        <div className="grid gap-3">
          {recalculate.data ? (
            <StatusText tone="ok">
              {`${recalculate.data.days_recalculated} дней пересчитано`}
            </StatusText>
          ) : null}
          {connectionError ? (
            <p className="border-t border-[var(--hairline)] pt-3 font-mono text-[11px] text-[var(--danger)]">
              {connectionError}
            </p>
          ) : null}
        </div>
      </section>
    </div>
  );
}
