# LAN Print Server

Standalone HTTP print server for a Zebra ZD411 (or similar ZPL printer) on Pi.

## Quick start

```bash
docker compose up -d --build
curl http://<pi>:8088/info | jq
```

## Endpoints

- `GET /healthz` — health check
- `GET /info` — self-description: printer, label dimensions, templates with field schemas
- `GET /status` — live `~HQES` query (paper / head / pause flags)
- `GET /templates` — list templates
- `GET /templates/{name}` — single template incl. raw body
- `PUT /templates/{name}` — upload `{body}` (token)
- `DELETE /templates/{name}` — (token)
- `POST /print/template` — `{template, data, copies}` (token)
- `POST /print/table` — `{title, columns:[{header,key,width,align}], rows, copies}` (token)
- `POST /print/raw` — `{zpl, copies}` (token)
- `POST /print/text` — `{text, barcode?, copies?}` (token)

## Token

If `PRINT_API_TOKEN` is set, all write/print endpoints require:
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

## Coexisting with station-v2 printer-service

Both services write `/dev/usb/lp0`. This server uses `flock` on
`/var/lock/zd411.lock` to serialize writes. To make the existing
`station-v2-docker` `printer-service` safe, wrap its device write with the
same lock (see `printer_manager.py`).

## Example calls

```bash
curl -s :8088/info | jq

curl -s -X POST :8088/print/text \
  -H "Content-Type: application/json" \
  -d '{"text":"Hello from print-server","barcode":"12345678"}'

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
