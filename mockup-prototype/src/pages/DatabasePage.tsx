import { useState } from 'react'
import { I } from '../components/Icons'
import PageHead from '../components/PageHead'
import RightPanel from '../components/RightPanel'
import DbItemPanel from '../components/DbItemPanel'
import { products, Product } from '../mock/products'

const tabs = ["Частые", "Рестораны", "Продукты", "Шаблоны", "Требуют проверки"]

export default function DatabasePage() {
  const [selectedItem, setSelectedItem] = useState<Product | null>(null)
  const [activeTab, setActiveTab] = useState("Частые")

  return (
    <div style={{ display: 'flex', height: '100%' }}>
      <div style={{ flex: 1, overflow: 'auto' }}>
        <div className="gt-page">
          <PageHead crumbs={["продукты", "шаблоны", "рестораны", "импорт"]} title="База" right={
            <div className="row gap-8">
              <button className="btn"><I.Pkg size={13} /> Импорт</button>
              <button className="btn dark"><I.Plus size={13} /> Добавить вручную</button>
            </div>
          } />

          <div className="card" style={{ padding: 14, marginBottom: 14 }}>
            <div className="row gap-12" style={{ alignItems: "center" }}>
              <div className="input-bar" style={{ flex: 1, height: 32 }}>
                <I.Search size={14} style={{ color: "var(--ink-4)" }} />
                <input placeholder="Поиск по базе…" />
              </div>
              <div className="field" style={{ width: 180 }}>
                <input defaultValue="Все источники" />
              </div>
              <div className="field" style={{ width: 140 }}>
                <input defaultValue="Все типы" />
              </div>
            </div>
          </div>

          <div className="row gap-8" style={{ marginBottom: 12 }}>
            {tabs.map((t, i) => (
              <button key={i} className={`btn${activeTab === t ? " dark" : ""}`} onClick={() => setActiveTab(t)}>
                {t}{t === "Требуют проверки" && <span className="tag warn" style={{ marginLeft: 4 }}>12</span>}
              </button>
            ))}
          </div>

          <div className="card">
            {products.map((it, i) => (
              <div key={i} className="row clickable-row" onClick={() => setSelectedItem(selectedItem === it ? null : it)} style={{
                alignItems: "center", padding: "12px 18px",
                borderBottom: i < products.length - 1 ? "1px solid var(--hairline)" : "none",
                gap: 14,
                background: selectedItem === it ? "var(--surface-2)" : "transparent",
                boxShadow: selectedItem === it ? "inset 2px 0 0 var(--ink)" : "none",
              }}>
                <div className="thumb" style={{ background: it.color, width: 44, height: 44, borderRadius: 3, display: 'flex', alignItems: 'center', justifyContent: 'center' }}><I.Photo size={14} style={{ color: "rgba(255,255,255,0.7)" }} /></div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13 }}>{it.name}</div>
                  <div className="mono" style={{ fontSize: 10, color: "var(--ink-4)", marginTop: 3, letterSpacing: 0.04 }}>{it.src}</div>
                </div>
                <span className="tag warn" style={{ fontSize: 9 }}>не проверено</span>
                <div style={{ width: 64 }}>
                  <div className="mp">
                    <div className="mp-bar c"><i style={{ width: `${Math.min(100, it.c * 1.4)}%` }} /></div>
                    <div className="mp-bar p"><i style={{ width: `${Math.min(100, it.p * 2.5)}%` }} /></div>
                    <div className="mp-bar f"><i style={{ width: `${Math.min(100, it.f * 2)}%` }} /></div>
                  </div>
                </div>
                <span className="mono" style={{ fontSize: 12, width: 36, textAlign: "right", color: "var(--accent)" }}>{it.c}<span style={{ color: "var(--ink-4)" }}>у</span></span>
                <span className="mono" style={{ fontSize: 12, width: 36, textAlign: "right" }}>{it.p}<span style={{ color: "var(--ink-4)" }}>б</span></span>
                <span className="mono" style={{ fontSize: 12, width: 36, textAlign: "right" }}>{it.f}<span style={{ color: "var(--ink-4)" }}>ж</span></span>
                <span className="mono" style={{ fontSize: 13, width: 70, textAlign: "right", fontWeight: 500 }}>{it.k} ккал</span>
                <button className="btn icon" style={{ border: "none", background: "transparent" }} onClick={(e) => e.stopPropagation()}><I.More size={14} /></button>
              </div>
            ))}
          </div>
        </div>
      </div>

      {selectedItem && (
        <RightPanel onClose={() => setSelectedItem(null)}>
          <DbItemPanel item={selectedItem} />
        </RightPanel>
      )}
    </div>
  )
}
