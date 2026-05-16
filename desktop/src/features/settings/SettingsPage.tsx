import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  ExternalLink,
  FileJson,
  Moon,
  RefreshCw,
  Send,
  Sun,
  Trash2,
  Wifi,
} from "lucide-react";
import { useEffect, useState } from "react";
import { StatusText } from "../../components/StatusText";
import {
  apiClient,
  apiErrorMessage,
  type UserProfileUpdate,
} from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import { defaultBackendUrl, useApiConfig } from "./settingsStore";
import {
  useNightscoutSettings,
  useSyncTodayToNightscout,
  useTestNightscoutConnection,
  useUpdateNightscoutSettings,
  localDateKey,
} from "../nightscout/useNightscout";
import {
  useConnectionTest,
  useRecalculateTotals,
} from "./useSettingsChecks";
import { EndocrinologistReportSection } from "./EndocrinologistReportSection";
import { FoodDiaryExportSection } from "./FoodDiaryExportSection";
import { type Theme, useSettingsStore } from "./settingsStore";

const openApiHref = (baseUrl: string) =>
  `${baseUrl.trim().replace(/\/+$/, "") || defaultBackendUrl}/openapi.json`;

type SyncFlags = {
  sync_glucose: boolean;
  import_insulin_events: boolean;
  allow_meal_send: boolean;
  autosend_meals: boolean;
};

