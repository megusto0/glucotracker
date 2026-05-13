type LogLevel = "debug" | "info" | "warn" | "error";

interface SyncLogEntry {
  timestamp: string;
  level: LogLevel;
  event: string;
  sensorId?: string;
  details?: Record<string, unknown>;
}

const MAX_LOG_ENTRIES = 500;

const entries: SyncLogEntry[] = [];

function formatTs(): string {
  return new Date().toISOString();
}

function push(entry: Omit<SyncLogEntry, "timestamp">) {
  const sensorId = (entry.details?.sensorId as string | undefined) ?? entry.sensorId;
  entries.push({ ...entry, sensorId, timestamp: formatTs() });
  if (entries.length > MAX_LOG_ENTRIES) {
    entries.splice(0, entries.length - MAX_LOG_ENTRIES);
  }
}

export const glucoseSyncLogger = {
  debug(event: string, details?: Record<string, unknown>) {
    push({ level: "debug", event, details });
  },

  info(event: string, details?: Record<string, unknown>) {
    push({ level: "info", event, details });
  },

  warn(event: string, details?: Record<string, unknown>) {
    push({ level: "warn", event, details });
  },

  error(event: string, details?: Record<string, unknown>) {
    push({ level: "error", event, details });
  },

  getEntries(level?: LogLevel): readonly SyncLogEntry[] {
    return level ? entries.filter((e) => e.level === level) : entries;
  },

  getEntriesForSensor(sensorId: string): readonly SyncLogEntry[] {
    return entries.filter((e) => e.sensorId === sensorId);
  },

  clear() {
    entries.length = 0;
  },

  exportLog(): string {
    return entries
      .map((e) => {
        const parts = [e.timestamp, e.level.toUpperCase(), e.event];
        if (e.sensorId) parts.push(`sensor=${e.sensorId}`);
        if (e.details) parts.push(JSON.stringify(e.details));
        return parts.join(" ");
      })
      .join("\n");
  },

  summary(): { total: number; byLevel: Record<LogLevel, number> } {
    const byLevel: Record<LogLevel, number> = {
      debug: 0,
      info: 0,
      warn: 0,
      error: 0,
    };
    for (const e of entries) byLevel[e.level]++;
    return { total: entries.length, byLevel };
  },
};
