# Lab Stations VM — operations and recovery

Project CMS (DRUS) #2014 "Lab Stations VM". Repo: github.com/wglst/deep-research-mcp, branch `claude-code-backend`.
No secrets in this file: it says where each secret lives.

## The machine
- VM `labserver-stations-ws` on the lab server (libvirt), template AI Workstation v0.6, 2 vCPU / 4 GB / 80 GB.
- Managed by the Lab VPS Server MCP (provider_id `2196d5d7-42c2-456f-b4a6-f46209beacbe`). VM autostart is off: after a lab-server reboot, start it with `lab_sandbox_lifecycle start`.
- Tailscale `labserver-stations-ws` = 100.69.92.42. User `sandbox` (SSH key login; password for console/Cockpit/xrdp kept by Harry).
- Command logs: `~/project/logs/NN-*.txt`.
- An older plain VM `labserver-stations` (192.168.122.178) holds only a baseline install; not used.

## Services (all systemd, all start on boot)
| Unit | What | Listens |
|---|---|---|
| research-station-mcp | Research MCP, tailnet copy, no auth | 100.69.92.42:8080 |
| research-station-mcp-public | Research MCP, PIN OAuth, for claude.ai | 127.0.0.1:8081 |
| research-station-ui | Textual web UI of the research TUI | 100.69.92.42:8000 |
| research-station-watcher | Directus queue watcher (`~/stations/research-queue/watcher.py`) | — |
| stations-directus | Directus 12.6.1 (docker compose in `~/stations/directus`, SQLite) | 100.69.92.42:8055 |
| cloudflared | Cloudflare Tunnel `lab-stations` (id 2ca497cd-3b01-49a9-a020-f2b9951373b6) | out-bound |
| caddy | HTTPS for tailnet names (custom build with caddy-dns/cloudflare) | 100.69.92.42:443 |
| dnsmasq | Split-DNS for *.labserver.artsofweb.com | 100.69.92.42:53 |
| cockpit.socket | Cockpit management page | 127.0.0.1:9090 |

## Names
Tailnet only (Tailscale split DNS `labserver.artsofweb.com` -> 100.69.92.42, set in the Tailscale admin console):
- https://directus.labserver.artsofweb.com — Directus admin
- https://research.labserver.artsofweb.com — research web UI
- https://mcp.labserver.artsofweb.com/mcp — research MCP for tailnet agents
- https://manage.labserver.artsofweb.com — Cockpit

Public (Cloudflare Tunnel, PIN OAuth): https://lab-research.artsofweb.com/mcp — claude.ai connector "Labserver Research MCP".

Claude Code on MBP-14-M5: `lab-research` (http://100.69.92.42:8080/mcp), `lab-directus` (http://100.69.92.42:8055/mcp, bearer token).

## Research backends (`~/.deep_research`)
- default: `codex-cli` — headless Codex CLI on Harry's ChatGPT subscription (login `~/.codex/auth.json`, `codex login --device-auth`).
- `claude`: `claude-code` — headless Claude Code on Harry's Claude subscription (login `~/.claude/.credentials.json`, run `claude` once to sign in).
- Legacy `openai-codex` (undocumented endpoint) still installed; its login is `~/.deep_research_auth.json`.
API-key variables are stripped from both CLI backends, so they never bill API credit.

## Secrets — where they live (never in git)
- Directus admin + KEY/SECRET: `~/stations/directus/.env` (0600)
- Directus worker token (watcher + MCP logging): `~/.stations-directus-token`
- Directus MCP token (lab-directus): `~/.stations-directus-mcp-token`
- Research PIN (public MCP sign-in): `~/.config/research-mcp/pin`
- Cloudflare tunnel cert/credentials: `~/.cloudflared/`
- Cloudflare DNS token (Caddy certificates): `~/.cloudflare-dns-token` and `/etc/caddy/cloudflare.env` (root, 0600)
- GitHub CLI login: `~/.config/gh/hosts.yml`

## Health check
```bash
systemctl is-active research-station-mcp research-station-mcp-public research-station-ui research-station-watcher stations-directus cloudflared caddy dnsmasq cockpit.socket
curl -s https://directus.labserver.artsofweb.com/server/ping
curl -s -o /dev/null -w '%{http_code}\n' https://lab-research.artsofweb.com/.well-known/oauth-protected-resource
```

## Recovery
- One service down: `sudo systemctl restart <unit>`; logs `journalctl -u <unit> -n 50`.
- Directus: `cd ~/stations/directus && docker compose up -d`. Data: `~/stations/directus/database/data.db` (back up this file plus `.env` and `uploads/`).
- Research job stuck in `running`: restarting the watcher puts queue records back to `pending` (MCP-owned records are left alone).
- Subscription login expired: `codex login --device-auth` or `claude` (sign in) as `sandbox`.
- Rebuild from scratch on a new VM (AI Workstation template):
  1. `git clone -b claude-code-backend https://github.com/wglst/deep-research-mcp ~/stations/research && cd ~/stations/research && uv sync`
  2. Copy `stations/systemd/*.service` to `/etc/systemd/system/`; Directus compose from `stations/directus-docker-compose.yml`; Caddyfile and dnsmasq files from `stations/caddy` and `stations/dnsmasq`.
  3. Restore the secrets listed above; log in Codex and Claude; `cloudflared tunnel login` + `cloudflared service install`.
  4. Update the Tailscale IP in the unit files, Caddyfile, dnsmasq and the Tailscale split-DNS entry if it changed.
  5. `sudo systemctl daemon-reload && sudo systemctl enable --now <units>`, then run the health check.
