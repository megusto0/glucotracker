// glucotacker mobile screens — all eight screens + extras
// Width: 380. Based on desktop tokens. Serif headers, mono numbers, hairlines.

// ───────────────────────────────────────────────────────────
// Shared primitives
// ───────────────────────────────────────────────────────────

const PHONE_W = 380;
const PHONE_H = 800;

// Android status bar — left-aligned time, right-side icons
function StatusBar({ time = '8:42' }) {
  return (
    <div style={{
      height: 28, padding: '6px 16px 4px', display: 'flex',
      alignItems: 'center', justifyContent: 'space-between',
      fontFamily: 'var(--sans)', fontWeight: 600, fontSize: 13,
      color: 'var(--ink)', letterSpacing: 0.1,
      flexShrink: 0,
    }}>
      <span style={{ fontVariantNumeric: 'tabular-nums' }}>{time}</span>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <svg width="16" height="10" viewBox="0 0 16 10">
          <rect x="0" y="6.5" width="2.6" height="3.5" rx="0.5" fill="currentColor" />
          <rect x="4" y="4.5" width="2.6" height="5.5" rx="0.5" fill="currentColor" />
          <rect x="8" y="2.5" width="2.6" height="7.5" rx="0.5" fill="currentColor" />
          <rect x="12" y="0" width="2.6" height="10" rx="0.5" fill="currentColor" />
        </svg>
        <svg width="14" height="10" viewBox="0 0 14 10">
          <path d="M7 2.5C8.9 2.5 10.6 3.2 11.8 4.4L12.7 3.5C11.2 2 9.2 1 7 1C4.8 1 2.8 2 1.3 3.5L2.2 4.4C3.4 3.2 5.1 2.5 7 2.5Z" fill="currentColor" />
          <path d="M7 5.5C8.1 5.5 9.1 5.9 9.8 6.6L10.7 5.7C9.7 4.7 8.4 4.1 7 4.1C5.6 4.1 4.3 4.7 3.3 5.7L4.2 6.6C4.9 5.9 5.9 5.5 7 5.5Z" fill="currentColor" />
          <circle cx="7" cy="8.5" r="1.3" fill="currentColor" />
        </svg>
        <svg width="22" height="11" viewBox="0 0 22 11">
          <rect x="0.5" y="0.5" width="19" height="10" rx="2.5" stroke="currentColor" strokeOpacity="0.4" fill="none" />
          <rect x="2" y="2" width="16" height="7" rx="1.5" fill="currentColor" />
          <path d="M20.5 3.5V7.5C21.1 7.3 21.5 6.7 21.5 6C21.5 5.3 21.1 4.7 20.5 4.5Z" fill="currentColor" fillOpacity="0.5" />
        </svg>
      </div>
    </div>
  );
}

// Android gesture nav pill
function HomeIndicator() {
  return (
    <div style={{
      height: 22, display: 'flex', alignItems: 'flex-end',
      justifyContent: 'center', paddingBottom: 6, flexShrink: 0,
      background: 'var(--surface)',
    }}>
      <div style={{ width: 108, height: 4, borderRadius: 2, background: 'var(--ink)', opacity: 0.7 }} />
    </div>
  );
}

// Phone shell — off-white canvas, the thing that gets put inside DCArtboard
function Phone({ children, dark = false, time = '8:42', showHome = true }) {
  return (
    <div style={{
      width: PHONE_W, height: PHONE_H,
      background: dark ? '#1c1b18' : 'var(--bg)',
      color: dark ? '#f6f4ef' : 'var(--ink)',
      fontFamily: 'var(--sans)',
      display: 'flex', flexDirection: 'column',
      position: 'relative', overflow: 'hidden',
    }}>
      <StatusBar time={time} />
      <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', position: 'relative' }}>
        {children}
      </div>
      {showHome && <HomeIndicator />}
    </div>
  );
}

// ───────────────────────────────────────────────────────────
// Glucose mini-widget (pulled from desktop bottom-left card)
// ───────────────────────────────────────────────────────────
function GlucoseSparkline({ width = 60, height = 22, color = 'var(--ink)', points }) {
  const pts = points || [
    7.2, 7.6, 8.1, 8.6, 9.1, 9.4, 9.6, 9.7, 9.9, 10.2, 10.0, 9.9,
  ];
  const min = 6, max = 12;
  const step = width / (pts.length - 1);
  const path = pts.map((v, i) => {
    const x = i * step;
    const y = height - ((v - min) / (max - min)) * height;
    return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
      <path d={path} stroke={color} strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

// ───────────────────────────────────────────────────────────
// Bottom tab bar — 5 tabs + center FAB
// ───────────────────────────────────────────────────────────
function TabBar({ active = 'today' }) {
  const Tab = ({ id, label, icon }) => {
    const isActive = active === id;
    return (
      <div style={{
        flex: 1, display: 'flex', flexDirection: 'column',
        alignItems: 'center', gap: 3, padding: '8px 0 6px',
        color: isActive ? 'var(--ink)' : 'var(--muted)',
      }}>
        <div style={{ width: 22, height: 22, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>{icon}</div>
        <span style={{ fontSize: 10, fontWeight: isActive ? 600 : 500, letterSpacing: 0.2 }}>{label}</span>
      </div>
    );
  };
  return (
    <div style={{
      height: 64, background: 'var(--surface)',
      borderTop: '0.5px solid var(--hairline)',
      display: 'flex', alignItems: 'flex-start',
      position: 'relative', flexShrink: 0,
      paddingBottom: 4,
    }}>
      <Tab id="today" label="СЕГОДНЯ" icon={
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
          <rect x="2.5" y="3.5" width="15" height="14" rx="1.5" stroke="currentColor" strokeWidth="1.4" />
          <path d="M2.5 7.5h15M6.5 2v3M13.5 2v3" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
        </svg>
      } />
      <Tab id="glucose" label="ГЛЮКОЗА" icon={
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
          <path d="M2 12 L5 12 L7 7 L9 15 L11 9 L13 13 L15 11 L18 11" stroke="currentColor" strokeWidth="1.4" fill="none" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      } />
      {/* FAB spacer */}
      <div style={{ flex: 1 }} />
      <Tab id="history" label="ИСТОРИЯ" icon={
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
          <circle cx="10" cy="10" r="7" stroke="currentColor" strokeWidth="1.4" />
          <path d="M10 6v4l2.5 2" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
        </svg>
      } />
      <Tab id="more" label="ЕЩЁ" icon={
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
          <circle cx="4.5" cy="10" r="1.4" fill="currentColor" />
          <circle cx="10" cy="10" r="1.4" fill="currentColor" />
          <circle cx="15.5" cy="10" r="1.4" fill="currentColor" />
        </svg>
      } />
      {/* Material FAB (capture) — squircle, elevated */}
      <div style={{
        position: 'absolute', left: '50%', top: -22,
        transform: 'translateX(-50%)',
        width: 56, height: 56, borderRadius: 16,
        background: 'var(--ink)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        boxShadow: '0 6px 16px rgba(37,36,31,0.32), 0 2px 4px rgba(37,36,31,0.2)',
      }}>
        <svg width="22" height="22" viewBox="0 0 22 22" fill="none">
          <path d="M11 4v14M4 11h14" stroke="#f6f4ef" strokeWidth="2" strokeLinecap="round" />
        </svg>
      </div>
    </div>
  );
}

// ───────────────────────────────────────────────────────────
// Mini header — used by Сегодня / История / etc
// ───────────────────────────────────────────────────────────
function ScreenHeader({ kicker, date, showNav = true, syncStatus }) {
  return (
    <div style={{ padding: '12px 18px 12px', flexShrink: 0 }}>
      {/* Top row: kicker + sync status (so they can't collide with the date) */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', minHeight: 14 }}>
        {kicker ? (
          <div style={{
            fontSize: 10, fontWeight: 600, letterSpacing: 1.2,
            color: 'var(--muted)', textTransform: 'uppercase',
          }}>{kicker}</div>
        ) : <span />}
        {syncStatus && (
          <div style={{
            fontSize: 10.5, color: 'var(--muted)', letterSpacing: 0.2,
            display: 'flex', alignItems: 'center', gap: 5,
          }}>
            <span style={{ display: 'inline-block', width: 6, height: 6, borderRadius: 3, background: 'var(--warn)' }} />
            {syncStatus}
          </div>
        )}
      </div>
      {/* Date row — full-width serif, nav buttons trail compactly */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 4, gap: 10 }}>
        <div style={{
          fontFamily: 'var(--serif)', fontSize: 26, fontWeight: 400,
          color: 'var(--ink)', lineHeight: 1.1, letterSpacing: -0.3,
          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
        }}>{date}</div>
        {showNav && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 4, flexShrink: 0 }}>
            <button style={iconBtn}>
              <svg width="14" height="14" viewBox="0 0 14 14"><path d="M9 2L4 7l5 5" stroke="currentColor" strokeWidth="1.6" fill="none" strokeLinecap="round" strokeLinejoin="round"/></svg>
            </button>
            <button style={iconBtn}>
              <svg width="14" height="14" viewBox="0 0 14 14"><path d="M5 2l5 5-5 5" stroke="currentColor" strokeWidth="1.6" fill="none" strokeLinecap="round" strokeLinejoin="round"/></svg>
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

const iconBtn = {
  width: 28, height: 28, borderRadius: 6,
  border: '0.5px solid var(--hairline-2)', background: 'var(--surface)',
  color: 'var(--ink-2)', display: 'flex', alignItems: 'center',
  justifyContent: 'center', padding: 0, cursor: 'pointer',
  fontFamily: 'var(--sans)', fontWeight: 500,
};

// ───────────────────────────────────────────────────────────
// SCREEN 1 · Сегодня (главный)
// ───────────────────────────────────────────────────────────
function ScreenToday() {
  return (
    <Phone>
      <ScreenHeader kicker="ВТОРНИК" date="5 мая 2026" syncStatus="NS · 4 несинхр." />

      {/* KPI 2×2 grid — brief allows it for narrow screens */}
      <div style={{
        display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8,
        padding: '0 18px 14px', flexShrink: 0,
      }}>
        <Kpi kicker="ККАЛ" value="1536" unit="ккал" goal="цель 2200 · 70%" pct={70} color="var(--good)" />
        <Kpi kicker="БЕЛКИ" value="44" unit="г" goal="цель 120 · 37%" pct={37} color="var(--bad)" />
        <Kpi kicker="УГЛЕВОДЫ" value="150" unit="г" goal="цель 225 · 66%" pct={66} color="var(--accent)" />
        <Kpi kicker="ОСТАЛОСЬ" value="664" unit="ккал" goal="30% от цели" pct={30} color="var(--warn)" />
      </div>

      {/* Meal list */}
      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '0 14px 14px' }}>
        <div style={{
          background: 'var(--surface)',
          border: '0.5px solid var(--hairline)',
          borderRadius: 10,
          overflow: 'hidden',
        }}>
          <MealRow time="20:08" name="Бисквит-сэндвич ×2" meta="смешано · принято · 2 шт по 30 г" carbs="37.2" kcal="246" b="2.7" f="9.6" c="37.2" thumb="cake" />
          <MealRow time="13:13" name="Сырные Медальоны (9 Шт) + Сметана и Лук" meta="шаблон · принято" carbs="34" kcal="340" b="15" f="16" c="34" thumb="empty" />
          <MealRow time="13:13" name="Воппер Ролл" meta="шаблон · принято" carbs="34" kcal="540" b="21" f="36" c="34" thumb="empty" timeMuted />
          <MealRow time="07:54" name="Кусочек торта" meta="вручную · принято · 100 г" carbs="44.4" kcal="410" b="5.1" f="23.9" c="44.4" thumb="cake2" last />
        </div>

        {/* Mini glucose widget (desktop bottom-left card → here, anchored below list) */}
        <div style={{
          marginTop: 14, background: 'var(--surface)',
          border: '0.5px solid var(--hairline)', borderRadius: 10,
          padding: '12px 14px',
          display: 'flex', alignItems: 'center', gap: 14,
        }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 9, letterSpacing: 1, color: 'var(--muted)', fontWeight: 600 }}>СЕЙЧАС · 2 МИН НАЗАД</div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, marginTop: 4 }}>
              <span style={{ fontFamily: 'var(--mono)', fontSize: 26, fontWeight: 500, letterSpacing: -0.5 }}>9,9</span>
              <span style={{ fontSize: 10, color: 'var(--muted)' }}>ммоль/л</span>
              <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--warn)', marginLeft: 4 }}>↓ −0,6</span>
            </div>
            <div style={{ fontSize: 10, color: 'var(--muted)', marginTop: 2 }}>последние 60 мин</div>
          </div>
          <GlucoseSparkline width={70} height={28} color="var(--ink-2)" />
        </div>
      </div>

      <TabBar active="today" />
    </Phone>
  );
}