export function SettingsPage() {
  const baseUrl = useSettingsStore((s) => s.baseUrl);
  const token = useSettingsStore((s) => s.token);
  const clearUiSettings = useSettingsStore((s) => s.clearUiSettings);
  const setBackendUrl = useSettingsStore((s) => s.setBackendUrl);
  const setTheme = useSettingsStore((s) => s.setTheme);
  const setToken = useSettingsStore((s) => s.setToken);
  const theme = useSettingsStore((s) => s.theme);
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
    allow_meal_send: true,
    autosend_meals: false,
  });

  useEffect(() => {
    if (!nightscout.data) return;
    setNightscoutUrl(nightscout.data.url ?? "");
    setFlags({
      sync_glucose: nightscout.data.sync_glucose,
      import_insulin_events: nightscout.data.import_insulin_events,
      allow_meal_send: nightscout.data.allow_meal_send,
      autosend_meals: nightscout.data.autosend_meals,
    });
  }, [nightscout.data]);

  const savedNightscoutUrl = nightscout.data?.url ?? "";
  const hasNightscoutChanges =
    nightscoutUrl.trim() !== savedNightscoutUrl ||
    nightscoutSecret.trim().length > 0 ||
    flags.sync_glucose !== (nightscout.data?.sync_glucose ?? true) ||
    flags.import_insulin_events !==
      (nightscout.data?.import_insulin_events ?? true) ||
    flags.allow_meal_send !== (nightscout.data?.allow_meal_send ?? true) ||
    flags.autosend_meals !== (nightscout.data?.autosend_meals ?? false);

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
    allow_meal_send: flags.allow_meal_send,
    confirm_before_send: nightscout.data?.confirm_before_send ?? true,
    autosend_meals: flags.autosend_meals,
  });

  const resetNightscoutForm = () => {
    setNightscoutUrl(nightscout.data?.url ?? "");
    setNightscoutSecret("");
    setFlags({
      sync_glucose: nightscout.data?.sync_glucose ?? true,
      import_insulin_events: nightscout.data?.import_insulin_events ?? true,
      allow_meal_send: nightscout.data?.allow_meal_send ?? true,
      autosend_meals: nightscout.data?.autosend_meals ?? false,
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
    ? "Подключено"
    : nightscout.data?.connected
      ? "Подключено"
      : connectionError
        ? "Ошибка"
        : nightscout.data?.configured
          ? "Не подключено"
          : "Не настроено";
  const connectionColor =
    testNightscout.data?.ok || nightscout.data?.connected
      ? "var(--good)"
      : connectionError
        ? "var(--warn)"
        : "var(--ink-4)";

  return (
    <div className="gt-page" style={{ minHeight: "100%" }}>
      <div className="gt-crumbs"><span>настройки</span><span>интеграции</span></div>
      <h1 className="gt-h1">Интеграция: Nightscout</h1>
      <p style={{ maxWidth: 720, color: "var(--ink-3)", marginTop: 12, marginBottom: 30, lineHeight: 1.6 }}>
        Nightscout остаётся дополнительной интеграцией. glucotracker может читать контекст глюкозы и
        показывать записи инсулина, но не считает дозы и не отправляет инсулин.
      </p>

      <div className="row gap-32" style={{ alignItems: "stretch" }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <h3 style={{ fontFamily: "var(--serif)", fontWeight: 500, fontSize: 18, margin: "0 0 14px" }}>Подключение</h3>
          <div className="card card-pad">
            <div className="row gap-16">
              <div className="field" style={{ flex: 2 }}>
                <label>Nightscout URL</label>
                <input
                  onChange={(e) => setNightscoutUrl(e.target.value)}
                  placeholder="https://your-nightscout.example"
                  value={nightscoutUrl}
                />
              </div>
              <div className="field" style={{ flex: 1 }}>
                <label>API Secret</label>
                <input
                  onChange={(e) => setNightscoutSecret(e.target.value)}
                  placeholder={nightscout.data?.secret_is_set ? "секрет сохранён; введите новый для замены" : "API Secret"}
                  type="password"
                  value={nightscoutSecret}
                />
              </div>
            </div>
            <div style={{ fontSize: 11, color: "var(--ink-4)", marginTop: 8 }}>
              Секрет хранится только на backend и не возвращается на frontend.
            </div>

            <div className="row" style={{ alignItems: "center", marginTop: 18, padding: "12px 14px", background: "var(--surface-2)", borderRadius: "var(--radius-lg)", border: "1px solid var(--hairline)", gap: 14 }}>
              <div>
                <div className="lbl">статус</div>
                <div className="row gap-6" style={{ alignItems: "center", marginTop: 4 }}>
                  <span className="dot-marker" style={{ background: connectionColor }} />
                  <span style={{ fontSize: 13, fontWeight: 500 }}>{connectionLabel}</span>
                  {connectionError ? (
                    <span style={{ fontSize: 11, color: "var(--warn)" }}>{connectionError}</span>
                  ) : null}
                </div>
              </div>
              <span className="spacer" />
              <button className="btn" disabled={testNightscout.isPending || updateNightscout.isPending} onClick={() => void testCurrentNightscout()} type="button">
                <Wifi size={13} /> {testNightscout.isPending ? "Проверяю..." : "Проверить подключение"}
              </button>
            </div>
          </div>

          <h3 style={{ fontFamily: "var(--serif)", fontWeight: 500, fontSize: 18, margin: "28px 0 14px" }}>Синхронизация</h3>
          <div className="card card-pad">
            <ToggleRow
              checked={flags.sync_glucose}
              description="Если включено, глюкоза из Nightscout загружается и хранится локально."
              label="Синхронизировать глюкозу"
              onChange={(v) => setFlags((c) => ({ ...c, sync_glucose: v }))}
            />
            <ToggleRow
              checked={flags.import_insulin_events}
              description="Только контекст из Nightscout. glucotracker никогда не отправляет инсулин и не предлагает дозу."
              label="Показывать записи инсулина из Nightscout"
              onChange={(v) => setFlags((c) => ({ ...c, import_insulin_events: v }))}
            />
            <ToggleRow
              checked={flags.allow_meal_send}
              description="Разрешает backend отправлять дневниковые записи еды в Nightscout. Инсулин не отправляется."
              label="Отправлять записи еды в Nightscout"
              onChange={(v) => setFlags((c) => ({ ...c, allow_meal_send: v, autosend_meals: v ? c.autosend_meals : false }))}
            />
            <ToggleRow
              checked={flags.allow_meal_send && flags.autosend_meals}
              description="Новые принятые записи отправляются автоматически; правки и удаления уже отправленных записей зеркалятся в Nightscout."
              disabled={!flags.allow_meal_send}
              label="Автосинхронизировать записи еды"
              onChange={(v) => setFlags((c) => ({ ...c, autosend_meals: v }))}
            />
          </div>
          {hasNightscoutChanges ? (
            <div className="row gap-8" style={{ marginTop: 12 }}>
              <button className="btn dark" disabled={updateNightscout.isPending} onClick={saveNightscout} type="button">
                {updateNightscout.isPending ? "Сохраняю..." : "Сохранить"}
              </button>
              <button className="btn" disabled={updateNightscout.isPending} onClick={resetNightscoutForm} type="button">Отмена</button>
            </div>
          ) : null}

          <h3 style={{ fontFamily: "var(--serif)", fontWeight: 500, fontSize: 18, margin: "28px 0 14px" }}>Действия</h3>
          <div className="row gap-8" style={{ flexWrap: "wrap" }}>
            <button className="btn dark" disabled={syncTodayNightscout.isPending || !nightscout.data?.configured} onClick={() => syncTodayNightscout.mutate()} type="button">
              <Send size={13} /> {syncTodayNightscout.isPending ? "Отправляю..." : "Отправить сегодняшние записи"}
            </button>
            {!nightscout.data?.configured ? (
              <span style={{ fontSize: 12, color: "var(--ink-3)", lineHeight: "30px" }}>сначала подключите Nightscout</span>
            ) : null}
          </div>
          {syncTodayNightscout.data ? (
            <p style={{ fontSize: 13, color: "var(--ink-3)", marginTop: 8 }}>
              Отправлено: {syncTodayNightscout.data.sent_count}, пропущено: {syncTodayNightscout.data.skipped_count}, ошибок: {syncTodayNightscout.data.failed_count}
            </p>
          ) : null}

          <EndocrinologistReportSection />
          <FoodDiaryExportSection />
        </div>

        <div style={{ width: 340, flex: "0 0 340px", alignSelf: "stretch", display: "flex", flexDirection: "column", gap: 16 }}>
          <div className="card card-pad">
            <div className="lbl">локальный backend</div>
            <h3 style={{ fontFamily: "var(--serif)", fontWeight: 500, fontSize: 16, margin: "4px 0 14px" }}>FastAPI</h3>
            <div className="field" style={{ marginBottom: 12 }}>
              <label>адрес</label>
              <input onChange={(e) => setBackendUrl(e.target.value)} value={baseUrl} />
            </div>
            <div className="field" style={{ marginBottom: 14 }}>
              <label>bearer-token</label>
              <input onChange={(e) => setToken(e.target.value)} type="password" value={token} />
            </div>
            <div className="col gap-8">
              <button className="btn" disabled={connection.isPending} onClick={() => connection.mutate()} type="button">
                <Wifi size={13} /> Проверить backend
              </button>
              <button className="btn" disabled={recalculate.isPending} onClick={() => recalculate.mutate()} type="button">
                <RefreshCw size={13} /> Пересчитать итоги
              </button>
              <button className="btn" style={{ color: "var(--warn)", borderColor: "var(--warn-soft)" }} onClick={() => clearUiSettings()} type="button">
                <Trash2 size={13} /> Очистить UI
              </button>
            </div>
            {connection.data ? (
              <div className="card" style={{ marginTop: 12, fontSize: 13 }}>
                <div className="t-row" style={{ justifyContent: "space-between" }}>
                  <span>Backend</span>
                  <StatusText tone="ok">{connection.data.health.status} / v{connection.data.health.version}</StatusText>
                </div>
                <div className="t-row" style={{ justifyContent: "space-between" }}>
                  <span>OpenAPI</span>
                  <StatusText tone={connection.data.openapiAvailable ? "ok" : "muted"}>
                    {connection.data.openapiAvailable ? "доступен" : "недоступен"}
                  </StatusText>
                </div>
                <div className="t-row" style={{ justifyContent: "space-between" }}>
                  <span>Токен</span>
                  <StatusText tone={connection.data.tokenValid ? "ok" : "danger"}>
                    {connection.data.tokenValid ? "верный" : "неверный или не задан"}
                  </StatusText>
                </div>
              </div>
            ) : null}
          </div>

          <RhythmSection />

          <div className="card card-pad">
            <div className="lbl">оформление</div>
            <h3 style={{ fontFamily: "var(--serif)", fontWeight: 500, fontSize: 16, margin: "4px 0 14px" }}>Тема</h3>
            <div className="seg" style={{ width: "100%", height: 36 }}>
              {themeOptions.map(({ value, label, icon: Icon }) => (
                <button key={value} className={theme === value ? "on" : ""} style={{ flex: 1 }} onClick={() => setTheme(value)} type="button">
                  {Icon ? <Icon size={13} style={{ verticalAlign: "middle", marginRight: 4 }} /> : null}
                  {label}
                </button>
              ))}
            </div>
          </div>

          <div className="card card-pad" style={{ flex: 1 }}>
            <div className="lbl">профиль для расчёта TDEE</div>
            <h3 style={{ fontFamily: "var(--serif)", fontWeight: 500, fontSize: 16, margin: "4px 0 4px" }}>BMR — Mifflin-St Jeor</h3>
            <div style={{ fontSize: 11, color: "var(--ink-3)", marginBottom: 14 }}>
              Данные активности с часов скорректируют TDEE автоматически.
            </div>
            <UserProfileForm />
          </div>

          <a className="btn" href={openApiHref(baseUrl)} rel="noreferrer" target="_blank">
            <FileJson size={14} /> OpenAPI <ExternalLink size={12} />
          </a>
        </div>
      </div>
    </div>
  );
}

const scheduleMinuteLabel = (minute?: number | null) => {
  if (minute === null || minute === undefined) return "—";
  const normalized = ((minute % 1440) + 1440) % 1440;
  const hour = Math.floor(normalized / 60).toString().padStart(2, "0");
  const min = (normalized % 60).toString().padStart(2, "0");
  return `${hour}:${min}`;
};

function RhythmSection() {
  const config = useApiConfig();
  const queryClient = useQueryClient();
  const [overrideValue, setOverrideValue] = useState("");
  const schedule = useQuery({
    queryKey: queryKeys.schedule,
    queryFn: () => apiClient.getSchedule(config),
    enabled: Boolean(config.token.trim()),
  });
  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: queryKeys.schedule });
  const putOverride = useMutation({
    mutationFn: (anchor_minutes: number) =>
      apiClient.putScheduleOverride(config, { anchor_minutes }),
    onSuccess: () => {
      setOverrideValue("");
      void invalidate();
    },
  });
  const clearOverride = useMutation({
    mutationFn: () => apiClient.deleteScheduleOverride(config),
    onSuccess: () => void invalidate(),
  });

  const data = schedule.data;
  const currentAnchor = data?.effective_anchor_minutes ?? null;
  const saveOverride = () => {
    const [hoursRaw, minutesRaw] = overrideValue.split(":");
    const hours = Number(hoursRaw);
    const minutes = Number(minutesRaw);
    if (!Number.isInteger(hours) || !Number.isInteger(minutes)) return;
    putOverride.mutate(hours * 60 + minutes);
  };

  return (
    <div className="card card-pad">
      <div className="lbl">мой ритм</div>
      <h3 style={{ fontFamily: "var(--serif)", fontWeight: 500, fontSize: 16, margin: "4px 0 10px" }}>
        День с {scheduleMinuteLabel(currentAnchor)}
      </h3>
      <div style={{ fontSize: 11, color: "var(--ink-3)", marginBottom: 12 }}>
        Основа: {data?.basis ?? "absolute_fallback"}
      </div>
      <div className="col gap-6">
        {(data?.windows ?? []).map((window) => (
          <div className="t-row" key={window.key} style={{ justifyContent: "space-between" }}>
            <span>{window.label}</span>
            <span className="mono">
              {scheduleMinuteLabel(window.start_minute)}-{scheduleMinuteLabel(window.end_minute)}
            </span>
          </div>
        ))}
      </div>
      <div className="row gap-8" style={{ marginTop: 12, alignItems: "center" }}>
        <input
          aria-label="Начало дня"
          onChange={(event) => setOverrideValue(event.target.value)}
          style={{ height: 30, width: 96 }}
          type="time"
          value={overrideValue}
        />
        <button className="btn" disabled={!overrideValue || putOverride.isPending} onClick={saveOverride} type="button">
          Сохранить
        </button>
      </div>
      {data?.user_override_minutes !== null && data?.user_override_minutes !== undefined ? (
        <button className="btn" disabled={clearOverride.isPending} onClick={() => clearOverride.mutate()} style={{ marginTop: 8 }} type="button">
          Снять ручной ритм
        </button>
      ) : null}
      {data?.history?.length ? (
        <div style={{ marginTop: 12, fontSize: 11, color: "var(--ink-3)" }}>
          Последнее изменение: {scheduleMinuteLabel(data.history[0].anchor_weekday_minutes)}
        </div>
      ) : null}
      {schedule.error || putOverride.error || clearOverride.error ? (
        <p style={{ fontSize: 12, color: "var(--warn)", marginTop: 8 }}>
          {apiErrorMessage(schedule.error ?? putOverride.error ?? clearOverride.error)}
        </p>
      ) : null}
    </div>
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
    <div className="checkbox">
      <div>
        <div className="l">{label}</div>
        {description ? <div className="s">{description}</div> : null}
      </div>
      <div
        className={`checkbox-box ${checked ? "" : "off"}`}
        onClick={() => !disabled && onChange?.(!checked)}
        role="checkbox"
        aria-checked={checked}
        tabIndex={0}
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>
      </div>
    </div>
  );
}

const themeOptions: { value: Theme; label: string; icon: typeof Sun | null }[] = [
  { value: "light", label: "Светлая", icon: Sun },
  { value: "dark", label: "Тёмная", icon: Moon },
  { value: "system", label: "Система", icon: null },
];

function UserProfileForm() {
  const config = useApiConfig();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [weight, setWeight] = useState("");
  const [height, setHeight] = useState("");
  const [age, setAge] = useState("");
  const [sex, setSex] = useState("");

  useEffect(() => {
    if (!config.token.trim()) return;
    apiClient.getUserProfile(config).then((data) => {
      setWeight(data.weight_kg != null ? String(data.weight_kg) : "");
      setHeight(data.height_cm != null ? String(data.height_cm) : "");
      setAge(data.age_years != null ? String(data.age_years) : "");
      setSex(data.sex ?? "");
    }).catch(() => {});
  }, [config.token, config.baseUrl]);

  const save = () => {
    setSaving(true);
    setError(null);
    const body: UserProfileUpdate = {};
    const w = parseFloat(weight.replace(",", "."));
    const h = parseFloat(height.replace(",", "."));
    const a = parseInt(age, 10);
    if (Number.isFinite(w)) body.weight_kg = w;
    if (Number.isFinite(h)) body.height_cm = h;
    if (Number.isFinite(a) && a > 0) body.age_years = a;
    if (sex === "male" || sex === "female") body.sex = sex;
    apiClient.updateUserProfile(config, body).then(() => {
      setSaving(false);
    }).catch((e: unknown) => {
      setError(apiErrorMessage(e));
      setSaving(false);
    });
  };

  return (
    <>
      {error ? <p style={{ fontSize: 12, color: "var(--warn)" }}>{error}</p> : null}
      <div className="row gap-8">
        <div className="field" style={{ flex: 1 }}>
          <label>вес, кг</label>
          <input inputMode="decimal" onChange={(e) => setWeight(e.target.value)} placeholder="70" value={weight} />
        </div>
        <div className="field" style={{ flex: 1 }}>
          <label>рост, см</label>
          <input inputMode="decimal" onChange={(e) => setHeight(e.target.value)} placeholder="175" value={height} />
        </div>
      </div>
      <div className="row gap-8" style={{ marginTop: 10 }}>
        <div className="field" style={{ flex: 1 }}>
          <label>возраст</label>
          <input inputMode="numeric" onChange={(e) => setAge(e.target.value)} placeholder="30" value={age} />
        </div>
        <div className="field" style={{ flex: 1 }}>
          <label>пол</label>
          <select onChange={(e) => setSex(e.target.value)} value={sex} style={{ height: 32, width: "100%", padding: "0 10px", border: "1px solid var(--hairline-2)", background: "var(--surface)", fontFamily: "var(--mono)", fontSize: 13, borderRadius: "var(--radius)", color: "var(--ink)", outline: "none" }}>
            <option value="">—</option>
            <option value="male">мужской</option>
            <option value="female">женский</option>
          </select>
        </div>
      </div>
      <button className="btn dark" disabled={saving} onClick={save} type="button" style={{ marginTop: 12 }}>
        {saving ? "Сохраняю..." : "Сохранить профиль"}
      </button>
    </>
  );
}

export function UserProfileSection() {
  return <UserProfileForm />;
}
