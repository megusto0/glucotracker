from __future__ import annotations

import argparse
import copy
import json
import random
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
import torch
from matplotlib import pyplot as plt
from torch import nn

from run_experiment import (
    ExperimentConfig,
    Metrics,
    calculate_metrics,
    find_export_root,
    generate_synthetic_timeline,
    read_export_csv,
    train_model,
)

matplotlib.use("Agg")

EPISODE_FEATURE_NAMES = (
    "glucose_minus_30",
    "total_carbs",
    "total_insulin",
    "duration",
    "has_insulin",
    "hour_sin",
    "hour_cos",
)
METHOD_LABELS_RU = {
    "persistence": "Последнее значение",
    "scratch": "Обучение с нуля",
    "pretrained": "До адаптации",
    "fine_tuned": "После дообучения",
}


@dataclass(frozen=True)
class EpisodeConfig:
    seed: int = 42
    personal_timezone: str = "Europe/Samara"
    train_fraction: float = 0.60
    validation_fraction: float = 0.20
    hidden_size: int = 24
    batch_size: int = 32
    pretrain_epochs: int = 120
    scratch_epochs: int = 180
    fine_tune_epochs: int = 100
    repetitions: int = 12
    synthetic_days_per_patient: int = 3
    synthetic_patients: tuple[str, ...] = (
        "adult#001",
        "adult#003",
        "adult#005",
        "adult#007",
        "adult#009",
        "adolescent#002",
    )


@dataclass(frozen=True)
class MetricSummary:
    mae_mean: float
    mae_std: float
    rmse_mean: float
    rmse_std: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fine-tune a SimGlucose-pretrained episode model using meal_insulin_episode_snapshots.",
    )
    parser.add_argument("--export-zip", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("results"))
    parser.add_argument("--report-path", type=Path, default=Path("EPISODE_REPORT.md"))
    parser.add_argument("--quick", action="store_true")
    return parser.parse_args()


def load_personal_episodes(export_zip: Path, timezone: str) -> pd.DataFrame:
    with zipfile.ZipFile(export_zip) as archive:
        root = find_export_root(archive)
        snapshots = read_export_csv(archive, root, "meal_insulin_episode_snapshots.csv")

    snapshots["start_at"] = pd.to_datetime(snapshots["start_at"], errors="coerce", format="mixed")
    snapshots["end_at"] = pd.to_datetime(snapshots["end_at"], errors="coerce", format="mixed")
    numeric_columns = (
        "total_carbs_g",
        "total_insulin_units",
        "glucose_minus_30_mmol_l",
        "glucose_plus_2h_mmol_l",
    )
    for column in numeric_columns:
        snapshots[column] = pd.to_numeric(snapshots[column], errors="coerce")

    usable = snapshots[
        snapshots["start_at"].notna()
        & snapshots["end_at"].notna()
        & snapshots["glucose_minus_30_mmol_l"].notna()
        & snapshots["glucose_plus_2h_mmol_l"].notna()
        & snapshots["glucose_minus_30_source"].astype(str).str.lower().eq("actual")
        & snapshots["glucose_plus_2h_source"].astype(str).str.lower().eq("actual")
        & snapshots["total_carbs_g"].gt(0.0)
    ].copy()
    usable["duration_minutes"] = (
        usable["end_at"] - usable["start_at"]
    ).dt.total_seconds().div(60.0).clip(lower=0.0, upper=180.0)
    usable["local_hour"] = usable["start_at"].dt.hour + usable["start_at"].dt.minute / 60.0
    usable["has_insulin"] = usable["total_insulin_units"].gt(0.0).astype(float)
    usable["source"] = "personal"
    usable["timezone"] = timezone
    return usable.sort_values("start_at").reset_index(drop=True)


