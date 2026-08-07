"""One definition of what belongs together, and of how long to watch it.

Before this module, "which meals and doses are one event" was decided in eight
places with three different windows, and "how did it land" was asked with five
different horizons — two of which estimated the same quantity from the same
episodes and disagreed for no reason but the constant.

See ADR-019. Two rules hold here:

- A sitting is anchored to its own first meal, never chained to the previous
  one, so its total span is bounded by construction.
- An outcome is a path, not a reading. Consumers ask for a horizon by the
  question they are answering, and read peak and nadir rather than the single
  value at the end.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from enum import Enum

# Meals within this of the sitting's *first* meal belong to it. Adopted from
# the value the mobile client had already arrived at independently; ADR-019 §5.1
# records that it is not yet measured against the 75-day export.
SITTING_SPAN = timedelta(minutes=30)

# Insulin joins a sitting when it lands this close to it. Unchanged for now:
# ADR-019 §5.4 asks whether coverage should anchor to the sitting's span rather
# than to each meal, which is a separate question from clustering the food.
INSULIN_COVERAGE_WINDOW = timedelta(minutes=90)

# A dose given while glucose is climbing is answering a rise that has already
# started, so it belongs to whatever caused the rise rather than to whatever is
# about to be eaten. Measured over 75 days for this owner: boluses at the plate
# sit on a −0.40 mmol/L per hour trend, later ones on +1.80 with 86% rising.
# +0.3 mmol/L per 15 min — above the noise of a flat trace, well under +1.80/h.
RISING_PER_MINUTE = 0.02
TREND_LOOKBACK = timedelta(minutes=20)
MIN_TREND_MINUTES = 5

#: "Was glucose climbing at this moment", in app-local wall time.
RisingAt = Callable[[datetime], bool]

# Bumped whenever a rule above changes what an episode contains. Anything that
# stores a derived number records this next to its own model version, so two
# groupings never end up mixed in one chart.
GROUPING_VERSION = "sitting-anchored-v2"


def rising_test(series: list[tuple[datetime, float]]) -> RisingAt:
    """Build the "climbing right now" test from a local-wall glucose series.

    Passed into grouping as a plain predicate rather than as a glucose series,
    so the graph engine keeps knowing nothing about sensors, calibration or
    which value is the display one. It only needs the answer.
    """
    ordered = sorted(series)

    def rising(at: datetime) -> bool:
        window = [
            (timestamp, value)
            for timestamp, value in ordered
            if at - TREND_LOOKBACK <= timestamp <= at
        ]
        if len(window) < 2:
            return False
        minutes = (window[-1][0] - window[0][0]).total_seconds() / 60
        if minutes < MIN_TREND_MINUTES:
            return False
        return (window[-1][1] - window[0][1]) / minutes >= RISING_PER_MINUTE

    return rising


class Horizon(Enum):
    """How long after an episode its result is judged, by the question asked."""

    #: Did the dose cover the food? Most of a meal's rise has happened.
    IMMEDIATE_RESPONSE = timedelta(hours=2)
    #: Carbohydrate ratio evidence, including slower mixed meals.
    FULL_ABSORPTION = timedelta(hours=3)
    #: Correction evidence. Measured at 4.5 h rather than the kernel's 6.5:
    #: over 597 carb-free windows 90% of insulin effect had landed by 244 min.
    INSULIN_EXHAUSTED = timedelta(hours=4, minutes=30)

    @property
    def minutes(self) -> int:
        return round(self.value.total_seconds() / 60)