function Kpi({ kicker, value, unit, goal, pct, color }) {
  return (
    <div style={{
      background: 'var(--surface)',
      border: '0.5px solid var(--hairline)',
      borderRadius: 10, padding: '10px 12px',
    }}>
      <div style={{ fontSize: 9, fontWeight: 600, letterSpacing: 1.2, color: 'var(--muted)' }}>{kicker}</div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 4, marginTop: 4 }}>
        <span style={{
          fontFamily: 'var(--mono)', fontSize: 22, fontWeight: 500,
          letterSpacing: -0.5, color: 'var(--ink)',
        }}>{value}</span>
        <span style={{ fontSize: 10, color: 'var(--muted)' }}>{unit}</span>
      </div>
      {/* Progress bar */}
      <div style={{
        marginTop: 8, height: 2, background: 'var(--hairline)', borderRadius: 1,
        position: 'relative', overflow: 'hidden',
      }}>
        <div style={{ position: 'absolute', inset: 0, width: `${pct}%`, background: color }} />
      </div>
      <div style={{ fontSize: 9.5, color: 'var(--muted)', marginTop: 6, letterSpacing: 0.2 }}>{goal}</div>
    </div>
  );
}

function MealRow({ time, name, meta, carbs, kcal, b, f, c, thumb, last, timeMuted }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'flex-start', gap: 10,
      padding: '12px 14px',
      borderBottom: last ? 'none' : '0.5px solid var(--hairline)',
    }}>
      <span style={{
        fontFamily: 'var(--mono)', fontSize: 10.5,
        color: timeMuted ? 'var(--muted)' : 'var(--ink-2)',
        opacity: timeMuted ? 0.5 : 1,
        width: 36, flexShrink: 0, paddingTop: 2,
      }}>{time}</span>
      <Thumb kind={thumb} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--ink)', lineHeight: 1.25 }}>{name}</div>
        <div style={{ fontSize: 10.5, color: 'var(--muted)', marginTop: 3, letterSpacing: 0.1 }}>{meta}</div>
        <div style={{ fontFamily: 'var(--mono)', fontSize: 9.5, color: 'var(--muted)', marginTop: 4, letterSpacing: 0.2 }}>
          Б <span style={{ color: 'var(--ink-2)' }}>{b}</span>{' '}
          F <span style={{ color: 'var(--ink-2)' }}>{f}</span>{' '}
          C <span style={{ color: 'var(--ink-2)' }}>{c}</span>
        </div>
      </div>
      <div style={{ textAlign: 'right', flexShrink: 0 }}>
        <div style={{ fontFamily: 'var(--mono)', fontSize: 11.5, color: 'var(--ink)' }}>
          <span style={{ fontWeight: 500 }}>{carbs}</span><span style={{ color: 'var(--muted)' }}> г угл</span>
        </div>
        <div style={{ fontFamily: 'var(--mono)', fontSize: 11.5, marginTop: 1 }}>
          <span style={{ fontWeight: 500 }}>{kcal}</span><span style={{ color: 'var(--muted)' }}> ккал</span>
        </div>
        <div style={{
          marginTop: 5, height: 2, width: 64, marginLeft: 'auto',
          background: 'var(--accent)', opacity: 0.55, borderRadius: 1,
        }} />
      </div>
    </div>
  );
}

// Tiny food thumb — placeholder swatches
function Thumb({ kind }) {
  const sz = 32;
  const common = {
    width: sz, height: sz, borderRadius: 5, flexShrink: 0,
    border: '0.5px solid var(--hairline-2)',
    overflow: 'hidden', position: 'relative',
  };
  if (kind === 'empty') {
    return (
      <div style={{ ...common, background: 'var(--bg)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
          <rect x="1.5" y="2.5" width="11" height="9" rx="1.2" stroke="var(--muted)" strokeWidth="0.8"/>
          <circle cx="5" cy="5.5" r="0.9" fill="var(--muted)"/>
          <path d="M2.5 9.5l2.5-2 2 1.5 2.5-2.5 2.5 2.5" stroke="var(--muted)" strokeWidth="0.8" fill="none"/>
        </svg>
      </div>
    );
  }
  if (kind === 'cake') {
    return (
      <div style={{ ...common, background: 'linear-gradient(160deg,#7a4a35 0%, #5e3525 60%, #3d2218 100%)' }}>
        <div style={{ position: 'absolute', left: 4, right: 4, top: 6, height: 4, background: 'rgba(245,225,180,0.4)' }} />
        <div style={{ position: 'absolute', left: 4, right: 4, top: 14, height: 4, background: 'rgba(245,225,180,0.3)' }} />
      </div>
    );
  }
  if (kind === 'cake2') {
    return (
      <div style={{ ...common, background: 'linear-gradient(160deg,#c9a884 0%, #9a7a5a 50%, #6a4f3a 100%)' }}>
        <div style={{ position: 'absolute', left: 5, top: 4, width: 4, height: 4, borderRadius: 2, background: '#5a2e2a' }} />
        <div style={{ position: 'absolute', left: 14, top: 7, width: 4, height: 4, borderRadius: 2, background: '#4a2820' }} />
      </div>
    );
  }
  if (kind === 'salad') {
    return <div style={{ ...common, background: 'linear-gradient(160deg,#8aa066 0%, #5e6f3a 100%)' }} />;
  }
  if (kind === 'bun') {
    return <div style={{ ...common, background: 'linear-gradient(160deg,#d2a87a 0%, #8f6a48 100%)' }} />;
  }
  return <div style={common} />;
}

// ───────────────────────────────────────────────────────────
// SCREEN 2 · Захват — bottom sheet (over Today, dimmed)
// ───────────────────────────────────────────────────────────
function ScreenCaptureSheet() {
  return (
    <Phone>
      {/* Dimmed background hint */}
      <div style={{ position: 'absolute', inset: 44, background: 'rgba(20,18,12,0.32)', zIndex: 1 }} />
      <ScreenHeader kicker="ВТОРНИК" date="5 мая 2026" syncStatus="NS · 4 несинхр." />
      <div style={{ flex: 1, opacity: 0.4, padding: '0 18px' }}>
        <div style={{ height: 40, background: 'var(--surface)', borderRadius: 8, marginBottom: 8 }}/>
        <div style={{ height: 60, background: 'var(--surface)', borderRadius: 8, marginBottom: 8 }}/>
        <div style={{ height: 60, background: 'var(--surface)', borderRadius: 8, marginBottom: 8 }}/>
      </div>

      {/* Sheet */}
      <div style={{
        position: 'absolute', left: 0, right: 0, bottom: 76,
        background: 'var(--bg)',
        borderTopLeftRadius: 18, borderTopRightRadius: 18,
        boxShadow: '0 -8px 32px rgba(0,0,0,0.18)',
        zIndex: 2, padding: '8px 18px 22px',
      }}>
        <div style={{
          width: 36, height: 4, borderRadius: 2, background: 'var(--hairline-2)',
          margin: '0 auto 14px',
        }} />
        <div style={{
          fontFamily: 'var(--serif)', fontSize: 22, color: 'var(--ink)',
          marginBottom: 14, letterSpacing: -0.2,
        }}>Записать приём</div>

        <CaptureOption
          icon={<svg width="20" height="20" viewBox="0 0 20 20" fill="none"><rect x="2" y="5" width="16" height="11" rx="1.5" stroke="currentColor" strokeWidth="1.4"/><circle cx="10" cy="10.5" r="3" stroke="currentColor" strokeWidth="1.4"/><path d="M7 5V4a1 1 0 011-1h4a1 1 0 011 1v1" stroke="currentColor" strokeWidth="1.4"/></svg>}
          title="Сделать фото"
          subtitle="Камера → AI оценка → принять"
          primary
        />
        <CaptureOption
          icon={<svg width="20" height="20" viewBox="0 0 20 20" fill="none"><rect x="2" y="3" width="13" height="13" rx="1.5" stroke="currentColor" strokeWidth="1.4"/><path d="M5 14l3-3 3 2 2-3 2 4" stroke="currentColor" strokeWidth="1.4" fill="none" strokeLinecap="round" strokeLinejoin="round"/><circle cx="6.5" cy="6.5" r="1" fill="currentColor"/></svg>}
          title="Из галереи"
          subtitle="Выбрать существующий снимок"
        />
        <CaptureOption
          icon={<svg width="20" height="20" viewBox="0 0 20 20" fill="none"><path d="M3 5h14M3 9h14M3 13h10" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/><circle cx="16" cy="13" r="2.5" stroke="currentColor" strokeWidth="1.4"/></svg>}
          title="Ввести текстом"
          subtitle="С автокомплитом по базе"
        />
        <CaptureOption
          icon={<svg width="20" height="20" viewBox="0 0 20 20" fill="none"><rect x="3" y="3" width="6" height="6" rx="1" stroke="currentColor" strokeWidth="1.4"/><rect x="11" y="3" width="6" height="6" rx="1" stroke="currentColor" strokeWidth="1.4"/><rect x="3" y="11" width="6" height="6" rx="1" stroke="currentColor" strokeWidth="1.4"/><rect x="11" y="11" width="6" height="6" rx="1" stroke="currentColor" strokeWidth="1.4"/></svg>}
          title="Шаблон"
          subtitle="4 частых · «Завтрак-3», «Обед-БК»…"
        />

        <div style={{ marginTop: 6, padding: '10px 12px', background: 'var(--surface)', borderRadius: 8, border: '0.5px solid var(--hairline)' }}>
          <div style={{ fontSize: 10, color: 'var(--muted)', letterSpacing: 0.6, fontWeight: 600, marginBottom: 3 }}>БЫСТРЫЕ КОМАНДЫ</div>
          <div style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--ink-2)' }}>
            bk: <span style={{ color: 'var(--muted)' }}>· завтрак </span>· bc: <span style={{ color: 'var(--muted)' }}>· последний</span>
          </div>
        </div>
      </div>

      <TabBar active="capture" />
    </Phone>
  );
}

function CaptureOption({ icon, title, subtitle, primary }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 14,
      padding: '12px 12px',
      background: primary ? 'var(--ink)' : 'var(--surface)',
      color: primary ? '#f6f4ef' : 'var(--ink)',
      border: primary ? 'none' : '0.5px solid var(--hairline)',
      borderRadius: 10, marginBottom: 8,
    }}>
      <div style={{
        width: 36, height: 36, borderRadius: 8,
        background: primary ? 'rgba(255,255,255,0.08)' : 'var(--bg)',
        color: primary ? '#f6f4ef' : 'var(--ink-2)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>{icon}</div>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 14, fontWeight: 600 }}>{title}</div>
        <div style={{ fontSize: 11, opacity: primary ? 0.7 : 1, color: primary ? 'rgba(246,244,239,0.7)' : 'var(--muted)', marginTop: 2 }}>{subtitle}</div>
      </div>
      <svg width="8" height="14" viewBox="0 0 8 14"><path d="M1 1l6 6-6 6" stroke="currentColor" strokeWidth="1.6" fill="none" strokeLinecap="round" strokeLinejoin="round"/></svg>
    </div>
  );
}

