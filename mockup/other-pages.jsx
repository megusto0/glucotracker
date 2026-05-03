/* global React, I, Shell, PageHead, AutocompletePanel, SelectedMealPanel, DbItemPanel */

// ───── Journal page ─────
function JournalPage({ panelMode = "none" }) {
  const meals = [
    { time: "16:04", title: "Кола Ориджинал", sub: ["Черноголовка", "смешано", "330 г"], c: 16, p: 0, f: 0, k: 63, color: "#7B2A2A", brand: "Черноголовка", weight: 330 },
    { time: "15:52", title: "Cheetos Пицца", sub: ["БРЕНДЫ", "принято", "37 г"], c: 22, p: 3, f: 9, k: 181, color: "#C95A2E" },
    { time: "15:45", title: "Лаваш с курицей и овощами", sub: ["фото", "принято", "324 г"], c: 27, p: 40, f: 41, k: 634, color: "#C2A06A", tag: "фото" },
    { time: "14:07", title: "Протеиновое брауни Shagi", sub: ["смешано", "принято", "33 г"], c: 8, p: 4, f: 11, k: 144, color: "#3F2E22" },
    { time: "14:07", title: "Сырок глазированный", sub: ["смешано", "принято", "40 г"], c: 14, p: 3, f: 10, k: 165, color: "#7C5A36" },
    { time: "05:30", title: "Халва подсолнечная глазированная", sub: ["восточный гость", "принято", "20 г"], c: 9, p: 2, f: 7, k: 110, color: "#9C6E3F" },
    { time: "05:15", title: "Творог со сметаной и замороженным фруктом", sub: ["фото", "принято", "150 г"], c: 15, p: 28, f: 14, k: 290, color: "#E2D4B5", tag: "фото" },
  ];

  const inputValue = panelMode === "autocomplete" ? "Воп" : "bk:whopper";
  const selectedIdx = panelMode === "selected-meal" ? 0 : -1;
  const rightPanel =
    panelMode === "autocomplete" ? <AutocompletePanel query="Воп" /> :
    panelMode === "selected-meal" ? <SelectedMealPanel meal={meals[0]} /> :
    null;

  return (
    <Shell active="Журнал" rightPanel={rightPanel}>
      <div className="gt-page">
        <PageHead crumbs={["суббота"]} title="2 мая 2026 г." right={
          <div className="row gap-8">
            <button className="btn icon"><I.ChevL size={14}/></button>
            <button className="btn">Сегодня</button>
            <button className="btn icon"><I.ChevR size={14}/></button>
            <div style={{ width: 12 }} />
            <button className="btn"><I.Cal size={13}/> 2 мая</button>
          </div>
        }/>

        {/* KPI strip */}
        <div className="kpi" style={{ marginBottom: 8 }}>
          <div>
            <div className="lbl">углеводы</div>
            <div className="kpi-val" style={{ marginTop: 8 }}>111<span className="u">г</span></div>
            <div className="pbar accent" style={{ marginTop: 10 }}><i style={{ width: "49%" }}/></div>
            <div className="kpi-sub">цель 225 г · <span className="mono">49%</span></div>
          </div>
          <div>
            <div className="lbl">ккал</div>
            <div className="kpi-val" style={{ marginTop: 8 }}>1587<span className="u">ккал</span></div>
            <div className="pbar good" style={{ marginTop: 10 }}><i style={{ width: "72%" }}/></div>
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
              <span className="dot-marker" style={{ background: "var(--good)" }}/>
              <span style={{ fontSize: 11, color: "var(--good)" }}>в цели</span>
            </div>
          </div>
        </div>

        {/* Nightscout strip */}
        <div className="row" style={{
          alignItems: "center", padding: "10px 14px", marginTop: 18, marginBottom: 10,
          background: "var(--surface)", border: "1px solid var(--hairline)", borderRadius: "var(--radius-lg)", gap: 12,
        }}>
          <span className="dot-marker" style={{ background: "var(--good)" }}/>
          <span style={{ fontSize: 12 }}>Nightscout подключён</span>
          <span style={{ fontSize: 11, color: "var(--ink-3)" }}>несинхронизировано: <b className="mono" style={{ color: "var(--ink)", fontWeight: 500 }}>7</b></span>
          <span className="spacer"/>
          <button className="btn-link">просмотр истории →</button>
          <button className="btn"><I.Send size={12}/> Отправить день в Nightscout</button>
        </div>

        {/* meals list */}
        <div className="card" style={{ padding: "8px 16px", marginTop: 6 }}>
          {meals.map((m, i) => (
            <div key={i} className="meal" style={{
              borderBottom: i < meals.length - 1 ? "1px solid var(--hairline)" : "none",
              background: selectedIdx === i ? "var(--surface-2)" : "transparent",
              boxShadow: selectedIdx === i ? "inset 2px 0 0 var(--ink)" : "none",
              paddingLeft: selectedIdx === i ? 8 : 0,
              marginLeft: selectedIdx === i ? -8 : 0,
            }}>
              <span className="time">{m.time}</span>
              <div className="thumb" style={{ background: m.color }}>
                {m.tag === "фото" ? <I.Photo size={14} style={{ color: "rgba(255,255,255,0.7)" }}/> : null}
              </div>
              <div>
                <div className="title">{m.title}</div>
                <div className="sub">
                  {m.sub.map((s, j) => <span key={j}>{j > 0 ? "·" : ""} {s}</span>)}
                </div>
              </div>
              <div style={{ width: 70 }}>
                <div className="mp">
                  <div className="mp-bar c"><i style={{ width: `${Math.min(100, m.c * 1.5)}%` }}/></div>
                  <div className="mp-bar p"><i style={{ width: `${Math.min(100, m.p * 2)}%` }}/></div>
                  <div className="mp-bar f"><i style={{ width: `${Math.min(100, m.f * 2)}%` }}/></div>
                </div>
              </div>
              <span className="v"><span style={{ color: "var(--accent)" }}>{m.c}</span><span className="u">У</span></span>
              <span className="v">{m.p}<span className="u">Б</span></span>
              <span className="v">{m.f}<span className="u">Ж</span></span>
              <span className="v kcal">{m.k}<span className="u"> ккал</span></span>
              <button className="btn icon" style={{ border: "none", background: "transparent" }}><I.More size={14}/></button>
            </div>
          ))}
        </div>

        {/* sticky-ish input */}
        <div className="row gap-12" style={{ marginTop: 18, alignItems: "center" }}>
          <div className="input-bar" style={{ flex: 1, borderColor: panelMode === "autocomplete" ? "var(--ink)" : "var(--hairline-2)" }}>
            <button className="btn icon" style={{ border: "none", background: "transparent" }}><I.Plus size={16}/></button>
            <span className="mono" style={{ color: "var(--ink-4)" }}>{">"}</span>
            <input defaultValue={inputValue} placeholder="bk:whopper · введите еду или используйте префикс bk: / mc:" />
            {panelMode === "autocomplete" && <button className="btn icon" style={{ border: "none", background: "transparent" }}><I.X size={14}/></button>}
            <button className="send-btn"><I.ArrowR size={14}/></button>
          </div>
          <button className="btn"><I.Camera size={13}/> Фото</button>
        </div>
        <div style={{ fontSize: 11, color: "var(--ink-4)", marginTop: 8, marginLeft: 4 }}>
          подсказки: <span className="mono">bk:</span> Burger King · <span className="mono">mc:</span> McDonald's · перетащите фото — Gemini оценит макросы
        </div>
      </div>
    </Shell>
  );
}

