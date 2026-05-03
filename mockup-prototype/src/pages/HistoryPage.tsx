import { useState } from 'react'
import { I } from '../components/Icons'
import PageHead from '../components/PageHead'
import RightPanel from '../components/RightPanel'
import SelectedMealPanel from '../components/SelectedMealPanel'
import type { Meal } from '../mock/meals'

const historyEpisodes = [
  {
    id: 'ep1',
    timeRange: "15:43–16:04",
    title: "Пищевой эпизод",
    detail: "4 события · 878 ккал · 64.8 г углеводов · 1 запись инсулина",
    peakInfo: "пик глюкозы 10.1 через 12 мин",
    insulinInfo: "инсулин 1.6 ЕД",
    items: [
      { time: "15:43", t: "Лаваш с курицей и овощами", c: "27.1 г", k: "634 ккал" },
      { time: "15:52", t: "Cheetos Пицца", c: "22.2 г", k: "181 ккал" },
      { time: "16:04", t: "Кола Ориджинал", c: "15.5 г", k: "63 ккал" },
      { time: "17:40", t: "Инсулин из Nightscout · только чтение", c: "—", k: "1.6 ЕД", insulin: true },
    ],
  },
  {
    id: 'ep2',
    timeRange: "14:07",
    title: "Приём пищи",
    detail: "309 ккал · 21.7 г углеводов",
    compact: true,
    items: [
      { time: "14:07", t: "Сырок глазированный", c: "14 г", k: "165 ккал" },
      { time: "14:07", t: "Протеиновое брауни Shagi", c: "8 г", k: "144 ккал" },
    ],
  },
  {
    id: 'ep3',
    timeRange: "05:30",
    title: "Халва подсолнечная глазированная",
    detail: "110 ккал · 9 г",
    standalone: true,
    items: [{ time: "05:30", t: "Халва подсолнечная глазированная", c: "9 г", k: "110 ккал" }],
  },
  {
    id: 'ep4',
    timeRange: "05:15",
    title: "Творог со сметаной и замороженным фруктом",
    detail: "290 ккал · 15 г",
    standalone: true,
    items: [{ time: "05:15", t: "Творог со сметаной и замороженным фруктом", c: "15 г", k: "290 ккал" }],
  },
]

