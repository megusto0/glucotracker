#!/data/data/com.termux/files/usr/bin/bash
# Sync Gadgetbridge activity export to glucotracker.

set -euo pipefail

# Configurable via environment:
#   BACKEND_URL=http://host:8000 GB_DB=/path/to/Gadgetbridge ~/bin/gb-sync.sh
#   ~/bin/gb-sync.sh                     # today
#   ~/bin/gb-sync.sh 2026-05-01          # one day
#   ~/bin/gb-sync.sh --backfill 7        # last 7 days, including today
BACKEND_URL="${BACKEND_URL:-http://192.168.3.6:8000}"
BACKEND_TOKEN="${BACKEND_TOKEN:-dev}"
GB_DB="${GB_DB:-$HOME/gb-export/database/Gadgetbridge}"
ACTIVITY_TABLE="${ACTIVITY_TABLE:-}"
HEART_RATE_TABLE="${HEART_RATE_TABLE:-${TABLE_HR:-}}"
RESTING_HEART_RATE_TABLE="${RESTING_HEART_RATE_TABLE:-}"
CURL_MAX_TIME="${CURL_MAX_TIME:-15}"
EXPORT_MAX_AGE_MIN="${EXPORT_MAX_AGE_MIN:-5}"
TRIGGER_EXPORT="${TRIGGER_EXPORT:-1}"
USER_WEIGHT_KG="${USER_WEIGHT_KG:-82}"
USER_HEIGHT_CM="${USER_HEIGHT_CM:-180}"
USER_AGE="${USER_AGE:-25}"
USER_SEX="${USER_SEX:-male}"
INTENSITY_MOVE_THRESHOLD="${INTENSITY_MOVE_THRESHOLD:-30}"
NO_MOVE_FACTOR="${NO_MOVE_FACTOR:-0.35}"
FLEX_HR_DELTA="${FLEX_HR_DELTA:-15}"
NO_MOVE_HR_EXTRA_DELTA="${NO_MOVE_HR_EXTRA_DELTA:-8}"
MAX_NO_MOVE_SHARE="${MAX_NO_MOVE_SHARE:-0.35}"
KCAL_PER_MIN_CAP="${KCAL_PER_MIN_CAP:-12}"

log() {
    printf '%s\n' "$*"
}

sql() {
    sqlite3 "$GB_DB" "$1"
}

has_table() {
    [ "$(sql "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='$1';")" -gt 0 ]
}

has_column() {
    [ "$(sql "SELECT COUNT(*) FROM pragma_table_info('$1') WHERE name='$2';")" -gt 0 ]
}

timestamp_expr() {
    local table="$1"
    local max_ts

    max_ts="$(sql "SELECT COALESCE(MAX(TIMESTAMP),0) FROM $table;" 2>/dev/null || printf '0')"
    if [ "${max_ts:-0}" -gt 9999999999 ]; then
        printf 'TIMESTAMP / 1000'
    else
        printf 'TIMESTAMP'
    fi
}

trigger_export() {
    [ "$TRIGGER_EXPORT" = "1" ] || return 0

    if [ ! -f "$GB_DB" ] || [ -n "$(find "$GB_DB" -mmin +"$EXPORT_MAX_AGE_MIN" 2>/dev/null)" ]; then
        log "Triggering Gadgetbridge export..."
        am broadcast -a nodomain.freeyourgadget.gadgetbridge.command.TRIGGER_EXPORT >/dev/null 2>&1 || true
        sleep 3
    fi
}

json_number_or_null() {
    if [ -n "$1" ]; then
        printf '%s' "$1"
    else
        printf 'null'
    fi
}

metric_for_table() {
    local table="$1"
    local day_start="$2"
    local day_end="$3"
    local hr_expr="''"

    if has_column "$table" HEART_RATE; then
        hr_expr="COALESCE(ROUND(AVG(NULLIF(HEART_RATE,0)),1),'')"
    fi

    sql "SELECT COUNT(*), COALESCE(SUM(STEPS),0), $hr_expr FROM $table WHERE TIMESTAMP >= $day_start AND TIMESTAMP < $day_end;"
}

heart_metrics_for_table() {
    local table="$1"
    local day_start="$2"
    local day_end="$3"
    local night_end=$((day_start + 25200))
    local avg rest ts_expr

    ts_expr="$(timestamp_expr "$table")"

    avg="$(sql "SELECT COALESCE(ROUND(AVG(NULLIF(HEART_RATE,0)),1),'') FROM $table WHERE $ts_expr >= $day_start AND $ts_expr < $day_end;")"
    rest="$(sql "SELECT COALESCE(ROUND(MIN(NULLIF(HEART_RATE,0)),1),'') FROM $table WHERE $ts_expr >= $day_start AND $ts_expr < $night_end;")"
    printf '%s|%s\n' "$avg" "$rest"
}

