#!/bin/bash
set -euo pipefail

if ! curl -sf http://127.0.0.1:8000/health > /dev/null; then
  systemctl restart glucotracker-web
  echo "$(date --iso-8601=seconds) restarted glucotracker-web" \
    >> /var/log/glucotracker-watchdog.log
fi
