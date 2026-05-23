import { AlertTriangle, CheckCircle2, Loader2, X } from "lucide-react";
import { useMemo, useState } from "react";
import {
  apiErrorMessage,
  type TwinDataSummaryResponse,
  type TwinFitResponse,
  type TwinParamsPatch,
  type TwinParamsRead,
} from "../../api/client";
import { formatDecimal, formatMmol } from "../../utils/nutritionFormat";
import {
  useFitTwin,
  usePatchTwinParams,
  useResetTwinParams,
  useTwinDataSummary,
} from "./useTwin";

type WizardStep = "range" | "fitting" | "result";

const pad = (value: number) => value.toString().padStart(2, "0");

const toDateTimeInput = (date: Date) =>
  `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(
    date.getHours(),
  )}:${pad(date.getMinutes())}`;

const toApiDateTime = (value: string) =>
  value.length === 16 ? `${value}:00` : value;

const defaultRange = () => {
  const to = new Date();
  const from = new Date(to.getTime() - 30 * 24 * 60 * 60 * 1000);
  return {
    from: toDateTimeInput(from),
    to: toDateTimeInput(to),
  };
};

const blockerLabel = (value: string) => {
  if (value.startsWith("cgm_count<")) return "CGM-точек меньше 200";
  if (value === "days_with_cgm<3") return "CGM есть меньше чем за 3 дня";
  if (value === "meal_count<1") return "Нет записей еды с углеводами";
  if (value === "insulin_count<1") return "Нет записей инсулина";
  return value;
};

export function TwinFitWizard({
  onClose,
  open,
  params,
}: {
  onClose: () => void;
  open: boolean;
  params: TwinParamsRead | undefined;
}) {
  const initialRange = useMemo(() => defaultRange(), []);
  const [fromInput, setFromInput] = useState(initialRange.from);
  const [toInput, setToInput] = useState(initialRange.to);
  const [step, setStep] = useState<WizardStep>("range");
  const [result, setResult] = useState<TwinFitResponse | null>(null);
  const from = toApiDateTime(fromInput);
  const to = toApiDateTime(toInput);
  const summaryQuery = useTwinDataSummary(from, to, open && step === "range");
  const fitTwin = useFitTwin();
  const patchParams = usePatchTwinParams();
  const resetParams = useResetTwinParams();

  if (!open) return null;

  const close = () => {
    setStep("range");
    fitTwin.reset();
    patchParams.reset();
    resetParams.reset();
    onClose();
  };

  const startFit = () => {
    setStep("fitting");
    fitTwin.mutate(
      { data_from: from, data_to: to },
      {
        onError: () => setStep("range"),
        onSuccess: (next) => {
          setResult(next);
          setStep("result");
        },
      },
    );
  };

  const rollback = () => {
    const previous = result?.previous_params;
    if (previous?.is_fitted) {
      patchParams.mutate(previousParamsPatch(previous), { onSuccess: close });
      return;
    }
    resetParams.mutate(undefined, { onSuccess: close });
  };

  return (
    <div className="twin-fit-backdrop" role="presentation">
      <section
        aria-label="Подгонка двойника"
        aria-modal="true"
        className="twin-fit-dialog"
        role="dialog"
      >
        <header className="twin-fit-head">
          <div>
            <div className="lbl">мастер</div>
            <h2>Подгонка двойника</h2>
          </div>
          <button
            className="btn icon"
            onClick={close}
            title="Закрыть"
            type="button"
          >
            <X size={14} />
          </button>
        </header>

        {step === "range" ? (
          <RangeStep
            error={fitTwin.error}
            fromInput={fromInput}
            onFromChange={setFromInput}
            onStart={startFit}
            onToChange={setToInput}
            summary={summaryQuery.data}
            summaryLoading={summaryQuery.isFetching}
            toInput={toInput}
          />
        ) : null}

        {step === "fitting" ? <FittingStep /> : null}

        {step === "result" && result ? (
          <ResultStep
            current={result.params}
            onClose={close}
            onRollback={rollback}
            previous={result.previous_params ?? params}
            result={result}
            rollbackPending={patchParams.isPending || resetParams.isPending}
          />
        ) : null}
      </section>
    </div>
  );
}

function RangeStep({
  error,
  fromInput,
  onFromChange,
  onStart,
  onToChange,
  summary,
  summaryLoading,
  toInput,
}: {
  error: unknown;
  fromInput: string;
  onFromChange: (value: string) => void;
  onStart: () => void;
  onToChange: (value: string) => void;
  summary: TwinDataSummaryResponse | undefined;
  summaryLoading: boolean;
  toInput: string;
}) {
  const ready = Boolean(summary?.ready_for_fit);
  return (
    <div className="twin-fit-body">
      <p className="twin-fit-copy">
        Двойник будет подогнан по историческим CGM-записям, съеденным
        углеводам и введённому инсулину в выбранном окне.
      </p>
      <div className="twin-fit-range">
        <label>
          От
          <input
            className="panel-input"
            onChange={(event) => onFromChange(event.target.value)}
            type="datetime-local"
            value={fromInput}
          />
        </label>
        <label>
          До
          <input
            className="panel-input"
            onChange={(event) => onToChange(event.target.value)}
            type="datetime-local"
            value={toInput}
          />
        </label>
      </div>

      <SummaryBox loading={summaryLoading} summary={summary} />

      {summary && !summary.ready_for_fit ? (
        <div className="twin-fit-blockers">
          <AlertTriangle size={15} />
          <div>
            <b>Недостаточно данных для подгонки:</b>
            <ul>
              {(summary.fit_blockers ?? []).map((blocker) => (
                <li key={blocker}>{blockerLabel(blocker)}</li>
              ))}
            </ul>
          </div>
        </div>
      ) : null}

      {error ? (
        <div className="gt-error">
          {apiErrorMessage(error, "Не удалось запустить подгонку.")}
        </div>
      ) : null}

      <div className="twin-fit-actions">
        <button className="btn primary" disabled={!ready} onClick={onStart} type="button">
          Запустить подгонку
        </button>
      </div>
    </div>
  );
}

