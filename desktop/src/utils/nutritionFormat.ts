const dash = "—";
const minus = "−";

const ruInteger = new Intl.NumberFormat("ru-RU", {
  maximumFractionDigits: 0,
  useGrouping: true,
});

const asFiniteNumber = (value?: number | null) => {
  if (value === null || value === undefined) {
    return null;
  }
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
};

const normalizeGrouping = (value: string) =>
  value.replace(/\u00a0/g, " ").replace(/\u202f/g, " ");

const formatInteger = (value: number) => normalizeGrouping(ruInteger.format(Math.round(value)));

export function formatDecimal(value?: number | null, digits = 1) {
  const numeric = asFiniteNumber(value);
  if (numeric === null) {
    return dash;
  }
  return normalizeGrouping(
    new Intl.NumberFormat("ru-RU", {
      maximumFractionDigits: digits,
      minimumFractionDigits: digits,
      useGrouping: true,
    }).format(numeric),
  );
}

export function formatSignedDecimal(value?: number | null, digits = 1) {
  const numeric = asFiniteNumber(value);
  if (numeric === null) {
    return dash;
  }
  const prefix = numeric > 0 ? "+" : numeric < 0 ? minus : "";
  return `${prefix}${formatDecimal(Math.abs(numeric), digits)}`;
}

export function formatGrams(value?: number | null) {
  const numeric = asFiniteNumber(value);
  if (numeric === null) {
    return dash;
  }
  const rounded = Math.round(numeric * 10) / 10;
  return Number.isInteger(rounded)
    ? formatInteger(rounded)
    : String(rounded);
}

export function formatMacroValue(value?: number | null) {
  return formatGrams(value);
}

export function formatKcalValue(value?: number | null) {
  const numeric = asFiniteNumber(value);
  if (numeric === null) {
    return dash;
  }
  return formatInteger(numeric);
}

export function formatMacro(value: number | null | undefined, unit: string) {
  return `${formatGrams(value)}${unit}`;
}

export function formatKcal(value: number | null | undefined) {
  return `${formatKcalValue(value)} ккал`;
}

export function formatSignedKcal(value?: number | null) {
  const numeric = asFiniteNumber(value);
  if (numeric === null) {
    return dash;
  }
  const rounded = Math.round(numeric);
  const prefix = rounded > 0 ? "+" : rounded < 0 ? minus : "";
  return `${prefix}${formatInteger(Math.abs(rounded))}`;
}

export function formatMmol(value?: number | null) {
  return formatDecimal(value, 1);
}

export function formatGlucose(value?: number | null) {
  return formatMmol(value);
}

export function formatWeight(value?: number | null) {
  const numeric = asFiniteNumber(value);
  if (numeric === null) {
    return dash;
  }
  return normalizeGrouping(
    new Intl.NumberFormat("ru-RU", {
      maximumFractionDigits: 2,
      minimumFractionDigits: 2,
      useGrouping: true,
    }).format(numeric),
  );
}

export function formatPercent(value?: number | null) {
  const numeric = asFiniteNumber(value);
  if (numeric === null) {
    return dash;
  }
  return formatInteger(numeric);
}

export function formatSafeInt(value?: number | null) {
  const numeric = asFiniteNumber(value);
  if (numeric === null) {
    return dash;
  }
  return formatInteger(numeric);
}

export function fmtInt(value: number) {
  return formatInteger(value);
}

export function fmtSignedInt(value: number) {
  return formatSignedKcal(value);
}

export function fmtGrams(value?: number | null) {
  return formatGrams(value);
}

export function fmtMmol(value?: number | null) {
  return formatMmol(value);
}
