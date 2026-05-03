export const currentSensor = {
  name: "Ottai",
  model: "Otta-1 · модель A",
  day: 2.7,
  maxDays: 15,
  quality: 92,
  artifacts: 0,
  comprLows: 0,
  noise: 1.0,
  trust: "high",
  offset: "+0.3",
  offsetUnit: "ммоль/л",
  medianDelta: "+0.3",
  range: "+0.3…+0.3",
  drift: "+0/день",
  mard: "3.1%",
  fingerstickCount: 1,
  phase: "стабильная фаза",
}

export const previousSensors = [
  { name: "Ottai", date: "30 апр", days: "14.8 д", q: 88 },
  { name: "Ottai", date: "16 апр", days: "13.2 д", q: 79 },
  { name: "Dexcom G7", date: "03 апр", days: "10.4 д", q: 91 },
]

export const lastFingerstick = {
  time: "16:33",
  value: 9.9,
  delta: "+0.3",
}