resting_hr_for_table() {
    local table="$1"
    local day_start="$2"
    local day_end="$3"
    local ts_expr

    ts_expr="$(timestamp_expr "$table")"
    sql "SELECT COALESCE(ROUND(AVG(NULLIF(HEART_RATE,0)),1),'') FROM $table WHERE $ts_expr >= $day_start AND $ts_expr < $day_end;"
}

pick_heart_rate_table() {
    local day_start="$1"
    local day_end="$2"
    local table metrics avg rest

    if [ -n "$HEART_RATE_TABLE" ]; then
        if ! has_table "$HEART_RATE_TABLE"; then
            log "ERROR: HEART_RATE_TABLE=$HEART_RATE_TABLE does not exist in $GB_DB" >&2
            exit 1
        fi
        has_column "$HEART_RATE_TABLE" TIMESTAMP || return 1
        has_column "$HEART_RATE_TABLE" HEART_RATE || return 1
        printf '%s\n' "$HEART_RATE_TABLE"
        return
    fi

    while IFS= read -r table; do
        has_column "$table" TIMESTAMP || continue
        has_column "$table" HEART_RATE || continue
        case "$table" in
            *RESTING*|*Resting*) continue ;;
        esac
        metrics="$(heart_metrics_for_table "$table" "$day_start" "$day_end" 2>/dev/null || true)"
        avg="$(printf '%s' "$metrics" | cut -d'|' -f1)"
        rest="$(printf '%s' "$metrics" | cut -d'|' -f2)"
        if [ -n "$avg" ] || [ -n "$rest" ]; then
            printf '%s\n' "$table"
            return
        fi
    done <<EOF
$(sql "SELECT name FROM sqlite_master WHERE type='table' ORDER BY CASE WHEN name LIKE '%ACTIVITY_SAMPLE' THEN 0 WHEN name LIKE '%HeartRate%' THEN 1 WHEN name LIKE '%HEART%' THEN 2 WHEN name LIKE '%HR%' THEN 3 WHEN name LIKE '%RESTING%' THEN 98 ELSE 99 END, name;")
EOF

    return 1
}

pick_resting_heart_rate_table() {
    local day_start="$1"
    local day_end="$2"
    local table value

    if [ -n "$RESTING_HEART_RATE_TABLE" ]; then
        if ! has_table "$RESTING_HEART_RATE_TABLE"; then
            log "ERROR: RESTING_HEART_RATE_TABLE=$RESTING_HEART_RATE_TABLE does not exist in $GB_DB" >&2
            exit 1
        fi
        has_column "$RESTING_HEART_RATE_TABLE" TIMESTAMP || return 1
        has_column "$RESTING_HEART_RATE_TABLE" HEART_RATE || return 1
        printf '%s\n' "$RESTING_HEART_RATE_TABLE"
        return
    fi

    while IFS= read -r table; do
        has_column "$table" TIMESTAMP || continue
        has_column "$table" HEART_RATE || continue
        value="$(resting_hr_for_table "$table" "$day_start" "$day_end" 2>/dev/null || true)"
        if [ -n "$value" ]; then
            printf '%s\n' "$table"
            return
        fi
    done <<EOF
$(sql "SELECT name FROM sqlite_master WHERE type='table' ORDER BY CASE WHEN name LIKE '%RESTING%' THEN 0 WHEN name LIKE '%HeartRateRest%' THEN 1 WHEN name LIKE '%HeartRate%' THEN 2 WHEN name LIKE '%HEART%' THEN 3 ELSE 99 END, name;")
EOF

    return 1
}

