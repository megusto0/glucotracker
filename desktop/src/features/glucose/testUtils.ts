export const CGM_INTERVAL_MS = 5 * 60 * 1000;
export const POST_DETECTION_DELAY_MS = 30 * 1000;
export const MIN_CHECK_INTERVAL_MS = 15 * 1000;

export function calculateNextCheckDelay(
  lastReadingTime: number,
  now: number = Date.now(),
): number {
  const elapsed = now - lastReadingTime;
  const cycleOffset = elapsed % CGM_INTERVAL_MS;

  if (cycleOffset <= MIN_CHECK_INTERVAL_MS || cycleOffset >= CGM_INTERVAL_MS - MIN_CHECK_INTERVAL_MS) {
    return Math.max(POST_DETECTION_DELAY_MS, MIN_CHECK_INTERVAL_MS);
  }

  return Math.max(
    CGM_INTERVAL_MS - cycleOffset + POST_DETECTION_DELAY_MS,
    MIN_CHECK_INTERVAL_MS,
  );
}

export function calculateBackoffMs(errors: number): number {
  const base = 10_000;
  const max = 5 * 60 * 1000;
  const delay = Math.min(base * Math.pow(2, errors), max);
  const jitter = Math.random() * base;
  return delay + jitter;
}