// ───── History page ─────
function HistoryPage({ panelMode = "none" }) {
  const sampleMeal = { title: "Лаваш с курицей и овощами", color: "#C2A06A", k: 634, brand: "фото · принято", weight: 324 };
  const rightPanel = panelMode === "selected-meal" ? <SelectedMealPanel meal={sampleMeal}/> : null;
  return (
    <Shell active="История" rightPanel={rightPanel}>
      <div className="gt-page">
        <PageHead crumbs={["история"]} title="История" right={
          <div className="row gap-8">
            <button className="btn"><I.Filter size={13}/> Активные</button>
            <button className="btn"><I.Cal size={13}/> Все даты</button>
          </div>
        }/>

        {/* filters row */}
        <div className="card" style={{ padding: 14, marginBottom: 18 }}>
          <div className="row gap-12" style={{ alignItems: "center" }}>
            <div className="input-bar" style={{ flex: 1, height: 32 }}>
              <I.Search size={14} style={{ color: "var(--ink-4)" }}/>
              <input placeholder="еда, заметка, позиция…"/>
            </div>
            <div className="row gap-8">
              <div className="field" style={{ width: 130 }}>
                <input className="mono" placeholder="дд.мм.гггг" defaultValue="01.04.2026"/>
              </div>
              <span style={{ color: "var(--ink-4)" }}>→</span>
              <div className="field" style={{ width: 130 }}>
                <input className="mono" placeholder="дд.мм.гггг" defaultValue="02.05.2026"/>
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
            <span className="spacer"/>
            <div className="row gap-12" style={{ fontSize: 11, color: "var(--ink-3)" }}>
              <span><b className="mono" style={{ color: "var(--ink)", fontWeight: 500 }}>7</b> приёмов</span>
              <span><b className="mono" style={{ color: "var(--ink)", fontWeight: 500 }}>111 г</b> углеводы</span>
              <span><b className="mono" style={{ color: "var(--ink)", fontWeight: 500 }}>1587</b> ккал</span>
              <span><b className="mono" style={{ color: "var(--ink)", fontWeight: 500 }}>4</b> NS события</span>
              <span>tdee <b className="mono" style={{ color: "var(--ink)", fontWeight: 500 }}>2829</b></span>
              <span>баланс <b className="mono" style={{ color: "var(--good)", fontWeight: 500 }}>−1242</b></span>
            </div>
          </div>

          {/* episode card */}
          <div className="card" style={{ marginTop: 14, padding: 0 }}>
            <div className="row" style={{ padding: "14px 18px", borderBottom: "1px solid var(--hairline)", gap: 18, alignItems: "stretch" }}>
              <div className="mono" style={{ width: 80, fontSize: 11, color: "var(--ink-3)" }}>
                15:43<br/>16:04
              </div>
              <div style={{ flex: 1 }}>
                <div className="row gap-8" style={{ alignItems: "center" }}>
                  <span style={{ fontSize: 14, fontWeight: 500 }}>Пищевой эпизод</span>
                  <span className="tag accent">15:43–16:04</span>
                </div>
                <div style={{ fontSize: 11, color: "var(--ink-3)", marginTop: 4 }}>
                  4 события · <span className="mono">878 ккал</span> · <span className="mono">64.8 г</span> углеводов · 1 запись инсулина
                </div>
                <div className="row gap-12" style={{ marginTop: 10, fontSize: 11, color: "var(--ink-3)" }}>
                  <span>пик глюкозы <b className="mono" style={{ color: "var(--accent)", fontWeight: 500 }}>10.1</b> через <b className="mono" style={{ color: "var(--ink)", fontWeight: 500 }}>12 мин</b></span>
                  <span>инсулин <b className="mono" style={{ color: "var(--ink)", fontWeight: 500 }}>1.6 ЕД</b></span>
                </div>
              </div>
              {/* mini glucose */}
              <div style={{ width: 260 }}>
                <div className="row" style={{ justifyContent: "space-between", fontSize: 10, color: "var(--ink-3)" }}>
                  <span>глюкоза CGM</span>
                  <span className="mono">5.3 → 9.8 ммоль/л</span>
                </div>
                <svg width="260" height="68" style={{ display: "block", marginTop: 4 }}>
                  <line x1="0" x2="260" y1="20" y2="20" stroke="var(--accent-soft)" strokeDasharray="2 3"/>
                  <line x1="0" x2="260" y1="56" y2="56" stroke="var(--accent-soft)" strokeDasharray="2 3"/>
                  <path d="M0,52 L20,50 L40,48 L60,46 L80,42 L100,32 L120,26 L140,20 L160,18 L180,22 L200,26 L220,28 L240,30 L260,28"
                    fill="none" stroke="var(--ink)" strokeWidth="1.4"/>
                  <circle cx="80" cy="42" r="3" fill="var(--accent)"/>
                  <text x="80" y="66" textAnchor="middle" fontFamily="var(--mono)" fontSize="9" fill="var(--ink-4)">15:43</text>
                </svg>
              </div>
            </div>
            {/* inner rows */}
            {[
              { time: "15:43", t: "Лаваш с курицей и овощами", c: "27.1 г", k: "634 ккал" },
              { time: "15:52", t: "Cheetos Пицца", c: "22.2 г", k: "181 ккал" },
              { time: "16:04", t: "Кола Ориджинал", c: "15.5 г", k: "63 ккал" },
              { time: "17:40", t: "Инсулин из Nightscout · только чтение", c: "—", k: "1.6 ЕД", insulin: true },
            ].map((r, i) => (
              <div key={i} className="row" style={{ padding: "10px 18px", borderBottom: i < 3 ? "1px solid var(--hairline)" : "none", alignItems: "center", gap: 14 }}>
                <span className="mono" style={{ fontSize: 11, color: "var(--ink-3)", width: 64 }}>{r.time}</span>
                <span style={{ flex: 1, fontSize: 13, color: r.insulin ? "var(--ink-3)" : "var(--ink)" }}>{r.t}</span>
                {!r.insulin && <span className="tag">принято</span>}
                <span className="mono" style={{ fontSize: 12, width: 70, textAlign: "right" }}>{r.c}</span>
                <span className="mono" style={{ fontSize: 12, width: 80, textAlign: "right", fontWeight: 500 }}>{r.k}</span>
              </div>
            ))}
          </div>

          {/* second episode */}
          <div className="card" style={{ marginTop: 14, padding: "12px 18px" }}>
            <div className="row" style={{ alignItems: "center", gap: 16 }}>
              <div className="mono" style={{ width: 80, fontSize: 11, color: "var(--ink-3)" }}>14:07</div>
              <div style={{ flex: 1 }}>
                <span style={{ fontSize: 13, fontWeight: 500 }}>Приём пищи</span>
                <span className="tag" style={{ marginLeft: 8 }}>2 события</span>
                <div style={{ fontSize: 11, color: "var(--ink-3)", marginTop: 3 }}>309 ккал · 21.7 г углеводов</div>
              </div>
              <svg width="180" height="40">
                <path d="M0,28 L30,26 L60,22 L90,16 L120,10 L150,14 L180,18" fill="none" stroke="var(--ink)" strokeWidth="1.4"/>
                <circle cx="60" cy="22" r="2.4" fill="var(--accent)"/>
              </svg>
              <span className="mono" style={{ fontSize: 12, color: "var(--ink-3)" }}>3.6 → пик 8.9 через 140 мин</span>
            </div>
          </div>

          {/* standalone meal */}
          <div className="card" style={{ marginTop: 14, padding: "10px 18px" }}>
            <div className="row" style={{ alignItems: "center", gap: 14 }}>
              <span className="mono" style={{ fontSize: 11, color: "var(--ink-3)", width: 64 }}>05:30</span>
              <div className="thumb" style={{ width: 36, height: 36, background: "#9C6E3F" }}/>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 13 }}>Халва подсолнечная глазированная</div>
                <div style={{ fontSize: 11, color: "var(--ink-3)", marginTop: 2 }}>восточный гость · принято</div>
              </div>
              <span className="mono" style={{ fontSize: 12, color: "var(--ink-3)" }}>9 У · 2 Б · 7 Ж</span>
              <span className="mono" style={{ fontSize: 12, fontWeight: 500 }}>110 ккал</span>
            </div>
          </div>
        </div>
      </div>
    </Shell>
  );
}

