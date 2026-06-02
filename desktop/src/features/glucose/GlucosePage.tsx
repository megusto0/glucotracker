import {
  Activity,
  AlertTriangle,
  Info,
  Plus,
  RefreshCw,
  Save,
  RotateCcw,
  Square,
} from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import {
  startTransition,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";
import {
  apiErrorMessage,
  type GlucoseDashboardResponse,
  type GlucoseMode,
  type KcalBalanceResponse,
  type NightscoutLatestReadingResponse,
  type SensorSessionResponse,
} from "../../api/client";
import { apiClient } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import RightPanel from "../../components/RightPanel";
import {
  useNightscoutSettings,
} from "../nightscout/useNightscout";
import { useApiConfig } from "../settings/settingsStore";
import {
  useCreateFingerstick,
  useGlucoseDashboard,
  useLatestGlucoseReading,
  useRecalculateSensorCalibration,
  useSaveSensor,
  useSensors,
  useUpdateFingerstick,
  useDeleteFingerstick,
} from "./useGlucoseDashboard";
import { useGlucoseSyncTracker, type SyncState } from "./useGlucoseSyncTracker";
import { SyncStatusIndicator } from "./SyncStatusIndicator";
import {
  formatDecimal,
  formatMmol,
  formatSafeInt,
  formatSignedDecimal,
  formatSignedKcal,
} from "../../utils/nutritionFormat";

type RangePreset = "3h" | "6h" | "12h" | "24h";
type DashboardPoint = GlucoseDashboardResponse["points"][number];
type Fingerstick = GlucoseDashboardResponse["fingersticks"][number];
type FoodEvent = GlucoseDashboardResponse["food_events"][number];
type InsulinEvent = GlucoseDashboardResponse["insulin_events"][number];
type Artifact = GlucoseDashboardResponse["artifacts"][number];
type ActivityTab = "episodes" | "events";
type GlucoseClientCache = Pick<
  GlucoseDashboardResponse,
  "artifacts" | "fingersticks" | "food_events" | "insulin_events" | "points"
>;

const TARGET_LOW = 3.9;
const TARGET_HIGH = 9.3;
const VERY_HIGH = 13;
const MAX_CLIENT_CGM_POINTS = 6000;
const CURRENT_WINDOW_TOLERANCE_MS = 6 * 60 * 1000;

type TirStats = {
  below: number;
  high: number;
  target: number;
  veryHigh: number;
};

type FocusMetrics = {
  average: number | null;
  carbs: number;
  cv: number | null;
  insulin: number;
  median: number | null;
  minutesHigh: number;
  minutesLow: number;
  nadir: { timestamp: string; value: number } | null;
  peak: { timestamp: string; value: number } | null;
};

type DaypartBucket = {
  count: number;
  highRisk: boolean;
  label: string;
  max: number | null;
  median: number | null;
  min: number | null;
  q1: number | null;
  q3: number | null;
  tir: number | null;
};

const rangeButtons: { label: string; value: RangePreset }[] = [
  { label: "3ч", value: "3h" },
  { label: "6ч", value: "6h" },
  { label: "12ч", value: "12h" },
  { label: "24ч", value: "24h" },
];

const rangeTitle = (preset: RangePreset) =>
  ({
    "3h": "3 часа",
    "6h": "6 часов",
    "12h": "12 часов",
    "24h": "24 часа",
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
          : 24;
  const from = new Date(to.getTime() - hours * 60 * 60 * 1000);
  return {
    from: toDateTimeInput(from),
    to: toDateTimeInput(to),
  };
};

function bufferedDashboardRange(from: string, to: string) {
  const fromMs = Date.parse(from);
  const toMs = Date.parse(to);
  const durationMs = Math.max(toMs - fromMs, 60 * 60 * 1000);
  if (!Number.isFinite(fromMs) || !Number.isFinite(toMs)) {
    return { from, to };
  }
  const bufferedFrom = fromMs - durationMs * 3;
  const bufferedTo = Math.min(toMs + durationMs, Date.now());
  return {
    from: toLocalDateTimeSecond(new Date(bufferedFrom)),
    to: toLocalDateTimeSecond(new Date(Math.max(bufferedTo, toMs))),
  };
}

const formatNumber = (
  value?: number | null,
  digits = 1,
  fallback = "—",
) => (value === null || value === undefined ? fallback : formatDecimal(value, digits));

const formatSigned = (value?: number | null, digits = 1) => {
  if (value === null || value === undefined) return "—";
  return formatSignedDecimal(value, digits);
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
  excluded_from_analytics: boolean;
  exclusion_reason: string;
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
  excluded_from_analytics: false,
  exclusion_reason: "",
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
  excluded_from_analytics: Boolean(sensor.excluded_from_analytics),
  exclusion_reason: sensor.exclusion_reason ?? "",
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

const sensorDurationDays = (sensor?: SensorSessionResponse | null) => {
  if (!sensor?.started_at) return null;
  const started = Date.parse(sensor.started_at);
  const ended = sensor.ended_at ? Date.parse(sensor.ended_at) : Date.now();
  if (!Number.isFinite(started) || !Number.isFinite(ended) || ended < started) {
    return null;
  }
  return (ended - started) / 86_400_000;
};

const sensorDurationLabel = (sensor?: SensorSessionResponse | null) => {
  const days = sensorDurationDays(sensor);
  if (days === null) return "—";
  const hours = days * 24;
  if (hours < 48) return `${formatNumber(hours, hours < 10 ? 1 : 0)} ч`;
  return `${formatNumber(days, days < 10 ? 1 : 0)} дн`;
};

const isOpenSensor = (sensor?: SensorSessionResponse | null) =>
  Boolean(sensor && !sensor.ended_at);

const isActiveSensor = (sensor?: SensorSessionResponse | null) =>
  isOpenSensor(sensor) && !sensor?.excluded_from_analytics;

const sensorStatusLabel = (sensor?: SensorSessionResponse | null) => {
  if (!sensor) return "нет";
  if (sensor.excluded_from_analytics) return "исключён";
  return isOpenSensor(sensor) ? "актив." : "завершён";
};

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

const nightscoutTrendSymbol = (trend?: string | null) => {
  const normalized = trend?.toLowerCase().replace(/[\s_-]+/g, "");
  switch (normalized) {
    case "doubleup":
      return "↑↑";
    case "singleup":
      return "↑";
    case "fortyfiveup":
      return "↗";
    case "flat":
      return "→";
    case "fortyfivedown":
      return "↘";
    case "singledown":
      return "↓";
    case "doubledown":
      return "↓↓";
    default:
      return null;
  }
};

const foodEventKcal = (event: FoodEvent) => event.kcal ?? 0;

const emptyGlucoseClientCache = (): GlucoseClientCache => ({
  artifacts: [],
  fingersticks: [],
  food_events: [],
  insulin_events: [],
  points: [],
});

function mergeByKey<T>(
  previous: T[],
  incoming: T[],
  keyFor: (item: T) => string,
  sortBy: (left: T, right: T) => number,
) {
  const map = new Map<string, T>();
  previous.forEach((item) => map.set(keyFor(item), item));
  incoming.forEach((item) => map.set(keyFor(item), item));
  return Array.from(map.values()).sort(sortBy);
}

function mergeGlucoseClientCache(
  previous: GlucoseClientCache,
  incoming: GlucoseDashboardResponse,
): GlucoseClientCache {
  const points = mergeByKey(
    previous.points,
    incoming.points,
    (point) => point.timestamp,
    (left, right) => Date.parse(left.timestamp) - Date.parse(right.timestamp),
  );
  const prunedPoints =
    points.length > MAX_CLIENT_CGM_POINTS
      ? points.slice(points.length - MAX_CLIENT_CGM_POINTS)
      : points;
  const oldestPointMs = prunedPoints.length
    ? Date.parse(prunedPoints[0].timestamp)
    : Number.NEGATIVE_INFINITY;

  return {
    artifacts: mergeByKey(
      previous.artifacts,
      incoming.artifacts,
      (artifact) => `${artifact.start_at}-${artifact.end_at}-${artifact.kind}`,
      (left, right) => Date.parse(left.start_at) - Date.parse(right.start_at),
    ).filter((artifact) => Date.parse(artifact.end_at) >= oldestPointMs),
    fingersticks: mergeByKey(
      previous.fingersticks,
      incoming.fingersticks,
      (row) => row.id,
      (left, right) => Date.parse(left.measured_at) - Date.parse(right.measured_at),
    ).filter((row) => Date.parse(row.measured_at) >= oldestPointMs),
    food_events: mergeByKey(
      previous.food_events,
      incoming.food_events,
      (event) => `${event.timestamp}-${event.title}-${event.carbs_g}`,
      (left, right) => Date.parse(left.timestamp) - Date.parse(right.timestamp),
    ).filter((event) => Date.parse(event.timestamp) >= oldestPointMs),
    insulin_events: mergeByKey(
      previous.insulin_events,
      incoming.insulin_events,
      (event) =>
        `${event.timestamp}-${event.event_type ?? ""}-${event.insulin_units ?? ""}-${event.notes ?? ""}`,
      (left, right) => Date.parse(left.timestamp) - Date.parse(right.timestamp),
    ).filter((event) => Date.parse(event.timestamp) >= oldestPointMs),
    points: prunedPoints,
  };
}

function cachedDashboardForRange(
  cache: GlucoseClientCache,
  base: GlucoseDashboardResponse | undefined,
  from: string,
  to: string,
): GlucoseDashboardResponse | undefined {
  if (!base) return undefined;
  const fromMs = Date.parse(from);
  const toMs = Date.parse(to);
  if (!Number.isFinite(fromMs) || !Number.isFinite(toMs)) return undefined;
  const inRange = (iso: string) => {
    const ms = Date.parse(iso);
    return ms >= fromMs && ms <= toMs;
  };
  const overlapsRange = (startIso: string, endIso: string) => {
    const startMs = Date.parse(startIso);
    const endMs = Date.parse(endIso);
    return endMs >= fromMs && startMs <= toMs;
  };

  const points = cache.points.filter((point) => inRange(point.timestamp));
  if (!points.length) return undefined;

  const latest = points[points.length - 1];
  return {
    ...base,
    artifacts: cache.artifacts.filter((artifact) =>
      overlapsRange(artifact.start_at, artifact.end_at),
    ),
    fingersticks: cache.fingersticks.filter((row) => inRange(row.measured_at)),
    food_events: cache.food_events.filter((event) => inRange(event.timestamp)),
    from_datetime: from,
    insulin_events: cache.insulin_events.filter((event) => inRange(event.timestamp)),
    points,
    summary: {
      ...base.summary,
      current_glucose: latest.display_value,
      current_glucose_at: latest.timestamp,
    },
    to_datetime: to,
  };
}

export function GlucosePage() {
  const config = useApiConfig();
  const queryClient = useQueryClient();
  const initialRange = useMemo(() => presetRange("6h"), []);
  const [preset, setPreset] = useState<RangePreset>("6h");
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
  const [editingSensorId, setEditingSensorId] = useState<string | null>(null);
  const [sensorForm, setSensorForm] = useState<SensorForm>(() => emptySensorForm());
  const [kcalBalance, setKcalBalance] = useState<KcalBalanceResponse | null>(null);
  const [glucoseClientCache, setGlucoseClientCache] = useState<GlucoseClientCache>(
    () => emptyGlucoseClientCache(),
  );

  useEffect(() => {
    if (!config.token.trim()) return;
    const today = new Date();
    const day = `${today.getFullYear()}-${pad(today.getMonth() + 1)}-${pad(today.getDate())}`;
    apiClient.getKcalBalance(config, day).then(setKcalBalance).catch(() => setKcalBalance(null));
  }, [config.token, config.baseUrl]);

  const from = toApiDateTime(fromInput);
  const to = toApiDateTime(toInput);
  const daypartRange = useMemo(() => {
    const end = new Date(to);
    const start = new Date(end.getTime() - 7 * 24 * 60 * 60 * 1000);
    return {
      from: toLocalDateTimeSecond(start),
      to: toLocalDateTimeSecond(end),
    };
  }, [to]);
  const dashboardRange = useMemo(
    () => bufferedDashboardRange(from, to),
    [from, to],
  );
  const dashboard = useGlucoseDashboard(dashboardRange.from, dashboardRange.to, mode);
  const daypartDashboard = useGlucoseDashboard(daypartRange.from, daypartRange.to, mode);
  const latestReading = useLatestGlucoseReading();
  const sensors = useSensors();
  const nightscoutSettings = useNightscoutSettings();

  const canImportNightscout = Boolean(
    config.token.trim() &&
      nightscoutSettings.data?.configured &&
      nightscoutSettings.data?.sync_glucose,
  );

  const { syncState, forceRefresh, resetConnection } = useGlucoseSyncTracker(
    mode,
    canImportNightscout,
    Boolean(nightscoutSettings.data?.configured),
  );

  const createFingerstick = useCreateFingerstick();
  const updateFingerstick = useUpdateFingerstick();
  const deleteFingerstick = useDeleteFingerstick();
  const saveSensor = useSaveSensor();
  const recalculate = useRecalculateSensorCalibration();

  useEffect(() => {
    if (!dashboard.data) return;
    setGlucoseClientCache((current) =>
      mergeGlucoseClientCache(current, dashboard.data),
    );
  }, [dashboard.data]);

  useEffect(() => {
    if (!daypartDashboard.data) return;
    setGlucoseClientCache((current) =>
      mergeGlucoseClientCache(current, daypartDashboard.data),
    );
  }, [daypartDashboard.data]);

  const immediateClientCache = useMemo(
    () =>
      dashboard.data
        ? mergeGlucoseClientCache(glucoseClientCache, dashboard.data)
        : glucoseClientCache,
    [dashboard.data, glucoseClientCache],
  );
  const cachedData = useMemo(
    () => cachedDashboardForRange(immediateClientCache, dashboard.data, from, to),
    [dashboard.data, from, immediateClientCache, to],
  );
  const data = cachedData ?? dashboard.data;
  const chartData = useMemo(
    () =>
      cachedDashboardForRange(
        immediateClientCache,
        dashboard.data,
        dashboardRange.from,
        dashboardRange.to,
      ) ?? data,
    [dashboard.data, dashboardRange.from, dashboardRange.to, data, immediateClientCache],
  );
  const nowReading = latestReading.data;
  const selectedToMs = Date.parse(to);
  const isCurrentWindow =
    Number.isFinite(selectedToMs) &&
    Date.now() - selectedToMs <= CURRENT_WINDOW_TOLERANCE_MS;
  const currentSensor = data?.current_sensor ?? null;
  const sensorList = sensors.data ?? data?.sensors ?? [];
  const sensorHistory = useMemo(
    () => sensorList.filter((sensor) => sensor.id !== currentSensor?.id),
    [currentSensor?.id, sensorList],
  );
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
  const chartEpisodes = useMemo(() => buildGroupedEpisodes(chartData), [chartData]);
  const tirStats = useMemo(() => buildTirStats(data, mode), [data, mode]);
  const focusMetrics = useMemo(() => buildFocusMetrics(data, mode), [data, mode]);
  const daypartProfile = useMemo(
    () => buildDaypartProfile(daypartDashboard.data, mode),
    [daypartDashboard.data, mode],
  );
  const recentFingersticks = (data?.fingersticks ?? []).slice(-4).reverse();

  const closeSensorForm = useCallback(() => {
    setShowSensorEdit(false);
  }, []);

  const openExistingSensorForm = useCallback((sensor?: SensorSessionResponse | null) => {
    const selectedSensor = sensor ?? currentSensor ?? null;
    setEditingSensorId(selectedSensor?.id ?? null);
    setSensorForm(selectedSensor ? sensorToForm(selectedSensor) : emptySensorForm());
    setShowSensorEdit(true);
  }, [currentSensor]);

  const openNewSensorForm = useCallback(() => {
    const next = emptySensorForm();
    if (currentSensor) {
      next.expected_life_days = String(currentSensor.expected_life_days ?? 15);
      next.model = currentSensor.model ?? "";
      next.vendor = currentSensor.vendor ?? "";
    }
    setEditingSensorId(null);
    setSensorForm(next);
    setShowSensorEdit(true);
    setShowSensorPanel(true);
  }, [currentSensor]);

  const endCurrentSensor = useCallback(() => {
    if (!currentSensor?.id || !isOpenSensor(currentSensor)) return;
    if (!confirm("Завершить текущий сенсор сейчас?")) return;
    saveSensor.mutate(
      {
        sensorId: currentSensor.id,
        body: {
          ended_at: toApiDateTime(toDateTimeInput(new Date())),
        },
      },
      {
        onSuccess: () => {
          setEditingSensorId(null);
          setShowSensorEdit(false);
        },
      },
    );
  }, [currentSensor, saveSensor]);

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
    if (!showSensorEdit) {
      setSensorForm(currentSensor ? sensorToForm(currentSensor) : emptySensorForm());
      setEditingSensorId(currentSensor?.id ?? null);
      return;
    }
    if (editingSensorId !== currentSensor?.id) return;
    setSensorForm(currentSensor ? sensorToForm(currentSensor) : emptySensorForm());
  }, [currentSensor, currentSensor?.id, currentSensor?.updated_at, editingSensorId, showSensorEdit]);

  const applyPreset = (value: RangePreset) => {
    const next = presetRange(value);
    startTransition(() => {
      setPreset(value);
      setFromInput(next.from);
      setToInput(next.to);
      setHoveredEpisodeId(null);
      setSelectedEpisodeId(null);
    });
  };

  const shiftRange = useCallback((offsetMs: number) => {
    const fromMs = Date.parse(from);
    const toMs = Date.parse(to);
    if (!Number.isFinite(fromMs) || !Number.isFinite(toMs)) return;
    const clampedOffset = Math.min(offsetMs, Date.now() - toMs);
    if (Math.abs(clampedOffset) < 60_000) return;
    setFromInput(toDateTimeInput(new Date(fromMs + clampedOffset)));
    setToInput(toDateTimeInput(new Date(toMs + clampedOffset)));
    setHoveredEpisodeId(null);
    setSelectedEpisodeId(null);
  }, [from, to]);

  useEffect(() => {
    if (!config.token.trim()) return;
    const fromMs = Date.parse(from);
    const toMs = Date.parse(to);
    const durationMs = toMs - fromMs;
    if (
      !Number.isFinite(fromMs) ||
      !Number.isFinite(toMs) ||
      !Number.isFinite(durationMs) ||
      durationMs <= 0
    ) {
      return;
    }

    const adjacentRanges = [
      { fromMs: fromMs - durationMs, toMs: fromMs },
      { fromMs: toMs, toMs: Math.min(toMs + durationMs, Date.now()) },
    ].filter((range) => range.toMs - range.fromMs >= 60_000);

    adjacentRanges.forEach((range) => {
      const visibleFrom = toLocalDateTimeSecond(new Date(range.fromMs));
      const visibleTo = toLocalDateTimeSecond(new Date(range.toMs));
      const adjacent = bufferedDashboardRange(visibleFrom, visibleTo);
      void queryClient.prefetchQuery({
        queryKey: queryKeys.glucoseDashboard(adjacent.from, adjacent.to, mode),
        queryFn: () =>
          apiClient.getGlucoseDashboard(config, adjacent.from, adjacent.to, mode),
        gcTime: 30 * 60 * 1000,
        staleTime: 5 * 60 * 1000,
      });
    });
  }, [config, from, mode, queryClient, to]);

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
        sensorId: editingSensorId ?? undefined,
        body: {
          ended_at: sensorForm.ended_at ? toApiDateTime(sensorForm.ended_at) : null,
          excluded_from_analytics: sensorForm.excluded_from_analytics,
          exclusion_reason: blankToNull(sensorForm.exclusion_reason),
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
        onSuccess: () => {
          setEditingSensorId(null);
          closeSensorForm();
        },
      },
    );
  };


  return (
    <div className="gt-glucose-layout">
      <div className="gt-glucose-main">
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

          <HeroCard
            correction={correction}
            latestPoint={latestPoint}
            latestReading={nowReading}
            previousPoint={previousPoint}
            quality={quality}
            sensor={currentSensor}
            tir={tirStats}
            onEditSensor={() => openExistingSensorForm()}
            onEndSensor={endCurrentSensor}
            onNewSensor={openNewSensorForm}
            onOpenSensorPanel={() => setShowSensorPanel(true)}
          />

          <GlucoseStatusStrip
            canImportNightscout={canImportNightscout}
            correction={quality?.correction_now_mmol_l ?? correction}
            data={data}
            kcalBalance={kcalBalance}
            syncState={syncState}
          />

          <div className="glucose-dashboard-grid">
            <div className="glucose-dashboard-primary">
          <section className="card glucose-chart-card">
            <div className="card-head">
              <div>
                <div className="lbl">график глюкозы</div>
                <h3>Окно {rangeTitle(preset)}</h3>
              </div>
              <div className="col gap-8" style={{ alignItems: "flex-end", flex: 1 }}>
                <div className="row gap-12" style={{ alignItems: "center", justifyContent: "flex-end", flexWrap: "wrap" }}>
                  {!isCurrentWindow ? (
                    <button className="btn" onClick={() => applyPreset(preset)} type="button">
                      <RefreshCw size={13} /> К текущему
                    </button>
                  ) : null}
                  <div className="seg">
                    {rangeButtons.map((item) => (
                      <button key={item.value} className={preset === item.value ? "on" : ""} onClick={() => applyPreset(item.value)} type="button">{item.label}</button>
                    ))}
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
            <div style={{ padding: "10px 12px 0" }}>
              <GlucoseChart
                data={chartData}
                episodes={chartEpisodes}
                hoveredEpisodeId={hoveredEpisodeId}
                loading={dashboard.isLoading}
                mode={mode}
                onEpisodeHover={setHoveredEpisodeId}
                onEpisodeSelect={setSelectedEpisodeId}
                onRangeShift={shiftRange}
                preset={preset}
                selectedEpisodeId={selectedEpisodeId}
                viewFrom={from}
                viewTo={to}
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

              <div className="glucose-secondary-grid">
          <section className="card">
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
              <DaypartProfileCard buckets={daypartProfile} />
              </div>
            </div>

            <FocusPanel
              episodes={episodes}
              metrics={focusMetrics}
              preset={preset}
            />
          </div>
        </div>
      </div>

      {showSensorPanel && (
        <RightPanel className="gt-rightpanel-inline" onClose={() => setShowSensorPanel(false)}>
          <SensorPanel
            currentSensor={currentSensor}
            quality={quality}
            data={data}
            trust={trust}
            validCalibrationPoints={validCalibrationPoints}
            recentFingersticks={recentFingersticks}
            sensorList={sensorHistory}
            openNewFingerstickForm={openNewFingerstickForm}
            openExistingSensorForm={openExistingSensorForm}
            openNewSensorForm={openNewSensorForm}
            onEndSensor={endCurrentSensor}
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
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.2)", zIndex: 100, display: "flex", alignItems: "center", justifyContent: "center" }} onClick={closeSensorForm}>
          <form className="card" style={{ padding: 24, width: 420, maxHeight: "90vh", overflow: "auto" }} onClick={(e) => e.stopPropagation()} onSubmit={submitSensor}>
            <h3 style={{ fontFamily: "var(--serif)", fontSize: 18, fontWeight: 500, margin: "0 0 16px" }}>{editingSensorId ? "Параметры сенсора" : "Новый сенсор"}</h3>
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
              <label className="field"><span>срок, дней</span><input inputMode="decimal" value={sensorForm.expected_life_days} onChange={(e) => setSensorForm(s => ({ ...s, expected_life_days: e.target.value }))} /></label>
              <label className="check-row" style={{ alignItems: "center", gap: 8, fontSize: 12, color: "var(--ink-2)" }}>
                <input type="checkbox" checked={sensorForm.excluded_from_analytics} onChange={(e) => setSensorForm(s => ({ ...s, excluded_from_analytics: e.target.checked, exclusion_reason: e.target.checked ? s.exclusion_reason || "corrupt" : s.exclusion_reason }))} />
                <span>исключить данные сенсора из аналитики</span>
              </label>
              {sensorForm.excluded_from_analytics ? (
                <label className="field"><span>причина исключения</span><input value={sensorForm.exclusion_reason} onChange={(e) => setSensorForm(s => ({ ...s, exclusion_reason: e.target.value }))} /></label>
              ) : null}
              <label className="field"><span>заметки</span><textarea value={sensorForm.notes} onChange={(e) => setSensorForm(s => ({ ...s, notes: e.target.value }))} rows={3} /></label>
              <div className="row gap-8">
                <button className="btn dark" type="submit" disabled={saveSensor.isPending || !sensorForm.started_at}><Save size={14} />{editingSensorId ? "Сохранить сенсор" : "Начать сенсор"}</button>
                {editingSensorId && !sensorForm.ended_at ? (
                  <button className="btn" type="button" onClick={() => setSensorForm(s => ({ ...s, ended_at: toDateTimeInput(new Date()) }))}><Square size={13} /> Завершить сейчас</button>
                ) : null}
                <button className="btn" type="button" onClick={closeSensorForm}>Отмена</button>
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
  latestReading,
  onEditSensor,
  onEndSensor,
  onNewSensor,
  onOpenSensorPanel,
  previousPoint,
  quality,
  sensor,
  tir,
}: {
  correction: number | null;
  latestPoint: DashboardPoint | null;
  latestReading?: NightscoutLatestReadingResponse;
  onEditSensor: () => void;
  onEndSensor: () => void;
  onNewSensor: () => void;
  onOpenSensorPanel: () => void;
  previousPoint: DashboardPoint | null;
  quality?: GlucoseDashboardResponse["quality"];
  sensor: SensorSessionResponse | null;
  tir: TirStats;
}) {
  const hasNowReading =
    latestReading?.value_mmol_l !== null &&
    latestReading?.value_mmol_l !== undefined;
  const current = hasNowReading
    ? latestReading.value_mmol_l
    : latestPoint?.display_value;
  const correctionEstimate = quality?.correction_now_mmol_l ?? correction;
  const delta =
    !hasNowReading && latestPoint && previousPoint
      ? latestPoint.display_value - previousPoint.display_value
      : 0;
  const trend =
    (hasNowReading ? nightscoutTrendSymbol(latestReading?.trend) : null) ??
    (delta > 0.2 ? "↑" : delta < -0.2 ? "↓" : "→");
  const nowTimestamp = hasNowReading ? latestReading?.timestamp : latestPoint?.timestamp;
  const trendContext =
    !hasNowReading && delta !== 0 ? `${trend} ${formatSigned(correctionEstimate ?? delta)}` : trend;
  const sensorLifePercent = clamp(
    ((quality?.sensor_age_days ?? 0) / Math.max(sensor?.expected_life_days ?? 15, 1)) * 100,
    0,
    100,
  );

  return (
      <div className="card glucose-hero-strip">
        <div className="glucose-hero-now">
          <div className="lbl">сейчас</div>
          <div className="glucose-hero-value">
            <span className="g-now">{formatNumber(current)}</span>
            <span className="glucose-unit">ммоль/л</span>
          </div>
          <div className="glucose-hero-context">
            <span className="tag">{trendContext}</span>
            <span className="mono">{nowTimestamp ? formatTime(nowTimestamp) : "—"}</span>
          </div>
        </div>

        <div className="glucose-hero-tir">
          <div className="lbl">время в диапазоне · окно</div>
          <div className="glucose-tir-main mono">{tir.target}%</div>
          <div className="glucose-tir-bar" aria-label="Время в диапазоне">
            <i style={{ width: `${tir.below}%`, background: "var(--warn)" }} />
            <i style={{ width: `${tir.target}%`, background: "var(--good)" }} />
            <i style={{ width: `${tir.high}%`, background: "var(--accent)" }} />
            <i style={{ width: `${tir.veryHigh}%`, background: "var(--ink)" }} />
          </div>
          <div className="glucose-tir-legend">
            <span>&lt;{TARGET_LOW} <b className="mono">{tir.below}%</b></span>
            <span>{TARGET_LOW}-{TARGET_HIGH} <b className="mono">{tir.target}%</b></span>
            <span>&gt;{TARGET_HIGH} <b className="mono">{tir.high + tir.veryHigh}%</b></span>
          </div>
        </div>

        <div className="glucose-hero-sensor">
          <div className="row" style={{ justifyContent: "space-between", alignItems: "baseline", gap: 10 }}>
            <span className="lbl">сенсор {sensorName(sensor)}</span>
            <span className={`tag ${isActiveSensor(sensor) ? "good" : ""}`}>{sensorStatusLabel(sensor)}</span>
          </div>
          <div className="row gap-6" style={{ alignItems: "baseline", marginTop: 6 }}>
            <span className="mono" style={{ fontSize: 26, fontWeight: 500 }}>{formatNumber(quality?.sensor_age_days)}</span>
            <span style={{ fontSize: 12, color: "var(--ink-3)" }}>/ {formatNumber(sensor?.expected_life_days, 0)} дн</span>
          </div>
          <div className="pbar" style={{ marginTop: 8 }}>
            <i style={{ width: `${sensorLifePercent}%` }} />
          </div>
          <div className="row" style={{ marginTop: 6, fontSize: 11, color: "var(--ink-3)", justifyContent: "space-between" }}>
            <span>{sensorPhaseCompact(quality?.sensor_phase, quality?.sensor_age_days)}</span>
            <span className="mono">стаб. {quality?.quality_score ?? 0}/100</span>
          </div>
          <div className="row gap-6" style={{ marginTop: 10, flexWrap: "wrap" }}>
            <button className="btn" onClick={onOpenSensorPanel} type="button">подробно</button>
            <button className="btn" onClick={onNewSensor} type="button"><Plus size={13} /> новый</button>
            {sensor ? (
              <button className="btn" onClick={onEditSensor} type="button">править</button>
            ) : null}
            {isOpenSensor(sensor) ? (
              <button className="btn" onClick={onEndSensor} type="button"><Square size={12} /> завершить</button>
            ) : null}
          </div>
        </div>
      </div>
    );
}

