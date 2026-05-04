import { useState, useMemo } from 'react'
import { I } from '../components/Icons'
import PageHead from '../components/PageHead'
import SegmentedControl from '../components/SegmentedControl'
import RightPanel from '../components/RightPanel'
import { generateCgmRaw, generateSensorOffset, glucoseEpisodes, episodeDetails, rawEvents } from '../mock/glucose'
import { currentSensor, previousSensors, lastFingerstick } from '../mock/sensors'

function SensorPanel() {
  return (
    <>
      <div className="lbl">текущий сенсор</div>
      <div className="row" style={{ alignItems: "baseline", justifyContent: "space-between", marginTop: 4 }}>
        <h2 style={{ margin: 0, fontFamily: "var(--serif)", fontSize: 24, fontWeight: 500 }}>{currentSensor.name}</h2>
        <span className="tag good">актив.</span>
      </div>
      <div style={{ fontSize: 11, color: "var(--ink-3)", marginTop: 4 }}>
        <span className="mono">{currentSensor.model}</span> · день <span className="mono">{currentSensor.day} / {currentSensor.maxDays}</span>
      </div>

      <div style={{ marginTop: 22 }}>
        <div className="lbl" style={{ marginBottom: 6 }}>Качество</div>
        <div className="row" style={{ alignItems: "baseline", gap: 4 }}>
          <span className="mono" style={{ fontSize: 28, fontWeight: 500 }}>{currentSensor.quality}</span>
          <span className="mono" style={{ fontSize: 12, color: "var(--ink-3)" }}>/ 100</span>
        </div>
        <div className="pbar good" style={{ marginTop: 6 }}><i style={{ width: `${currentSensor.quality}%` }} /></div>
      </div>

      <div className="row" style={{ marginTop: 18, gap: 0, borderTop: "1px solid var(--hairline)", borderBottom: "1px solid var(--hairline)" }}>
        {[
          { l: "артефакты", v: String(currentSensor.artifacts) },
          { l: "compr. lows", v: String(currentSensor.comprLows) },
          { l: "noise", v: String(currentSensor.noise) },
          { l: "доверие", v: currentSensor.trust },
        ].map((m, i) => (
          <div key={i} style={{ flex: 1, padding: "10px 0", borderRight: i < 3 ? "1px solid var(--hairline)" : "none", textAlign: "center" }}>
            <div className="mono" style={{ fontSize: 13 }}>{m.v}</div>
            <div className="lbl" style={{ marginTop: 2, fontSize: 9 }}>{m.l}</div>
          </div>
        ))}
      </div>

      <div style={{ marginTop: 18, padding: 14, border: "1px solid var(--hairline-2)", borderRadius: "var(--radius-lg)", background: "var(--surface)" }}>
        <div className="lbl">оценка смещения</div>
        <div className="row" style={{ alignItems: "baseline", marginTop: 4, gap: 4 }}>
          <span className="mono" style={{ fontSize: 22, fontWeight: 500 }}>{currentSensor.offset}</span>
          <span style={{ fontSize: 11, color: "var(--ink-3)" }}>{currentSensor.offsetUnit}</span>
        </div>
        <div style={{ fontSize: 11, color: "var(--ink-3)", marginTop: 4, lineHeight: 1.4 }}>
          {currentSensor.fingerstickCount} запись из пальца · {currentSensor.phase}
        </div>
        <div className="row" style={{ marginTop: 12, gap: 12 }}>
          <div style={{ flex: 1 }}>
            <div className="lbl" style={{ fontSize: 9 }}>медиана Δ</div>
            <div className="mono" style={{ fontSize: 12 }}>{currentSensor.medianDelta}</div>
          </div>
          <div style={{ flex: 1 }}>
            <div className="lbl" style={{ fontSize: 9 }}>диапазон</div>
            <div className="mono" style={{ fontSize: 12 }}>{currentSensor.range}</div>
          </div>
        </div>
        <div className="row" style={{ marginTop: 8, gap: 12 }}>
          <div style={{ flex: 1 }}>
            <div className="lbl" style={{ fontSize: 9 }}>дрейф</div>
            <div className="mono" style={{ fontSize: 12 }}>{currentSensor.drift}</div>
          </div>
          <div style={{ flex: 1 }}>
            <div className="lbl" style={{ fontSize: 9 }}>mard</div>
            <div className="mono" style={{ fontSize: 12 }}>{currentSensor.mard}</div>
          </div>
        </div>
      </div>

      <div className="col gap-8" style={{ marginTop: 18 }}>
        <button className="btn dark"><I.Plus size={13} /> Запись из пальца</button>
        <button className="btn"><I.Edit size={13} /> Редактировать сенсор</button>
        <button className="btn"><I.Refresh size={13} /> Пересчитать</button>
      </div>

      <div style={{ marginTop: 22 }}>
        <div className="lbl">последняя запись из пальца</div>
        <div className="row" style={{ alignItems: "center", marginTop: 6, padding: "10px 12px", border: "1px solid var(--hairline)", borderRadius: "var(--radius)", background: "var(--surface)", gap: 8 }}>
          <span className="mono" style={{ fontSize: 11, color: "var(--ink-3)" }}>{lastFingerstick.time}</span>
          <span className="mono" style={{ fontSize: 13, fontWeight: 500 }}>{lastFingerstick.value}</span>
          <span style={{ fontSize: 11, color: "var(--ink-3)" }}>ммоль/л</span>
          <span className="spacer" />
          <span className="tag accent">Δ {lastFingerstick.delta}</span>
        </div>
      </div>

      <div style={{ marginTop: 22 }}>
        <div className="lbl">предыдущие сенсоры</div>
        <div style={{ marginTop: 8 }}>
          {previousSensors.map((s, i) => (
            <div key={i} className="row" style={{ alignItems: "center", padding: "8px 0", borderTop: i === 0 ? "1px solid var(--hairline)" : "none", borderBottom: "1px solid var(--hairline)", gap: 10 }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 12 }}>{s.name}</div>
                <div className="mono" style={{ fontSize: 10, color: "var(--ink-4)", marginTop: 2 }}>{s.date} · {s.days}</div>
              </div>
              <span className="mono" style={{ fontSize: 11, color: "var(--ink-3)" }}>{s.q}</span>
            </div>
          ))}
        </div>
      </div>

      <div style={{ fontSize: 10, color: "var(--ink-4)", marginTop: 22, lineHeight: 1.5 }}>
        Это оценка, не медицинская рекомендация. Raw CGM не изменяется — нормализация применяется только на дисплее.
      </div>
    </>
  )
}

