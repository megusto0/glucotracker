# Ubuntu Self-Hosted Deployment

Repo-owned deployment assets for ADR-027. These files are templates; install them
on the Ubuntu desktop under the paths shown below and keep secrets out of Git.

## Files

- `caddy/Caddyfile` -> `/etc/caddy/Caddyfile`
- `systemd/glucotracker-web.service` -> `/etc/systemd/system/glucotracker-web.service`
- `systemd/glucotracker-worker.service` -> `/etc/systemd/system/glucotracker-worker.service`
- `env.example` -> `/media/megusto/storage/glucotracker/config/env` after
  replacing placeholders
- `cron/glucotracker-backup` -> `/etc/cron.daily/glucotracker-backup`
- `bin/glucotracker-watchdog.sh` -> `/usr/local/bin/glucotracker-watchdog.sh`

The Caddy DuckDNS token belongs in a systemd override for the `caddy` service:

```ini
[Service]
Environment="DUCKDNS_TOKEN=replace-with-token"
```

Fridge admin Basic auth stays on `/fridge*`, `/inventory*`, `/meal-prep*`,
`/receipts*`, `/containers*`, `/container-types*` and `/media*`. The bcrypt
hash is inlined in the live `/etc/caddy/Caddyfile` (a `$2a$…` value cannot
live in systemd `Environment=`). `/products*` must **not** be in that
matcher: the Android app calls `GET /products` with Bearer, and Caddy Basic
would reject it before GlucoTracker sees the token.

The backend is expected at
`/media/megusto/storage/glucotracker/project`, with a Python virtualenv at
`/media/megusto/storage/glucotracker/project/venv`, Postgres listening only on
localhost, and photo files under
`/media/megusto/storage/glucotracker/runtime/photos`.

## Hermes Codex authorization

Install `systemd/glucotracker-hermes-auth-sync.service` and `.timer` in
`/etc/systemd/system/`, then run:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now glucotracker-hermes-auth-sync.timer
sudo systemctl start glucotracker-hermes-auth-sync.service
```

The service runs as the Hermes owner (`megusto`) with the backend group
(`glucotracker`). Every minute, and after boot, it calls Hermes's own
`resolve_codex_runtime_credentials`, which refreshes expiring tokens under the
canonical auth-store lock. The service publishes only the current access token
to `runtime/hermes-auth.json` using atomic replacement and mode `0640`.
Refresh tokens and other provider credentials stay in Hermes's private store.
The backend rereads this file for each estimate, so rotation needs no restart.
The runtime directory must be writable by `megusto` (the deployed directory
already has that ACL). Adjust the Hermes installation paths, user and local
proxy in the unit when installing on another host.

Inspect failures with `journalctl -u glucotracker-hermes-auth-sync.service`.
A failed renewal retains the previous published copy and retries at the next
timer tick. If Hermes reports a revoked renewable session, sign in again in
Hermes; the next tick publishes the new access token.
