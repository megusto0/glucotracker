"""List meals (last 14 days): calculated vs actual insulin, glucose, trends.

Read-only report for admin2 (or --user). Uses episode grouping for actual
insulin and HistoricalInsulinRecommendationService for calculated insulin.

Glucose samples use the same display series as the glucose dashboard:
``raw`` = imported CGM; ``normalized`` = fingerstick-calibration display
series (display-only; raw CGM is never mutated). Default is ``normalized``.

Also samples CGM at meal −1h / meal / meal +2h and summarizes where the
calculated dose would retrospectively look better or worse for in-range
(+2h) glucose. That summary is a dosing-direction heuristic only — it does
not simulate counterfactual glucose curves.
"""

from __future__ import annotations

import argparse
import csv
import sys
from bisect import bisect_left
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal
from uuid import UUID

from sqlalchemy import select

from glucotracker.application.episodes import EpisodeQueryService
from glucotracker.application.glucose_dashboard import GlucoseDashboardService
from glucotracker.application.insulin_recommendation import (
    HistoricalInsulinRecommendationService,
)
from glucotracker.infra.db.models import User
from glucotracker.infra.db.session import get_session_factory

# Same TIR display bands as stats_insights / clients (mmol/L).
TIR_LOW = 3.9
TIR_HIGH = 10.0
# Ignore tiny calc vs actual differences (U).
DOSE_EPS = 0.5

GlucoseBand = Literal["low", "in_range", "high", "unknown"]
DoseSide = Literal["actual_less", "actual_more", "similar", "no_calc"]
GlucoseMode = Literal["raw", "normalized"]
Verdict = Literal[
    "calc_better",
    "calc_worse",
    "actual_ok_in_range",
    "both_missed",
    "similar_dose",
    "no_data",
]


class GlucoseSeries:
    """Sorted local-wall CGM series with nearest-point lookup."""

    def __init__(self, timestamps: list[datetime], values: list[float]) -> None:
        pairs = sorted(zip(timestamps, values, strict=True), key=lambda p: p[0])
        self.timestamps = [p[0] for p in pairs]
        self.values = [p[1] for p in pairs]

    @classmethod
    def from_dashboard(
        cls,
        session,
        user_id: UUID,
        local_from: datetime,
        local_to: datetime,
        mode: GlucoseMode,
    ) -> tuple[GlucoseSeries, list[str]]:
        """Build series from GlucoseDashboardService display values."""
        dashboard = GlucoseDashboardService(session, user_id).dashboard(
            local_from,
            local_to,
            mode,
        )
        stamps: list[datetime] = []
        values: list[float] = []
        for point in dashboard.points:
            # display_value already respects mode (raw or normalized).
            if point.display_value is None:
                continue
            stamps.append(point.timestamp)
            values.append(float(point.display_value))
        notes = list(dashboard.notes or [])
        return cls(stamps, values), notes

    def nearest(
        self,
        local_at: datetime,
        window_min: int = 15,
    ) -> float | None:
        """Nearest sample within +/- window_min minutes, else None."""
        if not self.timestamps:
            return None
        idx = bisect_left(self.timestamps, local_at)
        candidates: list[tuple[float, float]] = []
        for i in (idx - 1, idx):
            if 0 <= i < len(self.timestamps):
                delta_s = abs(
                    (self.timestamps[i] - local_at).total_seconds()
                )
                if delta_s <= window_min * 60:
                    candidates.append((delta_s, self.values[i]))
        if not candidates:
            return None
        return min(candidates, key=lambda c: c[0])[1]


def glucose_band(value: float | None) -> GlucoseBand:
    if value is None:
        return "unknown"
    if value < TIR_LOW:
        return "low"
    if value > TIR_HIGH:
        return "high"
    return "in_range"


def dose_side(actual: float, calc: float | None) -> DoseSide:
    if calc is None:
        return "no_calc"
    diff = actual - calc
    if abs(diff) <= DOSE_EPS:
        return "similar"
    if diff < 0:
        return "actual_less"
    return "actual_more"


def classify_verdict(
    side: DoseSide,
    band_plus_2h: GlucoseBand,
) -> Verdict:
    """Heuristic: would calculated dose direction have helped TIR at +2h?"""
    if band_plus_2h == "unknown" or side == "no_calc":
        return "no_data"
    if side == "similar":
        return "similar_dose" if band_plus_2h == "in_range" else "both_missed"
    if band_plus_2h == "in_range":
        return "actual_ok_in_range"

    if side == "actual_less" and band_plus_2h == "high":
        return "calc_better"
    if side == "actual_more" and band_plus_2h == "low":
        return "calc_better"
    if side == "actual_less" and band_plus_2h == "low":
        return "calc_worse"
    if side == "actual_more" and band_plus_2h == "high":
        return "calc_worse"
    return "both_missed"


