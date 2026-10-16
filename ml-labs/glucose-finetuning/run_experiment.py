from __future__ import annotations

import argparse
import copy
import importlib.metadata
import json
import math
import random
import warnings
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
import torch
from matplotlib import pyplot as plt
from sklearn.metrics import mean_absolute_error, mean_squared_error
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

matplotlib.use("Agg")

MMOL_PER_MG_DL = 1.0 / 18.0182
GRID_MINUTES = 5
HISTORY_STEPS = 12
HORIZON_STEPS = 6
FEATURE_NAMES = (
    "glucose_relative",
    "glucose_level",
    "glucose_delta",
    "carbs_recent",
    "insulin_recent",
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
class ExperimentConfig:
    seed: int = 42
    personal_timezone: str = "Europe/Samara"
    personal_train_fraction: float = 0.60
    personal_validation_fraction: float = 0.20
    fine_tune_fraction: float = 0.25
    batch_size: int = 128
    hidden_size: int = 32
    pretrain_epochs: int = 18
    scratch_epochs: int = 25
    fine_tune_epochs: int = 12
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
class Metrics:
    mae_mmol_l: float
    rmse_mmol_l: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pretrain a glucose forecasting GRU on SimGlucose and fine-tune it on a Glucotracker export.",
    )
    parser.add_argument("--export-zip", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("results"))
    parser.add_argument("--quick", action="store_true")
    return parser.parse_args()


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)


def find_export_root(archive: zipfile.ZipFile) -> str:
    summary_names = [name for name in archive.namelist() if name.endswith("/summary.json")]
    if len(summary_names) != 1:
        raise ValueError("Expected exactly one summary.json inside the Glucotracker export.")
    return summary_names[0].removesuffix("/summary.json")


def read_export_csv(archive: zipfile.ZipFile, root: str, filename: str) -> pd.DataFrame:
    path = f"{root}/csv/{filename}"
    try:
        with archive.open(path) as stream:
            return pd.read_csv(stream)
    except KeyError as exc:
        raise ValueError(f"Required export table is missing: {filename}") from exc


def load_personal_timeline(export_zip: Path, timezone: str) -> tuple[pd.DataFrame, dict[str, int | str]]:
    with zipfile.ZipFile(export_zip) as archive:
        root = find_export_root(archive)
        cgm = read_export_csv(archive, root, "cgm_nightscout_glucose_entries.csv")
        meals = read_export_csv(archive, root, "meals.csv")
        insulin = read_export_csv(archive, root, "insulin_nightscout_events.csv")
        sensors = read_export_csv(archive, root, "sensor_sessions.csv")

    cgm["timestamp"] = pd.to_datetime(cgm["timestamp"], utc=True, errors="coerce", format="mixed")
    cgm["glucose_mmol_l"] = pd.to_numeric(cgm["value_mmol_l"], errors="coerce")
    cgm = cgm.dropna(subset=["timestamp", "glucose_mmol_l"])
    cgm = cgm[cgm["glucose_mmol_l"].between(2.0, 30.0)]

    sensors["started_at"] = pd.to_datetime(
        sensors["started_at"],
        utc=True,
        errors="coerce",
        format="mixed",
    )
    sensors["ended_at"] = pd.to_datetime(
        sensors["ended_at"],
        utc=True,
        errors="coerce",
        format="mixed",
    )
    sensors["excluded_from_analytics"] = sensors["excluded_from_analytics"].fillna(False).astype(bool)
    active_mask = pd.Series(False, index=cgm.index)
    for session in sensors.loc[~sensors["excluded_from_analytics"]].itertuples():
        session_end = session.ended_at if pd.notna(session.ended_at) else cgm["timestamp"].max() + pd.Timedelta(minutes=1)
        active_mask |= (cgm["timestamp"] >= session.started_at) & (cgm["timestamp"] < session_end)
    cgm = cgm.loc[active_mask].copy()

    meals["eaten_at"] = pd.to_datetime(meals["eaten_at"], errors="coerce", format="mixed")
    meals = meals[meals["status"].astype(str).str.lower().eq("accepted")].copy()
    meals["timestamp"] = (
        meals["eaten_at"]
        .dt.tz_localize(timezone, ambiguous="NaT", nonexistent="shift_forward")
        .dt.tz_convert("UTC")
    )
    meals["carbs_g"] = pd.to_numeric(meals["total_carbs_g"], errors="coerce").fillna(0.0).clip(lower=0.0)
    meals = meals.dropna(subset=["timestamp"])

    insulin["timestamp"] = pd.to_datetime(
        insulin["timestamp"],
        utc=True,
        errors="coerce",
        format="mixed",
    )
    insulin["insulin_units"] = pd.to_numeric(insulin["insulin_units"], errors="coerce").fillna(0.0).clip(lower=0.0)
    insulin = insulin.dropna(subset=["timestamp"])

    start = cgm["timestamp"].min().floor(f"{GRID_MINUTES}min")
    end = cgm["timestamp"].max().ceil(f"{GRID_MINUTES}min")
    index = pd.date_range(start=start, end=end, freq=f"{GRID_MINUTES}min", tz="UTC")

    glucose = (
        cgm.set_index("timestamp")["glucose_mmol_l"]
        .sort_index()
        .resample(f"{GRID_MINUTES}min")
        .mean()
        .reindex(index)
        .interpolate(method="time", limit=2, limit_area="inside")
    )
    carbs = aggregate_events(meals, "timestamp", "carbs_g", index)
    insulin_units = aggregate_events(insulin, "timestamp", "insulin_units", index)

    timeline = build_features(glucose, carbs, insulin_units)
    metadata: dict[str, int | str] = {
        "raw_cgm_points": int(len(active_mask)),
        "kept_cgm_points": int(len(cgm)),
        "accepted_meals": int(len(meals)),
        "insulin_events": int(len(insulin)),
        "active_sensor_sessions": int((~sensors["excluded_from_analytics"]).sum()),
        "excluded_sensor_sessions": int(sensors["excluded_from_analytics"].sum()),
        "first_cgm_at": cgm["timestamp"].min().isoformat(),
        "last_cgm_at": cgm["timestamp"].max().isoformat(),
    }
    return timeline, metadata


