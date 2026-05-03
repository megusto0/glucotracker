export interface Meal {
  time: string
  title: string
  sub: string[]
  c: number
  p: number
  f: number
  k: number
  color: string
  brand?: string
  weight?: number
  tag?: string
}

export const todayMeals: Meal[] = [
  { time: "16:04", title: "Кола Ориджинал", sub: ["Черноголовка", "смешано", "330 г"], c: 16, p: 0, f: 0, k: 63, color: "#7B2A2A", brand: "Черноголовка", weight: 330 },
  { time: "15:52", title: "Cheetos Пицца", sub: ["БРЕНДЫ", "принято", "37 г"], c: 22, p: 3, f: 9, k: 181, color: "#C95A2E" },
  { time: "15:45", title: "Лаваш с курицей и овощами", sub: ["фото", "принято", "324 г"], c: 27, p: 40, f: 41, k: 634, color: "#C2A06A", tag: "фото" },
  { time: "14:07", title: "Протеиновое брауни Shagi", sub: ["смешано", "принято", "33 г"], c: 8, p: 4, f: 11, k: 144, color: "#3F2E22" },
  { time: "14:07", title: "Сырок глазированный", sub: ["смешано", "принято", "40 г"], c: 14, p: 3, f: 10, k: 165, color: "#7C5A36" },
  { time: "05:30", title: "Халва подсолнечная глазированная", sub: ["восточный гость", "принято", "20 г"], c: 9, p: 2, f: 7, k: 110, color: "#9C6E3F" },
  { time: "05:15", title: "Творог со сметаной и замороженным фруктом", sub: ["фото", "принято", "150 г"], c: 15, p: 28, f: 14, k: 290, color: "#E2D4B5", tag: "фото" },
]

export const autocompleteItems = [
  { name: "Воппер", src: "Ресторан · bk:whopper", c: 53, p: 27, f: 44, k: 720 },
  { name: "Воппер Джуниор", src: "Ресторан · bk:whopper_jr", c: 33, p: 13, f: 21, k: 370 },
  { name: "Воппер По-Итальянски", src: "Ресторан · bk:whopper_ital", c: 56, p: 29, f: 45, k: 750 },
  { name: "Воппер По-Итальянски Двойной", src: "Ресторан · bk:whopper_ital_dbl", c: 59, p: 49, f: 76, k: 1120 },
  { name: "Воппер Ролл", src: "Ресторан · bk:whopper_roll", c: 34, p: 21, f: 36, k: 540 },
  { name: "Воппер С Сыром", src: "Ресторан · bk:whopper_cheese", c: 54, p: 31, f: 50, k: 790 },
  { name: "Атомик Воппер", src: "Ресторан · bk:atomic_whopper", c: 56, p: 42, f: 43, k: 710 },
]
