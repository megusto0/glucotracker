import { useState, useMemo } from 'react'
import { I } from '../components/Icons'
import PageHead from '../components/PageHead'
import SegmentedControl from '../components/SegmentedControl'
import { generateCgmRaw, generateSensorOffset, glucoseEpisodes, episodeDetails, rawEvents } from '../mock/glucose'
import { currentSensor, previousSensors, lastFingerstick } from '../mock/sensors'

export default function GlucosePage() {
  const [timeRange, setTimeRange] = useState("6Ч")
  const [displayMode, setDisplayMode] = useState("НОРМ.")
  const [contextTab, setContextTab] = useState("Эпизоды")
  const [expandedEp, setExpandedEp] = useState(1)

  const cgmRaw = useMemo(() => generateCgmRaw(), [])
  const cgmNorm = useMemo(() => cgmRaw.map((p) => ({ y: p.y + 0.3 })), [cgmRaw])
  const offsetPts = useMemo(() => generateSensorOffset(), [])

  const W = 760, H = 280
  const padL = 38, padR = 16, padT = 28, padB = 28
  const yMin = 3.5, yMax = 12.2
  const innerW = W - padL - padR
  const innerH = H - padT - padB
  const yToY = (y: number) => padT + innerH - ((y - yMin) / (yMax - yMin)) * innerH
  const iToX = (i: number) => padL + (i / (cgmRaw.length - 1)) * innerW

  const rawPath = cgmRaw.map((p, i) => `${i === 0 ? "M" : "L"}${iToX(i).toFixed(1)},${yToY(p.y).toFixed(1)}`).join(" ")
  const normPath = cgmNorm.map((p, i) => `${i === 0 ? "M" : "L"}${iToX(i).toFixed(1)},${yToY(p.y).toFixed(1)}`).join(" ")

  const showRaw = displayMode === "RAW" || displayMode === "НОРМ."
  const showNorm = displayMode === "НОРМ." || displayMode === "СГЛАЖ."

  const events = [
    { i: 18, kind: "meal" as const, label: "14:07 · 21.7 г", title: "Приём пищи" },
    { i: 38, kind: "meal" as const, label: "15:43–16:04 · 64.8 г", title: "Приём пищи", big: true },
    { i: 50, kind: "fingerstick" as const, label: "16:33", value: "9.9" },
    { i: 60, kind: "insulin" as const, label: "17:40", value: "1.6 ЕД" },
  ]

  function GlucoseChart() {
    return (
      <svg width={W} height={H} style={{ display: "block", width: "100%" }}>
        {[3.9, 6.5, 9.3, 12].map((g, i) => (
          <g key={i}>
            <line x1={padL} x2={W - padR} y1={yToY(g)} y2={yToY(g)}
              stroke={g === 3.9 || g === 9.3 ? "var(--accent-soft)" : "var(--hairline)"}
              strokeDasharray={g === 3.9 || g === 9.3 ? "0" : "2 4"} />
            <text x={padL - 6} y={yToY(g) + 3} textAnchor="end" fontFamily="var(--mono)" fontSize="10" fill="var(--ink-4)">{g}</text>
          </g>
        ))}
        <rect x={padL} y={yToY(9.3)} width={innerW} height={yToY(3.9) - yToY(9.3)}
          fill="var(--accent-bg)" opacity="0.35" />
        <text x={padL + 8} y={yToY(9.3) + 12} fontFamily="var(--mono)" fontSize="9" fill="var(--accent)">целевой 3.9–9.3</text>

        {events.map((e, i) => (
          <line key={i} x1={iToX(e.i)} x2={iToX(e.i)} y1={padT} y2={H - padB}
            stroke={e.kind === "fingerstick" ? "var(--ink)" : "var(--ink-3)"}
            strokeDasharray="3 3" opacity={e.kind === "meal" ? 0.5 : 0.3} />
        ))}

        {showRaw && (
          <path d={rawPath} fill="none" stroke="var(--ink-3)" strokeWidth="1" strokeDasharray="2 2" opacity="0.7" />
        )}
        {showNorm && (
          <path d={normPath} fill="none" stroke="var(--ink)" strokeWidth="1.6" />
        )}

        {events.map((e, idx) => {
          if (e.kind !== "meal") return null
          const x = iToX(e.i)
          const w = ('big' in e && e.big) ? 138 : 96
          const tx = Math.min(W - padR - w, Math.max(padL, x - w / 2))
          return (
            <g key={idx}>
              <rect x={tx} y={padT - 22} width={w} height={16} rx={1}
                fill="var(--accent-bg)" stroke="var(--accent-soft)" />
              <text x={tx + 6} y={padT - 11} fontFamily="var(--sans)" fontSize="10" fill="var(--accent)">{e.title} {e.label}</text>
              <circle cx={x} cy={yToY(cgmRaw[e.i].y) - 6} r="3" fill="var(--accent)" />
            </g>
          )
        })}
        {events.filter(e => e.kind === "fingerstick").map((e, i) => (
          <g key={i}>
            <rect x={iToX(e.i) - 5} y={yToY(parseFloat(e.value!)) - 5} width="10" height="10"
              transform={`rotate(45 ${iToX(e.i)} ${yToY(parseFloat(e.value!))})`}
              fill="var(--surface)" stroke="var(--ink)" strokeWidth="1.4" />
          </g>
        ))}
        {events.filter(e => e.kind === "insulin").map((e, i) => (
          <g key={i}>
            <rect x={iToX(e.i) - 1.5} y={padT} width="3" height={innerH} fill="var(--ink)" opacity="0.18" />
            <rect x={iToX(e.i) - 12} y={padT + 4} width="24" height="14" rx="1" fill="var(--ink)" />
            <text x={iToX(e.i)} y={padT + 14} textAnchor="middle" fontFamily="var(--mono)" fontSize="9" fill="#fff">{e.value}</text>
          </g>
        ))}

        <line x1={iToX(cgmRaw.length - 1)} x2={iToX(cgmRaw.length - 1)} y1={padT} y2={H - padB} stroke="var(--ink)" strokeWidth="1" />
        <circle cx={iToX(cgmRaw.length - 1)} cy={yToY(cgmNorm[cgmNorm.length - 1].y)} r="4" fill="var(--ink)" />

        {[12, 24, 36, 48, 60].map((i) => (
          <text key={i} x={iToX(i)} y={H - 8} textAnchor="middle" fontFamily="var(--mono)" fontSize="9" fill="var(--ink-4)">
            {`${(12 + Math.round(i / 12))}:00`}
          </text>
        ))}
      </svg>
    )
  }

  function SensorOffsetChart() {
    const w = 760, h = 130
    const pL = 36, pR = 16, pT = 14, pB = 22
    const iH = h - pT - pB, iW = w - pL - pR
    const min = -0.2, max = 1.3
    const yToYS = (v: number) => pT + iH - ((v - min) / (max - min)) * iH
    const path = offsetPts.map((p, i) => `${i === 0 ? "M" : "L"}${(pL + (i / (offsetPts.length - 1)) * iW).toFixed(1)},${yToYS(p.y).toFixed(1)}`).join(" ")
    return (
      <svg width={w} height={h} style={{ display: "block", width: "100%" }}>
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
    <div className="gt-page" style={{ paddingRight: 0 }}>
      <div className="row" style={{ gap: 0 }}>
        <div style={{ flex: 1, paddingRight: 28 }}>
          <PageHead crumbs={["глюкоза", "локальный контекст"]} title="Глюкоза" right={
            <div className="row gap-8">
              <button className="btn"><I.Plus size={13} /> Запись из пальца</button>
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
              <div style={{ padding: "20px 22px", minWidth: 240 }}>
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
            <div className="row" style={{ borderTop: "1px solid var(--hairline)", padding: "10px 22px", gap: 18, fontSize: 11, color: "var(--ink-3)", alignItems: "center" }}>
              <span className="row gap-6" style={{ alignItems: "center" }}><span style={{ width: 18, height: 1.6, background: "var(--ink)", display: "inline-block" }} /> норм.</span>
              <span className="row gap-6" style={{ alignItems: "center" }}><span style={{ width: 18, height: 1, borderTop: "1px dashed var(--ink-3)", display: "inline-block" }} /> raw CGM</span>
              <span className="row gap-6" style={{ alignItems: "center" }}><span className="dot-marker" style={{ background: "var(--accent)" }} /> приём пищи</span>
              <span className="row gap-6" style={{ alignItems: "center" }}><span style={{ width: 8, height: 8, background: "var(--surface)", border: "1.4px solid var(--ink)", transform: "rotate(45deg)", display: "inline-block" }} /> запись из пальца</span>
              <span className="row gap-6" style={{ alignItems: "center" }}><span style={{ width: 12, height: 8, background: "var(--ink)", display: "inline-block" }} /> инсулин</span>
              <span className="spacer" />
              <span className="mono" style={{ color: "var(--ink-4)" }}>02 май · 12:02 — 18:02</span>
            </div>
          </div>

          {/* Episodes / events */}
          <div className="card" style={{ marginBottom: 22 }}>
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
                    <div className="row clickable-row" onClick={() => setExpandedEp(expandedEp === i ? -1 : i)} style={{
                      alignItems: "stretch", padding: "12px 0", gap: 16,
                      borderBottom: i === 0 ? "1px solid var(--hairline)" : "none",
                      background: ep.active ? "var(--surface-2)" : "transparent",
                      margin: ep.active ? "0 -18px" : 0,
                      paddingLeft: ep.active ? 18 : 0, paddingRight: ep.active ? 18 : 0,
                      cursor: 'pointer',
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
          <div className="card" style={{ marginBottom: 28 }}>
            <div className="card-head">
              <div>
                <div className="lbl">оценка по записям из пальца · raw CGM сохраняется без изменений</div>
                <h3>Смещение по времени сенсора</h3>
              </div>
              <span className="mono" style={{ fontSize: 11, color: "var(--ink-3)" }}>текущее <b style={{ color: "var(--ink)", fontWeight: 500 }}>{currentSensor.offset} ммоль/л</b></span>
            </div>
            <div style={{ padding: "10px 12px 14px" }}>
              <SensorOffsetChart />
            </div>
          </div>
        </div>

        {/* right sidebar */}
        <aside style={{ width: 300, flex: "0 0 300px", borderLeft: "1px solid var(--hairline)", padding: "24px 24px 56px", background: "var(--surface-2)" }}>
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

          {/* offset card */}
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
        </aside>
      </div>
    </div>
  )
}
