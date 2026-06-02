"""Meta-test: verify every scoped endpoint is covered by isolation tests.

Crawls the OpenAPI spec, finds all paths marked x-glucotracker-scoped: true,
and fails if any of those paths is missing from the known isolation test set.
"""

from __future__ import annotations

import json
from pathlib import Path


def _load_openapi_spec() -> dict:
    spec_path = Path(__file__).parents[2] / "docs" / "openapi.json"
    if spec_path.exists():
        return json.loads(spec_path.read_text(encoding="utf-8"))
    from glucotracker.main import app
    return app.openapi()


ISOLATION_TEST_ENDPOINTS: set[str] = {
    "GET /meals",
    "GET /meals/{meal_id}",
    "POST /meals",
    "PATCH /meals/{meal_id}",
    "DELETE /meals/{meal_id}",
    "POST /meals/{meal_id}/items",
    "PUT /meals/{meal_id}/items",
    "POST /meals/{meal_id}/accept",
    "POST /meals/{meal_id}/discard",
    "GET /meals/{meal_id}/ai_runs",
    "PATCH /meal_items/{item_id}",
    "DELETE /meal_items/{item_id}",
    "POST /meal_items/{item_id}/copy_by_weight",
    "POST /meal_items/{item_id}/remember_product",
    "POST /meals/{meal_id}/reestimate",
    "POST /meals/{meal_id}/apply_estimation_run/{run_id}",
    "POST /meals/{meal_id}/estimate",
    "POST /meals/{meal_id}/estimate_and_save_draft",
    "POST /meals/{meal_id}/photos",
    "DELETE /photos/{photo_id}",
    "GET /photos/{photo_id}/file",
    "GET /patterns",
    "POST /patterns",
    "GET /patterns/search",
    "GET /patterns/{pattern_id}",
    "PATCH /patterns/{pattern_id}",
    "POST /patterns/{pattern_id}/image",
    "GET /patterns/{pattern_id}/image/file",
    "DELETE /patterns/{pattern_id}",
    "GET /dashboard/today",
    "GET /dashboard/range",
    "GET /dashboard/heatmap",
    "GET /dashboard/top_patterns",
    "GET /dashboard/source_breakdown",
    "GET /dashboard/data_quality",
    "GET /glucose/dashboard",
    "POST /fingersticks",
    "GET /fingersticks",
    "PATCH /fingersticks/{fingerstick_id}",
    "DELETE /fingersticks/{fingerstick_id}",
    "POST /sensors",
    "GET /sensors",
    "PATCH /sensors/{sensor_id}",
    "GET /sensors/{sensor_id}/quality",
    "POST /sensors/{sensor_id}/recalculate-calibration",
    "GET /settings/nightscout",
    "PUT /settings/nightscout",
    "POST /settings/nightscout/test",
    "GET /nightscout/status",
    "GET /nightscout/day_status",
    "GET /nightscout/glucose",
    "GET /nightscout/insulin",
    "GET /nightscout/events",
    "GET /nightscout/latest-reading",
    "POST /nightscout/import",
    "POST /nightscout/sync/today",
    "POST /meals/{meal_id}/sync_nightscout",
    "POST /meals/{meal_id}/unsync_nightscout",
    "POST /meals/from-photo",
    "GET /timeline",
    "GET /timeline/insulin-links",
    "PUT /timeline/insulin-links",
    "GET /twin/params",
    "PATCH /twin/params",
    "POST /twin/params/reset",
    "GET /twin/fit/history",
    "GET /twin/curve",
    "GET /twin/data/summary",
    "POST /twin/fit",
    "GET /autocomplete",
    "GET /profile",
    "PUT /profile",
    "POST /activity/sync",
    "GET /activity/balance",
    "GET /activity/balance/range",
    "GET /reports/endocrinologist",
    "POST /admin/recalculate",
    "POST /admin/postprandial/recompute",
    "GET /database/items",
    "GET /products",
    "POST /products",
    "POST /products/from_label",
    "GET /products/search",
    "GET /products/{product_id}",
    "PATCH /products/{product_id}",
    "DELETE /products/{product_id}",
    "POST /products/{product_id}/image",
    "GET /products/{product_id}/image/file",
}


def test_all_scoped_endpoints_covered():
    spec = _load_openapi_spec()
    paths: dict = spec.get("paths", {})
    missing: list[str] = []

    for path, methods in paths.items():
        for method, operation in methods.items():
            if not isinstance(operation, dict):
                continue
            if not operation.get("x-glucotracker-scoped"):
                continue
            key = f"{method.upper()} {path}"
            if key not in ISOLATION_TEST_ENDPOINTS:
                missing.append(key)

    assert not missing, (
        "Scoped endpoints missing from isolation test suite:\n"
        + "\n".join(f"  {m}" for m in sorted(missing))
        + "\n\nAdd tests for these endpoints in test_user_isolation.py "
        "or test_shared_products.py, "
        "and register them in ISOLATION_TEST_ENDPOINTS in test_isolation_meta.py."
    )
