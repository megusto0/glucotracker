# ADR-027 - Self-hosted backend on Ubuntu desktop

> Replaces ADR-022..026. Hosts the backend on the user's own Ubuntu desktop, reachable via DuckDNS dynamic DNS at `megusto.duckdns.org:1338` (HTTPS) — alongside the existing Nightscout instance at `megusto.duckdns.org:1337` (HTTP). The architecture deliberately accommodates three confirmed ISP constraints: cellular network is whitelisted to VK/Yandex only (no inbound to home IP from mobile), inbound port 80 is blocked (no Let's Encrypt HTTP-01), and Nightscout is HTTP-only.

| | |
| --- | --- |
| Status | Accepted |
| Date | 2026-05-15 |
| Supersedes | ADR-022, ADR-023, ADR-024, ADR-025, ADR-026 |
| Affects | `backend/`, `desktop/`, `android-concept/`, deployment, all client API URLs |
| Risk | Medium — uptime depends on home desktop and home internet; cellular reach is impossible by design (mitigated via offline-first client) |

---

## 1 · Context

The hosted-backend ADRs (022..026) targeted Render + Supabase or Russian cloud
alternatives. Two factors make self-hosting more attractive:

- **Scale**: two users total (project owner + sister). Cloud is overkill.
- **Infrastructure exists**: `megusto.duckdns.org:1337` already serves
  Nightscout from the project owner's Ubuntu desktop with DuckDNS dynamic
  DNS and a working port-forward. The same machine, the same DNS, and the
  same router rules can host the FastAPI backend.

Three operational constraints are confirmed and shape the architecture:

1. **Cellular operator runs a whitelist.** The project owner's mobile
   carrier allows only VK and Yandex services on cellular data. Any
   request to `megusto.duckdns.org` (or to any home-IP-based domain) is
   blocked on cellular. This is not CGNAT — it's content filtering.
2. **Inbound port 80 is blocked by the ISP.** Common on residential plans.
   Let's Encrypt HTTP-01 challenge therefore cannot be used; DNS-01 is
   mandatory.