def synthetic_episodes_from_timeline(timeline: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, float | str | pd.Timestamp]] = []
    for series_id, group in timeline.groupby("series_id", sort=False):
        group = group.sort_index()
        meal_positions = np.flatnonzero(group["carbs_g"].to_numpy(dtype=float) > 0.5)
        if len(meal_positions) == 0:
            continue
        clusters: list[list[int]] = [[int(meal_positions[0])]]
        for position in meal_positions[1:]:
            position = int(position)
            if position - clusters[-1][-1] <= 3:
                clusters[-1].append(position)
            else:
                clusters.append([position])

        for cluster in clusters:
            start_position = cluster[0]
            end_position = cluster[-1]
            minus_30_position = start_position - 6
            plus_2h_position = start_position + 24
            if minus_30_position < 0 or plus_2h_position >= len(group):
                continue
            glucose_minus_30 = float(group["glucose_mmol_l"].iloc[minus_30_position])
            glucose_plus_2h = float(group["glucose_mmol_l"].iloc[plus_2h_position])
            if not np.isfinite([glucose_minus_30, glucose_plus_2h]).all():
                continue
            insulin_start = max(0, start_position - 3)
            insulin_end = min(len(group), end_position + 4)
            total_insulin = float(group["insulin_units"].iloc[insulin_start:insulin_end].sum())
            start_at = group.index[start_position]
            rows.append(
                {
                    "start_at": start_at,
                    "end_at": group.index[end_position],
                    "total_carbs_g": float(group["carbs_g"].iloc[cluster].sum()),
                    "total_insulin_units": total_insulin,
                    "glucose_minus_30_mmol_l": glucose_minus_30,
                    "glucose_plus_2h_mmol_l": glucose_plus_2h,
                    "duration_minutes": float((end_position - start_position + 1) * 5),
                    "local_hour": start_at.hour + start_at.minute / 60.0,
                    "has_insulin": float(total_insulin > 0.0),
                    "source": str(series_id),
                },
            )
    return pd.DataFrame(rows).sort_values(["source", "start_at"]).reset_index(drop=True)


def episode_arrays(frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    hour = frame["local_hour"].to_numpy(dtype=np.float32)
    baseline = frame["glucose_minus_30_mmol_l"].to_numpy(dtype=np.float32)
    features = np.column_stack(
        (
            baseline / 10.0,
            frame["total_carbs_g"].to_numpy(dtype=np.float32) / 100.0,
            frame["total_insulin_units"].to_numpy(dtype=np.float32) / 15.0,
            frame["duration_minutes"].to_numpy(dtype=np.float32) / 60.0,
            frame["has_insulin"].to_numpy(dtype=np.float32),
            np.sin(2.0 * np.pi * hour / 24.0),
            np.cos(2.0 * np.pi * hour / 24.0),
        ),
    ).astype(np.float32)
    target = (
        frame["glucose_plus_2h_mmol_l"].to_numpy(dtype=np.float32) - baseline
    ) / 3.0
    valid = np.isfinite(features).all(axis=1) & np.isfinite(target) & np.isfinite(baseline)
    return features[valid], target[valid].astype(np.float32), baseline[valid]


def split_personal_episodes(
    x: np.ndarray,
    y: np.ndarray,
    baseline: np.ndarray,
    config: EpisodeConfig,
) -> dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]]:
    train_end = max(1, int(len(x) * config.train_fraction))
    validation_end = max(
        train_end + 1,
        int(len(x) * (config.train_fraction + config.validation_fraction)),
    )
    return {
        "train": (x[:train_end], y[:train_end], baseline[:train_end]),
        "validation": (
            x[train_end:validation_end],
            y[train_end:validation_end],
            baseline[train_end:validation_end],
        ),
        "test": (x[validation_end:], y[validation_end:], baseline[validation_end:]),
    }


class EpisodeMLP(nn.Module):
    def __init__(self, input_size: int, hidden_size: int) -> None:
        super().__init__()
        self.network = nn.Sequential(
            nn.Linear(input_size, hidden_size),
            nn.LayerNorm(hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, 1),
        )

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        return self.network(inputs).squeeze(-1)


def predict_episode(model: nn.Module, x: np.ndarray, baseline: np.ndarray) -> np.ndarray:
    model.eval()
    with torch.no_grad():
        delta = model(torch.from_numpy(x)).numpy()
    return baseline + delta * 3.0


