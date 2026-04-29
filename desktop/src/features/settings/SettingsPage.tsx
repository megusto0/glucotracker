import {
  ExternalLink,
  FileJson,
  RefreshCw,
  Trash2,
  UploadCloud,
  Wifi,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { StatusText } from "../../components/StatusText";
import { Button } from "../../design/primitives/Button";
import {
  localDateKey,
  useNightscoutSettings,
  useSyncTodayToNightscout,
  useTestNightscoutConnection,
  useUpdateNightscoutSettings,
} from "../nightscout/useNightscout";
import {
  useConnectionTest,
  useRecalculateTotals,
} from "./useSettingsChecks";
import { EndocrinologistReportSection } from "./EndocrinologistReportSection";
import { useSettingsStore } from "./settingsStore";

const openApiHref = (baseUrl: string) =>
  `${baseUrl.trim().replace(/\/+$/, "") || "http://127.0.0.1:8000"}/openapi.json`;

type SyncFlags = {
  sync_glucose: boolean;
  import_insulin_events: boolean;
};

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
  const syncTodayNightscout = useSyncTodayToNightscout(localDateKey(new Date()));
  const [nightscoutUrl, setNightscoutUrl] = useState("");
  const [nightscoutSecret, setNightscoutSecret] = useState("");
  const [flags, setFlags] = useState<SyncFlags>({
    sync_glucose: true,
    import_insulin_events: true,
  });

  useEffect(() => {
    if (!nightscout.data) {
      return;
    }
    setNightscoutUrl(nightscout.data.url ?? "");
    setFlags({
      sync_glucose: nightscout.data.sync_glucose,
      import_insulin_events: nightscout.data.import_insulin_events,
    });
  }, [nightscout.data]);

  const savedNightscoutUrl = nightscout.data?.url ?? "";
  const hasNightscoutChanges =
    nightscoutUrl.trim() !== savedNightscoutUrl ||
    nightscoutSecret.trim().length > 0 ||
    flags.sync_glucose !== (nightscout.data?.sync_glucose ?? true) ||
    flags.import_insulin_events !==
      (nightscout.data?.import_insulin_events ?? true);

  const hasNightscoutCredentials = Boolean(
    nightscoutUrl.trim() &&
      (nightscoutSecret.trim() || nightscout.data?.secret_is_set),
  );

  const nightscoutPayload = () => ({
    nightscout_enabled: hasNightscoutCredentials,
    nightscout_url: nightscoutUrl.trim() || null,
    nightscout_api_secret: nightscoutSecret.trim() || "",
    sync_glucose: flags.sync_glucose,
    show_glucose_in_journal: flags.sync_glucose,
    import_insulin_events: flags.import_insulin_events,
    allow_meal_send: nightscout.data?.allow_meal_send ?? true,
    confirm_before_send: nightscout.data?.confirm_before_send ?? true,
    autosend_meals: false,
  });

  const resetNightscoutForm = () => {
    setNightscoutUrl(nightscout.data?.url ?? "");
    setNightscoutSecret("");
    setFlags({
      sync_glucose: nightscout.data?.sync_glucose ?? true,
      import_insulin_events: nightscout.data?.import_insulin_events ?? true,
    });
  };

  const saveNightscout = () => {
    updateNightscout.mutate(nightscoutPayload(), {
      onSuccess: () => setNightscoutSecret(""),
    });
  };

  const testCurrentNightscout = async () => {
    await updateNightscout.mutateAsync(nightscoutPayload());
    setNightscoutSecret("");
    testNightscout.mutate();
  };

  const connectionError =
    (!testNightscout.data?.ok ? testNightscout.data?.error : null) ??
    nightscout.data?.last_error ??
    null;
  const connectionLabel = testNightscout.data?.ok
    ? "подключено"
    : nightscout.data?.connected
      ? "подключено"
      : connectionError
        ? "ошибка"
        : nightscout.data?.configured
          ? "не подключено"
          : "не настроено";
  const connectionTone: "ok" | "danger" | "muted" =
    testNightscout.data?.ok || nightscout.data?.connected
      ? "ok"
      : connectionError
        ? "danger"
        : "muted";

  return (
    <div className="min-h-screen bg-[var(--bg)] px-5 py-8 sm:px-8 lg:px-14 lg:py-12">
      <header className="grid gap-4 border-b border-[var(--hairline)] pb-8 lg:pb-10">
        <p className="text-[12px] uppercase tracking-[0.06em] text-[var(--muted)]">
          настройки
        </p>
        <h1 className="text-[38px] font-normal leading-none text-[var(--fg)] sm:text-[48px] lg:text-[56px]">
          Интеграция: Nightscout
        </h1>
        <p className="max-w-[760px] text-[16px] text-[var(--muted)]">
          Nightscout остаётся дополнительной интеграцией. glucotracker может
          читать контекст глюкозы и показывать записи инсулина, но не считает
          дозы и не отправляет инсулин.
        </p>
      </header>

      <main className="grid gap-10 py-8 xl:grid-cols-[minmax(0,1fr)_360px] xl:items-start xl:gap-12">
        <div className="grid min-w-0 content-start gap-8">
          <SettingsSection title="Подключение">
            <label className="grid gap-2">
              <span className="text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">
                Nightscout URL
              </span>
              <input
                className="h-12 min-w-0 border-0 border-b border-[var(--hairline)] bg-transparent px-0 text-[18px] outline-none focus:border-[var(--fg)]"
                onChange={(event) => setNightscoutUrl(event.target.value)}
                placeholder="https://your-nightscout.example"
                value={nightscoutUrl}
              />
            </label>

            <label className="grid gap-2">
              <span className="text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">
                API Secret
              </span>
              <input
                className="h-12 min-w-0 border-0 border-b border-[var(--hairline)] bg-transparent px-0 font-mono text-[18px] outline-none focus:border-[var(--fg)]"
                onChange={(event) => setNightscoutSecret(event.target.value)}
                placeholder={
                  nightscout.data?.secret_is_set
                    ? "секрет сохранён; введите новый для замены"
                    : "API Secret"
                }
                type="password"
                value={nightscoutSecret}
              />
              <span className="text-[12px] text-[var(--muted)]">
                Секрет хранится только на backend и не возвращается во frontend.
              </span>
            </label>

            <div className="flex flex-wrap items-start justify-between gap-4 border border-[var(--hairline)] bg-[var(--surface)] p-4">
              <div className="grid gap-1">
                <span className="text-[12px] uppercase tracking-[0.06em] text-[var(--muted)]">
                  Статус
                </span>
                <StatusText tone={connectionTone}>{connectionLabel}</StatusText>
                {connectionError ? (
                  <span className="max-w-[560px] text-[12px] leading-5 text-[var(--danger)]">
                    {connectionError}
                  </span>
                ) : null}
              </div>
              <Button
                disabled={testNightscout.isPending || updateNightscout.isPending}
                icon={<Wifi size={18} />}
                onClick={() => void testCurrentNightscout()}
              >
                {testNightscout.isPending ? "Проверяю..." : "Проверить подключение"}
              </Button>
            </div>
          </SettingsSection>

          <SettingsSection title="Синхронизация">
            <ToggleRow
              checked={flags.sync_glucose}
              description="Если включено, глюкоза из Nightscout загружается и хранится локально."
              label="Синхронизировать глюкозу"
              onChange={(value) =>
                setFlags((current) => ({
                  ...current,
                  sync_glucose: value,
                }))
              }
            />
            <ToggleRow
              checked={flags.import_insulin_events}
              description="Только контекст из Nightscout; glucotracker никогда не отправляет инсулин."
              label="Показывать записи инсулина из Nightscout"
              onChange={(value) =>
                setFlags((current) => ({
                  ...current,
                  import_insulin_events: value,
                }))
              }
            />

            {hasNightscoutChanges ? (
              <div className="flex flex-wrap items-center gap-3 pt-2">
                <Button
                  disabled={updateNightscout.isPending}
                  onClick={saveNightscout}
                  variant="primary"
                >
                  {updateNightscout.isPending ? "Сохраняю..." : "Сохранить изменения"}
                </Button>
                <Button
                  disabled={updateNightscout.isPending}
                  onClick={resetNightscoutForm}
                >
                  Отмена
                </Button>
              </div>
            ) : null}
          </SettingsSection>

          <SettingsSection title="Действия">
            <div className="flex flex-wrap items-center gap-3">
              <Button
                disabled={
                  syncTodayNightscout.isPending || !nightscout.data?.configured
                }
                icon={<UploadCloud size={18} />}
                onClick={() => syncTodayNightscout.mutate()}
                variant="primary"
              >
                {syncTodayNightscout.isPending
                  ? "Отправляю..."
                  : "Отправить сегодняшние записи"}
              </Button>
              {!nightscout.data?.configured ? (
                <StatusText>сначала подключите Nightscout</StatusText>
              ) : null}
            </div>
            {syncTodayNightscout.data ? (
              <p className="text-[13px] text-[var(--muted)]">
                Отправлено: {syncTodayNightscout.data.sent_count}, пропущено:{" "}
                {syncTodayNightscout.data.skipped_count}, ошибок:{" "}
                {syncTodayNightscout.data.failed_count}
              </p>
            ) : null}
          </SettingsSection>

          <EndocrinologistReportSection />
        </div>

        <aside className="grid min-w-0 content-start gap-6 border-t border-[var(--hairline)] pt-8 xl:border-l xl:border-t-0 xl:pl-9 xl:pt-0">
          <section className="grid gap-5 border border-[var(--hairline)] bg-[var(--surface)] p-5">
            <h2 className="text-[20px] font-normal">Локальный backend</h2>
            <label className="grid gap-2">
              <span className="text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">
                Адрес backend
              </span>
              <input
                className="h-11 min-w-0 border-0 border-b border-[var(--hairline)] bg-transparent px-0 text-[17px] outline-none focus:border-[var(--fg)]"
                onChange={(event) => setBackendUrl(event.target.value)}
                value={baseUrl}
              />
            </label>
            <label className="grid gap-2">
              <span className="text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">
                Bearer-токен
              </span>
              <input
                className="h-11 min-w-0 border-0 border-b border-[var(--hairline)] bg-transparent px-0 font-mono text-[17px] outline-none focus:border-[var(--fg)]"
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
                Очистить UI
              </Button>
            </div>
            {connection.data ? (
              <div className="grid gap-3 border border-[var(--hairline)] bg-[var(--bg)] p-4 text-[14px]">
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

          <section className="border border-[var(--hairline)] p-5">
            <p className="text-[14px]">API Secret</p>
            <p className="mt-3 text-[13px] leading-5 text-[var(--muted)]">
              API Secret находится в админке Nightscout. Вставьте его один раз;
              потом frontend видит только признак, что секрет сохранён.
            </p>
          </section>

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
        </aside>
      </main>
    </div>
  );
}

function SettingsSection({
  children,
  title,
}: {
  children: ReactNode;
  title: string;
}) {
  return (
    <section className="grid gap-5 border-b border-[var(--hairline)] pb-8 last:border-b-0">
      <h2 className="text-[24px] font-normal">{title}</h2>
      {children}
    </section>
  );
}

function ToggleRow({
  checked,
  description,
  disabled = false,
  label,
  onChange,
}: {
  checked: boolean;
  description?: string;
  disabled?: boolean;
  label: string;
  onChange?: (value: boolean) => void;
}) {
  return (
    <label className="flex items-center justify-between gap-4 border-b border-[var(--hairline)] py-4 text-[15px] last:border-b-0">
      <span className="grid gap-1">
        <span>{label}</span>
        {description ? (
          <span className="text-[12px] leading-5 text-[var(--muted)]">
            {description}
          </span>
        ) : null}
      </span>
      <input
        checked={checked}
        className="h-5 w-10 shrink-0 accent-[var(--fg)]"
        disabled={disabled}
        onChange={(event) => onChange?.(event.target.checked)}
        type="checkbox"
      />
    </label>
  );
}
