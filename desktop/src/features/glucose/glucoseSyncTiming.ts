export const CGM_INTERVAL_MS = 5 * 60 * 1000;
export const POST_DETECTION_DELAY_MS = 30 * 1000;
export const MIN_CHECK_INTERVAL_MS = 15 * 1000;
export const MAX_CHECK_INTERVAL_MS = 5 * 60 * 1000;
export const SENSOR_DISCONNECTED_AFTER_MS = 15 * 60 * 1000;

export function calculateNextCheckDelay(
  lastReadingTime: number,
  now: number = Date.now(),
): number {
  const elapsed = now - lastReadingTime;
  const cycleOffset = elapsed % CGM_INTERVAL_MS;

  if (
    cycleOffset <= MIN_CHECK_INTERVAL_MS ||
    cycleOffset >= CGM_INTERVAL_MS - MIN_CHECK_INTERVAL_MS
  ) {
    return Math.max(POST_DETECTION_DELAY_MS, MIN_CHECK_INTERVAL_MS);
  }

  return Math.max(
    CGM_INTERVAL_MS - cycleOffset + POST_DETECTION_DELAY_MS,
    MIN_CHECK_INTERVAL_MS,
  );
}

export function calculateBackoffMs(errors: number): number {
  const base = 10_000;
  const delay = Math.min(base * Math.pow(2, errors), MAX_CHECK_INTERVAL_MS);
  const jitter = Math.random() * base;
  return delay + jitter;
}

export function delayFromLatestReading(
  latestTs: string,
  now: number = Date.now(),
): number {
  const parsed = Date.parse(latestTs);
  if (!Number.isFinite(parsed)) return MIN_CHECK_INTERVAL_MS;
  return calculateNextCheckDelay(parsed, now);
}

export function sensorReadingAgeMs(
  latestTs: string | null,
  now: number = Date.now(),
): number | null {
  if (!latestTs) return null;
  const parsed = Date.parse(latestTs);
  if (!Number.isFinite(parsed)) return null;
  return Math.max(0, now - parsed);
}

export function isSensorStreamDisconnected(
  latestTs: string | null,
  now: number = Date.now(),
): boolean {
  const ageMs = sensorReadingAgeMs(latestTs, now);
  return ageMs !== null && ageMs > SENSOR_DISCONNECTED_AFTER_MS;
}
