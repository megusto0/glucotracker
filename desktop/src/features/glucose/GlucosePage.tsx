import {
  Activity,
  AlertTriangle,
  Plus,
  RefreshCw,
  Save,
} from "lucide-react";
import {
  startTransition,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type Dispatch,
  type FormEvent,
  type HTMLAttributes,
  type ReactNode,
  type SetStateAction,
} from "react";
import {
  apiErrorMessage,
  type GlucoseDashboardResponse,
  type GlucoseMode,
  type SensorSessionResponse,
} from "../../api/client";
import { Button } from "../../design/primitives/Button";
import {
  useImportNightscoutContext,
  useNightscoutSettings,
} from "../nightscout/useNightscout";
import { useApiConfig } from "../settings/settingsStore";
import {
  useCreateFingerstick,
  useGlucoseDashboard,
  useRecalculateSensorCalibration,
  useSaveSensor,
  useSensors,
  useUpdateFingerstick,
  useDeleteFingerstick,
} from "./useGlucoseDashboard";

type RangePreset = "3h" | "6h" | "12h" | "24h" | "7d";
type DashboardPoint = GlucoseDashboardResponse["points"][number];
type Fingerstick = GlucoseDashboardResponse["fingersticks"][number];
type FoodEvent = GlucoseDashboardResponse["food_events"][number];
type InsulinEvent = GlucoseDashboardResponse["insulin_events"][number];
type Artifact = GlucoseDashboardResponse["artifacts"][number];
type ActivityTab = "episodes" | "events";

const rangeButtons: { label: string; value: RangePreset }[] = [
  { label: "3ч", value: "3h" },
  { label: "6ч", value: "6h" },
  { label: "12ч", value: "12h" },
  { label: "24ч", value: "24h" },
  { label: "7д", value: "7d" },
];

const modes: { label: string; value: GlucoseMode }[] = [
  { label: "Raw", value: "raw" },
  { label: "Сглаженная", value: "smoothed" },
  { label: "Нормализованная", value: "normalized" },
];

const pad = (value: number) => value.toString().padStart(2, "0");

const toDateTimeInput = (date: Date) =>
  `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(
    date.getHours(),
  )}:${pad(date.getMinutes())}`;

const toLocalDateTimeSecond = (date: Date) =>
  `${toDateTimeInput(date)}:${pad(date.getSeconds())}`;

const toApiDateTime = (value: string) =>
  value.length === 16 ? `${value}:00` : value;

const fromIsoToInput = (value?: string | null) =>
  value ? value.slice(0, 16) : "";

const presetRange = (preset: RangePreset) => {
  const to = new Date();
  const hours =
    preset === "3h"
      ? 3
      : preset === "6h"
        ? 6
        : preset === "12h"
          ? 12
          : preset === "24h"
            ? 24
            : 24 * 7;
  const from = new Date(to.getTime() - hours * 60 * 60 * 1000);
  return {
    from: toDateTimeInput(from),
    to: toDateTimeInput(to),
  };
};

const formatNumber = (
  value?: number | null,
  digits = 1,
  fallback = "—",
) => (value === null || value === undefined ? fallback : value.toFixed(digits));

const formatSigned = (value?: number | null, digits = 1) => {
  if (value === null || value === undefined) return "—";
  return `${value >= 0 ? "+" : ""}${value.toFixed(digits)}`;
};

const formatDateTime = (value?: string | null) =>
  value
    ? new Intl.DateTimeFormat("ru-RU", {
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        month: "short",
      }).format(new Date(value))
    : "—";

const formatTime = (value?: string | null) =>
  value
    ? new Intl.DateTimeFormat("ru-RU", {
        hour: "2-digit",
        minute: "2-digit",
      }).format(new Date(value))
    : "—";

const formatEpisodeRange = (startAt: string, endAt: string) => {
  const start = formatTime(startAt);
  const end = formatTime(endAt);
  return start === end ? start : `${start}–${end}`;
};

const confidenceLabel = (
  value?: string | null,
  validCalibrationPoints = 0,
) => {
  if (!value || value === "none" || validCalibrationPoints < 2) {
    return "недостаточно данных";
  }
  return (
    {
      low: "низкая",
      medium: "средняя",
      high: "высокая",
    }[value] ?? "недостаточно данных"
  );
};

const sensorPhaseLabel = (
  phase?: string | null,
  ageDays?: number | null,
) => {
  if (phase === "warmup") {
    const hours = Math.min(48, Math.max(0, Math.round((ageDays ?? 0) * 24)));
    return `Автокалибровка: ${hours} ч из 48`;
  }
  if (phase === "stable") return "Стабильная фаза";
  if (phase === "end_of_life") return "Конец срока";
  return "Фаза не определена";
};

const sensorPhaseCompact = (
  phase?: string | null,
  ageDays?: number | null,
) => {
  if (phase === "warmup") {
    const hours = Math.min(48, Math.max(0, Math.round((ageDays ?? 0) * 24)));
    return `автокалибровка ${hours}ч из 48`;
  }
  if (phase === "stable") return "стабильная фаза";
  if (phase === "end_of_life") return "конец срока";
  return "фаза не определена";
};

const fingerstickCountLabel = (count: number) => {
  const mod10 = Math.abs(count) % 10;
  const mod100 = Math.abs(count) % 100;
  const word =
    mod10 === 1 && mod100 !== 11
      ? "запись"
      : mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)
        ? "записи"
        : "записей";
  return `${count} ${word} из пальца`;
};

const calibrationStrategyLabel = (strategy?: string | null) =>
  ({
    insufficient: "недостаточно данных",
    linear: "линейная",
    median_delta: "медиана Δ",
    warmup_blend: "автокалибровка",
  })[strategy ?? ""] ?? "—";

const warmupSequenceText = (values?: number[] | null) => {
  const filtered = (values ?? []).filter((value) => Number.isFinite(value));
  if (filtered.length < 2) return null;
  return filtered.map((value) => formatSigned(value)).join("  ");
};

const blankToNull = (value: string) => {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
};

type SensorForm = {
  ended_at: string;
  expected_life_days: string;
  label: string;
  model: string;
  notes: string;
  source: string;
  started_at: string;
  vendor: string;
};

const emptySensorForm = (): SensorForm => ({
  ended_at: "",
  expected_life_days: "15",
  label: "",
  model: "",
  notes: "",
  source: "manual",
  started_at: toDateTimeInput(new Date()),
  vendor: "",
});

const sensorToForm = (sensor: SensorSessionResponse): SensorForm => ({
  ended_at: fromIsoToInput(sensor.ended_at),
  expected_life_days: String(sensor.expected_life_days ?? 15),
  label: sensor.label ?? "",
  model: sensor.model ?? "",
  notes: sensor.notes ?? "",
  source: sensor.source ?? "manual",
  started_at: fromIsoToInput(sensor.started_at),
  vendor: sensor.vendor ?? "",
});

const sensorName = (sensor?: SensorSessionResponse | null) =>
  sensor?.label || sensor?.model || sensor?.vendor || "Сенсор";

const currentCorrection = (point?: DashboardPoint | null) => {
  if (!point) return null;
  if (point.correction_mmol_l !== null && point.correction_mmol_l !== undefined) {
    return point.correction_mmol_l;
  }
  if (point.normalized_value !== null && point.normalized_value !== undefined) {
    return point.normalized_value - point.raw_value;
  }
  return null;
};

const foodEventKcal = (event: FoodEvent) => event.kcal ?? 0;