// ───────────────────────────────────────────────────────────
// SCREEN 2b · Черновик после фото
// ───────────────────────────────────────────────────────────
function ScreenDraft() {
  return (
    <Phone>
      {/* Modal-style header with close */}
      <div style={{
        padding: '8px 16px 12px', display: 'flex', alignItems: 'center',
        justifyContent: 'space-between', flexShrink: 0,
      }}>
        <button style={iconBtn}>
          <svg width="12" height="12" viewBox="0 0 12 12"><path d="M2 2l8 8M10 2l-8 8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/></svg>
        </button>
        <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: 1, color: 'var(--muted)' }}>ЧЕРНОВИК · ОЦЕНКА AI</div>
        <button style={iconBtn}>
          <svg width="14" height="4" viewBox="0 0 14 4"><circle cx="2" cy="2" r="1.5" fill="currentColor"/><circle cx="7" cy="2" r="1.5" fill="currentColor"/><circle cx="12" cy="2" r="1.5" fill="currentColor"/></svg>
        </button>
      </div>

      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '0 18px 16px' }}>
        {/* Photo preview */}
        <div style={{
          aspectRatio: '4/3', borderRadius: 10, overflow: 'hidden',
          background: 'linear-gradient(160deg,#caa078 0%, #8c6244 50%, #4a2e22 100%)',
          position: 'relative',
          border: '0.5px solid var(--hairline-2)',
        }}>
          <div style={{ position: 'absolute', inset: 0,
            background: 'radial-gradient(60% 80% at 30% 30%, rgba(255,235,200,0.4), transparent 70%)' }} />
          <div style={{ position: 'absolute', inset: 0,
            background: 'radial-gradient(40% 50% at 70% 60%, rgba(120,60,40,0.35), transparent 70%)' }} />
          {/* confidence chip */}
          <div style={{
            position: 'absolute', top: 10, right: 10,
            background: 'rgba(20,18,12,0.7)', color: '#f6f4ef',
            padding: '4px 8px', borderRadius: 12,
            fontSize: 10, letterSpacing: 0.4,
            fontFamily: 'var(--mono)',
            display: 'flex', alignItems: 'center', gap: 4,
          }}>
            <span style={{ width: 6, height: 6, borderRadius: 3, background: 'var(--good)' }} />
            УВЕРЕННОСТЬ 92%
          </div>
        </div>

        <div style={{ marginTop: 16 }}>
          <div style={{
            fontFamily: 'var(--serif)', fontSize: 22, color: 'var(--ink)', letterSpacing: -0.2,
          }}>Кусочек торта</div>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 3 }}>оценка по фото · 100 г</div>
        </div>

        {/* Macros — desktop layout, mono numbers */}
        <div style={{
          marginTop: 14, padding: '12px 14px',
          background: 'var(--surface)', border: '0.5px solid var(--hairline)', borderRadius: 10,
          display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8,
        }}>
          {[
            { k: 'УГЛ', v: '44.4', u: 'г', c: 'var(--accent)' },
            { k: 'БЕЛ', v: '5.1', u: 'г', c: 'var(--bad)' },
            { k: 'ЖИР', v: '23.9', u: 'г', c: 'var(--warn)' },
            { k: 'ККАЛ', v: '410', u: '', c: 'var(--good)' },
          ].map(m => (
            <div key={m.k}>
              <div style={{ fontSize: 9, fontWeight: 600, color: 'var(--muted)', letterSpacing: 1.2 }}>{m.k}</div>
              <div style={{ fontFamily: 'var(--mono)', fontSize: 18, fontWeight: 500, color: 'var(--ink)', marginTop: 2 }}>
                {m.v}<span style={{ fontSize: 9, color: 'var(--muted)', marginLeft: 2 }}>{m.u}</span>
              </div>
              <div style={{ marginTop: 4, height: 1.5, background: m.c, opacity: 0.6, width: '70%' }} />
            </div>
          ))}
        </div>

        {/* Editable weight only */}
        <div style={{
          marginTop: 12, background: 'var(--surface)', border: '0.5px solid var(--hairline)', borderRadius: 10,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 14px', borderBottom: '0.5px solid var(--hairline)' }}>
            <span style={{ fontSize: 12, color: 'var(--muted)', letterSpacing: 0.4 }}>ВЕС ЗАПИСИ</span>
            <span style={{ fontFamily: 'var(--mono)', fontSize: 14, color: 'var(--ink)' }}>100 <span style={{ color: 'var(--muted)' }}>г</span></span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 14px', borderBottom: '0.5px solid var(--hairline)' }}>
            <span style={{ fontSize: 12, color: 'var(--muted)', letterSpacing: 0.4 }}>ВРЕМЯ</span>
            <span style={{ fontFamily: 'var(--mono)', fontSize: 14, color: 'var(--ink)' }}>сегодня · 14:32</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 14px' }}>
            <span style={{ fontSize: 12, color: 'var(--muted)', letterSpacing: 0.4 }}>ИСТОЧНИК</span>
            <span style={{ fontSize: 12, color: 'var(--ink-2)' }}>фото · модель v3</span>
          </div>
        </div>

        <div style={{
          marginTop: 10, fontSize: 10.5, color: 'var(--muted)', lineHeight: 1.4,
          padding: '0 4px',
        }}>
          Развёрнутая правка компонентов и допущений модели — в десктоп-версии.
        </div>
      </div>

      {/* Footer CTA — black accept (the only place black-fill is allowed) */}
      <div style={{
        flexShrink: 0, padding: '12px 16px',
        borderTop: '0.5px solid var(--hairline)',
        background: 'var(--bg)',
        display: 'flex', gap: 8,
      }}>
        <button style={{
          flex: 0, padding: '14px 18px', borderRadius: 10,
          background: 'var(--surface)', border: '0.5px solid var(--hairline-2)',
          color: 'var(--ink-2)', fontSize: 14, fontWeight: 500,
          fontFamily: 'var(--sans)', cursor: 'pointer',
        }}>Отклонить</button>
        <button style={{
          flex: 1, padding: '14px 0', borderRadius: 10,
          background: 'var(--ink)', color: '#f6f4ef',
          border: 'none', fontSize: 15, fontWeight: 600,
          fontFamily: 'var(--sans)', cursor: 'pointer',
          letterSpacing: 0.2,
        }}>Принять</button>
      </div>
    </Phone>
  );
}

