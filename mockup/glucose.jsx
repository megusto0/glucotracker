/* global React, I, Shell, PageHead, buildSpline */

// ───── Glucose page (redesigned) ─────
function GlucosePage() {
  // Build a 6h glucose curve sample
  const cgmRaw = React.useMemo(() => {
    const pts = [];
    const N = 72;
    for (let i = 0; i < N; i++) {
      const t = i / (N - 1);
      // baseline
      let y = 5.4 + Math.sin(t * 2 * Math.PI * 0.6) * 0.4;
      // food bumps at 0.45 (small) and 0.62 (big)
      if (t > 0.42) y += 2.6 * Math.exp(-Math.pow((t - 0.55) / 0.13, 2));
      if (t > 0.55) y += 1.3 * Math.exp(-Math.pow((t - 0.7) / 0.09, 2));
      y += (Math.random() - 0.5) * 0.18;
      pts.push({ y });
    }
    return pts;
  }, []);
  const cgmNorm = cgmRaw.map((p) => ({ y: p.y + 0.3 }));

  // Glucose chart geometry
  const W = 760, H = 280;
  const padL = 38, padR = 16, padT = 28, padB = 28;
  const yMin = 3.5, yMax = 12.2;
  const innerW = W - padL - padR;
  const innerH = H - padT - padB;
  const yToY = (y) => padT + innerH - ((y - yMin) / (yMax - yMin)) * innerH;
  const iToX = (i) => padL + (i / (cgmRaw.length - 1)) * innerW;
  const rawPath = cgmRaw.map((p, i) => `${i === 0 ? "M" : "L"}${iToX(i).toFixed(1)},${yToY(p.y).toFixed(1)}`).join(" ");
  const normPath = cgmNorm.map((p, i) => `${i === 0 ? "M" : "L"}${iToX(i).toFixed(1)},${yToY(p.y).toFixed(1)}`).join(" ");

  // events
  const events = [
    { i: 18, kind: "meal", label: "14:07 · 21.7 г",  title: "Приём пищи" },
    { i: 38, kind: "meal", label: "15:43–16:04 · 64.8 г", title: "Приём пищи", big: true },
    { i: 50, kind: "fingerstick", label: "16:33", value: "9.9" },
    { i: 60, kind: "insulin", label: "17:40", value: "1.6 ЕД" },
  ];

  // sensor offset chart (2.7d)
  const offsetPts = React.useMemo(() => {
    const out = [];
    for (let i = 0; i < 60; i++) {
      let y = 0.95;
      if (i > 24 && i < 32) y = 0.5;
      if (i >= 32) y = 0.32 + (Math.random() - 0.5) * 0.04;
      if (i < 6) y = 0.85 + (Math.random() - 0.5) * 0.04;
      out.push({ y });
    }
    return out;
  }, []);

  function GlucoseChart() {
    return (
      <svg width={W} height={H} style={{ display: "block", width: "100%" }}>
        {/* y grid */}
        {[3.9, 6.5, 9.3, 12].map((g, i) => (
          <g key={i}>
            <line x1={padL} x2={W - padR} y1={yToY(g)} y2={yToY(g)}
              stroke={g === 3.9 || g === 9.3 ? "var(--accent-soft)" : "var(--hairline)"}
              strokeDasharray={g === 3.9 || g === 9.3 ? "0" : "2 4"} />
            <text x={padL - 6} y={yToY(g) + 3} textAnchor="end" fontFamily="var(--mono)" fontSize="10" fill="var(--ink-4)">{g}</text>
          </g>
        ))}
        {/* target band */}
        <rect x={padL} y={yToY(9.3)} width={innerW} height={yToY(3.9) - yToY(9.3)}
          fill="var(--accent-bg)" opacity="0.35" />
        <text x={padL + 8} y={yToY(9.3) + 12} fontFamily="var(--mono)" fontSize="9" fill="var(--accent)">целевой 3.9–9.3</text>

        {/* event guides */}
        {events.map((e, i) => (
          <line key={i} x1={iToX(e.i)} x2={iToX(e.i)} y1={padT} y2={H - padB}
            stroke={e.kind === "fingerstick" ? "var(--ink)" : "var(--ink-3)"}
            strokeDasharray="3 3" opacity={e.kind === "meal" ? 0.5 : 0.3} />
        ))}

        {/* raw line (dotted) */}
        <path d={rawPath} fill="none" stroke="var(--ink-3)" strokeWidth="1" strokeDasharray="2 2" opacity="0.7" />
        {/* normalized line */}
        <path d={normPath} fill="none" stroke="var(--ink)" strokeWidth="1.6" />

        {/* event markers above chart */}
        {events.map((e, idx) => {
          if (e.kind !== "meal") return null;
          const x = iToX(e.i);
          const w = e.big ? 138 : 96;
          const tx = Math.min(W - padR - w, Math.max(padL, x - w / 2));
          return (
            <g key={idx}>
              <rect x={tx} y={padT - 22} width={w} height={16} rx={1}
                fill="var(--accent-bg)" stroke="var(--accent-soft)" />
              <text x={tx + 6} y={padT - 11} fontFamily="var(--sans)" fontSize="10" fill="var(--accent)">{e.title} {e.label}</text>
              <circle cx={x} cy={yToY(cgmRaw[e.i].y) - 6} r="3" fill="var(--accent)" />
            </g>
          );
        })}
        {events.filter(e => e.kind === "fingerstick").map((e, i) => (
          <g key={i}>
            <rect x={iToX(e.i) - 5} y={yToY(parseFloat(e.value)) - 5} width="10" height="10"
              transform={`rotate(45 ${iToX(e.i)} ${yToY(parseFloat(e.value))})`}
              fill="var(--surface)" stroke="var(--ink)" strokeWidth="1.4" />
          </g>
        ))}
        {events.filter(e => e.kind === "insulin").map((e, i) => (
          <g key={i}>
            <rect x={iToX(e.i) - 1.5} y={padT} width="3" height={innerH}
              fill="var(--ink)" opacity="0.18" />
            <rect x={iToX(e.i) - 12} y={padT + 4} width="24" height="14" rx="1" fill="var(--ink)" />
            <text x={iToX(e.i)} y={padT + 14} textAnchor="middle" fontFamily="var(--mono)" fontSize="9" fill="#fff">{e.value}</text>
          </g>
        ))}

        {/* now line */}
        <line x1={iToX(cgmRaw.length - 1)} x2={iToX(cgmRaw.length - 1)} y1={padT} y2={H - padB} stroke="var(--ink)" strokeWidth="1" />
        <circle cx={iToX(cgmRaw.length - 1)} cy={yToY(cgmNorm[cgmNorm.length - 1].y)} r="4" fill="var(--ink)" />

        {/* x ticks */}
        {[12, 24, 36, 48, 60].map((i) => (
          <text key={i} x={iToX(i)} y={H - 8} textAnchor="middle" fontFamily="var(--mono)" fontSize="9" fill="var(--ink-4)">
            {`${(12 + Math.round(i / 12))}:00`}
          </text>
        ))}
      </svg>
    );
  }

  function SensorOffsetChart() {
    const w = 760, h = 130;
    const pL = 36, pR = 16, pT = 14, pB = 22;
    const iH = h - pT - pB, iW = w - pL - pR;
    const min = -0.2, max = 1.3;
    const yToYS = (v) => pT + iH - ((v - min) / (max - min)) * iH;
    const path = offsetPts.map((p, i) => `${i === 0 ? "M" : "L"}${(pL + (i / (offsetPts.length - 1)) * iW).toFixed(1)},${yToYS(p.y).toFixed(1)}`).join(" ");
    return (
      <svg width={w} height={h} style={{ display: "block", width: "100%" }}>
        {[0, 0.5, 1.0].map((v, i) => (
          <g key={i}>
            <line x1={pL} x2={w - pR} y1={yToYS(v)} y2={yToYS(v)} stroke="var(--hairline)" strokeDasharray={v === 0 ? "0" : "2 4"} />
            <text x={pL - 6} y={yToYS(v) + 3} textAnchor="end" fontFamily="var(--mono)" fontSize="9" fill="var(--ink-4)">{v.toFixed(1)}</text>
          </g>
        ))}
        {/* warmup zone */}
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
    );
  }

  return (
    <Shell active="Глюкоза">
      <div className="gt-page" style={{ paddingRight: 0 }}>
        <div className="row" style={{ gap: 0 }}>
          {/* left main column */}
          <div style={{ flex: 1, paddingRight: 28 }}>
            <PageHead crumbs={["глюкоза", "локальный контекст"]} title="Глюкоза" right={
              <div className="row gap-8">
                <button className="btn"><I.Plus size={13}/> Запись из пальца</button>
                <button className="btn"><I.Refresh size={13}/></button>
              </div>
            }/>

            {/* hero summary band */}
            <div className="card" style={{ marginBottom: 22, overflow: "hidden" }}>
              <div className="row" style={{ alignItems: "stretch" }}>
                {/* now */}
                <div style={{ padding: "20px 22px", borderRight: "1px solid var(--hairline)", minWidth: 200 }}>
                  <div className="lbl">сейчас</div>
                  <div className="row gap-6" style={{ alignItems: "baseline", marginTop: 6 }}>
                    <span className="g-now">9.8</span>
                    <span style={{ fontSize: 12, color: "var(--ink-3)" }}>ммоль/л</span>
                  </div>
                  <div className="row gap-6" style={{ alignItems: "center", marginTop: 6 }}>
                    <span className="tag accent"><I.Up size={10}/> +0.6 за 15 мин</span>
                  </div>
                </div>
                {/* TIR mini */}
                <div style={{ padding: "20px 22px", borderRight: "1px solid var(--hairline)", flex: 1 }}>
                  <div className="lbl">время в диапазоне · 24ч</div>
                  <div className="row" style={{ height: 8, marginTop: 12, borderRadius: 1, overflow: "hidden" }}>
                    <div style={{ width: "4%", background: "var(--warn)" }}/>
                    <div style={{ width: "68%", background: "var(--good)" }}/>
                    <div style={{ width: "26%", background: "var(--accent)" }}/>
                    <div style={{ width: "2%", background: "var(--ink)" }}/>
                  </div>
                  <div className="row" style={{ marginTop: 8, gap: 14, fontSize: 11, color: "var(--ink-3)" }}>
                    <span><span className="dot-marker" style={{ background: "var(--warn)" }}/> &lt;3.9 <b className="mono" style={{ color: "var(--ink)", fontWeight: 500, marginLeft: 4 }}>4%</b></span>
                    <span><span className="dot-marker" style={{ background: "var(--good)" }}/> 3.9–9.3 <b className="mono" style={{ color: "var(--ink)", fontWeight: 500, marginLeft: 4 }}>68%</b></span>
                    <span><span className="dot-marker" style={{ background: "var(--accent)" }}/> 9.3–13 <b className="mono" style={{ color: "var(--ink)", fontWeight: 500, marginLeft: 4 }}>26%</b></span>
                    <span><span className="dot-marker" style={{ background: "var(--ink)" }}/> &gt;13 <b className="mono" style={{ color: "var(--ink)", fontWeight: 500, marginLeft: 4 }}>2%</b></span>
                  </div>
                </div>
                {/* sensor */}
                <div style={{ padding: "20px 22px", minWidth: 240 }}>
                  <div className="row" style={{ justifyContent: "space-between", alignItems: "baseline" }}>
                    <span className="lbl">сенсор Ottai</span>
                    <span className="tag good">актив.</span>
                  </div>
                  <div className="row gap-6" style={{ alignItems: "baseline", marginTop: 6 }}>
                    <span className="mono" style={{ fontSize: 26, fontWeight: 500 }}>2.7</span>
                    <span style={{ fontSize: 12, color: "var(--ink-3)" }}>/ 15 дней</span>
                  </div>
                  <div className="pbar" style={{ marginTop: 8 }}><i style={{ width: "18%" }}/></div>
                  <div className="row" style={{ marginTop: 6, fontSize: 11, color: "var(--ink-3)", justifyContent: "space-between" }}>
                    <span>стабильная фаза</span>
                    <span className="mono">92/100</span>
                  </div>
                </div>
              </div>
              {/* status strip */}
              <div className="row" style={{ borderTop: "1px solid var(--hairline)", padding: "10px 22px", gap: 24, fontSize: 11, color: "var(--ink-3)", alignItems: "center" }}>
                <span>смещ. <b className="mono" style={{ color: "var(--ink)", fontWeight: 500 }}>+0.3 ммоль/л</b></span>
                <span>ккал <b className="mono" style={{ color: "var(--ink)", fontWeight: 500 }}>1587</b></span>
                <span>TDEE <b className="mono" style={{ color: "var(--ink)", fontWeight: 500 }}>2829</b></span>
                <span>шаги <b className="mono" style={{ color: "var(--ink)", fontWeight: 500 }}>0</b></span>
                <span>баланс <b className="mono" style={{ color: "var(--good)", fontWeight: 500 }}>−1242</b></span>
                <span className="spacer"/>
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
                  <div className="seg">
                    <button>3Ч</button>
                    <button className="on">6Ч</button>
                    <button>12Ч</button>
                    <button>24Ч</button>
                    <button>7Д</button>
                  </div>
                  <div className="seg">
                    <button>RAW</button>
                    <button>СГЛАЖ.</button>
                    <button className="on">НОРМ.</button>
                  </div>
                </div>
              </div>
              <div style={{ padding: "10px 12px 14px" }}>
                <GlucoseChart />
              </div>
              {/* legend */}
              <div className="row" style={{ borderTop: "1px solid var(--hairline)", padding: "10px 22px", gap: 18, fontSize: 11, color: "var(--ink-3)", alignItems: "center" }}>
                <span className="row gap-6" style={{ alignItems: "center" }}><span style={{ width: 18, height: 1.6, background: "var(--ink)" }}/> норм.</span>
                <span className="row gap-6" style={{ alignItems: "center" }}><span style={{ width: 18, height: 1, borderTop: "1px dashed var(--ink-3)" }}/> raw CGM</span>
                <span className="row gap-6" style={{ alignItems: "center" }}><span className="dot-marker" style={{ background: "var(--accent)" }}/> приём пищи</span>
                <span className="row gap-6" style={{ alignItems: "center" }}><span style={{ width: 8, height: 8, background: "var(--surface)", border: "1.4px solid var(--ink)", transform: "rotate(45deg)" }}/> запись из пальца</span>
                <span className="row gap-6" style={{ alignItems: "center" }}><span style={{ width: 12, height: 8, background: "var(--ink)" }}/> инсулин</span>
                <span className="spacer"/>
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
                <div className="seg">
                  <button className="on">Эпизоды</button>
                  <button>События</button>
                </div>
              </div>
              <div style={{ padding: "6px 18px 14px" }}>
                {[
                  { time: "14:07", events: 2, names: "Сырок глазированный, Протеиновое брауни Shagi", carbs: "21.7 г", kcal: "309", peak: "7.3 → пик 8.9 через 115 мин", insulin: "0.8 ЕД" },
                  { time: "15:43–16:04", events: 4, names: "Лаваш с курицей, Cheetos Пицца, Кола Ориджинал", carbs: "64.8 г", kcal: "878", peak: "9.5 → пик 10.1 через 12 мин", insulin: "1.6 ЕД", active: true },
                ].map((ep, i) => (
                  <div key={i} className="row" style={{
                    alignItems: "stretch", padding: "12px 0", gap: 16,
                    borderBottom: i === 0 ? "1px solid var(--hairline)" : "none",
                    background: ep.active ? "var(--surface-2)" : "transparent",
                    margin: ep.active ? "0 -18px" : 0,
                    paddingLeft: ep.active ? 18 : 0, paddingRight: ep.active ? 18 : 0,
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
                    <button className="btn-link">подробнее →</button>
                  </div>
                ))}
              </div>
            </div>

            {/* Sensor offset */}
            <div className="card" style={{ marginBottom: 28 }}>
              <div className="card-head">
                <div>
                  <div className="lbl">оценка по записям из пальца · raw CGM сохраняется без изменений</div>
                  <h3>Смещение по времени сенсора</h3>
                </div>
                <span className="mono" style={{ fontSize: 11, color: "var(--ink-3)" }}>текущее <b style={{ color: "var(--ink)", fontWeight: 500 }}>+0.3 ммоль/л</b></span>
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
              <h2 style={{ margin: 0, fontFamily: "var(--serif)", fontSize: 24, fontWeight: 500 }}>Ottai</h2>
              <span className="tag good">актив.</span>
            </div>
            <div style={{ fontSize: 11, color: "var(--ink-3)", marginTop: 4 }}>
              <span className="mono">Otta-1</span> · модель A · день <span className="mono">2.7 / 15</span>
            </div>

            <div style={{ marginTop: 22 }}>
              <div className="lbl" style={{ marginBottom: 6 }}>Качество</div>
              <div className="row" style={{ alignItems: "baseline", gap: 4 }}>
                <span className="mono" style={{ fontSize: 28, fontWeight: 500 }}>92</span>
                <span className="mono" style={{ fontSize: 12, color: "var(--ink-3)" }}>/ 100</span>
              </div>
              <div className="pbar good" style={{ marginTop: 6 }}><i style={{ width: "92%" }}/></div>
            </div>

            <div className="row" style={{ marginTop: 18, gap: 0, borderTop: "1px solid var(--hairline)", borderBottom: "1px solid var(--hairline)" }}>
              {[
                { l: "артефакты", v: "0" },
                { l: "compr. lows", v: "0" },
                { l: "noise", v: "1.0" },
                { l: "доверие", v: "high" },
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
                <span className="mono" style={{ fontSize: 22, fontWeight: 500 }}>+0.3</span>
                <span style={{ fontSize: 11, color: "var(--ink-3)" }}>ммоль/л</span>
              </div>
              <div style={{ fontSize: 11, color: "var(--ink-3)", marginTop: 4, lineHeight: 1.4 }}>
                1 запись из пальца · стабильная фаза
              </div>
              <div className="row" style={{ marginTop: 12, gap: 12 }}>
                <div style={{ flex: 1 }}>
                  <div className="lbl" style={{ fontSize: 9 }}>медиана Δ</div>
                  <div className="mono" style={{ fontSize: 12 }}>+0.3</div>
                </div>
                <div style={{ flex: 1 }}>
                  <div className="lbl" style={{ fontSize: 9 }}>диапазон</div>
                  <div className="mono" style={{ fontSize: 12 }}>+0.3…+0.3</div>
                </div>
              </div>
              <div className="row" style={{ marginTop: 8, gap: 12 }}>
                <div style={{ flex: 1 }}>
                  <div className="lbl" style={{ fontSize: 9 }}>дрейф</div>
                  <div className="mono" style={{ fontSize: 12 }}>+0/день</div>
                </div>
                <div style={{ flex: 1 }}>
                  <div className="lbl" style={{ fontSize: 9 }}>mard</div>
                  <div className="mono" style={{ fontSize: 12 }}>3.1%</div>
                </div>
              </div>
            </div>

            {/* actions */}
            <div className="col gap-8" style={{ marginTop: 18 }}>
              <button className="btn dark"><I.Plus size={13}/> Запись из пальца</button>
              <button className="btn"><I.Edit size={13}/> Редактировать сенсор</button>
              <button className="btn"><I.Refresh size={13}/> Пересчитать</button>
            </div>

            {/* last fingerstick */}
            <div style={{ marginTop: 22 }}>
              <div className="lbl">последняя запись из пальца</div>
              <div className="row" style={{ alignItems: "center", marginTop: 6, padding: "10px 12px", border: "1px solid var(--hairline)", borderRadius: "var(--radius)", background: "var(--surface)", gap: 8 }}>
                <span className="mono" style={{ fontSize: 11, color: "var(--ink-3)" }}>16:33</span>
                <span className="mono" style={{ fontSize: 13, fontWeight: 500 }}>9.9</span>
                <span style={{ fontSize: 11, color: "var(--ink-3)" }}>ммоль/л</span>
                <span className="spacer"/>
                <span className="tag accent">Δ +0.3</span>
              </div>
            </div>

            {/* prev sensors */}
            <div style={{ marginTop: 22 }}>
              <div className="lbl">предыдущие сенсоры</div>
              <div style={{ marginTop: 8 }}>
                {[
                  { name: "Ottai", date: "30 апр", days: "14.8 д", q: 88 },
                  { name: "Ottai", date: "16 апр", days: "13.2 д", q: 79 },
                  { name: "Dexcom G7", date: "03 апр", days: "10.4 д", q: 91 },
                ].map((s, i) => (
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
    </Shell>
  );
}

window.GlucosePage = GlucosePage;
