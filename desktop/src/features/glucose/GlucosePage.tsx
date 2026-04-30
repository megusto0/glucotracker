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
} from "./useGlucoseDashboard";

type RangePreset = "3h" | "6h" | "12h" | "24h" | "7d";
type DashboardPoint = GlucoseDashboardResponse["points"][number];
type Fingerstick = GlucoseDashboardResponse["fingersticks"][number];
type FoodEvent = GlucoseDashboardResponse["food_events"][number];
type InsulinEvent = GlucoseDashboardResponse["insulin_events"][number];
type Artifact = GlucoseDashboardResponse["artifacts"][number];

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

export function GlucosePage() {
  const config = useApiConfig();
  const initialRange = useMemo(() => presetRange("6h"), []);
  const [preset, setPreset] = useState<RangePreset | "custom">("6h");
  const [fromInput, setFromInput] = useState(initialRange.from);
  const [toInput, setToInput] = useState(initialRange.to);
  const [mode, setMode] = useState<GlucoseMode>("raw");
  const [fingerstickAt, setFingerstickAt] = useState(toDateTimeInput(new Date()));
  const [fingerstickValue, setFingerstickValue] = useState("");
  const [meterName, setMeterName] = useState("");
  const [lastImportAt, setLastImportAt] = useState<string | null>(null);
  const [showFingerstickForm, setShowFingerstickForm] = useState(false);
  const [showSensorEdit, setShowSensorEdit] = useState(false);
  const [sensorForm, setSensorForm] = useState<SensorForm>(() => emptySensorForm());

  const from = toApiDateTime(fromInput);
  const to = toApiDateTime(toInput);
  const dashboard = useGlucoseDashboard(from, to, mode);
  const sensors = useSensors();
  const nightscoutSettings = useNightscoutSettings();
  const nightscoutImport = useImportNightscoutContext(from, to);
  const createFingerstick = useCreateFingerstick();
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
  const recentFingersticks = (data?.fingersticks ?? []).slice(-4).reverse();

  const error = [
    dashboard.error,
    nightscoutImport.error,
    createFingerstick.error,
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
    if (!settings?.configured || !settings.sync_glucose || nightscoutImport.isPending) {
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
    nightscoutImport.mutate(
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
    nightscoutImport,
    nightscoutSettings.data,
    preset,
    toInput,
  ]);

  useEffect(() => {
    if (!canImportNightscout) return;
    const timer = window.setInterval(refreshNightscout, 5 * 60 * 1000);
    return () => window.clearInterval(timer);
  }, [canImportNightscout, refreshNightscout]);

  const applyPreset = (value: RangePreset) => {
    const next = presetRange(value);
    startTransition(() => {
      setPreset(value);
      setFromInput(next.from);
      setToInput(next.to);
    });
  };

  const submitFingerstick = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const value = Number(fingerstickValue.replace(",", "."));
    if (!fingerstickAt || !Number.isFinite(value) || value <= 0) return;
    createFingerstick.mutate(
      {
        glucose_mmol_l: value,
        measured_at: toApiDateTime(fingerstickAt),
        meter_name: blankToNull(meterName),
        notes: null,
      },
      {
        onSuccess: () => {
          setFingerstickValue("");
          setFingerstickAt(toDateTimeInput(new Date()));
          setShowFingerstickForm(false);
        },
      },
    );
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

  const nightscoutImportStatus = nightscoutImport.isPending
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
                    disabled={!canImportNightscout || nightscoutImport.isPending}
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
              loading={dashboard.isLoading}
              mode={mode}
            />
          </section>

          <EventsTable rows={events} />
        </main>

        <SensorQualityPanel
          createFingerstick={createFingerstick}
          fingerstickAt={fingerstickAt}
          fingerstickValue={fingerstickValue}
          meterName={meterName}
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
          toggleFingerstickForm={() => setShowFingerstickForm((value) => !value)}
          toggleSensorEdit={() => setShowSensorEdit((value) => !value)}
        />
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
            <>
              Raw {formatNumber(latestPoint?.raw_value)}{" "}
              <span className="text-[var(--muted)]">
                нормализация {formatSigned(correction)}
              </span>
            </>
          ) : (
            "Нормализация недоступна: мало записей из пальца"
          )}
        </div>
        <div className="mt-2 text-[12px] text-[var(--muted)]">
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
  createFingerstick,
  fingerstickAt,
  fingerstickValue,
  meterName,
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
  toggleFingerstickForm,
  toggleSensorEdit,
}: {
  artifactCount: number;
  createFingerstick: ReturnType<typeof useCreateFingerstick>;
  fingerstickAt: string;
  fingerstickValue: string;
  meterName: string;
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
  toggleFingerstickForm: () => void;
  toggleSensorEdit: () => void;
}) {
  const validCalibrationPoints = quality?.valid_calibration_points ?? 0;
  const enoughCalibration = validCalibrationPoints >= 2;
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
            <div className="w-fit border border-[var(--hairline)] bg-[var(--bg)] px-3 py-2 text-[12px] text-[var(--fg)]">
              {phaseText}
            </div>
          </div>
        ) : (
          <p className="text-[13px] text-[var(--muted)]">
            В выбранном диапазоне нет активного сенсора.
          </p>
        )}
      </PanelSection>

      <PanelSection title="Оценка смещения">
        {enoughCalibration ? (
          <div className="grid gap-3">
            <dl className="grid grid-cols-2 gap-3 text-[12px]">
              <Metric
                label="Оценка смещения"
                value={`${formatSigned(quality?.median_bias_mmol_l)} ммоль/л`}
              />
              <Metric
                label="Дрейф"
                value={`${formatSigned(quality?.drift_mmol_l_per_day)} / день`}
              />
              <Metric label="MARD" value={`${formatNumber(quality?.mard_percent)}%`} />
              <Metric label="MAD" value={formatNumber(quality?.mad_mmol_l)} />
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
            <p>{quality?.fingerstick_count ?? 0} запись из пальца</p>
            <p>Нужно минимум 2–3 валидные записи</p>
            {warmupBehaviorDetected ? (
              <p>
                В первые 12 ч расхождение менялось: {warmupResiduals} ммоль/л.
              </p>
            ) : null}
          </div>
        )}
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

      <PanelSection title="Действия">
        <div className="grid gap-2">
          <Button
            icon={<Plus size={14} />}
            onClick={toggleFingerstickForm}
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
            Новая запись из пальца
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
          <Button
            disabled={createFingerstick.isPending || !fingerstickValue.trim()}
            icon={<Plus size={14} />}
            type="submit"
            variant="primary"
          >
            Добавить
          </Button>
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
                  className="grid grid-cols-[52px_1fr_auto] items-center gap-3 border border-[var(--hairline)] bg-[var(--bg)] px-3 py-2 text-[12px]"
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