def run_repetitions(
    synthetic: tuple[np.ndarray, np.ndarray],
    splits: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]],
    config: EpisodeConfig,
) -> tuple[
    dict[str, MetricSummary],
    dict[str, np.ndarray],
    dict[str, list[dict[str, list[float]]]],
]:
    synthetic_x, synthetic_y = synthetic
    synthetic_split = max(1, int(len(synthetic_x) * 0.85))
    train_x, train_y, _ = splits["train"]
    validation_x, validation_y, _ = splits["validation"]
    test_x, test_y, test_baseline = splits["test"]
    actual = test_baseline + test_y * 3.0

    metrics_by_method: dict[str, list[Metrics]] = {
        "persistence": [calculate_metrics(actual, test_baseline)],
        "scratch": [],
        "pretrained": [],
        "fine_tuned": [],
    }
    predictions: dict[str, list[np.ndarray]] = {
        "persistence": [test_baseline.copy()],
        "scratch": [],
        "pretrained": [],
        "fine_tuned": [],
    }
    curves: dict[str, list[dict[str, list[float]]]] = {
        "pretraining": [],
        "scratch": [],
        "fine_tuning": [],
    }

    for repetition in range(config.repetitions):
        run_seed = config.seed + repetition
        random.seed(run_seed)
        np.random.seed(run_seed)
        torch.manual_seed(run_seed)

        pretrained = EpisodeMLP(len(EPISODE_FEATURE_NAMES), config.hidden_size)
        pretrained, pretrain_curve = train_model(
            pretrained,
            (synthetic_x[:synthetic_split], synthetic_y[:synthetic_split]),
            (synthetic_x[synthetic_split:], synthetic_y[synthetic_split:]),
            config.pretrain_epochs,
            config.batch_size,
            learning_rate=1e-3,
        )
        scratch = EpisodeMLP(len(EPISODE_FEATURE_NAMES), config.hidden_size)
        scratch, scratch_curve = train_model(
            scratch,
            (train_x, train_y),
            (validation_x, validation_y),
            config.scratch_epochs,
            min(config.batch_size, 16),
            learning_rate=1e-3,
        )
        fine_tuned = copy.deepcopy(pretrained)
        fine_tuned, fine_tune_curve = train_model(
            fine_tuned,
            (train_x, train_y),
            (validation_x, validation_y),
            config.fine_tune_epochs,
            min(config.batch_size, 16),
            learning_rate=3e-4,
        )

        model_map = {
            "scratch": scratch,
            "pretrained": pretrained,
            "fine_tuned": fine_tuned,
        }
        for name, model in model_map.items():
            predicted = predict_episode(model, test_x, test_baseline)
            metrics_by_method[name].append(calculate_metrics(actual, predicted))
            predictions[name].append(predicted)
        curves["pretraining"].append(pretrain_curve)
        curves["scratch"].append(scratch_curve)
        curves["fine_tuning"].append(fine_tune_curve)

    summaries: dict[str, MetricSummary] = {}
    ensemble_predictions: dict[str, np.ndarray] = {}
    for name, values in metrics_by_method.items():
        maes = np.asarray([value.mae_mmol_l for value in values])
        rmses = np.asarray([value.rmse_mmol_l for value in values])
        summaries[name] = MetricSummary(
            mae_mean=float(maes.mean()),
            mae_std=float(maes.std(ddof=0)),
            rmse_mean=float(rmses.mean()),
            rmse_std=float(rmses.std(ddof=0)),
        )
        ensemble_predictions[name] = np.mean(predictions[name], axis=0)
    ensemble_predictions["actual"] = actual
    return summaries, ensemble_predictions, curves


def plot_episode_comparison(
    summaries: dict[str, MetricSummary],
    output_path: Path,
) -> None:
    methods = list(summaries)
    labels = [METHOD_LABELS_RU[name] for name in methods]
    mae = [summaries[name].mae_mean for name in methods]
    mae_std = [summaries[name].mae_std for name in methods]
    rmse = [summaries[name].rmse_mean for name in methods]
    rmse_std = [summaries[name].rmse_std for name in methods]
    positions = np.arange(len(methods))
    width = 0.36
    fig, axis = plt.subplots(figsize=(11, 6))
    axis.bar(
        positions - width / 2,
        mae,
        width,
        yerr=mae_std,
        capsize=4,
        label="MAE",
        color="#5e6f3a",
    )
    axis.bar(
        positions + width / 2,
        rmse,
        width,
        yerr=rmse_std,
        capsize=4,
        label="RMSE",
        color="#c98a55",
    )
    axis.set_ylabel("Ошибка, ммоль/л")
    axis.set_title("Прогноз глюкозы через 2 часа после приёма пищи")
    axis.set_xticks(positions, labels)
    axis.legend(title="Метрика")
    axis.grid(axis="y", alpha=0.25)
    axis.text(
        0.01,
        -0.16,
        "Усики показывают разброс между повторными обучениями с разными random seeds.",
        transform=axis.transAxes,
        fontsize=9,
    )
    fig.tight_layout()
    fig.savefig(output_path, dpi=170)
    plt.close(fig)