export function GlucosePage() {
  const config = useApiConfig();
  const initialRange = useMemo(() => presetRange("6h"), []);
  const [preset, setPreset] = useState<RangePreset | "custom">("6h");
  const [fromInput, setFromInput] = useState(initialRange.from);
  const [toInput, setToInput] = useState(initialRange.to);
  const [mode, setMode] = useState<GlucoseMode>("normalized");
  const [activityTab, setActivityTab] = useState<ActivityTab>("episodes");
  const [selectedEpisodeId, setSelectedEpisodeId] = useState<string | null>(null);
  const [fingerstickAt, setFingerstickAt] = useState(toDateTimeInput(new Date()));
  const [fingerstickValue, setFingerstickValue] = useState("");
  const [meterName, setMeterName] = useState("");
  const [editingFingerstickId, setEditingFingerstickId] = useState<string | null>(null);
  const [lastImportAt, setLastImportAt] = useState<string | null>(null);
  const [showFingerstickForm, setShowFingerstickForm] = useState(false);
  const [showSensorEdit, setShowSensorEdit] = useState(false);
  const [sensorForm, setSensorForm] = useState<SensorForm>(() => emptySensorForm());
  const autoImportKeyRef = useRef("");

  const from = toApiDateTime(fromInput);
  const to = toApiDateTime(toInput);
  const dashboard = useGlucoseDashboard(from, to, mode);
  const sensors = useSensors();
  const nightscoutSettings = useNightscoutSettings();
  const nightscoutImport = useImportNightscoutContext(from, to);
  const importNightscout = nightscoutImport.mutate;
  const nightscoutImportPending = nightscoutImport.isPending;
  const importPendingRef = useRef(nightscoutImportPending);
  importPendingRef.current = nightscoutImportPending;
  const createFingerstick = useCreateFingerstick();
  const updateFingerstick = useUpdateFingerstick();
  const deleteFingerstick = useDeleteFingerstick();
  const saveSensor = useSaveSensor();
  const recalculate = useRecalculateSensorCalibration();

  const data = dashboard.data;
  const currentSensor = data?.current_sensor ?? null;
  const sensorList = sensors.data ?? data?.sensors ?? [];
  const quality = data?.quality;
  const summary = data?.summary;
  const latestPoint = data?.points.length
    ? data.points[data.points.length - 1]
    : null;
  const previousPoint =
    data && data.points.length > 1 ? data.points[data.points.length - 2] : null;
  const correction = currentCorrection(latestPoint);
  const normalizedAvailable = latestPoint?.normalized_value !== undefined && latestPoint?.normalized_value !== null;
  const validCalibrationPoints = quality?.valid_calibration_points ?? 0;
  const trust = confidenceLabel(summary?.calibration_confidence, validCalibrationPoints);
  const events = useMemo(() => buildEventRows(data), [data]);
  const episodes = useMemo(() => buildGroupedEpisodes(data), [data]);
  const recentFingersticks = (data?.fingersticks ?? []).slice(-4).reverse();

  useEffect(() => {
    if (
      selectedEpisodeId &&
      !episodes.some((episode) => episode.id === selectedEpisodeId)
    ) {
      setSelectedEpisodeId(null);
    }
  }, [episodes, selectedEpisodeId]);

  const error = [
    dashboard.error,
    nightscoutImport.error,
    createFingerstick.error,
    updateFingerstick.error,
    deleteFingerstick.error,
    saveSensor.error,
    recalculate.error,
  ].find(Boolean);

  useEffect(() => {
    setSensorForm(currentSensor ? sensorToForm(currentSensor) : emptySensorForm());
  }, [currentSensor?.id, currentSensor?.updated_at]);

  const canImportNightscout = Boolean(
    config.token.trim() &&
      nightscoutSettings.data?.configured &&
      nightscoutSettings.data?.sync_glucose,
  );

  const refreshNightscout = useCallback(() => {
    const settings = nightscoutSettings.data;
    if (!settings?.configured || !settings.sync_glucose || importPendingRef.current) {
      return;
    }
    const nextRange =
      preset === "custom"
        ? { from: fromInput, to: toInput }
        : presetRange(preset);
    if (!nextRange.from || !nextRange.to) return;
    if (preset !== "custom") {
      startTransition(() => {
        setFromInput(nextRange.from);
        setToInput(nextRange.to);
      });
    }
    importNightscout(
      {
        from_datetime: toApiDateTime(nextRange.from),
        to_datetime: toApiDateTime(nextRange.to),
        sync_glucose: true,
        import_insulin_events: Boolean(settings.import_insulin_events),
      },
      {
        onSuccess: () => setLastImportAt(new Date().toISOString()),
      },
    );
  }, [
    fromInput,
    importNightscout,
    nightscoutSettings.data,
    preset,
    toInput,
  ]);

  useEffect(() => {
    if (!canImportNightscout) {
      autoImportKeyRef.current = "";
      return;
    }
    const settings = nightscoutSettings.data;
    const autoImportKey =
      preset === "custom"
        ? `${preset}|${fromInput}|${toInput}|${settings?.import_insulin_events ? "insulin" : "glucose"}`
        : `${preset}|${settings?.import_insulin_events ? "insulin" : "glucose"}`;
    if (autoImportKeyRef.current !== autoImportKey) {
      autoImportKeyRef.current = autoImportKey;
      refreshNightscout();
    }
    const timer = window.setInterval(refreshNightscout, 5 * 60 * 1000);
    return () => window.clearInterval(timer);
  }, [
    canImportNightscout,
    fromInput,
    nightscoutSettings.data,
    preset,
    refreshNightscout,
    toInput,
  ]);

  const applyPreset = (value: RangePreset) => {
    const next = presetRange(value);
    startTransition(() => {
      setPreset(value);
      setFromInput(next.from);
      setToInput(next.to);
    });
  };

  const resetFingerstickForm = () => {
    setEditingFingerstickId(null);
    setFingerstickValue("");
    setFingerstickAt(toDateTimeInput(new Date()));
    setMeterName("");
    setShowFingerstickForm(false);
  };

  const openNewFingerstickForm = () => {
    setEditingFingerstickId(null);
    setFingerstickValue("");
    setFingerstickAt(toDateTimeInput(new Date()));
    setShowFingerstickForm(true);
  };

  const editFingerstick = (row: Fingerstick) => {
    setEditingFingerstickId(row.id);
    setFingerstickAt(fromIsoToInput(row.measured_at));
    setFingerstickValue(String(row.glucose_mmol_l));
    setMeterName(row.meter_name ?? "");
    setShowFingerstickForm(true);
  };

  const submitFingerstick = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const value = Number(fingerstickValue.replace(",", "."));
    if (!fingerstickAt || !Number.isFinite(value) || value <= 0) return;
    const body = {
      glucose_mmol_l: value,
      measured_at: toApiDateTime(fingerstickAt),
      meter_name: blankToNull(meterName),
    };
    if (editingFingerstickId) {
      updateFingerstick.mutate(
        { body, fingerstickId: editingFingerstickId },
        { onSuccess: resetFingerstickForm },
      );
      return;
    }
    createFingerstick.mutate(body, { onSuccess: resetFingerstickForm });
  };

  const deleteFingerstickHandler = () => {
    if (!editingFingerstickId) return;
    if (confirm("Удалить эту запись из пальца?")) {
      deleteFingerstick.mutate(editingFingerstickId, { onSuccess: resetFingerstickForm });
    }
  };

  const submitSensor = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!sensorForm.started_at) return;
    const expectedLife = Number(sensorForm.expected_life_days);
    saveSensor.mutate(
      {
        sensorId: currentSensor?.id,
        body: {
          ended_at: sensorForm.ended_at ? toApiDateTime(sensorForm.ended_at) : null,
          expected_life_days:
            Number.isFinite(expectedLife) && expectedLife > 0 ? expectedLife : 15,
          label: blankToNull(sensorForm.label),
          model: blankToNull(sensorForm.model),
          notes: blankToNull(sensorForm.notes),
          source: sensorForm.source.trim() || "manual",
          started_at: toApiDateTime(sensorForm.started_at),
          vendor: blankToNull(sensorForm.vendor),
        },
      },
      {
        onSuccess: () => setShowSensorEdit(false),
      },
    );
  };

  const nightscoutImportStatus = nightscoutImportPending
    ? "Обновляю Nightscout..."
    : lastImportAt
      ? `Обновлено ${formatTime(lastImportAt)}`
      : canImportNightscout
        ? "Автообновление каждые 5 минут"
        : nightscoutSettings.isLoading
          ? "Проверяю настройки Nightscout..."
          : nightscoutSettings.data?.configured
            ? "Синхронизация глюкозы выключена в настройках"
            : "Nightscout не подключён";

  return (
    <div className="min-h-screen bg-[var(--bg)] px-5 py-5 sm:px-8 lg:px-10">
      <header className="flex flex-col gap-2 pb-4">
        <p className="flex items-center gap-2 text-[11px] uppercase tracking-[0.08em] text-[var(--muted)]">
          <Activity size={14} />
          NIGHTSCOUT / ЛОКАЛЬНЫЙ КОНТЕКСТ
        </p>
        <h1 className="font-mono text-[46px] font-normal leading-none text-[var(--fg)] sm:text-[56px]">
          Глюкоза
        </h1>
      </header>

      {!config.token.trim() ? (
        <div className="mb-5 border border-[var(--hairline)] bg-[var(--surface)] p-4 text-[14px] text-[var(--muted)]">
          Укажите токен backend в настройках, чтобы загрузить локальные данные
          Nightscout.
        </div>
      ) : null}

      {error ? (
        <div className="mb-5 flex items-start gap-3 border border-[var(--danger)] bg-[var(--surface)] p-4 text-[14px] text-[var(--danger)]">
          <AlertTriangle size={18} />
          {apiErrorMessage(error)}
        </div>
      ) : null}

      <section className="grid gap-6 2xl:grid-cols-[minmax(0,1fr)_360px]">
        <main className="grid min-w-0 gap-5">
          <HeroSummary
            correction={correction}
            latestPoint={latestPoint}
            normalizedAvailable={normalizedAvailable}
            previousPoint={previousPoint}
            quality={quality}
            sensor={currentSensor}
            summary={summary}
            trust={trust}
          />

          <section className="border border-[var(--hairline)] bg-[var(--surface)]">
            <div className="grid gap-4 border-b border-[var(--hairline)] px-5 py-4 xl:grid-cols-[minmax(260px,1fr)_auto] xl:items-start">
              <div>
                <h2 className="text-[18px] text-[var(--fg)]">График глюкозы</h2>
                <p className="mt-1 max-w-[640px] text-[12px] text-[var(--muted)]">
                  Raw CGM сохраняется без изменений. Нормализация влияет только
                  на отображение.
                </p>
              </div>

              <div className="grid gap-3">
                <div className="flex flex-wrap justify-start gap-2 xl:justify-end">
                  {rangeButtons.map((item) => (
                    <button
                      className={`border px-3 py-2 text-[12px] uppercase tracking-[0.06em] ${
                        preset === item.value
                          ? "border-[var(--fg)] bg-[var(--fg)] text-[var(--surface)]"
                          : "border-[var(--hairline)] bg-[var(--surface)] text-[var(--muted)]"
                      }`}
                      key={item.value}
                      onClick={() => applyPreset(item.value)}
                      type="button"
                    >
                      {item.label}
                    </button>
                  ))}
                  <Button
                    disabled={!canImportNightscout || nightscoutImportPending}
                    icon={<RefreshCw size={14} />}
                    onClick={refreshNightscout}
                    variant="primary"
                  >
                    Подтянуть актуальные данные
                  </Button>
                </div>

                <div className="flex flex-wrap gap-2 xl:justify-end">
                  <label className="grid gap-1 text-[10px] uppercase tracking-[0.06em] text-[var(--muted)]">
                    от
                    <input
                      className="h-9 border border-[var(--hairline)] bg-[var(--surface)] px-2 text-[12px] text-[var(--fg)]"
                      onChange={(event) => {
                        setPreset("custom");
                        setFromInput(event.target.value);
                      }}
                      type="datetime-local"
                      value={fromInput}
                    />
                  </label>
                  <label className="grid gap-1 text-[10px] uppercase tracking-[0.06em] text-[var(--muted)]">
                    до
                    <input
                      className="h-9 border border-[var(--hairline)] bg-[var(--surface)] px-2 text-[12px] text-[var(--fg)]"
                      onChange={(event) => {
                        setPreset("custom");
                        setToInput(event.target.value);
                      }}
                      type="datetime-local"
                      value={toInput}
                    />
                  </label>
                </div>

                <div className="flex flex-wrap items-center gap-2 xl:justify-end">
                  {modes.map((item) => (
                    <button
                      className={`border px-3 py-2 text-[12px] uppercase tracking-[0.06em] ${
                        mode === item.value
                          ? "border-[var(--fg)] bg-[var(--fg)] text-[var(--surface)]"
                          : "border-[var(--hairline)] bg-[var(--surface)] text-[var(--muted)]"
                      }`}
                      key={item.value}
                      onClick={() => setMode(item.value)}
                      type="button"
                    >
                      {item.label}
                    </button>
                  ))}
                  <span className="text-[12px] text-[var(--muted)]">
                    {nightscoutImportStatus}
                  </span>
                </div>
              </div>
            </div>

            <GlucoseChart
              data={data}
              episodes={episodes}
              loading={dashboard.isLoading}
              mode={mode}
              onEpisodeSelect={setSelectedEpisodeId}
              selectedEpisodeId={selectedEpisodeId}
            />
          </section>

          <GlucoseActivityPanel
            activeTab={activityTab}
            episodes={episodes}
            onTabChange={setActivityTab}
            onEpisodeSelect={setSelectedEpisodeId}
            rows={events}
            selectedEpisodeId={selectedEpisodeId}
          />
        </main>

        <SensorQualityPanel
          editingFingerstickId={editingFingerstickId}
          fingerstickAt={fingerstickAt}
          fingerstickPending={createFingerstick.isPending || updateFingerstick.isPending}
          fingerstickValue={fingerstickValue}
          meterName={meterName}
          onCancelFingerstickForm={resetFingerstickForm}
          onDeleteFingerstick={deleteFingerstickHandler}
          onEditFingerstick={editFingerstick}
          onFingerstickAtChange={setFingerstickAt}
          onFingerstickValueChange={setFingerstickValue}
          onMeterNameChange={setMeterName}
          onRecalculate={() => {
            if (currentSensor?.id) recalculate.mutate(currentSensor.id);
          }}
          onSensorFormChange={setSensorForm}
          artifactCount={data?.artifacts.length ?? 0}
          points={data?.points ?? []}
          quality={quality}
          recentFingersticks={recentFingersticks}
          recalculatePending={recalculate.isPending}
          saveSensor={saveSensor}
          sensor={currentSensor}
          sensorForm={sensorForm}
          sensorList={sensorList}
          showFingerstickForm={showFingerstickForm}
          showSensorEdit={showSensorEdit}
          submitFingerstick={submitFingerstick}
          submitSensor={submitSensor}
          openNewFingerstickForm={openNewFingerstickForm}
          toggleSensorEdit={() => setShowSensorEdit((value) => !value)}
        />

        <BiasOverLifetimeChart data={data?.bias_over_lifetime ?? null} />
      </section>
    </div>
  );
}

