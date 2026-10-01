"""Keep the evaluated incumbent active until an experimental model is promoted."""

from types import ModuleType

from glucotracker.config import get_settings


def selected_predictor() -> ModuleType:
    if get_settings().experimental_glucose_prediction_enabled:
        from glucotracker.application import glucose_prediction_experimental

        return glucose_prediction_experimental
    from glucotracker.application import glucose_prediction

    return glucose_prediction