// ───────────────────────────────────────────────────────────
// SCREEN 3 · Запись (детали приёма)
// ───────────────────────────────────────────────────────────
function ScreenRecord() {
  return (
    <Phone>
      <div style={{
        padding: '8px 16px 10px', display: 'flex', alignItems: 'center',
        justifyContent: 'space-between', flexShrink: 0,
      }}>
        <button style={iconBtn}>
          <svg width="14" height="14" viewBox="0 0 14 14"><path d="M9 2L4 7l5 5" stroke="currentColor" strokeWidth="1.6" fill="none" strokeLinecap="round" strokeLinejoin="round"/></svg>
        </button>
        <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: 1, color: 'var(--muted)' }}>ЗАПИСЬ</div>
        <button style={iconBtn}>
          <svg width="14" height="4" viewBox="0 0 14 4"><circle cx="2" cy="2" r="1.5" fill="currentColor"/><circle cx="7" cy="2" r="1.5" fill="currentColor"/><circle cx="12" cy="2" r="1.5" fill="currentColor"/></svg>
        </button>
      </div>

      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '0 18px 14px' }}>
        {/* Hero: thumb + name + kcal */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 14 }}>
          <div style={{
            width: 64, height: 64, borderRadius: 8,
            background: 'linear-gradient(160deg,#c9a884 0%, #9a7a5a 50%, #6a4f3a 100%)',
            border: '0.5px solid var(--hairline-2)', flexShrink: 0,
          }} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontFamily: 'var(--serif)', fontSize: 20, color: 'var(--ink)', letterSpacing: -0.2 }}>Кусочек торта</div>
            <div style={{ fontFamily: 'var(--mono)', fontSize: 22, color: 'var(--ink)', marginTop: 2, fontWeight: 500 }}>
              410 <span style={{ fontSize: 11, color: 'var(--muted)' }}>ккал</span>
            </div>
            <div style={{ display: 'flex', gap: 5, marginTop: 6 }}>
              <Pill>вручную</Pill>
              <Pill solid>принято</Pill>
              <Pill mono>100 г</Pill>
            </div>
          </div>
        </div>

        {/* Macros summary */}
        <div style={{
          background: 'var(--surface)', border: '0.5px solid var(--hairline)', borderRadius: 10,
          padding: '10px 14px',
        }}>
          <div style={{ fontSize: 9, fontWeight: 600, letterSpacing: 1.2, color: 'var(--muted)', marginBottom: 6 }}>СВОДКА МАКРОСОВ</div>
          <div style={{ fontFamily: 'var(--mono)', fontSize: 13, color: 'var(--ink)' }}>
            У <strong style={{ fontWeight: 500 }}>44.4</strong> · Б <strong style={{ fontWeight: 500 }}>5.1</strong> · Ж <strong style={{ fontWeight: 500 }}>23.9</strong> · К <strong style={{ fontWeight: 500 }}>410</strong>
          </div>
        </div>

        {/* Edit fields */}
        <div style={{ marginTop: 14 }}>
          <div style={{ fontSize: 9, fontWeight: 600, letterSpacing: 1.2, color: 'var(--muted)', marginBottom: 6, paddingLeft: 4 }}>БЫСТРОЕ РЕДАКТИРОВАНИЕ</div>
          <div style={{ background: 'var(--surface)', border: '0.5px solid var(--hairline)', borderRadius: 10, overflow: 'hidden' }}>
            <Field label="Название" value="Кусочек торта" />
            <Field label="Время" value="05.05.2026 · 07:54" mono />
            <Field label="Вес записи" value="100 г" mono action="Пересчитать" />
            <Field label="Создать ещё порцию" value="100 г · 127 г · текущий" subdued last />
          </div>
        </div>

        {/* Source / sync — small lines */}
        <div style={{ marginTop: 14, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
          <MiniRow k="ИСТОЧНИК" v="оценка по фото" extra="высокая · 92%" />
          <MiniRow k="NIGHTSCOUT" v="не синхр." extra="будет при сети" warn />
        </div>

        {/* Glucose strip from desktop */}
        <div style={{
          marginTop: 14, padding: '12px 14px',
          background: 'var(--surface)', border: '0.5px solid var(--hairline)', borderRadius: 10,
          display: 'flex', alignItems: 'center', gap: 12,
        }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 9, fontWeight: 600, letterSpacing: 1.2, color: 'var(--muted)' }}>ГЛЮКОЗА В МОМЕНТ</div>
            <div style={{ fontFamily: 'var(--mono)', fontSize: 17, color: 'var(--ink)', marginTop: 4, fontWeight: 500 }}>
              9,9 <span style={{ fontSize: 10, color: 'var(--muted)' }}>ммоль/л</span>
              <span style={{ fontSize: 11, color: 'var(--good)', marginLeft: 8 }}>в диапазоне</span>
            </div>
          </div>
          <button style={{ ...iconBtn, padding: '5px 10px', width: 'auto', borderRadius: 8, fontSize: 11 }}>Открыть →</button>
        </div>

        {/* Actions */}
        <div style={{ marginTop: 16, display: 'flex', gap: 8 }}>
          <button style={{ flex: 1, padding: '12px 0', borderRadius: 10, background: 'var(--surface)', border: '0.5px solid var(--hairline-2)', color: 'var(--ink)', fontSize: 13, cursor: 'pointer', fontFamily: 'var(--sans)' }}>★ В избранное</button>
          <button style={{ flex: 1, padding: '12px 0', borderRadius: 10, background: 'var(--surface)', border: '0.5px solid var(--hairline-2)', color: 'var(--warn)', fontSize: 13, cursor: 'pointer', fontFamily: 'var(--sans)' }}>Удалить</button>
        </div>
      </div>
      <HomeIndicator />
    </Phone>
  );
}

function Pill({ children, solid, mono }) {
  return (
    <span style={{
      fontSize: 10, padding: '2px 7px', borderRadius: 4,
      background: solid ? 'var(--good)' : 'var(--bg)',
      color: solid ? '#f6f4ef' : 'var(--ink-2)',
      border: solid ? 'none' : '0.5px solid var(--hairline-2)',
      fontFamily: mono ? 'var(--mono)' : 'var(--sans)',
      letterSpacing: 0.3, fontWeight: 500,
    }}>{children}</span>
  );
}

function Field({ label, value, last, mono, action, subdued }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '11px 14px',
      borderBottom: last ? 'none' : '0.5px solid var(--hairline)',
      gap: 8,
    }}>
      <span style={{ fontSize: 12, color: 'var(--muted)', flexShrink: 0 }}>{label}</span>
      <span style={{
        fontSize: 13, color: subdued ? 'var(--muted)' : 'var(--ink)',
        fontFamily: mono ? 'var(--mono)' : 'var(--sans)',
        textAlign: 'right',
      }}>{value}</span>
      {action && (
        <button style={{ ...iconBtn, padding: '4px 8px', width: 'auto', borderRadius: 6, fontSize: 11, marginLeft: 4 }}>{action}</button>
      )}
    </div>
  );
}

function MiniRow({ k, v, extra, warn }) {
  return (
    <div style={{
      background: 'var(--surface)', border: '0.5px solid var(--hairline)',
      borderRadius: 10, padding: '8px 12px',
    }}>
      <div style={{ fontSize: 9, fontWeight: 600, letterSpacing: 1, color: 'var(--muted)' }}>{k}</div>
      <div style={{ fontSize: 12, color: 'var(--ink-2)', marginTop: 3 }}>{v}</div>
      <div style={{ fontSize: 10, color: warn ? 'var(--warn)' : 'var(--good)', marginTop: 2 }}>{extra}</div>
    </div>
  );
}

// ───────────────────────────────────────────────────────────
// SCREEN 4 · Глюкоза
// ───────────────────────────────────────────────────────────
function ScreenGlucose() {
  // build a longer, more interesting glucose curve
  const pts = [
    5.6, 5.4, 5.8, 6.2, 7.4, 8.9, 10.4, 11.2, 10.8, 9.6, 8.4, 7.8,
    7.4, 7.1, 7.0, 6.8, 6.6, 6.5, 6.3, 6.0, 6.4, 8.2, 10.1, 11.5,
    11.2, 10.0, 9.0, 8.4, 8.0, 7.6, 7.2, 7.0,
  ];
  return (
    <Phone>
      {/* Header */}
      <div style={{
        padding: '12px 18px 8px', flexShrink: 0,
        display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
      }}>
        <div>
          <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: 1.2, color: 'var(--muted)', marginBottom: 4 }}>ГЛЮКОЗА</div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
            <span style={{ fontFamily: 'var(--mono)', fontSize: 44, fontWeight: 400, color: 'var(--ink)', letterSpacing: -1 }}>9,9</span>
            <span style={{ fontSize: 12, color: 'var(--muted)' }}>ммоль/л</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 4 }}>
            <span style={{ fontFamily: 'var(--mono)', fontSize: 13, color: 'var(--warn)' }}>↘ −0,6 за 15 мин</span>
            <span style={{ fontSize: 11, color: 'var(--muted)' }}>2 мин назад</span>
          </div>
        </div>
        <button style={{ ...iconBtn, width: 36, height: 36, borderRadius: 8 }}>
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
            <path d="M9 2v6m0 0l-2.5-2.5M9 8l2.5-2.5M3 11h12M5 14h8" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
          </svg>
        </button>
      </div>

      {/* Segmented control */}
      <div style={{ padding: '4px 18px 10px', flexShrink: 0 }}>
        <div style={{
          display: 'flex', background: 'var(--hairline)', borderRadius: 8, padding: 2,
        }}>
          {['3 ч', '6 ч', '24 ч', '7 дн'].map((s, i) => (
            <div key={s} style={{
              flex: 1, padding: '7px 0', textAlign: 'center',
              fontSize: 12, fontWeight: 600,
              borderRadius: 6,
              background: i === 1 ? 'var(--surface)' : 'transparent',
              color: i === 1 ? 'var(--ink)' : 'var(--muted)',
              boxShadow: i === 1 ? '0 1px 2px rgba(0,0,0,0.06)' : 'none',
              letterSpacing: 0.4,
            }}>{s}</div>
          ))}
        </div>
      </div>

      {/* Big chart */}
      <div style={{ padding: '0 18px', flexShrink: 0 }}>
        <GlucoseChart points={pts} />
      </div>

      {/* TIR line */}
      <div style={{
        margin: '12px 18px 10px',
        background: 'var(--surface)', border: '0.5px solid var(--hairline)', borderRadius: 10,
        padding: '10px 14px',
      }}>
        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 8 }}>
          <span style={{ fontSize: 10, fontWeight: 600, letterSpacing: 1.2, color: 'var(--muted)' }}>TIR · СЕГОДНЯ</span>
          <span style={{ fontFamily: 'var(--mono)', fontSize: 13, color: 'var(--ink)' }}>
            <span style={{ color: 'var(--good)', fontWeight: 500 }}>62%</span>
            <span style={{ color: 'var(--muted)' }}> в диапазоне</span>
          </span>
        </div>
        <div style={{ display: 'flex', height: 6, borderRadius: 3, overflow: 'hidden' }}>
          <div style={{ width: '8%', background: 'var(--info)' }} />
          <div style={{ width: '62%', background: 'var(--good)' }} />
          <div style={{ width: '26%', background: 'var(--warn)' }} />
          <div style={{ width: '4%', background: 'var(--bad)' }} />
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 6, fontSize: 9.5, color: 'var(--muted)', fontFamily: 'var(--mono)', letterSpacing: 0.3 }}>
          <span>низко 8%</span><span>норма 62%</span><span>выше 26%</span><span>оч. выс. 4%</span>
        </div>
      </div>

      {/* Daypart 6×4ч grid 2×3 */}
      <div style={{ padding: '0 18px 12px', flex: 1, minHeight: 0, overflowY: 'auto' }}>
        <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: 1.2, color: 'var(--muted)', margin: '4px 0 8px' }}>ПРОФИЛЬ ПО ВРЕМЕНИ СУТОК</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
          {[
            { h: '00–04', v: '6,9', tir: '34%', tone: 'warn' },
            { h: '04–08', v: '5,9', tir: '62%', tone: 'good' },
            { h: '08–12', v: '6,0', tir: '69%', tone: 'good' },
            { h: '12–16', v: '6,6', tir: '67%', tone: 'good' },
            { h: '16–20', v: '6,2', tir: '74%', tone: 'good' },
            { h: '20–24', v: '5,4', tir: '41%', tone: 'warn' },
          ].map(d => (
            <div key={d.h} style={{
              background: d.tone === 'good' ? '#e9f0e0' : '#f5e6d4',
              border: '0.5px solid ' + (d.tone === 'good' ? '#cad8b8' : '#e2c9ad'),
              borderRadius: 8, padding: '10px 12px',
            }}>
              <div style={{ fontSize: 9.5, fontWeight: 600, letterSpacing: 0.6, color: 'var(--ink-2)' }}>{d.h}</div>
              <div style={{ fontFamily: 'var(--mono)', fontSize: 19, color: 'var(--ink)', marginTop: 2, fontWeight: 500 }}>{d.v}</div>
              <div style={{ fontFamily: 'var(--mono)', fontSize: 9.5, color: 'var(--muted)', letterSpacing: 0.2 }}>ммоль/л · TIR {d.tir}</div>
            </div>
          ))}
        </div>
      </div>

      <TabBar active="glucose" />
    </Phone>
  );
}

