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

export function generateHeatmap() {
  const out: number[][] = []
  for (let r = 0; r < 7; r++) {
    const row: number[] = []
    for (let c = 0; c < 24; c++) {
      let v = 0
      if ([8, 9].includes(c)) v = 0.2 + Math.random() * 0.5
      else if ([13, 14].includes(c)) v = 0.35 + Math.random() * 0.55
      else if ([19, 20, 21].includes(c)) v = 0.45 + Math.random() * 0.5
      else if ([10, 12, 16, 18].includes(c)) v = Math.random() * 0.28
      else v = Math.random() * 0.05
      if (r === 5 && (c === 15 || c === 16)) v = 0.95
      row.push(v)
    }
    out.push(row)
  }
  return out
}
