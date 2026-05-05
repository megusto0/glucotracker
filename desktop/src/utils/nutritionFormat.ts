const dash = "—";

const asFiniteNumber = (value?: number | null) => {
  if (value === null || value === undefined) {
    return null;
  }
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
};

export function formatMacroValue(value?: number | null) {
  const numeric = asFiniteNumber(value);
  if (numeric === null) {
    return dash;
  }
  const rounded = Math.round(numeric * 10) / 10;
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
}

export function formatKcalValue(value?: number | null) {
  const numeric = asFiniteNumber(value);
  if (numeric === null) {
    return dash;
  }
  return String(Math.round(numeric));
}

export function formatMacro(value: number | null | undefined, unit: string) {
  return `${formatMacroValue(value)}${unit}`;
}

export function formatKcal(value: number | null | undefined) {
  return `${formatKcalValue(value)} ккал`;
}

export function formatGlucose(value?: number | null) {
  const numeric = asFiniteNumber(value);
  if (numeric === null) {
    return dash;
  }
  return numeric.toFixed(1);
}

export function formatWeight(value?: number | null) {
  const numeric = asFiniteNumber(value);
  if (numeric === null) {
    return dash;
  }
  return numeric.toFixed(2).replace(".", ",");
}

export function formatPercent(value?: number | null) {
  const numeric = asFiniteNumber(value);
  if (numeric === null) {
    return dash;
  }
  return String(Math.round(numeric));
}

export function formatSafeInt(value?: number | null) {
  const numeric = asFiniteNumber(value);
  if (numeric === null) {
    return dash;
  }
  return String(Math.round(numeric));
}

export function fmtInt(value: number) {
  return String(Math.round(value));
}

export function fmtSignedInt(value: number) {
  const rounded = Math.round(value);
  return `${rounded > 0 ? "+" : ""}${rounded}`;
}

export function fmtGrams(value?: number | null) {
  const numeric = asFiniteNumber(value);
  if (numeric === null) {
    return dash;
  }
  const rounded = Math.round(numeric * 10) / 10;
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
}

export function fmtMmol(value?: number | null) {
  const numeric = asFiniteNumber(value);
  if (numeric === null) {
    return dash;
  }
  return numeric.toFixed(1).replace(".", ",");
}
