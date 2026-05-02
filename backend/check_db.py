import sqlite3
conn = sqlite3.connect("data/glucotracker.sqlite3")
tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print("Tables:", tables)
for t in tables:
    count = conn.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
    print(f"  {t}: {count} rows")
if "daily_activity" in tables:
    rows = conn.execute("SELECT date, steps, kcal_burned, heart_rate_avg, heart_rate_rest, hr_samples, hr_active_minutes, kcal_hr_active, kcal_steps, kcal_no_move_hr, calorie_confidence FROM daily_activity ORDER BY date DESC LIMIT 10").fetchall()
    for r in rows:
        print(f"  {r}")
if "user_profile" in tables:
    rows = conn.execute("SELECT * FROM user_profile").fetchall()
    for r in rows:
        print(f"  profile: {r}")
conn.close()