def aggregate_events(
    events: pd.DataFrame,
    timestamp_column: str,
    value_column: str,
    index: pd.DatetimeIndex,
) -> pd.Series:
    if events.empty:
        return pd.Series(0.0, index=index)
    values = (
        events.set_index(timestamp_column)[value_column]
        .sort_index()
        .resample(f"{GRID_MINUTES}min")
        .sum()
        .reindex(index, fill_value=0.0)
    )
    return values.astype(float)


def generate_synthetic_timeline(
    patients: tuple[str, ...],
    days_per_patient: int,
    seed: int,
) -> pd.DataFrame:
    from simglucose.actuator.pump import InsulinPump
    from simglucose.controller.basal_bolus_ctrller import BBController
    from simglucose.patient.t1dpatient import T1DPatient
    from simglucose.sensor.cgm import CGMSensor
    from simglucose.simulation.env import T1DSimEnv
    from simglucose.simulation.scenario_gen import RandomScenario

    frames: list[pd.DataFrame] = []
    warnings.filterwarnings("ignore", category=FutureWarning, module="simglucose")
    for patient_index, patient_name in enumerate(patients):
        patient_seed = seed + patient_index * 100
        patient = T1DPatient.withName(patient_name, random_init_bg=True, seed=patient_seed + 1)
        sensor = CGMSensor.withName("Dexcom", seed=patient_seed + 2)
        pump = InsulinPump.withName("Insulet")
        scenario = RandomScenario(
            start_time=datetime(2020, 1, 1) + timedelta(days=patient_index * 20),
            seed=patient_seed + 3,
        )
        env = T1DSimEnv(patient, sensor, pump, scenario)
        controller = BBController()
        observation, reward, done, info = env.reset()
        end_time = env.time + timedelta(days=days_per_patient)
        while env.time < end_time:
            action = controller.policy(observation, reward, done, **info)
            observation, reward, done, info = env.step(action)

        history = env.show_history().reset_index().rename(columns={"Time": "timestamp"})
        sample_minutes = float(env.sample_time)
        history["timestamp"] = pd.to_datetime(history["timestamp"], utc=True)
        history["glucose_mmol_l"] = pd.to_numeric(history["CGM"], errors="coerce") * MMOL_PER_MG_DL
        history["carbs_g"] = pd.to_numeric(history["CHO"], errors="coerce").fillna(0.0) * sample_minutes
        insulin_rate = pd.to_numeric(history["insulin"], errors="coerce").fillna(0.0)
        basal_rate = float(insulin_rate.quantile(0.20))
        history["insulin_units"] = (insulin_rate - basal_rate).clip(lower=0.0) * sample_minutes

        patient_frame = history.set_index("timestamp")
        grid = pd.date_range(
            patient_frame.index.min().floor(f"{GRID_MINUTES}min"),
            patient_frame.index.max().ceil(f"{GRID_MINUTES}min"),
            freq=f"{GRID_MINUTES}min",
            tz="UTC",
        )
        glucose = (
            patient_frame["glucose_mmol_l"]
            .resample(f"{GRID_MINUTES}min")
            .mean()
            .reindex(grid)
            .interpolate(method="time", limit=2, limit_area="inside")
        )
        carbs = patient_frame["carbs_g"].resample(f"{GRID_MINUTES}min").sum().reindex(grid, fill_value=0.0)
        insulin_units = (
            patient_frame["insulin_units"].resample(f"{GRID_MINUTES}min").sum().reindex(grid, fill_value=0.0)
        )
        featured = build_features(glucose, carbs, insulin_units)
        featured["series_id"] = patient_name
        frames.append(featured)
    return pd.concat(frames)