pick_activity_table() {
    local day_start="$1"
    local day_end="$2"
    local table metrics count steps
    local fallback_table=""

    if [ -n "$ACTIVITY_TABLE" ]; then
        if ! has_table "$ACTIVITY_TABLE"; then
            log "ERROR: ACTIVITY_TABLE=$ACTIVITY_TABLE does not exist in $GB_DB" >&2
            exit 1
        fi
        printf '%s\n' "$ACTIVITY_TABLE"
        return
    fi

    while IFS= read -r table; do
        has_column "$table" TIMESTAMP || continue
        has_column "$table" STEPS || continue
        [ -n "$fallback_table" ] || fallback_table="$table"
        metrics="$(metric_for_table "$table" "$day_start" "$day_end" 2>/dev/null || true)"
        count="${metrics%%|*}"
        steps="$(printf '%s' "$metrics" | cut -d'|' -f2)"
        if [ "${count:-0}" -gt 0 ] && [ "${steps:-0}" -gt 0 ]; then
            printf '%s\n' "$table"
            return
        fi
    done <<EOF
$(sql "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%ACTIVITY_SAMPLE' ORDER BY CASE name WHEN 'HUAMI_EXTENDED_ACTIVITY_SAMPLE' THEN 0 WHEN 'MI_BAND_ACTIVITY_SAMPLE' THEN 1 WHEN 'XIAOMI_ACTIVITY_SAMPLE' THEN 2 ELSE 99 END, name;")
EOF

    if [ -n "$fallback_table" ]; then
        printf '%s\n' "$fallback_table"
        return
    fi

    return 1
}

sum_calories() {
    local table="$1"
    local day_start="$2"
    local day_end="$3"
    local col value

    # 1. Try XIAOMI_DAILY_SUMMARY_SAMPLE for device-calculated calories.
    if has_table XIAOMI_DAILY_SUMMARY_SAMPLE; then
        value="$(sql "SELECT COALESCE(CALORIES,0) FROM XIAOMI_DAILY_SUMMARY_SAMPLE WHERE TIMESTAMP >= $day_start AND TIMESTAMP < $day_end AND COALESCE(CALORIES,0) > 0 LIMIT 1;")"
        if [ -n "$value" ] && [ "$value" != "0" ]; then
            printf '%s\n' "$value"
            return
        fi
    fi

    # 2. Try per-minute active calories if Xiaomi activity samples exist.
    if has_table XIAOMI_ACTIVITY_SAMPLE && has_column XIAOMI_ACTIVITY_SAMPLE ACTIVE_CALORIES; then
        value="$(sql "SELECT COALESCE(SUM(NULLIF(ACTIVE_CALORIES,-1)),0) FROM XIAOMI_ACTIVITY_SAMPLE WHERE TIMESTAMP >= $day_start AND TIMESTAMP < $day_end AND ACTIVE_CALORIES >= 0;")"
        if [ -n "$value" ] && [ "$value" != "0" ]; then
            printf '%s\n' "$value"
            return
        fi
    fi

    # 3. Fall back to calorie-like columns on the selected table.
    for col in CALORIES ACTIVE_CALORIES CALORIES_BURNT; do
        if has_column "$table" "$col"; then
            value="$(sql "SELECT COALESCE(SUM(NULLIF($col,-1)),0) FROM $table WHERE TIMESTAMP >= $day_start AND TIMESTAMP < $day_end;")"
            if [ -n "$value" ] && [ "$value" != "0" ]; then
                printf '%s\n' "$value"
                return
            fi
        fi
    done

    # 4. Estimate active kcal from HR when the DB has no explicit calories.
    # Keytel-style formula, converted to active kcal/min by subtracting BMR/min.
    if has_column "$table" HEART_RATE; then
        local bmr_per_min hr_coeff weight_coeff offset
        if [ "$USER_SEX" = "male" ]; then
            bmr_per_min="$(awk -v w="$USER_WEIGHT_KG" -v h="$USER_HEIGHT_CM" -v a="$USER_AGE" 'BEGIN { printf "%.4f", (10*w + 6.25*h - 5*a + 5) / 1440 }')"
            hr_coeff="0.6309"
            weight_coeff="0.1988"
            offset="55.0969"
        else
            bmr_per_min="$(awk -v w="$USER_WEIGHT_KG" -v h="$USER_HEIGHT_CM" -v a="$USER_AGE" 'BEGIN { printf "%.4f", (10*w + 6.25*h - 5*a - 161) / 1440 }')"
            hr_coeff="0.6309"
            weight_coeff="0.1293"
            offset="20.4022"
        fi

        value="$(sql "
            SELECT ROUND(COALESCE(SUM(
                CASE WHEN HEART_RATE > 40 THEN
                    CASE WHEN ($USER_AGE * 0.2017 + $USER_WEIGHT_KG * $weight_coeff + HEART_RATE * $hr_coeff - $offset) / 4.184 > $bmr_per_min
                        THEN ($USER_AGE * 0.2017 + $USER_WEIGHT_KG * $weight_coeff + HEART_RATE * $hr_coeff - $offset) / 4.184 - $bmr_per_min
                        ELSE 0 END
                    ELSE 0 END
            ), 0), 1)
            FROM $table WHERE TIMESTAMP >= $day_start AND TIMESTAMP < $day_end;
        " 2>/dev/null || true)"

        if [ -n "$value" ] && [ "$value" != "0" ] && [ "$value" != "0.0" ]; then
            printf '%s\n' "$value"
            return
        fi
    fi

    printf '\n'
}