function SummaryBox({
  loading,
  summary,
}: {
  loading: boolean;
  summary: TwinDataSummaryResponse | undefined;
}) {
  const items = [
    ["CGM-точек", summary ? String(summary.cgm_count) : "—"],
    ["Измерений из пальца", summary ? String(summary.fingerstick_count) : "—"],
    ["Еда с углеводами", summary ? String(summary.meal_count) : "—"],
    ["Инсулин", summary ? String(summary.insulin_count) : "—"],
  ];
  return (
    <div className="twin-fit-summary">
      <div className="lbl">в выбранном окне</div>
      <div className="twin-fit-summary-grid">
        {items.map(([label, value]) => (
          <div className="twin-fit-summary-item" key={label}>
            <span>{label}</span>
            <b className="mono">{loading ? "…" : value}</b>
          </div>
        ))}
      </div>
    </div>
  );
}

function FittingStep() {
  return (
    <div className="twin-fit-loading">
      <Loader2 size={24} />
      <h3>Подгоняем параметры...</h3>
      <p>Это может занять до минуты.</p>
    </div>
  );
}

function ResultStep({
  current,
  onClose,
  onRollback,
  previous,
  result,
  rollbackPending,
}: {
  current: TwinParamsRead;
  onClose: () => void;
  onRollback: () => void;
  previous: TwinParamsRead | undefined;
  result: TwinFitResponse;
  rollbackPending: boolean;
}) {
  const rows: Array<[string, number | null | undefined, number | null | undefined]> = [
    ["ICR утром", previous?.icr_morning, current.icr_morning],
    ["ICR днём", previous?.icr_day, current.icr_day],
    ["ICR вечером", previous?.icr_evening, current.icr_evening],
    ["ISF", previous?.isf, current.isf],
    ["Базовый дрейф", previous?.baseline_drift_per_hour, current.baseline_drift_per_hour],
  ];
  const quality = fitQuality(result.params.last_fit_holdout_mae_mmol);
  return (
    <div className="twin-fit-body">
      <div className="twin-fit-success">
        <CheckCircle2 size={18} />
        <h3>Подгонка завершена</h3>
      </div>
      <div className={`twin-fit-quality ${quality.kind}`}>{quality.label}</div>
      <div className="twin-fit-result-table">
        <div className="twin-fit-result-head">
          <span>Параметр</span>
          <span>Раньше</span>
          <span>Теперь</span>
          <span>Изменение</span>
        </div>
        {rows.map(([label, before, after]) => (
          <div className="twin-fit-result-row" key={label}>
            <span>{label}</span>
            <b className="mono">{formatParam(before)}</b>
            <b className="mono">{formatParam(after)}</b>
            <b className="mono">{formatDelta(before, after)}</b>
          </div>
        ))}
      </div>
      <p className="twin-fit-copy">
        MAE на отложенных днях:{" "}
        <b className="mono">
          {formatMmol(result.params.last_fit_holdout_mae_mmol)} ммоль/л
        </b>{" "}
        на <b className="mono">{result.params.last_fit_holdout_window_count ?? "—"}</b>{" "}
        окнах.
      </p>
      <div className="twin-fit-note">
        Подгонка использует ваши исторические записи и НЕ является рекомендацией
        по изменению реальных коэффициентов ICR/ISF, которые вы используете для
        дозирования инсулина. Любые такие изменения обсуждайте с врачом.
      </div>
      <div className="twin-fit-actions">
        <button className="btn" disabled={rollbackPending} onClick={onRollback} type="button">
          {previous?.is_fitted ? "Откатить к предыдущим" : "Сбросить"}
        </button>
        <button className="btn primary" onClick={onClose} type="button">
          Готово
        </button>
      </div>
    </div>
  );
}

function previousParamsPatch(params: TwinParamsRead): TwinParamsPatch {
  return {
    baseline_drift_per_hour: params.baseline_drift_per_hour,
    carb_duration_minutes: params.carb_duration_minutes,
    day_start_minutes: params.day_start_minutes,
    dia_minutes: params.dia_minutes,
    evening_start_minutes: params.evening_start_minutes,
    icr_day: params.icr_day,
    icr_evening: params.icr_evening,
    icr_morning: params.icr_morning,
    isf: params.isf,
    morning_start_minutes: params.morning_start_minutes,
  };
}

function formatParam(value: number | null | undefined) {
  if (value === null || value === undefined) return "—";
  return formatDecimal(value, Math.abs(value) < 3 ? 2 : 1);
}

function formatDelta(before: number | null | undefined, after: number | null | undefined) {
  if (before === null || before === undefined || after === null || after === undefined) {
    return "—";
  }
  const delta = after - before;
  const sign = delta > 0 ? "+" : "";
  return `${sign}${formatDecimal(delta, Math.abs(delta) < 3 ? 2 : 1)}`;
}

function fitQuality(value: number | null | undefined) {
  if (value === null || value === undefined) {
    return { kind: "neutral", label: "Качество будет видно после подгонки." };
  }
  if (value < 1.5) {
    return { kind: "good", label: "Высокое качество подгонки." };
  }
  if (value < 2.5) {
    return { kind: "warn", label: "Приемлемое качество подгонки." };
  }
  return {
    kind: "bad",
    label:
      "Низкое качество. Рассмотрите расширение диапазона данных или ручную настройку параметров.",
  };
}