function GlucoseChart({ points }) {
  const W = 344, H = 180, pad = { l: 22, r: 4, t: 8, b: 16 };
  const min = 3, max = 13;
  const step = (W - pad.l - pad.r) / (points.length - 1);
  const yFor = v => pad.t + (1 - (v - min) / (max - min)) * (H - pad.t - pad.b);

  const pathD = points.map((v, i) => `${i === 0 ? 'M' : 'L'}${(pad.l + i * step).toFixed(1)},${yFor(v).toFixed(1)}`).join(' ');
  const areaD = pathD + ` L${(pad.l + (points.length - 1) * step).toFixed(1)},${(H - pad.b).toFixed(1)} L${pad.l},${(H - pad.b).toFixed(1)} Z`;

  // band: 4–10 mmol/l (target range)
  const yLow = yFor(10);
  const yHigh = yFor(4);

  return (
    <div style={{
      background: 'var(--surface)', border: '0.5px solid var(--hairline)',
      borderRadius: 10, padding: '6px 6px 4px', position: 'relative',
    }}>
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} style={{ display: 'block', width: '100%', height: 'auto' }}>
        {/* target band */}
        <rect x={pad.l} y={yLow} width={W - pad.l - pad.r} height={yHigh - yLow}
              fill="var(--good)" fillOpacity="0.08" />
        <line x1={pad.l} y1={yLow} x2={W - pad.r} y2={yLow} stroke="var(--good)" strokeOpacity="0.4" strokeDasharray="2 3" strokeWidth="0.6" />
        <line x1={pad.l} y1={yHigh} x2={W - pad.r} y2={yHigh} stroke="var(--good)" strokeOpacity="0.4" strokeDasharray="2 3" strokeWidth="0.6" />

        {/* y labels */}
        {[3, 6, 9, 12].map(v => (
          <text key={v} x={pad.l - 4} y={yFor(v) + 3} fontSize="9" fontFamily="JetBrains Mono, monospace" fill="var(--muted)" textAnchor="end">{v}</text>
        ))}

        {/* x labels */}
        {[0, 0.25, 0.5, 0.75, 1].map(t => {
          const x = pad.l + t * (W - pad.l - pad.r);
          const labels = ['−6ч', '−4:30', '−3ч', '−1:30', 'сейчас'];
          return (
            <text key={t} x={x} y={H - 3} fontSize="9" fontFamily="JetBrains Mono, monospace" fill="var(--muted)" textAnchor={t === 0 ? 'start' : t === 1 ? 'end' : 'middle'}>
              {labels[Math.round(t * 4)]}
            </text>
          );
        })}

        {/* area + line */}
        <path d={areaD} fill="var(--ink)" fillOpacity="0.04" />
        <path d={pathD} stroke="var(--ink)" strokeWidth="1.4" fill="none" strokeLinejoin="round" strokeLinecap="round" />

        {/* current point */}
        <circle cx={pad.l + (points.length - 1) * step} cy={yFor(points[points.length - 1])} r="4" fill="var(--bg)" stroke="var(--ink)" strokeWidth="1.6" />

        {/* meal markers */}
        {[7, 23].map((idx) => (
          <g key={idx}>
            <line x1={pad.l + idx * step} y1={pad.t} x2={pad.l + idx * step} y2={H - pad.b}
                  stroke="var(--accent)" strokeOpacity="0.4" strokeWidth="0.6" strokeDasharray="1 2" />
            <circle cx={pad.l + idx * step} cy={pad.t + 2} r="2.2" fill="var(--accent)" />
          </g>
        ))}
      </svg>
    </div>
  );
}

// ───────────────────────────────────────────────────────────
// SCREEN 5 · История
// ───────────────────────────────────────────────────────────
function ScreenHistory() {
  return (
    <Phone>
      <div style={{ padding: '12px 18px 8px', flexShrink: 0 }}>
        <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: 1.2, color: 'var(--muted)' }}>ВСЕ ЗАПИСИ</div>
        <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', marginTop: 2 }}>
          <div style={{ fontFamily: 'var(--serif)', fontSize: 32, color: 'var(--ink)', letterSpacing: -0.4 }}>История</div>
          <div style={{ display: 'flex', gap: 6 }}>
            <button style={iconBtn}>
              <svg width="14" height="14" viewBox="0 0 14 14"><path d="M2 3h10M4 7h6M6 11h2" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/></svg>
            </button>
            <button style={iconBtn}>
              <svg width="14" height="14" viewBox="0 0 14 14"><circle cx="6" cy="6" r="4" stroke="currentColor" strokeWidth="1.4" fill="none"/><path d="M9 9l3 3" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/></svg>
            </button>
          </div>
        </div>
      </div>

      {/* Chip filters horizontal */}
      <div style={{
        padding: '4px 18px 10px', flexShrink: 0,
        display: 'flex', gap: 6, overflowX: 'auto',
      }}>
        {[
          { l: 'С CGM', icon: '〜' },
          { l: 'С инсулином', icon: '◯' },
          { l: 'Низкая увер.', icon: '⌽' },
          { l: 'Только фото', icon: '◫' },
        ].map(c => (
          <span key={c.l} style={{
            padding: '5px 10px', fontSize: 11, fontWeight: 500,
            borderRadius: 6, background: 'var(--surface)',
            border: '0.5px solid var(--hairline-2)', color: 'var(--ink-2)',
            whiteSpace: 'nowrap', flexShrink: 0,
          }}>{c.icon} {c.l}</span>
        ))}
      </div>

      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '0 14px 14px' }}>
        <DayBlock day="вторник, 5 мая" sparkline={[6.4, 7.2, 9.1, 10.4, 8.6, 7.4, 7.1, 6.8, 8.2, 10.1, 9.6, 8.4]} kpis={['4 приёма', '150 г углеводы', '1536 ккал', 'TIR 62%']}
          rows={[
            { time: '20:08', name: 'Бисквит-сэндвич ×2', meta: 'смешано · принято', carbs: '37.2', kcal: '246', thumb: 'cake' },
            { time: '13:13', name: 'Сырные Медальоны + Сметана', meta: 'шаблон · принято', carbs: '34', kcal: '340', thumb: 'empty' },
            { time: '07:54', name: 'Кусочек торта', meta: 'вручную · принято', carbs: '44.4', kcal: '410', thumb: 'cake2' },
          ]} />
        <DayBlock day="понедельник, 4 мая" sparkline={[7.2, 7.6, 8.4, 9.6, 8.2, 7.4, 6.8, 6.5, 8.6, 11.0, 10.2, 8.6]} kpis={['6 приёмов', '191 г углеводы', '1925 ккал', 'TIR 58%']}
          rows={[
            { time: '22:27', name: 'Хинкали «Сибирская коллекция»', meta: 'фото · принято · 500 г', carbs: '110', kcal: '800', thumb: 'cake' },
            { time: '17:12', name: 'Слойка с ветчиной и сыром', meta: 'фото · принято · 60 г', carbs: '24.6', kcal: '247', thumb: 'bun' },
          ]} />
      </div>

      <TabBar active="history" />
    </Phone>
  );
}

function DayBlock({ day, kpis, rows, sparkline }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ padding: '4px 4px 8px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ fontFamily: 'var(--serif)', fontSize: 18, color: 'var(--ink)', letterSpacing: -0.2 }}>{day}</div>
        <GlucoseSparkline width={64} height={20} color="var(--ink-2)" points={sparkline} />
      </div>
      <div style={{
        padding: '6px 4px 8px', fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--muted)',
        display: 'flex', flexWrap: 'wrap', gap: '4px 12px',
      }}>
        {kpis.map((k, i) => <span key={i}><span style={{ color: 'var(--ink-2)' }}>{k.split(' ')[0]}</span>{' ' + k.split(' ').slice(1).join(' ')}</span>)}
      </div>
      <div style={{
        background: 'var(--surface)', border: '0.5px solid var(--hairline)', borderRadius: 10, overflow: 'hidden',
      }}>
        {rows.map((r, i) => (
          <MealRow key={i} {...r} b="—" f="—" c={r.carbs} last={i === rows.length - 1} />
        ))}
      </div>
    </div>
  );
}