active_minutes() {
    local table="$1"
    local day_start="$2"
    local day_end="$3"

    if has_column "$table" RAW_INTENSITY; then
        sql "SELECT COUNT(*) FROM $table WHERE TIMESTAMP >= $day_start AND TIMESTAMP < $day_end AND RAW_INTENSITY > 30;"
    else
        printf '0\n'
    fi
}

post_payload() {
    local payload="$1"
    local tmp_body curl_exit http_status response_body
    local auth_args=()

    if [ -n "$BACKEND_TOKEN" ]; then
        auth_args=(-H "Authorization: Bearer $BACKEND_TOKEN")
    fi

    tmp_body="$(mktemp)"
    curl_exit=0
    http_status="$(curl -sS -o "$tmp_body" -w "%{http_code}" -X POST \
        --connect-timeout 5 \
        --max-time "$CURL_MAX_TIME" \
        "$BACKEND_URL/activity/sync" \
        -H "Content-Type: application/json" \
        "${auth_args[@]}" \
        -d "$payload")" || curl_exit=$?
    response_body="$(cat "$tmp_body")"
    rm -f "$tmp_body"

    log "  HTTP status: $http_status"
    log "  Curl exit: $curl_exit"
    log "  Response: $response_body"

    case "$http_status" in
        2*) [ "$curl_exit" -eq 0 ] ;;
        *) return 1 ;;
    esac
}

