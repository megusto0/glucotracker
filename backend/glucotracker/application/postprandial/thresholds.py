"""Classify glucose response thresholds for postprandial analysis.

Constants are documented with rationale. Tunable after observing
real distributions (see ADR-008 §2.3 and out-of-band ask #1).
"""

GENTLE_MAX_DELTA: float = 2.0
"""Gentle response: peak Δ from baseline < 2.0 mmol/L."""

GENTLE_RETURN_DELTA: float = 0.5
"""Gentle response: must return within this many mmol/L
of baseline by t=+90 min."""

SPIKE_MIN_DELTA: float = 4.0
"""Spike response: peak Δ >= 4.0 mmol/L."""

SPIKE_SUSTAINED_THRESHOLD: float = 10.0
"""If glucose stays above this value for >= 30 min, classify as spike."""

SPIKE_SUSTAINED_MINUTES: int = 30
"""Minimum duration above SUSTAINED_THRESHOLD for spike classification."""

UNSTABLE_MIN_PEAKS: int = 2
"""Number of distinct peaks for 'unstable' classification."""

UNSTABLE_PEAK_PROMINENCE: float = 1.0
"""Minimum peak prominence in mmol/L to count as a distinct peak."""

UNSTABLE_MAX_CV: float = 0.25
"""Coefficient of variation above which a response is unstable."""

COVERAGE_MIN_FOR_CLASSIFICATION: float = 0.60
"""Minimum CGM coverage fraction for a valid classification."""

COVERAGE_DOWNWEIGHT_THRESHOLD: float = 0.80
"""Coverage below this but >= min triggers a quality flag."""

CGM_GAP_MAX_MINUTES: int = 15
"""Max gap between CGM readings before an anchor is recorded as null."""

HYPO_RECOVERY_MIN_CARB_G: float = 10.0
"""Minimum grams of carbs for a meal to count as hypo recovery.
Below this, the meal cannot raise glucose (diet sodas, zero-carb drinks)."""

HYPO_RECOVERY_MAX_KCAL: float = 250.0
"""Maximum kcal for a meal to count as hypo recovery."""

DELAYED_PEAK_FAT_SHARE: float = 0.35
"""Fat share of total kcal above which a meal may have a delayed peak."""

DELAYED_PEAK_MIN_EXTENDED_COVERAGE: float = 0.70
"""Minimum extended CGM coverage to flag a delayed peak likely."""

EXTENDED_WINDOW_MINUTES: int = 300
"""Total window for extended analysis (includes anchors at 240 and 300 min)."""

DEFERRED_WORKER_DELAY_MINUTES: int = 300
"""How long after eaten_at the sweeper should wait before analyzing."""