function GlucoseStatusStrip({
  canImportNightscout,
  correction,
  data,
  kcalBalance,
  syncState,
}: {
  canImportNightscout: boolean;
  correction: number | null;
  data?: GlucoseDashboardResponse;
  kcalBalance: KcalBalanceResponse | null;
  syncState: SyncState;
}) {
  const nextText = syncState.nextScheduledAt
    ? formatShortCountdown(syncState.nextScheduledAt)
    : "—";
  const status = canImportNightscout
    ? syncState.phase === "offline"
      ? "нет связи"
      : syncState.phase === "importing"
        ? "обновляется"
        : "подключён"
    : "не настроен";

  return (
    <div className="glucose-status-strip">
      {canImportNightscout ? <SyncStatusIndicator compact syncState={syncState} /> : (
        <span className="mono">Nightscout · не настроен</span>
      )}
      <span>Nightscout · {status}</span>
      <span>смещение <b className="mono">{formatSigned(correction)} ммоль/л</b></span>
      <span>обновление <b className="mono">{nextText}</b></span>
      <span>точек <b className="mono">{data?.points.length ?? 0}</b></span>
      {kcalBalance?.bmr_available && kcalBalance.net_balance != null ? (
        <span>баланс <b className="mono">{formatSignedKcal(kcalBalance.net_balance)}</b></span>
      ) : null}
    </div>
  );
}

