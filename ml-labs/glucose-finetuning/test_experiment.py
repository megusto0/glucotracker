from __future__ import annotations

import numpy as np
import pandas as pd
import torch

from episode_experiment import (
    EPISODE_FEATURE_NAMES,
    EpisodeConfig,
    EpisodeMLP,
    episode_arrays,
    split_personal_episodes,
    synthetic_episodes_from_timeline,
)
from run_experiment import (
    FEATURE_NAMES,
    GlucoseGRU,
    ExperimentConfig,
    build_features,
    chronological_split,
    make_windows,
)


def sample_timeline(points: int = 240) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=points, freq="5min", tz="UTC")
    glucose = pd.Series(7.0 + np.sin(np.arange(points) / 12.0), index=index)
    carbs = pd.Series(0.0, index=index)
    insulin = pd.Series(0.0, index=index)
    carbs.iloc[50] = 40.0
    insulin.iloc[48] = 4.0
    return build_features(glucose, carbs, insulin)


def test_windows_have_expected_shape() -> None:
    x, y, last = make_windows(sample_timeline())

    assert x.shape[1:] == (12, len(FEATURE_NAMES))
    assert len(x) == len(y) == len(last)
    assert np.isfinite(x).all()


def test_gap_is_not_interpolated_into_training_window() -> None:
    timeline = sample_timeline()
    timeline.iloc[80:100, timeline.columns.get_loc("glucose_mmol_l")] = np.nan

    x_with_gap, _, _ = make_windows(timeline)
    x_without_gap, _, _ = make_windows(sample_timeline())

    assert len(x_with_gap) < len(x_without_gap)


def test_split_leaves_purge_gap() -> None:
    x, y, last = make_windows(sample_timeline(600))
    config = ExperimentConfig()
    splits = chronological_split(x, y, last, config)

    total_after_purge = sum(len(split[0]) for split in splits.values())
    assert total_after_purge < len(x)
    assert all(len(split[0]) > 0 for split in splits.values())


def test_model_returns_one_prediction_per_window() -> None:
    model = GlucoseGRU(input_size=len(FEATURE_NAMES), hidden_size=16)
    output = model(torch.zeros(4, 12, len(FEATURE_NAMES)))

    assert output.shape == (4,)


def test_episode_arrays_do_not_include_plus_2h_as_feature() -> None:
    episodes = pd.DataFrame(
        {
            "glucose_minus_30_mmol_l": [5.0, 6.0, 7.0],
            "glucose_plus_2h_mmol_l": [8.0, 9.0, 10.0],
            "total_carbs_g": [30.0, 40.0, 50.0],
            "total_insulin_units": [3.0, 4.0, 5.0],
            "duration_minutes": [10.0, 15.0, 20.0],
            "has_insulin": [1.0, 1.0, 1.0],
            "local_hour": [8.0, 12.0, 18.0],
        },
    )

    x, target, baseline = episode_arrays(episodes)

    assert x.shape == (3, len(EPISODE_FEATURE_NAMES))
    assert np.allclose(target * 3.0 + baseline, [8.0, 9.0, 10.0])


def test_episode_split_is_chronological() -> None:
    x = np.arange(36 * len(EPISODE_FEATURE_NAMES), dtype=np.float32).reshape(36, -1)
    y = np.arange(36, dtype=np.float32)
    baseline = y + 4.0

    splits = split_personal_episodes(x, y, baseline, EpisodeConfig())

    assert splits["train"][1][-1] < splits["validation"][1][0]
    assert splits["validation"][1][-1] < splits["test"][1][0]


def test_synthetic_episode_extraction_creates_targets() -> None:
    timeline = sample_timeline(300)
    timeline["series_id"] = "adult#test"
    episodes = synthetic_episodes_from_timeline(timeline)

    assert not episodes.empty
    assert episodes["glucose_minus_30_mmol_l"].notna().all()
    assert episodes["glucose_plus_2h_mmol_l"].notna().all()


def test_episode_model_returns_one_prediction_per_episode() -> None:
    model = EpisodeMLP(input_size=len(EPISODE_FEATURE_NAMES), hidden_size=12)
    output = model(torch.zeros(5, len(EPISODE_FEATURE_NAMES)))

    assert output.shape == (5,)