// ───────────────────────────────────────────────────────────
// SCREEN 6 · Статистика (свайп из Сегодня)
// ───────────────────────────────────────────────────────────
function ScreenStats() {
  return (
    <Phone>
      <div style={{ padding: '12px 18px 6px', flexShrink: 0 }}>
        <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: 1.2, color: 'var(--muted)' }}>СТАТИСТИКА</div>
        <div style={{ fontFamily: 'var(--serif)', fontSize: 22, color: 'var(--ink)', letterSpacing: -0.2, marginTop: 2 }}>5 мая 2026 г.</div>
        <div style={{ fontFamily: 'var(--serif)', fontSize: 17, color: 'var(--ink-2)', letterSpacing: -0.1 }}>Профицит <strong style={{ fontWeight: 500 }}>1892</strong> ккал за завершённые дни</div>
        <div style={{ fontSize: 10, color: 'var(--muted)', marginTop: 4, fontFamily: 'var(--mono)', letterSpacing: 0.2 }}>
          средн. <span style={{ color: 'var(--ink-2)' }}>2702</span> · сегодня <span style={{ color: 'var(--ink-2)' }}>1536</span> · баланс <span style={{ color: 'var(--warn)' }}>−3517</span>
        </div>
      </div>

      {/* Swipe indicator */}
      <div style={{ padding: '0 18px 6px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, fontSize: 10, color: 'var(--muted)', flexShrink: 0 }}>
        <span style={{ width: 24, height: 2, background: 'var(--ink-2)', borderRadius: 1 }} />
        <span style={{ width: 6, height: 6, borderRadius: 3, background: 'var(--ink)' }} />
        <span>СТАТИСТИКА</span>
        <span>·</span>
        <span style={{ color: 'var(--muted)' }}>СВАЙП ↔ СЕГОДНЯ</span>
      </div>

      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '8px 14px 14px' }}>
        {/* 4 KPIs in 2×2 */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
          <StatTile k="УГЛЕВОДЫ" v="149.6" u="г" sub="средн. 7 дн · 226.8 г" pct={66} c="var(--accent)" />
          <StatTile k="ККАЛ" v="1536" u="" sub="цель 2200 · TDEE 2814" pct={70} c="var(--good)" />
          <StatTile k="ГИ" v="38" u="" sub="норма < 100 · средн. 72" pct={38} c="var(--info)" />
          <StatTile k="БЖУ-БАЛАНС" v="Б 43.8" u="· Ж 85.5" sub="У 149.6 г · клетч. 0.9 г" pct={50} c="var(--warn)" />
        </div>

        {/* Chart 1 — углеводы по дням */}
        <ChartCard title="Углеводы (г) по дням" hint="дни с едой">
          <BarChart data={[230, 220, 280, 200, 215, 240, 195, 175, 210, 145]} target={225} color="var(--accent)" />
        </ChartCard>

        {/* Chart 2 — баланс калорий */}
        <ChartCard title="Баланс калорий (ккал)" hint="отн. TDEE">
          <BalanceChart data={[
            { d: 'ВТ', v: 364 }, { d: 'СР', v: 814 }, { d: 'ЧТ', v: 487 },
            { d: 'ПТ', v: 131 }, { d: 'СБ', v: 888 }, { d: 'ВС', v: -657 },
            { d: 'ПН', v: -136 }, { d: 'ВТ', v: -3517, current: true },
          ]} />
        </ChartCard>

        {/* TIR placeholder */}
        <ChartCard title="Время в диапазоне (TIR)" hint="6 дней · шкала 0–100%">
          <TIRBars data={[
            { l: 88, n: 8, h: 4 }, { l: 4, n: 84, h: 12 }, { l: 0, n: 88, h: 12 },
            { l: 6, n: 56, h: 38 }, { l: 4, n: 48, h: 48 }, { l: 8, n: 62, h: 30 },
          ]} />
        </ChartCard>

        {/* Daypart 2×3 — same as Glucose */}
        <ChartCard title="Профиль по времени суток" hint="средн. за 7 дней">
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 6 }}>
            {[
              { h: '00–04', v: '6,9', tone: 'warn' },
              { h: '04–08', v: '5,9', tone: 'good' },
              { h: '08–12', v: '6,0', tone: 'good' },
              { h: '12–16', v: '6,6', tone: 'good' },
              { h: '16–20', v: '6,2', tone: 'good' },
              { h: '20–24', v: '5,4', tone: 'warn' },
            ].map(d => (
              <div key={d.h} style={{
                background: d.tone === 'good' ? '#e9f0e0' : '#f5e6d4',
                border: '0.5px solid ' + (d.tone === 'good' ? '#cad8b8' : '#e2c9ad'),
                borderRadius: 6, padding: '6px 7px', textAlign: 'center',
              }}>
                <div style={{ fontFamily: 'var(--mono)', fontSize: 9, color: 'var(--ink-2)', letterSpacing: 0.4 }}>{d.h}</div>
                <div style={{ fontFamily: 'var(--mono)', fontSize: 14, fontWeight: 500, color: 'var(--ink)', marginTop: 1 }}>{d.v}</div>
              </div>
            ))}
          </div>
        </ChartCard>

        <div style={{
          marginTop: 6, padding: '12px 14px',
          background: 'var(--surface)', border: '0.5px dashed var(--hairline-2)', borderRadius: 10,
          fontSize: 11, color: 'var(--muted)', lineHeight: 1.4,
        }}>
          Тепловая карта 6 × 7 — <span style={{ color: 'var(--ink-2)' }}>в десктоп-версии</span>. На 380 px она нечитаема.
        </div>
      </div>
    </Phone>
  );
}

function StatTile({ k, v, u, sub, pct, c }) {
  return (
    <div style={{ background: 'var(--surface)', border: '0.5px solid var(--hairline)', borderRadius: 10, padding: '10px 12px' }}>
      <div style={{ fontSize: 9, fontWeight: 600, letterSpacing: 1.2, color: 'var(--muted)' }}>{k}</div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 4, marginTop: 4 }}>
        <span style={{ fontFamily: 'var(--mono)', fontSize: 18, color: c, fontWeight: 500, letterSpacing: -0.3 }}>{v}</span>
        <span style={{ fontSize: 9.5, color: 'var(--muted)' }}>{u}</span>
      </div>
      <div style={{ marginTop: 6, height: 1.5, background: 'var(--hairline)' }}>
        <div style={{ height: '100%', width: `${pct}%`, background: c, opacity: 0.6 }} />
      </div>
      <div style={{ fontSize: 9.5, color: 'var(--muted)', marginTop: 4, fontFamily: 'var(--mono)', letterSpacing: 0.1 }}>{sub}</div>
    </div>
  );
}

function ChartCard({ title, hint, children }) {
  return (
    <div style={{
      marginTop: 10,
      background: 'var(--surface)', border: '0.5px solid var(--hairline)',
      borderRadius: 10, padding: '12px 12px 10px',
    }}>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 8 }}>
        <span style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--ink)', letterSpacing: -0.1 }}>{title}</span>
        <span style={{ fontSize: 9.5, color: 'var(--muted)', letterSpacing: 0.4, textTransform: 'uppercase' }}>{hint}</span>
      </div>
      {children}
    </div>
  );
}

function BarChart({ data, target, color }) {
  const max = Math.max(...data, target) * 1.05;
  const W = 320, H = 92;
  const bw = (W - 6) / data.length - 4;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} style={{ display: 'block' }}>
      <line x1="0" y1={H - (target / max) * H} x2={W} y2={H - (target / max) * H}
            stroke="var(--accent)" strokeOpacity="0.5" strokeDasharray="3 3" strokeWidth="0.7" />
      {data.map((v, i) => {
        const h = (v / max) * H;
        return (
          <rect key={i} x={3 + i * (bw + 4)} y={H - h} width={bw} height={h} rx="1.5"
                fill={color} fillOpacity={i === data.length - 1 ? 0.9 : 0.65} />
        );
      })}
    </svg>
  );
}

function BalanceChart({ data }) {
  const max = Math.max(...data.map(d => Math.abs(d.v)));
  const W = 320, H = 110;
  const mid = H / 2;
  const bw = (W - 6) / data.length - 4;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} style={{ display: 'block' }}>
      <line x1="0" y1={mid} x2={W} y2={mid} stroke="var(--ink-2)" strokeOpacity="0.3" strokeWidth="0.7" />
      <text x="2" y={mid - 3} fontSize="8" fill="var(--muted)" fontFamily="JetBrains Mono">TDEE</text>
      {data.map((d, i) => {
        const h = (Math.abs(d.v) / max) * (mid - 14);
        const positive = d.v > 0;
        const x = 3 + i * (bw + 4);
        return (
          <g key={i}>
            <rect x={x} y={positive ? mid - h : mid} width={bw} height={h} rx="1.5"
                  fill={d.current ? 'var(--bad)' : positive ? 'var(--warn)' : 'var(--good)'}
                  fillOpacity={d.current ? 1 : 0.7} />
            <text x={x + bw / 2} y={positive ? mid - h - 3 : mid + h + 8} fontSize="8.5"
                  textAnchor="middle" fontFamily="JetBrains Mono" fill={d.current ? 'var(--bad)' : 'var(--muted)'}
                  fontWeight={d.current ? '600' : '400'}>
              {d.v > 0 ? `+${d.v}` : d.v}
            </text>
            <text x={x + bw / 2} y={H - 1} fontSize="8" textAnchor="middle"
                  fontFamily="JetBrains Mono" fill="var(--muted)" fontWeight={d.current ? '600' : '400'}>{d.d}</text>
          </g>
        );
      })}
    </svg>
  );
}

function TIRBars({ data }) {
  const W = 320, H = 80;
  const bw = (W - 8) / data.length - 6;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} style={{ display: 'block' }}>
      <line x1="0" y1={H - (70 / 100) * H} x2={W} y2={H - (70 / 100) * H}
            stroke="var(--good)" strokeOpacity="0.5" strokeDasharray="3 3" strokeWidth="0.7" />
      <text x={W - 2} y={H - (70 / 100) * H - 2} fontSize="8" fontFamily="JetBrains Mono"
            fill="var(--muted)" textAnchor="end">цель ≥70%</text>
      {data.map((d, i) => {
        const x = 4 + i * (bw + 6);
        const lh = (d.l / 100) * H, nh = (d.n / 100) * H, hh = (d.h / 100) * H;
        return (
          <g key={i}>
            <rect x={x} y={H - lh} width={bw} height={lh} fill="var(--info)" fillOpacity="0.7" />
            <rect x={x} y={H - lh - nh} width={bw} height={nh} fill="var(--good)" fillOpacity="0.85" />
            <rect x={x} y={H - lh - nh - hh} width={bw} height={hh} fill="var(--warn)" fillOpacity="0.7" />
          </g>
        );
      })}
    </svg>
  );
}