function FocusPanel({
  episodes,
  metrics,
  preset,
}: {
  episodes: GroupedEpisode[];
  metrics: FocusMetrics;
  preset: RangePreset;
}) {
  const topEpisode = episodes
    .filter((episode) => episode.areaAboveTarget !== null)
    .sort((left, right) => (right.areaAboveTarget ?? 0) - (left.areaAboveTarget ?? 0))[0];

  return (
    <aside className="card glucose-focus-panel">
      <div className="card-head">
        <div>
          <div className="lbl">окно {rangeTitle(preset)}</div>
          <h3>Сейчас в фокусе</h3>
        </div>
      </div>
      <div className="glucose-focus-grid">
        <FocusMetric label="медиана" value={`${formatNumber(metrics.median)} ммоль/л`} />
        <FocusMetric label="среднее" value={`${formatNumber(metrics.average)} ммоль/л`} />
        <FocusMetric label="CV" value={metrics.cv === null ? "—" : `${formatNumber(metrics.cv, 0)}%`} />
        <FocusMetric
          label="пик"
          value={metrics.peak ? `${formatNumber(metrics.peak.value)} · ${formatTime(metrics.peak.timestamp)}` : "—"}
        />
        <FocusMetric
          label="надир"
          value={metrics.nadir ? `${formatNumber(metrics.nadir.value)} · ${formatTime(metrics.nadir.timestamp)}` : "—"}
        />
        <FocusMetric label={`мин >${TARGET_HIGH}`} value={`${formatNumber(metrics.minutesHigh, 0)} мин`} />
        <FocusMetric label={`мин <${TARGET_LOW}`} value={`${formatNumber(metrics.minutesLow, 0)} мин`} />
        <FocusMetric label="углеводы" value={`${formatNumber(metrics.carbs, 0)} г`} />
        <FocusMetric label="инсулин" value={`${formatNumber(metrics.insulin, 1)} ЕД`} />
      </div>
      <div className="glucose-focus-episode">
        <div className="lbl">эпизод с максимумом над диапазоном</div>
        {topEpisode ? (
          <div>
            <div className="mono">{formatEpisodeRange(topEpisode.startAt, topEpisode.endAt)} · {formatNumber(topEpisode.areaAboveTarget, 1)} ммоль·ч</div>
            <div>{topEpisode.title}</div>
          </div>
        ) : (
          <div className="mono">—</div>
        )}
      </div>
    </aside>
  );
}

function FocusMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="glucose-focus-metric">
      <span>{label}</span>
      <b className="mono">{value}</b>
    </div>
  );
}

function DaypartProfileCard({ buckets }: { buckets: DaypartBucket[] }) {
  const values = buckets.flatMap((bucket) =>
    [bucket.min, bucket.max].filter((value): value is number => value !== null),
  );
  const minValue = values.length
    ? Math.min(3, Math.floor(Math.min(...values, TARGET_LOW)))
    : 3;
  const maxValue = values.length
    ? Math.max(11, Math.ceil(Math.max(...values, TARGET_HIGH)))
    : 11;
  const span = Math.max(maxValue - minValue, 1);
  const chartLeft = 54;
  const chartTop = 24;
  const chartWidth = 386;
  const chartHeight = 110;
  const bandTop = chartTop + (1 - (TARGET_HIGH - minValue) / span) * chartHeight;
  const bandBottom = chartTop + (1 - (TARGET_LOW - minValue) / span) * chartHeight;
  const bucketWidth = chartWidth / buckets.length;
  const boxWidth = Math.min(56, bucketWidth - 12);
  const yFor = (value: number) =>
    chartTop + (1 - clamp((value - minValue) / span, 0, 1)) * chartHeight;

  return (
    <section className="card daypart-card">
      <div className="card-head">
        <div>
          <div className="lbl">профиль по времени суток</div>
          <h3>7 дней</h3>
        </div>
      </div>
      <div className="daypart-profile-chart">
        <svg
          aria-label="Профиль глюкозы по времени суток за 7 дней"
          preserveAspectRatio="xMidYMid meet"
          role="img"
          viewBox="0 0 460 190"
        >
          <rect
            fill="var(--good-soft)"
            height={Math.max(1, bandBottom - bandTop)}
            opacity="0.42"
            width={chartWidth}
            x={chartLeft}
            y={bandTop}
          />
          {[maxValue, TARGET_HIGH, TARGET_LOW, minValue].map((tick) => (
            <g key={tick}>
              <line
                stroke={tick === TARGET_LOW || tick === TARGET_HIGH ? "var(--good)" : "var(--hairline)"}
                strokeDasharray={tick === TARGET_LOW || tick === TARGET_HIGH ? "3 3" : undefined}
                strokeOpacity={tick === TARGET_LOW || tick === TARGET_HIGH ? 0.45 : 1}
                x1={chartLeft}
                x2={chartLeft + chartWidth}
                y1={yFor(tick)}
                y2={yFor(tick)}
              />
              <text
                fill="var(--ink-4)"
                fontFamily="var(--mono)"
                fontSize="10"
                textAnchor="end"
                x={chartLeft - 10}
                y={yFor(tick) + 3}
              >
                {formatNumber(tick, Number.isInteger(tick) ? 0 : 1)}
              </text>
            </g>
          ))}
          {buckets.map((bucket, index) => {
            const cx = chartLeft + bucketWidth * index + bucketWidth / 2;
            const hasValues = bucket.median !== null;
            const medianY = bucket.median !== null ? yFor(bucket.median) : null;
            const q1Y = bucket.q1 !== null ? yFor(bucket.q1) : null;
            const q3Y = bucket.q3 !== null ? yFor(bucket.q3) : null;
            const minY = bucket.min !== null ? yFor(bucket.min) : null;
            const maxY = bucket.max !== null ? yFor(bucket.max) : null;
            const iqrY = q3Y !== null && q1Y !== null ? Math.min(q3Y, q1Y) : null;
            const iqrHeight =
              q3Y !== null && q1Y !== null
                ? Math.max(Math.abs(q1Y - q3Y), 5)
                : 0;
            const tone = bucket.highRisk ? "var(--warn)" : "var(--good)";
            const softTone = bucket.highRisk ? "var(--warn-soft)" : "var(--good-soft)";
            return (
              <g key={bucket.label}>
                <title>
                  {hasValues
                    ? `${bucket.label}: медиана ${formatNumber(bucket.median)} ммоль/л, TIR ${formatNumber(bucket.tir, 0)}%, точек ${bucket.count}`
                    : `${bucket.label}: нет данных`}
                </title>
                {minY !== null && maxY !== null ? (
                  <line
                    stroke="var(--ink-4)"
                    strokeOpacity="0.55"
                    x1={cx}
                    x2={cx}
                    y1={maxY}
                    y2={minY}
                  />
                ) : null}
                {iqrY !== null ? (
                  <rect
                    fill={softTone}
                    height={iqrHeight}
                    stroke={tone}
                    strokeOpacity="0.24"
                    width={boxWidth}
                    x={cx - boxWidth / 2}
                    y={iqrY}
                  />
                ) : null}
                {medianY !== null ? (
                  <line
                    stroke={tone}
                    strokeWidth="2"
                    x1={cx - boxWidth / 2}
                    x2={cx + boxWidth / 2}
                    y1={medianY}
                    y2={medianY}
                  />
                ) : null}
                {!hasValues ? (
                  <text
                    fill="var(--ink-4)"
                    fontFamily="var(--mono)"
                    fontSize="12"
                    textAnchor="middle"
                    x={cx}
                    y={chartTop + chartHeight / 2 + 4}
                  >
                    —
                  </text>
                ) : null}
                <text
                  fill="var(--ink-4)"
                  fontFamily="var(--mono)"
                  fontSize="9.5"
                  textAnchor="middle"
                  x={cx}
                  y="158"
                >
                  {bucket.label}
                </text>
                <text
                  fill={bucket.highRisk ? "var(--warn)" : "var(--ink)"}
                  fontFamily="var(--mono)"
                  fontSize="11"
                  fontWeight="500"
                  textAnchor="middle"
                  x={cx}
                  y="176"
                >
                  {bucket.median === null ? "—" : formatNumber(bucket.median)}
                </text>
              </g>
            );
          })}
        </svg>
        <div className="daypart-profile-note">
          <span>медиана и межквартиль</span>
          <span>красным — TIR &lt; 50%</span>
        </div>
      </div>
    </section>
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
  openExistingSensorForm,
  openNewSensorForm,
  onEndSensor,
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
  openExistingSensorForm: (sensor?: SensorSessionResponse | null) => void;
  openNewSensorForm: () => void;
  onEndSensor: () => void;
  recalculate: ReturnType<typeof useRecalculateSensorCalibration>;
  recalculatePending: boolean;
  editFingerstick: (row: Fingerstick) => void;
}) {
  return (
    <>
      <div className="lbl">текущий сенсор</div>
      <div className="row" style={{ alignItems: "baseline", justifyContent: "space-between", marginTop: 4 }}>
        <h2 style={{ margin: 0, fontFamily: "var(--serif)", fontSize: 24, fontWeight: 500 }}>{sensorName(currentSensor)}</h2>
        <span className={`tag ${isActiveSensor(currentSensor) ? "good" : ""}`}>{sensorStatusLabel(currentSensor)}</span>
      </div>
      <div style={{ fontSize: 11, color: "var(--ink-3)", marginTop: 4 }}>
        <span className="mono">{currentSensor?.model || "—"}</span> · носится <span className="mono">{sensorDurationLabel(currentSensor)}</span> из <span className="mono">{formatNumber(currentSensor?.expected_life_days, 0)}</span> дн
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
        <button className="btn" onClick={openNewSensorForm}><Plus size={13} /> Новый сенсор</button>
        {currentSensor ? (
          <button className="btn" onClick={() => openExistingSensorForm()}><Activity size={13} /> Редактировать</button>
        ) : null}
        {isOpenSensor(currentSensor) ? (
          <button className="btn" onClick={onEndSensor}><Square size={13} /> Завершить сейчас</button>
        ) : null}
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
                <span className="tag">Δ {formatSigned(delta)}</span>
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
                  <div className="mono" style={{ fontSize: 10, color: "var(--ink-4)", marginTop: 2 }}>{formatDateTime(s.started_at)}–{formatDateTime(s.ended_at)} · {sensorDurationLabel(s)} из {formatNumber(s.expected_life_days, 0)} дн</div>
                </div>
                {s.excluded_from_analytics ? <span className="tag">исключён</span> : null}
                <button className="btn" type="button" onClick={() => openExistingSensorForm(s)} style={{ height: 26, padding: "0 8px", fontSize: 10 }}>Править</button>
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
  areaAboveTarget: number | null;
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
  if (episodes || rows) {
    return (
      <section className="card glucose-episodes-card">
        <div className="card-head">
          <div>
            <div className="lbl">эпизоды</div>
            <h3>Отклик еды на CGM</h3>
          </div>
          <div className="seg">
            {[
              { label: "Эпизоды", value: "episodes" as const },
              { label: "События", value: "events" as const },
            ].map((item) => (
              <button
                className={activeTab === item.value ? "on" : ""}
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
          <div className="episode-response-table">
            <div className="episode-response-head">
              <span>время</span>
              <span>эпизод</span>
              <span>старт → пик</span>
              <span>над диапазоном</span>
              <span>контекст</span>
            </div>
            {episodes.length ? (
              episodes.map((episode) => {
                const selected = selectedEpisodeId === episode.id;
                const hovered = hoveredEpisodeId === episode.id;
                return (
                  <button
                    className={selected || hovered ? "episode-response-row active" : "episode-response-row"}
                    key={episode.id}
                    onClick={() => onEpisodeSelect(episode.id)}
                    onMouseEnter={() => onEpisodeHover(episode.id)}
                    onMouseLeave={() => onEpisodeHover(null)}
                    type="button"
                  >
                    <span className="mono">{formatEpisodeRange(episode.startAt, episode.endAt)}</span>
                    <span>{episode.title}</span>
                    <span className="mono">
                      {episode.cgmStart !== null && episode.cgmMax !== null
                        ? `${formatNumber(episode.cgmStart)} → ${formatNumber(episode.cgmMax)}${episode.timeToMax !== null ? ` · +${episode.timeToMax} мин` : ""}`
                        : "—"}
                    </span>
                    <span className="mono">
                      {episode.areaAboveTarget === null ? "—" : `${formatNumber(episode.areaAboveTarget, 1)} ммоль·ч`}
                    </span>
                    <span className="mono">
                      {formatNumber(episode.carbsTotal, 0)} г · {formatNumber(episode.insulinTotal, 1)} ЕД
                    </span>
                  </button>
                );
              })
            ) : (
              <div className="episode-response-empty">Эпизодов за выбранный период нет.</div>
            )}
          </div>
        ) : (
          <EventsTable rows={rows} />
        )}
      </section>
    );
  }

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
      areaAboveTarget: cgm.areaAboveTarget,
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
      areaAboveTarget: null,
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
  const areaAboveTarget = glucoseAreaAboveTarget(pointsInWindow, valueFor);
  const minutesFromStart = (point: DashboardPoint) =>
    Math.max(0, Math.round((Date.parse(point.timestamp) - foodStartMs) / 60000));
  return {
    areaAboveTarget,
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

function pointDisplayValues(data: GlucoseDashboardResponse | undefined, mode: GlucoseMode) {
  return (data?.points ?? [])
    .map((point) => ({
      timestamp: point.timestamp,
      value: glucosePointValue(point, mode),
    }))
    .filter(
      (point): point is { timestamp: string; value: number } =>
        point.value !== null && point.value !== undefined,
    );
}

function buildTirStats(data: GlucoseDashboardResponse | undefined, mode: GlucoseMode): TirStats {
  const values = pointDisplayValues(data, mode).map((point) => point.value);
  if (!values.length) {
    return { below: 0, high: 0, target: 0, veryHigh: 0 };
  }
  const counts = values.reduce(
    (acc, value) => {
      if (value < TARGET_LOW) acc.below += 1;
      else if (value <= TARGET_HIGH) acc.target += 1;
      else if (value < VERY_HIGH) acc.high += 1;
      else acc.veryHigh += 1;
      return acc;
    },
    { below: 0, high: 0, target: 0, veryHigh: 0 },
  );
  const toPercent = (count: number) => Math.round((count / values.length) * 100);
  const below = toPercent(counts.below);
  const target = toPercent(counts.target);
  const veryHigh = toPercent(counts.veryHigh);
  const high = Math.max(0, 100 - below - target - veryHigh);
  return { below, high, target, veryHigh };
}

function buildFocusMetrics(data: GlucoseDashboardResponse | undefined, mode: GlucoseMode): FocusMetrics {
  const points = pointDisplayValues(data, mode);
  const values = points.map((point) => point.value).sort((left, right) => left - right);
  const average = values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
  const median = percentile(values, 0.5);
  const sd =
    average !== null && values.length
      ? Math.sqrt(values.reduce((sum, value) => sum + Math.pow(value - average, 2), 0) / values.length)
      : null;
  const peak = points.length
    ? points.reduce((best, point) => (point.value > best.value ? point : best), points[0])
    : null;
  const nadir = points.length
    ? points.reduce((best, point) => (point.value < best.value ? point : best), points[0])
    : null;
  const { highMs, lowMs } = glucoseTimeOutsideRange(points);

  return {
    average,
    carbs: data?.food_events.reduce((sum, event) => sum + event.carbs_g, 0) ?? 0,
    cv: average && sd !== null ? (sd / average) * 100 : null,
    insulin: data?.insulin_events.reduce((sum, event) => sum + (event.insulin_units ?? 0), 0) ?? 0,
    median,
    minutesHigh: Math.round(highMs / 60000),
    minutesLow: Math.round(lowMs / 60000),
    nadir,
    peak,
  };
}

function buildDaypartProfile(data: GlucoseDashboardResponse | undefined, mode: GlucoseMode): DaypartBucket[] {
  const buckets = [
    { from: 0, label: "00-04", to: 4 },
    { from: 4, label: "04-08", to: 8 },
    { from: 8, label: "08-12", to: 12 },
    { from: 12, label: "12-16", to: 16 },
    { from: 16, label: "16-20", to: 20 },
    { from: 20, label: "20-24", to: 24 },
  ];
  const points = pointDisplayValues(data, mode);
  return buckets.map((bucket) => {
    const values = points
      .filter((point) => {
        const hour = new Date(point.timestamp).getHours();
        return hour >= bucket.from && hour < bucket.to;
      })
      .map((point) => point.value)
      .sort((left, right) => left - right);
    const tir =
      values.length > 0
        ? (values.filter((value) => value >= TARGET_LOW && value <= TARGET_HIGH).length / values.length) * 100
        : null;
    return {
      count: values.length,
      highRisk: tir !== null && tir < 50,
      label: bucket.label,
      max: values.length ? values[values.length - 1] : null,
      median: percentile(values, 0.5),
      min: values.length ? values[0] : null,
      q1: percentile(values, 0.25),
      q3: percentile(values, 0.75),
      tir,
    };
  });
}

function percentile(values: number[], ratio: number) {
  if (!values.length) return null;
  const index = clamp((values.length - 1) * ratio, 0, values.length - 1);
  const lower = Math.floor(index);
  const upper = Math.ceil(index);
  if (lower === upper) return values[lower];
  return values[lower] + (values[upper] - values[lower]) * (index - lower);
}

function glucoseTimeOutsideRange(points: { timestamp: string; value: number }[]) {
  let highMs = 0;
  let lowMs = 0;
  for (let index = 1; index < points.length; index += 1) {
    const previous = points[index - 1];
    const current = points[index];
    const dt = Math.max(0, Date.parse(current.timestamp) - Date.parse(previous.timestamp));
    const value = (previous.value + current.value) / 2;
    if (value > TARGET_HIGH) highMs += dt;
    if (value < TARGET_LOW) lowMs += dt;
  }
  return { highMs, lowMs };
}

function glucoseAreaAboveTarget(
  points: DashboardPoint[],
  valueFor: (point: DashboardPoint) => number,
) {
  let area = 0;
  for (let index = 1; index < points.length; index += 1) {
    const previous = points[index - 1];
    const current = points[index];
    const dtHours = Math.max(0, Date.parse(current.timestamp) - Date.parse(previous.timestamp)) / 3600000;
    const previousExcess = Math.max(0, valueFor(previous) - TARGET_HIGH);
    const currentExcess = Math.max(0, valueFor(current) - TARGET_HIGH);
    area += ((previousExcess + currentExcess) / 2) * dtHours;
  }
  return area;
}

function formatShortCountdown(date: Date) {
  const diff = date.getTime() - Date.now();
  if (diff <= 0) return "сейчас";
  if (diff < 60_000) return `через ${Math.ceil(diff / 1000)}с`;
  return `через ${Math.ceil(diff / 60_000)}м`;
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
  onRangeShift,
  preset,
  selectedEpisodeId,
  viewFrom,
  viewTo,
}: {
  data?: GlucoseDashboardResponse;
  episodes: GroupedEpisode[];
  hoveredEpisodeId: string | null;
  loading: boolean;
  mode: GlucoseMode;
  onEpisodeHover: (episodeId: string | null) => void;
  onEpisodeSelect: (episodeId: string) => void;
  onRangeShift: (offsetMs: number) => void;
  preset: RangePreset;
  selectedEpisodeId: string | null;
  viewFrom: string;
  viewTo: string;
}) {
  const [hoveredDayIndex, setHoveredDayIndex] = useState<number | null>(null);
  const [rangeOffsetMs, setRangeOffsetMs] = useState(0);
  const [isDraggingRange, setIsDraggingRange] = useState(false);
  const dragRef = useRef<{
    pointerId: number;
    startX: number;
  } | null>(null);
  const dragFrameRef = useRef<number | null>(null);
  const pendingDragOffsetRef = useRef(0);
  const suppressChartClickRef = useRef(false);
  const points = data?.points ?? [];
  const width = 1180;
  const left = 64;
  const right = 20;
  const chartTop = 24;
  const chartHeight = 264;
  const chartBottom = chartTop + chartHeight;
  const axisLabelY = chartBottom + 20;
  const laneHeight = 24;
  const laneGap = 8;
  const lane1Y = chartBottom + 42;
  const lane2Y = lane1Y + laneHeight + laneGap;
  const lane3Y = lane2Y + laneHeight + laneGap;
  const eventLaneY = lane1Y + laneHeight / 2;
  const lanesBottom = lane3Y + laneHeight;
  const height = lane3Y + laneHeight + 38;
  const chartWidth = width - left - right;
  const committedFromMs = Date.parse(viewFrom);
  const committedToMs = Date.parse(viewTo);
  const duration = Math.max(committedToMs - committedFromMs, 1);
  const clampedRangeOffsetMs = Math.min(rangeOffsetMs, Date.now() - committedToMs);
  const fromMs = committedFromMs + clampedRangeOffsetMs;
  const toMs = committedToMs + clampedRangeOffsetMs;
  const density = chartDensityForRange(preset, duration);
  const chartValues = [
    ...points
      .filter((point) => {
        const pointMs = Date.parse(point.timestamp);
        return pointMs >= fromMs && pointMs <= toMs;
      })
      .flatMap((point) => [
        point.raw_value,
        point.smoothed_value,
        point.normalized_value,
        point.display_value,
      ]),
    ...(data?.fingersticks
      .filter((row) => {
        const pointMs = Date.parse(row.measured_at);
        return pointMs >= fromMs && pointMs <= toMs;
      })
      .map((row) => row.glucose_mmol_l) ?? []),
  ].filter((value): value is number => typeof value === "number");
  const { max: maxValue, min: minValue } = glucoseChartDomain(chartValues);
  const yRange = Math.max(maxValue - minValue, 1);
  const scaleXMs = (ms: number) =>
    left + ((ms - fromMs) / duration) * chartWidth;
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
  const constrainRangeOffset = useCallback(
    (offsetMs: number) => Math.min(offsetMs, Date.now() - committedToMs),
    [committedToMs],
  );
  const msFromPixelDelta = useCallback(
    (deltaPx: number) => -(deltaPx / Math.max(chartWidth, 1)) * duration,
    [chartWidth, duration],
  );
  const commitRangeOffset = useCallback(
    (offsetMs: number) => {
      const nextOffset = constrainRangeOffset(offsetMs);
      setRangeOffsetMs(0);
      if (Math.abs(nextOffset) >= 60_000) {
        onRangeShift(nextOffset);
      }
    },
    [constrainRangeOffset, onRangeShift],
  );
  const cancelDragPreviewFrame = useCallback(() => {
    if (dragFrameRef.current !== null) {
      window.cancelAnimationFrame(dragFrameRef.current);
      dragFrameRef.current = null;
    }
  }, []);
  const scheduleDragPreview = useCallback((offsetMs: number) => {
    pendingDragOffsetRef.current = offsetMs;
    if (dragFrameRef.current !== null) return;
    dragFrameRef.current = window.requestAnimationFrame(() => {
      dragFrameRef.current = null;
      setRangeOffsetMs(pendingDragOffsetRef.current);
    });
  }, []);

  useEffect(() => {
    cancelDragPreviewFrame();
    setRangeOffsetMs(0);
    pendingDragOffsetRef.current = 0;
  }, [cancelDragPreviewFrame, preset, viewFrom, viewTo]);

  useEffect(() => () => {
    cancelDragPreviewFrame();
  }, [cancelDragPreviewFrame]);

  const handlePointerDown = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (event.button !== 0) return;
    dragRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
    };
    setIsDraggingRange(true);
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const handlePointerMove = (event: ReactPointerEvent<SVGSVGElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    if (Math.abs(event.clientX - drag.startX) > 4) {
      suppressChartClickRef.current = true;
    }
    const nextOffset = constrainRangeOffset(msFromPixelDelta(event.clientX - drag.startX));
    scheduleDragPreview(nextOffset);
  };

  const handlePointerUp = (event: ReactPointerEvent<SVGSVGElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    const nextOffset = constrainRangeOffset(msFromPixelDelta(event.clientX - drag.startX));
    cancelDragPreviewFrame();
    dragRef.current = null;
    setIsDraggingRange(false);
    event.currentTarget.releasePointerCapture(event.pointerId);
    commitRangeOffset(nextOffset);
    window.setTimeout(() => {
      suppressChartClickRef.current = false;
    }, 80);
  };

  const handlePointerCancel = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (dragRef.current?.pointerId === event.pointerId) {
      cancelDragPreviewFrame();
      dragRef.current = null;
      setIsDraggingRange(false);
      setRangeOffsetMs(0);
      pendingDragOffsetRef.current = 0;
      suppressChartClickRef.current = false;
    }
  };

  const selectEpisodeFromChart = (episodeId: string) => {
    if (suppressChartClickRef.current) return;
    onEpisodeSelect(episodeId);
  };

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
  const visiblePointValues = points
    .filter((point) => {
      const pointMs = Date.parse(point.timestamp);
      return pointMs >= fromMs && pointMs <= toMs;
    })
    .map((point) => ({ point, value: glucosePointValue(point, mode) }))
    .filter((item): item is { point: DashboardPoint; value: number } => item.value !== null && item.value !== undefined);
  const latestChartPoint = visiblePointValues[visiblePointValues.length - 1] ?? null;
  const peakChartPoint = visiblePointValues.length
    ? visiblePointValues.reduce((best, item) => (item.value > best.value ? item : best), visiblePointValues[0])
    : null;
  const chartClipId = "glucose-chart-window";

  return (
    <div
      className={`glucose-chart-scroll-shell${isDraggingRange ? " dragging" : ""}`}
    >
      <svg
        aria-label="График глюкозы"
        className="min-w-[940px] text-[var(--ink-3)]"
        onPointerCancel={handlePointerCancel}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        preserveAspectRatio="xMidYMid meet"
        role="img"
        style={{
          display: "block",
          fontFamily: "var(--sans)",
          width: "100%",
        }}
        viewBox={`0 0 ${width} ${height}`}
      >
        <defs>
          <clipPath id={chartClipId}>
            <rect
              height={lanesBottom - chartTop + 18}
              width={chartWidth}
              x={left}
              y={chartTop - 8}
            />
          </clipPath>
        </defs>
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

        <g clipPath={`url(#${chartClipId})`}>
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
        </g>

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
          <g clipPath={`url(#${chartClipId})`}>
            <EpisodeChartHighlight
              chartBottom={chartBottom}
              chartHeight={chartHeight}
              chartTop={chartTop}
              episode={activeEpisode}
              laneY={eventLaneY}
              scaleX={scaleX}
              scaleY={scaleY}
            />
          </g>
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
              {formatMmol(tick)}
            </text>
          </g>
        ))}

        <g clipPath={`url(#${chartClipId})`}>
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

        {peakChartPoint && peakChartPoint !== latestChartPoint ? (
          <g>
            <line
              stroke="var(--accent)"
              strokeDasharray="2 3"
              strokeWidth="1"
              x1={scaleX(peakChartPoint.point.timestamp)}
              x2={scaleX(peakChartPoint.point.timestamp)}
              y1={scaleY(peakChartPoint.value)}
              y2={eventLaneY}
            />
            <circle
              cx={scaleX(peakChartPoint.point.timestamp)}
              cy={scaleY(peakChartPoint.value)}
              fill="var(--surface)"
              r="4"
              stroke="var(--accent)"
              strokeWidth="1.5"
            />
            <text
              fill="var(--accent)"
              fontFamily="var(--mono)"
              fontSize="10"
              fontWeight="500"
              x={Math.min(scaleX(peakChartPoint.point.timestamp) + 8, width - right - 64)}
              y={scaleY(peakChartPoint.value) - 6}
            >
              {formatNumber(peakChartPoint.value)} · пик
            </text>
          </g>
        ) : null}

        {latestChartPoint ? (
          <g>
            <circle
              cx={scaleX(latestChartPoint.point.timestamp)}
              cy={scaleY(latestChartPoint.value)}
              fill="var(--ink)"
              r="4"
              stroke="var(--surface)"
              strokeWidth="2"
            />
            <rect
              fill="var(--ink)"
              height="20"
              rx="2"
              width="42"
              x={Math.min(scaleX(latestChartPoint.point.timestamp) + 8, width - right - 44)}
              y={scaleY(latestChartPoint.value) - 10}
            />
            <text
              fill="var(--ink-fg)"
              fontFamily="var(--mono)"
              fontSize="10"
              fontWeight="500"
              textAnchor="middle"
              x={Math.min(scaleX(latestChartPoint.point.timestamp) + 29, width - right - 23)}
              y={scaleY(latestChartPoint.value) + 4}
            >
              {formatNumber(latestChartPoint.value)}
            </text>
          </g>
        ) : null}

        {points.map((point, i) => {
          const mainVal = glucosePointValue(point, mode);
          if (mainVal == null) return null;
          const tooltipText = [
            formatTime(point.timestamp),
            `Raw: ${formatMmol(point.raw_value)}`,
            point.normalized_value != null
              ? `Нормализованная: ${formatMmol(point.normalized_value)}`
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
          { label: "еда", y: lane1Y },
          { label: "инсулин", y: lane2Y },
          { label: "из пальца", y: lane3Y },
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
                  {day.insulin > 0 ? formatDecimal(day.insulin, 1) : "—"}
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
                  onClick={() => selectEpisodeFromChart(episode.id)}
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
                  onClick={() => selectEpisodeFromChart(episode.id)}
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
                  {pillWidth >= 42 ? (
                    <text
                      fill={active ? "var(--surface)" : "var(--ink-2)"}
                      fontFamily="var(--mono)"
                      fontSize="10"
                      fontWeight="500"
                      textAnchor="middle"
                      x={pillX + pillWidth / 2}
                      y={lane1Y + laneHeight / 2 + 4}
                    >
                      {formatNumber(episode.carbsTotal, 1)} г
                    </text>
                  ) : null}
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

        </g>

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
              y={axisLabelY}
            >
              {axisLabelForTime(tick, density, duration)}
            </text>
          );
        })}

        <g transform={`translate(${width - 448},${height - 10})`}>
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
          {formatNumber(episode.cgmMax)}{episode.timeToMax !== null ? ` · +${episode.timeToMax} мин` : ""}
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
  preset: RangePreset,
  durationMs: number,
): ChartDensity {
  if (durationMs >= 6 * 24 * 60 * 60 * 1000) {
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
              {formatMmol(tick)}
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
          const rawPart = `Raw: ${formatMmol(point.raw_value)}`;
          const normPart =
            point.normalized_value != null
              ? `Нормализованная: ${formatMmol(point.normalized_value)}`
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
              ? `Ближайшее: ${formatSafeInt(point.nearest_fingerstick_distance_min)} мин`
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
    return `${formatDecimal(h / 24, 1)}д`;
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
          {formatMmol(yHi)}
        </text>
        <text fill="var(--ink-3)" fontSize="6" textAnchor="end" x={padL - 3} y={padT + chartH}>
          {formatMmol(yLo)}
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
              {`${formatDecimal(r.sensor_age_hours, 1)}ч: Δ${formatSignedDecimal(r.residual, 1)} ммоль/л · из пальца ${formatMmol(r.fingerstick_value)} / raw ${formatMmol(r.raw_cgm_value)}`}
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
              {`${formatDecimal(r.sensor_age_hours, 1)}ч: Δ${formatSignedDecimal(r.residual, 1)} · ${r.exclusion_reason ?? "исключено"}`}
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