def glucose_context(
    series: GlucoseSeries,
    meal_at: datetime,
) -> dict[str, float | None]:
    """Sample series around the meal (−1h, at meal, +2h)."""
    g_meal = series.nearest(meal_at, 15)
    g_prev = series.nearest(meal_at - timedelta(hours=1), 20)
    g_plus2 = series.nearest(meal_at + timedelta(hours=2), 20)
    delta_1h = (
        round(g_meal - g_prev, 1)
        if g_meal is not None and g_prev is not None
        else None
    )
    delta_2h = (
        round(g_plus2 - g_meal, 1)
        if g_meal is not None and g_plus2 is not None
        else None
    )
    return {
        "g_meal": g_meal,
        "g_1h": g_prev,
        "g_plus2": g_plus2,
        "delta_1h": delta_1h,
        "delta_2h": delta_2h,
    }


def resolve_user(session, username: str) -> UUID:
    user = session.execute(
        select(User).where(User.username == username)
    ).scalar_one_or_none()
    if user is None:
        raise SystemExit(f"User not found: {username}")
    return user.id


def fmt_num(value: float | None, digits: int = 1, signed: bool = False) -> str:
    if value is None:
        return "—"
    if signed:
        return f"{value:+.{digits}f}"
    return f"{value:.{digits}f}"


def print_episode_list(label: str, items: list[dict], limit: int = 12) -> None:
    print(f"\n{label} ({len(items)}):")
    if not items:
        print("  (none)")
        return
    for r in items[:limit]:
        print(
            f"  {r['date'][5:]} {r['time']}  "
            f"calc={fmt_num(r['calculated_u'])} act={fmt_num(r['actual_u'])} "
            f"A−C={fmt_num(r['diff_actual_minus_calc'], signed=True)}  "
            f"glu@meal={fmt_num(r['glucose_at_meal_mmol'])} "
            f"+2h={fmt_num(r['glucose_plus_2h_mmol'])} "
            f"({r['glucose_plus_2h_band']})  "
            f"{r['title'][:40]}"
        )
    if len(items) > limit:
        print(f"  … +{len(items) - limit} more")


