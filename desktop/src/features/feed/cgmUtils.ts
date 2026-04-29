const CGM_MIN_VALID = 2.4;

export const isValidCGM = (value: number) => value >= CGM_MIN_VALID;

export function filterValidCGM<T extends { value: number }>(entries: T[]): T[] {
  return entries.filter((e) => isValidCGM(e.value));
}