export default function HistoryPage() {
  const [selectedItem, setSelectedItem] = useState<Meal | null>(null)
  const [expandedEp, setExpandedEp] = useState<string | null>("ep1")

  return (
    <div style={{ display: 'flex', height: '100%' }}>
      <div style={{ flex: 1, overflow: 'auto' }}>
        <div className="gt-page">
          <PageHead crumbs={["история"]} title="История" right={
            <div className="row gap-8">
              <button className="btn"><I.Filter size={13} /> Активные</button>
              <button className="btn"><I.Cal size={13} /> Все даты</button>
            </div>
          } />

          {/* filters row */}
          <div className="card" style={{ padding: 14, marginBottom: 18 }}>
            <div className="row gap-12" style={{ alignItems: "center" }}>
              <div className="input-bar" style={{ flex: 1, height: 32 }}>
                <I.Search size={14} style={{ color: "var(--ink-4)" }} />
                <input placeholder="еда, заметка, позиция…" />
              </div>
              <div className="row gap-8">
                <div className="field" style={{ width: 130 }}>
                  <input className="mono" placeholder="дд.мм.гггг" defaultValue="01.04.2026" />
                </div>
                <span style={{ color: "var(--ink-4)" }}>→</span>
                <div className="field" style={{ width: 130 }}>
                  <input className="mono" placeholder="дд.мм.гггг" defaultValue="02.05.2026" />
                </div>
              </div>
              <div className="seg">
                <button className="on">с CGM</button>
                <button>с инсулином</button>
                <button>низкая увер.</button>
                <button>+</button>
              </div>
            </div>
          </div>

          {/* day section */}
          <div style={{ marginTop: 14 }}>
            <div className="row" style={{ alignItems: "baseline", padding: "8px 0", borderBottom: "1px solid var(--hairline)" }}>
              <h2 style={{ margin: 0, fontFamily: "var(--serif)", fontSize: 28, fontWeight: 400 }}>суббота, 2 мая</h2>
              <span className="spacer" />
              <div className="row gap-12" style={{ fontSize: 11, color: "var(--ink-3)" }}>
                <span><b className="mono" style={{ color: "var(--ink)", fontWeight: 500 }}>7</b> приёмов</span>
                <span><b className="mono" style={{ color: "var(--ink)", fontWeight: 500 }}>111 г</b> углеводы</span>
                <span><b className="mono" style={{ color: "var(--ink)", fontWeight: 500 }}>1587</b> ккал</span>
                <span><b className="mono" style={{ color: "var(--ink)", fontWeight: 500 }}>4</b> NS события</span>
                <span>tdee <b className="mono" style={{ color: "var(--ink)", fontWeight: 500 }}>2829</b></span>
                <span>баланс <b className="mono" style={{ color: "var(--good)", fontWeight: 500 }}>−1242</b></span>
              </div>
            </div>

            {historyEpisodes.map((ep) => (
              <div key={ep.id} className="card clickable-row" style={{
                marginTop: 14, padding: 0, cursor: 'pointer',
                background: expandedEp === ep.id ? 'var(--surface)' : 'var(--surface)',
              }}
                onClick={() => setExpandedEp(expandedEp === ep.id ? null : ep.id)}>
                <div className="row" style={{ padding: "14px 18px", gap: 16, alignItems: "center" }}>
                  <div className="mono" style={{ width: 80, fontSize: 11, color: "var(--ink-3)" }}>{ep.timeRange}</div>
                  <div style={{ flex: 1 }}>
                    <div className="row gap-8" style={{ alignItems: "center" }}>
                      <span style={{ fontSize: 14, fontWeight: 500 }}>{ep.title}</span>
                      {!ep.standalone && <span className="tag accent">{ep.timeRange}</span>}
                    </div>
                    <div style={{ fontSize: 11, color: "var(--ink-3)", marginTop: 4 }}>{ep.detail}</div>
                    {ep.peakInfo && (
                      <div className="row gap-12" style={{ marginTop: 6, fontSize: 11, color: "var(--ink-3)" }}>
                        <span>{ep.peakInfo}</span>
                        {ep.insulinInfo && <span>{ep.insulinInfo}</span>}
                      </div>
                    )}
                  </div>
                  <div style={{ color: 'var(--ink-4)', transform: expandedEp === ep.id ? 'rotate(180deg)' : 'none', transition: 'transform 0.15s' }}>
                    <I.ChevD size={14} />
                  </div>
                </div>
                {expandedEp === ep.id && ep.items.length > 0 && (
                  <div style={{ borderTop: '1px solid var(--hairline)' }}>
                    {ep.items.map((r, i) => (
                      <div key={i} className="row clickable-row" style={{
                        padding: "10px 18px",
                        borderBottom: i < ep.items.length - 1 ? "1px solid var(--hairline)" : "none",
                        alignItems: "center", gap: 14,
                      }}
                        onClick={(e) => {
                          e.stopPropagation()
                          if (!('insulin' in r && r.insulin)) {
                            setSelectedItem({
                              time: r.time, title: r.t, sub: ["принято"], c: 20, p: 10, f: 8, k: parseInt(r.k) || 0,
                              color: "#C2A06A", brand: "", weight: 100,
                            })
                          }
                        }}>
                        <span className="mono" style={{ fontSize: 11, color: "var(--ink-3)", width: 64 }}>{r.time}</span>
                        <span style={{ flex: 1, fontSize: 13, color: ('insulin' in r && r.insulin) ? "var(--ink-3)" : "var(--ink)" }}>{r.t}</span>
                        {!('insulin' in r && r.insulin) && <span className="tag">принято</span>}
                        <span className="mono" style={{ fontSize: 12, width: 70, textAlign: "right" }}>{r.c}</span>
                        <span className="mono" style={{ fontSize: 12, width: 80, textAlign: "right", fontWeight: 500 }}>{r.k}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>

      {selectedItem && (
        <RightPanel onClose={() => setSelectedItem(null)}>
          <SelectedMealPanel meal={selectedItem} />
        </RightPanel>
      )}
    </div>
  )
}
