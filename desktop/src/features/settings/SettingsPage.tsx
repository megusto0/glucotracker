import { ExternalLink, FileJson, RefreshCw, Trash2, Wifi } from "lucide-react";
import { useEffect, useState } from "react";
import { StatusText } from "../../components/StatusText";
import { Button } from "../../design/primitives/Button";
import {
  useNightscoutSettings,
  useTestNightscoutConnection,
  useUpdateNightscoutSettings,
} from "../nightscout/useNightscout";
import {
  useConnectionTest,
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
  const recalculate = useRecalculateTotals();
  const nightscout = useNightscoutSettings();
  const updateNightscout = useUpdateNightscoutSettings();
  const testNightscout = useTestNightscoutConnection();
  const [nightscoutUrl, setNightscoutUrl] = useState("");
  const [nightscoutSecret, setNightscoutSecret] = useState("");
  const [flags, setFlags] = useState({
    enabled: false,
    sync_glucose: true,
    show_glucose_in_journal: true,
    import_insulin_events: true,
    allow_meal_send: true,
    confirm_before_send: true,
  });

  useEffect(() => {
    if (!nightscout.data) {
      return;
    }
    setNightscoutUrl(nightscout.data.url ?? "");
    setFlags({
      enabled: nightscout.data.enabled,
      sync_glucose: nightscout.data.sync_glucose,
      show_glucose_in_journal: nightscout.data.show_glucose_in_journal,
      import_insulin_events: nightscout.data.import_insulin_events,
      allow_meal_send: nightscout.data.allow_meal_send,
      confirm_before_send: nightscout.data.confirm_before_send,
    });
  }, [nightscout.data]);

  const nightscoutPayload = () => {
    const hasNightscoutCredentials = Boolean(
      nightscoutUrl.trim() || nightscoutSecret.trim() || nightscout.data?.secret_is_set,
    );
    return {
      nightscout_enabled: flags.enabled || hasNightscoutCredentials,
      nightscout_url: nightscoutUrl.trim() || null,
      nightscout_api_secret: nightscoutSecret.trim() || "",
      sync_glucose: flags.sync_glucose,
      show_glucose_in_journal: flags.show_glucose_in_journal,
      import_insulin_events: flags.import_insulin_events,
      allow_meal_send: flags.allow_meal_send,
      confirm_before_send: flags.confirm_before_send,
      autosend_meals: false,
    };
  };

  const saveNightscout = () => {
    updateNightscout.mutate(nightscoutPayload());
    setNightscoutSecret("");
  };

  const testCurrentNightscout = async () => {
    await updateNightscout.mutateAsync(nightscoutPayload());
    setNightscoutSecret("");
    testNightscout.mutate();
  };

  return (
    <div className="min-h-screen bg-[var(--bg)] px-14 py-12">
      <header className="grid gap-4 border-b border-[var(--hairline)] pb-10">
        <p className="text-[12px] uppercase tracking-[0.06em] text-[var(--muted)]">
          настройки
        </p>
        <h1 className="text-[56px] font-normal leading-none text-[var(--fg)]">
          Интеграция: Nightscout
        </h1>
        <p className="max-w-[760px] text-[16px] text-[var(--muted)]">
          Подключите свой Nightscout для синхронизации данных о глюкозе,
          инсулине и еде. glucotracker не рассчитывает дозы и не отправляет
          инсулин.
        </p>
      </header>

      <main className="grid gap-12 py-10 xl:grid-cols-[minmax(520px,1fr)_420px]">
        <div className="grid content-start gap-12">
          <section className="grid gap-6 border-b border-[var(--hairline)] pb-10">
            <h2 className="text-[24px] font-normal">Локальный backend</h2>
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
            <div className="flex flex-wrap gap-3">
              <Button
                disabled={connection.isPending}
                icon={<Wifi size={18} />}
                onClick={() => connection.mutate()}
                variant="primary"
              >
                Проверить backend
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
            {connection.data ? (
              <div className="grid w-full max-w-[720px] gap-3 border border-[var(--hairline)] bg-[var(--surface)] p-4 text-[14px]">
                <div className="flex items-center justify-between gap-4">
                  <span>Backend</span>
                  <StatusText tone="ok">
                    {connection.data.health.status} / v
                    {connection.data.health.version}
                  </StatusText>
                </div>
                <div className="flex items-center justify-between gap-4">
                  <span>OpenAPI</span>
                  <StatusText
                    tone={connection.data.openapiAvailable ? "ok" : "muted"}
                  >
                    {connection.data.openapiAvailable ? "доступен" : "недоступен"}
                  </StatusText>
                </div>
              </div>
            ) : null}
          </section>

          <section className="grid gap-6">
            <h2 className="text-[24px] font-normal">Подключение</h2>
            <label className="grid gap-2">
              <span className="text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">
                Nightscout URL
              </span>
              <input
                className="h-12 border-0 border-b border-[var(--hairline)] bg-transparent px-0 text-[18px] outline-none focus:border-[var(--fg)]"
                onChange={(event) => setNightscoutUrl(event.target.value)}
                placeholder="https://ваш-сервер-nightscout.example"
                value={nightscoutUrl}
              />
              <span className="text-[12px] text-[var(--muted)]">
                Укажите полный URL вашего Nightscout, включая https://
              </span>
            </label>
            <label className="grid gap-2">
              <span className="text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">
                API Secret
              </span>
              <input
                className="h-12 border-0 border-b border-[var(--hairline)] bg-transparent px-0 font-mono text-[18px] outline-none focus:border-[var(--fg)]"
                onChange={(event) => setNightscoutSecret(event.target.value)}
                placeholder={
                  nightscout.data?.secret_is_set
                    ? "секрет сохранён, введите новый для замены"
                    : "API Secret"
                }
                type="password"
                value={nightscoutSecret}
              />
              <span className="text-[12px] text-[var(--muted)]">
                Секрет хранится только на backend и не возвращается во frontend.
              </span>
            </label>
            <div className="flex flex-wrap items-center gap-3">
              <span className="text-[14px]">Статус подключения</span>
              <StatusText tone={nightscout.data?.connected ? "ok" : "muted"}>
                {nightscout.data?.connected ? "подключено" : "не подключено"}
              </StatusText>
              {nightscout.data?.last_error ? (
                <span className="text-[12px] text-[var(--danger)]">
                  {nightscout.data.last_error}
                </span>
              ) : null}
            </div>
            <Button
              disabled={testNightscout.isPending || updateNightscout.isPending}
              icon={<Wifi size={18} />}
              onClick={() => void testCurrentNightscout()}
            >
              Проверить подключение
            </Button>
          </section>

          <section className="grid gap-4">
            <h2 className="text-[24px] font-normal">Синхронизация</h2>
            <ToggleRow
              checked={flags.enabled}
              label="Включить Nightscout"
              onChange={(value) => setFlags((current) => ({ ...current, enabled: value }))}
            />
            <ToggleRow
              checked={flags.show_glucose_in_journal}
              label="Показывать глюкозу в журнале"
              onChange={(value) =>
                setFlags((current) => ({
                  ...current,
                  show_glucose_in_journal: value,
                  sync_glucose: value,
                }))
              }
            />
            <ToggleRow
              checked={flags.import_insulin_events}
              label="Показывать ручные записи инсулина"
              onChange={(value) =>
                setFlags((current) => ({
                  ...current,
                  import_insulin_events: value,
                }))
              }
            />
            <ToggleRow
              checked={flags.allow_meal_send}
              label="Разрешить отправку записей о еде"
              onChange={(value) =>
                setFlags((current) => ({ ...current, allow_meal_send: value }))
              }
            />
            <ToggleRow
              checked={flags.confirm_before_send}
              label="Подтверждать перед отправкой"
              onChange={(value) =>
                setFlags((current) => ({
                  ...current,
                  confirm_before_send: value,
                }))
              }
            />
            <ToggleRow checked={false} disabled label="Автоотправка еды: позже" />
          </section>
        </div>

        <aside className="grid content-start gap-8 border-l border-[var(--hairline)] pl-9">
          <section className="border border-[var(--hairline)] bg-[var(--surface)] p-5">
            <p className="text-[13px]">Предпросмотр: как запись появится в Nightscout</p>
            <div className="mt-6 grid grid-cols-[72px_1fr_auto] gap-4 border border-[var(--hairline)] p-4">
              <div className="h-16 w-16 bg-[var(--bg)]" />
              <div>
                <p className="text-[16px]">Обед с котлетами и гарниром</p>
                <p className="mt-1 text-[12px] text-[var(--muted)]">
                  28 апр. 2026, 19:58
                </p>
                <p className="mt-3 font-mono text-[15px]">123 г углеводов</p>
              </div>
              <span className="h-fit border border-[var(--fg)] px-2 py-1 text-[10px] uppercase">
                Nightscout
              </span>
            </div>
            <p className="mt-5 text-[12px] leading-5 text-[var(--muted)]">
              Отображение в Nightscout зависит от вашей темы и конфигурации.
            </p>
          </section>

          <section className="border border-[var(--hairline)] p-5">
            <p className="text-[14px]">Где взять API Secret?</p>
            <p className="mt-3 text-[13px] leading-5 text-[var(--muted)]">
              Nightscout → Admin → API Secret. Скопируйте значение и вставьте
              его выше.
            </p>
          </section>

          <section className="grid gap-3">
            <a
              className="inline-flex h-10 w-fit items-center justify-center gap-2 border border-[var(--hairline)] bg-[var(--surface)] px-3 text-[13px] font-medium uppercase tracking-[0.06em] text-[var(--fg)] transition duration-200 ease-out hover:border-[var(--fg)]"
              href={openApiHref(baseUrl)}
              rel="noreferrer"
              target="_blank"
            >
              <FileJson size={18} />
              OpenAPI
              <ExternalLink size={14} />
            </a>
            <div className="flex gap-3 pt-4">
              <Button onClick={() => nightscout.refetch()}>Отмена</Button>
              <Button
                disabled={updateNightscout.isPending}
                onClick={saveNightscout}
                variant="primary"
              >
                {updateNightscout.isPending ? "Сохраняю..." : "Сохранить"}
              </Button>
            </div>
            {testNightscout.data ? (
              <StatusText tone={testNightscout.data.ok ? "ok" : "danger"}>
                {testNightscout.data.ok
                  ? "подключение работает"
                  : (testNightscout.data.error ?? "ошибка подключения")}
              </StatusText>
            ) : null}
          </section>
        </aside>
      </main>
    </div>
  );
}

function ToggleRow({
  checked,
  disabled = false,
  label,
  onChange,
}: {
  checked: boolean;
  disabled?: boolean;
  label: string;
  onChange?: (value: boolean) => void;
}) {
  return (
    <label className="flex items-center justify-between gap-4 border-b border-[var(--hairline)] py-3 text-[15px]">
      <span>{label}</span>
      <input
        checked={checked}
        className="h-5 w-10 accent-[var(--fg)]"
        disabled={disabled}
        onChange={(event) => onChange?.(event.target.checked)}
        type="checkbox"
      />
    </label>
  );
}