def build_features(
    glucose: pd.Series,
    carbs: pd.Series,
    insulin_units: pd.Series,
) -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "glucose_mmol_l": glucose.astype(float),
            "carbs_g": carbs.astype(float),
            "insulin_units": insulin_units.astype(float),
        },
    )
    frame["glucose_delta"] = frame["glucose_mmol_l"].diff()
    frame["carbs_recent"] = frame["carbs_g"].rolling(6, min_periods=1).sum()
    frame["insulin_recent"] = frame["insulin_units"].rolling(24, min_periods=1).sum()
    local_hour = frame.index.hour + frame.index.minute / 60.0
    frame["hour_sin"] = np.sin(2.0 * np.pi * local_hour / 24.0)
    frame["hour_cos"] = np.cos(2.0 * np.pi * local_hour / 24.0)
    return frame


def make_windows(frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    all_x: list[np.ndarray] = []
    all_y: list[float] = []
    all_last: list[float] = []
    grouped = frame.groupby("series_id", sort=False) if "series_id" in frame.columns else [("personal", frame)]
    for _, group in grouped:
        group = group.sort_index()
        glucose = group["glucose_mmol_l"].to_numpy(dtype=np.float32)
        delta = group["glucose_delta"].to_numpy(dtype=np.float32)
        carbs = group["carbs_recent"].to_numpy(dtype=np.float32)
        insulin = group["insulin_recent"].to_numpy(dtype=np.float32)
        hour_sin = group["hour_sin"].to_numpy(dtype=np.float32)
        hour_cos = group["hour_cos"].to_numpy(dtype=np.float32)
        for end in range(HISTORY_STEPS - 1, len(group) - HORIZON_STEPS):
            start = end - HISTORY_STEPS + 1
            target_index = end + HORIZON_STEPS
            history_glucose = glucose[start : end + 1]
            last_glucose = float(history_glucose[-1])
            target_glucose = float(glucose[target_index])
            raw = np.column_stack(
                (
                    (history_glucose - last_glucose) / 3.0,
                    np.full(HISTORY_STEPS, last_glucose / 10.0, dtype=np.float32),
                    delta[start : end + 1] / 1.5,
                    carbs[start : end + 1] / 60.0,
                    insulin[start : end + 1] / 12.0,
                    hour_sin[start : end + 1],
                    hour_cos[start : end + 1],
                ),
            )
            if not np.isfinite(raw).all() or not math.isfinite(target_glucose):
                continue
            all_x.append(raw.astype(np.float32))
            all_y.append((target_glucose - last_glucose) / 3.0)
            all_last.append(last_glucose)
    return (
        np.asarray(all_x, dtype=np.float32),
        np.asarray(all_y, dtype=np.float32),
        np.asarray(all_last, dtype=np.float32),
    )


def chronological_split(
    x: np.ndarray,
    y: np.ndarray,
    last: np.ndarray,
    config: ExperimentConfig,
) -> dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]]:
    count = len(x)
    train_end = max(1, int(count * config.personal_train_fraction))
    validation_end = max(train_end + 1, int(count * (config.personal_train_fraction + config.personal_validation_fraction)))
    purge = HISTORY_STEPS + HORIZON_STEPS
    return {
        "train": (x[:train_end], y[:train_end], last[:train_end]),
        "validation": (
            x[train_end + purge : validation_end],
            y[train_end + purge : validation_end],
            last[train_end + purge : validation_end],
        ),
        "test": (
            x[validation_end + purge :],
            y[validation_end + purge :],
            last[validation_end + purge :],
        ),
    }


