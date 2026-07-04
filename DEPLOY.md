# Deploy To Vietnam Server

Current server:

```bash
ssh -i ~/Desktop/sshs/vietnam-proxy root@160.30.54.188
```

Existing services observed on the server:

- `gemini-proxy.service`: `/home/ubuntu/gemini-proxy/gemini-proxy`
- `rieltor.service`: `/opt/rieltor/server.js`
- `nginx.service`: `podzemnykrot.xyz` currently proxies to AI Realtor on `127.0.0.1:3001`

Do not touch Gemini proxy. The Twilight Zone MVP uses Telegram long polling, so it does not need nginx or the `podzemnykrot.xyz` domain yet.

## First Deploy

After creating the GitHub repo and pushing this project:

```bash
ssh -i ~/Desktop/sshs/vietnam-proxy root@160.30.54.188
cd /opt
git clone GITHUB_REPO_URL twilight-zone
cd /opt/twilight-zone
python3 -m venv .venv
.venv/bin/pip install -e .
cp deploy/env.production.example .env
nano .env
.venv/bin/twilight-zone init-db
cp deploy/twilight-zone.service /etc/systemd/system/twilight-zone.service
systemctl daemon-reload
systemctl enable --now twilight-zone.service
systemctl status twilight-zone.service --no-pager
```

Logs:

```bash
journalctl -u twilight-zone.service -f
```

Manual smoke test:

```bash
cd /opt/twilight-zone
.venv/bin/twilight-zone search-once
.venv/bin/twilight-zone deliver-once
```

## Domain

No domain is required while Telegram uses long polling.

Use `podzemnykrot.xyz` later only if we add:

- Telegram webhook
- small admin/status page
- public landing/debug endpoint

If that happens, migrate or stop `rieltor.service`, then point nginx at the new app. Until then, leave AI Realtor and nginx alone.
