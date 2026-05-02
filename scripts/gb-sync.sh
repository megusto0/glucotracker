#!/data/data/com.termux/files/usr/bin/bash
# gb-sync.sh — sync today's activity from Gadgetbridge DB to glucotracker backend
#
# Prerequisites (Termux):
#   pkg install sqlite curl
#
# Usage:
#   chmod +x gb-sync.sh
#   ./gb-sync.sh                           # sync today
#   ./gb-sync.sh 2026-05-01                # sync specific date
#
# Tasker automation:
#   1. Trigger GB sync:    am broadcast -a nodomain.freeyourgadget.gadgetbridge.command.ACTIVITY_SYNC
#   2. Wait for broadcast: nodomain.freeyourgadget.gadgetbridge.action.ACTIVITY_SYNC_FINISH
#   3. Trigger export:     am broadcast -a nodomain.freeyourgadget.gadgetbridge.command.TRIGGER_EXPORT
#   4. Wait for broadcast: nodomain.freeyourgadget.gadgetbridge.action.DATABASE_EXPORT_SUCCESS
#   5. Run this script via Termux:Tasker plugin

set -euo pipefail

# --- Config ---
BACKEND_URL="http://192.168.1.100:8000"  # <-- your glucotracker backend IP
BACKEND_TOKEN=""                           # <-- your backend token

# Gadgetbridge DB location (export)
GB_DB="/storage/emulated/0/Android/data/nodomain.freeyourgadget.gadgetbridge/files/Gadgetbridge"

if [ ! -f "$GB_DB" ]; then
    echo "ERROR: Gadgetbridge DB not found at $GB_DB"
    echo "Trigger DB export first:"
    echo "  am broadcast -a nodomain.freeyourgadget.gadgetbridge.command.TRIGGER_EXPORT nodomain.freeyourgadget.gadgetbridge"
    exit 1
fi

DAY="${1:-$(date +%Y-%m-%d)}"

echo "Reading activity for $DAY from Gadgetbridge..."

# Steps: sum from ACTIVITY_SAMPLE where TIMESTAMP_START is on DAY
# GB stores timestamps as epoch seconds
DAY_START=$(date -d "$DAY 00:00:00" +%s 2>/dev/null || date -j -f "%Y-%m-%d %H:%M:%S" "$DAY 00:00:00" +%s)
DAY_END=$((DAY_START + 86400))

STEPS=$(sqlite3 "$GB_DB" \
    "SELECT COALESCE(SUM(STEPS), 0) FROM ACTIVITY_SAMPLE WHERE TIMESTAMP >= $DAY_START AND TIMESTAMP < $DAY_END;" \
    2>/dev/null || echo "0")

# Heart rate average
HR_AVG=$(sqlite3 "$GB_DB" \
    "SELECT ROUND(AVG(VALUE), 1) FROM HUAMI_STRESS_SAMPLE WHERE TIMESTAMP >= $DAY_START AND TIMESTAMP < $DAY_END AND VALUE > 0;" \
    2>/dev/null || echo "")

# Try heart rate from a different table name (varies by device)
if [ -z "$HR_AVG" ] || [ "$HR_AVG" = "0.0" ]; then
    HR_AVG=$(sqlite3 "$GB_DB" \
        "SELECT ROUND(AVG(VALUE), 1) FROM MI_BAND_ACTIVITY_SAMPLE WHERE TIMESTAMP >= $DAY_START AND TIMESTAMP < $DAY_END AND VALUE > 0;" \
        2>/dev/null || echo "")
fi

echo "  Steps: $STEPS"
echo "  HR avg: ${HR_AVG:--}"

# Estimate kcal burned: steps * 0.04 (rough estimate; GB may have its own)
# Adjust this formula based on your weight/profile
KCAL_BURNED=$(echo "$STEPS * 0.04" | bc 2>/dev/null || echo "0")

echo "  Est. kcal burned: $KCAL_BURNED"

# Build JSON payload
HR_JSON=""
if [ -n "$HR_AVG" ] && [ "$HR_AVG" != "" ]; then
    HR_JSON=", \"heart_rate_avg\": $HR_AVG"
fi

PAYLOAD="{\"date\": \"$DAY\", \"steps\": $STEPS, \"kcal_burned\": $KCAL_BURNED, \"active_minutes\": 0, \"source\": \"gadgetbridge\"$HR_JSON}"

echo "Syncing to glucotracker..."
curl -s -X POST \
    "$BACKEND_URL/activity/sync" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $BACKEND_TOKEN" \
    -d "$PAYLOAD"

echo ""
echo "Done."