sync_day() {
    local day="$1"
    local day_start day_end table metrics sample_count steps hr_avg hr_rest
    local heart_table resting_hr_table heart_metrics calories active_min payload
    local hr_samples=0 hr_active_min=0 kcal_hr_active=0 kcal_steps_est=0 kcal_no_move_hr=0
    local flex_hr=0 confidence="none"

    day_start="$(date -d "$day 00:00:00" +%s)"
    day_end=$((day_start + 86400))
    if ! table="$(pick_activity_table "$day_start" "$day_end")"; then
        log "ERROR: no activity table with TIMESTAMP and STEPS columns found" >&2
        return 1
    fi
    metrics="$(metric_for_table "$table" "$day_start" "$day_end")"
    sample_count="$(printf '%s' "$metrics" | cut -d'|' -f1)"
    steps="$(printf '%s' "$metrics" | cut -d'|' -f2)"
    hr_avg="$(printf '%s' "$metrics" | cut -d'|' -f3)"
    hr_rest=""
    heart_table=""
    resting_hr_table=""
    if heart_table="$(pick_heart_rate_table "$day_start" "$day_end" 2>/dev/null)"; then
        heart_metrics="$(heart_metrics_for_table "$heart_table" "$day_start" "$day_end")"
        hr_avg="$(printf '%s' "$heart_metrics" | cut -d'|' -f1)"
        hr_rest="$(printf '%s' "$heart_metrics" | cut -d'|' -f2)"
    fi
    if resting_hr_table="$(pick_resting_heart_rate_table "$day_start" "$day_end" 2>/dev/null)"; then
        hr_rest="$(resting_hr_for_table "$resting_hr_table" "$day_start" "$day_end" 2>/dev/null || true)"
    fi
    calories="$(sum_calories "$table" "$day_start" "$day_end")"
    active_min="$(active_minutes "$table" "$day_start" "$day_end")"

    if [ -z "$calories" ] || [ "$calories" = "0" ]; then
        calories="0"
    fi

    if has_column "$table" HEART_RATE && has_column "$table" RAW_INTENSITY; then
        local bmr_per_min hr_coeff weight_coeff offset hr_rest_val hybrid kcal_from_hr no_move_hr_floor

        if [ "$USER_SEX" = "male" ]; then
            bmr_per_min="$(awk -v w="$USER_WEIGHT_KG" -v h="$USER_HEIGHT_CM" -v a="$USER_AGE" 'BEGIN { printf "%.4f", (10*w + 6.25*h - 5*a + 5) / 1440 }')"
            hr_coeff="0.6309"
            weight_coeff="0.1988"
            offset="55.0969"
        else
            bmr_per_min="$(awk -v w="$USER_WEIGHT_KG" -v h="$USER_HEIGHT_CM" -v a="$USER_AGE" 'BEGIN { printf "%.4f", (10*w + 6.25*h - 5*a - 161) / 1440 }')"
            hr_coeff="0.6309"
            weight_coeff="0.1293"
            offset="20.4022"
        fi

        hr_rest_val="${hr_rest:-60}"
        flex_hr="$(awk -v r="$hr_rest_val" -v d="$FLEX_HR_DELTA" 'BEGIN { printf "%.0f", r + d }')"
        no_move_hr_floor="$(awk -v f="$flex_hr" -v d="$NO_MOVE_HR_EXTRA_DELTA" 'BEGIN { printf "%.0f", f + d }')"

        hybrid="$(sql "
            SELECT
                SUM(CASE WHEN HEART_RATE > 40 THEN 1 ELSE 0 END),
                SUM(CASE WHEN HEART_RATE >= $flex_hr AND (STEPS > 0 OR RAW_INTENSITY > $INTENSITY_MOVE_THRESHOLD) THEN 1 ELSE 0 END),
                ROUND(COALESCE(SUM(
                    CASE WHEN HEART_RATE >= $flex_hr AND (STEPS > 0 OR RAW_INTENSITY > $INTENSITY_MOVE_THRESHOLD) THEN
                        CASE WHEN ($USER_AGE * 0.2017 + $USER_WEIGHT_KG * $weight_coeff + HEART_RATE * $hr_coeff - $offset) / 4.184 > $bmr_per_min
                            THEN ($USER_AGE * 0.2017 + $USER_WEIGHT_KG * $weight_coeff + HEART_RATE * $hr_coeff - $offset) / 4.184 - $bmr_per_min
                            ELSE 0 END
                    ELSE 0 END
                ), 0), 1),
                ROUND(COALESCE(SUM(
                    CASE WHEN HEART_RATE >= $no_move_hr_floor AND STEPS = 0 AND RAW_INTENSITY <= $INTENSITY_MOVE_THRESHOLD THEN
                        CASE WHEN ($USER_AGE * 0.2017 + $USER_WEIGHT_KG * $weight_coeff + HEART_RATE * $hr_coeff - $offset) / 4.184 > $bmr_per_min
                            THEN (($USER_AGE * 0.2017 + $USER_WEIGHT_KG * $weight_coeff + HEART_RATE * $hr_coeff - $offset) / 4.184 - $bmr_per_min) * $NO_MOVE_FACTOR
                            ELSE 0 END
                    ELSE 0 END
                ), 0), 1)
            FROM $table WHERE TIMESTAMP >= $day_start AND TIMESTAMP < $day_end;
        " 2>/dev/null || true)"

        hr_samples="$(printf '%s' "$hybrid" | cut -d'|' -f1)"
        hr_active_min="$(printf '%s' "$hybrid" | cut -d'|' -f2)"
        kcal_hr_active="$(printf '%s' "$hybrid" | cut -d'|' -f3)"
        kcal_no_move_hr="$(printf '%s' "$hybrid" | cut -d'|' -f4)"

        hr_samples="${hr_samples:-0}"
        hr_active_min="${hr_active_min:-0}"
        kcal_hr_active="${kcal_hr_active:-0}"
        kcal_no_move_hr="${kcal_no_move_hr:-0}"
        kcal_no_move_hr="$(awk -v nm="$kcal_no_move_hr" -v hr="$kcal_hr_active" -v share="$MAX_NO_MOVE_SHARE" 'BEGIN { cap = hr * share; if (nm > cap) nm = cap; printf "%.1f", nm }')"

        # Cap HR active kcal at KCAL_PER_MIN_CAP * minutes
        local hr_active_cap
        hr_active_cap="$(awk -v min="$hr_active_min" -v cap="$KCAL_PER_MIN_CAP" 'BEGIN { printf "%.1f", min * cap }')"
        kcal_hr_active="$(awk -v val="$kcal_hr_active" -v cap="$hr_active_cap" 'BEGIN { printf "%.1f", (val > cap) ? cap : val }')"

        kcal_steps_est="$(awk -v s="$steps" -v w="$USER_WEIGHT_KG" -v stride=0.72 'BEGIN { printf "%.1f", w * (s * stride / 1000) * 0.6 }')"
        kcal_from_hr="$kcal_hr_active"
        calories="$(awk -v hr="$kcal_from_hr" -v st="$kcal_steps_est" -v nm="$kcal_no_move_hr" 'BEGIN { printf "%.1f", ((hr > st) ? hr : st) + nm }')"

        if [ "${hr_active_min:-0}" -gt 60 ] && [ "${steps:-0}" -gt 1000 ]; then
            confidence="high"
        elif [ "${hr_active_min:-0}" -gt 30 ] && [ "${steps:-0}" -gt 500 ]; then
            confidence="medium"
        else
            confidence="low"
        fi
    fi

    payload="$(printf '{"date":"%s","steps":%s,"kcal_burned":%s,"active_minutes":%s,"source":"gadgetbridge","heart_rate_avg":%s,"heart_rate_rest":%s,"hr_samples":%s,"hr_active_minutes":%s,"kcal_hr_active":%s,"kcal_steps":%s,"kcal_no_move_hr":%s,"calorie_confidence":"%s"}' \
        "$day" "$steps" "$calories" "$active_min" "$(json_number_or_null "$hr_avg")" "$(json_number_or_null "$hr_rest")" \
        "$hr_samples" "$hr_active_min" "$kcal_hr_active" "$kcal_steps_est" "$kcal_no_move_hr" "$confidence")"

    log "Reading activity for $day from Gadgetbridge..."
    log "  DB: $GB_DB"
    log "  Backend: $BACKEND_URL"
    log "  Epoch range: $day_start..$day_end"
    log "  Table: $table"
    if [ -n "$heart_table" ] && [ "$heart_table" != "$table" ]; then
        log "  Heart table: $heart_table"
    fi
    if [ -n "$resting_hr_table" ] && [ "$resting_hr_table" != "$heart_table" ]; then
        log "  Resting HR table: $resting_hr_table"
    fi
    log "  Samples: $sample_count"
    log "  Steps: $steps"
    log "  Calories: $calories (HR active: $kcal_hr_active, Steps: $kcal_steps_est, HR no-move: $kcal_no_move_hr)"
    log "  Active minutes: $active_min (HR active: $hr_active_min)"
    log "  HR avg: ${hr_avg:-null}, rest: ${hr_rest:-null}, flex: $flex_hr, no-move HR floor: ${no_move_hr_floor:-0}, no-move factor: $NO_MOVE_FACTOR"
    log "  Confidence: $confidence"
    log "  Payload: $payload"

    if post_payload "$payload"; then
        log "Done."
        return 0
    fi

    log "ERROR: sync failed" >&2
    return 1
}

