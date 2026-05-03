import { I } from './Icons'
import { autocompleteItems } from '../mock/meals'

export default function AutocompletePanel({ query = "Воп" }: { query?: string }) {
  return (
    <div>
      <div className="lbl">автозаполнение</div>
      <h2 style={{ fontFamily: "var(--serif)" }}>{query}</h2>
      <div style={{ fontSize: 11, color: "var(--ink-3)", marginTop: 4 }}>
        {autocompleteItems.length} совпадений · <span className="mono">bk:</span> Burger King
      </div>

      <div style={{ marginTop: 18 }}>
        <div className="lbl" style={{ marginBottom: 6 }}>Частые</div>
        {autocompleteItems.map((it, i) => (
          <div key={i} className="ac-item">
            <div className="thumb" style={{
              background: i === 0 ? "#7B4A2A" : "var(--shade)",
              display: "flex", alignItems: "center", justifyContent: "center",
              color: i === 0 ? "rgba(255,255,255,0.8)" : "var(--ink-4)"
            }}>
              <I.Photo size={14} />
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 12.5, fontWeight: 500 }}>{it.name}</div>
              <div className="mono" style={{ fontSize: 10, color: "var(--ink-4)", marginTop: 2, textOverflow: "ellipsis", overflow: "hidden", whiteSpace: "nowrap" }}>{it.src}</div>
              <div className="mono" style={{ fontSize: 10, color: "var(--ink-3)", marginTop: 4 }}>
                <span style={{ color: "var(--accent)" }}>{it.c}У</span> · {it.p}Б · {it.f}Ж · <b style={{ color: "var(--ink)", fontWeight: 500 }}>{it.k} ккал</b>
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="panel-row" style={{ justifyContent: "space-between", padding: "14px 0", borderTop: "1px solid var(--hairline)", marginTop: 6 }}>
        <span style={{ fontSize: 11, color: "var(--ink-3)" }}>Показать все результаты для «{query}»</span>
        <I.ArrowR size={14} style={{ color: "var(--ink-3)" }} />
      </div>
    </div>
  )
}
