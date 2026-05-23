import { AlertTriangle, Play, RefreshCw, RotateCcw } from "lucide-react";
import { useMemo, useState } from "react";
import {
  apiErrorMessage,
  type TwinCurveResponse,
  type TwinParamsRead,
} from "../../api/client";
import { formatDecimal, formatMmol } from "../../utils/nutritionFormat";
import { TwinChart } from "./TwinChart";
import { TwinFitWizard } from "./TwinFitWizard";
import { useResetTwinParams, useTwinCurve, useTwinParams } from "./useTwin";

type RangePreset = "6h" | "12h" | "24h";

const rangeButtons: { label: string; value: RangePreset }[] = [
  { label: "6ч", value: "6h" },
  { label: "12ч", value: "12h" },
  { label: "24ч", value: "24h" },
];

const pad = (value: number) => value.toString().padStart(2, "0");

const toDateTimeInput = (date: Date) =>
  `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(
    date.getHours(),
  )}:${pad(date.getMinutes())}`;

const toApiDateTime = (value: string) =>
  value.length === 16 ? `${value}:00` : value;

const presetRange = (preset: RangePreset) => {
  const to = new Date();
  const hours = preset === "6h" ? 6 : preset === "12h" ? 12 : 24;
  const from = new Date(to.getTime() - hours * 60 * 60 * 1000);
  return {
    from: toDateTimeInput(from),
    to: toDateTimeInput(to),
  };
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

const slotTime = (minutes: number) =>
  `${pad(Math.floor(minutes / 60))}:${pad(minutes % 60)}`;

const hintLabel = (hint?: TwinParamsRead["hint"]) => {
  if (hint === "ready") return "готов";
  if (hint === "stale") return "устарела";
  return "не подогнан";
};

const fitQualityLabel = (value?: number | null) => {
  if (value === null || value === undefined) return "—";
  if (value < 1.5) return "высокое";
  if (value < 2.5) return "приемлемое";
  return "низкое";
};

export function TwinPage() {
  const initialRange = useMemo(() => presetRange("6h"), []);
  const [preset, setPreset] = useState<RangePreset>("6h");
  const [fromInput, setFromInput] = useState(initialRange.from);
  const [toInput, setToInput] = useState(initialRange.to);
  const [fitWizardOpen, setFitWizardOpen] = useState(false);
  const from = toApiDateTime(fromInput);
  const to = toApiDateTime(toInput);
  const paramsQuery = useTwinParams();
  const curveQuery = useTwinCurve(from, to, 5);
  const resetParams = useResetTwinParams();

  const curve = curveQuery.data;
  const params = curve?.params ?? paramsQuery.data;
  const error = paramsQuery.error ?? curveQuery.error ?? resetParams.error;
  const isLoading = paramsQuery.isLoading || curveQuery.isLoading;

  const applyPreset = (value: RangePreset) => {
    const next = presetRange(value);
    setPreset(value);
    setFromInput(next.from);
    setToInput(next.to);
  };

  const reset = () => {
    if (
      window.confirm(
        "Сбросить параметры цифрового двойника? История подгонок останется в журнале.",
      )
    ) {
      resetParams.mutate();
    }
  };

  return (
    <div className="gt-page twin-page">
      <header className="gt-page-head twin-page-head">
        <div>
          <div className="gt-kicker">Исследовательский режим</div>
          <h1>Цифровой двойник</h1>
          <p>
            Реконструкция и прогноз по вашим записям. Это не CGM-измерение,
            не медицинская рекомендация и не основание менять дозирование
            инсулина.
          </p>
        </div>
        <div className="twin-toolbar">
          <div className="seg" aria-label="Период графика">
            {rangeButtons.map((button) => (
              <button
                className={preset === button.value ? "on" : ""}
                key={button.value}
                onClick={() => applyPreset(button.value)}
                type="button"
              >
                {button.label}
              </button>
            ))}
          </div>
          <button
            className="btn icon"
            onClick={() => void curveQuery.refetch()}
            title="Обновить"
            type="button"
          >
            <RefreshCw size={13} />
          </button>
          <button
            className="btn"
            onClick={() => setFitWizardOpen(true)}
            type="button"
          >
            <Play size={13} />
            Подогнать
          </button>
        </div>
      </header>

      <TwinDisclaimer />

      {params?.hint === "stale" ? (
        <div className="twin-warning">
          <AlertTriangle size={15} />
          <span>
            Подгонка устарела (&gt; 30 дней). Перенастройка будет доступна в
            мастере подгонки.
          </span>
          <button className="btn" onClick={() => setFitWizardOpen(true)} type="button">
            Перенастроить
          </button>
        </div>
      ) : null}

      {error ? (
        <div className="gt-error">
          {apiErrorMessage(error, "Не удалось загрузить цифровой двойник.")}
        </div>
      ) : null}

      <TwinHeaderCards curve={curve} params={params} loading={isLoading} />

      <div className="twin-layout">
        <main className="twin-main-card card">
          <div className="card-head twin-card-head">
            <div>
              <div className="lbl">кривая</div>
              <h3>Реконструкция и прогноз</h3>
            </div>
            <div className="twin-date-controls">
              <label>
                От
                <input
                  aria-label="Начало периода"
                  className="panel-input"
                  onChange={(event) => setFromInput(event.target.value)}
                  type="datetime-local"
                  value={fromInput}
                />
              </label>
              <label>
                До
                <input
                  aria-label="Конец периода"
                  className="panel-input"
                  onChange={(event) => setToInput(event.target.value)}
                  type="datetime-local"
                  value={toInput}
                />
              </label>
            </div>
          </div>
          {params && !params.is_fitted ? (
            <NotFittedState onStartFit={() => setFitWizardOpen(true)} />
          ) : (
            <TwinChart data={curve} />
          )}
        </main>

        <TwinParamsPanel
          curve={curve}
          onStartFit={() => setFitWizardOpen(true)}
          onReset={reset}
          params={params}
          resetting={resetParams.isPending}
        />
      </div>
      <TwinFitWizard
        onClose={() => setFitWizardOpen(false)}
        open={fitWizardOpen}
        params={params}
      />
    </div>
  );
}

function TwinDisclaimer() {
  return (
    <section className="twin-disclaimer">
      <b>Информационно.</b>
      <span>
        Цифровой двойник помогает изучать личные паттерны глюкозы по записям,
        но не является медицинской рекомендацией, CGM-измерением или основанием
        менять дозирование инсулина.
      </span>
    </section>
  );
}

function TwinHeaderCards({
  curve,
  loading,
  params,
}: {
  curve: TwinCurveResponse | undefined;
  loading: boolean;
  params: TwinParamsRead | undefined;
}) {
  const forecast = curve?.points
    .slice()
    .reverse()
    .find((point) => point.mode === "forecast");
  const cards = [
    {
      label: "состояние",
      value: loading ? "…" : hintLabel(params?.hint),
      unit: "",
      sub: params?.last_fit_method === "manual" ? "ручная настройка" : "модель",
    },
    {
      label: "якорей",
      value: curve ? String(curve.anchors.length) : "—",
      unit: "",
      sub: "измерения из пальца",
    },
    {
      label: "прогноз",
      value: forecast ? formatMmol(forecast.mmol) : "—",
      unit: forecast ? "ммоль/л" : "",
      sub: forecast
        ? `уверенность ${formatDecimal(forecast.confidence * 100, 0)}%`
        : "нет точки",
    },
    {
      label: "holdout MAE",
      value: formatMmol(params?.last_fit_holdout_mae_mmol),
      unit:
        params?.last_fit_holdout_mae_mmol !== null &&
        params?.last_fit_holdout_mae_mmol !== undefined
          ? "ммоль/л"
          : "",
      sub: fitQualityLabel(params?.last_fit_holdout_mae_mmol),
    },
  ];

  return (
    <section className="twin-kpi-grid">
      {cards.map((card) => (
        <div className="gt-kpi-card" key={card.label}>
          <div className="gt-kpi-label">{card.label}</div>
          <div className="gt-kpi-value">
            {card.value}
            {card.unit ? <span className="gt-kpi-unit">{card.unit}</span> : null}
          </div>
          <div className="gt-kpi-sub">{card.sub}</div>
        </div>
      ))}
    </section>
  );
}

function NotFittedState({ onStartFit }: { onStartFit: () => void }) {
  return (
    <div className="twin-not-fitted">
      <h2>Двойник ещё не подогнан.</h2>
      <p>
        Запустите подгонку на исторических CGM-данных, чтобы построить
        персональную исследовательскую модель.
      </p>
      <button
        className="btn"
        onClick={onStartFit}
        type="button"
      >
        Запустить подгонку
      </button>
    </div>
  );
}

function TwinParamsPanel({
  curve,
  onStartFit,
  onReset,
  params,
  resetting,
}: {
  curve: TwinCurveResponse | undefined;
  onStartFit: () => void;
  onReset: () => void;
  params: TwinParamsRead | undefined;
  resetting: boolean;
}) {
  const fitted = Boolean(params?.is_fitted);
  const values = [
    ["ICR утром", params?.icr_morning ? formatDecimal(params.icr_morning, 1) : "—"],
    ["ICR днём", params?.icr_day ? formatDecimal(params.icr_day, 1) : "—"],
    ["ICR вечером", params?.icr_evening ? formatDecimal(params.icr_evening, 1) : "—"],
    ["ISF", params?.isf ? formatDecimal(params.isf, 2) : "—"],
    [
      "Базовый дрейф",
      params ? formatDecimal(params.baseline_drift_per_hour, 2) : "—",
    ],
  ];

  return (
    <aside className="twin-panel card">
      <div className="card-head">
        <div>
          <div className="lbl">параметры</div>
          <h3>Модель</h3>
        </div>
        <span className={fitted ? "tag good" : "tag"}>{hintLabel(params?.hint)}</span>
      </div>
      <div className="twin-panel-body">
        <div className="twin-param-list">
          {values.map(([label, value]) => (
            <div className="twin-param-row" key={label}>
              <span>{label}</span>
              <b className="mono">{value}</b>
            </div>
          ))}
        </div>
        <div className="twin-panel-section">
          <div className="lbl">слоты</div>
          <div className="twin-slot-row">
            <span>Утро</span>
            <b className="mono">{slotTime(params?.morning_start_minutes ?? 360)}</b>
          </div>
          <div className="twin-slot-row">
            <span>День</span>
            <b className="mono">{slotTime(params?.day_start_minutes ?? 660)}</b>
          </div>
          <div className="twin-slot-row">
            <span>Вечер</span>
            <b className="mono">{slotTime(params?.evening_start_minutes ?? 1080)}</b>
          </div>
        </div>
        <div className="twin-panel-section">
          <div className="lbl">окна действия</div>
          <div className="twin-slot-row">
            <span>DIA</span>
            <b className="mono">{params?.dia_minutes ?? 270} мин</b>
          </div>
          <div className="twin-slot-row">
            <span>Углеводы</span>
            <b className="mono">{params?.carb_duration_minutes ?? 180} мин</b>
          </div>
        </div>
        <div className="twin-panel-section">
          <div className="lbl">последняя подгонка</div>
          <div className="twin-slot-row">
            <span>Дата</span>
            <b className="mono">{formatDateTime(params?.last_fit_at)}</b>
          </div>
          <div className="twin-slot-row">
            <span>Окон holdout</span>
            <b className="mono">{params?.last_fit_holdout_window_count ?? "—"}</b>
          </div>
          <div className="twin-slot-row">
            <span>События</span>
            <b className="mono">
              {(curve?.food_events.length ?? 0) + (curve?.insulin_events.length ?? 0)}
            </b>
          </div>
        </div>
        <button
          className="btn"
          disabled={!params}
          onClick={onStartFit}
          type="button"
        >
          <Play size={13} />
          {fitted ? "Перенастроить" : "Запустить подгонку"}
        </button>
        <button
          className="btn"
          disabled={!params || resetting}
          onClick={onReset}
          type="button"
        >
          <RotateCcw size={13} />
          {resetting ? "Сбрасываю..." : "Сбросить параметры"}
        </button>
      </div>
    </aside>
  );
}