// ───── Database page ─────
function DatabasePage({ panelMode = "none" }) {
  const items = [
    { name: "Протеиновое брауни Shagi.", src: "ROYAL CAKE · LABEL_CALC · НЕ ПРОВЕРЕНО", c: 8, p: 4, f: 11, k: 144, color: "#3F2E22" },
    { name: "Сырок глазированный", src: "LABEL_CALC · НЕ ПРОВЕРЕНО", c: 14, p: 3, f: 10, k: 165, color: "#7C5A36" },
    { name: "Кола Ориджинал", src: "4604441024742 · ЧЕРНОГОЛОВКА · НЕ ПРОВЕРЕНО", c: 16, p: 0, f: 0, k: 63, color: "#7B2A2A" },
    { name: "Халва подсолнечная глазированная", src: "ВОСТОЧНЫЙ ГОСТЬ · LABEL_CALC · НЕ ПРОВЕРЕНО", c: 9, p: 2, f: 7, k: 110, color: "#9C6E3F" },
    { name: "Бисквит-сэндвич", src: "LABEL_CALC · НЕ ПРОВЕРЕНО", c: 19, p: 1, f: 5, k: 123, color: "#D8B98A" },
    { name: "Cheetos Пицца", src: "4690631527407 · CHEETOS · НЕ ПРОВЕРЕНО", c: 30, p: 4, f: 12, k: 245, color: "#C95A2E" },
    { name: 'Сырок глазированный "Эфер"', src: "ЭФЕР · LABEL_CALC · НЕ ПРОВЕРЕНО", c: 13, p: 4, f: 7, k: 128, color: "#B8AC7E" },
    { name: "Воппер", src: "BKWHOPPER · BURGER KING OFFICIAL PDF · НЕ ПРОВЕРЕНО", c: 53, p: 27, f: 44, k: 720, color: "#7B4A2A" },
  ];
  const selectedIdx = panelMode === "selected-db" ? 2 : -1;
  const rightPanel = panelMode === "selected-db" ? <DbItemPanel item={items[2]}/> : null;
  return (
    <Shell active="База" rightPanel={rightPanel}>
      <div className="gt-page">
        <PageHead crumbs={["продукты", "шаблоны", "рестораны", "импорт"]} title="База" right={
          <div className="row gap-8">
            <button className="btn"><I.Pkg size={13}/> Импорт</button>
            <button className="btn dark"><I.Plus size={13}/> Добавить вручную</button>
          </div>
        }/>

        <div className="card" style={{ padding: 14, marginBottom: 14 }}>
          <div className="row gap-12" style={{ alignItems: "center" }}>
            <div className="input-bar" style={{ flex: 1, height: 32 }}>
              <I.Search size={14} style={{ color: "var(--ink-4)" }}/>
              <input placeholder="Поиск по базе…"/>
            </div>
            <div className="field" style={{ width: 180 }}>
              <input defaultValue="Все источники"/>
            </div>
            <div className="field" style={{ width: 140 }}>
              <input defaultValue="Все типы"/>
            </div>
          </div>
        </div>

        <div className="row gap-8" style={{ marginBottom: 12 }}>
          {["Частые", "Рестораны", "Продукты", "Шаблоны", "Требуют проверки"].map((t, i) => (
            <button key={i} className={`btn${i === 0 ? " dark" : ""}`}>{t}{i === 4 && <span className="tag warn" style={{ marginLeft: 4 }}>12</span>}</button>
          ))}
        </div>

        <div className="card">
          {items.map((it, i) => (
            <div key={i} className="row" style={{
              alignItems: "center", padding: "12px 18px",
              borderBottom: i < items.length - 1 ? "1px solid var(--hairline)" : "none",
              gap: 14,
              background: selectedIdx === i ? "var(--surface-2)" : "transparent",
              boxShadow: selectedIdx === i ? "inset 2px 0 0 var(--ink)" : "none",
            }}>
              <div className="thumb" style={{ background: it.color }}><I.Photo size={14} style={{ color: "rgba(255,255,255,0.7)" }}/></div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13 }}>{it.name}</div>
                <div className="mono" style={{ fontSize: 10, color: "var(--ink-4)", marginTop: 3, letterSpacing: 0.04 }}>{it.src}</div>
              </div>
              <span className="tag warn" style={{ fontSize: 9 }}>не проверено</span>
              <div style={{ width: 64 }}>
                <div className="mp">
                  <div className="mp-bar c"><i style={{ width: `${Math.min(100, it.c * 1.4)}%` }}/></div>
                  <div className="mp-bar p"><i style={{ width: `${Math.min(100, it.p * 2.5)}%` }}/></div>
                  <div className="mp-bar f"><i style={{ width: `${Math.min(100, it.f * 2)}%` }}/></div>
                </div>
              </div>
              <span className="mono" style={{ fontSize: 12, width: 36, textAlign: "right", color: "var(--accent)" }}>{it.c}<span style={{ color: "var(--ink-4)" }}>у</span></span>
              <span className="mono" style={{ fontSize: 12, width: 36, textAlign: "right" }}>{it.p}<span style={{ color: "var(--ink-4)" }}>б</span></span>
              <span className="mono" style={{ fontSize: 12, width: 36, textAlign: "right" }}>{it.f}<span style={{ color: "var(--ink-4)" }}>ж</span></span>
              <span className="mono" style={{ fontSize: 13, width: 70, textAlign: "right", fontWeight: 500 }}>{it.k} ккал</span>
              <button className="btn icon" style={{ border: "none", background: "transparent" }}><I.More size={14}/></button>
            </div>
          ))}
        </div>
      </div>
    </Shell>
  );
}

