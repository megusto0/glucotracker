/* global React, I, Shell */

// ───── Statistics v4 – refined editorial ─────

function StatsPage() {
  const tdee = 2829;
  const goal = 2200;

  // 7-day data (most relevant)
  const days7 = [
    { d: "пн", date: "27", intake: 0,    carbs: 0   },
    { d: "вт", date: "28", intake: 1842, carbs: 145 },
    { d: "ср", date: "29", intake: 2410, carbs: 198 },
    { d: "чт", date: "30", intake: 2156, carbs: 240 },
    { d: "пт", date: "01", intake: 1924, carbs: 178 },
    { d: "сб", date: "02", intake: 1587, carbs: 111, today: true },
  ];
  const filled7 = days7.filter(d => d.intake > 0);
  const cumDef = filled7.reduce((a,d) => a + (d.intake - tdee), 0);
  const avgIntake = Math.round(filled7.reduce((a,d) => a + d.intake, 0) / filled7.length);
  const todayIntake = days7[days7.length-1].intake;
  const todayBal = todayIntake - tdee;
  const todayCarbs = days7[days7.length-1].carbs;
  const todayGi = 38;
  const macroScore = 22; // БЖУ-баланс (усреднено)

  // 14-day carbs (crop empty left)
  const carbs14 = React.useMemo(() => {
    const vals = [145,198,312,240,178,95,156,111,0,0,0,0,0,0];
    return vals;
  }, []);
  const c14max = Math.max(...carbs14);
  const c14avg = 227;

  // CGM sparkline (24h)
  const cgm24 = React.useMemo(() => {
    const pts = [];
    for (let i = 0; i < 96; i++) {
      const t = i / 95;
      let y = 5.6 + Math.sin(t * Math.PI * 2.4) * 0.5;
      if (t > 0.28 && t < 0.52) y += 2.8 * Math.exp(-Math.pow((t - 0.42) / 0.1, 2));
      if (t > 0.58 && t < 0.82) y += 1.9 * Math.exp(-Math.pow((t - 0.7) / 0.09, 2));
      y += (Math.random() - 0.5) * 0.15;
      pts.push({ y: Math.max(2.5, y) });
    }
    return pts;
  }, []);

  // heatmap
  const heatCells = React.useMemo(() => {
    const out = [];
    for (let r = 0; r < 7; r++) {
      const row = [];
      for (let c = 0; c < 24; c++) {
        let v = 0;
        if ([8,9].includes(c)) v = 0.2 + Math.random()*0.5;
        else if ([13,14].includes(c)) v = 0.35 + Math.random()*0.55;
        else if ([19,20,21].includes(c)) v = 0.45 + Math.random()*0.5;
        else if ([10,12,16,18].includes(c)) v = Math.random()*0.28;
        else v = Math.random()*0.05;
        if (r === 5 && (c===15||c===16)) v = 0.95;
        row.push(v);
      }
      out.push(row);
    }
    return out;
  }, []);

  // ── 1. Narrative headline ────────────────────────────────────────────────
  function Headline() {
    return (
      <div style={{ marginBottom: 36 }}>
        {/* Verdict (bold, primary) */}
        <h2 style={{
          fontFamily: "var(--serif)", fontSize: 32, fontWeight: 400,
          margin: "0 0 8px", letterSpacing: "-0.01em", lineHeight: 1.2,
        }}>
          Дефицит <span style={{ fontFamily: "var(--mono)", color: "var(--ink)" }}>4 226 ккал</span> за неделю
        </h2>
        {/* Footnotes (small, secondary) */}
        <div style={{
          fontFamily: "var(--mono)", fontSize: 11, color: "var(--ink-3)",
          lineHeight: 1.8, display: "flex", gap: 24, flexWrap: "wrap",
        }}>
          <span><b style={{ color: "var(--ink)" }}>среднее</b> {avgIntake} ккал/день</span>
          <span><b style={{ color: "var(--ink)" }}>сегодня</b> {todayIntake} ккал</span>
          <span><b style={{ color: "var(--ink)" }}>баланс</b> {todayBal > 0 ? "+" : ""}{todayBal}</span>
          <span><b style={{ color: "var(--ink)" }}>расчётно</b> {(Math.abs(cumDef)/7700).toFixed(2)} кг</span>
        </div>
      </div>
    );
  }

  // ── 2. KPI strip (4 metrics) ─────────────────────────────────────────────
  function KpiStrip() {
    const kpis = [
      {
        lbl: "Углеводы",
        val: todayCarbs, u: "г",
        sub: `сред. за 7 дн. ${c14avg} г · пик 312 г`,
        pct: todayCarbs / 225,
      },
      {
        lbl: "Ккал",
        val: todayIntake, u: "",
        sub: `цель 2200 · TDEE ${tdee}`,
        pct: todayIntake / goal,
        color: todayIntake <= goal ? "oklch(0.7 0.08 145)" : "oklch(0.72 0.07 50)",
      },
      {
        lbl: "ГН",
        val: todayGi, u: "",
        sub: `норма < 100 / день · сред. 72`,
        pct: todayGi / 100,
      },
      {
        lbl: "БЖУ-баланс",
        val: macroScore, u: "%",
        sub: `углеводы 28% · белки 22% · жиры 50%`,
        pct: null,
      },
    ];
    return (
      <div style={{
        display: "grid", gridTemplateColumns: "repeat(4,1fr)",
        borderTop: "2px solid var(--ink)",
        borderBottom: "1px solid var(--hairline)",
        marginBottom: 40,
      }}>
        {kpis.map((k, i) => (
          <div key={i} style={{
            padding: "14px 0",
            paddingLeft: i > 0 ? 20 : 0,
            paddingRight: 20,
            borderLeft: i > 0 ? "1px solid var(--hairline)" : "none",
          }}>
            <div style={{ fontSize: 9, letterSpacing: "0.16em", textTransform: "uppercase", color: "var(--ink-4)", marginBottom: 6, fontWeight: 500 }}>
              {k.lbl}
            </div>
            <div style={{ fontFamily: "var(--mono)", fontSize: 28, fontWeight: 500, lineHeight: 1, letterSpacing: "-0.01em", color: k.color || "var(--ink)" }}>
              {k.val}{k.u && <span style={{ fontSize: 10, color: "var(--ink-3)", marginLeft: 3 }}>{k.u}</span>}
            </div>
            {k.pct !== null && (
              <div style={{ height: 2, background: "var(--hairline)", marginTop: 8, marginBottom: 10 }}>
                <div style={{ height: "100%", width: `${Math.min(100, k.pct * 100)}%`, background: k.color || "var(--accent)" }}/>
              </div>
            )}
            {k.pct === null && <div style={{ height: 18 }}/>}
            <div style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--ink-3)", lineHeight: 1.6 }}>
              {k.sub}
            </div>
          </div>
        ))}
      </div>
    );
  }

  // ── 3. Paired charts (14d carbs + 7d balance) ────────────────────────────
  function PairedCharts() {
    const W = 480, H = 160;
    const pL = 38, pR = 8, pT = 20, pB = 28;
    const iW = W - pL - pR, iH = H - pT - pB;
    const N = carbs14.length;
    const bw = iW / N;

    function CarbsChart() {
      const avgY = pT + iH - (c14avg / c14max) * iH;
      return (
        <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} style={{ display:"block", width:"100%", height:"auto" }}>
          <line x1={pL} x2={W-pR} y1={avgY} y2={avgY} stroke="var(--accent)" strokeDasharray="3 4" strokeWidth="1"/>
          <text x={pL-4} y={avgY-2} textAnchor="end" fontFamily="var(--mono)" fontSize="8" fill="var(--accent)">сред.</text>
          {carbs14.map((v, i) => {
            const bh = v === 0 ? 0 : Math.max(1.5, (v/c14max)*iH);
            const x  = pL + i*bw + bw*0.2;
            const isT = i === N-1;
            return <rect key={i} x={x} y={pT+iH-bh} width={bw*0.6} height={bh}
              fill={v===0?"var(--hairline-2)": isT ? "var(--ink)" : "oklch(0.82 0.06 78)"}/>;
          })}
          <line x1={pL} x2={pL} y1={pT} y2={pT+iH} stroke="var(--hairline)" strokeWidth="1"/>
          <line x1={pL} x2={W-pR} y1={pT+iH} y2={pT+iH} stroke="var(--hairline)" strokeWidth="1"/>
          <text x={pL-2} y={pT+iH+12} fontFamily="var(--mono)" fontSize="9" fill="var(--ink-4)">25 апр</text>
          <text x={W-pR} y={pT+iH+12} textAnchor="end" fontFamily="var(--mono)" fontSize="9" fill="var(--ink-4)">02 май</text>
        </svg>
      );
    }

    function BalanceChart() {
      const Wb = 360, Hb = 160;
      const pLb=38, pRb=8, pTb=20, pBb=28;
      const iWb=Wb-pLb-pRb, iHb=Hb-pTb-pBb;
      const maxAbs = 1200;
      const midY = pTb + iHb/2;
      const bwb  = iWb / days7.length;
      const tdeeLine = midY;

      return (
        <svg width={Wb} height={Hb} viewBox={`0 0 ${Wb} ${Hb}`} style={{ display:"block", width:"100%", height:"auto" }}>
          {/* TDEE line */}
          <line x1={pLb} x2={Wb-pRb} y1={tdeeLine} y2={tdeeLine} stroke="var(--ink-3)" strokeWidth="1"/>
          <text x={pLb-2} y={tdeeLine-3} textAnchor="end" fontFamily="var(--mono)" fontSize="8" fill="var(--ink-3)">TDEE</text>

          {days7.map((d, i) => {
            const cx  = pLb + i*bwb + bwb/2;
            const bww = bwb*0.48;
            if (d.intake === 0) {
              return <line key={i} x1={cx} x2={cx} y1={midY-1.5} y2={midY+1.5} stroke="var(--hairline-2)" strokeWidth="1"/>;
            }
            const bal = d.intake - tdee;
            const bh  = (Math.abs(bal)/maxAbs)*(iHb/2);
            const y   = bal < 0 ? midY : midY - bh;
            const h   = bal < 0 ? bh   : bh;
            const fill = d.today ? "#444" : (bal < 0 ? "oklch(0.78 0.04 145)" : "oklch(0.78 0.04 60)");

            return (
              <g key={i}>
                <rect x={cx-bww/2} y={y} width={bww} height={Math.max(h,1)} fill={fill}/>
                {/* label inside bar */}
                <text x={cx} y={bal < 0 ? y + h - 3 : y + 9}
                  textAnchor="middle" fontFamily="var(--mono)" fontSize="8"
                  fill={d.today ? "#fff" : "var(--ink-3)"}
                  style={{ pointerEvents: "none" }}>
                  {Math.abs(bal) > 100 ? Math.round(bal/100)+"00" : Math.round(bal)}
                </text>
                {/* day label */}
                <text x={cx} y={Hb-8} textAnchor="middle" fontFamily="var(--sans)" fontSize="10"
                  fill={d.today ? "var(--ink)" : "var(--ink-4)"} fontWeight={d.today ? "500" : "400"}>
                  {d.d}
                </text>
              </g>
            );
          })}

          <line x1={pLb} x2={pLb} y1={pTb} y2={pTb+iHb} stroke="var(--hairline)" strokeWidth="1"/>
        </svg>
      );
    }

    return (
      <div style={{ display:"grid", gridTemplateColumns:"1fr 0.75fr", gap: 32, marginBottom: 40 }}>
        {/* left: carbs */}
        <div>
          <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-end", paddingBottom: 8, borderBottom:"1px solid var(--hairline)", marginBottom:12 }}>
            <div>
              <div style={{ fontSize:9, letterSpacing:"0.16em", textTransform:"uppercase", color:"var(--ink-4)", fontWeight:500, marginBottom:3 }}>01 · 14 дней</div>
              <h2 style={{ fontFamily:"var(--serif)", fontSize:20, fontWeight:400, margin:0, letterSpacing:"-0.01em" }}>Углеводы</h2>
            </div>
            <div style={{ textAlign:"right", fontFamily:"var(--mono)", fontSize:10, color:"var(--ink-3)" }}>
              <div>сред. <b style={{ color:"var(--ink)" }}>{c14avg} г</b></div>
              <div style={{ color:"var(--ink-4)", fontSize:9 }}>пик 312 г</div>
            </div>
          </div>
          <CarbsChart />
        </div>

        {/* right: balance */}
        <div>
          <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-end", paddingBottom:8, borderBottom:"1px solid var(--hairline)", marginBottom:12 }}>
            <div>
              <div style={{ fontSize:9, letterSpacing:"0.16em", textTransform:"uppercase", color:"var(--ink-4)", fontWeight:500, marginBottom:3 }}>02 · 7 дней</div>
              <h2 style={{ fontFamily:"var(--serif)", fontSize:20, fontWeight:400, margin:0, letterSpacing:"-0.01em" }}>Баланс</h2>
            </div>
            <div style={{ textAlign:"right", fontFamily:"var(--mono)", fontSize:10, color: cumDef < 0 ? "oklch(0.7 0.08 145)" : "var(--warn)", fontWeight:500 }}>
              {cumDef.toLocaleString("ru-RU")} ккал
            </div>
          </div>
          <BalanceChart />
        </div>
      </div>
    );
  }

  // ── 4. Glucose section ──────────────────────────────────────────────────
  function GlucoseSection() {
    const W = 520, H = 140;
    const pL=10, pR=10, pT=10, pB=20;
    const iW=W-pL-pR, iH=H-pT-pB;
    const yMin=2.5, yMax=14;
    const pts = cgm24;

    const path = pts.map((p,i) => {
      const x = pL + (i/(pts.length-1))*iW;
      const y = pT + iH - ((p.y-yMin)/(yMax-yMin))*iH;
      return `${i===0?"M":"L"}${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(" ");

    const lowY  = pT + iH - ((3.9-yMin)/(yMax-yMin))*iH;
    const highY = pT + iH - ((7.8-yMin)/(yMax-yMin))*iH;

    const inRange = pts.filter(p => p.y >= 3.9 && p.y <= 7.8).length;
    const tirPct  = Math.round(inRange/pts.length*100);
    const below   = Math.round(pts.filter(p=>p.y<3.9).length/pts.length*100);
    const above   = 100 - tirPct - below;
    const lastPt  = pts[pts.length-1];
    const lastY   = pT + iH - ((lastPt.y-yMin)/(yMax-yMin))*iH;

    return (
      <div style={{ marginBottom:40 }}>
        <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-end", paddingBottom:8, borderBottom:"1px solid var(--hairline)", marginBottom:12 }}>
          <div>
            <div style={{ fontSize:9, letterSpacing:"0.16em", textTransform:"uppercase", color:"var(--ink-4)", fontWeight:500, marginBottom:3 }}>03 · 24 часа</div>
            <h2 style={{ fontFamily:"var(--serif)", fontSize:20, fontWeight:400, margin:0, letterSpacing:"-0.01em" }}>Глюкоза</h2>
          </div>
          <div style={{ display:"flex", gap:28, alignItems:"baseline" }}>
            <div style={{ textAlign:"right" }}>
              <div style={{ fontSize:9, letterSpacing:"0.12em", textTransform:"uppercase", color:"var(--ink-4)", marginBottom:2, fontWeight:500 }}>в диапазоне</div>
              <div style={{ fontFamily:"var(--mono)", fontSize:22, fontWeight:500, color:"var(--ink)" }}>{tirPct}<span style={{ fontSize:10, color:"var(--ink-4)" }}>%</span></div>
            </div>
            <div style={{ textAlign:"right" }}>
              <div style={{ fontSize:9, letterSpacing:"0.12em", textTransform:"uppercase", color:"var(--ink-4)", marginBottom:2, fontWeight:500 }}>текущий пик</div>
              <div style={{ fontFamily:"var(--mono)", fontSize:22, fontWeight:500, color:"var(--ink)" }}>10.1<span style={{ fontSize:10, color:"var(--ink-4)" }}>ммоль</span></div>
            </div>
            <div style={{ textAlign:"right" }}>
              <div style={{ fontSize:9, letterSpacing:"0.12em", textTransform:"uppercase", color:"var(--ink-4)", marginBottom:2, fontWeight:500 }}>возврат</div>
              <div style={{ fontFamily:"var(--mono)", fontSize:22, fontWeight:500, color:"var(--ink)" }}>92<span style={{ fontSize:10, color:"var(--ink-4)" }}>мин</span></div>
            </div>
          </div>
        </div>

        <div style={{ display:"grid", gridTemplateColumns:"1fr 120px", gap:20, alignItems:"center" }}>
          {/* sparkline */}
          <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} style={{ display:"block", width:"100%", height:"auto" }}>
            {/* target band */}
            <rect x={pL} y={highY} width={iW} height={lowY-highY} fill="oklch(0.96 0.015 145)" opacity="0.7"/>
            <line x1={pL} x2={W-pR} y1={lowY}  y2={lowY}  stroke="var(--ink-3)" strokeWidth="0.8" opacity="0.5"/>
            <line x1={pL} x2={W-pR} y1={highY} y2={highY} stroke="var(--ink-3)" strokeWidth="0.8" opacity="0.5"/>

            {/* meal ticks on x-axis */}
            {[0.28, 0.7].map((t, i) => (
              <line key={i} x1={pL + t*iW} x2={pL + t*iW} y1={pT+iH} y2={pT+iH+4} stroke="var(--accent)" strokeWidth="1.2"/>
            ))}

            {/* curve */}
            <path d={path} fill="none" stroke="var(--ink)" strokeWidth="1.6"/>
            {/* now marker */}
            <circle cx={pL + iW} cy={lastY} r="3" fill="var(--ink)"/>

            {/* time labels */}
            {[0, 8, 16, 24].map((h, j) => (
              <text key={j} x={pL + (h/24)*iW} y={H-4} textAnchor="middle" fontFamily="var(--mono)" fontSize="8" fill="var(--ink-4)">
                {String(h).padStart(2,"0")}:00
              </text>
            ))}
            {/* y labels */}
            <text x={pL-4} y={pT+4} textAnchor="end" fontFamily="var(--mono)" fontSize="8" fill="var(--ink-4)">14</text>
            <text x={pL-4} y={pT+iH+4} textAnchor="end" fontFamily="var(--mono)" fontSize="8" fill="var(--ink-4)">2.5</text>
          </svg>

          {/* TIR stack */}
          <div style={{ display:"flex", flexDirection:"column", gap:6 }}>
            {[
              { l: "< 3.9",    v: below,   c:"oklch(0.72 0.08 30)" },
              { l: "3.9–7.8",  v: tirPct,  c:"oklch(0.7 0.08 145)" },
              { l: "> 7.8",    v: above,   c:"oklch(0.74 0.06 60)" },
            ].map((t,i) => (
              <div key={i}>
                <div style={{ display:"flex", justifyContent:"space-between", marginBottom:2, fontSize:9 }}>
                  <span style={{ color:"var(--ink-3)" }}>{t.l}</span>
                  <span style={{ fontFamily:"var(--mono)", fontWeight:500, color:"var(--ink)" }}>{t.v}%</span>
                </div>
                <div style={{ height:3, background:"var(--hairline)", borderRadius:1 }}>
                  <div style={{ height:"100%", width:`${t.v}%`, background:t.c, borderRadius:1 }}/>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  // ── 5. Heatmap ─────────────────────────────────────────────────────────
  function HeatSection() {
    const rows = ["пн","вт","ср","чт","пт","сб","вс"];
    return (
      <div style={{ marginBottom:40 }}>
        <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-end", paddingBottom:8, borderBottom:"1px solid var(--hairline)", marginBottom:12 }}>
          <div>
            <div style={{ fontSize:9, letterSpacing:"0.16em", textTransform:"uppercase", color:"var(--ink-4)", fontWeight:500, marginBottom:3 }}>04 · 4 недели</div>
            <h2 style={{ fontFamily:"var(--serif)", fontSize:20, fontWeight:400, margin:0, letterSpacing:"-0.01em" }}>Когда вы едите</h2>
          </div>
        </div>
        <div style={{ display:"flex", gap:3, marginBottom:2, paddingLeft:20, fontFamily:"var(--mono)", fontSize:8, color:"var(--ink-4)" }}>
          {[0,3,6,9,12,15,18,21].map(h => (
            <span key={h} style={{ flex:"0 0 auto", width: `calc(${(3/24)*100}% - 2px)`, textAlign:"center" }}>{String(h).padStart(2,"0")}</span>
          ))}
        </div>
        <div style={{ display:"flex", flexDirection:"column", gap:2 }}>
          {rows.map((r, ri) => (
            <div key={r} style={{ display:"flex", gap:3, alignItems:"center" }}>
              <span style={{ fontFamily:"var(--mono)", fontSize:9, color:"var(--ink-4)", width:16, flexShrink:0 }}>{r}</span>
              <div style={{ display:"flex", gap:3, flex:1 }}>
                {heatCells[ri].map((v, ci) => (
                  <div key={ci} style={{
                    flex:1, height:16,
                    background: v < 0.05 ? "var(--shade)" : `oklch(${0.94 - v*0.18} ${0.015 + v*0.08} 78 / ${0.3 + v*0.7})`,
                    borderRadius:1, cursor:"default",
                  }}/>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  // ── 6. Footer: quality + behaviour metrics ────────────────────────────
  function QualityFooter() {
    const [open, setOpen] = React.useState(false);
    return (
      <div style={{ borderTop:"2px solid var(--ink)", paddingTop:14 }}>
        <div style={{ fontSize:11, color:"var(--ink-3)", marginBottom:8 }}>
          <span className="mono" style={{ fontSize:10 }}>
            <b style={{ color:"var(--ink)" }}>92%</b> с этикеткой ·
            <span style={{ color:"var(--hairline-2)", margin:"0 6px" }}>•</span>
            <b style={{ color:"var(--ink)" }}>16</b> из базы ·
            <span style={{ color:"var(--hairline-2)", margin:"0 6px" }}>•</span>
            <b style={{ color:"var(--ink)" }}>2</b> вручную ·
            <span style={{ color:"var(--hairline-2)", margin:"0 6px" }}>•</span>
            <b style={{ color:"var(--warn)" }}>3</b> низкой увер.
          </span>
        </div>
        <div style={{ fontSize:9, letterSpacing:"0.12em", textTransform:"uppercase", color:"var(--ink-4)", marginBottom:10, fontWeight:500 }}>
          Поведение
        </div>
        <div style={{ display:"grid", gridTemplateColumns:"repeat(3,1fr)", gap:16, fontSize:11 }}>
          <div>
            <div className="mono" style={{ fontSize:11, fontWeight:500 }}>10.5 ч</div>
            <div style={{ color:"var(--ink-3)", fontSize:10, marginTop:2 }}>окно питания</div>
          </div>
          <div>
            <div className="mono" style={{ fontSize:11, fontWeight:500 }}>&lt;1 ч</div>
            <div style={{ color:"var(--ink-3)", fontSize:10, marginTop:2 }}>с последней еды</div>
          </div>
          <div>
            <div className="mono" style={{ fontSize:11, fontWeight:500 }}>7</div>
            <div style={{ color:"var(--ink-3)", fontSize:10, marginTop:2 }}>записей сегодня</div>
          </div>
        </div>
      </div>
    );
  }

  // ── page ────────────────────────────────────────────────────────────────
  return (
    <Shell active="Статистика">
      <div style={{ padding:"24px 48px 64px", maxWidth:1040 }}>
        {/* Head */}
        <div style={{ marginBottom:8 }}>
          <div style={{ fontSize:9, letterSpacing:"0.18em", textTransform:"uppercase", color:"var(--ink-4)", marginBottom:4, fontWeight:500 }}>
            статистика
          </div>
          <h1 style={{ fontFamily:"var(--serif)", fontSize:40, fontWeight:400, margin:0, letterSpacing:"-0.02em", lineHeight:1.05 }}>
            3 мая 2026 г.
          </h1>
        </div>

        <Headline />
        <KpiStrip />
        <PairedCharts />
        <GlucoseSection />
        <HeatSection />
        <QualityFooter />
      </div>
    </Shell>
  );
}

window.StatsPage = StatsPage;
