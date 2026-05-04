export const tdee = 2829
export const calorieGoal = 2200

export const days7 = [
  { d: "пн", date: "27", intake: 0, carbs: 0 },
  { d: "вт", date: "28", intake: 1842, carbs: 145 },
  { d: "ср", date: "29", intake: 2410, carbs: 198 },
  { d: "чт", date: "30", intake: 2156, carbs: 240 },
  { d: "пт", date: "01", intake: 1924, carbs: 178 },
  { d: "сб", date: "02", intake: 1587, carbs: 111, today: true as const },
]

export const carbs14 = [145, 198, 312, 240, 178, 95, 156, 111, 0, 0, 0, 0, 0, 0]
export const carbs14avg = 227

// 6×7 meal heatmap (6 four-hour blocks × 7 days). Stable, hand-tuned values.
export const mealHeatmap6x7: number[][] = [
  // 00-04 04-08 08-12 12-16 16-20 20-24
  [0.05, 0.30, 0.55, 0.75, 0.55, 0.45], // Пн
  [0.05, 0.25, 0.50, 0.85, 0.60, 0.40], // Вт
  [0.05, 0.35, 0.60, 0.70, 0.65, 0.50], // Ср
  [0.10, 0.30, 0.55, 0.95, 0.50, 0.30], // Чт
  [0.05, 0.40, 0.50, 0.80, 0.70, 0.45], // Пт
  [0.05, 0.20, 0.45, 0.65, 0.75, 0.55], // Сб
  [0.10, 0.30, 0.55, 0.75, 0.55, 0.40], // Вс
]

// TIR distribution per day (last 9 days). Each entry sums to 100 (%).
// below = ниже диапазона, in = в диапазоне, above = выше диапазона.
export const tirDays = [
  { d: "25 апр", below: 4, inRange: 62, above: 34 },
  { d: "26 апр", below: 6, inRange: 58, above: 36 },
  { d: "27 апр", below: 3, inRange: 65, above: 32 },
  { d: "28 апр", below: 5, inRange: 60, above: 35 },
  { d: "29 апр", below: 8, inRange: 54, above: 38 },
  { d: "30 апр", below: 4, inRange: 67, above: 29 },
  { d: "01 мая", below: 5, inRange: 63, above: 32 },
  { d: "02 мая", below: 7, inRange: 56, above: 37 },
  { d: "03 мая", below: 3, inRange: 70, above: 27 },
]

// Daypart glucose profile (avg per 4-hour window over 7 days).
export const dayparts = [
  { range: "00:00–04:00", avg: 8.1, tir: 63 },
  { range: "04:00–08:00", avg: 8.6, tir: 65 },
  { range: "08:00–12:00", avg: 9.4, tir: 57 },
  { range: "12:00–16:00", avg: 9.3, tir: 56 },
  { range: "16:00–20:00", avg: 9.2, tir: 55 },
  { range: "20:00–24:00", avg: 8.6, tir: 67 },
]
