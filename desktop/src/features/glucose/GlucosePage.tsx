import {
  Activity,
  AlertTriangle,
  Info,
  Plus,
  RefreshCw,
  Save,
  RotateCcw,
} from "lucide-react";
import {
  startTransition,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type FormEvent,
} from "react";
import {
  apiErrorMessage,
  type GlucoseDashboardResponse,
  type GlucoseMode,
  type KcalBalanceResponse,
  type SensorSessionResponse,
} from "../../api/client";
import { apiClient } from "../../api/client";
import RightPanel from "../../components/RightPanel";
import {
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
import { useGlucoseSyncTracker } from "./useGlucoseSyncTracker";
import { SyncStatusIndicator } from "./SyncStatusIndicator";

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

const rangeTitle = (preset: RangePreset | "custom") =>
  ({
    "3h": "Последние 3 часа",
    "6h": "Последние 6 часов",
    "12h": "Последние 12 часов",
    "24h": "Последние 24 часа",
    "7d": "Последние 7 дней",
    custom: "Выбранный период",
  })[preset];

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
  const [hoveredEpisodeId, setHoveredEpisodeId] = useState<string | null>(null);
  const [fingerstickAt, setFingerstickAt] = useState(toDateTimeInput(new Date()));
  const [fingerstickValue, setFingerstickValue] = useState("");
  const [meterName, setMeterName] = useState("");
  const [editingFingerstickId, setEditingFingerstickId] = useState<string | null>(null);
  const [showFingerstickForm, setShowFingerstickForm] = useState(false);
  const [showSensorEdit, setShowSensorEdit] = useState(false);
  const [showSensorPanel, setShowSensorPanel] = useState(false);
  const [sensorForm, setSensorForm] = useState<SensorForm>(() => emptySensorForm());
  const [kcalBalance, setKcalBalance] = useState<KcalBalanceResponse | null>(null);
  const toggleSensorEdit = useCallback(() => setShowSensorEdit((v) => !v), []);

  useEffect(() => {
    if (!config.token.trim()) return;
    const today = new Date();
    const day = `${today.getFullYear()}-${pad(today.getMonth() + 1)}-${pad(today.getDate())}`;
    apiClient.getKcalBalance(config, day).then(setKcalBalance).catch(() => setKcalBalance(null));
  }, [config.token, config.baseUrl]);

  const from = toApiDateTime(fromInput);
  const to = toApiDateTime(toInput);
  const dashboard = useGlucoseDashboard(from, to, mode);
  const sensors = useSensors();
  const nightscoutSettings = useNightscoutSettings();

  const canImportNightscout = Boolean(
    config.token.trim() &&
      nightscoutSettings.data?.configured &&
      nightscoutSettings.data?.sync_glucose,
  );

  const { syncState, forceRefresh, resetConnection } = useGlucoseSyncTracker(
    from,
    to,
    mode,
    canImportNightscout,
    Boolean(nightscoutSettings.data?.configured),
  );

  const createFingerstick = useCreateFingerstick();
  const updateFingerstick = useUpdateFingerstick();
  const deleteFingerstick = useDeleteFingerstick();
  const saveSensor = useSaveSensor();
  const recalculate = useRecalculateSensorCalibration();
  const isCustomRange = preset === "custom";

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
    createFingerstick.error,
    updateFingerstick.error,
    deleteFingerstick.error,
    saveSensor.error,
    recalculate.error,
  ].find(Boolean);

  useEffect(() => {
    setSensorForm(currentSensor ? sensorToForm(currentSensor) : emptySensorForm());
  }, [currentSensor?.id, currentSensor?.updated_at]);

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


  return (
    <div style={{ display: "flex", height: "100%" }}>
      <div style={{ flex: 1, overflow: "auto" }}>
        <div className="gt-page">
          {!config.token.trim() ? (
            <div className="card card-pad" style={{ marginBottom: 16, fontSize: 14, color: "var(--ink-3)" }}>
              Укажите токен backend в настройках, чтобы загрузить локальные данные Nightscout.
            </div>
          ) : null}

          {error ? (
            <div className="card card-pad" style={{ marginBottom: 16, display: "flex", alignItems: "flex-start", gap: 10, fontSize: 14, color: "var(--warn)", borderColor: "var(--warn)" }}>
              <AlertTriangle size={18} />
              {apiErrorMessage(error)}
            </div>
          ) : null}

          <header style={{ marginBottom: 20 }}>
            <div className="gt-crumbs">
              <Activity size={14} />
              <span>NIGHTSCOUT / ЛОКАЛЬНЫЙ КОНТЕКСТ</span>
            </div>
            <h1 className="gt-h1">Глюкоза</h1>
          </header>

          <div className="row gap-8" style={{ marginBottom: 22 }}>
            <button className="btn" onClick={openNewFingerstickForm}><Plus size={13} /> Запись из пальца</button>
            <button className="btn" onClick={() => setShowSensorPanel(!showSensorPanel)}
              style={showSensorPanel ? { background: "var(--surface-2)", color: "var(--ink)", borderColor: "var(--ink-3)", boxShadow: "inset 0 -2px 0 var(--ink-3)" } : {}}>
              <Activity size={13} /> Сенсор
            </button>
            <button className="btn" disabled={!canImportNightscout || syncState.phase === "importing"} onClick={forceRefresh}>
              <RefreshCw size={13} /> Подтянуть
            </button>
            {syncState.phase === "offline" && (
              <button className="btn" onClick={resetConnection} style={{ color: "var(--warn)", borderColor: "var(--warn-soft)" }}>
                <RotateCcw size={13} /> Переподключить
              </button>
            )}
          </div>

          {canImportNightscout && (
            <SyncStatusIndicator syncState={syncState} />
          )}

          <HeroCard
            correction={correction}
            latestPoint={latestPoint}
            previousPoint={previousPoint}
            quality={quality}
            sensor={currentSensor}
            kcalBalance={kcalBalance}
          />

          <section className="card" style={{ marginBottom: 22 }}>
            <div className="card-head">
              <div>
                <div className="lbl">график глюкозы</div>
                <h3>{rangeTitle(preset)}</h3>
              </div>
              <div className="col gap-8" style={{ alignItems: "flex-end", flex: 1 }}>
                <div className="row gap-12" style={{ alignItems: "center", justifyContent: "flex-end", flexWrap: "wrap" }}>
                  <div className="seg">
                    {rangeButtons.map((item) => (
                      <button key={item.value} className={preset === item.value ? "on" : ""} onClick={() => applyPreset(item.value)} type="button">{item.label}</button>
                    ))}
                    <button
                      className={isCustomRange ? "on" : ""}
                      onClick={() => setPreset("custom")}
                      type="button"
                    >
                      Период
                    </button>
                  </div>
                  <div className="seg">
                    {modes.map((item) => (
                      <button key={item.value} className={mode === item.value ? "on" : ""} onClick={() => setMode(item.value)} type="button">{item.label}</button>
                    ))}
                  </div>
                </div>
                <div className="row gap-6" style={{ alignItems: "center", fontSize: 11, color: "var(--ink-4)" }}>
                  <Info size={12} />
                  <span>Raw / Сглаж. / Норм. применяются только к отображению.</span>
                </div>
              </div>
            </div>
            <div
              style={{
                borderBottom: isCustomRange ? "1px solid var(--hairline)" : "none",
                maxHeight: isCustomRange ? 90 : 0,
                opacity: isCustomRange ? 1 : 0,
                overflow: "hidden",
                padding: isCustomRange ? "10px 18px" : "0 18px",
                transition: "max-height 220ms ease, opacity 180ms ease, padding 220ms ease, border-color 220ms ease",
              }}
            >
              <div className="row" style={{ gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                <label className="field" style={{ width: "auto" }}>
                  <span>от</span>
                  <input type="datetime-local" value={fromInput} onChange={(event) => { setPreset("custom"); setFromInput(event.target.value); }} />
                </label>
                <label className="field" style={{ width: "auto" }}>
                  <span>до</span>
                  <input type="datetime-local" value={toInput} onChange={(event) => { setPreset("custom"); setToInput(event.target.value); }} />
                </label>
              </div>
            </div>
            <div style={{ padding: "10px 12px 0" }}>
              <GlucoseChart
                data={data}
                episodes={episodes}
                hoveredEpisodeId={hoveredEpisodeId}
                loading={dashboard.isLoading}
                mode={mode}
                onEpisodeHover={setHoveredEpisodeId}
                onEpisodeSelect={setSelectedEpisodeId}
                preset={preset}
                selectedEpisodeId={selectedEpisodeId}
              />
            </div>
            <div className="row" style={{ borderTop: "1px solid var(--hairline)", padding: "10px 22px", gap: 18, fontSize: 11, color: "var(--ink-3)", alignItems: "center" }}>
              <span className="row gap-6" style={{ alignItems: "center" }}><span style={{ width: 18, height: 1.6, background: "var(--ink)", display: "inline-block" }} /> норм.</span>
              <span className="row gap-6" style={{ alignItems: "center" }}><span style={{ width: 18, height: 1, borderTop: "1px dashed var(--ink-3)", display: "inline-block" }} /> raw CGM</span>
              <span className="row gap-6" style={{ alignItems: "center" }}><span className="dot-marker" style={{ background: "var(--accent)" }} /> приём пищи</span>
              <span className="row gap-6" style={{ alignItems: "center" }}><span style={{ width: 8, height: 8, background: "var(--surface)", border: "1.4px solid var(--ink)", transform: "rotate(45deg)", display: "inline-block" }} /> запись из пальца</span>
              <span className="row gap-6" style={{ alignItems: "center" }}><span style={{ width: 12, height: 8, background: "var(--ink)", display: "inline-block" }} /> инсулин</span>
              <span className="spacer" />
              <span className="mono" style={{ color: "var(--ink-4)" }}>
                {data ? `${new Intl.DateTimeFormat("ru-RU", { day: "2-digit", month: "short" }).format(new Date(data.from_datetime))} · ${formatTime(data.from_datetime)} — ${formatTime(data.to_datetime)}` : "—"}
              </span>
            </div>
          </section>

          <GlucoseActivityPanel
            activeTab={activityTab}
            episodes={episodes}
            hoveredEpisodeId={hoveredEpisodeId}
            onEpisodeHover={setHoveredEpisodeId}
            onEpisodeSelect={setSelectedEpisodeId}
            onTabChange={setActivityTab}
            rows={events}
            selectedEpisodeId={selectedEpisodeId}
          />

          <section className="card" style={{ marginTop: 22, marginBottom: 28 }}>
            <div className="card-head">
              <div>
                <div className="lbl">raw CGM сохраняется без изменений</div>
                <h3>Смещение сенсора</h3>
              </div>
              <span className="mono" style={{ fontSize: 11, color: "var(--ink-3)" }}>
                текущее <b style={{ color: "var(--ink)", fontWeight: 500 }}>{formatSigned(quality?.correction_now_mmol_l ?? quality?.median_delta_mmol_l)} ммоль/л</b>
              </span>
            </div>
            <div style={{ padding: "10px 12px 14px" }}>
              <BiasOverLifetimeChart data={data?.bias_over_lifetime ?? null} />
            </div>
          </section>
        </div>
      </div>

      {showSensorPanel && (
        <RightPanel onClose={() => setShowSensorPanel(false)}>
          <SensorPanel
            currentSensor={currentSensor}
            quality={quality}
            data={data}
            trust={trust}
            validCalibrationPoints={validCalibrationPoints}
            recentFingersticks={recentFingersticks}
            sensorList={sensorList}
            openNewFingerstickForm={openNewFingerstickForm}
            toggleSensorEdit={toggleSensorEdit}
            recalculate={recalculate}
            recalculatePending={recalculate.isPending}
            editFingerstick={editFingerstick}
          />
        </RightPanel>
      )}

      {showFingerstickForm ? (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.2)", zIndex: 100, display: "flex", alignItems: "center", justifyContent: "center" }} onClick={resetFingerstickForm}>
          <form className="card" style={{ padding: 24, width: 400, maxHeight: "90vh", overflow: "auto" }} onClick={(e) => e.stopPropagation()} onSubmit={(e) => { submitFingerstick(e); }}>
            <h3 style={{ fontFamily: "var(--serif)", fontSize: 18, fontWeight: 500, margin: "0 0 16px" }}>{editingFingerstickId ? "Редактировать запись из пальца" : "Новая запись из пальца"}</h3>
            <div className="col gap-16">
              <label className="field"><span>время</span><input type="datetime-local" value={fingerstickAt} onChange={(e) => setFingerstickAt(e.target.value)} /></label>
              <div className="row gap-16">
                <label className="field" style={{ flex: 1 }}><span>глюкоза, ммоль/л</span><input inputMode="decimal" placeholder="6.8" value={fingerstickValue} onChange={(e) => setFingerstickValue(e.target.value)} /></label>
                <label className="field" style={{ flex: 1 }}><span>глюкометр</span><input placeholder="опционально" value={meterName} onChange={(e) => setMeterName(e.target.value)} /></label>
              </div>
              <div className="row gap-8">
                <button className="btn dark" type="submit" disabled={createFingerstick.isPending || updateFingerstick.isPending || !fingerstickValue.trim()}><Save size={14} />{editingFingerstickId ? "Сохранить" : "Добавить"}</button>
                {editingFingerstickId ? (<button className="btn" type="button" onClick={deleteFingerstickHandler} style={{ color: "var(--warn)", borderColor: "var(--warn-soft)" }}>Удалить</button>) : null}
                <button className="btn" type="button" onClick={resetFingerstickForm}>Отмена</button>
              </div>
            </div>
          </form>
        </div>
      ) : null}

      {showSensorEdit ? (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.2)", zIndex: 100, display: "flex", alignItems: "center", justifyContent: "center" }} onClick={() => setShowSensorEdit(false)}>
          <form className="card" style={{ padding: 24, width: 420, maxHeight: "90vh", overflow: "auto" }} onClick={(e) => e.stopPropagation()} onSubmit={submitSensor}>
            <h3 style={{ fontFamily: "var(--serif)", fontSize: 18, fontWeight: 500, margin: "0 0 16px" }}>{currentSensor ? "Параметры сенсора" : "Новый сенсор"}</h3>
            <div className="col gap-16">
              <div className="row gap-16">
                <label className="field" style={{ flex: 1 }}><span>производитель</span><input value={sensorForm.vendor} onChange={(e) => setSensorForm(s => ({ ...s, vendor: e.target.value }))} /></label>
                <label className="field" style={{ flex: 1 }}><span>модель</span><input value={sensorForm.model} onChange={(e) => setSensorForm(s => ({ ...s, model: e.target.value }))} /></label>
              </div>
              <label className="field"><span>метка</span><input value={sensorForm.label} onChange={(e) => setSensorForm(s => ({ ...s, label: e.target.value }))} /></label>
              <div className="row gap-16">
                <label className="field" style={{ flex: 1 }}><span>старт</span><input type="datetime-local" value={sensorForm.started_at} onChange={(e) => setSensorForm(s => ({ ...s, started_at: e.target.value }))} /></label>
                <label className="field" style={{ flex: 1 }}><span>конец</span><input type="datetime-local" value={sensorForm.ended_at} onChange={(e) => setSensorForm(s => ({ ...s, ended_at: e.target.value }))} /></label>
              </div>
              <label className="field"><span>заметки</span><textarea value={sensorForm.notes} onChange={(e) => setSensorForm(s => ({ ...s, notes: e.target.value }))} rows={3} /></label>
              <div className="row gap-8">
                <button className="btn dark" type="submit" disabled={saveSensor.isPending || !sensorForm.started_at}><Save size={14} />Сохранить сенсор</button>
                <button className="btn" type="button" onClick={() => setShowSensorEdit(false)}>Отмена</button>
              </div>
            </div>
          </form>
        </div>
      ) : null}
    </div>
  );
}