// ───────────────────────────────────────────────────────────
// SCREEN 7 · База продуктов
// ───────────────────────────────────────────────────────────
function ScreenBase() {
  return (
    <Phone>
      <div style={{ padding: '12px 18px 8px', flexShrink: 0 }}>
        <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: 1.2, color: 'var(--muted)' }}>ПРОДУКТЫ · ШАБЛОНЫ · РЕСТОРАНЫ</div>
        <div style={{ fontFamily: 'var(--serif)', fontSize: 32, color: 'var(--ink)', letterSpacing: -0.4, marginTop: 2 }}>База</div>
      </div>

      <div style={{ padding: '4px 18px 8px', flexShrink: 0 }}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          background: 'var(--surface)', border: '0.5px solid var(--hairline-2)',
          borderRadius: 8, padding: '9px 12px',
        }}>
          <svg width="14" height="14" viewBox="0 0 14 14" style={{ color: 'var(--muted)' }}>
            <circle cx="6" cy="6" r="4" stroke="currentColor" strokeWidth="1.4" fill="none"/>
            <path d="M9 9l3 3" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
          </svg>
          <span style={{ fontSize: 13, color: 'var(--muted)' }}>Поиск по базе…</span>
        </div>
      </div>

      <div style={{ padding: '0 18px 10px', flexShrink: 0, display: 'flex', gap: 5, overflowX: 'auto' }}>
        {[
          { l: 'Частые', active: true },
          { l: 'Рестораны' }, { l: 'Продукты' }, { l: 'Шаблоны' }, { l: 'Требуют проверки' },
        ].map(c => (
          <span key={c.l} style={{
            padding: '5px 10px', fontSize: 11, fontWeight: 500,
            borderRadius: 6,
            background: c.active ? 'var(--ink)' : 'var(--surface)',
            border: c.active ? 'none' : '0.5px solid var(--hairline-2)',
            color: c.active ? '#f6f4ef' : 'var(--ink-2)',
            whiteSpace: 'nowrap', flexShrink: 0,
          }}>{c.l}</span>
        ))}
      </div>

      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '0 14px 14px' }}>
        <div style={{ background: 'var(--surface)', border: '0.5px solid var(--hairline)', borderRadius: 10, overflow: 'hidden' }}>
          <BaseRow name="Протеиновое брауни Shagi" tag="ROYAL CAKE" y="8" b="4" k="11" kcal="144" used="10" thumb="cake" />
          <BaseRow name="Халва подсолнечная глазированная" tag="ВОСТОЧНЫЙ ГОСТЬ" y="9" b="2" k="7" kcal="110" used="7" thumb="cake2" />
          <BaseRow name="Сырок глазированный" tag="LABEL_CALC" y="14" b="3" k="10" kcal="165" used="7" thumb="bun" />
          <BaseRow name="Кола Ориджинал" tag="ЧЕРНОГОЛОВКА" y="16" b="0" k="0" kcal="63" used="5" thumb="empty" />
          <BaseRow name="Бисквит-сэндвич" tag="LABEL_CALC" y="19" b="1" k="5" kcal="123" used="4" thumb="cake" />
          <BaseRow name="Чизбургер Новый" tag="ROSTICS" y="40" b="13" k="14" kcal="336" used="2" thumb="bun" />
          <BaseRow name="Шоколад тёмный Бабаевский" tag="БАБАЕВСКИЙ" y="29" b="3" k="12" kcal="240" used="2" thumb="cake2" last />
        </div>
        <div style={{
          marginTop: 12, padding: '12px 14px',
          background: 'var(--surface)', border: '0.5px dashed var(--hairline-2)', borderRadius: 10,
          fontSize: 11, color: 'var(--muted)', lineHeight: 1.4,
        }}>
          Импорт и создание со всеми полями — <span style={{ color: 'var(--ink-2)' }}>в десктоп-версии</span>.
        </div>
      </div>

      <TabBar active="more" />
    </Phone>
  );
}

function BaseRow({ name, tag, y, b, k, kcal, used, thumb, last }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 10,
      padding: '10px 12px', borderBottom: last ? 'none' : '0.5px solid var(--hairline)',
    }}>
      <Thumb kind={thumb} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 12.5, fontWeight: 500, color: 'var(--ink)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{name}</div>
        <div style={{ fontSize: 9.5, color: 'var(--muted)', fontFamily: 'var(--mono)', letterSpacing: 0.4, marginTop: 2 }}>{tag} · НЕ ПРОВЕРЕНО</div>
      </div>
      <div style={{ textAlign: 'right', flexShrink: 0, fontFamily: 'var(--mono)', fontSize: 10.5 }}>
        <div style={{ color: 'var(--ink-2)' }}>{y}<span style={{ color: 'var(--muted)' }}>у</span> · {b}<span style={{ color: 'var(--muted)' }}>б</span> · {k}<span style={{ color: 'var(--muted)' }}>к</span></div>
        <div style={{ color: 'var(--ink)', fontWeight: 500, marginTop: 1 }}>{kcal}<span style={{ color: 'var(--muted)', fontWeight: 400 }}> ккал</span></div>
        <div style={{ color: 'var(--muted)', marginTop: 1, fontSize: 9 }}>×{used} раз</div>
      </div>
    </div>
  );
}

// ───────────────────────────────────────────────────────────
// SCREEN 8 · Ещё / Настройки
// ───────────────────────────────────────────────────────────
function ScreenSettings() {
  return (
    <Phone>
      <div style={{ padding: '12px 18px 8px', flexShrink: 0 }}>
        <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: 1.2, color: 'var(--muted)' }}>НАСТРОЙКИ · БАЗА · ИНФО</div>
        <div style={{ fontFamily: 'var(--serif)', fontSize: 32, color: 'var(--ink)', letterSpacing: -0.4, marginTop: 2 }}>Ещё</div>
      </div>

      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '4px 14px 14px' }}>
        {/* Nightscout connection — status only */}
        <Section title="NIGHTSCOUT">
          <div style={{ padding: '12px 14px', borderBottom: '0.5px solid var(--hairline)' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--ink)' }}>Подключено</div>
                <div style={{ fontSize: 10.5, color: 'var(--muted)', fontFamily: 'var(--mono)', marginTop: 2 }}>последняя синхр. <span style={{ color: 'var(--ink-2)' }}>2 мин назад</span></div>
              </div>
              <span style={{
                width: 8, height: 8, borderRadius: 4, background: 'var(--good)',
              }} />
            </div>
          </div>
          <SetRow label="Синхронизировать сейчас" hint="4 несинхр." chevron={false} action="→" />
          <div style={{ padding: '8px 14px', fontSize: 10.5, color: 'var(--muted)', lineHeight: 1.4, borderTop: '0.5px solid var(--hairline)' }}>
            URL и secret — <span style={{ color: 'var(--ink-2)' }}>в десктоп-версии</span>. Только на чтение.
          </div>
        </Section>

        <Section title="ЦЕЛИ">
          <SetRow label="Калории" value="2200 ккал" mono />
          <SetRow label="Углеводы" value="225 г" mono />
          <SetRow label="Белки · жиры" value="120 · 70 г" mono />
          <SetRow label="TDEE-профиль" value="сидячий + 30 мин" />
          <SetRow label="Целевой диапазон CGM" value="4,0 – 10,0 ммоль/л" mono last />
        </Section>

        <Section title="ВНЕШНИЙ ВИД">
          <SetRow label="Тема" value="Светлая" />
          <SetRow label="Размер шрифта" value="Стандартный" />
          <SetRow label="Моно для всех чисел" toggle on last />
        </Section>

        <Section title="УВЕДОМЛЕНИЯ">
          <SetRow label="Напомнить записать обед" toggle on />
          <SetRow label="Сбой синхр. с Nightscout" toggle on />
          <SetRow label="Низкая уверенность модели" toggle off last />
        </Section>

        <div style={{
          marginTop: 6, padding: '12px 14px',
          background: 'var(--surface)', border: '0.5px dashed var(--hairline-2)', borderRadius: 10,
          fontSize: 11, color: 'var(--muted)', lineHeight: 1.5,
        }}>
          PDF-отчёт эндокринологу, TXT-экспорт, OpenAPI и ссылки бэкенд-токен — <span style={{ color: 'var(--ink-2)' }}>доступно в десктоп-версии</span>.
        </div>

        <div style={{ marginTop: 14, padding: '0 4px', display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ width: 28, height: 28, borderRadius: 14, background: 'var(--ink)', color: '#f6f4ef', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 600 }}>?</div>
          <div>
            <div style={{ fontSize: 12, color: 'var(--ink)', fontWeight: 500 }}>glucotracker</div>
            <div style={{ fontSize: 10, color: 'var(--muted)' }}>v1.0 · мобильный клиент · подключён</div>
          </div>
        </div>
      </div>

      <TabBar active="more" />
    </Phone>
  );
}

function Section({ title, children }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ fontSize: 9, fontWeight: 600, letterSpacing: 1.2, color: 'var(--muted)', padding: '0 6px 6px' }}>{title}</div>
      <div style={{ background: 'var(--surface)', border: '0.5px solid var(--hairline)', borderRadius: 10, overflow: 'hidden' }}>
        {children}
      </div>
    </div>
  );
}

function SetRow({ label, value, hint, mono, last, toggle, on, action, chevron = true }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '11px 14px', gap: 10,
      borderBottom: last ? 'none' : '0.5px solid var(--hairline)',
    }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13, color: 'var(--ink)' }}>{label}</div>
        {hint && <div style={{ fontSize: 10.5, color: 'var(--warn)', marginTop: 2 }}>{hint}</div>}
      </div>
      {toggle && (
        <div style={{
          width: 36, height: 22, borderRadius: 11,
          background: on ? 'var(--ink)' : 'var(--hairline-2)',
          position: 'relative', flexShrink: 0,
        }}>
          <div style={{
            position: 'absolute', top: 2, left: on ? 16 : 2,
            width: 18, height: 18, borderRadius: 9, background: 'white',
            boxShadow: '0 1px 2px rgba(0,0,0,0.2)',
          }} />
        </div>
      )}
      {value && (
        <span style={{
          fontSize: 12, color: 'var(--muted)',
          fontFamily: mono ? 'var(--mono)' : 'var(--sans)',
        }}>{value}</span>
      )}
      {action && (
        <span style={{ fontSize: 13, color: 'var(--ink)', fontWeight: 500 }}>{action}</span>
      )}
      {!toggle && !value && !action && chevron && (
        <svg width="6" height="10" viewBox="0 0 6 10"><path d="M1 1l4 4-4 4" stroke="var(--muted)" strokeWidth="1.4" fill="none" strokeLinecap="round" strokeLinejoin="round"/></svg>
      )}
    </div>
  );
}

