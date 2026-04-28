const dash = "—";

export function formatMacroValue(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return dash;
  }
  const rounded = Math.round(Number(value) * 10) / 10;
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
}

export function formatKcalValue(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return dash;
  }
  return String(Math.round(Number(value)));
}

export function formatMacro(value: number | null | undefined, unit: string) {
  return `${formatMacroValue(value)}${unit}`;
}

export function formatKcal(value: number | null | undefined) {
  return `${formatKcalValue(value)} ккал`;
}