function HeroCard({
  correction,
  latestPoint,
  previousPoint,
  quality,
  sensor,
  kcalBalance,
}: {
  correction: number | null;
  latestPoint: DashboardPoint | null;
  previousPoint: DashboardPoint | null;
  quality?: GlucoseDashboardResponse["quality"];
  sensor: SensorSessionResponse | null;
  kcalBalance: KcalBalanceResponse | null;
}) {
  const current = latestPoint?.display_value;
  const correctionEstimate = quality?.correction_now_mmol_l ?? correction;
  const delta = latestPoint && previousPoint ? latestPoint.display_value - previousPoint.display_value : 0;
  const trend = delta > 0.2 ? "↑" : delta < -0.2 ? "↓" : "→";

  return (
    <div className="card" style={{ marginBottom: 22, overflow: "hidden" }}>
      <div className="row" style={{ alignItems: "stretch" }}>
        <div style={{ padding: "20px 22px", borderRight: "1px solid var(--hairline)", minWidth: 200 }}>
          <div className="lbl">сейчас</div>
          <div className="row gap-6" style={{ alignItems: "baseline", marginTop: 6 }}>
            <span className="g-now">{formatNumber(current)}</span>
            <span style={{ fontSize: 12, color: "var(--ink-3)" }}>ммоль/л</span>
          </div>
          <div className="row gap-6" style={{ alignItems: "center", marginTop: 6 }}>
            <span className="tag accent">{trend} {delta !== 0 ? `${formatSigned(correctionEstimate ?? delta)}` : ""}</span>
          </div>
        </div>
        <div style={{ padding: "20px 22px", borderRight: "1px solid var(--hairline)", flex: 1 }}>
          <div className="lbl">время в диапазоне · 24ч</div>
          <div className="row" style={{ height: 8, marginTop: 12, borderRadius: 1, overflow: "hidden" }}>
            <div style={{ width: "4%", background: "var(--warn)" }} />
            <div style={{ width: "68%", background: "var(--good)" }} />
            <div style={{ width: "26%", background: "var(--accent)" }} />
            <div style={{ width: "2%", background: "var(--ink)" }} />
          </div>
          <div className="row" style={{ marginTop: 8, gap: 14, fontSize: 11, color: "var(--ink-3)" }}>
            <span><span className="dot-marker" style={{ background: "var(--warn)" }} /> &lt;3.9 <b className="mono" style={{ color: "var(--ink)", fontWeight: 500, marginLeft: 4 }}>4%</b></span>
            <span><span className="dot-marker" style={{ background: "var(--good)" }} /> 3.9–9.3 <b className="mono" style={{ color: "var(--ink)", fontWeight: 500, marginLeft: 4 }}>68%</b></span>
            <span><span className="dot-marker" style={{ background: "var(--accent)" }} /> 9.3–13 <b className="mono" style={{ color: "var(--ink)", fontWeight: 500, marginLeft: 4 }}>26%</b></span>
            <span><span className="dot-marker" style={{ background: "var(--ink)" }} /> &gt;13 <b className="mono" style={{ color: "var(--ink)", fontWeight: 500, marginLeft: 4 }}>2%</b></span>
          </div>
        </div>
        <div style={{ padding: "20px 22px", minWidth: 240 }}>
          <div className="row" style={{ justifyContent: "space-between", alignItems: "baseline" }}>
            <span className="lbl">сенсор {sensorName(sensor)}</span>
            <span className="tag good">актив.</span>
          </div>
          <div className="row gap-6" style={{ alignItems: "baseline", marginTop: 6 }}>
            <span className="mono" style={{ fontSize: 26, fontWeight: 500 }}>{formatNumber(quality?.sensor_age_days)}</span>
            <span style={{ fontSize: 12, color: "var(--ink-3)" }}>/ {formatNumber(sensor?.expected_life_days, 0)} дней</span>
          </div>
          <div className="pbar" style={{ marginTop: 8 }}>
            <i style={{ width: `${((quality?.sensor_age_days ?? 0) / (sensor?.expected_life_days ?? 15) * 100)}%` }} />
          </div>
          <div className="row" style={{ marginTop: 6, fontSize: 11, color: "var(--ink-3)", justifyContent: "space-between" }}>
            <span>{sensorPhaseCompact(quality?.sensor_phase, quality?.sensor_age_days)}</span>
            <span className="mono">{quality?.quality_score ?? 0}/100</span>
          </div>
        </div>
      </div>
      {kcalBalance?.bmr_available && kcalBalance.net_balance != null ? (
        <div className="row" style={{ borderTop: "1px solid var(--hairline)", padding: "10px 22px", gap: 24, fontSize: 11, color: "var(--ink-3)", alignItems: "center" }}>
          <span>смещ. <b className="mono" style={{ color: "var(--ink)", fontWeight: 500 }}>{formatSigned(quality?.correction_now_mmol_l ?? correction)} ммоль/л</b></span>
          <span>ккал <b className="mono" style={{ color: "var(--ink)", fontWeight: 500 }}>{Math.round(kcalBalance.kcal_in)}</b></span>
          <span>TDEE <b className="mono" style={{ color: "var(--ink)", fontWeight: 500 }}>{Math.round(kcalBalance.tdee ?? 0)}</b></span>
          <span>шаги <b className="mono" style={{ color: "var(--ink)", fontWeight: 500 }}>{kcalBalance.steps ?? 0}</b></span>
          <span>баланс <b className="mono" style={{ color: ((kcalBalance.net_balance) > 0 ? "var(--warn)" : "var(--good)"), fontWeight: 500 }}>{kcalBalance.net_balance > 0 ? "+" : ""}{Math.round(kcalBalance.net_balance)}</b></span>
        </div>
      ) : (
        <div className="row" style={{ borderTop: "1px solid var(--hairline)", padding: "10px 22px", gap: 24, fontSize: 11, color: "var(--ink-3)", alignItems: "center" }}>
          <span>смещ. <b className="mono" style={{ color: "var(--ink)", fontWeight: 500 }}>{formatSigned(quality?.correction_now_mmol_l ?? correction)} ммоль/л</b></span>
        </div>
      )}
    </div>
  );
}