def plot_episode_predictions(
    predictions: dict[str, np.ndarray],
    output_path: Path,
) -> None:
    positions = np.arange(1, len(predictions["actual"]) + 1)
    fig, axis = plt.subplots(figsize=(11, 6))
    axis.plot(
        positions,
        predictions["actual"],
        marker="o",
        linewidth=2.5,
        label="Фактическая глюкоза +2ч",
        color="#25241f",
    )
    axis.plot(
        positions,
        predictions["scratch"],
        marker="s",
        linestyle="--",
        label="Обучение с нуля",
        color="#6b7a92",
    )
    axis.plot(
        positions,
        predictions["fine_tuned"],
        marker="^",
        linestyle="--",
        label="После дообучения",
        color="#5e6f3a",
    )
    axis.set_xlabel("Эпизод в хронологическом тестовом наборе")
    axis.set_ylabel("Глюкоза, ммоль/л")
    axis.set_title("Фактические и прогнозируемые значения на тестовых эпизодах")
    axis.set_xticks(positions)
    axis.grid(alpha=0.25)
    axis.legend()
    fig.tight_layout()
    fig.savefig(output_path, dpi=170)
    plt.close(fig)


def render_episode_report(
    output_path: Path,
    config: EpisodeConfig,
    personal_count: int,
    synthetic_count: int,
    split_counts: dict[str, int],
    summaries: dict[str, MetricSummary],
) -> None:
    rows = "\n".join(
        "| {label} | {mae:.3f} ± {mae_std:.3f} | {rmse:.3f} ± {rmse_std:.3f} |".format(
            label=METHOD_LABELS_RU[name],
            mae=value.mae_mean,
            mae_std=value.mae_std,
            rmse=value.rmse_mean,
            rmse_std=value.rmse_std,
        )
        for name, value in summaries.items()
    )
    scratch = summaries["scratch"]
    fine_tuned = summaries["fine_tuned"]
    mae_change = 100.0 * (scratch.mae_mean - fine_tuned.mae_mean) / scratch.mae_mean
    report = f"""# Эксперимент с meal_insulin_episode_snapshots

## 1. Идея эксперимента

Второй эксперимент использует готовые эпизоды «еда + связанный инсулин» из
таблицы `meal_insulin_episode_snapshots`. Для каждого эпизода известны суммарные
углеводы, фактически зарегистрированный инсулин, глюкоза за 30 минут до начала
и глюкоза через 2 часа.

Задача модели — спрогнозировать `glucose_plus_2h_mmol_l`. Поле `+2h`
используется **только как target**. Его значение, timestamp и любые производные
не попадают во вход модели, иначе возникла бы утечка будущего.

## 2. Отбор данных

Из 74 snapshot-строк оставлены только эпизоды, где:

1. `total_carbs_g > 0`, то есть присутствует приём пищи;
2. есть фактическая точка `glucose_minus_30_mmol_l`;
3. есть фактическая точка `glucose_plus_2h_mmol_l`;
4. обе точки имеют источник `actual`.

После фильтрации осталось **{personal_count} персональных эпизодов**. Они
отсортированы по времени и разделены без перемешивания:

- train: {split_counts["train"]};
- validation: {split_counts["validation"]};
- test: {split_counts["test"]}.

Тестовые эпизоды являются самыми поздними по времени. Такой split сложнее
случайного, но ближе к реальному сценарию прогноза будущих дней.

## 3. Признаки и целевая переменная

Входной вектор содержит семь признаков:

1. глюкоза за 30 минут до начала;
2. суммарные углеводы эпизода;
3. фактически зарегистрированный связанный инсулин;
4. продолжительность эпизода;
5. бинарный признак наличия инсулина;
6. синус времени суток;
7. косинус времени суток.

Категория еды, название блюда, фотографии, UUID и поле `snapshot_json` не
используются. Модель предсказывает изменение глюкозы относительно `−30m`, что
стабильнее прямой регрессии абсолютного значения.

## 4. Предварительное обучение

SimGlucose сгенерировал временные ряды для
{len(config.synthetic_patients)} виртуальных пациентов по
{config.synthetic_days_per_patient} суток. Из синтетических рядов выделено
**{synthetic_count} эпизодов еды**. Для них тем же способом рассчитаны:

- глюкоза `−30m`;
- углеводы;
- зарегистрированный симулятором инсулин;
- глюкоза `+2h`.

Одинаковая схема признаков позволяет сначала обучить общую MLP на
синтетической популяции, а затем адаптировать её веса к персональным эпизодам.

## 5. Модель и варианты сравнения

Использована MLP: два скрытых слоя, LayerNorm, ReLU и регрессионный выход.
Сравниваются четыре варианта:

- **Последнее значение** — прогноз `+2h` равен глюкозе `−30m`;
- **Обучение с нуля** — случайная инициализация, только personal train;
- **До адаптации** — SimGlucose-модель без персонального fine-tuning;
- **После fine-tuning** — SimGlucose-модель, дообученная на personal train.

Из-за малого набора обучение повторено {config.repetitions} раз с разными
random seeds. В таблице показаны среднее и стандартное отклонение ошибки.

## 6. Результаты

| Метод | MAE, ммоль/л | RMSE, ммоль/л |
|---|---:|---:|
{rows}

Изменение среднего MAE fine-tuned модели относительно scratch:
**{mae_change:+.1f}%**. Отрицательное значение означало бы ухудшение,
положительное — уменьшение ошибки.

График `episode_comparison_ru.png` показывает средние ошибки и разброс между
повторными обучениями. График `episode_predictions_ru.png` показывает
фактические и прогнозируемые значения для каждого позднего test-эпизода.

## 7. Интерпретация

Этот эксперимент проверяет более узкую задачу, чем прогноз непрерывного CGM:
реакцию на конкретный пищевой эпизод. Snapshot-таблица полезна тем, что уже
содержит детерминированную агрегацию еды и связанного с ней инсулина, поэтому
модели не нужно самостоятельно решать задачу сопоставления событий.

При этом {personal_count} эпизодов недостаточно для клинических выводов.
Несколько необычных приёмов пищи могут заметно изменить итоговые метрики.
Результат следует трактовать как демонстрацию transfer learning на ограниченных
данных, а не как валидированную модель физиологии.

## 8. Ограничения

1. Связи еды и инсулина частично построены автоматическими правилами.
2. Суммарные углеводы могут содержать ошибки оценки.
3. В выборке один пользователь и короткий диапазон дат.
4. SimGlucose и реальные данные имеют различающееся распределение.
5. Наличие инсулина используется как наблюдаемый исторический факт, но модель
   не рассчитывает и не рекомендует дозировку.
6. Прогноз не предназначен для лечения или принятия медицинских решений.
"""
    report += f"""

## 9. Математическая постановка

Для эпизода `i` модель получает вектор `x_i` из семи признаков и предсказывает
не абсолютную глюкозу, а нормированное изменение:

`y_i = (G_i(+2ч) - G_i(-30м)) / 3`.

Обратное преобразование прогноза:

`G_hat_i(+2ч) = G_i(-30м) + 3 * model(x_i)`.

Деление признаков на фиксированные масштабы (`10 ммоль/л`, `100 г`,
`15 ЕД`, `60 минут`) удерживает входы примерно в одном численном диапазоне.
Время суток закодировано парой `sin/cos`, поэтому 23:55 и 00:05 остаются
близкими, в отличие от обычного числового часа.

## 10. Процедура обучения

1. MLP предварительно обучается {config.pretrain_epochs} эпох на 85% эпизодов
   SimGlucose; оставшиеся 15% используются как synthetic validation.
2. Независимая MLP со случайными весами обучается {config.scratch_epochs} эпох
   только на ранних персональных эпизодах.
3. Копия предварительно обученной сети дообучается {config.fine_tune_epochs}
   эпох на тех же персональных train-эпизодах с меньшим learning rate.
4. Выбор лучшего состояния сети выполняется по validation loss. Test-эпизоды
   не участвуют ни в выборе эпохи, ни в настройке параметров.
5. Шаги повторяются {config.repetitions} раз с разными seed. Это особенно важно
   при 21 train-эпизоде: отдельный запуск может сильно зависеть от начальных
   весов и порядка mini-batch.

Функция потерь при обучении — SmoothL1. Она ведёт себя как квадратичная ошибка
около нуля, но слабее реагирует на единичные большие выбросы, чем MSE.

## 11. Как читать метрики и графики

`MAE` — средняя абсолютная ошибка в ммоль/л. Она отвечает на вопрос, насколько
в среднем прогноз отличается от фактического `+2ч`. `RMSE` сильнее штрафует
крупные промахи, поэтому разница между RMSE и MAE указывает на наличие эпизодов
с особенно большой ошибкой. Для обеих метрик меньшее значение лучше.

На столбчатом графике высота — средняя ошибка по {config.repetitions} запускам,
а чёрные усы — стандартное отклонение между запусками. У baseline
«Последнее значение» усов нет, поскольку в нём отсутствует случайное обучение.
Линейный график показывает средний прогноз для каждого из
{split_counts["test"]} поздних test-эпизодов, но из-за малого test-набора его
следует использовать только для качественного разбора отдельных ошибок.

## 12. Что показал эксперимент

Zero-shot перенос оказался слабым: модель «До адаптации» получила MAE
{summaries["pretrained"].mae_mean:.3f} ммоль/л. Это признак domain shift:
виртуальная физиология, расписание еды и механизм регистрации инсулина в
SimGlucose отличаются от персональных snapshot-данных.

После fine-tuning MAE снизилась до
{summaries["fine_tuned"].mae_mean:.3f} ±
{summaries["fine_tuned"].mae_std:.3f} ммоль/л. Относительно обучения с нуля
улучшение составило {mae_change:.1f}%. Следовательно, в этом конкретном
хронологическом разбиении полезными оказались не готовые synthetic-прогнозы,
а начальные представления сети, скорректированные персональными данными.

Этот вывод является учебным результатом на ограниченной выборке, а не оценкой
клинической применимости. Для устойчивого вывода нужны более длинный период,
несколько пользователей и внешняя проверка на полностью независимых данных.
"""
    output_path.write_text(report, encoding="utf-8")