class GlucoseGRU(nn.Module):
    def __init__(self, input_size: int, hidden_size: int) -> None:
        super().__init__()
        self.gru = nn.GRU(input_size=input_size, hidden_size=hidden_size, batch_first=True)
        self.head = nn.Sequential(
            nn.LayerNorm(hidden_size),
            nn.Linear(hidden_size, 16),
            nn.ReLU(),
            nn.Linear(16, 1),
        )

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        sequence, _ = self.gru(inputs)
        return self.head(sequence[:, -1]).squeeze(-1)


def loader(x: np.ndarray, y: np.ndarray, batch_size: int, shuffle: bool) -> DataLoader:
    dataset = TensorDataset(torch.from_numpy(x), torch.from_numpy(y))
    return DataLoader(dataset, batch_size=batch_size, shuffle=shuffle, drop_last=False)


def train_model(
    model: nn.Module,
    train_data: tuple[np.ndarray, np.ndarray],
    validation_data: tuple[np.ndarray, np.ndarray],
    epochs: int,
    batch_size: int,
    learning_rate: float,
) -> tuple[nn.Module, dict[str, list[float]]]:
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=1e-4)
    loss_function = nn.SmoothL1Loss()
    train_loader = loader(*train_data, batch_size=batch_size, shuffle=True)
    validation_loader = loader(*validation_data, batch_size=batch_size, shuffle=False)
    best_state = copy.deepcopy(model.state_dict())
    best_validation = float("inf")
    patience = 5
    stale_epochs = 0
    curves = {"train": [], "validation": []}

    for _ in range(epochs):
        model.train()
        train_losses: list[float] = []
        for batch_x, batch_y in train_loader:
            optimizer.zero_grad()
            loss = loss_function(model(batch_x), batch_y)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            train_losses.append(float(loss.detach()))

        model.eval()
        validation_losses: list[float] = []
        with torch.no_grad():
            for batch_x, batch_y in validation_loader:
                validation_losses.append(float(loss_function(model(batch_x), batch_y)))

        train_loss = float(np.mean(train_losses))
        validation_loss = float(np.mean(validation_losses))
        curves["train"].append(train_loss)
        curves["validation"].append(validation_loss)
        if validation_loss < best_validation - 1e-5:
            best_validation = validation_loss
            best_state = copy.deepcopy(model.state_dict())
            stale_epochs = 0
        else:
            stale_epochs += 1
            if stale_epochs >= patience:
                break

    model.load_state_dict(best_state)
    return model, curves


def predict_glucose(model: nn.Module, x: np.ndarray, last: np.ndarray) -> np.ndarray:
    model.eval()
    with torch.no_grad():
        predicted_delta = model(torch.from_numpy(x)).numpy()
    return last + predicted_delta * 3.0


def calculate_metrics(actual: np.ndarray, predicted: np.ndarray) -> Metrics:
    return Metrics(
        mae_mmol_l=float(mean_absolute_error(actual, predicted)),
        rmse_mmol_l=float(mean_squared_error(actual, predicted) ** 0.5),
    )


def plot_comparison(metrics: dict[str, Metrics], output_path: Path) -> None:
    labels = list(metrics)
    mae = [metrics[label].mae_mmol_l for label in labels]
    rmse = [metrics[label].rmse_mmol_l for label in labels]
    positions = np.arange(len(labels))
    width = 0.36
    fig, axis = plt.subplots(figsize=(9, 5))
    axis.bar(positions - width / 2, mae, width, label="MAE")
    axis.bar(positions + width / 2, rmse, width, label="RMSE")
    axis.set_ylabel("ммоль/л")
    axis.set_title("Прогноз CGM через 30 минут")
    axis.set_xticks(positions, [METHOD_LABELS_RU[label] for label in labels], rotation=8)
    axis.legend(title="Метрика")
    axis.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_path, dpi=160)
    plt.close(fig)


def plot_curves(curves: dict[str, dict[str, list[float]]], output_path: Path) -> None:
    title_map = {
        "pretraining": "Предварительное обучение",
        "scratch": "Обучение с нуля",
        "fine-tuning": "Персональное дообучение",
    }
    fig, axes = plt.subplots(1, len(curves), figsize=(5 * len(curves), 4), squeeze=False)
    for axis, (name, values) in zip(axes[0], curves.items(), strict=True):
        axis.plot(values["train"], label="Обучение")
        axis.plot(values["validation"], label="Проверка")
        axis.set_title(title_map.get(name, name))
        axis.set_xlabel("Эпоха")
        axis.set_ylabel("Ошибка SmoothL1")
        axis.grid(alpha=0.25)
        axis.legend()
    fig.tight_layout()
    fig.savefig(output_path, dpi=160)
    plt.close(fig)