function SensorPanel({
  currentSensor,
  quality,
  data,
  trust,
  validCalibrationPoints,
  recentFingersticks,
  sensorList,
  openNewFingerstickForm,
  toggleSensorEdit,
  recalculate,
  recalculatePending,
  editFingerstick,
}: {
  currentSensor: SensorSessionResponse | null;
  quality?: GlucoseDashboardResponse["quality"];
  data?: GlucoseDashboardResponse;
  trust: string;
  validCalibrationPoints: number;
  recentFingersticks: Fingerstick[];
  sensorList: SensorSessionResponse[];
  openNewFingerstickForm: () => void;
  toggleSensorEdit: () => void;
  recalculate: ReturnType<typeof useRecalculateSensorCalibration>;
  recalculatePending: boolean;
  editFingerstick: (row: Fingerstick) => void;
}) {
  return (
    <>
      <div className="lbl">текущий сенсор</div>
      <div className="row" style={{ alignItems: "baseline", justifyContent: "space-between", marginTop: 4 }}>
        <h2 style={{ margin: 0, fontFamily: "var(--serif)", fontSize: 24, fontWeight: 500 }}>{sensorName(currentSensor)}</h2>
        <span className="tag good">актив.</span>
      </div>
      <div style={{ fontSize: 11, color: "var(--ink-3)", marginTop: 4 }}>
        <span className="mono">{currentSensor?.model || "—"}</span> · день <span className="mono">{formatNumber(quality?.sensor_age_days)} / {formatNumber(currentSensor?.expected_life_days, 0)}</span>
      </div>

      <div style={{ marginTop: 22 }}>
        <div className="lbl" style={{ marginBottom: 6 }}>Качество</div>
        <div className="row" style={{ alignItems: "baseline", gap: 4 }}>
          <span className="mono" style={{ fontSize: 28, fontWeight: 500 }}>{quality?.quality_score ?? 0}</span>
          <span className="mono" style={{ fontSize: 12, color: "var(--ink-3)" }}>/ 100</span>
        </div>
        <div className="pbar good" style={{ marginTop: 6 }}><i style={{ width: `${quality?.quality_score ?? 0}%` }} /></div>
      </div>

      <div className="row" style={{ marginTop: 18, gap: 0, borderTop: "1px solid var(--hairline)", borderBottom: "1px solid var(--hairline)" }}>
        {[
          { l: "артефакты", v: String(data?.artifacts.length ?? 0) },
          { l: "compr. lows", v: String(quality?.suspected_compression_count ?? 0) },
          { l: "noise", v: formatNumber(quality?.noise_score) },
          { l: "доверие", v: trust },
        ].map((m, i) => (
          <div key={i} style={{ flex: 1, padding: "10px 0", borderRight: i < 3 ? "1px solid var(--hairline)" : "none", textAlign: "center" }}>
            <div className="mono" style={{ fontSize: 13 }}>{m.v}</div>
            <div className="lbl" style={{ marginTop: 2, fontSize: 9 }}>{m.l}</div>
          </div>
        ))}
      </div>

      <div className="card-offset-box">
        <div className="lbl">оценка смещения</div>
        <div className="row" style={{ alignItems: "baseline", marginTop: 4, gap: 4 }}>
          <span className="mono" style={{ fontSize: 22, fontWeight: 500 }}>{formatSigned(quality?.correction_now_mmol_l ?? quality?.median_delta_mmol_l)}</span>
          <span style={{ fontSize: 11, color: "var(--ink-3)" }}>ммоль/л</span>
        </div>
        <div style={{ fontSize: 11, color: "var(--ink-3)", marginTop: 4, lineHeight: 1.4 }}>
          {fingerstickCountLabel(quality?.fingerstick_count ?? validCalibrationPoints)} · {sensorPhaseCompact(quality?.sensor_phase, quality?.sensor_age_days)}
        </div>
        <div className="row" style={{ marginTop: 12, gap: 12 }}>
          <div style={{ flex: 1 }}>
            <div className="lbl" style={{ fontSize: 9 }}>медиана Δ</div>
            <div className="mono" style={{ fontSize: 12 }}>{formatSigned(quality?.median_delta_mmol_l)}</div>
          </div>
          <div style={{ flex: 1 }}>
            <div className="lbl" style={{ fontSize: 9 }}>диапазон</div>
            <div className="mono" style={{ fontSize: 12 }}>
              {quality?.delta_min_mmol_l != null && quality?.delta_max_mmol_l != null
                ? `${formatSigned(quality.delta_min_mmol_l)}…${formatSigned(quality.delta_max_mmol_l)}`
                : "—"}
            </div>
          </div>
        </div>
        <div className="row" style={{ marginTop: 8, gap: 12 }}>
          <div style={{ flex: 1 }}>
            <div className="lbl" style={{ fontSize: 9 }}>дрейф</div>
            <div className="mono" style={{ fontSize: 12 }}>{formatSigned(quality?.b1_capped_mmol_l_per_day)}/день</div>
          </div>
          <div style={{ flex: 1 }}>
            <div className="lbl" style={{ fontSize: 9 }}>mard</div>
            <div className="mono" style={{ fontSize: 12 }}>{formatNumber(quality?.mard_percent)}%</div>
          </div>
        </div>
      </div>

      <div className="col gap-8" style={{ marginTop: 18 }}>
        <button className="btn dark" onClick={openNewFingerstickForm}><Plus size={13} /> Запись из пальца</button>
        <button className="btn" onClick={toggleSensorEdit}><Activity size={13} /> {currentSensor ? "Редактировать сенсор" : "Создать сенсор"}</button>
        {currentSensor?.id ? (
          <button className="btn" disabled={recalculatePending} onClick={() => recalculate.mutate(currentSensor.id)}><RefreshCw size={13} /> Пересчитать</button>
        ) : null}
      </div>

      <div style={{ marginTop: 22 }}>
        <div className="lbl">последняя запись из пальца</div>
        {recentFingersticks.length ? (
          recentFingersticks.slice(0, 1).map((row) => {
            const nearest = nearestPoint(data?.points ?? [], row.measured_at);
            const delta = nearest ? row.glucose_mmol_l - nearest.raw_value : null;
            return (
              <div key={row.id} className="row" style={{ alignItems: "center", marginTop: 6, padding: "10px 12px", border: "1px solid var(--hairline)", borderRadius: "var(--radius)", background: "var(--surface)", gap: 8, cursor: "pointer" }} onClick={() => editFingerstick(row)}>
                <span className="mono" style={{ fontSize: 11, color: "var(--ink-3)" }}>{formatTime(row.measured_at)}</span>
                <span className="mono" style={{ fontSize: 13, fontWeight: 500 }}>{formatNumber(row.glucose_mmol_l)}</span>
                <span style={{ fontSize: 11, color: "var(--ink-3)" }}>ммоль/л</span>
                <span className="spacer" />
                <span className="tag accent">Δ {formatSigned(delta)}</span>
              </div>
            );
          })
        ) : (
          <div style={{ fontSize: 12, color: "var(--ink-4)", marginTop: 6 }}>Записей пока нет.</div>
        )}
      </div>

      <div style={{ marginTop: 22 }}>
        <div className="lbl">предыдущие сенсоры</div>
        <div style={{ marginTop: 8 }}>
          {sensorList.length ? (
            sensorList.slice(0, 5).map((s) => (
              <div key={s.id} className="row" style={{ alignItems: "center", padding: "8px 0", borderTop: "1px solid var(--hairline)", borderBottom: "1px solid var(--hairline)", gap: 10 }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 12 }}>{sensorName(s)}</div>
                  <div className="mono" style={{ fontSize: 10, color: "var(--ink-4)", marginTop: 2 }}>{formatDateTime(s.started_at)} · день {formatNumber(s.expected_life_days, 0)}</div>
                </div>
                <span className="mono" style={{ fontSize: 11, color: "var(--ink-3)" }}>—</span>
              </div>
            ))
          ) : (
            <div style={{ fontSize: 12, color: "var(--ink-4)" }}>Сенсоры пока не заведены.</div>
          )}
        </div>
      </div>

    </>
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
  cgmPeakAt: string | null;
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
  hoveredEpisodeId,
  onEpisodeHover,
  onEpisodeSelect,
  onTabChange,
  rows,
  selectedEpisodeId,
}: {
  activeTab: ActivityTab;
  episodes: GroupedEpisode[];
  hoveredEpisodeId: string | null;
  onEpisodeHover: (episodeId: string | null) => void;
  onEpisodeSelect: (episodeId: string) => void;
  onTabChange: (tab: ActivityTab) => void;
  rows: EventRow[];
  selectedEpisodeId: string | null;
}) {
  return (
    <section className="border border-[var(--hairline)] bg-[var(--surface)]">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--hairline)] px-5 py-4">
        <div>
          <h2 className="text-[18px] text-[var(--ink)]">Активность на графике</h2>
          <p className="mt-1 text-[12px] text-[var(--ink-3)]">
            Эпизоды группируют еду и ближайший контекст, raw события доступны отдельно.
          </p>
        </div>
        <div className="flex border border-[var(--hairline)]">
          {[
            { label: "Эпизоды", value: "episodes" as const },
            { label: "События", value: "events" as const },
          ].map((item) => (
            <button
              className={`px-3 py-1.5 text-[12px] ${
                activeTab === item.value
                  ? "bg-[var(--surface-2)] text-[var(--ink)] shadow-[inset_0_-2px_0_var(--ink-3)]"
                  : "bg-[var(--surface)] text-[var(--ink-3)]"
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
          hoveredEpisodeId={hoveredEpisodeId}
          onEpisodeHover={onEpisodeHover}
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
  hoveredEpisodeId,
  onEpisodeHover,
  onEpisodeSelect,
  selectedEpisodeId,
}: {
  episodes: GroupedEpisode[];
  hoveredEpisodeId: string | null;
  onEpisodeHover: (episodeId: string | null) => void;
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
      <div className="px-5 py-8 text-center text-[13px] text-[var(--ink-3)]">
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
          hovered={hoveredEpisodeId === episode.id}
          key={episode.id}
          onHover={onEpisodeHover}
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
  hovered,
  onHover,
  onToggle,
  selected,
}: {
  episode: GroupedEpisode;
  expanded: boolean;
  hovered: boolean;
  onHover: (episodeId: string | null) => void;
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
        selected || hovered ? "bg-[#F6F0E5]" : ""
      }`}
      onMouseEnter={() => onHover(episode.id)}
      onMouseLeave={() => onHover(null)}
      style={{
        boxShadow: selected || hovered ? "inset 2px 0 0 var(--accent)" : "none",
      }}
    >
      <button
        aria-pressed={selected}
        className="grid w-full gap-4 px-5 py-4 text-left transition hover:bg-[var(--bg)] lg:grid-cols-[112px_1fr_180px_220px]"
        onClick={onToggle}
        type="button"
      >
        <div className="font-mono text-[14px] text-[var(--ink)]">
          {formatEpisodeRange(episode.startAt, episode.endAt)}
        </div>
        <div className="grid gap-1">
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-[16px] text-[var(--ink)]">Приём пищи</span>
            <span className="border border-[var(--hairline)] bg-[var(--bg)] px-2 py-1 text-[10px] uppercase tracking-[0.06em] text-[var(--ink-3)]">
              {eventCount} событий
            </span>
          </div>
          <div className="text-[13px] text-[var(--ink-3)]">{episode.title}</div>
        </div>
        <div className="grid grid-cols-3 gap-3 font-mono text-[13px] text-[var(--ink)] lg:grid-cols-1">
          <span>{formatNumber(episode.carbsTotal, 1)} г</span>
          <span>{formatNumber(episode.kcalTotal, 0)} ккал</span>
          <span>{formatNumber(episode.insulinTotal, 1)} ЕД</span>
        </div>
        <div className="grid gap-1 text-[12px] text-[var(--ink-3)]">
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
            <span className="font-mono text-[var(--ink)]">{row.time}</span>
            <span className="text-[var(--ink)]">{row.label}</span>
            <span className="font-mono text-[var(--ink-3)]">{row.data}</span>
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
          <thead className="text-[10px] uppercase tracking-[0.08em] text-[var(--ink-3)]">
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
                  <td className="px-5 py-3 font-mono text-[var(--ink)]">{row.time}</td>
                  <td className="px-5 py-3 text-[var(--ink)]">{row.type}</td>
                  <td className="px-5 py-3 font-mono text-[var(--ink)]">{row.data}</td>
                  <td className="px-5 py-3 font-mono text-[var(--ink-3)]">{row.cgm}</td>
                  <td className="px-5 py-3 text-[var(--ink-3)]">{row.comment}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td className="px-5 py-8 text-center text-[var(--ink-3)]" colSpan={5}>
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
      cgmPeakAt: cgm.maxAt,
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
    return {
      max: null,
      maxAt: null,
      min: null,
      minAt: null,
      start: null,
      timeToMax: null,
      timeToMin: null,
    };
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
    maxAt: maxPoint.timestamp,
    min: valueFor(minPoint),
    minAt: minPoint.timestamp,
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

type ChartDensity = "full" | "compact" | "aggregate";

type DailyAggregate = {
  carbs: number;
  fingersticks: number;
  insulin: number;
  meals: number;
};

function GlucoseChart({
  data,
  episodes,
  hoveredEpisodeId,
  loading,
  mode,
  onEpisodeHover,
  onEpisodeSelect,
  preset,
  selectedEpisodeId,
}: {
  data?: GlucoseDashboardResponse;
  episodes: GroupedEpisode[];
  hoveredEpisodeId: string | null;
  loading: boolean;
  mode: GlucoseMode;
  onEpisodeHover: (episodeId: string | null) => void;
  onEpisodeSelect: (episodeId: string) => void;
  preset: RangePreset | "custom";
  selectedEpisodeId: string | null;
}) {
  const [hoveredDayIndex, setHoveredDayIndex] = useState<number | null>(null);
  const points = data?.points ?? [];
  const width = 1180;
  const left = 64;
  const right = 20;
  const chartTop = 24;
  const chartHeight = 258;
  const chartBottom = chartTop + chartHeight;
  const laneGap = 32;
  const laneHeight = 34;
  const lanesTop = chartBottom + 34;
  const lane1Y = lanesTop;
  const lane2Y = lane1Y + laneHeight + laneGap;
  const lane3Y = lane2Y + laneHeight + laneGap;
  const lanesBottom = lane3Y + laneHeight;
  const height = lanesBottom + 34;
  const chartWidth = width - left - right;
  const fromMs = data ? Date.parse(data.from_datetime) : Date.now() - 6 * 3600000;
  const toMs = data ? Date.parse(data.to_datetime) : Date.now();
  const duration = Math.max(toMs - fromMs, 1);
  const density = chartDensityForRange(preset, duration);
  const chartValues = [
    ...points.flatMap((point) => [
      point.raw_value,
      point.smoothed_value,
      point.normalized_value,
      point.display_value,
    ]),
    ...(data?.fingersticks.map((row) => row.glucose_mmol_l) ?? []),
  ].filter((value): value is number => typeof value === "number");
  const { max: maxValue, min: minValue } = glucoseChartDomain(chartValues);
  const yRange = Math.max(maxValue - minValue, 1);
  const scaleXMs = (ms: number) =>
    left + clamp((ms - fromMs) / duration, 0, 1) * chartWidth;
  const scaleX = (iso: string) => scaleXMs(Date.parse(iso));
  const scaleY = (value: number) =>
    chartTop + (1 - (value - minValue) / yRange) * chartHeight;
  const line = (
    source: DashboardPoint[],
    value: (point: DashboardPoint) => number | null | undefined,
  ) =>
    source
      .map((point) => {
        const yValue = value(point);
        if (yValue === null || yValue === undefined) return "";
        return `${scaleX(point.timestamp)},${scaleY(yValue)}`;
      })
      .filter(Boolean)
      .join(" ");
  const rawLine = line(points, (point) => point.raw_value);
  const mainLine = line(points, (point) => glucosePointValue(point, mode));
  const xTicks = timeAxisTicks(fromMs, toMs);
  const yTicks = glucoseTickValues(minValue, maxValue);
  const dailyAggregates =
    density === "aggregate"
      ? buildDailyAggregates(data, episodes, fromMs, toMs)
      : [];
  const maxDayCarbs = Math.max(...dailyAggregates.map((day) => day.carbs), 1);
  const maxDayInsulin = Math.max(
    ...dailyAggregates.map((day) => day.insulin),
    1,
  );
  const activeEpisodeId = hoveredEpisodeId ?? selectedEpisodeId;
  const activeEpisode =
    activeEpisodeId !== null
      ? episodes.find((episode) => episode.id === activeEpisodeId) ?? null
      : null;
  const activeDayIndex =
    hoveredDayIndex ??
    (activeEpisode
      ? aggregateIndexForMs(Date.parse(activeEpisode.startAt), fromMs, toMs)
      : null);

  if (!points.length) {
    return (
      <div
        aria-label="График глюкозы"
        className="grid h-[520px] place-items-center text-[14px] text-[var(--ink-3)]"
        role="img"
      >
        {loading ? "Загружаю CGM..." : "CGM за период не найден."}
      </div>
    );
  }

  const targetTop = scaleY(9.3);
  const targetBottom = scaleY(3.9);

  return (
    <div className="overflow-x-auto">
      <svg
        aria-label="График глюкозы"
        className="min-w-[940px] text-[var(--ink-3)]"
        preserveAspectRatio="xMidYMid meet"
        role="img"
        style={{
          display: "block",
          fontFamily: "var(--sans)",
          width: "100%",
        }}
        viewBox={`0 0 ${width} ${height}`}
      >
        <rect fill="var(--surface)" height={height} width={width} />

        <rect
          fill="var(--accent-bg)"
          height={Math.max(1, targetBottom - targetTop)}
          opacity="0.35"
          width={chartWidth}
          x={left}
          y={targetTop}
        />
        <text
          fill="var(--accent)"
          fontFamily="var(--mono)"
          fontSize="10"
          x={left + 8}
          y={targetTop + 13}
        >
          целевой 3.9–9.3
        </text>

        {data?.artifacts.map((artifact) => {
          const x = scaleX(artifact.start_at);
          const w = Math.max(5, scaleX(artifact.end_at) - x);
          return (
            <rect
              fill="var(--shade)"
              height={chartHeight}
              key={`${artifact.start_at}-${artifact.kind}`}
              opacity={0.54}
              width={w}
              x={x}
              y={chartTop}
            />
          );
        })}

        {density === "aggregate" && activeDayIndex !== null ? (
          <rect
            fill="var(--accent)"
            height={lanesBottom - chartTop}
            opacity="0.055"
            width={chartWidth / 7 - 4}
            x={left + activeDayIndex * (chartWidth / 7) + 2}
            y={chartTop}
          />
        ) : null}

        {activeEpisode && density !== "aggregate" ? (
          <EpisodeChartHighlight
            chartBottom={chartBottom}
            chartHeight={chartHeight}
            chartTop={chartTop}
            episode={activeEpisode}
            laneY={lane1Y + laneHeight / 2}
            scaleX={scaleX}
            scaleY={scaleY}
          />
        ) : null}

        {yTicks.map((tick) => (
          <g key={tick}>
            <line
              stroke={tick === 3.9 || tick === 9.3 ? "var(--accent-soft)" : "var(--hairline)"}
              strokeDasharray={tick === 3.9 || tick === 9.3 ? undefined : "2 5"}
              x1={left}
              x2={width - right}
              y1={scaleY(tick)}
              y2={scaleY(tick)}
            />
            <text
              fill="var(--ink-4)"
              fontFamily="var(--mono)"
              fontSize="10"
              textAnchor="end"
              x={left - 8}
              y={scaleY(tick) + 3}
            >
              {tick.toFixed(1)}
            </text>
          </g>
        ))}

        {mode !== "raw" ? (
          <polyline
            fill="none"
            opacity="0.7"
            points={rawLine}
            stroke="var(--ink-3)"
            strokeDasharray="2 3"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="1.3"
          />
        ) : null}
        <polyline
          fill="none"
          points={mainLine}
          stroke="var(--ink)"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.9"
        />

        {points.map((point, i) => {
          const mainVal = glucosePointValue(point, mode);
          if (mainVal == null) return null;
          const tooltipText = [
            formatTime(point.timestamp),
            `Raw: ${point.raw_value.toFixed(1)}`,
            point.normalized_value != null
              ? `Нормализованная: ${point.normalized_value.toFixed(1)}`
              : null,
            point.correction_mmol_l != null
              ? `Смещение: ${formatSigned(point.correction_mmol_l)}`
              : null,
          ]
            .filter(Boolean)
            .join("\n");
          return (
            <circle
              cx={scaleX(point.timestamp)}
              cy={scaleY(mainVal)}
              fill="transparent"
              key={`pt-${i}`}
              r="7"
            >
              <title>{tooltipText}</title>
            </circle>
          );
        })}

        {data?.fingersticks.map((row) => {
          const x = scaleX(row.measured_at);
          const y = scaleY(row.glucose_mmol_l);
          return (
            <polygon
              fill="var(--surface)"
              key={row.id}
              points={`${x},${y - 6} ${x + 6},${y} ${x},${y + 6} ${x - 6},${y}`}
              stroke="var(--ink)"
              strokeWidth="1.4"
            >
              <title>
                {`${formatTime(row.measured_at)} · ${formatNumber(row.glucose_mmol_l)} ммоль/л`}
              </title>
            </polygon>
          );
        })}

        <line
          stroke="var(--ink)"
          strokeWidth="1"
          x1={left}
          x2={width - right}
          y1={chartBottom}
          y2={chartBottom}
        />

        {[
          { label: "Питание", y: lane1Y },
          { label: "Инсулин", y: lane2Y },
          { label: "Калибровка", y: lane3Y },
        ].map((lane) => (
          <g key={lane.label}>
            <text
              fill="var(--ink-4)"
              fontSize="10"
              fontWeight="500"
              textAnchor="end"
              x={left - 8}
              y={lane.y + laneHeight / 2 + 4}
            >
              {lane.label}
            </text>
            <line
              stroke="var(--hairline)"
              strokeWidth="0.8"
              x1={left}
              x2={width - right}
              y1={lane.y + laneHeight / 2}
              y2={lane.y + laneHeight / 2}
            />
          </g>
        ))}

        {density === "aggregate" ? (
          dailyAggregates.map((day, index) => {
            const colW = chartWidth / dailyAggregates.length;
            const cx = left + index * colW + colW / 2;
            const active = activeDayIndex === index;
            const carbsBarHeight = (day.carbs / maxDayCarbs) * (laneHeight - 8);
            const insulinBarHeight =
              day.insulin > 0
                ? (day.insulin / maxDayInsulin) * (laneHeight - 8)
                : 0;
            return (
              <g
                cursor="pointer"
                key={`day-${index}`}
                onMouseEnter={() => setHoveredDayIndex(index)}
                onMouseLeave={() => setHoveredDayIndex(null)}
              >
                <title>
                  {`${axisLabelForTime(fromMs + (index + 0.5) * (duration / 7), "aggregate", duration)} · ${Math.round(
                    day.carbs,
                  )} г · ${day.meals} приёмов · ${formatNumber(day.insulin, 1)} ЕД · ${day.fingersticks} калибр.`}
                </title>
                <rect
                  fill={active ? "var(--accent)" : "var(--accent-soft)"}
                  height={carbsBarHeight}
                  width={Math.max(12, colW * 0.48)}
                  x={cx - Math.max(12, colW * 0.48) / 2}
                  y={lane1Y + laneHeight - 4 - carbsBarHeight}
                />
                <text
                  fill={active ? "var(--accent)" : "var(--ink-2)"}
                  fontFamily="var(--mono)"
                  fontSize="10"
                  fontWeight="500"
                  textAnchor="middle"
                  x={cx}
                  y={lane1Y - 3}
                >
                  {Math.round(day.carbs)}г
                </text>
                <text
                  fill="var(--ink-4)"
                  fontFamily="var(--mono)"
                  fontSize="9"
                  textAnchor="middle"
                  x={cx}
                  y={lane1Y + laneHeight + 10}
                >
                  {day.meals} приём.
                </text>

                {insulinBarHeight > 0 ? (
                  <rect
                    fill={active ? "var(--ink)" : "var(--ink-3)"}
                    height={insulinBarHeight}
                    width={Math.max(8, colW * 0.28)}
                    x={cx - Math.max(8, colW * 0.28) / 2}
                    y={lane2Y + laneHeight - 4 - insulinBarHeight}
                  />
                ) : (
                  <line
                    stroke="var(--hairline-2)"
                    strokeWidth="1"
                    x1={cx - 7}
                    x2={cx + 7}
                    y1={lane2Y + laneHeight - 5}
                    y2={lane2Y + laneHeight - 5}
                  />
                )}
                <text
                  fill={active ? "var(--ink)" : "var(--ink-2)"}
                  fontFamily="var(--mono)"
                  fontSize="10"
                  fontWeight="500"
                  textAnchor="middle"
                  x={cx}
                  y={lane2Y - 3}
                >
                  {day.insulin > 0 ? day.insulin.toFixed(1) : "—"}
                </text>

                <text
                  fill={day.fingersticks > 0 ? "var(--ink-2)" : "var(--ink-4)"}
                  fontFamily="var(--mono)"
                  fontSize="13"
                  fontWeight="500"
                  textAnchor="middle"
                  x={cx}
                  y={lane3Y + laneHeight / 2 + 4}
                >
                  {day.fingersticks}
                </text>
              </g>
            );
          })
        ) : density === "compact" ? (
          <>
            {episodes.map((episode) => {
              const x1 = scaleX(episode.startAt);
              const x2 = scaleX(episode.endAt);
              const cx = (x1 + x2) / 2;
              const cy = lane1Y + laneHeight / 2;
              const active = activeEpisodeId === episode.id;
              const r = Math.max(4, Math.min(12, 3 + Math.sqrt(episode.carbsTotal) * 0.9));
              return (
                <g
                  cursor="pointer"
                  key={`meal-dot-${episode.id}`}
                  onClick={() => onEpisodeSelect(episode.id)}
                  onMouseEnter={() => onEpisodeHover(episode.id)}
                  onMouseLeave={() => onEpisodeHover(null)}
                >
                  <title>{episodeTooltip(episode)}</title>
                  {x2 - x1 > 10 ? (
                    <line
                      opacity="0.82"
                      stroke={active ? "var(--accent)" : "var(--accent-soft)"}
                      strokeWidth="2.5"
                      x1={x1}
                      x2={x2}
                      y1={cy}
                      y2={cy}
                    />
                  ) : null}
                  <circle
                    cx={cx}
                    cy={cy}
                    fill={active ? "var(--accent)" : "var(--accent-bg)"}
                    r={r}
                    stroke={active ? "var(--accent)" : "var(--accent-soft)"}
                    strokeWidth={active ? "1.6" : "1"}
                  />
                </g>
              );
            })}
            {(data?.insulin_events ?? []).map((event, index) => {
              const x = scaleX(event.timestamp);
              return (
                <rect
                  fill="var(--ink)"
                  height={laneHeight - 12}
                  key={`insulin-tick-${event.timestamp}-${index}`}
                  width="2"
                  x={x - 1}
                  y={lane2Y + 6}
                >
                  <title>
                    {`${formatTime(event.timestamp)} · ${formatNumber(event.insulin_units, 1)} ЕД`}
                  </title>
                </rect>
              );
            })}
            {(data?.fingersticks ?? []).map((row) => {
              const x = scaleX(row.measured_at);
              const cy = lane3Y + laneHeight / 2;
              return (
                <rect
                  fill="var(--surface)"
                  height="8"
                  key={`finger-lane-${row.id}`}
                  stroke="var(--ink)"
                  strokeWidth="1.2"
                  transform={`rotate(45 ${x} ${cy})`}
                  width="8"
                  x={x - 4}
                  y={cy - 4}
                >
                  <title>
                    {`${formatTime(row.measured_at)} · ${formatNumber(row.glucose_mmol_l)} ммоль/л`}
                  </title>
                </rect>
              );
            })}
            <text
              fill="var(--ink-4)"
              fontFamily="var(--mono)"
              fontSize="9"
              fontStyle="italic"
              textAnchor="end"
              x={width - right}
              y={lane1Y - 3}
            >
              {episodes.length} приёмов · наведите для деталей
            </text>
          </>
        ) : (
          <>
            {episodes.map((episode) => {
              const x1 = scaleX(episode.startAt);
              const x2 = scaleX(episode.endAt);
              const pillWidth = Math.max(24, x2 - x1) + 8;
              const pillX = x1 - 4;
              const active = activeEpisodeId === episode.id;
              const totalCarbs = Math.max(episode.carbsTotal, 1);
              return (
                <g
                  cursor="pointer"
                  key={`meal-pill-${episode.id}`}
                  onClick={() => onEpisodeSelect(episode.id)}
                  onMouseEnter={() => onEpisodeHover(episode.id)}
                  onMouseLeave={() => onEpisodeHover(null)}
                >
                  <title>{episodeTooltip(episode)}</title>
                  <rect
                    fill={active ? "var(--accent)" : "var(--accent-bg)"}
                    height={laneHeight - 8}
                    rx={(laneHeight - 8) / 2}
                    stroke={active ? "var(--accent)" : "var(--accent-soft)"}
                    strokeWidth="1"
                    width={pillWidth}
                    x={pillX}
                    y={lane1Y + 4}
                  />
                  {episode.foodEvents.map((event, eventIndex) => (
                    <circle
                      cx={scaleX(event.timestamp)}
                      cy={lane1Y + laneHeight / 2}
                      fill={active ? "var(--surface)" : "var(--accent)"}
                      key={`meal-event-${episode.id}-${eventIndex}`}
                      r={Math.max(2.2, Math.min(5, (event.carbs_g / totalCarbs) * 16))}
                    />
                  ))}
                  <text
                    fill={active ? "var(--accent)" : "var(--ink-2)"}
                    fontFamily="var(--mono)"
                    fontSize="10"
                    fontWeight="500"
                    textAnchor="middle"
                    x={pillX + pillWidth / 2}
                    y={lane1Y - 3}
                  >
                    {formatNumber(episode.carbsTotal, 1)} г
                  </text>
                  <text
                    fill="var(--ink-4)"
                    fontFamily="var(--mono)"
                    fontSize="9"
                    textAnchor="middle"
                    x={pillX + pillWidth / 2}
                    y={lane1Y + laneHeight + 10}
                  >
                    {episode.foodEvents.length} событий · {formatEpisodeRange(episode.startAt, episode.endAt)}
                  </text>
                </g>
              );
            })}
            {(data?.insulin_events ?? []).map((event, index) => {
              const x = scaleX(event.timestamp);
              const badgeX = Math.min(x + 26, width - right - 24);
              return (
                <g key={`insulin-full-${event.timestamp}-${index}`}>
                  <title>
                    {`${formatTime(event.timestamp)} · ${formatNumber(event.insulin_units, 1)} ЕД`}
                  </title>
                  <rect
                    fill="var(--ink)"
                    height={laneHeight - 10}
                    width="3"
                    x={x - 1.5}
                    y={lane2Y + 5}
                  />
                  <rect
                    fill="var(--surface)"
                    height="18"
                    rx="2"
                    stroke="var(--ink)"
                    strokeWidth="1"
                    width="44"
                    x={badgeX - 22}
                    y={lane2Y + 8}
                  />
                  <text
                    fill="var(--ink)"
                    fontFamily="var(--mono)"
                    fontSize="10"
                    fontWeight="500"
                    textAnchor="middle"
                    x={badgeX}
                    y={lane2Y + 21}
                  >
                    {formatNumber(event.insulin_units, 1)} ЕД
                  </text>
                  <text
                    fill="var(--ink-4)"
                    fontFamily="var(--mono)"
                    fontSize="9"
                    textAnchor="middle"
                    x={x}
                    y={lane2Y + laneHeight + 10}
                  >
                    {formatTime(event.timestamp)}
                  </text>
                </g>
              );
            })}
            {(data?.fingersticks ?? []).map((row) => {
              const x = scaleX(row.measured_at);
              const cy = lane3Y + laneHeight / 2;
              const labelOnLeft = x > width - right - 90;
              return (
                <g key={`finger-full-${row.id}`}>
                  <title>
                    {`${formatTime(row.measured_at)} · ${formatNumber(row.glucose_mmol_l)} ммоль/л`}
                  </title>
                  <rect
                    fill="var(--surface)"
                    height="10"
                    stroke="var(--ink)"
                    strokeWidth="1.4"
                    transform={`rotate(45 ${x} ${cy})`}
                    width="10"
                    x={x - 5}
                    y={cy - 5}
                  />
                  <text
                    fill="var(--ink)"
                    fontFamily="var(--mono)"
                    fontSize="10"
                    fontWeight="500"
                    textAnchor={labelOnLeft ? "end" : "start"}
                    x={x + (labelOnLeft ? -12 : 12)}
                    y={cy + 4}
                  >
                    {formatNumber(row.glucose_mmol_l)} ммоль
                  </text>
                  <text
                    fill="var(--ink-4)"
                    fontFamily="var(--mono)"
                    fontSize="9"
                    textAnchor="middle"
                    x={x}
                    y={lane3Y + laneHeight + 10}
                  >
                    {formatTime(row.measured_at)}
                  </text>
                </g>
              );
            })}
          </>
        )}

        {xTicks.map((tick, index) => {
          const x = left + (index / (xTicks.length - 1)) * chartWidth;
          return (
            <text
              fill="var(--ink-4)"
              fontFamily="var(--mono)"
              fontSize="9"
              key={tick}
              textAnchor="middle"
              x={x}
              y={height - 6}
            >
              {axisLabelForTime(tick, density, duration)}
            </text>
          );
        })}

        <g transform={`translate(${width - 448},${height - 8})`}>
          <LegendItem color="var(--ink-3)" dashed label="raw CGM" x={0} />
          <LegendItem color="var(--ink)" label={modeLabel(mode)} x={98} />
          <LegendItem color="var(--accent)" label="еда" x={244} />
          <LegendItem color="var(--ink)" label="инсулин" x={304} />
        </g>
      </svg>
    </div>
  );
}

function EpisodeChartHighlight({
  chartHeight,
  chartTop,
  episode,
  laneY,
  scaleX,
  scaleY,
}: {
  chartBottom: number;
  chartHeight: number;
  chartTop: number;
  episode: GroupedEpisode;
  laneY: number;
  scaleX: (iso: string) => number;
  scaleY: (value: number) => number;
}) {
  const x1 = scaleX(episode.startAt);
  const x2 = Math.max(scaleX(episode.endAt), x1 + 4);
  const peakX = episode.cgmPeakAt ? scaleX(episode.cgmPeakAt) : x2;
  const peakY = episode.cgmMax !== null ? scaleY(episode.cgmMax) : chartTop + chartHeight / 2;
  return (
    <g>
      <rect
        fill="var(--accent)"
        height={chartHeight}
        opacity="0.10"
        width={Math.max(4, x2 - x1)}
        x={x1}
        y={chartTop}
      />
      <line
        opacity="0.72"
        stroke="var(--accent)"
        strokeDasharray="2 3"
        strokeWidth="1"
        x1={peakX}
        x2={peakX}
        y1={peakY}
        y2={laneY}
      />
      <circle
        cx={peakX}
        cy={peakY}
        fill="var(--surface)"
        r="4"
        stroke="var(--accent)"
        strokeWidth="1.6"
      />
      {episode.cgmMax !== null ? (
        <text
          fill="var(--accent)"
          fontFamily="var(--mono)"
          fontSize="10"
          fontWeight="500"
          x={peakX + 8}
          y={peakY - 5}
        >
          пик {formatNumber(episode.cgmMax)}
        </text>
      ) : null}
    </g>
  );
}

function glucosePointValue(point: DashboardPoint, mode: GlucoseMode) {
  if (mode === "normalized") {
    return point.normalized_value ?? point.raw_value;
  }
  if (mode === "smoothed") return point.smoothed_value ?? point.raw_value;
  return point.raw_value;
}

function chartDensityForRange(
  preset: RangePreset | "custom",
  durationMs: number,
): ChartDensity {
  if (preset === "7d" || durationMs >= 6 * 24 * 60 * 60 * 1000) {
    return "aggregate";
  }
  if (
    preset === "12h" ||
    preset === "24h" ||
    durationMs > 6.5 * 60 * 60 * 1000
  ) {
    return "compact";
  }
  return "full";
}

function glucoseChartDomain(values: number[]) {
  const baseMin = 3.5;
  const baseMax = 12;
  if (!values.length) return { max: baseMax, min: baseMin };
  const rawMin = Math.min(...values, 3.9);
  const rawMax = Math.max(...values, 9.3);
  const min = rawMin < baseMin ? Math.max(0, Math.floor((rawMin - 0.6) * 2) / 2) : baseMin;
  const max = rawMax > baseMax ? Math.ceil((rawMax + 0.6) * 2) / 2 : baseMax;
  return { max, min };
}

function glucoseTickValues(minValue: number, maxValue: number) {
  return Array.from(new Set([minValue, 3.9, 6.5, 9.3, 12, maxValue]))
    .filter((tick) => tick >= minValue && tick <= maxValue)
    .sort((left, right) => left - right);
}

function timeAxisTicks(fromMs: number, toMs: number) {
  const duration = Math.max(toMs - fromMs, 1);
  return Array.from({ length: 7 }, (_, index) => fromMs + (duration * index) / 6);
}

function axisLabelForTime(ms: number, density: ChartDensity, durationMs: number) {
  if (density === "aggregate") {
    return new Intl.DateTimeFormat("ru-RU", { weekday: "short" })
      .format(new Date(ms))
      .replace(".", "");
  }
  if (durationMs > 6.5 * 60 * 60 * 1000) {
    return new Intl.DateTimeFormat("ru-RU", { hour: "2-digit" }).format(
      new Date(ms),
    );
  }
  return new Intl.DateTimeFormat("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(ms));
}

function buildDailyAggregates(
  data: GlucoseDashboardResponse | undefined,
  episodes: GroupedEpisode[],
  fromMs: number,
  toMs: number,
): DailyAggregate[] {
  const buckets: DailyAggregate[] = Array.from({ length: 7 }, () => ({
    carbs: 0,
    fingersticks: 0,
    insulin: 0,
    meals: 0,
  }));
  episodes.forEach((episode) => {
    const index = aggregateIndexForMs(Date.parse(episode.startAt), fromMs, toMs);
    buckets[index].carbs += episode.carbsTotal;
    buckets[index].meals += 1;
  });
  data?.insulin_events.forEach((event) => {
    const index = aggregateIndexForMs(Date.parse(event.timestamp), fromMs, toMs);
    buckets[index].insulin += event.insulin_units ?? 0;
  });
  data?.fingersticks.forEach((row) => {
    const index = aggregateIndexForMs(Date.parse(row.measured_at), fromMs, toMs);
    buckets[index].fingersticks += 1;
  });
  return buckets;
}

function aggregateIndexForMs(ms: number, fromMs: number, toMs: number) {
  const duration = Math.max(toMs - fromMs, 1);
  return clamp(Math.floor(((ms - fromMs) / duration) * 7), 0, 6);
}

export function LegacyGlucoseChart({
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
        className="grid h-[520px] place-items-center text-[14px] text-[var(--ink-3)]"
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
        className="min-w-[940px] text-[var(--ink-3)]"
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
        <text fill="var(--ink-3)" fontSize="11" x={left} y={18}>
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
                fill={selected ? "var(--ink)" : "var(--accent)"}
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
        <text fill="var(--ink-3)" fontSize="11" x={left + 8} y={scaleY(10) + 14}>
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
              fill="var(--ink-3)"
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
          stroke="var(--ink)"
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
                stroke="var(--ink)"
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
              stroke="var(--ink)"
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
          stroke="var(--ink)"
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
              fill="var(--ink-3)"
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
          stroke="var(--ink)"
          strokeWidth="1"
          width={chartWidth}
          x={left}
          y={overviewTop}
        />
        <text fill="var(--ink-3)" fontSize="11" x={left} y={height - 4}>
          обзор выбранного периода
        </text>

        <g transform={`translate(${width - 430},${height - 4})`}>
          <LegendItem color="#9B958B" dashed label="raw CGM" x={0} />
          <LegendItem color="var(--ink)" label={modeLabel(mode)} x={100} />
          <LegendItem color="var(--accent)" label="еда" x={258} />
          <LegendItem color="var(--ink)" label="инсулин" x={320} />
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
        stroke={selected ? "var(--ink)" : "var(--accent)"}
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
          stroke={selected ? "var(--ink)" : "none"}
          strokeWidth="1.2"
        />
      ) : (
        <>
          <text
            fill="var(--ink)"
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
              fill="var(--ink-3)"
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
        stroke="var(--ink)"
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
        stroke="var(--ink)"
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
      <text fill="var(--ink-3)" fontSize="11" x="25" y="-1">
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
        <h3 className="text-[14px] text-[var(--ink)]">Смещение по времени сенсора</h3>
        <p className="mt-2 text-[12px] text-[var(--ink-3)]">
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
      <h3 className="text-[14px] text-[var(--ink)]">Смещение по времени сенсора</h3>
      <p className="mb-2 text-[10px] text-[var(--ink-3)]">
        Оценка по записям из пальца
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
          <text fill="var(--ink-3)" fontSize="6" key={h} textAnchor="middle" x={xForAge(h)} y={viewH - 3}>
            {formatAge(h)}
          </text>
        ))}
        <text fill="var(--ink-3)" fontSize="6" textAnchor="end" x={padL - 3} y={padT + 4}>
          {yHi.toFixed(1)}
        </text>
        <text fill="var(--ink-3)" fontSize="6" textAnchor="end" x={padL - 3} y={padT + chartH}>
          {yLo.toFixed(1)}
        </text>
        <text fill="var(--ink-3)" fontSize="5" textAnchor="end" x={padL - 3} y={padT + chartH / 2 + 2}>
          ммоль/л
        </text>
        {biasLine ? (
          <polyline
            fill="none"
            points={biasLine}
            stroke="var(--ink)"
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
            stroke="var(--ink-3)"
            strokeWidth="0.5"
          >
            <title>
              {`${r.sensor_age_hours.toFixed(1)}ч: Δ${r.residual > 0 ? "+" : ""}${r.residual.toFixed(1)} · ${r.exclusion_reason ?? "исключено"}`}
            </title>
          </circle>
        ))}
      </svg>
      <div className="mt-1 flex gap-4 text-[10px] text-[var(--ink-3)]">
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 rotate-45 bg-[var(--accent)]" />
          из пальца (включено)
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-full border border-[var(--ink-3)]" />
          исключено
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-0 w-3 border-t border-[var(--ink)]" />
          оценка смещения
        </span>
      </div>
    </section>
  );
}