def print_summary(rows: list[dict], glucose_mode: str) -> None:
    comparable = [
        r
        for r in rows
        if r["calculated_u"] is not None
        and r["actual_u"] > 0
        and r["glucose_plus_2h_mmol"] is not None
    ]
    print()
    print("=" * 72)
    print("SUMMARY — calculated vs actual for +2h in-range glucose")
    print(
        f"Glucose series: {glucose_mode} "
        f"(dashboard display_value; TIR {TIR_LOW}–{TIR_HIGH} mmol/L; "
        f"dose tie ±{DOSE_EPS} U)"
    )
    print(
        "Heuristic only: uses dose direction + observed +2h CGM; "
        "does not simulate what glucose would have been under the other dose."
    )
    print("=" * 72)

    by_verdict: dict[str, list[dict]] = defaultdict(list)
    for r in comparable:
        by_verdict[r["verdict"]].append(r)

    n = len(comparable)
    print(f"\nComparable meals (have calc + +2h CGM): {n}/{len(rows)}")

    def pct(k: str) -> str:
        c = len(by_verdict[k])
        return f"{c} ({100 * c / n:.0f}%)" if n else f"{c}"

    print(f"  calc would look better:     {pct('calc_better')}")
    print(f"  calc would look worse:      {pct('calc_worse')}")
    print(f"  actual kept +2h in range:   {pct('actual_ok_in_range')}")
    print(f"  similar dose (±{DOSE_EPS} U):      {pct('similar_dose')}")
    print(f"  similar dose but out:       {pct('both_missed')}")

    bands: dict[str, int] = defaultdict(int)
    for r in rows:
        bands[r["glucose_plus_2h_band"]] += 1
    print("\n+2h glucose bands (all meals):")
    for key in ("low", "in_range", "high", "unknown"):
        print(f"  {key:10} {bands.get(key, 0)}")

    under_high = [
        r
        for r in comparable
        if r["dose_side"] == "actual_less" and r["glucose_plus_2h_band"] == "high"
    ]
    over_low = [
        r
        for r in comparable
        if r["dose_side"] == "actual_more" and r["glucose_plus_2h_band"] == "low"
    ]
    under_low = [
        r
        for r in comparable
        if r["dose_side"] == "actual_less" and r["glucose_plus_2h_band"] == "low"
    ]
    over_high = [
        r
        for r in comparable
        if r["dose_side"] == "actual_more" and r["glucose_plus_2h_band"] == "high"
    ]

    print("\nDirection detail (among comparable):")
    print(
        f"  took LESS than calc → +2h HIGH  (calc may help): "
        f"{len(under_high)}"
    )
    print(
        f"  took MORE than calc → +2h LOW   (calc may help): "
        f"{len(over_low)}"
    )
    print(
        f"  took LESS than calc → +2h LOW   (calc may hurt): "
        f"{len(under_low)}"
    )
    print(
        f"  took MORE than calc → +2h HIGH  (calc may hurt): "
        f"{len(over_high)}"
    )

    print_episode_list(
        "Where calculated looks BETTER for in-range +2h",
        by_verdict["calc_better"],
    )
    print_episode_list(
        "Where calculated looks WORSE for in-range +2h",
        by_verdict["calc_worse"],
    )

    better = len(by_verdict["calc_better"])
    worse = len(by_verdict["calc_worse"])
    print()
    if better + worse == 0:
        print("Net: no clear directional calc vs actual cases.")
    elif better > worse:
        print(
            f"Net: calculated direction favored more often "
            f"({better} better vs {worse} worse)."
        )
    elif worse > better:
        print(
            f"Net: calculated direction favored less often "
            f"({better} better vs {worse} worse)."
        )
    else:
        print(f"Net: tied ({better} better vs {worse} worse).")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user", default="admin2")
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument(
        "--glucose-mode",
        choices=("raw", "normalized"),
        default="normalized",
        help=(
            "CGM series: raw = Nightscout import values; "
            "normalized = fingerstick calibration display series "
            "(same as dashboard mode=normalized). Default: normalized."
        ),
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=None,
        help="Optional CSV output path",
    )
    parser.add_argument(
        "--as-of",
        default=None,
        help="Local wall-clock end datetime ISO (default: now local)",
    )
    args = parser.parse_args()
    glucose_mode: GlucoseMode = args.glucose_mode

    session = get_session_factory()()
    try:
        user_id = resolve_user(session, args.user)
        if args.as_of:
            now_local = datetime.fromisoformat(args.as_of)
        else:
            now_local = datetime.now().replace(microsecond=0)
        start = (now_local - timedelta(days=args.days)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        # One dashboard pass for the whole window (+ buffers for −1h / +2h).
        series_from = start - timedelta(hours=2)
        series_to = now_local + timedelta(hours=3)
        print(
            f"Loading {glucose_mode} glucose series "
            f"{series_from} .. {series_to} …",
            flush=True,
        )
        series, dash_notes = GlucoseSeries.from_dashboard(
            session,
            user_id,
            series_from,
            series_to,
            glucose_mode,
        )
        print(f"Glucose points loaded: {len(series.timestamps)}", flush=True)
        if dash_notes:
            for note in dash_notes[:8]:
                print(f"  dashboard note: {note}", flush=True)

        svc = HistoricalInsulinRecommendationService(session, user_id)
        components = EpisodeQueryService(session, user_id).components(
            start - timedelta(hours=2),
            now_local + timedelta(hours=2),
        )

        rows: list[dict] = []
        for ep in components:
            if not ep.meals:
                continue
            meal_at = min(m.eaten_at for m in ep.meals)
            if meal_at < start or meal_at > now_local:
                continue

            meals_sorted = sorted(ep.meals, key=lambda m: m.eaten_at)
            meal_ids = [m.id for m in meals_sorted]
            titles = " + ".join((m.title or "meal")[:50] for m in meals_sorted)
            carbs = round(sum(float(m.total_carbs_g or 0) for m in meals_sorted), 1)
            kcal = round(sum(float(m.total_kcal or 0) for m in meals_sorted), 0)
            actual = round(
                sum(float(e.insulin_units or 0) for e in ep.insulin),
                2,
            )

            calc = svc.estimate(meal_ids, correction_target_mmol_l=None)
            meal_rec = calc.meal.recommended_units if calc else None
            correction_rec = calc.correction.units if calc else None
            total_rec = calc.total_recommended_units if calc else None
            meal_status = calc.meal.status if calc else None
            correction_status = calc.correction.status if calc else None
            conf = calc.meal.confidence if calc else None
            range_low = calc.meal.range_low_units if calc else None
            range_high = calc.meal.range_high_units if calc else None

            gctx = glucose_context(series, meal_at)
            g_meal = gctx["g_meal"]
            g_1h = gctx["g_1h"]
            g_plus2 = gctx["g_plus2"]
            side = dose_side(actual, total_rec)
            band2 = glucose_band(g_plus2)
            verdict = classify_verdict(side, band2)

            rows.append(
                {
                    "eaten_at": meal_at.isoformat(timespec="seconds"),
                    "date": meal_at.strftime("%Y-%m-%d"),
                    "time": meal_at.strftime("%H:%M"),
                    "title": titles,
                    "n_meals": len(meals_sorted),
                    "carbs_g": carbs,
                    "kcal": int(kcal),
                    "calculated_u": total_rec,
                    "meal_calculated_u": meal_rec,
                    "correction_calculated_u": correction_rec,
                    "calc_range_low_u": range_low,
                    "calc_range_high_u": range_high,
                    "calc_status": meal_status,
                    "correction_status": correction_status,
                    "calc_confidence": conf,
                    "actual_u": actual,
                    "n_insulin_events": len(ep.insulin),
                    "diff_actual_minus_calc": (
                        round(actual - total_rec, 2)
                        if total_rec is not None
                        else None
                    ),
                    "dose_side": side,
                    "glucose_mode": glucose_mode,
                    "glucose_at_meal_mmol": (
                        round(g_meal, 1) if g_meal is not None else None
                    ),
                    "glucose_1h_before_mmol": (
                        round(g_1h, 1) if g_1h is not None else None
                    ),
                    "trend_1h_delta_mmol": gctx["delta_1h"],
                    "glucose_plus_2h_mmol": (
                        round(g_plus2, 1) if g_plus2 is not None else None
                    ),
                    "delta_meal_to_plus_2h_mmol": gctx["delta_2h"],
                    "glucose_plus_2h_band": band2,
                    "verdict": verdict,
                }
            )

        print(
            f"User={args.user}  range={start.date()} .. {now_local.date()}  "
            f"food episodes={len(rows)}  glucose_mode={glucose_mode}"
        )
        print()
        header = (
            f"{'When':<14} {'Meal':>5} {'Corr':>5} {'Total':>5} "
            f"{'Act':>5} {'A-C':>5} "
            f"{'Glu':>5} {'-1h':>5} {'d1h':>5} {'+2h':>5} "
            f"{'band':>8} {'Carbs':>5}  Meal"
        )
        print(header)
        print("-" * (len(header) + 40))
        for r in rows:
            when = f"{r['date'][5:]} {r['time']}"
            print(
                f"{when:<14} "
                f"{fmt_num(r['meal_calculated_u']):>5} "
                f"{fmt_num(r['correction_calculated_u']):>5} "
                f"{fmt_num(r['calculated_u']):>5} "
                f"{fmt_num(r['actual_u']):>5} "
                f"{fmt_num(r['diff_actual_minus_calc'], signed=True):>5} "
                f"{fmt_num(r['glucose_at_meal_mmol']):>5} "
                f"{fmt_num(r['glucose_1h_before_mmol']):>5} "
                f"{fmt_num(r['trend_1h_delta_mmol'], signed=True):>5} "
                f"{fmt_num(r['glucose_plus_2h_mmol']):>5} "
                f"{r['glucose_plus_2h_band']:>8} "
                f"{r['carbs_g']:>5.0f}  "
                f"{r['title'][:40]}"
            )

        with_both = [
            r
            for r in rows
            if r["calculated_u"] is not None and r["actual_u"] > 0
        ]
        print()
        print(f"With both calc+actual: {len(with_both)}/{len(rows)}")
        if with_both:
            diffs = [r["diff_actual_minus_calc"] for r in with_both]
            print(
                "Actual−Calc U: "
                f"mean={sum(diffs)/len(diffs):+.2f}  "
                f"median={sorted(diffs)[len(diffs)//2]:+.2f}  "
                f"min={min(diffs):+.1f}  max={max(diffs):+.1f}"
            )
        statuses: dict[str | None, int] = defaultdict(int)
        for r in rows:
            statuses[r["calc_status"]] += 1
        print("Calc status counts:", dict(statuses))
        correction_statuses: dict[str | None, int] = defaultdict(int)
        for r in rows:
            correction_statuses[r["correction_status"]] += 1
        print("Correction status counts:", dict(correction_statuses))

        print_summary(rows, glucose_mode)

        if args.csv:
            args.csv.parent.mkdir(parents=True, exist_ok=True)
            fieldnames = list(rows[0].keys()) if rows else [
                "eaten_at",
                "date",
                "time",
                "title",
                "n_meals",
                "carbs_g",
                "kcal",
                "calculated_u",
                "meal_calculated_u",
                "correction_calculated_u",
                "calc_range_low_u",
                "calc_range_high_u",
                "calc_status",
                "correction_status",
                "calc_confidence",
                "actual_u",
                "n_insulin_events",
                "diff_actual_minus_calc",
                "dose_side",
                "glucose_mode",
                "glucose_at_meal_mmol",
                "glucose_1h_before_mmol",
                "trend_1h_delta_mmol",
                "glucose_plus_2h_mmol",
                "delta_meal_to_plus_2h_mmol",
                "glucose_plus_2h_band",
                "verdict",
            ]
            with args.csv.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            print(f"\nCSV written: {args.csv}")

        return 0
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
