# LAN Print Server

Standalone HTTP print server for a Zebra ZD411 (or similar ZPL printer) on Pi.
Multi-arch image (`linux/arm64`, `linux/amd64`) published to GHCR by GitHub
Actions on every `v*` tag.

- UI: `http://<pi>:8088/ui/`
- Image: `ghcr.io/aptitudemedicalsystems/print-server-zebra:<version>`
- Source: this repo

## Deploy on a new Pi (one command)

Prereqs on the Pi:
- Docker + Docker Compose v2 (already in Station V2 pi-gen image)
- Zebra ZD411 connected via USB (`/dev/usb/lp0` present after plug-in)
- A Classic PAT with `read:packages` scope (one PAT is shared across the fleet;
  see *Credentials* below)

```bash
GHCR_TOKEN=ghp_xxx \
LABEL_WIDTH_MM=50.8 LABEL_HEIGHT_MM=50.8 \
  bash <(curl -fsSL https://raw.githubusercontent.com/AptitudeMedicalSystems/print-server-zebra/main/setup.sh)
```

What `setup.sh` does:
1. checks docker / git / `/dev/usb/lp0`
2. `git clone` (or `pull`) this repo into `/home/pi/print-server`
3. writes `.env` with your label dimensions + version
4. `docker login ghcr.io` with the given token
5. `docker compose pull && up -d`
6. waits for `GET /healthz` to come up

Common per-Pi overrides:

| env | default | note |
|---|---|---|
| `LABEL_WIDTH_MM` / `LABEL_HEIGHT_MM` | 50.8 / 50.8 | match the physical label stock |
| `PRINTER_DPI` | 203 | 300 for ZD411-300dpi units |
| `PRINT_SERVER_VERSION` | 0.2.0 | bump for upgrades |
| `INSTALL_DIR` | `/home/pi/print-server` | |

Manual equivalent (no setup script):

```bash
git clone https://github.com/AptitudeMedicalSystems/print-server-zebra /home/pi/print-server
cd /home/pi/print-server
cat > .env <<EOF
PRINT_SERVER_VERSION=0.2.0
LABEL_WIDTH_MM=50.8
LABEL_HEIGHT_MM=50.8
PRINTER_DPI=203
EOF
echo "$GHCR_TOKEN" | docker login ghcr.io -u <github-user> --password-stdin
docker compose pull && docker compose up -d
curl http://localhost:8088/info | jq
```

## Upgrades

```bash
cd /home/pi/print-server
git pull
sed -i 's/PRINT_SERVER_VERSION=.*/PRINT_SERVER_VERSION=0.3.0/' .env  # or edit by hand
docker compose pull && docker compose up -d
```

Roll back = set `PRINT_SERVER_VERSION` to the previous tag and pull/up again.

## Credentials

The GHCR package is **private** (GitHub-Settings precludes public-org packages in
the current org policy). Pulls require a Classic PAT with **`read:packages`**
scope. Cross-org pulls work with a single Classic PAT.

Recommended pattern:
- create a dedicated **bot account** (e.g., `aptitude-fleet`)
- invite it (read-only) to every org that hosts a fleet image
- generate one Classic PAT under the bot, scope = `read:packages`
- bake the PAT into the Pi base image via `~pi/.docker/config.json` (pi-gen)

Rotate the PAT yearly. Revoking the PAT kills pulls fleet-wide; existing
running containers keep running.

A future hardening path (deferred): SSH-key-as-identity token broker, see
internal notes.

## Local development

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
# code lives in app/, edits are reflected on container restart
```

## Endpoints

- `GET /healthz` — health check
- `GET /info` — self-description: printer, label dimensions, templates with field schemas, preview flag
- `GET /status` — live `~HQES` query (paper / head / pause flags)
- `GET /templates` — list templates
- `GET /templates/{name}` — single template incl. raw body
- `PUT /templates/{name}` — upload `{body}` (token)
- `DELETE /templates/{name}` — (token)
- `POST /print/template` — `{template, data, copies, dry_run?}` (token unless dry_run)
- `POST /print/table` — `{title?, columns, rows, options, dry_run?}` (token unless dry_run)
- `POST /print/raw` — `{zpl, copies, dry_run?}` (token unless dry_run)
- `POST /print/text` — `{text, barcode?, copies?, dry_run?}` (token unless dry_run)
- `POST /preview` — `{zpl}` → `{count, images:[data:image/png;base64]}` (multi-label via Labelary)

`dry_run: true` on print endpoints returns the rendered ZPL without sending to
the printer and does not require a token. The UI uses this for preview.

## Print API token

If `PRINT_API_TOKEN` env is set, all print/write endpoints require:
`Authorization: Bearer <token>`. GET endpoints stay open inside LAN.

## Template format

```
;; @label width=50mm height=30mm
;; @field patient: str required "Patient name"
;; @field qty: int default=1
^XA
^CI28
^FO20,20^A0N,30,30^FD{{patient}}^FS
^XZ
```

`{{var}}` placeholders are auto-discovered if no `@field` lines are present.

Built-in templates (in `templates/`):
- `zd411_test` — printer self-test (fonts / Code128 / QR / specs)
- `station_v2` — Station V2 device label (SN + barcode + DUID + MID + URL)
- `sample_label` — basic title/code/note example

## Coexisting with station-v2 printer-service

Both services write `/dev/usb/lp0`. This server uses `flock` on
`/var/lock/zd411.lock` to serialize writes. The legacy
`station-v2-docker/printer-service` does NOT yet share the lock — under heavy
contention bytes can interleave. The eventual migration is to have stations
POST to this server's `/print/template` instead of writing the USB device
directly.

## Example calls

```bash
curl -s :8088/info | jq

curl -s -X POST :8088/print/text \
  -H "Content-Type: application/json" \
  -d '{"text":"Hello from print-server","barcode":"12345678"}'

curl -s -X POST :8088/print/template \
  -H "Content-Type: application/json" \
  -d '{
    "template":"station_v2",
    "data":{
      "sn":"S201135Q000004",
      "duid":"1000911008383640",
      "mid_line1":"8155bf3b-d3a2-4d16",
      "mid_line2":"b6d0-c5e757345d58",
      "timestamp":"2026-06-02 23:09 UTC",
      "url":"http://192.168.2.30"
    }
  }'

curl -s -X POST :8088/print/table \
  -H "Content-Type: application/json" \
  -d '{
    "title":"Run #42",
    "columns":[
      {"header":"#","key":"i","width":"6mm","align":"R"},
      {"header":"Target","key":"tgt"},
      {"header":"Cq","key":"cq","align":"R","width":"12mm"}
    ],
    "rows":[
      {"i":1,"tgt":"GAPDH","cq":"21.3"},
      {"i":2,"tgt":"ACTB","cq":"22.7"}
    ]
  }'
```
