import { I } from './Icons'
import type { Product } from '../mock/products'

export default function DbItemPanel({ item }: { item: Product }) {
  return (
    <div>
      <div className="row" style={{ alignItems: "flex-start", gap: 12 }}>
        <div className="thumb" style={{ width: 56, height: 56, borderRadius: 3, background: item.color || "var(--shade)" }} />
        <div style={{ flex: 1 }}>
          <h2 style={{ fontSize: 18 }}>{item.name}</h2>
          <div className="mono" style={{ fontSize: 10, color: "var(--ink-4)", marginTop: 4 }}>{item.src}</div>
          <div className="row gap-4" style={{ marginTop: 8 }}>
            <span className="tag warn">не проверено</span>
            <span className="tag">label_calc</span>
          </div>
        </div>
      </div>

      <div className="panel-section">
        <div className="lbl">Макро на 100 г</div>
        <div className="row" style={{ gap: 0, marginTop: 6, borderTop: "1px solid var(--hairline)", borderBottom: "1px solid var(--hairline)" }}>
          {[
            { l: "У", v: item.c, c: "var(--accent)" },
            { l: "Б", v: item.p, c: "var(--ink)" },
            { l: "Ж", v: item.f, c: "var(--ink-3)" },
            { l: "ккал", v: item.k, c: "var(--ink)" },
          ].map((m, i) => (
            <div key={i} style={{ flex: 1, padding: "10px 0", borderRight: i < 3 ? "1px solid var(--hairline)" : "none", textAlign: "center" }}>
              <div className="mono" style={{ fontSize: 14, fontWeight: 500, color: m.c }}>{m.v}</div>
              <div className="lbl" style={{ marginTop: 2, fontSize: 9 }}>{m.l}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="panel-section">
        <div className="lbl">Псевдонимы</div>
        <div className="row gap-4" style={{ marginTop: 6, flexWrap: "wrap" }}>
          <span className="tag">кола</span>
          <span className="tag">cola</span>
          <span className="tag">черноголовка</span>
          <button className="tag" style={{ cursor: "pointer", borderStyle: "dashed" }}>+ добавить</button>
        </div>
      </div>

      <div className="panel-section">
        <div className="lbl">Источник данных</div>
        <div style={{ fontSize: 12, marginTop: 4 }}>{item.src}</div>
        <div className="row gap-8" style={{ marginTop: 10 }}>
          <button className="btn" style={{ flex: 1 }}><I.Edit size={12} /> Править</button>
          <button className="btn" style={{ flex: 1 }}><I.Check size={12} /> Проверено</button>
        </div>
      </div>

      <div className="panel-section">
        <div className="lbl">История использования</div>
        <div style={{ fontSize: 12, marginTop: 6 }}>
          <b className="mono">12×</b> за 7 дней · последний приём <span className="mono">сегодня 16:04</span>
        </div>
      </div>

      <div className="panel-section">
        <button className="btn" style={{ width: "100%", justifyContent: "center", color: "var(--warn)", borderColor: "var(--warn-soft)" }}>
          <I.Trash size={13} /> Удалить из базы
        </button>
      </div>
    </div>
  )
}
