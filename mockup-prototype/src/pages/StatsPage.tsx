import {
  tdee,
  calorieGoal,
  days7,
  carbs14,
  carbs14avg,
  mealHeatmap6x7,
  tirDays,
  dayparts,
} from '../mock/stats'

const COLOR_BELOW = 'oklch(0.72 0.07 240)' // muted blue
const COLOR_IN = 'oklch(0.72 0.08 145)'    // sage green
const COLOR_ABOVE = 'oklch(0.78 0.09 65)'  // muted amber

export default function StatsPage() {
  const filled7 = days7.filter(d => d.intake > 0)
  const cumDef = filled7.reduce((a, d) => a + (d.intake - tdee), 0)
  const avgIntake = Math.round(filled7.reduce((a, d) => a + d.intake, 0) / filled7.length)
  const todayIntake = days7[days7.length - 1].intake
  const todayBal = todayIntake - tdee
  const todayCarbs = days7[days7.length - 1].carbs
  const todayGi = 38
  const macroScore = 22
  const c14max = Math.max(...carbs14)

  // ---------- Header / narrative ----------
  function Header() {
    return (
      <div style={{ marginBottom: 24 }}>
        <div
          style={{
            fontSize: 9,
            letterSpacing: '0.18em',
            textTransform: 'uppercase',
            color: 'var(--ink-4)',
            marginBottom: 6,
            fontWeight: 500,
          }}
        >
          статистика
        </div>
        <h1
          style={{
            fontFamily: 'var(--serif)',
            fontSize: 30,
            fontWeight: 400,
            margin: 0,
            letterSpacing: '-0.02em',
            lineHeight: 1.1,
          }}
        >
          3 мая 2026 г.
        </h1>
        <h2
          style={{
            fontFamily: 'var(--serif)',
            fontSize: 26,
            fontWeight: 400,
            margin: '4px 0 6px',
            letterSpacing: '-0.01em',
            lineHeight: 1.2,
          }}
        >
          Дефицит{' '}
          <span style={{ fontFamily: 'var(--mono)', color: 'var(--ink)' }}>
            4&nbsp;226
          </span>{' '}
          ккал за неделю
        </h2>
        <div
          style={{
            fontFamily: 'var(--mono)',
            fontSize: 11,
            color: 'var(--ink-3)',
            display: 'flex',
            gap: 18,
            flexWrap: 'wrap',
          }}
        >
          <span>
            <span style={{ color: 'var(--ink-4)' }}>среднее</span>{' '}
            <b style={{ color: 'var(--ink)' }}>{avgIntake}</b> ккал/день
          </span>
          <span style={{ color: 'var(--hairline-2)' }}>·</span>
          <span>
            <span style={{ color: 'var(--ink-4)' }}>сегодня</span>{' '}
            <b style={{ color: 'var(--ink)' }}>{todayIntake}</b>
          </span>
          <span style={{ color: 'var(--hairline-2)' }}>·</span>
          <span>
            <span style={{ color: 'var(--ink-4)' }}>баланс</span>{' '}
            <b style={{ color: 'var(--ink)' }}>
              {todayBal > 0 ? '+' : ''}
              {todayBal}
            </b>
          </span>
          <span style={{ color: 'var(--hairline-2)' }}>·</span>
          <span>
            <span style={{ color: 'var(--ink-4)' }}>расчётно</span>{' '}
            <b style={{ color: 'var(--ink)' }}>
              ≈ {(Math.abs(cumDef) / 7700).toFixed(2)} кг
            </b>
          </span>
        </div>
      </div>
    )
  }

  // ---------- KPI row ----------
  function KpiRow() {
    const kpis: Array<{
      lbl: string
      val: string | number
      u: string
      sub: string
      pct: number | null
      color?: string
      delta?: { value: string; direction: 'up' | 'down' | 'flat'; tone: 'good' | 'warn' | 'neutral' }
    }> = [
      {
        lbl: 'Углеводы',
        val: todayCarbs,
        u: 'г',
        sub: `сред. за 7 дн. ${carbs14avg} г · лим. 312 г`,
        pct: todayCarbs / 312,
        delta: { value: '−18%', direction: 'down', tone: 'good' },
      },
      {
        lbl: 'Ккал',
        val: todayIntake,
        u: '',
        sub: `цель: ${calorieGoal} · TDEE ${tdee}`,
        pct: todayIntake / calorieGoal,
        color: 'var(--good)',
        delta: { value: '−240', direction: 'down', tone: 'good' },
      },
      {
        lbl: 'ГН',
        val: todayGi,
        u: '',
        sub: 'норма < 100 / день · сред. 72',
        pct: todayGi / 100,
        delta: { value: '−6', direction: 'down', tone: 'good' },
      },
      {
        lbl: 'БЖУ-баланс',
        val: macroScore,
        u: '%',
        sub: 'углеводы 28% · белки 22% · жиры 50%',
        pct: null,
        delta: { value: '+2', direction: 'up', tone: 'neutral' },
      },
    ]
    return (
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, 1fr)',
          gap: 12,
          marginBottom: 16,
        }}
      >
        {kpis.map((k, i) => (
          <div
            key={i}
            style={{
              background: 'var(--surface-2)',
              border: '1px solid var(--hairline)',
              borderRadius: 'var(--radius-lg)',
              padding: '12px 16px 14px',
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'baseline',
                justifyContent: 'space-between',
                marginBottom: 6,
              }}
            >
              <div
                style={{
                  fontSize: 9,
                  letterSpacing: '0.16em',
                  textTransform: 'uppercase',
                  color: 'var(--ink-4)',
                  fontWeight: 500,
                }}
              >
                {k.lbl}
              </div>
              {k.delta && (
                <div
                  style={{
                    fontFamily: 'var(--mono)',
                    fontSize: 10,
                    color:
                      k.delta.tone === 'good'
                        ? 'var(--good)'
                        : k.delta.tone === 'warn'
                          ? 'var(--warn)'
                          : 'var(--ink-3)',
                    fontWeight: 500,
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 2,
                  }}
                  title="Сравнение со средней за прошлую неделю"
                >
                  <span style={{ fontSize: 9 }}>
                    {k.delta.direction === 'up'
                      ? '▲'
                      : k.delta.direction === 'down'
                        ? '▼'
                        : '▬'}
                  </span>
                  {k.delta.value}
                </div>
              )}
            </div>
            <div
              style={{
                fontFamily: 'var(--mono)',
                fontSize: 30,
                fontWeight: 500,
                lineHeight: 1,
                letterSpacing: '-0.01em',
                color: k.color || 'var(--ink)',
              }}
            >
              {k.val}
              {k.u && (
                <span
                  style={{ fontSize: 11, color: 'var(--ink-3)', marginLeft: 3 }}
                >
                  {k.u}
                </span>
              )}
            </div>
            <div
              style={{
                height: 2,
                background: 'var(--hairline)',
                marginTop: 10,
                marginBottom: 10,
              }}
            >
              {k.pct !== null && (
                <div
                  style={{
                    height: '100%',
                    width: `${Math.min(100, k.pct * 100)}%`,
                    background: k.color || 'var(--accent)',
                  }}
                />
              )}
            </div>
            <div
              style={{
                fontFamily: 'var(--mono)',
                fontSize: 10,
                color: 'var(--ink-3)',
                lineHeight: 1.5,
              }}
            >
              {k.sub}
            </div>
          </div>
        ))}
      </div>
    )
  }

  // ---------- Card wrapper ----------
  function Card({
    title,
    headerRight,
    children,
    bodyPad = '14px 18px 18px',
  }: {
    title: React.ReactNode
    headerRight?: React.ReactNode
    children: React.ReactNode
    bodyPad?: string
  }) {
    return (
      <div
        style={{
          background: 'var(--surface-2)',
          border: '1px solid var(--hairline)',
          borderRadius: 'var(--radius-lg)',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'baseline',
            justifyContent: 'space-between',
            padding: '12px 18px 0',
          }}
        >
          <div
            style={{
              fontFamily: 'var(--serif)',
              fontSize: 14,
              fontWeight: 500,
              color: 'var(--ink)',
              letterSpacing: '-0.005em',
            }}
          >
            {title}
          </div>
          {headerRight && (
            <div
              style={{
                fontFamily: 'var(--mono)',
                fontSize: 9,
                letterSpacing: '0.14em',
                textTransform: 'uppercase',
                color: 'var(--ink-4)',
              }}
            >
              {headerRight}
            </div>
          )}
        </div>
        <div style={{ padding: bodyPad }}>{children}</div>
      </div>
    )
  }

  // ---------- Carbs by day ----------
  function CarbsCard() {
    const W = 480,
      H = 200
    const pL = 32,
      pR = 12,
      pT = 16,
      pB = 28
    const iW = W - pL - pR,
      iH = H - pT - pB
    const N = carbs14.length
    const bw = iW / N
    const yMax = 450
    const ticks = [0, 150, 300, 450]
    const avgY = pT + iH - (carbs14avg / yMax) * iH

    return (
      <Card title="Углеводы (г) по дням">
        <svg
          width={W}
          height={H}
          viewBox={`0 0 ${W} ${H}`}
          style={{ display: 'block', width: '100%', height: 'auto' }}
        >
          {ticks.map((t, i) => {
            const y = pT + iH - (t / yMax) * iH
            return (
              <g key={i}>
                <line
                  x1={pL}
                  x2={W - pR}
                  y1={y}
                  y2={y}
                  stroke="var(--hairline)"
                  strokeWidth="1"
                  strokeDasharray={t === 0 ? undefined : '2 3'}
                  opacity={t === 0 ? 1 : 0.6}
                />
                <text
                  x={pL - 6}
                  y={y + 3}
                  textAnchor="end"
                  fontFamily="var(--mono)"
                  fontSize="9"
                  fill="var(--ink-4)"
                >
                  {t}
                </text>
              </g>
            )
          })}
          {carbs14.map((v, i) => {
            const bh = v === 0 ? 0 : Math.max(1.5, (v / yMax) * iH)
            const x = pL + i * bw + bw * 0.18
            const isToday = i === 7 // last filled day
            return (
              <rect
                key={i}
                x={x}
                y={pT + iH - bh}
                width={bw * 0.64}
                height={bh}
                fill={
                  v === 0
                    ? 'var(--hairline)'
                    : isToday
                      ? 'oklch(0.78 0.10 75)'
                      : 'oklch(0.85 0.07 78)'
                }
              />
            )
          })}
          <line
            x1={pL}
            x2={W - pR}
            y1={avgY}
            y2={avgY}
            stroke="var(--accent)"
            strokeDasharray="4 4"
            strokeWidth="1"
          />
          <text
            x={pL + 6}
            y={pT + iH + 18}
            fontFamily="var(--mono)"
            fontSize="9"
            fill="var(--ink-4)"
          >
            25 апр
          </text>
          <text
            x={W - pR - 4}
            y={pT + iH + 18}
            textAnchor="end"
            fontFamily="var(--mono)"
            fontSize="9"
            fill="var(--ink-4)"
          >
            02 май
          </text>
        </svg>
      </Card>
    )
  }

  // ---------- Calorie balance ----------
  function BalanceCard() {
    const Wb = 480,
      Hb = 200
    const pLb = 32,
      pRb = 12,
      pTb = 16,
      pBb = 32
    const iWb = Wb - pLb - pRb,
      iHb = Hb - pTb - pBb
    const maxAbs = 1500
    const midY = pTb + iHb * 0.28
    const visible = days7.filter(d => d.intake > 0)
    const bwb = iWb / visible.length

    return (
      <Card title="Баланс калорий (ккал)" headerRight="02 — 7 дней">
        <svg
          width={Wb}
          height={Hb}
          viewBox={`0 0 ${Wb} ${Hb}`}
          style={{ display: 'block', width: '100%', height: 'auto' }}
        >
          <line
            x1={pLb}
            x2={Wb - pRb}
            y1={midY}
            y2={midY}
            stroke="var(--ink-3)"
            strokeWidth="1"
          />
          <text
            x={pLb - 6}
            y={midY - 3}
            textAnchor="end"
            fontFamily="var(--mono)"
            fontSize="9"
            fill="var(--ink-3)"
          >
            TDEE
          </text>
          {visible.map((d, i) => {
            const cx = pLb + i * bwb + bwb / 2
            const bww = bwb * 0.42
            const bal = d.intake - tdee
            const bh = (Math.abs(bal) / maxAbs) * (iHb * 0.7)
            const y = bal < 0 ? midY : midY - bh
            const h = bh
            const isToday = 'today' in d && d.today
            const fill = isToday
              ? 'var(--ink)'
              : bal < 0
                ? 'oklch(0.78 0.05 145)'
                : 'oklch(0.78 0.06 60)'
            return (
              <g key={i}>
                <rect
                  x={cx - bww / 2}
                  y={y}
                  width={bww}
                  height={Math.max(h, 1)}
                  fill={fill}
                />
                <text
                  x={cx}
                  y={bal < 0 ? y + h - 4 : y + 11}
                  textAnchor="middle"
                  fontFamily="var(--mono)"
                  fontSize="10"
                  fill={isToday ? 'var(--ink-fg)' : 'var(--ink-2)'}
                  fontWeight={500}
                >
                  {bal > 0 ? '+' : ''}
                  {Math.round(bal)}
                </text>
                <text
                  x={cx}
                  y={Hb - 10}
                  textAnchor="middle"
                  fontFamily="var(--sans)"
                  fontSize="11"
                  fill={isToday ? 'var(--ink)' : 'var(--ink-3)'}
                  fontWeight={isToday ? 500 : 400}
                >
                  {d.d}
                </text>
              </g>
            )
          })}
        </svg>
      </Card>
    )
  }

  // ---------- TIR distribution ----------
  function TirCard() {
    const W = 520,
      H = 280
    const pL = 36,
      pR = 12,
      pT = 14,
      pB = 28
    const iW = W - pL - pR,
      iH = H - pT - pB
    const N = tirDays.length
    const bw = iW / N
    const ticks = [0, 50, 100]

    return (
      <Card
        title="Время в диапазоне (TIR)"
        bodyPad="6px 18px 14px"
      >
        <div
          style={{
            fontSize: 11,
            color: 'var(--ink-2)',
            fontWeight: 500,
            marginBottom: 4,
          }}
        >
          Распределение по дням
        </div>
        <div
          style={{
            fontSize: 11,
            color: 'var(--ink-3)',
            lineHeight: 1.4,
            marginBottom: 10,
          }}
        >
          Каждый столбик: один день. Синий: ниже диапазона, зелёный: в
          диапазоне, оранжевый: выше диапазона
        </div>
        <svg
          width={W}
          height={H}
          viewBox={`0 0 ${W} ${H}`}
          style={{ display: 'block', width: '100%', height: 'auto' }}
        >
          {ticks.map((t, i) => {
            const y = pT + iH - (t / 100) * iH
            return (
              <g key={i}>
                <line
                  x1={pL}
                  x2={W - pR}
                  y1={y}
                  y2={y}
                  stroke="var(--hairline)"
                  strokeWidth="1"
                  opacity={t === 0 ? 1 : 0.55}
                />
                <text
                  x={pL - 6}
                  y={y + 3}
                  textAnchor="end"
                  fontFamily="var(--mono)"
                  fontSize="9"
                  fill="var(--ink-4)"
                >
                  {t}%
                </text>
              </g>
            )
          })}
          {tirDays.map((d, i) => {
            const cx = pL + i * bw + bw / 2
            const bww = bw * 0.55
            const x = cx - bww / 2
            const total = d.below + d.inRange + d.above
            const yBelow = pT + iH - (d.below / total) * iH
            const hBelow = (d.below / total) * iH
            const yIn = yBelow - (d.inRange / total) * iH
            const hIn = (d.inRange / total) * iH
            const yAbove = yIn - (d.above / total) * iH
            const hAbove = (d.above / total) * iH
            const showLabel = i % 2 === 0 || i === N - 1
            const tip = `${d.d}\nв диапазоне ${d.inRange}% · ниже ${d.below}% · выше ${d.above}%`
            return (
              <g key={i}>
                <rect
                  x={x}
                  y={yAbove}
                  width={bww}
                  height={hAbove}
                  fill={COLOR_ABOVE}
                >
                  <title>{tip}</title>
                </rect>
                <rect x={x} y={yIn} width={bww} height={hIn} fill={COLOR_IN}>
                  <title>{tip}</title>
                </rect>
                <rect
                  x={x}
                  y={yBelow}
                  width={bww}
                  height={hBelow}
                  fill={COLOR_BELOW}
                >
                  <title>{tip}</title>
                </rect>
                {/* invisible hover target covering full bar */}
                <rect
                  x={x}
                  y={pT}
                  width={bww}
                  height={iH}
                  fill="transparent"
                  style={{ cursor: 'help' }}
                >
                  <title>{tip}</title>
                </rect>
                {showLabel && (
                  <text
                    x={cx}
                    y={pT + iH + 14}
                    textAnchor="middle"
                    fontFamily="var(--mono)"
                    fontSize="9"
                    fill="var(--ink-4)"
                  >
                    {d.d}
                  </text>
                )}
              </g>
            )
          })}
          {/* Target line at 70% TIR */}
          <line
            x1={pL}
            x2={W - pR}
            y1={pT + iH - (70 / 100) * iH}
            y2={pT + iH - (70 / 100) * iH}
            stroke="var(--good)"
            strokeDasharray="4 3"
            strokeWidth="1"
            opacity="0.7"
          />
          <text
            x={W - pR - 4}
            y={pT + iH - (70 / 100) * iH - 3}
            textAnchor="end"
            fontFamily="var(--mono)"
            fontSize="9"
            fill="var(--good)"
          >
            цель ≥70%
          </text>
        </svg>
        <div
          style={{
            display: 'flex',
            gap: 18,
            marginTop: 6,
            fontFamily: 'var(--sans)',
            fontSize: 11,
            color: 'var(--ink-3)',
            flexWrap: 'wrap',
          }}
        >
          <LegendDot color={COLOR_BELOW} label="Ниже диапазона" />
          <LegendDot color={COLOR_IN} label="В диапазоне" />
          <LegendDot color={COLOR_ABOVE} label="Выше диапазона" />
        </div>
      </Card>
    )
  }

  function LegendDot({ color, label }: { color: string; label: string }) {
    return (
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
        <span
          style={{
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: color,
            display: 'inline-block',
          }}
        />
        {label}
      </span>
    )
  }

  // ---------- Daypart profile ----------
  function DaypartCard() {
    return (
      <Card title="Профиль по времени суток (ср. за 7 дней)">
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(3, 1fr)',
            gap: 8,
          }}
        >
          {dayparts.map((d, i) => {
            // tint based on TIR (higher = better = more sage; lower = warmer)
            const warm = d.tir < 60
            const bg = warm
              ? 'oklch(0.96 0.03 75)'
              : 'oklch(0.96 0.025 145)'
            const border = warm
              ? 'oklch(0.88 0.045 75)'
              : 'oklch(0.88 0.04 145)'
            return (
              <div
                key={i}
                style={{
                  background: bg,
                  border: `1px solid ${border}`,
                  borderRadius: 'var(--radius-lg)',
                  padding: '10px 12px 12px',
                  textAlign: 'center',
                }}
              >
                <div
                  style={{
                    fontFamily: 'var(--mono)',
                    fontSize: 10,
                    color: 'var(--ink-3)',
                    marginBottom: 6,
                    letterSpacing: '0.02em',
                  }}
                >
                  {d.range}
                </div>
                <div
                  style={{
                    fontFamily: 'var(--mono)',
                    fontSize: 22,
                    fontWeight: 500,
                    lineHeight: 1,
                    letterSpacing: '-0.01em',
                    color: 'var(--ink)',
                  }}
                >
                  {d.avg.toString().replace('.', ',')}
                </div>
                <div
                  style={{
                    fontSize: 10,
                    color: 'var(--ink-3)',
                    marginTop: 2,
                  }}
                >
                  ммоль/л
                </div>
                <div
                  style={{
                    fontFamily: 'var(--mono)',
                    fontSize: 10,
                    color: warm ? 'var(--warn)' : 'var(--good)',
                    marginTop: 6,
                    fontWeight: 500,
                  }}
                >
                  TIR {d.tir}%
                </div>
              </div>
            )
          })}
        </div>
      </Card>
    )
  }

  // ---------- Meal heatmap (6×7) ----------
  function HeatmapCard() {
    const cols = ['00–04', '04–08', '08–12', '12–16', '16–20', '20–24']
    const rows = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']

    return (
      <Card
        title="Тепловая карта питания (6×7)"
        bodyPad="6px 18px 18px"
      >
        <div
          style={{
            fontSize: 11,
            color: 'var(--ink-3)',
            marginBottom: 12,
            lineHeight: 1.4,
          }}
        >
          Каждая ячейка: 4-часовой блок. Интенсивность отражает приём пищи.
        </div>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 220px',
            gap: 28,
            alignItems: 'start',
          }}
        >
          <div>
            {/* column headers */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: '28px repeat(6, 1fr)',
                gap: 4,
                marginBottom: 4,
              }}
            >
              <div />
              {cols.map(c => (
                <div
                  key={c}
                  style={{
                    fontFamily: 'var(--mono)',
                    fontSize: 9,
                    color: 'var(--ink-4)',
                    textAlign: 'center',
                    letterSpacing: '0.04em',
                  }}
                >
                  {c}
                </div>
              ))}
            </div>
            {/* rows */}
            {rows.map((r, ri) => {
              const isWeekend = ri >= 5
              return (
                <div
                  key={r}
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '28px repeat(6, 1fr)',
                    gap: 4,
                    marginBottom: 4,
                  }}
                >
                  <div
                    style={{
                      fontFamily: 'var(--mono)',
                      fontSize: 10,
                      color: isWeekend ? 'var(--accent)' : 'var(--ink-4)',
                      fontStyle: isWeekend ? 'italic' : 'normal',
                      display: 'flex',
                      alignItems: 'center',
                    }}
                  >
                    {r}
                  </div>
                  {mealHeatmap6x7[ri].map((v, ci) => {
                    const meals = Math.round(v * 4)
                    const carbs = Math.round(v * 90)
                    return (
                      <div
                        key={ci}
                        style={{
                          height: 22,
                          background: heatColor(v),
                          borderRadius: 2,
                          cursor: 'help',
                        }}
                        title={`${r} · ${cols[ci]}\n${meals} ${meals === 1 ? 'приём' : 'приёмов'} · ~${carbs} г углеводов`}
                      />
                    )
                  })}
                </div>
              )
            })}
          </div>
          {/* legend */}
          <div>
            <div
              style={{
                fontSize: 11,
                color: 'var(--ink-2)',
                fontWeight: 500,
                marginBottom: 8,
              }}
            >
              Интенсивность приёмов пищи
            </div>
            <div
              style={{
                height: 10,
                borderRadius: 2,
                background: `linear-gradient(90deg, ${heatColor(0.05)}, ${heatColor(0.5)}, ${heatColor(0.95)})`,
                marginBottom: 6,
              }}
            />
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                fontFamily: 'var(--mono)',
                fontSize: 10,
                color: 'var(--ink-4)',
                marginBottom: 14,
              }}
            >
              <span>Низкая</span>
              <span>Высокая</span>
            </div>
            <div
              style={{
                fontSize: 10,
                color: 'var(--ink-3)',
                lineHeight: 1.5,
              }}
            >
              Больше цвета = больше приёмов пищи или больше углеводов в это
              время
            </div>
          </div>
        </div>
      </Card>
    )
  }

  function heatColor(v: number) {
    if (v < 0.05) return 'var(--shade)'
    return `oklch(${0.94 - v * 0.18} ${0.015 + v * 0.085} 78 / ${0.35 + v * 0.65})`
  }

  // ---------- Bottom service row ----------
  function FooterRow() {
    return (
      <div
        style={{
          marginTop: 18,
          paddingTop: 14,
          borderTop: '1px solid var(--hairline)',
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: 36,
        }}
      >
        <FooterGroup
          title="Качество и полнота данных"
          items={[
            { v: '93%', l: 'с этикеткой', tone: 'ink' },
            { v: '16 из 18', l: 'баз заполнено', tone: 'ink' },
            { v: '2', l: 'вручную добавлено', tone: 'ink' },
            { v: '3', l: 'низкой увер. в анализе', tone: 'warn' },
          ]}
        />
        <FooterGroup
          title="Контекст дня и поведение"
          items={[
            { v: '18,5 ч', l: 'окно питания (сред.)', tone: 'ink' },
            { v: '<1 ч', l: 'с последней еды', tone: 'ink' },
            { v: '7', l: 'записей сегодня', tone: 'ink' },
          ]}
        />
      </div>
    )
  }

  function FooterGroup({
    title,
    items,
  }: {
    title: string
    items: Array<{ v: string; l: string; tone: 'ink' | 'warn' }>
  }) {
    return (
      <div>
        <div
          style={{
            fontSize: 9,
            letterSpacing: '0.16em',
            textTransform: 'uppercase',
            color: 'var(--ink-4)',
            marginBottom: 10,
            fontWeight: 500,
          }}
        >
          {title}
        </div>
        <div
          style={{
            display: 'flex',
            gap: 20,
            flexWrap: 'wrap',
          }}
        >
          {items.map((it, i) => (
            <div
              key={i}
              style={{
                display: 'flex',
                flexDirection: 'column',
                paddingRight: 18,
                borderRight:
                  i === items.length - 1 ? 'none' : '1px solid var(--hairline)',
                minWidth: 78,
              }}
            >
              <div
                style={{
                  fontFamily: 'var(--mono)',
                  fontSize: 14,
                  fontWeight: 500,
                  color: it.tone === 'warn' ? 'var(--warn)' : 'var(--ink)',
                  letterSpacing: '-0.005em',
                }}
              >
                {it.v}
              </div>
              <div
                style={{
                  fontSize: 10,
                  color: 'var(--ink-3)',
                  marginTop: 2,
                  lineHeight: 1.4,
                }}
              >
                {it.l}
              </div>
            </div>
          ))}
        </div>
      </div>
    )
  }

  return (
    <div style={{ padding: '28px 40px 56px' }}>
      <Header />
      <KpiRow />
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: 14,
          marginBottom: 14,
        }}
      >
        <CarbsCard />
        <BalanceCard />
      </div>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: 14,
          marginBottom: 14,
        }}
      >
        <TirCard />
        <DaypartCard />
      </div>
      <HeatmapCard />
      <FooterRow />
    </div>
  )
}
