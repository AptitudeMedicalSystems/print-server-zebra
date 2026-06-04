# CLAUDE.md

## Project Overview

`print-server-zebra` — Standalone LAN HTTP print server for Zebra ZD411 (USB on Pi).
FastAPI + ZPL template engine + Labelary preview. Multi-arch Docker image
published to GHCR on every `v*` tag and pulled by Pi fleet.

Lives alongside (not inside) `station-v2-docker`; the Station V2 stack has its
own `printer-service` (patient-info only). This server is general-purpose, for
stations and intranet callers.

## Status

- **Shipped on `main`**:
  - `v0.2.0` initial release — FastAPI + templates + table + preview + UI
  - `v0.2.1`(unreleased commit `1b73597`) default label size fix to 2.25×2 inch (456×406 dots)
- **In flight on `design/multi-printer`**:
  - Design doc for multi-printer + template size auto-match
    (`_docs/design/multi_printer.md`)
  - Implementation plan (`_docs/plan/multi_printer_plan.md`) — targets `v0.3.0`
- **Deployed**: 1× Pi (`qwh-pi5-c.local:8088`, ZD411 @ 203 dpi, 2.25×2 inch stock)
- **Pending follow-ups** (from `plan/initial_release_plan.md`):
  - Rotate fleet PAT to bot account, bake into pi-gen base image
  - station-v2 `printer-service` either grabs the same flock or migrates to HTTP
  - CI checks on `main` push (currently only release tags trigger Actions)
  - Local ZPL renderer to replace Labelary for PII labels

## Tech Stack

- Python 3.11 (slim image)
- FastAPI + Uvicorn
- Stdlib `urllib` + `fcntl.flock` (no Redis / no DB)
- Docker / docker compose v2; host network on Pi
- GitHub Actions buildx → GHCR (`ghcr.io/aptitudemedicalsystems/print-server-zebra`)

## Key Paths

- `app/main.py` — FastAPI app + endpoint handlers
- `app/printer.py` — USB write, `flock`, `~HQES` status query
- `app/templates.py` — Template engine (`;; @field` frontmatter + `{{var}}`)
- `app/table.py` — Table → ZPL renderer
- `app/preview.py` — Labelary multi-label preview proxy
- `app/config.py` — Env config (read once at import)
- `static/index.html` — Single-file UI (4 tabs + preview pane)
- `templates/*.zpl` — Built-in templates
- `setup.sh` — One-shot new-Pi bootstrap
- `_docs/` — Project docs (see `_docs/DOC_GUIDE.md`)

## Coexistence

The legacy `station-v2-docker/printer-service` (port 8086) writes the same
`/dev/usb/lp0`. This server takes `/var/lock/zd411.lock` via `fcntl.flock`
around every device write. The legacy service does NOT yet share the lock —
under contention bytes can interleave. Eventual fix is to have station-v2 call
this server's HTTP API instead of writing the device directly.

## Rules

- **No new long-running deps** unless justified. `fcntl` and `urllib` are
  enough; do not add Redis/MQ.
- **Templates stay text files**. Don't move to YAML/JSON metadata —
  frontmatter keeps schema next to ZPL.
- **`{{var}}` is plain string replace, no escaping**. If a field can contain
  `^` or `~`, callers sanitize.
- **Tags drive releases**. `git tag vX.Y.Z && git push --tags` → Actions →
  GHCR. Never use `:latest` in fleet compose files.
- **Image is private**. Pi `docker login` uses a Classic PAT with
  `read:packages` scope; the PAT lives in `~pi/.docker/config.json` (baked
  into pi-gen base).
- **Chinese for docs and conversation, English for code and commits**.

## Communication

- User prefers Chinese conversation
- Documentation in Chinese, technical terms in English
- CLAUDE.md and code in English
- Doc structure follows `_docs/DOC_GUIDE.md`

## Workflow

```bash
# local dev
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build

# release
git tag v0.x.y && git push origin v0.x.y  # Actions builds & pushes to GHCR

# Pi cutover (one Pi)
GHCR_TOKEN=... bash <(curl -fsSL https://raw.githubusercontent.com/AptitudeMedicalSystems/print-server-zebra/main/setup.sh)
```

## Endpoints (cheat sheet)

- `GET /info` — capabilities (printer, label, templates with schema)
- `GET /status` — live `~HQES` query
- `POST /print/template` — `{template, data, copies, dry_run?}`
- `POST /print/table` — `{title?, columns, rows, copies, dry_run?}`
- `POST /print/raw` — `{zpl, copies, dry_run?}`
- `POST /print/text` — `{text, barcode?, copies?, dry_run?}`
- `POST /preview` — `{zpl}` → `{count, images:[data:image/png;base64]}`

`dry_run: true` skips printing AND the token check; the UI uses it for preview.
