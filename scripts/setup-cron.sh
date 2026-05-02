#!/data/data/com.termux/files/usr/bin/bash
# ============================================================
# setup-cron.sh — автоматическая синхронизация GB → glucotracker
# ============================================================
#
# Запуск один раз:
#   bash setup-cron.sh
#
# Что делает:
#   - Устанавливает cronie (если нет)
#   - Добавляет задачу: gb-sync.sh каждые 30 минут
#   - Запускает crond
#
# Проверить:
#   crontab -l
#   crond status    (если поддерживается)
#
# Лог:
#   ~/gb-sync-cron.log
# ============================================================

set -euo pipefail

SCRIPT="$HOME/bin/gb-sync.sh"
LOG="$HOME/gb-sync-cron.log"

if [ ! -f "$SCRIPT" ]; then
    echo "ОШИБКА: $SCRIPT не найден. Сначала скопируй gb-sync.sh в ~/bin/"
    exit 1
fi

pkg install cronie -y 2>/dev/null || true

# cron запись: каждые 30 минут
CRON_ENTRY="*/30 * * * * $SCRIPT >> $LOG 2>&1"

# Удалить старую запись если есть
(crontab -l 2>/dev/null | grep -v "gb-sync.sh") | { cat; echo "$CRON_ENTRY"; } | crontab -

echo "Crontab установлен:"
crontab -l

# Запустить crond
crond 2>/dev/null || true

echo ""
echo "Готово! Синхронизация каждые 30 минут."
echo "Лог: $LOG"
echo ""
echo "Для бэкфилла за прошлые дни запусти один раз:"
echo "  $SCRIPT --backfill 7"