function HeroSummary({
  correction,
  latestPoint,
  normalizedAvailable,
  previousPoint,
  quality,
  sensor,
  summary,
  trust,
}: {
  correction: number | null;
  latestPoint: DashboardPoint | null;
  normalizedAvailable: boolean;
  previousPoint: DashboardPoint | null;
  quality?: GlucoseDashboardResponse["quality"];
  sensor: SensorSessionResponse | null;
  summary?: GlucoseDashboardResponse["summary"];
  trust: string;
}) {
  const current = summary?.current_glucose ?? latestPoint?.display_value;
  const correctionEstimate =
    quality?.correction_now_mmol_l ?? summary?.bias_mmol_l ?? correction;
  const validCalibrationPoints = quality?.valid_calibration_points ?? 0;
  const delta =
    latestPoint && previousPoint
      ? latestPoint.display_value - previousPoint.display_value
      : 0;
  const trend = delta > 0.2 ? "↑" : delta < -0.2 ? "↓" : "→";
  const phaseText = sensorPhaseLabel(
    quality?.sensor_phase,
    quality?.sensor_age_days,
  );

  return (
    <section className="grid gap-4 border border-[var(--hairline)] bg-[var(--surface)] p-5 lg:grid-cols-[minmax(220px,0.9fr)_minmax(280px,1.2fr)_minmax(220px,0.8fr)] lg:items-center">
      <div>
        <div className="text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">
          сейчас
        </div>
        <div className="mt-2 flex items-end gap-3">
          <span className="font-mono text-[48px] leading-none text-[var(--fg)]">
            {formatNumber(current)}
          </span>
          <span className="mb-1 text-[13px] text-[var(--muted)]">ммоль/л</span>
          <span className="mb-0.5 font-mono text-[30px] text-[var(--fg)]">
            {trend}
          </span>
        </div>
      </div>

      <div className="border-y border-[var(--hairline)] py-3 lg:border-x lg:border-y-0 lg:px-6 lg:py-0">
        <div className="font-mono text-[18px] text-[var(--fg)]">
          {normalizedAvailable ? (
            `Смещение в этот момент ${formatSigned(correctionEstimate)} ммоль/л`
          ) : (
            "Нормализация недоступна: мало записей из пальца"
          )}
        </div>
        <div className="mt-2 font-mono text-[12px] text-[var(--muted)]">
          {fingerstickCountLabel(validCalibrationPoints)} ·{" "}
          {sensorPhaseCompact(quality?.sensor_phase, quality?.sensor_age_days)}
          {latestPoint?.contributing_fingerstick_count != null && latestPoint.contributing_fingerstick_count > 0 ? (
            <> · из пальца: {latestPoint.contributing_fingerstick_count}</>
          ) : null}
          {latestPoint?.nearest_fingerstick_distance_min != null ? (
            <> · ближайшее: {formatNumber(latestPoint.nearest_fingerstick_distance_min, 0)} мин</>
          ) : null}
        </div>
        <div className="mt-1 text-[12px] text-[var(--muted)]">
          Raw CGM сохраняется без изменений
        </div>
      </div>

      <div className="grid gap-2 text-[13px]">
        <div className="font-mono text-[20px] text-[var(--fg)]">
          {sensorName(sensor)}{" "}
          <span className="text-[var(--muted)]">
            день {formatNumber(quality?.sensor_age_days)} /{" "}
            {formatNumber(sensor?.expected_life_days, 0)}
          </span>
        </div>
        <div className="text-[var(--muted)]">
          Доверие: <span className="text-[var(--fg)]">{trust}</span>
        </div>
        <div className="text-[12px] text-[var(--muted)]">{phaseText}</div>
      </div>
    </section>
  );
}