function EventsTable({ rows }: { rows: EventRow[] }) {
  return (
    <section className="border border-[var(--hairline)] bg-[var(--surface)]">
      <div className="border-b border-[var(--hairline)] px-5 py-4">
        <h2 className="text-[18px] text-[var(--fg)]">События на графике</h2>
      </div>
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
    </section>
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
      data: `${formatNumber(event.carbs_g, 1)}г`,
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

  return rows.sort((left, right) => left.sortKey - right.sortKey).slice(0, 14);
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
  loading,
  mode,
}: {
  data?: GlucoseDashboardResponse;
  loading: boolean;
  mode: GlucoseMode;
}) {
  const points = data?.points ?? [];
  const width = 1180;
  const height = 610;
  const left = 56;
  const right = 26;
  const eventTop = 26;
  const eventHeight = 34;
  const chartTop = 86;
  const chartHeight = 450;
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
    if (mode === "normalized") return point.normalized_value ?? point.raw_value;
    if (mode === "smoothed") return point.smoothed_value ?? point.raw_value;
    return point.raw_value;
  });
  const overviewLine = line(points, (point) => point.raw_value, overviewY);
  const xTicks = [0, 0.25, 0.5, 0.75, 1].map((ratio) => fromMs + duration * ratio);
  const yTicks = [0, 0.25, 0.5, 0.75, 1].map(
    (ratio) => minValue + yRange * ratio,
  );
  const longRange = duration > 36 * 60 * 60 * 1000;

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
          fingersticks={data?.fingersticks ?? []}
          food={data?.food_events ?? []}
          insulin={data?.insulin_events ?? []}
          scaleX={scaleX}
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
  eventTop,
  fingersticks,
  food,
  insulin,
  scaleX,
}: {
  artifacts: Artifact[];
  eventTop: number;
  fingersticks: Fingerstick[];
  food: FoodEvent[];
  insulin: InsulinEvent[];
  scaleX: (iso: string) => number;
}) {
  return (
    <g>
      {food.map((event, index) => (
        <EventChip
          fill="#F2E8D8"
          key={`food-${event.timestamp}-${index}`}
          label={`еда ${formatNumber(event.carbs_g, 1)}г`}
          stroke="var(--accent)"
          x={scaleX(event.timestamp)}
          y={eventTop}
        />
      ))}
      {insulin.map((event, index) => (
        <EventChip
          fill="#F6F4EE"
          key={`insulin-${event.timestamp}-${index}`}
          label={`инсулин ${formatNumber(event.insulin_units, 1)} ЕД`}
          stroke="var(--fg)"
          x={scaleX(event.timestamp)}
          y={eventTop + 2}
        />
      ))}
      {fingersticks.map((row) => (
        <EventChip
          fill="#FFFFFF"
          key={`finger-${row.id}`}
          label={`из пальца ${formatNumber(row.glucose_mmol_l)}`}
          stroke="var(--fg)"
          x={scaleX(row.measured_at)}
          y={eventTop + 4}
        />
      ))}
      {artifacts.map((artifact, index) => (
        <EventChip
          fill="#FFF8EA"
          key={`artifact-${artifact.start_at}-${index}`}
          label="артефакт?"
          stroke="#A77730"
          x={scaleX(artifact.start_at)}
          y={eventTop + 6}
        />
      ))}
    </g>
  );
}

function EventChip({
  fill,
  label,
  stroke,
  x,
  y,
}: {
  fill: string;
  label: string;
  stroke: string;
  x: number;
  y: number;
}) {
  const width = Math.max(58, Math.min(118, label.length * 6.4 + 18));
  return (
    <g transform={`translate(${x - width / 2},${y})`}>
      <rect
        fill={fill}
        height="24"
        rx="0"
        stroke={stroke}
        strokeOpacity="0.65"
        width={width}
      />
      <text
        fill="var(--fg)"
        fontSize="11"
        textAnchor="middle"
        x={width / 2}
        y="16"
      >
        {label}
      </text>
    </g>
  );
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
