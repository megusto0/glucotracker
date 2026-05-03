/* global React, I */

// ───── Right panel: autocomplete (typing) ─────
function AutocompletePanel({ query = "Воп" }) {
  const items = [
    { name: "Воппер",                  src: "Ресторан · bk:whopper",         c: 53, p: 27, f: 44, k: 720 },
    { name: "Воппер Джуниор",          src: "Ресторан · bk:whopper_jr",      c: 33, p: 13, f: 21, k: 370 },
    { name: "Воппер По-Итальянски",    src: "Ресторан · bk:whopper_ital",    c: 56, p: 29, f: 45, k: 750 },
    { name: "Воппер По-Итальянски Двойной", src: "Ресторан · bk:whopper_ital_dbl", c: 59, p: 49, f: 76, k: 1120 },
    { name: "Воппер Ролл",             src: "Ресторан · bk:whopper_roll",    c: 34, p: 21, f: 36, k: 540 },
    { name: "Воппер С Сыром",          src: "Ресторан · bk:whopper_cheese",  c: 54, p: 31, f: 50, k: 790 },
    { name: "Атомик Воппер",           src: "Ресторан · bk:atomic_whopper",  c: 56, p: 42, f: 43, k: 710 },
  ];
  return (
    <div>
      <div className="lbl">автозаполнение</div>
      <h2 style={{ fontFamily: "var(--serif)" }}>{query}</h2>
      <div style={{ fontSize: 11, color: "var(--ink-3)", marginTop: 4 }}>
        {items.length} совпадений · <span className="mono">bk:</span> Burger King
      </div>

      <div style={{ marginTop: 18 }}>
        <div className="lbl" style={{ marginBottom: 6 }}>Частые</div>
        {items.map((it, i) => (
          <div key={i} className="ac-item">
            <div className="thumb" style={{ background: i === 0 ? "#7B4A2A" : "var(--shade)", display: "flex", alignItems: "center", justifyContent: "center", color: "rgba(255,255,255,0.8)" }}>
              {i === 0 ? <I.Photo size={14}/> : <span style={{ color: "var(--ink-4)" }}><I.Photo size={14}/></span>}
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
        <I.ArrowR size={14} style={{ color: "var(--ink-3)" }}/>
      </div>
    </div>
  );
}

// ───── Right panel: selected meal (Журнал/История) ─────
function SelectedMealPanel({ meal }) {
  if (!meal) return null;
  return (
    <div>
      <div className="row" style={{ alignItems: "flex-start", gap: 12 }}>
        <div className="thumb" style={{ width: 56, height: 56, borderRadius: 3, background: meal.color || "var(--shade)" }}/>
        <div style={{ flex: 1 }}>
          <h2>{meal.title}</h2>
          <div style={{ fontSize: 11, color: "var(--ink-3)", marginTop: 2 }}>{meal.brand || "Черноголовка"}</div>
          <div className="row gap-4" style={{ marginTop: 8, flexWrap: "wrap" }}>
            <span className="tag">смешано</span>
            <span className="tag good">принято</span>
            <span className="tag">{meal.weight || 330} г</span>
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
            style={{ flex: 1, height: 30, padding: "0 10px", border: "1px solid var(--hairline-2)", background: "var(--surface)", borderRadius: 2, fontSize: 12 }}/>
          <button className="btn dark" style={{ height: 30 }}>Сохранить</button>
        </div>
        <div style={{ fontSize: 10, color: "var(--ink-4)", marginTop: 6 }}>
          Обновит название записи, позиции и продукта в базе.
        </div>
      </div>

      <div className="panel-section">
        <div className="lbl">Дата и время записи</div>
        <div className="row gap-8" style={{ alignItems: "center", marginTop: 4 }}>
          <input className="mono" defaultValue="02.05.2026 16:04"
            style={{ flex: 1, height: 30, padding: "0 10px", border: "1px solid var(--hairline-2)", background: "var(--surface)", borderRadius: 2, fontSize: 12 }}/>
          <button className="btn" style={{ height: 30 }}>Сохранить</button>
        </div>
        <div style={{ fontSize: 10, color: "var(--ink-4)", marginTop: 6 }}>
          2 мая 2026 г. · текущее: <span className="mono">2026-05-02 16:04</span><br/>
          Если изменить день, запись переместится в журнал этого дня.
        </div>
      </div>

      <div className="panel-section">
        <div className="lbl">Вес текущей записи</div>
        <div style={{ fontSize: 11, color: "var(--ink-3)", margin: "4px 0 8px" }}>
          Изменит эту запись. Backend пересчитает углеводы, ккал и макросы пропорционально весу.
        </div>
        <div className="row gap-8" style={{ alignItems: "center" }}>
          <input className="mono" defaultValue="330"
            style={{ flex: 1, height: 30, padding: "0 10px", border: "1px solid var(--hairline-2)", background: "var(--surface)", borderRadius: 2, fontSize: 12 }}/>
          <button className="btn dark" style={{ height: 30 }}>Сохранить вес</button>
        </div>
      </div>

      <div className="panel-section">
        <div className="lbl">Повтор по весу</div>
        <div style={{ fontSize: 11, color: "var(--ink-3)", margin: "4px 0 8px" }}>
          Оставит 330 г. Backend пересчитает значения на новый вес и создаст запись сейчас.
        </div>
        <div className="row gap-8" style={{ alignItems: "center" }}>
          <input className="mono" defaultValue="100"
            style={{ flex: 1, height: 30, padding: "0 10px", border: "1px solid var(--hairline-2)", background: "var(--surface)", borderRadius: 2, fontSize: 12 }}/>
          <button className="btn dark" style={{ height: 30 }}>Добавить 100 г</button>
        </div>
        <div className="row gap-4" style={{ marginTop: 8, flexWrap: "wrap" }}>
          <button className="btn" style={{ height: 26, fontSize: 11 }}>100 г</button>
          <button className="btn" style={{ height: 26, fontSize: 11 }}>127 г</button>
          <button className="btn" style={{ height: 26, fontSize: 11 }}>330 г</button>
        </div>
      </div>

      <div className="panel-section">
        <button className="btn" style={{ width: "100%", justifyContent: "center", color: "var(--warn)", borderColor: "var(--warn-soft)" }}>
          <I.Trash size={13}/> Удалить
        </button>
        <div style={{ fontSize: 10, color: "var(--ink-4)", marginTop: 8, textAlign: "center" }}>
          Это оценка, не медицинская рекомендация.
        </div>
      </div>
    </div>
  );
}

// ───── Right panel: DB item ─────
function DbItemPanel({ item }) {
  if (!item) return null;
  return (
    <div>
      <div className="row" style={{ alignItems: "flex-start", gap: 12 }}>
        <div className="thumb" style={{ width: 56, height: 56, borderRadius: 3, background: item.color || "var(--shade)" }}/>
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
          <button className="btn" style={{ flex: 1 }}><I.Edit size={12}/> Править</button>
          <button className="btn" style={{ flex: 1 }}><I.Check size={12}/> Проверено</button>
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
          <I.Trash size={13}/> Удалить из базы
        </button>
      </div>
    </div>
  );
}

window.AutocompletePanel = AutocompletePanel;
window.SelectedMealPanel = SelectedMealPanel;
window.DbItemPanel = DbItemPanel;
