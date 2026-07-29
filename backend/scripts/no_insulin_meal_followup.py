"""Meals with no linked insulin: carbs and delayed boluses/corrections.

Episode grouping has no explicit "correction meal" kind for food without
insulin. This read-only report finds food episodes with 0 linked insulin and
checks whether a rapid bolus arrived soon after (free correction or attached
to a later meal).
"""

from __future__ import annotations

import argparse
import csv
import sys
from bisect import bisect_left
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from glucotracker.application.episodes import EpisodeQueryService
from glucotracker.application.glucose_dashboard import GlucoseDashboardService
from glucotracker.application.nightscout_context import (
    INSULIN_WINDOW_AFTER,
    INSULIN_WINDOW_BEFORE,
    _local_wall_time,
)
from glucotracker.application.on_board.classification import is_rapid_insulin_event
from glucotracker.application.time import utc_instant_from_local_wall
from glucotracker.infra.db.models import NightscoutInsulinEvent, User
from glucotracker.infra.db.session import get_session_factory

CARB_SNACK = 15.0
CARB_MEAL = 30.0
CARB_LARGE = 50.0
SEARCH_AFTER_H = 4.0


def resolve_user(session, username: str) -> UUID:
    user = session.execute(
        select(User).where(User.username == username)
    ).scalar_one_or_none()
    if user is None:
        raise SystemExit(f"User not found: {username}")
    return user.id


def carb_class(carbs: float) -> str:
    if carbs < CARB_SNACK:
        return "small_snack"
    if carbs < CARB_MEAL:
        return "snack"
    if carbs < CARB_LARGE:
        return "meal"
    return "large_meal"