def main() -> None:
    args = parse_args()
    config = EpisodeConfig()
    if args.quick:
        config = EpisodeConfig(
            pretrain_epochs=30,
            scratch_epochs=50,
            fine_tune_epochs=30,
            repetitions=3,
            synthetic_days_per_patient=1,
            synthetic_patients=("adult#001", "adult#005"),
        )
    args.output_dir.mkdir(parents=True, exist_ok=True)

    personal = load_personal_episodes(args.export_zip, config.personal_timezone)
    personal_x, personal_y, personal_baseline = episode_arrays(personal)
    splits = split_personal_episodes(personal_x, personal_y, personal_baseline, config)
    if min(len(value[0]) for value in splits.values()) < 2:
        raise ValueError("Not enough episode snapshots for chronological train/validation/test.")

    timeline_config = ExperimentConfig(
        seed=config.seed,
        synthetic_days_per_patient=config.synthetic_days_per_patient,
        synthetic_patients=config.synthetic_patients,
    )
    synthetic_timeline = generate_synthetic_timeline(
        timeline_config.synthetic_patients,
        timeline_config.synthetic_days_per_patient,
        timeline_config.seed,
    )
    synthetic_episodes = synthetic_episodes_from_timeline(synthetic_timeline)
    synthetic_x, synthetic_y, _ = episode_arrays(synthetic_episodes)
    minimum_synthetic_episodes = 8 if args.quick else 20
    if len(synthetic_x) < minimum_synthetic_episodes:
        raise ValueError(
            "SimGlucose produced too few synthetic meal episodes: "
            f"{len(synthetic_x)} < {minimum_synthetic_episodes}."
        )

    summaries, predictions, _ = run_repetitions(
        (synthetic_x, synthetic_y),
        splits,
        config,
    )
    split_counts = {name: int(len(value[0])) for name, value in splits.items()}
    payload = {
        "config": asdict(config),
        "feature_names": list(EPISODE_FEATURE_NAMES),
        "personal_episode_count": int(len(personal_x)),
        "synthetic_episode_count": int(len(synthetic_x)),
        "split_counts": split_counts,
        "metrics": {name: asdict(summary) for name, summary in summaries.items()},
    }
    (args.output_dir / "episode_metrics.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    plot_episode_comparison(
        summaries,
        args.output_dir / "episode_comparison_ru.png",
    )
    plot_episode_predictions(
        predictions,
        args.output_dir / "episode_predictions_ru.png",
    )
    render_episode_report(
        args.output_dir / "EPISODE_REPORT.md",
        config,
        len(personal_x),
        len(synthetic_x),
        split_counts,
        summaries,
    )
    render_episode_report(
        args.report_path,
        config,
        len(personal_x),
        len(synthetic_x),
        split_counts,
        summaries,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
