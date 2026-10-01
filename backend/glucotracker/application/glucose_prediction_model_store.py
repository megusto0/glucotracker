"""Owner-scoped, content-addressed forecast fits; JSON and LightGBM text only."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from threading import RLock
from uuid import UUID

import numpy as np
from lightgbm.basic import LightGBMError

from glucotracker.application import glucose_prediction_experimental as prediction
from glucotracker.config import get_settings

logger = logging.getLogger(__name__)
_MEMORY: OrderedDict[tuple[str, str], prediction._FittedHistory] = OrderedDict()
_LOCK = RLock()


def _signature(arrays: list[np.ndarray], metadata: dict) -> str:
    digest = hashlib.sha256(json.dumps(metadata, sort_keys=True).encode())
    for array in arrays:
        digest.update(str((array.shape, array.dtype.str)).encode())
        digest.update(np.ascontiguousarray(array).tobytes())
    return digest.hexdigest()


def _encode(fit: prediction._FittedHistory) -> dict:
    return {
        "selected_tau": fit.selected_tau,
        "shape_blend": fit.shape_blend,
        "coefficients": fit.coefficients.tolist(),
        "shape": [b.model_to_string() for b in fit.shape.boosters],
        "quantiles": {
            str(q): [b.model_to_string() for b in boosters]
            for q, boosters in fit.quantiles.boosters.items()
        },
        "conformal_scale": fit.conformal_scale.tolist(),
        "validation_mae": fit.validation_mae,
        "baseline_mae": fit.baseline_mae,
        "post_meal_metrics": fit.post_meal_metrics,
        "critical_metrics": fit.critical_metrics,
    }


def _decode(payload: dict) -> prediction._FittedHistory:
    import lightgbm as lgb

    values = dict(payload)
    values["coefficients"] = np.asarray(values["coefficients"], dtype=float)
    values["conformal_scale"] = np.asarray(values["conformal_scale"], dtype=float)
    values["shape"] = prediction._TreeFit(
        [lgb.Booster(model_str=text) for text in values["shape"]]
    )
    values["quantiles"] = prediction._QuantileFit(
        {
            float(q): [lgb.Booster(model_str=text) for text in texts]
            for q, texts in values["quantiles"].items()
        }
    )
    return prediction._FittedHistory(**values)


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".fit-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, allow_nan=False)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def fitted_history(
    user_id: UUID,
    x: np.ndarray,
    y: np.ndarray,
    eligibility: np.ndarray,
    row_times: list[datetime],
    horizons: list[int],
    effects: prediction._KnownInputEffects,
    train_end: int,
    calibration_end: int,
) -> prediction._FittedHistory:
    """Reuse only a fit for this owner, exact data and implementation/configuration."""
    if user_id is None:
        raise ValueError("Forecast model artifacts require user_id")
    root = get_settings().prediction_model_dir.resolve()
    namespace = str(root / str(user_id))
    # Source digest also invalidates artifacts during uncommitted development.
    source_digest = hashlib.sha256(Path(prediction.__file__).read_bytes()).hexdigest()
    signature = _signature(
        [
            x,
            y,
            eligibility,
            effects.momentum_slope,
            effects.absorbed_carbs,
            effects.delivered_insulin,
        ],
        {
            "owner": str(user_id),
            "version": prediction.MODEL_VERSION,
            "source": source_digest,
            "horizons": horizons,
            "times": [t.isoformat() for t in row_times],
            "splits": [train_end, calibration_end],
        },
    )
    key = (namespace, signature)
    path = (
        Path(namespace)
        / f"{prediction.MODEL_VERSION}-{horizons[-1]}-{horizons[0]}.json"
    )
    with _LOCK:
        if key in _MEMORY:
            _MEMORY.move_to_end(key)
            return _MEMORY[key]
        fit = None
        if path.exists():
            try:
                payload = json.loads(path.read_text())
                if payload.get("signature") == signature and payload.get(
                    "owner"
                ) == str(user_id):
                    fit = _decode(payload["fit"])
            except (ValueError, KeyError, TypeError, OSError, LightGBMError):
                logger.warning("Ignoring an unreadable forecast model artifact")
        if fit is None:
            fit = prediction._train_history(
                x,
                y,
                eligibility,
                row_times,
                horizons,
                effects,
                train_end,
                calibration_end,
            )
            try:
                _write(
                    path,
                    {
                        "signature": signature,
                        "owner": str(user_id),
                        "version": prediction.MODEL_VERSION,
                        "fit": _encode(fit),
                    },
                )
            except OSError:
                # A valid forecast remains usable if disk caching is unavailable.
                logger.warning(
                    "Forecast model retained in memory; disk cache unavailable"
                )
        _MEMORY[key] = fit
        while len(_MEMORY) > 8:
            _MEMORY.popitem(last=False)
        return fit