def classify_pattern(first: dict | None) -> str:
    if first is None:
        return "no_bolus_within_4h"
    mins = first["mins_after"]
    linked = first["linked_to_other_food"]
    outside = first["outside_std_window"]
    if mins <= 90 and not outside:
        return "bolus_in_window_but_unlinked"
    if mins <= 180:
        if linked:
            return "delayed_bolus_attached_to_later_meal"
        return "delayed_correction_bolus"
    if linked:
        return "later_bolus_with_next_meal"
    return "late_bolus_3_4h"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user", default="admin2")
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument(
        "--glucose-mode",
        choices=("raw", "normalized"),
        default="normalized",
    )
    parser.add_argument("--csv", type=Path, default=None)
    args = parser.parse_args()

    session = get_session_factory()()
    try:
        user_id = resolve_user(session, args.user)
        now = datetime.now().replace(microsecond=0)
        start = (now - timedelta(days=args.days)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        dash = GlucoseDashboardService(session, user_id).dashboard(
            start - timedelta(hours=2),
            now + timedelta(hours=4),
            args.glucose_mode,
        )
        pairs = sorted(
            [
                (p.timestamp, float(p.display_value))
                for p in dash.points
                if p.display_value is not None
            ],
            key=lambda x: x[0],
        )
        g_ts = [a for a, _ in pairs]
        g_val = [b for _, b in pairs]

        def nearest_g(t: datetime, window_min: int = 20) -> float | None:
            if not g_ts:
                return None
            i = bisect_left(g_ts, t)
            best: tuple[float, float] | None = None
            for j in (i - 1, i):
                if 0 <= j < len(g_ts):
                    d = abs((g_ts[j] - t).total_seconds())
                    if d <= window_min * 60 and (best is None or d < best[0]):
                        best = (d, g_val[j])
            return best[1] if best else None

        ins_rows = (
            session.execute(
                select(NightscoutInsulinEvent)
                .where(
                    NightscoutInsulinEvent.owner_id == user_id,
                    NightscoutInsulinEvent.timestamp
                    >= utc_instant_from_local_wall(start - timedelta(hours=2)),
                    NightscoutInsulinEvent.timestamp
                    <= utc_instant_from_local_wall(now + timedelta(hours=6)),
                    NightscoutInsulinEvent.insulin_units.is_not(None),
                    NightscoutInsulinEvent.insulin_units > 0,
                )
                .order_by(NightscoutInsulinEvent.timestamp.asc())
            )
            .scalars()
            .all()
        )
        rapid: list[dict] = []
        for event in ins_rows:
            if not is_rapid_insulin_event(
                insulin_type=event.insulin_type,
                event_type=event.event_type,
            ):
                continue
            rapid.append(
                {
                    "id": event.id,
                    "at": _local_wall_time(event.timestamp),
                    "u": float(event.insulin_units or 0),
                    "type": event.event_type,
                    "ins_type": event.insulin_type,
                }
            )
        rapid.sort(key=lambda r: r["at"])
        rapid_ts = [r["at"] for r in rapid]

        comps = EpisodeQueryService(session, user_id).components(
            start - timedelta(hours=2),
            now + timedelta(hours=3),
        )

        insulin_to_food_ep: dict = {}
        food_eps = []
        for ep in comps:
            if not ep.meals:
                continue
            meal_at = min(m.eaten_at for m in ep.meals)
            if not (start <= meal_at <= now):
                continue
            food_eps.append(ep)
            ep_key = meal_at.isoformat()
            for ev in ep.insulin:
                insulin_to_food_ep[ev.id] = ep_key

        window_after_min = INSULIN_WINDOW_AFTER.total_seconds() / 60
        rows: list[dict] = []

        for ep in food_eps:
            meal_at = min(m.eaten_at for m in ep.meals)
            act = round(sum(float(e.insulin_units or 0) for e in ep.insulin), 2)
            if act > 0:
                continue

            meals_sorted = sorted(ep.meals, key=lambda m: m.eaten_at)
            carbs = round(sum(float(m.total_carbs_g or 0) for m in meals_sorted), 1)
            titles = " + ".join((m.title or "?")[:40] for m in meals_sorted)
            g0 = nearest_g(meal_at, 15)
            g2 = nearest_g(meal_at + timedelta(hours=2), 20)

            i = bisect_left(rapid_ts, meal_at)
            later: list[dict] = []
            for r in rapid[i:]:
                mins = (r["at"] - meal_at).total_seconds() / 60
                if mins < 0:
                    continue
                if mins > SEARCH_AFTER_H * 60:
                    break
                later.append(
                    {
                        **r,
                        "mins_after": round(mins, 0),
                        "linked_to_other_food": r["id"] in insulin_to_food_ep,
                        "outside_std_window": mins > window_after_min,
                        "g_at_bolus": nearest_g(r["at"], 15),
                    }
                )

            first = later[0] if later else None
            pattern = classify_pattern(first)
            rows.append(
                {
                    "eaten_at": meal_at.isoformat(timespec="seconds"),
                    "date": meal_at.strftime("%Y-%m-%d"),
                    "time": meal_at.strftime("%H:%M"),
                    "title": titles,
                    "carbs_g": carbs,
                    "carb_class": carb_class(carbs),
                    "glucose_at_meal_mmol": (
                        round(g0, 1) if g0 is not None else None
                    ),
                    "glucose_plus_2h_mmol": (
                        round(g2, 1) if g2 is not None else None
                    ),
                    "pattern": pattern,
                    "first_bolus_mins": (
                        int(first["mins_after"]) if first else None
                    ),
                    "first_bolus_u": first["u"] if first else None,
                    "first_bolus_g": (
                        round(first["g_at_bolus"], 1)
                        if first and first["g_at_bolus"] is not None
                        else None
                    ),
                    "first_bolus_linked_to_other_food": (
                        first["linked_to_other_food"] if first else None
                    ),
                    "insulin_u_within_2h": round(
                        sum(x["u"] for x in later if x["mins_after"] <= 120),
                        2,
                    ),
                    "insulin_u_within_4h": round(
                        sum(x["u"] for x in later if x["mins_after"] <= 240),
                        2,
                    ),
                    "n_bolus_within_4h": len(later),
                    "later_detail": "; ".join(
                        (
                            f"+{int(x['mins_after'])}m {x['u']:.1f}U"
                            + (
                                "->other_meal"
                                if x["linked_to_other_food"]
                                else " free"
                            )
                            + (
                                f" g={x['g_at_bolus']:.1f}"
                                if x["g_at_bolus"] is not None
                                else ""
                            )
                        )
                        for x in later[:4]
                    ),
                }
            )

        rows.sort(key=lambda r: r["eaten_at"])
        n_food = len(food_eps)
        n = len(rows)

        print(
            f"User={args.user}  days={args.days}  "
            f"food_eps={n_food}  no_linked_insulin={n}"
        )
        print(
            f"Std auto-link window: -{INSULIN_WINDOW_BEFORE} .. "
            f"+{INSULIN_WINDOW_AFTER}"
        )
        print(f"Glucose mode: {args.glucose_mode}")
        print(f"Carb class counts: {dict(Counter(r['carb_class'] for r in rows))}")
        print(f"Pattern counts: {dict(Counter(r['pattern'] for r in rows))}")
        print()

        heavy = [r for r in rows if r["carbs_g"] >= CARB_MEAL]
        print(
            f"=== No-insulin episodes with carbs >= {CARB_MEAL:g}g "
            f"({len(heavy)}) — likely under-bolused food ==="
        )
        header = (
            f"{'When':<14} {'Carb':>5} {'Glu':>5} {'+2h':>5} "
            f"{'1stBol':>7} {'U':>5} {'gBol':>5}  pattern"
        )
        print(header)
        print("-" * 100)
        for r in heavy:
            bol = (
                f"+{r['first_bolus_mins']}m"
                if r["first_bolus_mins"] is not None
                else "—"
            )
            u = (
                f"{r['first_bolus_u']:.1f}"
                if r["first_bolus_u"] is not None
                else "—"
            )
            gb = (
                f"{r['first_bolus_g']:.1f}"
                if r["first_bolus_g"] is not None
                else "—"
            )
            g0 = (
                f"{r['glucose_at_meal_mmol']:.1f}"
                if r["glucose_at_meal_mmol"] is not None
                else "—"
            )
            g2 = (
                f"{r['glucose_plus_2h_mmol']:.1f}"
                if r["glucose_plus_2h_mmol"] is not None
                else "—"
            )
            when = f"{r['date'][5:]} {r['time']}"
            print(
                f"{when:<14} {r['carbs_g']:>5.0f} {g0:>5} {g2:>5} "
                f"{bol:>7} {u:>5} {gb:>5}  {r['pattern']}"
            )
            print(f"               {r['title'][:72]}")
            if r["later_detail"]:
                print(f"               next: {r['later_detail']}")
            print()

        print("=== All no-insulin food episodes ===")
        print(
            f"{'When':<14} {'Carb':>5} {'class':>11} {'Glu':>5} {'+2h':>5} "
            f"{'bol+m':>6} {'U4h':>5}  pattern"
        )
        print("-" * 100)
        for r in rows:
            bolm = (
                f"+{r['first_bolus_mins']}"
                if r["first_bolus_mins"] is not None
                else "—"
            )
            g0 = (
                f"{r['glucose_at_meal_mmol']:.1f}"
                if r["glucose_at_meal_mmol"] is not None
                else "—"
            )
            g2 = (
                f"{r['glucose_plus_2h_mmol']:.1f}"
                if r["glucose_plus_2h_mmol"] is not None
                else "—"
            )
            when = f"{r['date'][5:]} {r['time']}"
            print(
                f"{when:<14} {r['carbs_g']:>5.0f} {r['carb_class']:>11} "
                f"{g0:>5} {g2:>5} {bolm:>6} {r['insulin_u_within_4h']:>5.1f}  "
                f"{r['pattern']}"
            )
            print(f"               {r['title'][:70]}")

        # Summary
        with_bolus = [r for r in rows if r["first_bolus_mins"] is not None]
        heavy_bolus_3h = [
            r
            for r in heavy
            if r["first_bolus_mins"] is not None and r["first_bolus_mins"] <= 180
        ]
        pure_corr = [
            r for r in rows if r["pattern"] == "delayed_correction_bolus"
        ]
        attached = [
            r
            for r in rows
            if r["pattern"] == "delayed_bolus_attached_to_later_meal"
        ]
        no_bolus = [r for r in rows if r["first_bolus_mins"] is None]
        high_carb_no_bolus = [r for r in no_bolus if r["carbs_g"] >= CARB_MEAL]

        print()
        print("=== Summary ===")
        print(f"No-insulin food episodes: {n}/{n_food}")
        print(
            f"  any rapid bolus within 4h: {len(with_bolus)} "
            f"({100 * len(with_bolus) / n:.0f}%)"
            if n
            else "  any rapid bolus within 4h: 0"
        )
        print(
            f"  carbs >= {CARB_MEAL:g}g (meal-sized without bolus link): "
            f"{len(heavy)}"
        )
        print(
            f"    of those, bolus within 3h: {len(heavy_bolus_3h)}/"
            f"{len(heavy)}"
        )
        print(f"  delayed free correction bolus (90m–3h): {len(pure_corr)}")
        print(
            f"  delayed bolus attributed to a LATER food episode: "
            f"{len(attached)}"
        )
        print(f"  truly no bolus in 4h: {len(no_bolus)}")
        if high_carb_no_bolus:
            print(
                f"  HIGH carbs and no bolus at all in 4h: "
                f"{len(high_carb_no_bolus)}"
            )
            for r in high_carb_no_bolus:
                print(
                    f"    {r['date'][5:]} {r['time']}  {r['carbs_g']:.0f}g  "
                    f"g={r['glucose_at_meal_mmol']} +2h={r['glucose_plus_2h_mmol']}  "
                    f"{r['title'][:50]}"
                )

        if heavy_bolus_3h:
            delays = [r["first_bolus_mins"] for r in heavy_bolus_3h]
            units = [r["insulin_u_within_4h"] for r in heavy_bolus_3h]
            print(
                f"\nHeavy (>= {CARB_MEAL:g}g) + bolus <=3h: "
                f"median delay {sorted(delays)[len(delays) // 2]}m, "
                f"median insulin in 4h {sorted(units)[len(units) // 2]:.1f} U"
            )

        # Answer framing
        print()
        print("=== Readout ===")
        print(
            "Episode model only links insulin in "
            f"[-{int(INSULIN_WINDOW_BEFORE.total_seconds()//60)}m, "
            f"+{int(window_after_min)}m] (or manual links). "
            "There is no 'correction meal' food kind — insulin-only "
            "episodes are kind=correction, food with no insulin is food_only."
        )
        if heavy:
            delayed_heavy = [
                r
                for r in heavy
                if r["pattern"]
                in {
                    "delayed_correction_bolus",
                    "delayed_bolus_attached_to_later_meal",
                    "later_bolus_with_next_meal",
                    "late_bolus_3_4h",
                }
            ]
            print(
                f"Of {len(heavy)} meal-sized no-insulin episodes, "
                f"{len(delayed_heavy)} had a bolus later (likely delayed "
                f"coverage / correction not attached to the meal)."
            )

        if args.csv:
            args.csv.parent.mkdir(parents=True, exist_ok=True)
            with args.csv.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else [])
                if rows:
                    writer.writeheader()
                    writer.writerows(rows)
            print(f"\nCSV written: {args.csv}")

        return 0
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
