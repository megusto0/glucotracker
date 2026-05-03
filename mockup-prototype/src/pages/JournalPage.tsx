import { useState } from 'react'
import { I } from '../components/Icons'
import PageHead from '../components/PageHead'
import RightPanel from '../components/RightPanel'
import SelectedMealPanel from '../components/SelectedMealPanel'
import AutocompletePanel from '../components/AutocompletePanel'
import { todayMeals } from '../mock/meals'

export default function JournalPage() {
  const [selectedIdx, setSelectedIdx] = useState(-1)
  const [inputValue, setInputValue] = useState("bk:whopper")
  const [showAutocomplete, setShowAutocomplete] = useState(false)

  const hasPanel = selectedIdx >= 0 || showAutocomplete

  return (
    <div style={{ display: 'flex', height: '100%' }}>
      <div style={{ flex: 1, overflow: 'auto' }}>
        <div className="gt-page">
          <PageHead crumbs={["суббота"]} title="2 мая 2026 г." right={
            <div className="row gap-8">
              <button className="btn icon"><I.ChevL size={14} /></button>
              <button className="btn">Сегодня</button>
              <button className="btn icon"><I.ChevR size={14} /></button>
              <div style={{ width: 12 }} />
              <button className="btn"><I.Cal size={13} /> 2 мая</button>
            </div>
          } />

          {/* KPI strip */}
          <div className="kpi" style={{ marginBottom: 8 }}>
            <div>
              <div className="lbl">углеводы</div>
              <div className="kpi-val" style={{ marginTop: 8 }}>111<span className="u">г</span></div>
              <div className="pbar accent" style={{ marginTop: 10 }}><i style={{ width: "49%" }} /></div>
              <div className="kpi-sub">цель 225 г · <span className="mono">49%</span></div>
            </div>
            <div>
              <div className="lbl">ккал</div>
              <div className="kpi-val" style={{ marginTop: 8 }}>1587<span className="u">ккал</span></div>
              <div className="pbar good" style={{ marginTop: 10 }}><i style={{ width: "72%" }} /></div>
              <div className="kpi-sub">цель 2200 · <span className="mono">72%</span></div>
            </div>
            <div>
              <div className="lbl">белки · жиры · клетчатка</div>
              <div className="row gap-12" style={{ marginTop: 8, alignItems: "baseline" }}>
                <span className="mono" style={{ fontSize: 20, fontWeight: 500 }}>79<span style={{ fontSize: 10, color: "var(--ink-3)", marginLeft: 2 }}>г Б</span></span>
                <span className="mono" style={{ fontSize: 20, fontWeight: 500 }}>91<span style={{ fontSize: 10, color: "var(--ink-3)", marginLeft: 2 }}>г Ж</span></span>
                <span className="mono" style={{ fontSize: 20, fontWeight: 500 }}>12<span style={{ fontSize: 10, color: "var(--ink-3)", marginLeft: 2 }}>г Кл</span></span>
              </div>
              <div className="kpi-sub" style={{ marginTop: 10 }}>сред. за неделю · <span className="mono">92 / 89 / 14 г</span></div>
            </div>
            <div>
              <div className="lbl">баланс по TDEE</div>
              <div className="kpi-val" style={{ marginTop: 8, color: "var(--good)" }}>−1242<span className="u">ккал</span></div>
              <div className="kpi-sub" style={{ marginTop: 10 }}>дефицит · TDEE <span className="mono">2829</span></div>
              <div className="row gap-6" style={{ marginTop: 6, alignItems: "center" }}>
                <span className="dot-marker" style={{ background: "var(--good)" }} />
                <span style={{ fontSize: 11, color: "var(--good)" }}>в цели</span>
              </div>
            </div>
          </div>

          {/* Nightscout strip */}
          <div className="row" style={{
            alignItems: "center", padding: "10px 14px", marginTop: 18, marginBottom: 10,
            background: "var(--surface)", border: "1px solid var(--hairline)", borderRadius: "var(--radius-lg)", gap: 12,
          }}>
            <span className="dot-marker" style={{ background: "var(--good)" }} />
            <span style={{ fontSize: 12 }}>Nightscout подключён</span>
            <span style={{ fontSize: 11, color: "var(--ink-3)" }}>несинхронизировано: <b className="mono" style={{ color: "var(--ink)", fontWeight: 500 }}>7</b></span>
            <span className="spacer" />
            <button className="btn-link">просмотр истории →</button>
            <button className="btn"><I.Send size={12} /> Отправить день в Nightscout</button>
          </div>

          {/* meals list */}
          <div className="card" style={{ padding: "8px 16px", marginTop: 6 }}>
            {todayMeals.map((m, i) => (
              <div key={i} className="meal clickable-row" onClick={() => setSelectedIdx(selectedIdx === i ? -1 : i)} style={{
                borderBottom: i < todayMeals.length - 1 ? "1px solid var(--hairline)" : "none",
                background: selectedIdx === i ? "var(--surface-2)" : "transparent",
                boxShadow: selectedIdx === i ? "inset 2px 0 0 var(--ink)" : "none",
                paddingLeft: selectedIdx === i ? 8 : 0,
                marginLeft: selectedIdx === i ? -8 : 0,
              }}>
                <span className="time">{m.time}</span>
                <div className="thumb" style={{ background: m.color }}>
                  {m.tag === "фото" ? <I.Photo size={14} style={{ color: "rgba(255,255,255,0.7)" }} /> : null}
                </div>
                <div>
                  <div className="title">{m.title}</div>
                  <div className="sub">
                    {m.sub.map((s, j) => <span key={j}>{j > 0 ? "·" : ""} {s}</span>)}
                  </div>
                </div>
                <div style={{ width: 70 }}>
                  <div className="mp">
                    <div className="mp-bar c"><i style={{ width: `${Math.min(100, m.c * 1.5)}%` }} /></div>
                    <div className="mp-bar p"><i style={{ width: `${Math.min(100, m.p * 2)}%` }} /></div>
                    <div className="mp-bar f"><i style={{ width: `${Math.min(100, m.f * 2)}%` }} /></div>
                  </div>
                </div>
                <span className="v"><span style={{ color: "var(--accent)" }}>{m.c}</span><span className="u">У</span></span>
                <span className="v">{m.p}<span className="u">Б</span></span>
                <span className="v">{m.f}<span className="u">Ж</span></span>
                <span className="v kcal">{m.k}<span className="u"> ккал</span></span>
                <button className="btn icon" style={{ border: "none", background: "transparent" }} onClick={(e) => e.stopPropagation()}><I.More size={14} /></button>
              </div>
            ))}
          </div>

          {/* input */}
          <div className="row gap-12" style={{ marginTop: 18, alignItems: "center" }}>
            <div className="input-bar" style={{ flex: 1, borderColor: showAutocomplete ? "var(--ink)" : "var(--hairline-2)" }}>
              <button className="btn icon" style={{ border: "none", background: "transparent" }}><I.Plus size={16} /></button>
              <span className="mono" style={{ color: "var(--ink-4)" }}>{">"}</span>
              <input value={inputValue}
                onChange={(e) => {
                  setInputValue(e.target.value)
                  setShowAutocomplete(e.target.value.length > 0)
                  if (e.target.value.length > 0) setSelectedIdx(-1)
                }}
                onFocus={() => { if (inputValue.length > 0) { setShowAutocomplete(true); setSelectedIdx(-1) } }}
                placeholder="bk:whopper · введите еду или используйте префикс bk: / mc:" />
              {showAutocomplete && <button className="btn icon" style={{ border: "none", background: "transparent" }} onClick={() => { setShowAutocomplete(false); setInputValue("") }}><I.X size={14} /></button>}
              <button className="send-btn"><I.ArrowR size={14} /></button>
            </div>
            <button className="btn"><I.Camera size={13} /> Фото</button>
          </div>
          <div style={{ fontSize: 11, color: "var(--ink-4)", marginTop: 8, marginLeft: 4 }}>
            подсказки: <span className="mono">bk:</span> Burger King · <span className="mono">mc:</span> McDonald's · перетащите фото — Gemini оценит макросы
          </div>
        </div>
      </div>

      {hasPanel && (
        <RightPanel onClose={() => { setSelectedIdx(-1); setShowAutocomplete(false) }}>
          {showAutocomplete ? (
            <AutocompletePanel query={inputValue} />
          ) : selectedIdx >= 0 ? (
            <SelectedMealPanel meal={todayMeals[selectedIdx]} />
          ) : null}
        </RightPanel>
      )}
    </div>
  )
}
