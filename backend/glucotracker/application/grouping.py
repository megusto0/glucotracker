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

from datetime import timedelta
from enum import Enum

# Meals within this of the sitting's *first* meal belong to it. Adopted from
# the value the mobile client had already arrived at independently; ADR-019 §5.1
# records that it is not yet measured against the 75-day export.
SITTING_SPAN = timedelta(minutes=30)

# Insulin joins a sitting when it lands this close to it. Unchanged for now:
# ADR-019 §5.4 asks whether coverage should anchor to the sitting's span rather
# than to each meal, which is a separate question from clustering the food.
INSULIN_COVERAGE_WINDOW = timedelta(minutes=90)

# Bumped whenever a rule above changes what an episode contains. Anything that
# stores a derived number records this next to its own model version, so two
# groupings never end up mixed in one chart.
GROUPING_VERSION = "sitting-anchored-v1"


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
