#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
OPENAPI="$REPO_ROOT/docs/openapi.yaml"

if [ ! -f "$OPENAPI" ]; then
  echo "missing $OPENAPI" >&2
  exit 1
fi

assert_path_marker() {
  path="$1"
  marker="$2"
  if ! awk -v path="  $path:" -v marker="$marker" '
    $0 == path { in_path=1; next }
    in_path && /^  \// { in_path=0 }
    in_path && index($0, marker) { found=1 }
    END { exit found ? 0 : 1 }
  ' "$OPENAPI"; then
    echo "$path is missing $marker" >&2
    exit 1
  fi
}

for path in \
  "/glucose/dashboard" \
  "/fingersticks" \
  "/fingersticks/{fingerstick_id}" \
  "/sensors" \
  "/sensors/{sensor_id}" \
  "/sensors/{sensor_id}/quality" \
  "/sensors/{sensor_id}/recalculate-calibration" \
  "/reports/endocrinologist"; do
  assert_path_marker "$path" "security:"
  assert_path_marker "$path" "x-glucotracker-required-role: gluco"
  assert_path_marker "$path" "x-glucotracker-required-feature: glucose"
done

for path in \
  "/settings/nightscout" \
  "/settings/nightscout/test" \
  "/nightscout/status" \
  "/meals/{meal_id}/sync_nightscout" \
  "/meals/{meal_id}/unsync_nightscout" \
  "/nightscout/sync/today" \
  "/nightscout/day_status" \
  "/nightscout/glucose" \
  "/nightscout/insulin" \
  "/nightscout/events" \
  "/nightscout/latest-reading" \
  "/nightscout/import"; do
  assert_path_marker "$path" "security:"
  assert_path_marker "$path" "x-glucotracker-required-role: gluco"
  assert_path_marker "$path" "x-glucotracker-required-feature: nightscout"
done

for path in "/dashboard/today" "/timeline"; do
  assert_path_marker "$path" "security:"
  assert_path_marker "$path" "x-glucotracker-role-variant: true"
done

assert_component_clean() {
  component="$1"
  if awk -v component="    $component:" '
    $0 == component { in_component=1; next }
    in_component && /^    [A-Za-z0-9_]+:/ { in_component=0 }
    in_component && tolower($0) ~ /(glucose|nightscout|cgm|insulin)/ { found=1 }
    END { exit found ? 0 : 1 }
  ' "$OPENAPI"; then
    echo "$component mentions glucose/Nightscout/CGM/insulin" >&2
    exit 1
  fi
}

assert_component_clean "DashboardTodayResponse"
assert_component_clean "TimelineFoodResponse"
assert_component_clean "FoodEpisodeFoodResponse"

echo "OpenAPI glucose/Nightscout feature markers verified."