export default function GlucosePage() {
  const [timeRange, setTimeRange] = useState("6Ч")
  const [displayMode, setDisplayMode] = useState("НОРМ.")
  const [contextTab, setContextTab] = useState("Эпизоды")
  const [expandedEp, setExpandedEp] = useState(1)
  const [showSensorPanel, setShowSensorPanel] = useState(false)
  const [hoveredEpisode, setHoveredEpisode] = useState<number>(-1)

  const cgmRaw = useMemo(() => generateCgmRaw(), [])
  const cgmNorm = useMemo(() => cgmRaw.map((p) => ({ y: p.y + 0.3 })), [cgmRaw])
  const offsetPts = useMemo(() => generateSensorOffset(), [])

  // ---- chart geometry ----
  const W = 960
  const padL = 46, padR = 16

  // chart zone (glucose curve)
  const chartTop = 18
  const chartH = 220
  const chartBottom = chartTop + chartH

  // lanes zone — laneGap must accommodate "below-lane label" + "above-lane label"
  // (each ~10px font + 2-4px breathing room → minimum 28px between lane bodies)
  const laneGap = 30
  const laneH = 30
  const lanesTop = chartBottom + 26
  const lanesLabelW = 76
  const lane1Y = lanesTop                      // Питание
  const lane2Y = lanesTop + laneH + laneGap    // Инсулин
  const lane3Y = lane2Y + laneH + laneGap      // Калибровка
  const lanesBottom = lane3Y + laneH

  // axis labels area
  const axisH = 32
  const H = lanesBottom + axisH

  const yMin = 3.5, yMax = 12.2
  const innerW = W - padL - padR
  const yToY = (y: number) => chartTop + chartH - ((y - yMin) / (yMax - yMin)) * chartH
  const iToX = (i: number) => padL + (i / (cgmRaw.length - 1)) * innerW

  const rawPath = cgmRaw.map((p, i) => `${i === 0 ? "M" : "L"}${iToX(i).toFixed(1)},${yToY(p.y).toFixed(1)}`).join(" ")
  const normPath = cgmNorm.map((p, i) => `${i === 0 ? "M" : "L"}${iToX(i).toFixed(1)},${yToY(p.y).toFixed(1)}`).join(" ")

  const showRaw = displayMode === "RAW" || displayMode === "НОРМ."
  const showNorm = displayMode === "НОРМ." || displayMode === "СГЛАЖ."

  // ---- adaptive rendering: density depends on time range ----
  const density: 'full' | 'compact' | 'aggregate' =
    timeRange === '7Д' ? 'aggregate'
      : (timeRange === '12Ч' || timeRange === '24Ч') ? 'compact'
      : 'full'

  type MealEpisode = {
    iStart: number; iEnd: number; peakI: number
    carbs: number; label: string
    events: Array<{ i: number; name: string; c: number }>
  }

  // 'full' mode (3Ч / 6Ч): the rich detail dataset
  const mealEpisodesFull: MealEpisode[] = [
    {
      iStart: 18, iEnd: 19, peakI: 28,
      carbs: 21.7, label: "14:07",
      events: [
        { i: 18, name: "Сырок глазированный", c: 11.2 },
        { i: 19, name: "Брауни Shagi", c: 10.5 },
      ],
    },
    {
      iStart: 36, iEnd: 42, peakI: 45,
      carbs: 64.8, label: "15:43–16:04",
      events: [
        { i: 36, name: "Лаваш с курицей", c: 28.4 },
        { i: 38, name: "Cheetos Пицца", c: 8.2 },
        { i: 40, name: "Кола Ориджинал", c: 26.0 },
        { i: 42, name: "Доб.", c: 2.2 },
      ],
    },
  ]

  // 'compact' mode (12Ч / 24Ч): more events, simpler visuals
  const mealEpisodesCompact: MealEpisode[] = [
    { iStart: 4, iEnd: 5, peakI: 11, carbs: 38, label: "08:30", events: [
      { i: 4, name: "Овсянка", c: 28 }, { i: 5, name: "Банан", c: 10 } ] },
    { iStart: 14, iEnd: 14, peakI: 18, carbs: 12, label: "11:15", events: [
      { i: 14, name: "Йогурт", c: 12 } ] },
    { iStart: 24, iEnd: 26, peakI: 32, carbs: 21, label: "13:45", events: [
      { i: 24, name: "Сырок", c: 11 }, { i: 26, name: "Брауни", c: 10 } ] },
    { iStart: 38, iEnd: 44, peakI: 48, carbs: 65, label: "15:43", events: [
      { i: 38, name: "Лаваш", c: 28 }, { i: 40, name: "Чипсы", c: 8 },
      { i: 42, name: "Кола", c: 26 }, { i: 44, name: "Доб.", c: 3 } ] },
    { iStart: 54, iEnd: 56, peakI: 62, carbs: 78, label: "19:00", events: [
      { i: 54, name: "Котлета", c: 12 }, { i: 55, name: "Пюре", c: 36 },
      { i: 56, name: "Хлеб", c: 30 } ] },
    { iStart: 66, iEnd: 67, peakI: 70, carbs: 14, label: "22:00", events: [
      { i: 66, name: "Печенье", c: 14 } ] },
  ]

  type InsulinShot = { i: number; units: string; label: string }
  const insulinFull: InsulinShot[] = [
    { i: 24, units: "0.8", label: "14:50" },
    { i: 60, units: "1.6", label: "17:40" },
  ]
  const insulinCompact: InsulinShot[] = [
    { i: 5, units: "2.4", label: "08:35" },
    { i: 26, units: "1.4", label: "13:50" },
    { i: 44, units: "4.2", label: "16:00" },
    { i: 56, units: "5.0", label: "19:10" },
  ]

  type FingerStick = { i: number; value: number; label: string }
  const fingerFull: FingerStick[] = [
    { i: 50, value: 9.9, label: "16:33" },
  ]
  const fingerCompact: FingerStick[] = [
    { i: 8, value: 6.2, label: "09:30" },
    { i: 50, value: 9.9, label: "16:33" },
    { i: 62, value: 7.8, label: "20:15" },
  ]

  // 7-day aggregates per day
  const dailyAggregate = [
    { day: 'пн', date: '27', carbs: 198, insulin: 4.2, sticks: 3, meals: 5 },
    { day: 'вт', date: '28', carbs: 145, insulin: 3.1, sticks: 2, meals: 4 },
    { day: 'ср', date: '29', carbs: 240, insulin: 5.8, sticks: 1, meals: 6 },
    { day: 'чт', date: '30', carbs: 178, insulin: 3.6, sticks: 2, meals: 5 },
    { day: 'пт', date: '01', carbs:  95, insulin: 1.0, sticks: 0, meals: 3 },
    { day: 'сб', date: '02', carbs: 156, insulin: 2.8, sticks: 1, meals: 4 },
    { day: 'вс', date: '03', carbs: 111, insulin: 1.6, sticks: 2, meals: 4 },
  ]
  const maxDayCarbs = Math.max(...dailyAggregate.map(d => d.carbs))
  const maxDayIns = Math.max(...dailyAggregate.map(d => d.insulin))

  const mealEpisodes = density === 'compact' ? mealEpisodesCompact : mealEpisodesFull
  const insulinShots = density === 'compact' ? insulinCompact : insulinFull
  const fingerSticks = density === 'compact' ? fingerCompact : fingerFull

  // x-axis time labels per timeRange
  const xLabels = (() => {
    if (timeRange === '7Д') return ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс']
    if (timeRange === '24Ч') return ['00', '04', '08', '12', '16', '20', '24']
    if (timeRange === '12Ч') return ['08', '10', '12', '14', '16', '18', '20']
    if (timeRange === '3Ч') return ['15:00', '15:30', '16:00', '16:30', '17:00', '17:30', '18:00']
    return ['12:00', '13:00', '14:00', '15:00', '16:00', '17:00', '18:00'] // 6Ч default
  })()

  function GlucoseChart() {
    const hovered =
      density !== 'aggregate' && hoveredEpisode >= 0 && hoveredEpisode < mealEpisodes.length
        ? mealEpisodes[hoveredEpisode]
        : null

    return (
      <svg
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="xMidYMid meet"
        style={{ display: "block", width: "100%" }}
      >
        {/* ====== CHART ZONE ====== */}
        {/* gridlines + y-axis labels */}
        {[3.9, 6.5, 9.3, 12].map((g, i) => (
          <g key={i}>
            <line
              x1={padL} x2={W - padR}
              y1={yToY(g)} y2={yToY(g)}
              stroke={g === 3.9 || g === 9.3 ? "var(--accent-soft)" : "var(--hairline)"}
              strokeDasharray={g === 3.9 || g === 9.3 ? "0" : "2 4"}
            />
            <text
              x={padL - 6} y={yToY(g) + 3}
              textAnchor="end" fontFamily="var(--mono)" fontSize="10" fill="var(--ink-4)"
            >{g}</text>
          </g>
        ))}
        {/* target band */}
        <rect
          x={padL} y={yToY(9.3)}
          width={innerW} height={yToY(3.9) - yToY(9.3)}
          fill="var(--accent-bg)" opacity="0.35"
        />
        <text
          x={padL + 8} y={yToY(9.3) + 12}
          fontFamily="var(--mono)" fontSize="9" fill="var(--accent)"
        >целевой 3.9–9.3</text>

        {/* hovered episode: range fill on chart */}
        {hovered && (
          <>
            <rect
              x={iToX(hovered.iStart)}
              y={chartTop}
              width={Math.max(4, iToX(hovered.iEnd) - iToX(hovered.iStart))}
              height={chartH}
              fill="var(--accent)" opacity="0.10"
            />
            {/* connector from peak point on curve down to lane pill */}
            <line
              x1={iToX(hovered.peakI)}
              x2={iToX(hovered.peakI)}
              y1={yToY(cgmNorm[hovered.peakI].y)}
              y2={lane1Y + laneH / 2}
              stroke="var(--accent)" strokeDasharray="2 3" strokeWidth="1" opacity="0.7"
            />
            {/* peak marker */}
            <circle
              cx={iToX(hovered.peakI)}
              cy={yToY(cgmNorm[hovered.peakI].y)}
              r="4" fill="var(--surface)"
              stroke="var(--accent)" strokeWidth="1.6"
            />
            <text
              x={iToX(hovered.peakI) + 8}
              y={yToY(cgmNorm[hovered.peakI].y) - 4}
              fontFamily="var(--mono)" fontSize="10" fill="var(--accent)" fontWeight="500"
            >пик {cgmNorm[hovered.peakI].y.toFixed(1)}</text>
          </>
        )}

        {/* CGM lines */}
        {showRaw && (
          <path d={rawPath} fill="none" stroke="var(--ink-3)" strokeWidth="1" strokeDasharray="2 2" opacity="0.7" />
        )}
        {showNorm && (
          <path d={normPath} fill="none" stroke="var(--ink)" strokeWidth="1.6" />
        )}

        {/* fingerstick diamond on curve */}
        {fingerSticks.map((fs, i) => (
          <g key={i}>
            <rect
              x={iToX(fs.i) - 5} y={yToY(fs.value) - 5}
              width="10" height="10"
              transform={`rotate(45 ${iToX(fs.i)} ${yToY(fs.value)})`}
              fill="var(--surface)" stroke="var(--ink)" strokeWidth="1.4"
            />
          </g>
        ))}

        {/* "now" line + dot */}
        <line
          x1={iToX(cgmRaw.length - 1)} x2={iToX(cgmRaw.length - 1)}
          y1={chartTop} y2={chartBottom}
          stroke="var(--ink)" strokeWidth="1"
        />
        <circle
          cx={iToX(cgmRaw.length - 1)}
          cy={yToY(cgmNorm[cgmNorm.length - 1].y)}
          r="4" fill="var(--ink)"
        />

        {/* ====== LANES ZONE ====== */}
        {/* lane background lines + left labels (always present) */}
        {[
          { y: lane1Y, label: 'Питание' },
          { y: lane2Y, label: 'Инсулин' },
          { y: lane3Y, label: 'Калибровка' },
        ].map((l, i) => (
          <g key={i}>
            <text
              x={padL - 6} y={l.y + laneH / 2 + 4}
              textAnchor="end" fontFamily="var(--sans)" fontSize="10"
              fill="var(--ink-4)" fontWeight="500"
            >{l.label}</text>
            <line
              x1={padL} x2={W - padR}
              y1={l.y + laneH / 2} y2={l.y + laneH / 2}
              stroke="var(--hairline)" strokeWidth="0.8"
            />
          </g>
        ))}

        {density === 'aggregate' ? (
          /* ====== AGGREGATE MODE (7Д) — per-day bars ====== */
          dailyAggregate.map((d, i) => {
            const colW = innerW / dailyAggregate.length
            const cx = padL + i * colW + colW / 2
            // lane 1: carbs bar
            const carbsBarH = (d.carbs / maxDayCarbs) * (laneH - 8)
            const insBarH = d.insulin > 0 ? (d.insulin / maxDayIns) * (laneH - 8) : 0
            const isHov = hoveredEpisode === i
            return (
              <g
                key={i}
                style={{ cursor: 'pointer' }}
                onMouseEnter={() => setHoveredEpisode(i)}
                onMouseLeave={() => setHoveredEpisode(-1)}
              >
                {/* full-day hover background */}
                {isHov && (
                  <rect
                    x={cx - colW / 2 + 2} y={chartTop}
                    width={colW - 4} height={lanesBottom - chartTop}
                    fill="var(--accent)" opacity="0.05"
                  />
                )}
                {/* lane 1: carbs */}
                <rect
                  x={cx - colW * 0.28} y={lane1Y + (laneH - 4) - carbsBarH}
                  width={colW * 0.56} height={carbsBarH}
                  fill={isHov ? 'var(--accent)' : 'var(--accent-soft)'}
                  stroke={isHov ? 'var(--accent)' : 'none'}
                />
                <text
                  x={cx} y={lane1Y - 2}
                  textAnchor="middle" fontFamily="var(--mono)" fontSize="10"
                  fill={isHov ? 'var(--accent)' : 'var(--ink-2)'} fontWeight="500"
                >{d.carbs}</text>
                <text
                  x={cx} y={lane1Y + laneH + 10}
                  textAnchor="middle" fontFamily="var(--mono)" fontSize="9"
                  fill="var(--ink-4)"
                >{d.meals} приёмов</text>

                {/* lane 2: insulin */}
                {insBarH > 0 ? (
                  <rect
                    x={cx - colW * 0.18} y={lane2Y + (laneH - 4) - insBarH}
                    width={colW * 0.36} height={insBarH}
                    fill={isHov ? 'var(--ink)' : 'var(--ink-3)'}
                  />
                ) : (
                  <line
                    x1={cx - 6} x2={cx + 6}
                    y1={lane2Y + laneH - 4} y2={lane2Y + laneH - 4}
                    stroke="var(--hairline-2)" strokeWidth="1"
                  />
                )}
                <text
                  x={cx} y={lane2Y - 2}
                  textAnchor="middle" fontFamily="var(--mono)" fontSize="10"
                  fill={isHov ? 'var(--ink)' : 'var(--ink-2)'} fontWeight="500"
                >{d.insulin > 0 ? d.insulin.toFixed(1) : '—'}</text>

                {/* lane 3: stick count as a number */}
                <text
                  x={cx} y={lane3Y + laneH / 2 + 4}
                  textAnchor="middle" fontFamily="var(--mono)" fontSize="13"
                  fill={d.sticks > 0 ? (isHov ? 'var(--ink)' : 'var(--ink-2)') : 'var(--ink-4)'}
                  fontWeight={500}
                >{d.sticks}</text>
              </g>
            )
          })
        ) : density === 'compact' ? (
          /* ====== COMPACT MODE (12Ч / 24Ч) — dots + ticks ====== */
          <>
            {/* lane 1: meal dots scaled by carbs */}
            {mealEpisodes.map((ep, idx) => {
              const cx = (iToX(ep.iStart) + iToX(ep.iEnd)) / 2
              const cy = lane1Y + laneH / 2
              const r = Math.max(3, Math.min(11, 2 + Math.sqrt(ep.carbs) * 0.9))
              const isHov = hoveredEpisode === idx
              const tip = `${ep.label} · ${ep.carbs} г · ${ep.events.length} ${ep.events.length === 1 ? 'событие' : 'событий'}`
              return (
                <g
                  key={idx}
                  style={{ cursor: 'pointer' }}
                  onMouseEnter={() => setHoveredEpisode(idx)}
                  onMouseLeave={() => setHoveredEpisode(-1)}
                >
                  <circle
                    cx={cx} cy={cy} r={r}
                    fill={isHov ? 'var(--accent)' : 'var(--accent-bg)'}
                    stroke="var(--accent-soft)"
                    strokeWidth={isHov ? 1.5 : 1}
                  >
                    <title>{tip}</title>
                  </circle>
                  {/* duration tail for meals lasting >1 chart unit */}
                  {ep.iEnd - ep.iStart >= 2 && (
                    <line
                      x1={iToX(ep.iStart)} x2={iToX(ep.iEnd)}
                      y1={cy} y2={cy}
                      stroke={isHov ? 'var(--accent)' : 'var(--accent-soft)'}
                      strokeWidth="2.5" opacity="0.8"
                    />
                  )}
                </g>
              )
            })}
            {/* lane 2: insulin tiny ticks */}
            {insulinShots.map((shot, i) => {
              const x = iToX(shot.i)
              return (
                <g key={i}>
                  <rect
                    x={x - 1} y={lane2Y + 6}
                    width="2" height={laneH - 12}
                    fill="var(--ink)"
                  >
                    <title>{`${shot.label} · ${shot.units} ЕД`}</title>
                  </rect>
                </g>
              )
            })}
            {/* lane 3: small fingerstick diamonds */}
            {fingerSticks.map((fs, i) => {
              const x = iToX(fs.i)
              const cy = lane3Y + laneH / 2
              return (
                <g key={i}>
                  <rect
                    x={x - 4} y={cy - 4}
                    width="8" height="8"
                    transform={`rotate(45 ${x} ${cy})`}
                    fill="var(--surface)" stroke="var(--ink)" strokeWidth="1.2"
                  >
                    <title>{`${fs.label} · ${fs.value} ммоль/л`}</title>
                  </rect>
                </g>
              )
            })}
            {/* density hint at the right edge */}
            <text
              x={W - padR} y={lane1Y - 2}
              textAnchor="end" fontFamily="var(--mono)" fontSize="9"
              fill="var(--ink-4)" fontStyle="italic"
            >{mealEpisodes.length} приёмов · наведите для деталей</text>
          </>
        ) : (
          /* ====== FULL MODE (3Ч / 6Ч) — pills with internal events ====== */
          <>
            {mealEpisodes.map((ep, idx) => {
              const x1 = iToX(ep.iStart)
              const x2 = iToX(ep.iEnd)
              const pillW = Math.max(14, x2 - x1)
              const pillX = x1 - 4
              const isHov = hoveredEpisode === idx
              const totalC = ep.events.reduce((s, e) => s + e.c, 0)
              return (
                <g
                  key={idx}
                  style={{ cursor: 'pointer' }}
                  onMouseEnter={() => setHoveredEpisode(idx)}
                  onMouseLeave={() => setHoveredEpisode(-1)}
                >
                  <rect
                    x={pillX} y={lane1Y + 3}
                    width={pillW + 8} height={laneH - 6}
                    rx={(laneH - 6) / 2}
                    fill={isHov ? 'var(--accent)' : 'var(--accent-bg)'}
                    stroke={isHov ? 'var(--accent)' : 'var(--accent-soft)'} strokeWidth="1"
                    style={{ transition: 'fill .15s' }}
                  />
                  {ep.events.map((e, ei) => {
                    const ex = iToX(e.i)
                    const r = Math.max(2, Math.min(5, (e.c / totalC) * 16))
                    return (
                      <circle
                        key={ei}
                        cx={ex} cy={lane1Y + laneH / 2}
                        r={r}
                        fill={isHov ? 'var(--surface)' : 'var(--accent)'}
                      />
                    )
                  })}
                  <text
                    x={pillX + (pillW + 8) / 2}
                    y={lane1Y - 2}
                    textAnchor="middle"
                    fontFamily="var(--mono)" fontSize="10"
                    fill={isHov ? 'var(--accent)' : 'var(--ink-2)'}
                    fontWeight="500"
                  >{ep.carbs} г</text>
                  <text
                    x={pillX + (pillW + 8) / 2}
                    y={lane1Y + laneH + 10}
                    textAnchor="middle"
                    fontFamily="var(--mono)" fontSize="9" fill="var(--ink-4)"
                  >{ep.events.length} событий · {ep.label}</text>
                </g>
              )
            })}
            {insulinShots.map((shot, i) => {
              const x = iToX(shot.i)
              return (
                <g key={i}>
                  <rect
                    x={x - 1.5} y={lane2Y + 4}
                    width="3" height={laneH - 8}
                    fill="var(--ink)"
                  />
                  <rect
                    x={x + 5} y={lane2Y + 6}
                    width="38" height="18" rx="2"
                    fill="var(--surface)" stroke="var(--ink)" strokeWidth="1"
                  />
                  <text
                    x={x + 24} y={lane2Y + 18}
                    textAnchor="middle" fontFamily="var(--mono)" fontSize="10"
                    fill="var(--ink)" fontWeight="500"
                  >{shot.units} ЕД</text>
                  <text
                    x={x - 4} y={lane2Y + laneH + 10}
                    textAnchor="end" fontFamily="var(--mono)" fontSize="9"
                    fill="var(--ink-4)"
                  >{shot.label}</text>
                </g>
              )
            })}
            {fingerSticks.map((fs, i) => {
              const x = iToX(fs.i)
              const cy = lane3Y + laneH / 2
              return (
                <g key={i}>
                  <rect
                    x={x - 5} y={cy - 5}
                    width="10" height="10"
                    transform={`rotate(45 ${x} ${cy})`}
                    fill="var(--surface)" stroke="var(--ink)" strokeWidth="1.4"
                  />
                  <text
                    x={x + 12} y={cy + 4}
                    fontFamily="var(--mono)" fontSize="10"
                    fill="var(--ink)" fontWeight="500"
                  >{fs.value} ммоль</text>
                  <text
                    x={x - 4} y={lane3Y + laneH + 10}
                    textAnchor="end" fontFamily="var(--mono)" fontSize="9"
                    fill="var(--ink-4)"
                  >{fs.label}</text>
                </g>
              )
            })}
          </>
        )}

        {/* shared x-axis time labels */}
        {xLabels.map((label, i) => {
          const ratio = i / (xLabels.length - 1)
          const x = padL + ratio * innerW
          return (
            <text
              key={i}
              x={x}
              y={H - 4}
              textAnchor="middle"
              fontFamily="var(--mono)" fontSize="9"
              fill="var(--ink-4)"
            >{label}</text>
          )
        })}

        {/* unused but reserved */}
        <g style={{ display: 'none' }} data-w={lanesLabelW} />
      </svg>
    )
  }

  function SensorOffsetChart() {
    const w = 960, h = 150
    const pL = 36, pR = 16, pT = 14, pB = 22
    const iH = h - pT - pB, iW = w - pL - pR
    const min = -0.2, max = 1.3
    const yToYS = (v: number) => pT + iH - ((v - min) / (max - min)) * iH
    const path = offsetPts.map((p, i) => `${i === 0 ? "M" : "L"}${(pL + (i / (offsetPts.length - 1)) * iW).toFixed(1)},${yToYS(p.y).toFixed(1)}`).join(" ")
    return (
      <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="xMidYMid meet" style={{ display: "block", width: "100%" }}>
        {[0, 0.5, 1.0].map((v, i) => (
          <g key={i}>
            <line x1={pL} x2={w - pR} y1={yToYS(v)} y2={yToYS(v)} stroke="var(--hairline)" strokeDasharray={v === 0 ? "0" : "2 4"} />
            <text x={pL - 6} y={yToYS(v) + 3} textAnchor="end" fontFamily="var(--mono)" fontSize="9" fill="var(--ink-4)">{v.toFixed(1)}</text>
          </g>
        ))}
        <rect x={pL} y={pT} width={(48 / 65) * iW} height={iH} fill="var(--accent-bg)" opacity="0.3" />
        <text x={pL + (48 / 65) * iW - 4} y={pT + 10} textAnchor="end" fontFamily="var(--mono)" fontSize="9" fill="var(--accent)">прогрев 48ч</text>
        <path d={path} fill="none" stroke="var(--ink)" strokeWidth="1.5" />
        {[8, 18, 26, 34, 44, 52].map((i) => (
          <polygon key={i} points={`${pL + (i / 60) * iW},${yToYS(offsetPts[i].y) - 5} ${pL + (i / 60) * iW - 4},${yToYS(offsetPts[i].y) + 2} ${pL + (i / 60) * iW + 4},${yToYS(offsetPts[i].y) + 2}`} fill="var(--accent)" />
        ))}
        {[0, 16, 32, 48, 65].map((d, i) => (
          <text key={i} x={pL + (d / 65) * iW} y={h - 6} textAnchor="middle" fontFamily="var(--mono)" fontSize="9" fill="var(--ink-4)">
            {d === 0 ? "0ч" : d === 65 ? "2.7д" : `${d}ч`}
          </text>
        ))}
      </svg>
    )
  }

  return (
    <div style={{ display: 'flex', height: '100%' }}>
      <div style={{ flex: 1, overflow: 'auto' }}>
        <div className="gt-page">
          <PageHead crumbs={["глюкоза", "локальный контекст"]} title="Глюкоза" right={
            <div className="row gap-8">
              <button className="btn"><I.Plus size={13} /> Запись из пальца</button>
              <button className="btn" onClick={() => setShowSensorPanel(!showSensorPanel)}
                style={showSensorPanel ? { background: 'var(--ink)', color: 'var(--ink-fg)', borderColor: 'var(--ink)' } : {}}>
                <I.Cog size={13} /> Сенсор
              </button>
              <button className="btn"><I.Refresh size={13} /></button>
            </div>
          } />

          {/* hero summary */}
          <div className="card" style={{ marginBottom: 22, overflow: "hidden" }}>
            <div className="row" style={{ alignItems: "stretch" }}>
              <div style={{ padding: "20px 22px", borderRight: "1px solid var(--hairline)", minWidth: 200 }}>
                <div className="lbl">сейчас</div>
                <div className="row gap-6" style={{ alignItems: "baseline", marginTop: 6 }}>
                  <span className="g-now">9.8</span>
                  <span style={{ fontSize: 12, color: "var(--ink-3)" }}>ммоль/л</span>
                </div>
                <div className="row gap-6" style={{ alignItems: "center", marginTop: 6 }}>
                  <span className="tag accent"><I.Up size={10} /> +0.6 за 15 мин</span>
                </div>
              </div>
              <div style={{ padding: "20px 22px", borderRight: "1px solid var(--hairline)", flex: 1 }}>
                <div className="lbl">время в диапазоне · 24ч</div>
                <div className="row" style={{ height: 8, marginTop: 12, borderRadius: 1, overflow: "hidden" }}>
                  <div style={{ width: "4%", background: "var(--warn)" }} />
                  <div style={{ width: "68%", background: "var(--good)" }} />
                  <div style={{ width: "26%", background: "var(--accent)" }} />
                  <div style={{ width: "2%", background: "var(--ink)" }} />
                </div>
                <div className="row" style={{ marginTop: 8, gap: 14, fontSize: 11, color: "var(--ink-3)" }}>
                  <span><span className="dot-marker" style={{ background: "var(--warn)" }} /> &lt;3.9 <b className="mono" style={{ color: "var(--ink)", fontWeight: 500, marginLeft: 4 }}>4%</b></span>
                  <span><span className="dot-marker" style={{ background: "var(--good)" }} /> 3.9–9.3 <b className="mono" style={{ color: "var(--ink)", fontWeight: 500, marginLeft: 4 }}>68%</b></span>
                  <span><span className="dot-marker" style={{ background: "var(--accent)" }} /> 9.3–13 <b className="mono" style={{ color: "var(--ink)", fontWeight: 500, marginLeft: 4 }}>26%</b></span>
                  <span><span className="dot-marker" style={{ background: "var(--ink)" }} /> &gt;13 <b className="mono" style={{ color: "var(--ink)", fontWeight: 500, marginLeft: 4 }}>2%</b></span>
                </div>
              </div>
              <div style={{ padding: "20px 22px", minWidth: 240, cursor: "pointer" }} onClick={() => setShowSensorPanel(!showSensorPanel)}>
                <div className="row" style={{ justifyContent: "space-between", alignItems: "baseline" }}>
                  <span className="lbl">сенсор {currentSensor.name}</span>
                  <span className="tag good">актив.</span>
                </div>
                <div className="row gap-6" style={{ alignItems: "baseline", marginTop: 6 }}>
                  <span className="mono" style={{ fontSize: 26, fontWeight: 500 }}>{currentSensor.day}</span>
                  <span style={{ fontSize: 12, color: "var(--ink-3)" }}>/ {currentSensor.maxDays} дней</span>
                </div>
                <div className="pbar" style={{ marginTop: 8 }}><i style={{ width: `${(currentSensor.day / currentSensor.maxDays * 100)}%` }} /></div>
                <div className="row" style={{ marginTop: 6, fontSize: 11, color: "var(--ink-3)", justifyContent: "space-between" }}>
                  <span>{currentSensor.phase}</span>
                  <span className="mono">{currentSensor.quality}/100</span>
                </div>
              </div>
            </div>
            <div className="row" style={{ borderTop: "1px solid var(--hairline)", padding: "10px 22px", gap: 24, fontSize: 11, color: "var(--ink-3)", alignItems: "center" }}>
              <span>смещ. <b className="mono" style={{ color: "var(--ink)", fontWeight: 500 }}>{currentSensor.offset} ммоль/л</b></span>
              <span>ккал <b className="mono" style={{ color: "var(--ink)", fontWeight: 500 }}>1587</b></span>
              <span>TDEE <b className="mono" style={{ color: "var(--ink)", fontWeight: 500 }}>2829</b></span>
              <span>шаги <b className="mono" style={{ color: "var(--ink)", fontWeight: 500 }}>0</b></span>
              <span>баланс <b className="mono" style={{ color: "var(--good)", fontWeight: 500 }}>−1242</b></span>
              <span className="spacer" />
              <span style={{ color: "var(--ink-4)" }}>raw CGM сохранён без изменений · нормализация только на отображение</span>
            </div>
          </div>

          {/* chart card */}
          <div className="card" style={{ marginBottom: 22 }}>
            <div className="card-head">
              <div>
                <div className="lbl">график глюкозы</div>
                <h3>Последние 6 часов</h3>
              </div>
              <div className="row gap-12" style={{ alignItems: "center" }}>
                <SegmentedControl items={["3Ч", "6Ч", "12Ч", "24Ч", "7Д"]} value={timeRange} onChange={setTimeRange} />
                <SegmentedControl items={["RAW", "СГЛАЖ.", "НОРМ."]} value={displayMode} onChange={setDisplayMode} />
              </div>
            </div>
            <div style={{ padding: "10px 12px 14px" }}>
              <GlucoseChart />
            </div>
            <div className="row" style={{ borderTop: "1px solid var(--hairline)", padding: "10px 22px", gap: 18, fontSize: 11, color: "var(--ink-3)", alignItems: "center", flexWrap: 'wrap' }}>
              <span className="row gap-6" style={{ alignItems: "center" }}><span style={{ width: 18, height: 1.6, background: "var(--ink)", display: "inline-block" }} /> норм.</span>
              <span className="row gap-6" style={{ alignItems: "center" }}><span style={{ width: 18, height: 1, borderTop: "1px dashed var(--ink-3)", display: "inline-block" }} /> raw CGM</span>
              <span className="row gap-6" style={{ alignItems: "center" }}>
                <span style={{ width: 22, height: 10, background: "var(--accent-bg)", border: "1px solid var(--accent-soft)", borderRadius: 5, display: "inline-block" }} />
                приём пищи (длительность · события)
              </span>
              <span className="row gap-6" style={{ alignItems: "center" }}><span style={{ width: 3, height: 10, background: "var(--ink)", display: "inline-block" }} /> инсулин</span>
              <span className="row gap-6" style={{ alignItems: "center" }}><span style={{ width: 8, height: 8, background: "var(--surface)", border: "1.4px solid var(--ink)", transform: "rotate(45deg)", display: "inline-block" }} /> запись из пальца</span>
              <span className="spacer" />
              <span className="mono" style={{ color: "var(--ink-4)" }}>02 май · 12:02 — 18:02 · наведите на пилюлю / эпизод</span>
            </div>
          </div>

          {/* Episodes / events + Sensor offset side by side */}
          <div className="row gap-16" style={{ marginBottom: 28, alignItems: "flex-start" }}>
            <div className="card" style={{ flex: 1, minWidth: 0 }}>
              <div className="card-head">
                <div>
                  <div className="lbl">контекст графика</div>
                  <h3>Активность · эпизоды</h3>
                </div>
                <SegmentedControl items={["Эпизоды", "События"]} value={contextTab} onChange={setContextTab} />
              </div>
              <div style={{ padding: "6px 18px 14px" }}>
                {contextTab === "Эпизоды" ? (
                  glucoseEpisodes.map((ep, i) => (
                    <div key={i}>
                      <div className="row clickable-row"
                        onClick={() => setExpandedEp(expandedEp === i ? -1 : i)}
                        onMouseEnter={() => setHoveredEpisode(i)}
                        onMouseLeave={() => setHoveredEpisode(-1)}
                        style={{
                        alignItems: "stretch", padding: "12px 0", gap: 16,
                        borderBottom: i === 0 ? "1px solid var(--hairline)" : "none",
                        background: hoveredEpisode === i || ep.active ? "var(--surface-2)" : "transparent",
                        boxShadow: hoveredEpisode === i ? "inset 2px 0 0 var(--accent)" : "none",
                        margin: ep.active || hoveredEpisode === i ? "0 -18px" : 0,
                        paddingLeft: ep.active || hoveredEpisode === i ? 18 : 0,
                        paddingRight: ep.active || hoveredEpisode === i ? 18 : 0,
                        cursor: 'pointer',
                        transition: 'background .15s',
                      }}>
                        <div className="mono" style={{ width: 92, fontSize: 11, color: "var(--ink-3)" }}>{ep.time}</div>
                        <div style={{ flex: 1 }}>
                          <div className="row gap-8" style={{ alignItems: "center" }}>
                            <span style={{ fontSize: 13, fontWeight: 500 }}>Приём пищи</span>
                            <span className="tag">{ep.events} событий</span>
                          </div>
                          <div style={{ fontSize: 11, color: "var(--ink-3)", marginTop: 3 }}>{ep.names}</div>
                        </div>
                        <div style={{ width: 100, textAlign: "right" }}>
                          <div className="mono" style={{ fontSize: 13, fontWeight: 500 }}>{ep.carbs}</div>
                          <div className="mono" style={{ fontSize: 11, color: "var(--ink-3)", marginTop: 2 }}>{ep.kcal} ккал</div>
                        </div>
                        <div style={{ width: 220 }}>
                          <div style={{ fontSize: 11, color: "var(--ink-3)" }}>{ep.peak}</div>
                          <div className="mono" style={{ fontSize: 11, marginTop: 2, color: "var(--accent)" }}>инсулин {ep.insulin}</div>
                        </div>
                        <div style={{ color: 'var(--ink-4)', transform: expandedEp === i ? 'rotate(180deg)' : 'none', transition: 'transform 0.15s', display: 'flex', alignItems: 'center' }}>
                          <I.ChevD size={14} />
                        </div>
                      </div>
                      {expandedEp === i && episodeDetails[i] && (
                        <div style={{ padding: "0 0 8px", marginLeft: 92, borderBottom: i === 0 ? "1px solid var(--hairline)" : "none" }}>
                          {episodeDetails[i].map((d, j) => (
                            <div key={j} className="row" style={{ padding: "6px 0", gap: 14, alignItems: "center", fontSize: 12 }}>
                              <span className="mono" style={{ fontSize: 10, color: "var(--ink-4)", width: 48 }}>{d.time}</span>
                              <span style={{ flex: 1, color: d.insulin ? "var(--ink-4)" : "var(--ink-3)" }}>{d.t}</span>
                              <span className="mono" style={{ fontSize: 11, width: 60, textAlign: "right", color: "var(--ink-3)" }}>{d.c}</span>
                              <span className="mono" style={{ fontSize: 11, width: 70, textAlign: "right" }}>{d.k}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  ))
                ) : (
                  rawEvents.map((ev, i) => (
                    <div key={i} className="row" style={{ padding: "8px 0", gap: 14, alignItems: "center", borderBottom: i < rawEvents.length - 1 ? "1px solid var(--hairline)" : "none" }}>
                      <span className="mono" style={{ fontSize: 11, color: "var(--ink-3)", width: 48 }}>{ev.time}</span>
                      <span className="tag" style={{ fontSize: 9, width: 72, justifyContent: 'center' }}>{ev.type}</span>
                      <span style={{ flex: 1, fontSize: 13, color: ev.type === "insulin" ? "var(--ink-3)" : "var(--ink)" }}>{ev.title}</span>
                      <span className="mono" style={{ fontSize: 12, width: 60, textAlign: "right", color: "var(--ink-3)" }}>{ev.carbs}</span>
                      <span className="mono" style={{ fontSize: 12, width: 80, textAlign: "right", fontWeight: 500 }}>{ev.kcal}</span>
                    </div>
                  ))
                )}
              </div>
            </div>

            {/* Sensor offset */}
            <div className="card" style={{ width: 420, flex: "0 0 420px" }}>
              <div className="card-head">
                <div>
                  <div className="lbl">raw CGM сохраняется без изменений</div>
                  <h3>Смещение сенсора</h3>
                </div>
                <span className="mono" style={{ fontSize: 11, color: "var(--ink-3)" }}>текущее <b style={{ color: "var(--ink)", fontWeight: 500 }}>{currentSensor.offset} ммоль/л</b></span>
              </div>
              <div style={{ padding: "10px 12px 14px" }}>
                <SensorOffsetChart />
              </div>
            </div>
          </div>
        </div>
      </div>

      {showSensorPanel && (
        <RightPanel onClose={() => setShowSensorPanel(false)}>
          <SensorPanel />
        </RightPanel>
      )}
    </div>
  )
}
