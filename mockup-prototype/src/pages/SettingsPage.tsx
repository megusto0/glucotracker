import { useState } from 'react'
import { I } from '../components/Icons'
import PageHead from '../components/PageHead'
import { useTheme } from '../theme'

export default function SettingsPage() {
  const [syncGlucose, setSyncGlucose] = useState(true)
  const [showInsulin, setShowInsulin] = useState(true)
  const [applyNorm, setApplyNorm] = useState(false)
  const { mode: theme, setMode: setTheme } = useTheme()

  return (
    <div className="gt-page">
      <PageHead crumbs={["настройки", "интеграции"]} title="Интеграция: Nightscout" />
      <p style={{ maxWidth: 640, color: "var(--ink-3)", marginTop: -10, marginBottom: 28 }}>
        Nightscout остаётся дополнительной интеграцией. glucotracker может читать контекст глюкозы и
        показывать записи инсулина, но не считает дозы и не отправляет инсулин.
      </p>

      <div className="row gap-32" style={{ alignItems: "flex-start" }}>
        <div style={{ flex: 1 }}>
          <h3 style={{ fontFamily: "var(--serif)", fontWeight: 500, fontSize: 18, margin: "0 0 14px" }}>Подключение</h3>
          <div className="card card-pad">
            <div className="row gap-16">
              <div className="field" style={{ flex: 2 }}>
                <label>nightscout url</label>
                <input defaultValue="http://megusto.duckdns.org:1337" />
              </div>
              <div className="field" style={{ flex: 1 }}>
                <label>api secret</label>
                <input type="password" defaultValue="••••••••••••" />
              </div>
            </div>
            <div style={{ fontSize: 11, color: "var(--ink-4)", marginTop: 8 }}>
              Секрет хранится только на backend и не возвращается на frontend.
            </div>
            <div className="row" style={{ alignItems: "center", marginTop: 18, padding: "12px 14px", background: "var(--surface-2)", borderRadius: "var(--radius-lg)", border: "1px solid var(--hairline)", gap: 14 }}>
              <div>
                <div className="lbl">статус</div>
                <div className="row gap-6" style={{ alignItems: "center", marginTop: 4 }}>
                  <span className="dot-marker" style={{ background: "var(--good)" }} />
                  <span style={{ fontSize: 13, fontWeight: 500 }}>Подключено</span>
                  <span style={{ fontSize: 11, color: "var(--ink-3)" }}>· последний пинг 12 сек назад</span>
                </div>
              </div>
              <span className="spacer" />
              <button className="btn"><I.Wifi size={13} /> Проверить подключение</button>
            </div>
          </div>

          <h3 style={{ fontFamily: "var(--serif)", fontWeight: 500, fontSize: 18, margin: "28px 0 14px" }}>Синхронизация</h3>
          <div className="card card-pad">
            <div className="checkbox" style={{ borderTop: "none" }}>
              <div>
                <div className="l">Синхронизировать глюкозу</div>
                <div className="s">Если включено, глюкоза из Nightscout загружается и хранится локально.</div>
              </div>
              <div className={`checkbox-box${syncGlucose ? '' : ' off'}`} onClick={() => setSyncGlucose(!syncGlucose)}><I.Check /></div>
            </div>
            <div className="checkbox">
              <div>
                <div className="l">Показывать записи инсулина из Nightscout</div>
                <div className="s">Только контекст из Nightscout. glucotracker никогда не отправляет инсулин и не предлагает дозу.</div>
              </div>
              <div className={`checkbox-box${showInsulin ? '' : ' off'}`} onClick={() => setShowInsulin(!showInsulin)}><I.Check /></div>
            </div>
            <div className="checkbox">
              <div>
                <div className="l">Применять нормализацию к Nightscout-данным</div>
                <div className="s">Только на отображение. Raw CGM сохраняется без изменений.</div>
              </div>
              <div className={`checkbox-box${applyNorm ? '' : ' off'}`} onClick={() => setApplyNorm(!applyNorm)}><I.Check /></div>
            </div>
          </div>

          <h3 style={{ fontFamily: "var(--serif)", fontWeight: 500, fontSize: 18, margin: "28px 0 14px" }}>Действия</h3>
          <div className="row gap-8">
            <button className="btn dark"><I.Send size={13} /> Отправить сегодняшние записи</button>
            <button className="btn"><I.Refresh size={13} /> Переимпорт за 7 дней</button>
            <button className="btn"><I.Trash size={13} /> Очистить кэш Nightscout</button>
          </div>
        </div>

        <div style={{ width: 340, flex: "0 0 340px" }}>
          <div className="card card-pad">
            <div className="lbl">локальный backend</div>
            <h3 style={{ fontFamily: "var(--serif)", fontWeight: 500, fontSize: 16, margin: "4px 0 14px" }}>FastAPI</h3>
            <div className="field" style={{ marginBottom: 12 }}>
              <label>адрес</label>
              <input defaultValue="http://127.0.0.1:8000" />
            </div>
            <div className="field" style={{ marginBottom: 14 }}>
              <label>bearer-token</label>
              <input type="password" defaultValue="•••••" />
            </div>
            <div className="col gap-8">
              <button className="btn"><I.Wifi size={13} /> Проверить backend</button>
              <button className="btn"><I.Refresh size={13} /> Пересчитать итоги</button>
              <button className="btn" style={{ color: "var(--warn)", borderColor: "var(--warn-soft)" }}><I.Trash size={13} /> Очистить UI</button>
            </div>
          </div>

          <div className="card card-pad" style={{ marginTop: 16 }}>
            <div className="lbl">оформление</div>
            <h3 style={{ fontFamily: "var(--serif)", fontWeight: 500, fontSize: 16, margin: "4px 0 14px" }}>Тема</h3>
            <div className="seg" style={{ width: "100%", height: 36 }}>
              <button className={theme === "Светлая" ? "on" : ""} style={{ flex: 1 }} onClick={() => setTheme("Светлая")}><I.Sun size={13} style={{ marginRight: 4 }} /> Светлая</button>
              <button className={theme === "Тёмная" ? "on" : ""} style={{ flex: 1 }} onClick={() => setTheme("Тёмная")}><I.Moon size={13} style={{ marginRight: 4 }} /> Тёмная</button>
              <button className={theme === "Система" ? "on" : ""} style={{ flex: 1 }} onClick={() => setTheme("Система")}>Система</button>
            </div>
          </div>

          <div className="card card-pad" style={{ marginTop: 16 }}>
            <div className="lbl">профиль для расчёта tdee</div>
            <h3 style={{ fontFamily: "var(--serif)", fontWeight: 500, fontSize: 16, margin: "4px 0 4px" }}>BMR — Mifflin-St Jeor</h3>
            <div style={{ fontSize: 11, color: "var(--ink-3)", marginBottom: 14 }}>
              Данные активности с часов скорректируют TDEE автоматически.
            </div>
            <div className="row gap-8">
              <div className="field" style={{ flex: 1 }}><label>вес, кг</label><input defaultValue="82" /></div>
              <div className="field" style={{ flex: 1 }}><label>рост, см</label><input defaultValue="180" /></div>
            </div>
            <div className="row gap-8" style={{ marginTop: 10 }}>
              <div className="field" style={{ flex: 1 }}><label>возраст</label><input defaultValue="25" /></div>
              <div className="field" style={{ flex: 1 }}><label>пол</label><input defaultValue="мужской" /></div>
            </div>
            <div className="row" style={{ alignItems: "baseline", justifyContent: "space-between", marginTop: 14, padding: "10px 0", borderTop: "1px solid var(--hairline)" }}>
              <span className="lbl">расчёт TDEE</span>
              <span className="mono" style={{ fontSize: 16, fontWeight: 500 }}>2829 ккал</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