// ───────────────────────────────────────────────────────────
// EXTRA · Текстовый ввод (FAB → текст flow)
// ───────────────────────────────────────────────────────────
function ScreenTextInput() {
  return (
    <Phone showHome={false}>
      <div style={{
        padding: '8px 16px 10px', display: 'flex', alignItems: 'center',
        justifyContent: 'space-between', flexShrink: 0,
      }}>
        <button style={iconBtn}>
          <svg width="12" height="12" viewBox="0 0 12 12"><path d="M2 2l8 8M10 2l-8 8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/></svg>
        </button>
        <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: 1, color: 'var(--muted)' }}>ТЕКСТОВЫЙ ВВОД</div>
        <span style={{ width: 28 }} />
      </div>

      {/* Search input */}
      <div style={{ padding: '0 18px 10px', flexShrink: 0 }}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          background: 'var(--surface)', border: '1px solid var(--ink)',
          borderRadius: 10, padding: '12px 14px',
        }}>
          <svg width="14" height="14" viewBox="0 0 14 14" style={{ color: 'var(--muted)' }}>
            <path d="M2 4h10M2 7h10M2 10h6" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
          </svg>
          <span style={{ fontSize: 14, color: 'var(--ink)' }}>воппе</span>
          <span style={{
            width: 1.5, height: 16, background: 'var(--ink)', marginLeft: -2,
            animation: 'caret 1s steps(2) infinite',
          }} />
          <span style={{ flex: 1 }} />
          <span style={{ fontSize: 11, color: 'var(--muted)', fontFamily: 'var(--mono)', letterSpacing: 0.3 }}>4 совпадения</span>
        </div>
        <div style={{ fontSize: 10.5, color: 'var(--muted)', marginTop: 6, padding: '0 4px' }}>
          Команды: <span style={{ fontFamily: 'var(--mono)', color: 'var(--ink-2)' }}>bk:</span> завтрак · <span style={{ fontFamily: 'var(--mono)', color: 'var(--ink-2)' }}>bc:</span> последний
        </div>
      </div>

      {/* Suggestions */}
      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '0 14px' }}>
        <div style={{ fontSize: 9, fontWeight: 600, letterSpacing: 1.2, color: 'var(--muted)', padding: '4px 6px 6px' }}>ЧАСТЫЕ</div>
        <div style={{ background: 'var(--surface)', border: '0.5px solid var(--hairline)', borderRadius: 10, overflow: 'hidden' }}>
          <Suggest name="Воппер" tag="Ресторан · blkwhopper" m="53у 27б 44ж 720к" />
          <Suggest name="Воппер Ролл" tag="Ресторан · blkvopper_roll" m="34у 21б 36ж 540к" highlight />
          <Suggest name="Воппер Джуниор" tag="Ресторан · blkvopper_dzhunior" m="33у 13б 21ж 370к" />
          <Suggest name="Воппер По-итальянски" tag="Ресторан · blkvopper_po_italyanski" m="56у 29б 45ж 750к" />
          <Suggest name="Воппер с Сыром" tag="Ресторан · blkwhopper_cheese" m="54у 31б 50ж 790к" last />
        </div>
      </div>

      {/* Mobile keyboard stub */}
      <FauxKeyboard />
    </Phone>
  );
}

function Suggest({ name, tag, m, highlight, last }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 12,
      padding: '11px 14px',
      background: highlight ? 'var(--bg)' : 'transparent',
      borderBottom: last ? 'none' : '0.5px solid var(--hairline)',
    }}>
      <div style={{ width: 32, height: 32, borderRadius: 5, background: 'linear-gradient(160deg,#d2a87a 0%, #8f6a48 100%)', flexShrink: 0 }} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--ink)' }}>
          <span style={{ background: highlight ? '#f0e6c4' : 'transparent', padding: highlight ? '0 1px' : 0 }}>Воппе</span>
          {name.replace('Воппе', '')}
        </div>
        <div style={{ fontSize: 10, color: 'var(--muted)', fontFamily: 'var(--mono)', marginTop: 2 }}>{tag}</div>
      </div>
      <div style={{ fontSize: 10, fontFamily: 'var(--mono)', color: 'var(--muted)', textAlign: 'right' }}>{m}</div>
    </div>
  );
}

function FauxKeyboard() {
  const rows = [
    ['й','ц','у','к','е','н','г','ш','щ','з','х'],
    ['ф','ы','в','а','п','р','о','л','д','ж','э'],
    ['я','ч','с','м','и','т','ь','б','ю'],
  ];
  return (
    <div style={{
      flexShrink: 0, background: '#d4d4cc', padding: '8px 4px 6px',
    }}>
      {rows.map((r, i) => (
        <div key={i} style={{ display: 'flex', justifyContent: 'center', gap: 4, marginBottom: 6 }}>
          {i === 2 && <div style={{ ...key, width: 32, fontSize: 12 }}>⇧</div>}
          {r.map(k => (
            <div key={k} style={key}>{k}</div>
          ))}
          {i === 2 && <div style={{ ...key, width: 32, fontSize: 14 }}>⌫</div>}
        </div>
      ))}
      <div style={{ display: 'flex', justifyContent: 'center', gap: 4 }}>
        <div style={{ ...key, width: 36, fontSize: 11 }}>123</div>
        <div style={{ ...key, width: 28 }}>🌐</div>
        <div style={{ ...key, flex: 1, maxWidth: 160 }}>пробел</div>
        <div style={{ ...key, width: 50, fontSize: 11, background: 'var(--ink)', color: '#f6f4ef' }}>готово</div>
      </div>
    </div>
  );
}

const key = {
  height: 32, minWidth: 26, borderRadius: 4,
  background: 'white', display: 'flex', alignItems: 'center',
  justifyContent: 'center', fontSize: 14, color: '#1c1b18',
  boxShadow: '0 1px 0 rgba(0,0,0,0.25)',
  flex: 1,
};

// ───────────────────────────────────────────────────────────
// EXTRA · Офлайн outbox (notification banner state on Today)
// ───────────────────────────────────────────────────────────
function ScreenOffline() {
  return (
    <Phone>
      <ScreenHeader kicker="ВТОРНИК · ОФЛАЙН" date="5 мая 2026" />
      {/* Offline banner */}
      <div style={{
        margin: '0 18px 10px', padding: '10px 14px',
        background: '#fdf3e6', border: '0.5px solid #e2c9ad',
        borderRadius: 8, display: 'flex', alignItems: 'center', gap: 10,
        flexShrink: 0,
      }}>
        <svg width="16" height="16" viewBox="0 0 16 16" style={{ color: 'var(--warn)', flexShrink: 0 }}>
          <path d="M2 6L8 1l6 5M3 8v6h10V8M5 14v-3h6v3" stroke="currentColor" strokeWidth="1.3" fill="none" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--ink)' }}>Нет сети</div>
          <div style={{ fontSize: 10.5, color: 'var(--muted)', marginTop: 1 }}>Записи сохраняются локально, отправятся при подключении.</div>
        </div>
        <span style={{ fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--warn)', fontWeight: 500 }}>3</span>
      </div>

      {/* List with sync state icons */}
      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '0 14px 14px' }}>
        <div style={{ background: 'var(--surface)', border: '0.5px solid var(--hairline)', borderRadius: 10, overflow: 'hidden' }}>
          <OutboxRow time="20:08" name="Бисквит-сэндвич ×2" carbs="37.2" kcal="246" thumb="cake" state="sent" />
          <OutboxRow time="13:13" name="Сырные Медальоны + Сметана" carbs="34" kcal="340" thumb="empty" state="sending" />
          <OutboxRow time="13:13" name="Воппер Ролл" carbs="34" kcal="540" thumb="empty" state="queued" />
          <OutboxRow time="07:54" name="Кусочек торта" carbs="44.4" kcal="410" thumb="cake2" state="conflict" last />
        </div>

        <div style={{ marginTop: 12, fontSize: 10.5, color: 'var(--muted)', padding: '0 6px', lineHeight: 1.5 }}>
          <div style={{ fontWeight: 600, color: 'var(--ink-2)', letterSpacing: 1, fontSize: 9, marginBottom: 4 }}>СОСТОЯНИЯ ВЫГРУЗКИ</div>
          ◯ отправляется &nbsp;·&nbsp; ⌃ в очереди &nbsp;·&nbsp; ✓ отправлено &nbsp;·&nbsp; ⚠ конфликт
        </div>
      </div>

      <TabBar active="today" />
    </Phone>
  );
}

function OutboxRow({ time, name, carbs, kcal, thumb, state, last }) {
  const stateUI = {
    sent:    { icon: '✓', color: 'var(--good)', label: 'отпр.' },
    sending: { icon: '◯', color: 'var(--info)', label: 'идёт' },
    queued:  { icon: '⌃', color: 'var(--muted)', label: 'в оч.' },
    conflict:{ icon: '!', color: 'var(--warn)', label: 'конфл.' },
  }[state];
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 10,
      padding: '12px 14px',
      borderBottom: last ? 'none' : '0.5px solid var(--hairline)',
    }}>
      <span style={{ fontFamily: 'var(--mono)', fontSize: 10.5, color: 'var(--ink-2)', width: 36, flexShrink: 0 }}>{time}</span>
      <Thumb kind={thumb} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--ink)' }}>{name}</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 3 }}>
          <span style={{
            width: 14, height: 14, borderRadius: 7,
            background: state === 'sent' ? '#e9f0e0' : state === 'conflict' ? '#fbe9d8' : '#eee9d8',
            color: stateUI.color, fontSize: 9, display: 'flex',
            alignItems: 'center', justifyContent: 'center', fontWeight: 700,
            border: '0.5px solid ' + stateUI.color,
          }}>{stateUI.icon}</span>
          <span style={{ fontSize: 10, color: stateUI.color, fontWeight: 500, letterSpacing: 0.3 }}>{stateUI.label}</span>
        </div>
      </div>
      <div style={{ textAlign: 'right', fontFamily: 'var(--mono)', fontSize: 10.5 }}>
        <div style={{ color: 'var(--ink)' }}>{carbs}<span style={{ color: 'var(--muted)' }}> г угл</span></div>
        <div style={{ color: 'var(--ink)', marginTop: 1 }}>{kcal}<span style={{ color: 'var(--muted)' }}> ккал</span></div>
      </div>
    </div>
  );
}

// ───────────────────────────────────────────────────────────
// Export to window (Babel scope-isolation workaround)
// ───────────────────────────────────────────────────────────
Object.assign(window, {
  ScreenToday, ScreenCaptureSheet, ScreenDraft, ScreenRecord,
  ScreenGlucose, ScreenHistory, ScreenStats, ScreenBase,
  ScreenSettings, ScreenTextInput, ScreenOffline,
  PHONE_W, PHONE_H,
});
