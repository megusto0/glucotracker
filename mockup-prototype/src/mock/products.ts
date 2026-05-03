export interface Product {
  name: string
  src: string
  c: number
  p: number
  f: number
  k: number
  color: string
}

export const products: Product[] = [
  { name: "Протеиновое брауни Shagi.", src: "ROYAL CAKE · LABEL_CALC · НЕ ПРОВЕРЕНО", c: 8, p: 4, f: 11, k: 144, color: "#3F2E22" },
  { name: "Сырок глазированный", src: "LABEL_CALC · НЕ ПРОВЕРЕНО", c: 14, p: 3, f: 10, k: 165, color: "#7C5A36" },
  { name: "Кола Ориджинал", src: "4604441024742 · ЧЕРНОГОЛОВКА · НЕ ПРОВЕРЕНО", c: 16, p: 0, f: 0, k: 63, color: "#7B2A2A" },
  { name: "Халва подсолнечная глазированная", src: "ВОСТОЧНЫЙ ГОСТЬ · LABEL_CALC · НЕ ПРОВЕРЕНО", c: 9, p: 2, f: 7, k: 110, color: "#9C6E3F" },
  { name: "Бисквит-сэндвич", src: "LABEL_CALC · НЕ ПРОВЕРЕНО", c: 19, p: 1, f: 5, k: 123, color: "#D8B98A" },
  { name: "Cheetos Пицца", src: "4690631527407 · CHEETOS · НЕ ПРОВЕРЕНО", c: 30, p: 4, f: 12, k: 245, color: "#C95A2E" },
  { name: 'Сырок глазированный "Эфер"', src: "ЭФЕР · LABEL_CALC · НЕ ПРОВЕРЕНО", c: 13, p: 4, f: 7, k: 128, color: "#B8AC7E" },
  { name: "Воппер", src: "BKWHOPPER · BURGER KING OFFICIAL PDF · НЕ ПРОВЕРЕНО", c: 53, p: 27, f: 44, k: 720, color: "#7B4A2A" },
]
