import { I } from './Icons'
import type { Meal } from '../mock/meals'

export default function SelectedMealPanel({ meal }: { meal: Meal }) {
  return (
    <div>
      <div className="row" style={{ alignItems: "flex-start", gap: 12 }}>
        <div className="thumb" style={{ width: 56, height: 56, borderRadius: 3, background: meal.color || "var(--shade)" }} />
        <div style={{ flex: 1 }}>
          <h2>{meal.title}</h2>
          <div style={{ fontSize: 11, color: "var(--ink-3)", marginTop: 2 }}>{meal.brand || ""}</div>
          <div className="row gap-4" style={{ marginTop: 8, flexWrap: "wrap" }}>
            <span className="tag">смешано</span>
            <span className="tag good">принято</span>
            <span className="tag">{meal.weight || 100} г</span>
          </div>
        </div>
        <div className="mono" style={{ fontSize: 22, fontWeight: 500, lineHeight: 1 }}>
          {meal.k}<span style={{ fontSize: 10, color: "var(--ink-3)", display: "block", textAlign: "right", marginTop: 2 }}>ккал</span>
        </div>
      </div>

      <div className="panel-section">
        <div className="lbl">Название</div>
        <div className="row gap-8" style={{ alignItems: "center", marginTop: 4 }}>
          <input className="mono" defaultValue={meal.title}
            style={{ flex: 1, height: 30, padding: "0 10px", border: "1px solid var(--hairline-2)", background: "var(--surface)", borderRadius: 2, fontSize: 12 }} />
          <button className="btn dark" style={{ height: 30 }}>Сохранить</button>
        </div>
      </div>

      <div className="panel-section">
        <div className="lbl">Дата и время записи</div>
        <div className="row gap-8" style={{ alignItems: "center", marginTop: 4 }}>
          <input className="mono" defaultValue="02.05.2026 16:04"
            style={{ flex: 1, height: 30, padding: "0 10px", border: "1px solid var(--hairline-2)", background: "var(--surface)", borderRadius: 2, fontSize: 12 }} />
          <button className="btn" style={{ height: 30 }}>Сохранить</button>
        </div>
      </div>

      <div className="panel-section">
        <div className="lbl">Вес текущей записи</div>
        <div style={{ fontSize: 11, color: "var(--ink-3)", margin: "4px 0 8px" }}>
          Изменит эту запись. Backend пересчитает углеводы, ккал и макросы пропорционально весу.
        </div>
        <div className="row gap-8" style={{ alignItems: "center" }}>
          <input className="mono" defaultValue={String(meal.weight || 100)}
            style={{ flex: 1, height: 30, padding: "0 10px", border: "1px solid var(--hairline-2)", background: "var(--surface)", borderRadius: 2, fontSize: 12 }} />
          <button className="btn dark" style={{ height: 30 }}>Сохранить вес</button>
        </div>
      </div>

      <div className="panel-section">
        <div className="lbl">Повтор по весу</div>
        <div style={{ fontSize: 11, color: "var(--ink-3)", margin: "4px 0 8px" }}>
          Создаст новую запись с указанным весом.
        </div>
        <div className="row gap-8" style={{ alignItems: "center" }}>
          <input className="mono" defaultValue="100"
            style={{ flex: 1, height: 30, padding: "0 10px", border: "1px solid var(--hairline-2)", background: "var(--surface)", borderRadius: 2, fontSize: 12 }} />
          <button className="btn dark" style={{ height: 30 }}>Добавить 100 г</button>
        </div>
        <div className="row gap-4" style={{ marginTop: 8, flexWrap: "wrap" }}>
          <button className="btn" style={{ height: 26, fontSize: 11 }}>100 г</button>
          <button className="btn" style={{ height: 26, fontSize: 11 }}>127 г</button>
          <button className="btn" style={{ height: 26, fontSize: 11 }}>{meal.weight || 100} г</button>
        </div>
      </div>

      <div className="panel-section">
        <button className="btn" style={{ width: "100%", justifyContent: "center", color: "var(--warn)", borderColor: "var(--warn-soft)" }}>
          <I.Trash size={13} /> Удалить
        </button>
        <div style={{ fontSize: 10, color: "var(--ink-4)", marginTop: 8, textAlign: "center" }}>
          Это оценка, не медицинская рекомендация.
        </div>
      </div>
    </div>
  )
}