// ───── Settings page (Nightscout) ─────
function SettingsPage() {
  return (
    <Shell active="Настройки">
      <div className="gt-page">
        <PageHead crumbs={["настройки", "интеграции"]} title="Интеграция: Nightscout"/>
        <p style={{ maxWidth: 640, color: "var(--ink-3)", marginTop: -10, marginBottom: 28 }}>
          Nightscout остаётся дополнительной интеграцией. glucotracker может читать контекст глюкозы и
          показывать записи инсулина, но не считает дозы и не отправляет инсулин.
        </p>

        <div className="row gap-32" style={{ alignItems: "flex-start" }}>
          {/* main column */}
          <div style={{ flex: 1 }}>
            <h3 style={{ fontFamily: "var(--serif)", fontWeight: 500, fontSize: 18, margin: "0 0 14px" }}>Подключение</h3>
            <div className="card card-pad">
              <div className="row gap-16">
                <div className="field" style={{ flex: 2 }}>
                  <label>nightscout url</label>
                  <input defaultValue="http://megusto.duckdns.org:1337"/>
                </div>
                <div className="field" style={{ flex: 1 }}>
                  <label>api secret</label>
                  <input type="password" defaultValue="••••••••••••"/>
                </div>
              </div>
              <div style={{ fontSize: 11, color: "var(--ink-4)", marginTop: 8 }}>
                Секрет хранится только на backend и не возвращается на frontend.
              </div>
              <div className="row" style={{ alignItems: "center", marginTop: 18, padding: "12px 14px", background: "var(--surface-2)", borderRadius: "var(--radius-lg)", border: "1px solid var(--hairline)", gap: 14 }}>
                <div>
                  <div className="lbl">статус</div>
                  <div className="row gap-6" style={{ alignItems: "center", marginTop: 4 }}>
                    <span className="dot-marker" style={{ background: "var(--good)" }}/>
                    <span style={{ fontSize: 13, fontWeight: 500 }}>Подключено</span>
                    <span style={{ fontSize: 11, color: "var(--ink-3)" }}>· последний пинг 12 сек назад</span>
                  </div>
                </div>
                <span className="spacer"/>
                <button className="btn"><I.Wifi size={13}/> Проверить подключение</button>
              </div>
            </div>

            <h3 style={{ fontFamily: "var(--serif)", fontWeight: 500, fontSize: 18, margin: "28px 0 14px" }}>Синхронизация</h3>
            <div className="card card-pad">
              <div className="checkbox" style={{ borderTop: "none" }}>
                <div>
                  <div className="l">Синхронизировать глюкозу</div>
                  <div className="s">Если включено, глюкоза из Nightscout загружается и хранится локально.</div>
                </div>
                <div className="checkbox-box"><I.Check/></div>
              </div>
              <div className="checkbox">
                <div>
                  <div className="l">Показывать записи инсулина из Nightscout</div>
                  <div className="s">Только контекст из Nightscout. glucotracker никогда не отправляет инсулин и не предлагает дозу.</div>
                </div>
                <div className="checkbox-box"><I.Check/></div>
              </div>
              <div className="checkbox">
                <div>
                  <div className="l">Применять нормализацию к Nightscout-данным</div>
                  <div className="s">Только на отображение. Raw CGM сохраняется без изменений.</div>
                </div>
                <div className="checkbox-box off"><I.Check/></div>
              </div>
            </div>

            <h3 style={{ fontFamily: "var(--serif)", fontWeight: 500, fontSize: 18, margin: "28px 0 14px" }}>Действия</h3>
            <div className="row gap-8">
              <button className="btn dark"><I.Send size={13}/> Отправить сегодняшние записи</button>
              <button className="btn"><I.Refresh size={13}/> Переимпорт за 7 дней</button>
              <button className="btn"><I.Trash size={13}/> Очистить кэш Nightscout</button>
            </div>
          </div>

          {/* right column */}
          <div style={{ width: 340, flex: "0 0 340px" }}>
            <div className="card card-pad">
              <div className="lbl">локальный backend</div>
              <h3 style={{ fontFamily: "var(--serif)", fontWeight: 500, fontSize: 16, margin: "4px 0 14px" }}>FastAPI</h3>
              <div className="field" style={{ marginBottom: 12 }}>
                <label>адрес</label>
                <input defaultValue="http://127.0.0.1:8000"/>
              </div>
              <div className="field" style={{ marginBottom: 14 }}>
                <label>bearer-token</label>
                <input type="password" defaultValue="•••••"/>
              </div>
              <div className="col gap-8">
                <button className="btn"><I.Wifi size={13}/> Проверить backend</button>
                <button className="btn"><I.Refresh size={13}/> Пересчитать итоги</button>
                <button className="btn" style={{ color: "var(--warn)", borderColor: "var(--warn-soft)" }}><I.Trash size={13}/> Очистить UI</button>
              </div>
            </div>

            <div className="card card-pad" style={{ marginTop: 16 }}>
              <div className="lbl">оформление</div>
              <h3 style={{ fontFamily: "var(--serif)", fontWeight: 500, fontSize: 16, margin: "4px 0 14px" }}>Тема</h3>
              <div className="seg" style={{ width: "100%", height: 36 }}>
                <button className="on" style={{ flex: 1 }}><I.Sun size={13} style={{ marginRight: 4 }}/> Светлая</button>
                <button style={{ flex: 1 }}><I.Moon size={13} style={{ marginRight: 4 }}/> Тёмная</button>
                <button style={{ flex: 1 }}>Система</button>
              </div>
            </div>

            <div className="card card-pad" style={{ marginTop: 16 }}>
              <div className="lbl">профиль для расчёта tdee</div>
              <h3 style={{ fontFamily: "var(--serif)", fontWeight: 500, fontSize: 16, margin: "4px 0 4px" }}>BMR — Mifflin-St Jeor</h3>
              <div style={{ fontSize: 11, color: "var(--ink-3)", marginBottom: 14 }}>
                Данные активности с часов скорректируют TDEE автоматически.
              </div>
              <div className="row gap-8">
                <div className="field" style={{ flex: 1 }}><label>вес, кг</label><input defaultValue="82"/></div>
                <div className="field" style={{ flex: 1 }}><label>рост, см</label><input defaultValue="180"/></div>
              </div>
              <div className="row gap-8" style={{ marginTop: 10 }}>
                <div className="field" style={{ flex: 1 }}><label>возраст</label><input defaultValue="25"/></div>
                <div className="field" style={{ flex: 1 }}><label>пол</label><input defaultValue="мужской"/></div>
              </div>
              <div className="row" style={{ alignItems: "baseline", justifyContent: "space-between", marginTop: 14, padding: "10px 0", borderTop: "1px solid var(--hairline)" }}>
                <span className="lbl">расчёт TDEE</span>
                <span className="mono" style={{ fontSize: 16, fontWeight: 500 }}>2829 ккал</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Shell>
  );
}

window.JournalPage = JournalPage;
window.HistoryPage = HistoryPage;
window.DatabasePage = DatabasePage;
window.SettingsPage = SettingsPage;