function SensorQualityPanel({
  editingFingerstickId,
  fingerstickAt,
  fingerstickPending,
  fingerstickValue,
  meterName,
  onCancelFingerstickForm,
  onDeleteFingerstick,
  onEditFingerstick,
  onFingerstickAtChange,
  onFingerstickValueChange,
  onMeterNameChange,
  onRecalculate,
  onSensorFormChange,
  artifactCount,
  points,
  quality,
  recentFingersticks,
  recalculatePending,
  saveSensor,
  sensor,
  sensorForm,
  sensorList,
  showFingerstickForm,
  showSensorEdit,
  submitFingerstick,
  submitSensor,
  openNewFingerstickForm,
  toggleSensorEdit,
}: {
  artifactCount: number;
  editingFingerstickId: string | null;
  fingerstickAt: string;
  fingerstickPending: boolean;
  fingerstickValue: string;
  meterName: string;
  onCancelFingerstickForm: () => void;
  onDeleteFingerstick: () => void;
  onEditFingerstick: (row: Fingerstick) => void;
  onFingerstickAtChange: (value: string) => void;
  onFingerstickValueChange: (value: string) => void;
  onMeterNameChange: (value: string) => void;
  onRecalculate: () => void;
  onSensorFormChange: Dispatch<SetStateAction<SensorForm>>;
  points: DashboardPoint[];
  quality?: GlucoseDashboardResponse["quality"];
  recentFingersticks: Fingerstick[];
  recalculatePending: boolean;
  saveSensor: ReturnType<typeof useSaveSensor>;
  sensor: SensorSessionResponse | null;
  sensorForm: SensorForm;
  sensorList: SensorSessionResponse[];
  showFingerstickForm: boolean;
  showSensorEdit: boolean;
  submitFingerstick: (event: FormEvent<HTMLFormElement>) => void;
  submitSensor: (event: FormEvent<HTMLFormElement>) => void;
  openNewFingerstickForm: () => void;
  toggleSensorEdit: () => void;
}) {
  const validCalibrationPoints = quality?.valid_calibration_points ?? 0;
  const enoughCalibration = validCalibrationPoints >= 1;
  const correctionEstimate =
    quality?.correction_now_mmol_l ??
    quality?.median_delta_mmol_l ??
    quality?.median_bias_mmol_l;
  const deltaRange =
    quality?.delta_min_mmol_l !== null &&
    quality?.delta_min_mmol_l !== undefined &&
    quality?.delta_max_mmol_l !== null &&
    quality?.delta_max_mmol_l !== undefined
      ? `${formatSigned(quality.delta_min_mmol_l)}…${formatSigned(
          quality.delta_max_mmol_l,
        )}`
      : "—";
  const phaseText = sensorPhaseLabel(
    quality?.sensor_phase,
    quality?.sensor_age_days,
  );
  const warmupMetrics = quality?.warmup_metrics;
  const warmupResiduals = warmupSequenceText(
    warmupMetrics?.residual_sequence_mmol_l,
  );
  const warmupBehaviorDetected =
    Boolean(warmupResiduals) &&
    (warmupMetrics?.warmup_instability_score ?? 0) >= 0.8;
  const calibrationBasisNote =
    quality?.calibration_basis === "warmup_after_12h_fallback"
      ? "Оценка смещения построена по данным после 12 ч, информационно."
      : null;

  return (
    <aside className="grid h-fit gap-5 border border-[var(--hairline)] bg-[var(--surface)] p-5 2xl:sticky 2xl:top-5">
      <PanelSection title="Текущий сенсор">
        {sensor ? (
          <div className="grid gap-3">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="font-mono text-[22px] text-[var(--fg)]">
                  {sensorName(sensor)}
                </div>
                <div className="mt-1 text-[12px] text-[var(--muted)]">
                  {sensor.vendor || "производитель —"} /{" "}
                  {sensor.model || "модель —"}
                </div>
              </div>
              <span className="border border-[var(--hairline)] px-2 py-1 text-[10px] uppercase tracking-[0.08em] text-[var(--fg)]">
                active
              </span>
            </div>
            <div className="font-mono text-[15px] text-[var(--muted)]">
              день {formatNumber(quality?.sensor_age_days)} /{" "}
              {formatNumber(sensor.expected_life_days, 0)}
            </div>
          </div>
        ) : (
          <p className="text-[13px] text-[var(--muted)]">
            В выбранном диапазоне нет активного сенсора.
          </p>
        )}
      </PanelSection>

      <PanelSection title="Фаза">
        <div className="grid gap-2 border border-[var(--hairline)] bg-[var(--bg)] p-3 text-[13px]">
          <div className="font-mono text-[18px] text-[var(--fg)]">{phaseText}</div>
          <p className="text-[12px] text-[var(--muted)]">
            Фаза влияет только на оценку качества и отображение нормализации.
          </p>
        </div>
      </PanelSection>

      <PanelSection title="Качество">
        <div className="grid gap-3 text-[13px]">
          <div className="font-mono text-[28px] leading-none text-[var(--fg)]">
            {enoughCalibration
              ? `${quality?.quality_score ?? 0}/100`
              : "Качество не рассчитано"}
          </div>
          <div className="grid grid-cols-2 gap-3 text-[12px]">
            <Metric
              label="Артефакты"
              value={String(artifactCount)}
            />
            <Metric
              label="Compression lows"
              value={String(quality?.suspected_compression_count ?? 0)}
            />
            <Metric label="Noise" value={formatNumber(quality?.noise_score)} />
            <Metric
              label="Доверие"
              value={confidenceLabel(quality?.confidence, validCalibrationPoints)}
            />
          </div>
        </div>
      </PanelSection>

      <PanelSection title="Оценка смещения">
        {enoughCalibration ? (
          <div className="grid gap-3">
            <div className="grid gap-1 border border-[var(--hairline)] bg-[var(--bg)] p-3">
              <div className="font-mono text-[24px] leading-none text-[var(--fg)]">
                Оценка смещения {formatSigned(correctionEstimate)} ммоль/л
              </div>
              <div className="text-[12px] text-[var(--muted)]">
                {fingerstickCountLabel(validCalibrationPoints)} ·{" "}
                {sensorPhaseCompact(quality?.sensor_phase, quality?.sensor_age_days)}
              </div>
              <div className="text-[12px] text-[var(--muted)]">
                Raw CGM сохраняется без изменений
              </div>
            </div>
            <dl className="grid grid-cols-2 gap-3 text-[12px]">
              <Metric
                label="Медиана Δ"
                value={`${formatSigned(quality?.median_delta_mmol_l)} ммоль/л`}
              />
              <Metric
                label="Диапазон Δ"
                value={`${deltaRange} ммоль/л`}
              />
              <Metric
                label="b0"
                value={`${formatSigned(quality?.b0_mmol_l)} ммоль/л`}
              />
              <Metric
                label="b1 raw"
                value={`${formatSigned(quality?.b1_raw_mmol_l_per_day)} / день`}
              />
              <Metric
                label="b1 capped"
                value={`${formatSigned(quality?.b1_capped_mmol_l_per_day)} / день`}
              />
              <Metric label="MARD" value={`${formatNumber(quality?.mard_percent)}%`} />
              <Metric
                label="Модель"
                value={calibrationStrategyLabel(quality?.calibration_strategy)}
              />
            </dl>
            {calibrationBasisNote ? (
              <p className="text-[12px] text-[var(--muted)]">
                {calibrationBasisNote}
              </p>
            ) : null}
            {warmupBehaviorDetected ? (
              <p className="text-[12px] text-[var(--muted)]">
                В первые 12 ч расхождение менялось: {warmupResiduals} ммоль/л.
              </p>
            ) : null}
          </div>
        ) : (
          <div className="grid gap-2 text-[13px] text-[var(--muted)]">
            <p className="text-[var(--fg)]">Оценка смещения: недостаточно данных</p>
            <p>{fingerstickCountLabel(quality?.fingerstick_count ?? 0)}</p>
            <p>Нужна хотя бы 1 валидная запись после 12 ч сенсора</p>
            {warmupBehaviorDetected ? (
              <p>
                В первые 12 ч расхождение менялось: {warmupResiduals} ммоль/л.
              </p>
            ) : null}
          </div>
        )}
      </PanelSection>

      <PanelSection title="Действия">
        <div className="grid gap-2">
          <Button
            icon={<Plus size={14} />}
            onClick={openNewFingerstickForm}
            variant="primary"
          >
            + Запись из пальца
          </Button>
          <Button onClick={toggleSensorEdit}>
            {sensor ? "Редактировать сенсор" : "Создать сенсор"}
          </Button>
          {sensor?.id ? (
            <Button
              disabled={recalculatePending}
              icon={<RefreshCw size={14} />}
              onClick={onRecalculate}
            >
              Пересчитать
            </Button>
          ) : null}
        </div>
      </PanelSection>

      {showFingerstickForm ? (
        <form
          className="grid gap-3 border-y border-[var(--hairline)] py-4"
          onSubmit={submitFingerstick}
        >
          <h3 className="text-[13px] uppercase tracking-[0.06em] text-[var(--fg)]">
            {editingFingerstickId ? "Редактировать запись из пальца" : "Новая запись из пальца"}
          </h3>
          <DateTimeInput
            label="время"
            onChange={onFingerstickAtChange}
            value={fingerstickAt}
          />
          <div className="grid gap-3 sm:grid-cols-2 2xl:grid-cols-1">
            <TextInput
              inputMode="decimal"
              label="глюкоза, ммоль/л"
              onChange={onFingerstickValueChange}
              placeholder="6.8"
              value={fingerstickValue}
            />
            <TextInput
              label="глюкометр"
              onChange={onMeterNameChange}
              placeholder="опционально"
              value={meterName}
            />
          </div>
          <div className="grid gap-2 sm:grid-cols-2 2xl:grid-cols-1">
            <Button
              disabled={fingerstickPending || !fingerstickValue.trim()}
              icon={editingFingerstickId ? <Save size={14} /> : <Plus size={14} />}
              type="submit"
              variant="primary"
            >
              {editingFingerstickId ? "Сохранить изменения" : "Добавить"}
            </Button>
            {editingFingerstickId ? (
              <Button
                disabled={fingerstickPending}
                onClick={onDeleteFingerstick}
                type="button"
                variant="danger"
              >
                Удалить
              </Button>
            ) : null}
            <Button onClick={onCancelFingerstickForm} type="button">
              Отмена
            </Button>
          </div>
        </form>
      ) : null}

      {showSensorEdit ? (
        <form className="grid gap-3 border-y border-[var(--hairline)] py-4" onSubmit={submitSensor}>
          <h3 className="text-[13px] uppercase tracking-[0.06em] text-[var(--fg)]">
            {sensor ? "Параметры сенсора" : "Новый сенсор"}
          </h3>
          <div className="grid gap-3 sm:grid-cols-2 2xl:grid-cols-1">
            <TextInput
              label="производитель"
              onChange={(vendor) =>
                onSensorFormChange((state) => ({ ...state, vendor }))
              }
              value={sensorForm.vendor}
            />
            <TextInput
              label="модель"
              onChange={(model) =>
                onSensorFormChange((state) => ({ ...state, model }))
              }
              value={sensorForm.model}
            />
          </div>
          <TextInput
            label="метка"
            onChange={(label) =>
              onSensorFormChange((state) => ({ ...state, label }))
            }
            value={sensorForm.label}
          />
          <div className="grid gap-3 sm:grid-cols-2 2xl:grid-cols-1">
            <DateTimeInput
              label="старт"
              onChange={(started_at) =>
                onSensorFormChange((state) => ({ ...state, started_at }))
              }
              value={sensorForm.started_at}
            />
            <DateTimeInput
              label="конец"
              onChange={(ended_at) =>
                onSensorFormChange((state) => ({ ...state, ended_at }))
              }
              value={sensorForm.ended_at}
            />
          </div>
          <TextInput
            label="заметки"
            onChange={(notes) =>
              onSensorFormChange((state) => ({ ...state, notes }))
            }
            value={sensorForm.notes}
          />
          <Button
            disabled={saveSensor.isPending || !sensorForm.started_at}
            icon={<Save size={14} />}
            type="submit"
            variant="primary"
          >
            Сохранить сенсор
          </Button>
        </form>
      ) : null}

      <PanelSection title="Последние записи из пальца">
        {recentFingersticks.length ? (
          <div className="grid gap-2">
            {recentFingersticks.map((row) => {
              const nearest = nearestPoint(points, row.measured_at);
              const delta = nearest ? row.glucose_mmol_l - nearest.raw_value : null;
              return (
                <div
                  className="grid grid-cols-[52px_1fr_auto_auto] items-center gap-3 border border-[var(--hairline)] bg-[var(--bg)] px-3 py-2 text-[12px]"
                  key={row.id}
                >
                  <span className="font-mono text-[var(--fg)]">
                    {formatTime(row.measured_at)}
                  </span>
                  <span className="font-mono text-[var(--fg)]">
                    {formatNumber(row.glucose_mmol_l)} ммоль/л
                  </span>
                  <span className="font-mono text-[var(--muted)]">
                    Δ {formatSigned(delta)}
                  </span>
                  <button
                    className="border border-[var(--hairline)] bg-[var(--surface)] px-2 py-1 text-[10px] uppercase tracking-[0.06em] text-[var(--muted)] transition hover:text-[var(--fg)]"
                    onClick={() => onEditFingerstick(row)}
                    type="button"
                  >
                    изменить
                  </button>
                </div>
              );
            })}
          </div>
        ) : (
          <p className="text-[13px] text-[var(--muted)]">Записей пока нет.</p>
        )}
      </PanelSection>

      <PanelSection title="Предыдущие сенсоры">
        {sensorList.length ? (
          <div className="grid gap-2">
            {sensorList.slice(0, 5).map((row) => (
              <div
                className="border border-[var(--hairline)] bg-[var(--bg)] p-3 text-[12px]"
                key={row.id}
              >
                <div className="text-[var(--fg)]">{sensorName(row)}</div>
                <div className="mt-1 text-[var(--muted)]">
                  {formatDateTime(row.started_at)} → {formatDateTime(row.ended_at)}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-[13px] text-[var(--muted)]">
            Сенсоры пока не заведены.
          </p>
        )}
      </PanelSection>
    </aside>
  );
}

function PanelSection({
  children,
  title,
}: {
  children: ReactNode;
  title: string;
}) {
  return (
    <section className="grid gap-3">
      <h3 className="text-[11px] uppercase tracking-[0.08em] text-[var(--muted)]">
        {title}
      </h3>
      {children}
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-[10px] uppercase tracking-[0.06em] text-[var(--muted)]">
        {label}
      </dt>
      <dd className="mt-1 text-[var(--fg)]">{value}</dd>
    </div>
  );
}

function TextInput({
  inputMode,
  label,
  onChange,
  placeholder,
  value,
}: {
  inputMode?: HTMLAttributes<HTMLInputElement>["inputMode"];
  label: string;
  onChange: (value: string) => void;
  placeholder?: string;
  value: string;
}) {
  return (
    <label className="grid gap-1 text-[12px] text-[var(--muted)]">
      {label}
      <input
        className="border border-[var(--hairline)] bg-[var(--bg)] px-3 py-2 text-[13px] text-[var(--fg)]"
        inputMode={inputMode}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        value={value}
      />
    </label>
  );
}

function DateTimeInput({
  label,
  onChange,
  value,
}: {
  label: string;
  onChange: (value: string) => void;
  value: string;
}) {
  return (
    <label className="grid gap-1 text-[12px] text-[var(--muted)]">
      {label}
      <input
        className="border border-[var(--hairline)] bg-[var(--bg)] px-3 py-2 text-[13px] text-[var(--fg)]"
        onChange={(event) => onChange(event.target.value)}
        type="datetime-local"
        value={value}
      />
    </label>
  );
}

type EpisodeDetailEvent = {
  data: string;
  id: string;
  label: string;
  sortKey: number;
  time: string;
  type: "food" | "insulin" | "fingerstick";
};

type GroupedEpisode = {
  carbsTotal: number;
  cgmMax: number | null;
  cgmMin: number | null;
  cgmStart: number | null;
  endAt: string;
  fingerstickEvents: Fingerstick[];
  foodEvents: FoodEvent[];
  id: string;
  insulinEvents: InsulinEvent[];
  insulinTotal: number;
  kcalTotal: number;
  startAt: string;
  timeToMax: number | null;
  timeToMin: number | null;
  title: string;
  type: "meal";
};

function GlucoseActivityPanel({
  activeTab,
  episodes,
  onEpisodeSelect,
  onTabChange,
  rows,
  selectedEpisodeId,
}: {
  activeTab: ActivityTab;
  episodes: GroupedEpisode[];
  onEpisodeSelect: (episodeId: string) => void;
  onTabChange: (tab: ActivityTab) => void;
  rows: EventRow[];
  selectedEpisodeId: string | null;
}) {
  return (
    <section className="border border-[var(--hairline)] bg-[var(--surface)]">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--hairline)] px-5 py-4">
        <div>
          <h2 className="text-[18px] text-[var(--fg)]">Активность на графике</h2>
          <p className="mt-1 text-[12px] text-[var(--muted)]">
            Эпизоды группируют еду и ближайший контекст, raw события доступны отдельно.
          </p>
        </div>
        <div className="flex border border-[var(--hairline)]">
          {[
            { label: "Эпизоды", value: "episodes" as const },
            { label: "События", value: "events" as const },
          ].map((item) => (
            <button
              className={`px-4 py-2 text-[12px] uppercase tracking-[0.06em] ${
                activeTab === item.value
                  ? "bg-[var(--fg)] text-[var(--surface)]"
                  : "bg-[var(--surface)] text-[var(--muted)]"
              }`}
              key={item.value}
              onClick={() => onTabChange(item.value)}
              type="button"
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>
      {activeTab === "episodes" ? (
        <EpisodeList
          episodes={episodes}
          onEpisodeSelect={onEpisodeSelect}
          selectedEpisodeId={selectedEpisodeId}
        />
      ) : (
        <EventsTable rows={rows} />
      )}
    </section>
  );
}

function EpisodeList({
  episodes,
  onEpisodeSelect,
  selectedEpisodeId,
}: {
  episodes: GroupedEpisode[];
  onEpisodeSelect: (episodeId: string) => void;
  selectedEpisodeId: string | null;
}) {
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const toggleEpisode = (id: string) => {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  if (!episodes.length) {
    return (
      <div className="px-5 py-8 text-center text-[13px] text-[var(--muted)]">
        Эпизодов за выбранный период нет.
      </div>
    );
  }

  return (
    <div className="grid">
      {episodes.map((episode) => (
        <EpisodeCard
          episode={episode}
          expanded={expanded.has(episode.id)}
          key={episode.id}
          onToggle={() => {
            onEpisodeSelect(episode.id);
            toggleEpisode(episode.id);
          }}
          selected={selectedEpisodeId === episode.id}
        />
      ))}
    </div>
  );
}

function EpisodeCard({
  episode,
  expanded,
  onToggle,
  selected,
}: {
  episode: GroupedEpisode;
  expanded: boolean;
  onToggle: () => void;
  selected: boolean;
}) {
  const eventCount =
    episode.foodEvents.length +
    episode.insulinEvents.length +
    episode.fingerstickEvents.length;
  const cgmSummary =
    episode.cgmStart !== null && episode.cgmMax !== null
      ? `${formatNumber(episode.cgmStart)} → пик ${formatNumber(episode.cgmMax)}${
          episode.timeToMax !== null ? ` через ${episode.timeToMax} мин` : ""
        }`
      : "CGM контекст недоступен";

  return (
    <article
      className={`border-b border-[var(--hairline)] last:border-b-0 ${
        selected ? "bg-[#F6F0E5]" : ""
      }`}
    >
      <button
        aria-pressed={selected}
        className="grid w-full gap-4 px-5 py-4 text-left transition hover:bg-[var(--bg)] lg:grid-cols-[112px_1fr_180px_220px]"
        onClick={onToggle}
        type="button"
      >
        <div className="font-mono text-[14px] text-[var(--fg)]">
          {formatEpisodeRange(episode.startAt, episode.endAt)}
        </div>
        <div className="grid gap-1">
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-[16px] text-[var(--fg)]">Приём пищи</span>
            <span className="border border-[var(--hairline)] bg-[var(--bg)] px-2 py-1 text-[10px] uppercase tracking-[0.06em] text-[var(--muted)]">
              {eventCount} событий
            </span>
          </div>
          <div className="text-[13px] text-[var(--muted)]">{episode.title}</div>
        </div>
        <div className="grid grid-cols-3 gap-3 font-mono text-[13px] text-[var(--fg)] lg:grid-cols-1">
          <span>{formatNumber(episode.carbsTotal, 1)} г</span>
          <span>{formatNumber(episode.kcalTotal, 0)} ккал</span>
          <span>{formatNumber(episode.insulinTotal, 1)} ЕД</span>
        </div>
        <div className="grid gap-1 text-[12px] text-[var(--muted)]">
          <span>{cgmSummary}</span>
          <span className="text-[10px] uppercase tracking-[0.06em]">
            {expanded ? "свернуть детали" : "показать детали"}
          </span>
        </div>
      </button>
      {expanded ? <EpisodeDetails episode={episode} /> : null}
    </article>
  );
}

function EpisodeDetails({ episode }: { episode: GroupedEpisode }) {
  const rows = episodeDetailRows(episode);
  return (
    <div className="border-t border-[var(--hairline)] bg-[var(--bg)] px-5 py-3">
      <div className="grid gap-2">
        {rows.map((row) => (
          <div
            className="grid gap-2 border border-[var(--hairline)] bg-[var(--surface)] px-3 py-2 text-[13px] sm:grid-cols-[64px_1fr_auto]"
            key={row.id}
          >
            <span className="font-mono text-[var(--fg)]">{row.time}</span>
            <span className="text-[var(--fg)]">{row.label}</span>
            <span className="font-mono text-[var(--muted)]">{row.data}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function EventsTable({ rows }: { rows: EventRow[] }) {
  return (
      <div className="overflow-x-auto">
        <table className="w-full min-w-[760px] border-collapse text-left text-[13px]">
          <thead className="text-[10px] uppercase tracking-[0.08em] text-[var(--muted)]">
            <tr>
              {["Время", "Тип", "Данные", "CGM", "Комментарий"].map((label) => (
                <th className="border-b border-[var(--hairline)] px-5 py-3 font-normal" key={label}>
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.length ? (
              rows.map((row) => (
                <tr className="border-b border-[var(--hairline)] last:border-b-0" key={row.id}>
                  <td className="px-5 py-3 font-mono text-[var(--fg)]">{row.time}</td>
                  <td className="px-5 py-3 text-[var(--fg)]">{row.type}</td>
                  <td className="px-5 py-3 font-mono text-[var(--fg)]">{row.data}</td>
                  <td className="px-5 py-3 font-mono text-[var(--muted)]">{row.cgm}</td>
                  <td className="px-5 py-3 text-[var(--muted)]">{row.comment}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td className="px-5 py-8 text-center text-[var(--muted)]" colSpan={5}>
                  Событий за выбранный период нет.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
  );
}

type EventRow = {
  cgm: string;
  comment: string;
  data: string;
  id: string;
  sortKey: number;
  time: string;
  type: string;
};

function buildEventRows(data?: GlucoseDashboardResponse): EventRow[] {
  if (!data) return [];
  const rows: EventRow[] = [];

  data.food_events.forEach((event, index) => {
    const nearest = nearestPoint(data.points, event.timestamp);
    rows.push({
      cgm: nearest ? `${formatNumber(nearest.raw_value)} raw` : "—",
      comment: event.title,
      data: `${formatNumber(event.carbs_g, 1)}г / ${formatNumber(foodEventKcal(event), 0)} ккал`,
      id: `food-${event.timestamp}-${index}`,
      sortKey: Date.parse(event.timestamp),
      time: formatTime(event.timestamp),
      type: "Еда",
    });
  });

  data.insulin_events.forEach((event, index) => {
    const nearest = nearestPoint(data.points, event.timestamp);
    rows.push({
      cgm: nearest ? `${formatNumber(nearest.raw_value)} raw` : "—",
      comment: event.event_type ?? event.notes ?? "Nightscout",
      data:
        event.insulin_units !== null && event.insulin_units !== undefined
          ? `${formatNumber(event.insulin_units, 1)} ЕД`
          : "—",
      id: `insulin-${event.timestamp}-${index}`,
      sortKey: Date.parse(event.timestamp),
      time: formatTime(event.timestamp),
      type: "Инсулин",
    });
  });

  data.fingersticks.forEach((row) => {
    const nearest = nearestPoint(data.points, row.measured_at);
    const delta = nearest ? row.glucose_mmol_l - nearest.raw_value : null;
    rows.push({
      cgm: nearest
        ? `raw ${formatNumber(nearest.raw_value)} / Δ ${formatSigned(delta)}`
        : "—",
      comment: "проверяется backend для калибровки",
      data: `${formatNumber(row.glucose_mmol_l)} ммоль/л`,
      id: `fingerstick-${row.id}`,
      sortKey: Date.parse(row.measured_at),
      time: formatTime(row.measured_at),
      type: "Из пальца",
    });
  });

  data.artifacts.forEach((artifact, index) => {
    rows.push({
      cgm: "—",
      comment: artifact.label,
      data: artifact.kind,
      id: `artifact-${artifact.start_at}-${index}`,
      sortKey: Date.parse(artifact.start_at),
      time: formatTime(artifact.start_at),
      type: "Артефакт?",
    });
  });

  return rows.sort((left, right) => left.sortKey - right.sortKey);
}

function buildGroupedEpisodes(data?: GlucoseDashboardResponse): GroupedEpisode[] {
  if (!data?.food_events.length) return [];
  const foodEvents = [...data.food_events].sort(
    (left, right) => Date.parse(left.timestamp) - Date.parse(right.timestamp),
  );
  const clusters: FoodEvent[][] = [];
  foodEvents.forEach((event) => {
    const current = clusters[clusters.length - 1];
    const eventMs = Date.parse(event.timestamp);
    const previousMs = current?.length
      ? Date.parse(current[current.length - 1].timestamp)
      : null;
    if (current && previousMs !== null && eventMs - previousMs <= 20 * 60 * 1000) {
      current.push(event);
      return;
    }
    clusters.push([event]);
  });

  return clusters.map((foodCluster, index) => {
    const foodStartMs = Date.parse(foodCluster[0].timestamp);
    const foodEndMs = Date.parse(foodCluster[foodCluster.length - 1].timestamp);
    const insulinEvents = data.insulin_events.filter((event) => {
      const eventMs = Date.parse(event.timestamp);
      return eventMs >= foodStartMs - 30 * 60 * 1000 && eventMs <= foodStartMs + 15 * 60 * 1000;
    });
    const fingerstickEvents = data.fingersticks.filter((event) => {
      const eventMs = Date.parse(event.measured_at);
      return eventMs >= foodStartMs - 20 * 60 * 1000 && eventMs <= foodStartMs + 30 * 60 * 1000;
    });
    const includedTimes = [
      ...foodCluster.map((event) => Date.parse(event.timestamp)),
      ...insulinEvents.map((event) => Date.parse(event.timestamp)),
    ];
    const startMs = Math.min(...includedTimes);
    const endMs = Math.max(...includedTimes, foodEndMs);
    const cgm = cgmSummaryForEpisode(data.points, foodStartMs, foodEndMs);
    const title =
      foodCluster.length === 1
        ? foodCluster[0].title
        : foodCluster.map((event) => event.title).join(", ");
    return {
      carbsTotal: foodCluster.reduce((sum, event) => sum + event.carbs_g, 0),
      cgmMax: cgm.max,
      cgmMin: cgm.min,
      cgmStart: cgm.start,
      endAt: toLocalDateTimeSecond(new Date(endMs)),
      fingerstickEvents,
      foodEvents: foodCluster,
      id: `episode-${foodCluster[0].timestamp}-${index}`,
      insulinEvents,
      insulinTotal: insulinEvents.reduce(
        (sum, event) => sum + (event.insulin_units ?? 0),
        0,
      ),
      kcalTotal: foodCluster.reduce((sum, event) => sum + foodEventKcal(event), 0),
      startAt: toLocalDateTimeSecond(new Date(startMs)),
      timeToMax: cgm.timeToMax,
      timeToMin: cgm.timeToMin,
      title,
      type: "meal" as const,
    };
  });
}

function cgmSummaryForEpisode(
  points: DashboardPoint[],
  foodStartMs: number,
  foodEndMs: number,
) {
  const windowStart = foodStartMs - 20 * 60 * 1000;
  const windowEnd = Math.max(foodEndMs, foodStartMs) + 120 * 60 * 1000;
  const pointsInWindow = points.filter((point) => {
    const pointMs = Date.parse(point.timestamp);
    return pointMs >= windowStart && pointMs <= windowEnd;
  });
  if (!pointsInWindow.length) {
    return { max: null, min: null, start: null, timeToMax: null, timeToMin: null };
  }
  const valueFor = (point: DashboardPoint) =>
    point.display_value ?? point.normalized_value ?? point.smoothed_value ?? point.raw_value;
  const startPoint = pointsInWindow.reduce((best, point) => {
    const distance = Math.abs(Date.parse(point.timestamp) - foodStartMs);
    const bestDistance = Math.abs(Date.parse(best.timestamp) - foodStartMs);
    return distance < bestDistance ? point : best;
  }, pointsInWindow[0]);
  let minPoint = pointsInWindow[0];
  let maxPoint = pointsInWindow[0];
  pointsInWindow.forEach((point) => {
    if (valueFor(point) < valueFor(minPoint)) minPoint = point;
    if (valueFor(point) > valueFor(maxPoint)) maxPoint = point;
  });
  const minutesFromStart = (point: DashboardPoint) =>
    Math.max(0, Math.round((Date.parse(point.timestamp) - foodStartMs) / 60000));
  return {
    max: valueFor(maxPoint),
    min: valueFor(minPoint),
    start: valueFor(startPoint),
    timeToMax: minutesFromStart(maxPoint),
    timeToMin: minutesFromStart(minPoint),
  };
}

function episodeDetailRows(episode: GroupedEpisode): EpisodeDetailEvent[] {
  const rows: EpisodeDetailEvent[] = [];
  episode.insulinEvents.forEach((event, index) => {
    rows.push({
      data:
        event.insulin_units !== null && event.insulin_units !== undefined
          ? `${formatNumber(event.insulin_units, 1)} ЕД`
          : "—",
      id: `insulin-${event.timestamp}-${index}`,
      label: "Инсулин из Nightscout",
      sortKey: Date.parse(event.timestamp),
      time: formatTime(event.timestamp),
      type: "insulin",
    });
  });
  episode.foodEvents.forEach((event, index) => {
    rows.push({
      data: `${formatNumber(event.carbs_g, 1)} г, ${formatNumber(foodEventKcal(event), 0)} ккал`,
      id: `food-${event.timestamp}-${index}`,
      label: event.title,
      sortKey: Date.parse(event.timestamp),
      time: formatTime(event.timestamp),
      type: "food",
    });
  });
  episode.fingerstickEvents.forEach((event) => {
    rows.push({
      data: `${formatNumber(event.glucose_mmol_l, 1)} ммоль/л`,
      id: `fingerstick-${event.id}`,
      label: "Из пальца",
      sortKey: Date.parse(event.measured_at),
      time: formatTime(event.measured_at),
      type: "fingerstick",
    });
  });
  return rows.sort((left, right) => left.sortKey - right.sortKey);
}

function nearestPoint(points: DashboardPoint[], iso: string) {
  if (!points.length) return null;
  const target = Date.parse(iso);
  return points.reduce((best, point) => {
    const currentDistance = Math.abs(Date.parse(point.timestamp) - target);
    const bestDistance = Math.abs(Date.parse(best.timestamp) - target);
    return currentDistance < bestDistance ? point : best;
  }, points[0]);
}

function GlucoseChart({
  data,
  episodes,
  loading,
  mode,
  onEpisodeSelect,
  selectedEpisodeId,
}: {
  data?: GlucoseDashboardResponse;
  episodes: GroupedEpisode[];
  loading: boolean;
  mode: GlucoseMode;
  onEpisodeSelect: (episodeId: string) => void;
  selectedEpisodeId: string | null;
}) {
  const points = data?.points ?? [];
  const width = 1180;
  const height = 610;
  const left = 56;
  const right = 26;
  const eventTop = 22;
  const eventHeight = 56;
  const chartTop = 106;
  const chartHeight = 430;
  const chartBottom = chartTop + chartHeight;
  const overviewTop = 552;
  const overviewHeight = 42;
  const chartWidth = width - left - right;
  const fromMs = data ? Date.parse(data.from_datetime) : Date.now() - 6 * 3600000;
  const toMs = data ? Date.parse(data.to_datetime) : Date.now();
  const duration = Math.max(toMs - fromMs, 1);
  const chartValues = [
    ...points.flatMap((point) => [
      point.raw_value,
      point.smoothed_value,
      point.normalized_value,
      point.display_value,
    ]),
    ...(data?.fingersticks.map((row) => row.glucose_mmol_l) ?? []),
  ].filter((value): value is number => typeof value === "number");
  const minValue = Math.max(0, Math.floor(Math.min(...chartValues, 4) - 1));
  const maxValue = Math.ceil(Math.max(...chartValues, 11) + 1);
  const yRange = Math.max(maxValue - minValue, 1);
  const scaleX = (iso: string) => {
    const ratio = (Date.parse(iso) - fromMs) / duration;
    return left + Math.min(1, Math.max(0, ratio)) * chartWidth;
  };
  const scaleY = (value: number) =>
    chartTop + (1 - (value - minValue) / yRange) * chartHeight;
  const overviewY = (value: number) =>
    overviewTop + (1 - (value - minValue) / yRange) * overviewHeight;
  const line = (
    source: DashboardPoint[],
    value: (point: DashboardPoint) => number | null | undefined,
    scale: (value: number) => number = scaleY,
  ) =>
    source
      .map((point) => {
        const yValue = value(point);
        if (yValue === null || yValue === undefined) return "";
        return `${scaleX(point.timestamp)},${scale(yValue)}`;
      })
      .filter(Boolean)
      .join(" ");
  const rawLine = line(points, (point) => point.raw_value);
  const mainLine = line(points, (point) => {
    if (mode === "normalized") {
      return point.normalized_value ?? point.raw_value;
    }
    if (mode === "smoothed") return point.smoothed_value ?? point.raw_value;
    return point.raw_value;
  });
  const overviewLine = line(points, (point) => point.raw_value, overviewY);
  const xTicks = [0, 0.25, 0.5, 0.75, 1].map((ratio) => fromMs + duration * ratio);
  const yTicks = [0, 0.25, 0.5, 0.75, 1].map(
    (ratio) => minValue + yRange * ratio,
  );
  const longRange = duration > 36 * 60 * 60 * 1000;
  const episodeDensity = episodeDensityForDuration(duration);
  const episodeLayouts = layoutEpisodeChips({
    chartLeft: left,
    chartRight: width - right,
    density: episodeDensity,
    episodes,
    scaleX,
  });

  if (!points.length) {
    return (
      <div
        aria-label="График глюкозы"
        className="grid h-[520px] place-items-center text-[14px] text-[var(--muted)]"
        role="img"
      >
        {loading ? "Загружаю CGM..." : "CGM за период не найден."}
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <svg
        aria-label="График глюкозы"
        className="min-w-[940px] text-[var(--muted)]"
        role="img"
        viewBox={`0 0 ${width} ${height}`}
      >
        <rect fill="var(--surface)" height={height} width={width} />
        <line
          stroke="var(--hairline)"
          x1={left}
          x2={width - right}
          y1={eventTop + eventHeight + 10}
          y2={eventTop + eventHeight + 10}
        />
        <text fill="var(--muted)" fontSize="11" x={left} y={18}>
          события
        </text>

        {data?.artifacts.map((artifact) => {
          const x = scaleX(artifact.start_at);
          const w = Math.max(5, scaleX(artifact.end_at) - x);
          return (
            <rect
              fill="#E9DDC8"
              height={chartHeight}
              key={`${artifact.start_at}-${artifact.kind}`}
              opacity={0.34}
              width={w}
              x={x}
              y={chartTop}
            />
          );
        })}

        {episodes.map((episode) => {
          const x = scaleX(episode.startAt);
          const w = Math.max(14, scaleX(episode.endAt) - x);
          const selected = selectedEpisodeId === episode.id;
          return (
            <g
              cursor="pointer"
              key={`episode-band-${episode.id}`}
              onClick={() => onEpisodeSelect(episode.id)}
              role="button"
              tabIndex={0}
            >
              <title>{episodeTooltip(episode)}</title>
              <rect
                fill={selected ? "#D9B874" : "#D8C2A3"}
                height={chartHeight}
                opacity={selected ? 0.32 : 0.18}
                stroke="var(--accent)"
                strokeOpacity={selected ? 0.72 : 0.34}
                strokeWidth={selected ? "1.8" : "1"}
                width={w}
                x={x}
                y={chartTop}
              />
              <rect
                fill={selected ? "var(--fg)" : "var(--accent)"}
                height={selected ? "5" : "3"}
                opacity={selected ? 0.9 : 0.58}
                width={w}
                x={x}
                y={chartTop - 7}
              />
            </g>
          );
        })}

        <rect
          fill="#EDEBE2"
          height={Math.max(1, scaleY(3.9) - scaleY(10))}
          opacity={0.72}
          width={chartWidth}
          x={left}
          y={scaleY(10)}
        />
        <text fill="var(--muted)" fontSize="11" x={left + 8} y={scaleY(10) + 14}>
          целевой диапазон 3.9–10.0
        </text>

        {yTicks.map((tick) => (
          <g key={tick}>
            <line
              stroke="var(--hairline)"
              strokeDasharray="3 7"
              x1={left}
              x2={width - right}
              y1={scaleY(tick)}
              y2={scaleY(tick)}
            />
            <text
              fill="var(--muted)"
              fontSize="12"
              textAnchor="end"
              x={left - 10}
              y={scaleY(tick) + 4}
            >
              {tick.toFixed(1)}
            </text>
          </g>
        ))}

        <EventLane
          artifacts={data?.artifacts ?? []}
          eventTop={eventTop}
          episodeLayouts={episodeLayouts}
          fingersticks={data?.fingersticks ?? []}
          food={data?.food_events ?? []}
          insulin={data?.insulin_events ?? []}
          onEpisodeSelect={onEpisodeSelect}
          scaleX={scaleX}
          selectedEpisodeId={selectedEpisodeId}
        />

        <polyline
          fill="none"
          points={rawLine}
          stroke="#9B958B"
          strokeDasharray="1 8"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="2.5"
        />
        <polyline
          fill="none"
          points={mainLine}
          stroke="var(--fg)"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="3"
        />

        {points.map((point, i) => {
          const mainVal =
            mode === "normalized"
              ? point.normalized_value ?? point.raw_value
              : mode === "smoothed"
                ? point.smoothed_value ?? point.raw_value
                : point.raw_value;
          if (mainVal == null) return null;
          const x = scaleX(point.timestamp);
          const y = scaleY(mainVal);
          const rawPart = `Raw: ${point.raw_value.toFixed(1)}`;
          const normPart =
            point.normalized_value != null
              ? `Нормализованная: ${point.normalized_value.toFixed(1)}`
              : null;
          const corrPart =
            point.correction_mmol_l != null
              ? `Смещение: ${formatSigned(point.correction_mmol_l)}`
              : null;
          const confPart = point.bias_confidence
            ? `Доверие: ${point.bias_confidence}`
            : null;
          const contribPart =
            point.contributing_fingerstick_count != null
              ? `Записей из пальца: ${point.contributing_fingerstick_count}`
              : null;
          const distPart =
            point.nearest_fingerstick_distance_min != null
              ? `Ближайшее: ${point.nearest_fingerstick_distance_min.toFixed(0)} мин`
              : null;
          const tooltipText = [
            formatTime(point.timestamp),
            rawPart,
            normPart,
            corrPart,
            confPart,
            contribPart,
            distPart,
          ]
            .filter(Boolean)
            .join("\n");
          return (
            <circle
              cx={x}
              cy={y}
              fill="transparent"
              key={`pt-${i}`}
              r="8"
            >
              <title>{tooltipText}</title>
            </circle>
          );
        })}

        {data?.fingersticks.map((row) => {
          const x = scaleX(row.measured_at);
          const y = scaleY(row.glucose_mmol_l);
          return (
            <g key={row.id}>
              <polygon
                fill="var(--surface)"
                points={`${x},${y - 7} ${x + 7},${y} ${x},${y + 7} ${x - 7},${y}`}
                stroke="var(--fg)"
                strokeWidth="2"
              />
            </g>
          );
        })}

        {data?.food_events.map((event) => {
          const x = scaleX(event.timestamp);
          return (
            <line
              key={`${event.timestamp}-${event.title}`}
              opacity={0.55}
              stroke="var(--accent)"
              strokeDasharray="2 5"
              strokeWidth="1.4"
              x1={x}
              x2={x}
              y1={chartTop}
              y2={chartBottom}
            />
          );
        })}

        {data?.insulin_events.map((event) => {
          const x = scaleX(event.timestamp);
          return (
            <line
              key={`${event.timestamp}-${event.event_type ?? "insulin"}`}
              opacity={0.58}
              stroke="var(--fg)"
              strokeDasharray="5 5"
              strokeWidth="1"
              x1={x}
              x2={x}
              y1={chartTop}
              y2={chartBottom}
            />
          );
        })}

        <line
          stroke="var(--fg)"
          strokeWidth="1"
          x1={left}
          x2={width - right}
          y1={chartBottom}
          y2={chartBottom}
        />
        {xTicks.map((tick) => {
          const x = left + ((tick - fromMs) / duration) * chartWidth;
          return (
            <text
              fill="var(--muted)"
              fontSize="12"
              key={tick}
              textAnchor="middle"
              x={x}
              y={chartBottom + 24}
            >
              {new Intl.DateTimeFormat("ru-RU", {
                day: longRange ? "2-digit" : undefined,
                hour: "2-digit",
                minute: "2-digit",
                month: longRange ? "short" : undefined,
              }).format(new Date(tick))}
            </text>
          );
        })}

        <rect
          fill="var(--bg)"
          height={overviewHeight}
          stroke="var(--hairline)"
          width={chartWidth}
          x={left}
          y={overviewTop}
        />
        <polyline
          fill="none"
          opacity={0.85}
          points={overviewLine}
          stroke="#777168"
          strokeWidth="1.6"
        />
        <rect
          fill="transparent"
          height={overviewHeight}
          stroke="var(--fg)"
          strokeWidth="1"
          width={chartWidth}
          x={left}
          y={overviewTop}
        />
        <text fill="var(--muted)" fontSize="11" x={left} y={height - 4}>
          обзор выбранного периода
        </text>

        <g transform={`translate(${width - 430},${height - 4})`}>
          <LegendItem color="#9B958B" dashed label="raw CGM" x={0} />
          <LegendItem color="var(--fg)" label={modeLabel(mode)} x={100} />
          <LegendItem color="var(--accent)" label="еда" x={258} />
          <LegendItem color="var(--fg)" label="инсулин" x={320} />
        </g>
      </svg>
    </div>
  );
}

function EventLane({
  artifacts,
  episodeLayouts,
  eventTop,
  fingersticks,
  food,
  insulin,
  onEpisodeSelect,
  scaleX,
  selectedEpisodeId,
}: {
  artifacts: Artifact[];
  episodeLayouts: EpisodeChipLayout[];
  eventTop: number;
  fingersticks: Fingerstick[];
  food: FoodEvent[];
  insulin: InsulinEvent[];
  onEpisodeSelect: (episodeId: string) => void;
  scaleX: (iso: string) => number;
  selectedEpisodeId: string | null;
}) {
  const markerY = eventTop + 43;
  const compactMarkers = episodeLayouts.some((layout) =>
    ["minimal", "marker"].includes(layout.density),
  );

  return (
    <g>
      {episodeLayouts.map((layout) => (
        <EpisodeSummaryChip
          key={`episode-${layout.episode.id}`}
          layout={layout}
          onSelect={onEpisodeSelect}
          selected={selectedEpisodeId === layout.episode.id}
          y={eventTop + 1}
        />
      ))}
      {food.map((event, index) => (
        <FoodEventMarker
          key={`food-${event.timestamp}-${index}`}
          title={`${formatTime(event.timestamp)} Еда: ${event.title} ${formatNumber(
            event.carbs_g,
            1,
          )} г`}
          compact={compactMarkers}
          x={scaleX(event.timestamp)}
          y={markerY}
        />
      ))}
      {insulin.map((event, index) => (
        <InsulinEventMarker
          key={`insulin-${event.timestamp}-${index}`}
          title={`${formatTime(event.timestamp)} Инсулин из Nightscout: ${formatNumber(
            event.insulin_units,
            1,
          )} ЕД`}
          compact={compactMarkers}
          x={scaleX(event.timestamp)}
          y={markerY}
        />
      ))}
      {fingersticks.map((row) => (
        <FingerstickEventMarker
          key={`finger-${row.id}`}
          title={`${formatTime(row.measured_at)} Из пальца: ${formatNumber(
            row.glucose_mmol_l,
          )} ммоль/л`}
          compact={compactMarkers}
          x={scaleX(row.measured_at)}
          y={markerY}
        />
      ))}
      {artifacts.map((artifact, index) => (
        <ArtifactEventMarker
          key={`artifact-${artifact.start_at}-${index}`}
          title={`${formatTime(artifact.start_at)} ${artifact.label}`}
          compact={compactMarkers}
          x={scaleX(artifact.start_at)}
          y={markerY}
        />
      ))}
    </g>
  );
}

type EpisodeVisualDensity = "detailed" | "compact" | "minimal" | "marker";

type EpisodeChipLayout = {
  density: EpisodeVisualDensity;
  episode: GroupedEpisode;
  left: number;
  primaryLabel: string;
  secondaryLabel: string | null;
  width: number;
};

function EpisodeSummaryChip({
  layout,
  onSelect,
  selected,
  y,
}: {
  layout: EpisodeChipLayout;
  onSelect: (episodeId: string) => void;
  selected: boolean;
  y: number;
}) {
  const height = layout.density === "marker" ? 24 : 34;
  const markerOnly = layout.density === "marker";
  return (
    <g
      cursor="pointer"
      onClick={() => onSelect(layout.episode.id)}
      role="button"
      tabIndex={0}
      transform={`translate(${layout.left},${y})`}
    >
      <title>{episodeTooltip(layout.episode)}</title>
      <rect
        fill={selected ? "#E3C17D" : "#F1E4CE"}
        height={height}
        rx="0"
        stroke={selected ? "var(--fg)" : "var(--accent)"}
        strokeOpacity={selected ? "0.86" : "0.58"}
        strokeWidth={selected ? "1.6" : "1"}
        width={layout.width}
      />
      {markerOnly ? (
        <circle
          cx={layout.width / 2}
          cy={height / 2}
          fill="var(--accent)"
          r={4}
          stroke={selected ? "var(--fg)" : "none"}
          strokeWidth="1.2"
        />
      ) : (
        <>
          <text
            fill="var(--fg)"
            fontSize={layout.density === "minimal" ? "11" : "12"}
            fontWeight={selected ? "700" : "600"}
            textAnchor="middle"
            x={layout.width / 2}
            y={layout.secondaryLabel ? "14" : "21"}
          >
            {layout.primaryLabel}
          </text>
          {layout.secondaryLabel ? (
            <text
              fill="var(--muted)"
              fontSize="10"
              textAnchor="middle"
              x={layout.width / 2}
              y="27"
            >
              {layout.secondaryLabel}
            </text>
          ) : null}
        </>
      )}
    </g>
  );
}

function FoodEventMarker({
  compact,
  title,
  x,
  y,
}: {
  compact: boolean;
  title: string;
  x: number;
  y: number;
}) {
  return (
    <g>
      <title>{title}</title>
      <circle
        cx={x}
        cy={y}
        fill="var(--accent)"
        opacity={compact ? 0.62 : 0.86}
        r={compact ? 3 : 4.5}
        stroke="var(--surface)"
        strokeWidth="1"
      />
    </g>
  );
}

function InsulinEventMarker({
  compact,
  title,
  x,
  y,
}: {
  compact: boolean;
  title: string;
  x: number;
  y: number;
}) {
  return (
    <g>
      <title>{title}</title>
      <line
        opacity={compact ? 0.58 : 0.82}
        stroke="var(--fg)"
        strokeLinecap="round"
        strokeWidth={compact ? "1.4" : "2"}
        x1={x}
        x2={x}
        y1={y - (compact ? 8 : 12)}
        y2={y + (compact ? 8 : 12)}
      />
    </g>
  );
}

function FingerstickEventMarker({
  compact,
  title,
  x,
  y,
}: {
  compact: boolean;
  title: string;
  x: number;
  y: number;
}) {
  const size = compact ? 5 : 7;
  return (
    <g>
      <title>{title}</title>
      <polygon
        fill="var(--surface)"
        opacity={compact ? 0.7 : 1}
        points={`${x},${y - size} ${x + size},${y} ${x},${y + size} ${x - size},${y}`}
        stroke="var(--fg)"
        strokeWidth={compact ? "1.2" : "1.6"}
      />
    </g>
  );
}

function ArtifactEventMarker({
  compact,
  title,
  x,
  y,
}: {
  compact: boolean;
  title: string;
  x: number;
  y: number;
}) {
  const size = compact ? 7 : 9;
  return (
    <g>
      <title>{title}</title>
      <rect
        fill="#FFF8EA"
        height={size}
        opacity={compact ? 0.64 : 0.9}
        stroke="#A77730"
        strokeWidth="1"
        width={size}
        x={x - size / 2}
        y={y - size / 2}
      />
    </g>
  );
}

function episodeDensityForDuration(durationMs: number): EpisodeVisualDensity {
  if (durationMs <= 6 * 60 * 60 * 1000) return "detailed";
  if (durationMs <= 24 * 60 * 60 * 1000) return "compact";
  return "minimal";
}

function layoutEpisodeChips({
  chartLeft,
  chartRight,
  density,
  episodes,
  scaleX,
}: {
  chartLeft: number;
  chartRight: number;
  density: EpisodeVisualDensity;
  episodes: GroupedEpisode[];
  scaleX: (iso: string) => number;
}): EpisodeChipLayout[] {
  if (!episodes.length) return [];
  const chartWidth = chartRight - chartLeft;
  const resolvedDensity = resolveEpisodeChipDensity(density, episodes, chartWidth);
  const gap = resolvedDensity === "marker" ? 4 : 6;
  const widthOverride =
    resolvedDensity === "marker" && episodes.length > 1
      ? Math.max(
          14,
          Math.min(32, (chartWidth - gap * (episodes.length - 1)) / episodes.length),
        )
      : null;
  const items = episodes
    .map((episode) => {
      const width = widthOverride ?? episodeChipWidth(episode, resolvedDensity);
      const center =
        (scaleX(episode.startAt) + Math.max(scaleX(episode.endAt), scaleX(episode.startAt))) /
        2;
      const labels = episodeChipLabels(episode, resolvedDensity);
      return {
        center,
        density: resolvedDensity,
        episode,
        left: clamp(center - width / 2, chartLeft, chartRight - width),
        primaryLabel: labels.primary,
        secondaryLabel: labels.secondary,
        width,
      };
    })
    .sort((left, right) => left.center - right.center);

  let cursor = chartLeft;
  items.forEach((item) => {
    item.left = Math.max(item.left, cursor);
    cursor = item.left + item.width + gap;
  });

  for (let index = items.length - 1; index >= 0; index -= 1) {
    const next = items[index + 1];
    const maxLeft = next
      ? next.left - gap - items[index].width
      : chartRight - items[index].width;
    items[index].left = Math.min(items[index].left, maxLeft);
  }

  const underflow = chartLeft - items[0].left;
  if (underflow > 0) {
    items.forEach((item) => {
      item.left += underflow;
    });
  }

  return items;
}

function resolveEpisodeChipDensity(
  preferred: EpisodeVisualDensity,
  episodes: GroupedEpisode[],
  chartWidth: number,
): EpisodeVisualDensity {
  const options: EpisodeVisualDensity[] =
    preferred === "detailed"
      ? ["detailed", "compact", "minimal", "marker"]
      : preferred === "compact"
        ? ["compact", "minimal", "marker"]
        : preferred === "minimal"
          ? ["minimal", "marker"]
          : ["marker"];
  return (
    options.find((density) => {
      const gap = density === "marker" ? 4 : 6;
      const totalWidth =
        episodes.reduce((sum, episode) => sum + episodeChipWidth(episode, density), 0) +
        gap * Math.max(0, episodes.length - 1);
      return totalWidth <= chartWidth;
    }) ?? "marker"
  );
}

function episodeChipWidth(
  episode: GroupedEpisode,
  density: EpisodeVisualDensity,
) {
  if (density === "marker") return 32;
  if (density === "minimal") return 78;
  if (density === "compact") return 150;
  const primary = episodeChipLabels(episode, density).primaryLabelLength;
  return Math.max(210, Math.min(270, primary * 6.2 + 24));
}

function episodeChipLabels(
  episode: GroupedEpisode,
  density: EpisodeVisualDensity,
) {
  const carbs = `${formatNumber(episode.carbsTotal, 1)} г`;
  const insulin =
    episode.insulinTotal > 0 ? `${formatNumber(episode.insulinTotal, 1)} ЕД` : null;
  if (density === "marker") {
    return { primary: "", primaryLabelLength: 0, secondary: null };
  }
  if (density === "minimal") {
    return {
      primary: carbs,
      primaryLabelLength: carbs.length,
      secondary: insulin,
    };
  }
  if (density === "compact") {
    const primary = `Приём пищи  ${carbs}`;
    return {
      primary,
      primaryLabelLength: primary.length,
      secondary: insulin,
    };
  }
  const primary = `Приём пищи  ${formatEpisodeRange(
    episode.startAt,
    episode.endAt,
  )}  ${carbs}`;
  return {
    primary,
    primaryLabelLength: primary.length,
    secondary: insulin,
  };
}

function episodeTooltip(episode: GroupedEpisode) {
  const lines = [
    `Приём пищи ${formatEpisodeRange(episode.startAt, episode.endAt)}`,
    `${formatNumber(episode.carbsTotal, 1)} г углеводов · ${formatNumber(
      episode.kcalTotal,
      0,
    )} ккал · ${formatNumber(episode.insulinTotal, 1)} ЕД`,
    ...episodeDetailRows(episode).map((row) => `${row.time} ${row.label} ${row.data}`),
  ];
  return lines.join("\n");
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function LegendItem({
  color,
  dashed,
  label,
  x,
}: {
  color: string;
  dashed?: boolean;
  label: string;
  x: number;
}) {
  return (
    <g transform={`translate(${x},0)`}>
      <line
        stroke={color}
        strokeDasharray={dashed ? "1 6" : undefined}
        strokeWidth="2"
        x1="0"
        x2="18"
        y1="-5"
        y2="-5"
      />
      <text fill="var(--muted)" fontSize="11" x="25" y="-1">
        {label}
      </text>
    </g>
  );
}

function modeLabel(mode: GlucoseMode) {
  if (mode === "normalized") return "нормализованная";
  if (mode === "smoothed") return "сглаженная";
  return "raw";
}

type BiasData = NonNullable<GlucoseDashboardResponse["bias_over_lifetime"]>;

function BiasOverLifetimeChart({ data }: { data: BiasData | null }) {
  if (!data || data.residuals.length === 0) {
    return (
      <section className="border border-[var(--hairline)] bg-[var(--surface)] p-5">
        <h3 className="text-[14px] text-[var(--fg)]">Смещение по времени сенсора</h3>
        <p className="mt-2 text-[12px] text-[var(--muted)]">
          Недостаточно записей из пальца для графика смещения.
        </p>
      </section>
    );
  }

  const viewW = 360;
  const viewH = 120;
  const padL = 32;
  const padR = 8;
  const padT = 8;
  const padB = 18;
  const chartW = viewW - padL - padR;
  const chartH = viewH - padT - padB;

  const residuals = data.residuals.filter((r) => r.included);
  const allValues = [
    ...residuals.map((r) => r.residual),
    ...data.bias_curve.map((c) => c.bias),
  ];
  const vMin = Math.min(...allValues, -0.5);
  const vMax = Math.max(...allValues, 0.5);
  const vPad = (vMax - vMin) * 0.15 || 0.5;
  const yLo = vMin - vPad;
  const yHi = vMax + vPad;

  const maxAgeH = Math.max(
    ...data.residuals.map((r) => r.sensor_age_hours),
    ...data.bias_curve.map((c) => c.sensor_age_hours),
    48,
  );

  const xForAge = (h: number) => padL + (h / maxAgeH) * chartW;
  const yForVal = (v: number) => padT + chartH - ((v - yLo) / (yHi - yLo)) * chartH;

  const warmupEndX = xForAge(48);

  const biasLine = data.bias_curve
    .map((p) => `${xForAge(p.sensor_age_hours)},${yForVal(p.bias)}`)
    .join(" ");

  const formatAge = (h: number) => {
    if (h < 48) return `${Math.round(h)}ч`;
    return `${(h / 24).toFixed(1)}д`;
  };

  const tickCount = 5;
  const ticks = Array.from({ length: tickCount }, (_, i) =>
    (i / (tickCount - 1)) * maxAgeH,
  );

  return (
    <section className="border border-[var(--hairline)] bg-[var(--surface)] p-5">
      <h3 className="text-[14px] text-[var(--fg)]">Смещение по времени сенсора</h3>
      <p className="mb-2 text-[10px] text-[var(--muted)]">
        Оценка по записям из пальца · Raw CGM сохраняется без изменений
      </p>
      <svg
        className="w-full"
        preserveAspectRatio="xMidYMid meet"
        viewBox={`0 0 ${viewW} ${viewH}`}
      >
        <rect fill="rgba(255,200,100,0.08)" height={chartH} width={warmupEndX - padL} x={padL} y={padT} />
        <line stroke="rgba(255,200,100,0.3)" strokeDasharray="3 3" x1={warmupEndX} x2={warmupEndX} y1={padT} y2={padT + chartH} />
        <text fill="rgba(255,200,100,0.6)" fontSize="5" x={warmupEndX + 2} y={padT + 6}>
          48ч
        </text>
        <line stroke="var(--hairline)" x1={padL} x2={padL} y1={padT} y2={padT + chartH} />
        <line stroke="var(--hairline)" x1={padL} x2={padL + chartW} y1={padT + chartH} y2={padT + chartH} />
        {ticks.map((h) => (
          <text fill="var(--muted)" fontSize="6" key={h} textAnchor="middle" x={xForAge(h)} y={viewH - 3}>
            {formatAge(h)}
          </text>
        ))}
        <text fill="var(--muted)" fontSize="6" textAnchor="end" x={padL - 3} y={padT + 4}>
          {yHi.toFixed(1)}
        </text>
        <text fill="var(--muted)" fontSize="6" textAnchor="end" x={padL - 3} y={padT + chartH}>
          {yLo.toFixed(1)}
        </text>
        <text fill="var(--muted)" fontSize="5" textAnchor="end" x={padL - 3} y={padT + chartH / 2 + 2}>
          ммоль/л
        </text>
        {biasLine ? (
          <polyline
            fill="none"
            points={biasLine}
            stroke="var(--fg)"
            strokeLinejoin="round"
            strokeWidth="1"
          />
        ) : null}
        {residuals.map((r, i) => (
          <polygon
            fill="var(--accent)"
            key={`d-${i}`}
            points={`${xForAge(r.sensor_age_hours)},${yForVal(r.residual) - 3} ${xForAge(r.sensor_age_hours) + 2.5},${yForVal(r.residual) + 2} ${xForAge(r.sensor_age_hours) - 2.5},${yForVal(r.residual) + 2}`}
          >
            <title>
              {`${r.sensor_age_hours.toFixed(1)}ч: Δ${r.residual > 0 ? "+" : ""}${r.residual.toFixed(1)} ммоль/л · из пальца ${r.fingerstick_value} / raw ${r.raw_cgm_value}`}
            </title>
          </polygon>
        ))}
        {data.residuals.filter((r) => !r.included).map((r, i) => (
          <circle
            cx={xForAge(r.sensor_age_hours)}
            cy={yForVal(r.residual)}
            fill="none"
            key={`ex-${i}`}
            r="2"
            stroke="var(--muted)"
            strokeWidth="0.5"
          >
            <title>
              {`${r.sensor_age_hours.toFixed(1)}ч: Δ${r.residual > 0 ? "+" : ""}${r.residual.toFixed(1)} · ${r.exclusion_reason ?? "исключено"}`}
            </title>
          </circle>
        ))}
      </svg>
      <div className="mt-1 flex gap-4 text-[10px] text-[var(--muted)]">
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 rotate-45 bg-[var(--accent)]" />
          из пальца (включено)
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-full border border-[var(--muted)]" />
          исключено
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-0 w-3 border-t border-[var(--fg)]" />
          оценка смещения
        </span>
      </div>
    </section>
  );
}