def render_report(
    output_path: Path,
    config: ExperimentConfig,
    metadata: dict[str, int | str],
    sample_counts: dict[str, int],
    metrics: dict[str, Metrics],
) -> None:
    best_mae_name = min(metrics, key=lambda name: metrics[name].mae_mmol_l)
    best_rmse_name = min(metrics, key=lambda name: metrics[name].rmse_mmol_l)
    persistence = metrics["persistence"].mae_mmol_l
    fine_tuned = metrics["fine_tuned"].mae_mmol_l
    zero_shot = metrics["pretrained"].mae_mmol_l
    persistence_improvement = 100.0 * (persistence - fine_tuned) / persistence
    transfer_improvement = 100.0 * (zero_shot - fine_tuned) / zero_shot
    rows = "\n".join(
        f"| {name} | {value.mae_mmol_l:.3f} | {value.rmse_mmol_l:.3f} |"
        for name, value in metrics.items()
    )
    report = f"""# Лабораторная работа

## Тема

Fine-tuning нейронной сети для краткосрочного прогноза глюкозы на ограниченном
персональном наборе данных.

## Цель

Исследовать, улучшает ли предварительное обучение на синтетической популяции
SimGlucose качество прогноза после адаптации на небольшом персональном наборе.

## Постановка задачи

По 60 минутам истории предсказывается CGM через 30 минут. Вход содержит только
наблюдаемые исторические данные: CGM, недавние углеводы, зафиксированные события
инсулина и время суток. Выход модели — изменение глюкозы относительно последней
точки. Модель не рассчитывает дозу и не является медицинским изделием.

## Данные

- SimGlucose: {len(config.synthetic_patients)} виртуальных пациентов,
  по {config.synthetic_days_per_patient} суток.
- Персональный экспорт: {metadata["kept_cgm_points"]} CGM-точек после фильтрации.
- Принятые приёмы пищи: {metadata["accepted_meals"]}.
- События инсулина: {metadata["insulin_events"]}.
- Исключённые sensor sessions: {metadata["excluded_sensor_sessions"]}.
- Персональные окна train/validation/test:
  {sample_counts["personal_train"]}/{sample_counts["personal_validation"]}/{sample_counts["personal_test"]}.
- Для fine-tuning использовано только {sample_counts["fine_tune"]} окон
  ({config.fine_tune_fraction:.0%} personal train).

Разбиение выполняется хронологически. Между частями оставлен purge gap длиной
90 минут, поэтому перекрывающиеся окна на границе не создают утечку.
Corrupted sensor intervals исключаются по флагу экспорта.

## Архитектура

Однослойная GRU с {config.hidden_size} скрытыми признаками, LayerNorm и
двухслойной регрессионной головой. Функция потерь — SmoothL1, оптимизатор —
AdamW. Количество входных признаков: {len(FEATURE_NAMES)}.

## Эксперименты

| Метод | MAE, ммоль/л | RMSE, ммоль/л |
|---|---:|---:|
{rows}

Лучший результат по MAE: **{best_mae_name}**.
Лучший результат по RMSE: **{best_rmse_name}**.
Fine-tuning снизил MAE относительно zero-shot pretrained модели на
**{transfer_improvement:.1f}%**, а относительно persistence — на
**{persistence_improvement:.1f}%**.

## Вывод

Эксперимент демонстрирует перенос параметров с синтетических виртуальных
пациентов на ограниченный персональный ряд. Сравнение со scratch-моделью
показывает, даёт ли pretraining преимущество именно при одинаковом малом объёме
персональных данных. Результаты относятся только к этому временному диапазону и
не подтверждают клиническую пригодность модели.

## Ограничения

1. SimGlucose является математическим симулятором и не воспроизводит полностью
   конкретного человека.
2. В персональных данных возможны ошибки оценок углеводов и пропущенные события.
3. Использован один пользователь и один хронологический test interval.
4. Модель прогнозирует CGM, но не должна применяться для выбора лечения.

## Источники

1. Jinyu Xie, SimGlucose — Python-реализация симулятора UVA/Padova:
   https://github.com/jxx123/simglucose
2. Описание пакета и виртуальной популяции SimGlucose:
   https://pypi.org/project/simglucose/
"""
    output_path.write_text(report, encoding="utf-8")