usage() {
    cat <<EOF
Usage:
  gb-sync.sh [YYYY-MM-DD]
  gb-sync.sh --backfill [DAYS]

Environment:
  BACKEND_URL, BACKEND_TOKEN, GB_DB, ACTIVITY_TABLE, HEART_RATE_TABLE,
  RESTING_HEART_RATE_TABLE,
  CURL_MAX_TIME, EXPORT_MAX_AGE_MIN, TRIGGER_EXPORT=0|1,
  USER_WEIGHT_KG, USER_HEIGHT_CM, USER_AGE, USER_SEX,
  INTENSITY_MOVE_THRESHOLD, NO_MOVE_FACTOR, FLEX_HR_DELTA,
  NO_MOVE_HR_EXTRA_DELTA, MAX_NO_MOVE_SHARE
EOF
}

main() {
    local ok fail days i day

    case "${1:-}" in
        -h|--help)
            usage
            ;;
        --backfill)
            trigger_export
            if [ ! -f "$GB_DB" ]; then
                log "ERROR: Gadgetbridge DB not found at $GB_DB" >&2
                exit 1
            fi
            days="${2:-7}"
            ok=0
            fail=0
            log "Backfill for last $days days..."
            for i in $(seq 0 $((days - 1))); do
                day="$(date -d "$((-i)) days" +%Y-%m-%d)"
                if sync_day "$day"; then
                    ok=$((ok + 1))
                else
                    fail=$((fail + 1))
                fi
                log ""
            done
            log "Backfill complete: $ok OK, $fail failed."
            [ "$fail" -eq 0 ]
            ;;
        *)
            trigger_export
            if [ ! -f "$GB_DB" ]; then
                log "ERROR: Gadgetbridge DB not found at $GB_DB" >&2
                log "Set GB_DB=/path/to/Gadgetbridge and run again." >&2
                exit 1
            fi
            day="${1:-$(date +%Y-%m-%d)}"
            sync_day "$day"
            ;;
    esac
}

main "$@"
