import { useEffect, useState } from "react";
import type { SyncState } from "./useGlucoseSyncTracker";

const CGM_NO_NEW_THRESHOLD_MS = 4 * 60 * 1000;

function formatRelative(isoTs: string | null): string {
  if (!isoTs) return "—";
  const diff = Date.now() - new Date(isoTs).getTime();
  if (diff < 60_000) return "только что";
  if (diff < 3600_000) return `${Math.floor(diff / 60_000)} мин назад`;
  if (diff < 86400_000) {
    const h = Math.floor(diff / 3600_000);
    const m = Math.floor((diff % 3600_000) / 60_000);
    return `${h}ч ${m}м назад`;
  }
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    month: "short",
  }).format(new Date(isoTs));
}

function formatCountdown(date: Date | null): string {
  if (!date) return "";
  const diff = date.getTime() - Date.now();
  if (diff <= 0) return "сейчас";
  if (diff < 60_000) return `через ${Math.ceil(diff / 1000)}с`;
  return `через ${Math.ceil(diff / 60_000)}м`;
}

export function SyncStatusIndicator({
  syncState,
  compact = false,
}: {
  syncState: SyncState;
  compact?: boolean;
}) {
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(interval);
  }, []);

  void tick;

  const {
    phase,
    lastSuccessfulImportAt,
    consecutiveErrors,
    lastError,
    nextScheduledAt,
    lastCheckAt,
    lastKnownReadingTs,
  } = syncState;
  const isError = phase === "offline" || Boolean(lastError);
  const isLoading =
    phase === "checking" || phase === "importing" || phase === "backing_off";
  const checkTs = lastCheckAt ? Date.parse(lastCheckAt) : NaN;
  const knownTs = lastKnownReadingTs ? Date.parse(lastKnownReadingTs) : NaN;
  const noNewPoints =
    phase === "awaiting_data" &&
    Number.isFinite(checkTs) &&
    Number.isFinite(knownTs) &&
    checkTs - knownTs > CGM_NO_NEW_THRESHOLD_MS;

  const label = isError
    ? "Не удалось обновить"
    : isLoading
      ? "Обновляем данные…"
      : noNewPoints
        ? "Нет новых CGM-точек"
        : "Данные актуальны";
  const color = isError
    ? "var(--warn)"
    : isLoading
      ? "var(--accent)"
      : noNewPoints
        ? "var(--ink-3)"
        : "var(--good)";
  const nextCheck =
    nextScheduledAt && phase !== "offline"
      ? ` · следующее обновление ${formatCountdown(nextScheduledAt)}`
      : "";
  const details = lastSuccessfulImportAt
    ? ` · обновление ${formatRelative(lastSuccessfulImportAt)}`
    : "";
  const singleLine = `${label}${nextCheck}${details}`;

  if (compact) {
    return (
      <span
        className="row gap-6"
        style={{ alignItems: "center", fontSize: 11, color }}
      >
        <span
          style={{
            width: 6,
            height: 6,
            borderRadius: "50%",
            background: color,
            display: "inline-block",
            animation:
              isLoading
                ? "sync-pulse 1s ease-in-out infinite"
                : "none",
          }}
        />
        <span className="mono" style={{ color }}>
          {singleLine}
        </span>
      </span>
    );
  }

  return (
    <div
      className="card"
      style={{ padding: "10px 14px", marginBottom: 16, fontSize: 12 }}
    >
      <div className="row" style={{ alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <span
          style={{
            width: 8,
            height: 8,
            borderRadius: "50%",
            background: color,
            display: "inline-block",
            flexShrink: 0,
            animation:
              isLoading
                ? "sync-pulse 1s ease-in-out infinite"
                : "none",
          }}
        />
        <span className="mono" style={{ fontWeight: 500, color }}>
          {singleLine}
        </span>
        {consecutiveErrors > 0 && (
          <span className="tag" style={{ background: "var(--warn-soft)", color: "var(--warn)", fontSize: 10 }}>
            {consecutiveErrors} ошибок
          </span>
        )}
      </div>

      {lastError && (
        <div
          style={{
            marginTop: 6,
            fontSize: 11,
            color: "var(--warn)",
            whiteSpace: "normal",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {lastError}
        </div>
      )}
    </div>
  );
}
