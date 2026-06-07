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

The backend is expected at
`/media/megusto/storage/glucotracker/project`, with a Python virtualenv at
`/media/megusto/storage/glucotracker/project/venv`, Postgres listening only on
localhost, and photo files under
`/media/megusto/storage/glucotracker/runtime/photos`.
