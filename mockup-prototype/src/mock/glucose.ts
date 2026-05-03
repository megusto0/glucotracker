export function generateCgmRaw(n = 72) {
  const pts: { y: number }[] = []
  for (let i = 0; i < n; i++) {
    const t = i / (n - 1)
    let y = 5.4 + Math.sin(t * 2 * Math.PI * 0.6) * 0.4
    if (t > 0.42) y += 2.6 * Math.exp(-Math.pow((t - 0.55) / 0.13, 2))
    if (t > 0.55) y += 1.3 * Math.exp(-Math.pow((t - 0.7) / 0.09, 2))
    y += (Math.random() - 0.5) * 0.18
    pts.push({ y })
  }
  return pts
}

export function generateCgm24(n = 96) {
  const pts: { y: number }[] = []
  for (let i = 0; i < n; i++) {
    const t = i / (n - 1)
    let y = 5.6 + Math.sin(t * Math.PI * 2.4) * 0.5
    if (t > 0.28 && t < 0.52) y += 2.8 * Math.exp(-Math.pow((t - 0.42) / 0.1, 2))
    if (t > 0.58 && t < 0.82) y += 1.9 * Math.exp(-Math.pow((t - 0.7) / 0.09, 2))
    y += (Math.random() - 0.5) * 0.15
    pts.push({ y: Math.max(2.5, y) })
  }
  return pts
}

export function generateSensorOffset(n = 60) {
  const out: { y: number }[] = []
  for (let i = 0; i < n; i++) {
    let y = 0.95
    if (i > 24 && i < 32) y = 0.5
    if (i >= 32) y = 0.32 + (Math.random() - 0.5) * 0.04
    if (i < 6) y = 0.85 + (Math.random() - 0.5) * 0.04
    out.push({ y })
  }
  return out
}

export const glucoseEvents = [
  { i: 18, kind: "meal" as const, label: "14:07 · 21.7 г", title: "Приём пищи" },
  { i: 38, kind: "meal" as const, label: "15:43–16:04 · 64.8 г", title: "Приём пищи", big: true },
  { i: 50, kind: "fingerstick" as const, label: "16:33", value: "9.9" },
  { i: 60, kind: "insulin" as const, label: "17:40", value: "1.6 ЕД" },
]

export const glucoseEpisodes = [
  {
    time: "14:07", events: 2,
    names: "Сырок глазированный, Протеиновое брауни Shagi",
    carbs: "21.7 г", kcal: "309",
    peak: "7.3 → пик 8.9 через 115 мин", insulin: "0.8 ЕД",
  },
  {
    time: "15:43–16:04", events: 4,
    names: "Лаваш с курицей, Cheetos Пицца, Кола Ориджинал",
    carbs: "64.8 г", kcal: "878",
    peak: "9.5 → пик 10.1 через 12 мин", insulin: "1.6 ЕД",
    active: true,
  },
]

export const episodeDetails = [
  [
    { time: "14:07", t: "Сырок глазированный", c: "14 г", k: "165 ккал" },
    { time: "14:07", t: "Протеиновое брауни Shagi", c: "7.7 г", k: "144 ккал" },
  ],
  [
    { time: "15:43", t: "Лаваш с курицей и овощами", c: "27.1 г", k: "634 ккал" },
    { time: "15:52", t: "Cheetos Пицца", c: "22.2 г", k: "181 ккал" },
    { time: "16:04", t: "Кола Ориджинал", c: "15.5 г", k: "63 ккал" },
    { time: "17:40", t: "Инсулин из Nightscout · только чтение", c: "—", k: "1.6 ЕД", insulin: true },
  ],
]

export const rawEvents = [
  { time: "05:15", type: "meal", title: "Творог со сметаной", carbs: "15 г", kcal: "290 ккал" },
  { time: "05:30", type: "meal", title: "Халва подсолнечная", carbs: "9 г", kcal: "110 ккал" },
  { time: "14:07", type: "meal", title: "Сырок глазированный", carbs: "14 г", kcal: "165 ккал" },
  { time: "14:07", type: "meal", title: "Протеиновое брауни Shagi", carbs: "8 г", kcal: "144 ккал" },
  { time: "14:07", type: "insulin", title: "Инсулин (NS)", carbs: "—", kcal: "0.8 ЕД" },
  { time: "15:43", type: "meal", title: "Лаваш с курицей и овощами", carbs: "27 г", kcal: "634 ккал" },
  { time: "15:52", type: "meal", title: "Cheetos Пицца", carbs: "22 г", kcal: "181 ккал" },
  { time: "16:04", type: "meal", title: "Кола Ориджинал", carbs: "16 г", kcal: "63 ккал" },
  { time: "16:33", type: "fingerstick", title: "Запись из пальца", carbs: "—", kcal: "9.9 ммоль/л" },
  { time: "17:40", type: "insulin", title: "Инсулин (NS)", carbs: "—", kcal: "1.6 ЕД" },
]
