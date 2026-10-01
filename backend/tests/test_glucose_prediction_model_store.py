"""Fit persistence, invalidation and owner boundaries without production data."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import lightgbm as lgb
import numpy as np
import pytest

from glucotracker.application import glucose_prediction_experimental as prediction
from glucotracker.application import glucose_prediction_model_store as store
from glucotracker.config import get_settings


def _fit():
    x = np.arange(20, dtype=float).reshape(-1, 1)
    booster = lgb.train(
        {"verbosity": -1, "num_threads": 1, "min_data_in_leaf": 2},
        lgb.Dataset(x, label=x[:, 0] * 0.1),
        num_boost_round=2,
    )
    return prediction._FittedHistory(
        30,
        0.5,
        np.ones((1, 3)),
        prediction._TreeFit([booster]),
        prediction._QuantileFit({0.1: [booster], 0.9: [booster]}),
        np.ones(1),
        0.2,
        0.3,
        {"count": 0},
        {"low_count": 0},
    )


def test_artifact_roundtrip_preserves_predictions():
    original = _fit()
    restored = store._decode(store._encode(original))
    x = np.array([[1.0], [8.0], [15.0]])
    np.testing.assert_array_equal(
        original.shape.boosters[0].predict(x), restored.shape.boosters[0].predict(x)
    )
    np.testing.assert_array_equal(original.coefficients, restored.coefficients)


@pytest.mark.parametrize("change", ["owner", "data", "disk_reload"])
def test_fit_reuse_is_scoped_and_invalidates_changed_data(
    tmp_path, monkeypatch, change
):
    monkeypatch.setenv("GLUCOTRACKER_PREDICTION_MODEL_DIR", str(tmp_path))
    get_settings.cache_clear()
    fitted = _fit()
    calls = []
    monkeypatch.setattr(
        prediction, "_train_history", lambda *args: calls.append(args) or fitted
    )
    owner = uuid4()
    x = np.ones((4, 2))
    y = np.ones((4, 1))
    mask = np.ones((4, 1), dtype=bool)
    times = [datetime(2026, 7, 1, tzinfo=UTC) + timedelta(hours=i) for i in range(4)]
    effects = prediction._KnownInputEffects(
        np.ones(4), np.ones((4, 1)), np.ones((4, 1))
    )

    def load(uid, inputs):
        return store.fitted_history(uid, inputs, y, mask, times, [30], effects, 2, 3)

    load(owner, x)
    assert len(calls) == 1
    load(owner, x)
    assert len(calls) == 1
    if change == "owner":
        load(uuid4(), x)
        assert len(calls) == 2
    elif change == "data":
        load(owner, x + 1)
        assert len(calls) == 2
    else:
        store._MEMORY.clear()
        load(owner, x)
        assert len(calls) == 1  # Reuse survives a worker restart.
    get_settings.cache_clear()