3. **Nightscout is HTTP-only on `:1337`.** It works from any non-cellular
   network (home Wi-Fi, friend's place, cafes) but is plain HTTP. Reusing
   the same pattern for Glucotracker is inadequate because Glucotracker
   handles medical data over public networks; HTTPS is required.

For a single-developer, two-user project these constraints are acceptable.
Cloud migration remains a future option if the project grows. This ADR
consolidates the parts of ADR-022..026 that still apply (SQL portability,
sanitized logging, smoke tests, degraded-mode UX) and drops the cloud-
specific parts (Supabase pgbouncer, Render free-tier sleep, multi-instance
worker guardrails).

## 2 · Architecture

```
[Android / Tauri clients]                  (public internet, Wi-Fi only)
        │
        │ HTTPS over port 1338
        ▼
megusto.duckdns.org:1338
        │
        │ DuckDNS dynamic DNS → home IP
        │ Router port forward: 1338 → 192.168.x.y:1338 (desktop LAN IP)
        ▼
┌─────────────────────────────────────────────────┐
│ Ubuntu Desktop (megusto)                        │
│                                                 │
│  Caddy (listens on :1338 only — no :80)         │
│   ├─ TLS via Let's Encrypt DNS-01 (DuckDNS)     │
│   └─ reverse proxy → 127.0.0.1:8000             │
│            │                                    │
│            ▼                                    │
│  FastAPI / uvicorn (127.0.0.1:8000)             │
│   ├─ systemd: glucotracker-web.service          │
│   └─ separate process: glucotracker-worker      │
│            │                                    │
│   ┌────────┴───────┬─────────────────┐          │
│   ▼                ▼                 ▼          │
│  PostgreSQL    storage/glucotracker/runtime/    │
│  (localhost)   (filesystem)                     │
│                                                 │
│  Glucotracker backend reaches Nightscout via    │
│  http://127.0.0.1:1337 (internal loopback)      │
│                                                 │
│  Nightscout (untouched, public :1337 HTTP)      │
└─────────────────────────────────────────────────┘
```

One host, four systemd services (Caddy, Postgres, glucotracker-web,
glucotracker-worker). Nightscout continues to run unchanged on its own
public port. Backend talks to Nightscout via loopback so the HTTP-vs-HTTPS
asymmetry is irrelevant for backend↔Nightscout traffic; only client traffic
crosses the public internet and is always HTTPS.

## 3 · Prerequisites (verify BEFORE setup)

### 3.1 — Confirm public reachability from non-cellular Wi-Fi

The existing Nightscout setup proves the public path works:

1. From a Wi-Fi network that is **not** the home Wi-Fi (cafe, friend's
   place, mobile hotspot from a different carrier if available), open
   `http://megusto.duckdns.org:1337`. Should load Nightscout.
2. If it loads: DNS + port forward + ISP allow inbound for :1337. The
   pattern extends to :1338.
3. If it doesn't load: investigate before continuing — likely a router or
   ISP issue.

Note: testing from cellular is pointless because the whitelist blocks
everything. Use only Wi-Fi networks for connectivity checks.

### 3.2 — Confirm port 80 stays blocked (informational)

You don't need to fix this — DNS-01 challenge avoids :80 entirely. But
confirm so you don't waste time trying HTTP-01:

```bash
# From a network outside the home (or use an online port checker)
curl -v http://megusto.duckdns.org:80
# Expected: connection refused or timeout after a few seconds
```

If it works (unusual): port 80 is open and HTTP-01 would work too. Use
either approach. If it times out: stick with DNS-01 (the path this ADR
spec'd).

### 3.3 — DuckDNS API token

Log into the DuckDNS account at https://www.duckdns.org. The token is on
the account page, shown above the domains list. Copy it; you'll need it
for Caddy's DNS-01 challenge.

If you can't find it, regenerate (button on the page). Regenerating
invalidates the current token — update wherever else you use it
(probably the IP-update script for Nightscout uses it too).

### 3.4 — Desktop power policy

Verify the desktop doesn't sleep when idle:

```bash
sudo systemctl status sleep.target suspend.target hibernate.target
# All should be 'masked' or 'inactive'

# Permanently disable sleep:
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
```

The desktop must stay running for the backend to be reachable. Plan
reboot windows for OS updates.

## 4 · Network setup

### 4.1 — DuckDNS

Already working for Nightscout. The IP-update script runs as a cron job
or systemd timer:

```bash
# /usr/local/bin/duckdns-update.sh (already exists)
echo url="https://www.duckdns.org/update?domains=megusto&token=YOUR_TOKEN&ip=" \
  | curl -k -o ~/duckdns.log -K -
```

```bash
# crontab -e
*/5 * * * * /usr/local/bin/duckdns-update.sh > /dev/null 2>&1
```

No new DNS work for Glucotracker — `megusto.duckdns.org` already resolves
to the home IP.

### 4.2 — Router port forwarding

Add one new rule alongside the existing Nightscout forward:

| External port | Internal target | Protocol | Service |
| --- | --- | --- | --- |
| 1337 (existing) | desktop:1337 | TCP | Nightscout (HTTP) |
| **1338 (new)** | desktop:1338 | TCP | Caddy → Glucotracker (HTTPS) |

**Port 80 is NOT forwarded.** ISP blocks it, and DNS-01 challenge doesn't
need it. This is an explicit choice — by not forwarding :80 we avoid any
attempt by Caddy to use HTTP-01 and the resulting fallback ceremony.

Reserve a **static LAN IP** for the desktop in router DHCP settings so
forwards don't break after DHCP renewal.

### 4.3 — Custom Caddy with DuckDNS plugin

Standard Caddy doesn't include the DuckDNS DNS-01 plugin. Two ways to
install:

**Option A (recommended) — pre-built binary from Caddy's download page**:

1. Visit https://caddyserver.com/download
2. Select "linux" / "amd64" (or your architecture).
3. In the "modules" search, add `github.com/caddy-dns/duckdns`.
4. Click "Download" — you get a binary with that plugin built in.
5. Install:
   ```bash
   sudo systemctl stop caddy
   sudo mv ~/Downloads/caddy /usr/bin/caddy
   sudo chmod +x /usr/bin/caddy
   sudo systemctl start caddy
   caddy version  # verify
   ```

**Option B — xcaddy build from source** (if you prefer):

```bash
sudo apt install golang-go
go install github.com/caddyserver/xcaddy/cmd/xcaddy@latest
~/go/bin/xcaddy build --with github.com/caddy-dns/duckdns
sudo mv caddy /usr/bin/caddy
```

Either way ends up with a Caddy binary that knows how to do DNS-01 via
DuckDNS API.

### 4.4 — Caddyfile

`/etc/caddy/Caddyfile`:

```caddy
{
    # Global options
    email your-email@example.com  # Let's Encrypt account
}

megusto.duckdns.org:1338 {
    tls {
        dns duckdns {env.DUCKDNS_TOKEN}
        propagation_delay 30s
    }

    reverse_proxy 127.0.0.1:8000

    # Match PHOTO_MAX_SIZE_BYTES (12 MB) plus headers margin
    request_body {
        max_size 14MB
    }

    log {
        output file /var/log/caddy/glucotracker-access.log
        format json
    }
}
```

Provide the DuckDNS token to Caddy via systemd override:

```bash
sudo systemctl edit caddy
```

Add:

```ini
[Service]
Environment="DUCKDNS_TOKEN=your-duckdns-token-here"
```

`propagation_delay 30s` gives DuckDNS time to publish the TXT record
before Let's Encrypt validates. Without it, validation can be flaky.

Restart and watch:

```bash
sudo systemctl restart caddy
sudo journalctl -u caddy -f
```

Look for:
```
INFO    tls.obtain  certificate obtained successfully
```

If validation fails, sanity-check the DuckDNS token:

```bash
curl "https://www.duckdns.org/update?domains=megusto&token=YOUR_TOKEN&txt=test123"
# Should print "OK"
dig +short TXT _acme-challenge.megusto.duckdns.org
# Should show test123 after 30-60s
```

If that's clean but Caddy still fails, raise `propagation_delay` to 60s
or 90s.

### 4.5 — Renewal

Caddy auto-renews 30 days before expiry using the same DNS-01 flow.
Nothing else to configure. No port 80 ever opened.

## 5 · Database setup (PostgreSQL)

### 5.1 — Install and create database

```bash
sudo apt install postgresql postgresql-contrib
sudo -u postgres psql <<EOF
CREATE USER glucotracker WITH PASSWORD 'CHANGE_THIS_PASSWORD';
CREATE DATABASE glucotracker_prod OWNER glucotracker;
GRANT ALL PRIVILEGES ON DATABASE glucotracker_prod TO glucotracker;
EOF
```

### 5.2 — Local-only binding

Edit `/etc/postgresql/16/main/postgresql.conf` (current version path may
differ):

```
listen_addresses = 'localhost'    # NOT '*'
```

Edit `/etc/postgresql/16/main/pg_hba.conf` to keep Postgres reachable only
from localhost:

```
local   all   all                  peer
host    all   all   127.0.0.1/32   scram-sha-256
host    all   all   ::1/128        scram-sha-256
# no other host entries
```

Restart:

```bash
sudo systemctl restart postgresql
```

### 5.3 — SQL portability rules (carried from old ADR-023)

Development uses SQLite per `docs/architecture.md`; production now uses
Postgres. Same portability constraints.

Forbidden patterns in application code, ORM expressions, and Alembic
migrations:

| Forbidden | Use instead |
| --- | --- |
| `JSON_EXTRACT(col, '$.key')` (SQLite) or `col->>'key'` (Postgres) in raw SQL | SQLAlchemy `col['key'].as_string()` or `sqlalchemy.JSON` typed columns |
| `DATETIME('now')` | `sqlalchemy.func.now()` |
| `INSERT OR REPLACE` | `INSERT ... ON CONFLICT ... DO UPDATE` via ORM merge |
| `AUTOINCREMENT` / `SERIAL` in DDL | `sa.Integer` PK with `autoincrement=True` |
| Booleans as `INTEGER 0/1` | `sa.Boolean` everywhere |
| `STRFTIME('%Y-%m-%d', ts)` | `sa.func.date(ts)` |

Alembic rules:

1. No `op.drop_column` without `batch_alter_table` (SQLite compatibility).
2. No `ALTER COLUMN TYPE` without explicit `USING` for Postgres.
3. No `CREATE INDEX CONCURRENTLY` (Postgres-only, breaks SQLite).
4. Type changes forward-only: add new column → backfill → switch reads →
   drop old column in a follow-up migration after one verified deploy.

Timezone: absolute timestamps `sa.DateTime(timezone=True)` → `TIMESTAMPTZ` in
Postgres. User-entered wall-clock fields (`meals.eaten_at`,
`photos.taken_at`, `meal_audit_events.eaten_at`) are explicit exceptions:
they use `timestamp without time zone` so a Tauri `datetime-local` value like
`2026-05-16T20:10:00` round-trips as 20:10 and is never shifted through UTC.
Application code never `datetime.now()` for absolute timestamps — always
`datetime.now(timezone.utc)`. `GLUCOTRACKER_APP_TIMEZONE` governs conversion
from timezone-aware client values into local wall-clock values.

### 5.4 — Connection pool

Simple for single-instance home host — no Supabase pgbouncer concerns:

```python
engine = create_engine(
    "postgresql+psycopg://glucotracker:pass@localhost:5432/glucotracker_prod",
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=3600,
    connect_args={"options": "-c timezone=utc"},
)
```

### 5.5 — Testing

| Job | Database | Purpose |
| --- | --- | --- |
| `test-sqlite` | SQLite | Application logic |
| `test-postgres` | Local Postgres (Docker or native) | Postgres-specific SQL, timezone, constraint behavior |
| `test-migrations-fresh` | Both | `alembic upgrade head` from scratch |

Both must pass before merging any SQL-touching code.

## 6 · Photo storage (filesystem, single host)

### 6.1 — Storage location

```bash
sudo mkdir -p /media/megusto/storage/glucotracker/runtime/photos
sudo chown -R glucotracker:glucotracker \
  /media/megusto/storage/glucotracker/runtime
sudo chmod 700 /media/megusto/storage/glucotracker/runtime/photos
```

The `glucotracker` system user (created in §7.1) is the only one with
read/write access. Photos stored as `{user_id}/{photo_id}.jpg` under
that root.

### 6.2 — `PhotoStorage` adapter

The adapter abstraction from old ADR-024 remains useful (clean swap path
if you ever migrate off the desktop):

```python
class PhotoStorage(Protocol):
    def save_upload(self, file_stream, content_type: str) -> StorageKey: ...
    def open_for_read(self, key: StorageKey) -> tuple[BinaryIO, StorageMetadata]: ...
    def delete(self, key: StorageKey) -> None: ...
    def exists(self, key: StorageKey) -> bool: ...
```

Only `FilesystemPhotoStorage` is needed for production now.

### 6.3 — Streaming requirements

Streaming is mandatory even with desktop RAM headroom (a 12 MB upload from
each user concurrently still spikes a synchronous process). Spec from
old ADR-024 §Streaming:

- 64 KB chunks for save and read paths.
- `PHOTO_MAX_SIZE_BYTES` cap (default 12 MB), rejected at first crossing
  chunk.
- `/photos/{photo_id}/file` returns `StreamingResponse`.

### 6.4 — Retention and deletion

Same as old ADR-024 §Retention. When a meal/photo is deleted:

- Hard delete the DB row.
- Tombstone the file: rename to `{photo_id}.jpg.deleted` with mtime stamp.
- Daily worker deletes files matching `*.deleted` older than 30 days.

Tombstoning protects against accidental deletion or DB rollback.

### 6.5 — Error taxonomy

```python
class StorageError(Exception): ...
class StorageNotFoundError(StorageError): ...
class StorageIOError(StorageError): ...  # disk full, I/O error, permission
```

For filesystem, `StorageAuthError` and `StorageQuotaError` collapse into
`StorageIOError` plus operator alert.

## 7 · systemd services

### 7.1 — Service user

```bash
sudo useradd --system --no-create-home --shell /usr/sbin/nologin glucotracker
```

### 7.2 — Web service

`/etc/systemd/system/glucotracker-web.service`:

```ini
[Unit]
Description=Glucotracker FastAPI backend
After=network.target postgresql.service
Wants=postgresql.service
RequiresMountsFor=/media/megusto/storage/glucotracker

[Service]
Type=simple
User=glucotracker
Group=glucotracker
WorkingDirectory=/media/megusto/storage/glucotracker/project/backend
Environment="PATH=/media/megusto/storage/glucotracker/project/venv/bin"
EnvironmentFile=/media/megusto/storage/glucotracker/config/env
ExecStartPre=/media/megusto/storage/glucotracker/project/venv/bin/python -m alembic upgrade head
ExecStart=/media/megusto/storage/glucotracker/project/venv/bin/python -m uvicorn glucotracker.main:app \
    --host 127.0.0.1 --port 8000 --workers 2
Restart=always
RestartSec=10s

# Resource limits
MemoryMax=1G
TasksMax=200

# Security
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/media/megusto/storage/glucotracker/runtime /media/megusto/storage/glucotracker/logs

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=glucotracker-web

[Install]
WantedBy=multi-user.target
```

### 7.3 — Worker service

`/etc/systemd/system/glucotracker-worker.service`: same pattern,
`ExecStart` runs the worker entry point (Nightscout import via loopback,
photo tombstone cleanup, daily totals refresh, reconciliation).

```ini
ExecStart=/media/megusto/storage/glucotracker/project/venv/bin/python -m glucotracker.workers
```

### 7.4 — Environment file

`/media/megusto/storage/glucotracker/config/env` (mode 640, owned by
`root:glucotracker`):

```bash
GLUCOTRACKER_DATABASE_URL=postgresql+psycopg://glucotracker:PASS@localhost:5432/glucotracker_prod
GLUCOTRACKER_JWT_SECRET=GENERATE_WITH_OPENSSL_RAND
GLUCOTRACKER_APP_TIMEZONE=Europe/Moscow
GEMINI_API_KEY=...
GEMINI_MODEL_PHOTO=gemini-2.0-flash-exp
STORAGE_BACKEND=filesystem
PHOTO_STORAGE_DIR=/media/megusto/storage/glucotracker/runtime/photos
ACTIVITY_LOG_DIR=/media/megusto/storage/glucotracker/runtime/activity_logs
PHOTO_MAX_SIZE_BYTES=12582912
LOG_LEVEL=INFO
NIGHTSCOUT_BASE_URL=http://127.0.0.1:1337
NIGHTSCOUT_API_SECRET=...
NIGHTSCOUT_IMPORT_INTERVAL_SECONDS=300
```

Note `NIGHTSCOUT_BASE_URL=http://127.0.0.1:1337` — the backend reaches
Nightscout over loopback, not over the public domain. Internal HTTP is
fine.

### 7.5 — Enable on boot

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now glucotracker-web.service
sudo systemctl enable --now glucotracker-worker.service
```

Verify:

```bash
sudo systemctl status glucotracker-web
journalctl -u glucotracker-web -n 50 -f
curl http://127.0.0.1:8000/health
curl https://megusto.duckdns.org:1338/health
```

### 7.6 — Health checks and watchdog

`/health` returns 200 in <500ms, no DB query. systemd doesn't auto-check
HTTP, so add a small watchdog:

```bash
# /usr/local/bin/glucotracker-watchdog.sh
#!/bin/bash
if ! curl -sf http://127.0.0.1:8000/health > /dev/null; then
  systemctl restart glucotracker-web
  echo "$(date) - restarted glucotracker-web" >> /var/log/glucotracker-watchdog.log
fi
```

Cron every 2 minutes. Optionally add Telegram alert in the same script.

## 8 · Logging hygiene (carried from old ADR-025)

Logs go to journald via systemd, accessible with `journalctl -u glucotracker-*`.

Forbidden in logs:

- Photo bytes (raw or base64)
- Nightscout secrets, API keys, JWTs, refresh tokens
- Gemini API keys
- Database connection URLs (password leak)
- DuckDNS API token
- Email addresses in error messages
- Full request bodies for `POST /photos/*`

`safe_repr` helper and CI grep enforce this:

```python
def safe_repr(obj: Any) -> str:
    if isinstance(obj, bytes):
        return f"<{len(obj)} bytes>"
    if isinstance(obj, str) and (
        "Bearer " in obj or "@" in obj or len(obj) > 200
    ):
        return f"<redacted len={len(obj)}>"
    return repr(obj)[:200]
```

Structured logging with request IDs returned to clients in `X-Request-ID`
header.

## 9 · Backup strategy

### 9.1 — What needs backup

- PostgreSQL database (users, meals, photos metadata).
- Photo files in `/media/megusto/storage/glucotracker/runtime/photos/`.
- App config in `/media/megusto/storage/glucotracker/config/`.
- Caddy config in `/etc/caddy/Caddyfile` (and the DuckDNS token override).

### 9.2 — Local daily backup

`/etc/cron.daily/glucotracker-backup`:

```bash
#!/bin/bash
set -e
BACKUP_DIR=/media/megusto/storage/glucotracker/backups
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"

sudo -u postgres pg_dump glucotracker_prod \
  | gzip > "$BACKUP_DIR/db_${TIMESTAMP}.sql.gz"

tar czf "$BACKUP_DIR/photos_${TIMESTAMP}.tar.gz" \
  -C /media/megusto/storage/glucotracker/runtime photos

# Retain 7 days
find "$BACKUP_DIR" -name "db_*.sql.gz" -mtime +7 -delete
find "$BACKUP_DIR" -name "photos_*.tar.gz" -mtime +7 -delete
```

### 9.3 — Off-site copy

Local backup alone isn't enough — if the desktop dies, both data and
backups are gone. Pick one:

- **External USB drive**: weekly `rsync` to a USB drive stored elsewhere.
- **Yandex Disk**: free 10 GB usually covers a year for two users.
  Encrypt the dump with `gpg --symmetric` before upload.
- **Second machine** (laptop, NAS, friend's home server): `rsync` over
  SSH.

Yandex Disk is the easiest given the carrier whitelist (Yandex is
allowed on cellular, so off-site retrieval works from anywhere).

### 9.4 — Restore drill

Quarterly: restore the latest backup into a separate test database,
verify it boots.

```bash
sudo -u postgres createdb glucotracker_restore_test
gunzip -c db_LATEST.sql.gz | sudo -u postgres psql glucotracker_restore_test
sudo -u postgres psql glucotracker_restore_test -c "SELECT COUNT(*) FROM meals"
sudo -u postgres dropdb glucotracker_restore_test
```

Catches "I had backups but they're corrupt" surprises.

## 10 · Client configuration

### 10.1 — API base URL per build

| Client build | API base URL |
| --- | --- |
| Debug / local dev | `http://127.0.0.1:8000` |
| Release | `https://megusto.duckdns.org:1338` |

Mobile clients ship release URL hardcoded; debug builds read from
`BuildConfig.API_BASE_URL`. Tauri reads from env at startup.

### 10.2 — Network access matrix

Realistic reachability per network type:

| Where | Network | Glucotracker | Nightscout | Notes |
| --- | --- | --- | --- | --- |
| Home | Home Wi-Fi | ✓ | ✓ | Both services local |
| Sister's home | Her Wi-Fi | ✓ | ✓ | Public internet, HTTPS for gluco |
| Work / cafe | Public Wi-Fi | ✓ | ✓ | HTTPS for gluco protects on hostile networks |
| On the go | Cellular (carrier whitelist) | **✗** | **✗** | Operator blocks anything not VK/Yandex |
| On the go | Cellular + VPN | **conditional** | **conditional** | See §13.1 (Tailscale) |

Cellular is unreachable by design — this is acknowledged, not a defect to
fix.

### 10.3 — Degraded-mode UX

The client distinguishes these states for user-visible copy:

| State | Cause | Client UX |
| --- | --- | --- |
| Online | Wi-Fi, backend reachable | Normal |
| Offline | No network at all | Banner «нет сети» |
| Backend unreachable on Wi-Fi | Desktop off, home internet down, ISP routing problem | Banner «домашний сервер недоступен», retry per ADR-013 |
| Cellular-blocked | On cellular, can reach VK/Yandex but not home | Banner «домашний сервер недоступен с мобильной сети — нужен Wi-Fi» |
| Backend slow | Request taking >5s | "обрабатывается..." indicator, wait up to 60s |

Detecting "cellular-blocked" specifically:

```kotlin
suspend fun isCellularBlocked(): Boolean {
  val canReachYandex = pingHost("https://yandex.ru/favicon.ico")
  val canReachBackend = pingHost("https://megusto.duckdns.org:1338/health")
  return canReachYandex && !canReachBackend
}
```

If yes, show the specific cellular copy. Otherwise generic. Detection can
be deferred — generic copy works for v1; add the cellular-aware variant
later if the sister gets confused.

### 10.4 — Outbox visibility

When on cellular (or any unreachable state), the outbox row shows
`ждёт Wi-Fi` per ADR-013 vocabulary, slotting in alongside existing
`ждёт сети` and `пробует сейчас`. The copy distinction matters:

- «ждёт сети» — any network may help, retry will trigger automatically.
- «ждёт Wi-Fi» — won't help to wait on cellular, user must switch
  networks.

### 10.5 — Outbox behavior unchanged

ADR-001..006, ADR-011, ADR-013 unchanged. Photos and edits queue when
the backend is unreachable; sync when reachable.

## 11 · Cutover plan

### Phase 1 — Local setup (no clients affected)

1. Install Postgres, custom Caddy (§4.3), Python venv (§5, §7).
2. Deploy Glucotracker code to `/media/megusto/storage/glucotracker/project`.
3. Configure env file `/media/megusto/storage/glucotracker/config/env`.
4. Create systemd units, enable, start.
5. Verify: `curl http://127.0.0.1:8000/health` returns 200.

### Phase 2 — Public exposure

1. Add router port-forward for 1338.
2. Set Caddy with DNS-01 (Caddyfile + DUCKDNS_TOKEN env).
3. Verify TLS issued (`journalctl -u caddy`).
4. From a non-home Wi-Fi network: `curl https://megusto.duckdns.org:1338/health`
   returns 200 with valid Let's Encrypt cert.

### Phase 3 — Smoke tests

Run from **non-home Wi-Fi** (cafe, friend's place, mobile hotspot from a
different carrier if you can borrow one). Skip cellular — known blocked
by the whitelist.

Same smoke test list as old ADR-026 §Smoke tests:

- Auth: login/refresh
- Capture (online and offline → outbox → sync when back on Wi-Fi)
- Reads: Today, History, card stack
- Nightscout (gluco): glucose, insulin
- Reports (gluco): endo PDF
- Multi-user isolation: A's data invisible to B
- Performance: warm request <2s, 5 MB photo upload <30s
- Degraded UX: kill Wi-Fi mid-capture, verify outbox queues correctly

### Phase 4 — Client release

1. Update debug builds: `API_BASE_URL = "https://megusto.duckdns.org:1338"`.
2. Self-test on own phone for 48 h (home + at least one other Wi-Fi).
3. Sister-test on her device for 48 h.
4. Release production builds with the same URL.

### Phase 5 — Operations

- Watchdog cron (§7.6) running.
- Daily backups (§9.2) running.
- Weekly off-site sync (§9.3) running.
- Monthly restore drill (§9.4).
- Reboot for OS updates: announce in family chat, do it in <10 min window.

## 12 · Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Desktop power off / hardware failure | Daily backups + off-site copy. UPS for routine power flickers (§13.4). |
| Home internet outage | Same as power off from client side — outbox queues per ADR-013. |
| ISP changes routing / introduces CGNAT | Re-test §3.1 quarterly. Cloud migration ADRs (022..026) remain drafted, can be revived. |
| ISP closes port 1338 | Unlikely — non-standard ports are usually left alone. If it happens, pick another high port and update Caddy + router. |
| DuckDNS service down | Historically reliable. If it goes flaky, point at Cloudflare with dynamic-update script (more setup, more flexibility). |
| DuckDNS token leaks | Token gives full control over the domain. Stored in systemd override file (mode 600 root) and in the IP-update script. Don't log it (§8). Regenerate if compromised. |
| Disk fills up | Monitor in cron, alert when <10% free. Photo growth bounded by retention policy. |
| Backup is silently broken | Quarterly restore drill (§9.4). |
| Cellular ever becomes critical for either user | §13.1 (Tailscale) or fall back to cloud (ADR-022..026). |
| Carrier whitelist gets stricter | Already at minimum (VK + Yandex only). Can't get worse without breaking actual phone calls. |
| JWT secret leak | Mode-600 file, owned by root, readable only when service starts. Same approach as Nightscout. |

## 13 · What's deferred

These were spec'd in old ADR-022..026 but don't apply here:

- Multi-instance worker guardrails (one process).
- Supabase pgbouncer connection modes (direct local connection).
- Free-tier cold-start UX (desktop doesn't sleep).
- Storage migration playbook (fresh start, filesystem only).
- Canary cutover phase (two users; self-test 48 h is the canary).

If the project later grows beyond two users or moves to cloud, those
sections can be revived from the superseded ADRs.

## 14 · Acceptance criteria

- `https://megusto.duckdns.org:1338/health` returns 200 from any
  non-home Wi-Fi network with a valid Let's Encrypt cert.
- Both clients (own phone, sister's phone) successfully capture, sync,
  and read meals against the URL while on Wi-Fi.
- Capture while offline (Wi-Fi off or cellular only) queues in outbox
  per ADR-013 and syncs cleanly on next Wi-Fi connection.
- Photos uploaded survive a desktop reboot.
- `journalctl -u glucotracker-*` contains no entries matching §8
  forbidden patterns.
- Daily backup cron produces both DB and photo archives.
- Off-site backup mirror is non-empty and recent (verified manually).
- One restore drill has been performed and documented.
- Watchdog cron has fired at least once in test (kill the service
  manually, verify it's back within 2 min).
- Caddy cert auto-renews at least once observed in logs before the
  90-day expiration of the initial cert.

## 15 · Out-of-band asks

### 15.1 — Tailscale for cellular access

If cellular unreachability becomes painful (project owner wants to read
History on the go, sister wants to log meals at work on cellular), set
up **Tailscale**:

1. Install Tailscale on the desktop, own phone, sister's phone.
2. All three join the same tailnet.
3. Glucotracker reachable via the desktop's tailnet IP (e.g.,
   `https://100.x.y.z:1338`) from any device in the tailnet, regardless
   of the carrier whitelist.

How this might bypass the whitelist:

- Tailscale uses UDP to talk to DERP relays on Cloudflare-hosted
  infrastructure. The carrier sees only UDP to Cloudflare, not to the
  home IP.
- **However**: a whitelist this aggressive ("only VK and Yandex") may
  also block UDP, Cloudflare, or anything else. Test with the free plan
  first.

Worst case: Tailscale doesn't work either, and cellular access stays
impossible. Acceptable — no regression, just no improvement.

### 15.2 — UPS for the desktop

400–600 VA basic UPS (~3–5 k ₽) buys 20–40 min runtime, riding out brief
power outages and giving time for graceful shutdown on longer ones.
Worth it if the area has unstable power.

### 15.3 — WireGuard self-hosted as Tailscale alternative

If Tailscale's free tier feels constraining or you want full control:
WireGuard server on the same desktop, phones as clients. Same effect
without third-party infrastructure. More setup; same potential
whitelist-blocked outcome.

### 15.4 — Path-based routing on a single port

Currently spec'd: Glucotracker on `:1338`, Nightscout on `:1337`, two
ports. Alternative: route both through Caddy on `:443` with path-based
routing (`/api/* → Glucotracker`, `/nightscout/* → Nightscout`). Cleaner
mobile URLs but requires reconfiguring Nightscout's mount path and may
expose `:443` to the same ISP-block concern as `:80`. Default: keep
separate ports.

### 15.5 — Gemini API costs

Even self-hosted, photo estimation still hits Google Gemini per ADR-005.
For two users, the free tier likely covers it. Monitor usage in Google
Cloud console; switch to paid (~$0.075 per 1M input tokens for Flash) if
needed. **Note**: Google Gemini endpoints aren't on the cellular
whitelist either, but this traffic originates from the desktop, not from
phones, so the whitelist doesn't apply.

### 15.6 — Wake-on-LAN for remote reboot

If the desktop hangs and the project owner is away from home, no
recovery path until physically present. WoL + a small always-on box
(Raspberry Pi, an old router with custom firmware) could send the WoL
magic packet. Probably overkill for this scale.