def main() -> None:
    args = parse_args()
    config = ExperimentConfig()
    if args.quick:
        config = ExperimentConfig(
            pretrain_epochs=5,
            scratch_epochs=7,
            fine_tune_epochs=5,
            synthetic_days_per_patient=1,
            synthetic_patients=("adult#001", "adult#005"),
        )
    seed_everything(config.seed)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    print("Loading and filtering personal export...")
    personal_timeline, metadata = load_personal_timeline(args.export_zip, config.personal_timezone)
    personal_x, personal_y, personal_last = make_windows(personal_timeline)
    splits = chronological_split(personal_x, personal_y, personal_last, config)
    train_x, train_y, _ = splits["train"]
    validation_x, validation_y, _ = splits["validation"]
    test_x, test_y, test_last = splits["test"]
    fine_tune_count = max(64, int(len(train_x) * config.fine_tune_fraction))
    fine_tune_x = train_x[-fine_tune_count:]
    fine_tune_y = train_y[-fine_tune_count:]

    if min(len(fine_tune_x), len(validation_x), len(test_x)) == 0:
        raise ValueError("Not enough valid personal windows after filtering.")

    print("Generating SimGlucose population...")
    synthetic_timeline = generate_synthetic_timeline(
        config.synthetic_patients,
        config.synthetic_days_per_patient,
        config.seed,
    )
    synthetic_x, synthetic_y, _ = make_windows(synthetic_timeline)
    synthetic_split = int(len(synthetic_x) * 0.85)

    print("Pretraining on synthetic patients...")
    pretrained = GlucoseGRU(len(FEATURE_NAMES), config.hidden_size)
    pretrained, pretrain_curves = train_model(
        pretrained,
        (synthetic_x[:synthetic_split], synthetic_y[:synthetic_split]),
        (synthetic_x[synthetic_split:], synthetic_y[synthetic_split:]),
        config.pretrain_epochs,
        config.batch_size,
        learning_rate=1e-3,
    )

    print("Training personal model from scratch...")
    scratch = GlucoseGRU(len(FEATURE_NAMES), config.hidden_size)
    scratch, scratch_curves = train_model(
        scratch,
        (fine_tune_x, fine_tune_y),
        (validation_x, validation_y),
        config.scratch_epochs,
        min(config.batch_size, 64),
        learning_rate=1e-3,
    )

    print("Fine-tuning pretrained model...")
    fine_tuned = copy.deepcopy(pretrained)
    fine_tuned, fine_tune_curves = train_model(
        fine_tuned,
        (fine_tune_x, fine_tune_y),
        (validation_x, validation_y),
        config.fine_tune_epochs,
        min(config.batch_size, 64),
        learning_rate=3e-4,
    )

    actual_glucose = test_last + test_y * 3.0
    predictions = {
        "persistence": test_last,
        "scratch": predict_glucose(scratch, test_x, test_last),
        "pretrained": predict_glucose(pretrained, test_x, test_last),
        "fine_tuned": predict_glucose(fine_tuned, test_x, test_last),
    }
    metrics = {name: calculate_metrics(actual_glucose, values) for name, values in predictions.items()}
    sample_counts = {
        "synthetic": int(len(synthetic_x)),
        "personal_total": int(len(personal_x)),
        "personal_train": int(len(train_x)),
        "personal_validation": int(len(validation_x)),
        "personal_test": int(len(test_x)),
        "fine_tune": int(len(fine_tune_x)),
    }
    payload = {
        "config": asdict(config),
        "versions": {
            package: importlib.metadata.version(package)
            for package in ("simglucose", "torch", "pandas", "scikit-learn")
        },
        "metadata": metadata,
        "sample_counts": sample_counts,
        "metrics": {name: asdict(value) for name, value in metrics.items()},
    }
    (args.output_dir / "metrics.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    plot_comparison(metrics, args.output_dir / "comparison.png")
    plot_curves(
        {
            "pretraining": pretrain_curves,
            "scratch": scratch_curves,
            "fine-tuning": fine_tune_curves,
        },
        args.output_dir / "training_curves.png",
    )
    render_report(
        args.output_dir / "LAB_REPORT.md",
        config,
        metadata,
        sample_counts,
        metrics,
    )
    print(json.dumps(payload["metrics"], ensure_ascii=False, indent=2))
    print(f"Results: {args.output_dir.resolve()}")


if __name__ == "__main__":
    main()
