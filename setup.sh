#!/usr/bin/env bash
# Bootstrap print-server on a new Pi.
#
# Usage:
#   GHCR_TOKEN=ghp_... bash setup.sh
#
# Optional env:
#   GHCR_USER             GitHub username for the token (default: QIUWEIHAO)
#   PRINT_SERVER_VERSION  image tag (default: 0.2.0)
#   LABEL_WIDTH_MM        label width  (default: 50.8)
#   LABEL_HEIGHT_MM       label height (default: 50.8)
#   PRINTER_DPI           203 or 300   (default: 203)
#   INSTALL_DIR           where to clone (default: /home/pi/print-server)

set -euo pipefail

GHCR_TOKEN="${GHCR_TOKEN:-}"
GHCR_USER="${GHCR_USER:-QIUWEIHAO}"
PRINT_SERVER_VERSION="${PRINT_SERVER_VERSION:-0.2.0}"
LABEL_WIDTH_MM="${LABEL_WIDTH_MM:-50.8}"
LABEL_HEIGHT_MM="${LABEL_HEIGHT_MM:-50.8}"
PRINTER_DPI="${PRINTER_DPI:-203}"
INSTALL_DIR="${INSTALL_DIR:-/home/pi/print-server}"
REPO_URL="https://github.com/AptitudeMedicalSystems/print-server-zebra.git"

red()   { printf "\033[31m%s\033[0m\n" "$*"; }
green() { printf "\033[32m%s\033[0m\n" "$*"; }
blue()  { printf "\033[34m%s\033[0m\n" "$*"; }

blue "==> Preflight checks"
for bin in docker git curl; do
  command -v "$bin" >/dev/null || { red "missing: $bin"; exit 1; }
done
docker compose version >/dev/null 2>&1 || { red "docker compose v2 not found"; exit 1; }
if [[ ! -e /dev/usb/lp0 ]]; then
  red "warning: /dev/usb/lp0 not present — plug in the ZD411 and retry, or continue (service will run but print will fail)"
fi
if [[ -z "$GHCR_TOKEN" ]]; then
  red "GHCR_TOKEN env required (Classic PAT with read:packages)"
  exit 1
fi

blue "==> Cloning/updating repo at $INSTALL_DIR"
if [[ -d "$INSTALL_DIR/.git" ]]; then
  git -C "$INSTALL_DIR" pull --ff-only
else
  git clone "$REPO_URL" "$INSTALL_DIR"
fi

blue "==> Writing .env"
cat > "$INSTALL_DIR/.env" <<EOF
PRINT_SERVER_VERSION=$PRINT_SERVER_VERSION
LABEL_WIDTH_MM=$LABEL_WIDTH_MM
LABEL_HEIGHT_MM=$LABEL_HEIGHT_MM
PRINTER_DPI=$PRINTER_DPI
PRINTER_MODEL=Zebra ZD411-${PRINTER_DPI}dpi
EOF

blue "==> docker login ghcr.io"
echo "$GHCR_TOKEN" | docker login ghcr.io -u "$GHCR_USER" --password-stdin

blue "==> Pulling image $PRINT_SERVER_VERSION"
( cd "$INSTALL_DIR" && docker compose pull )

blue "==> Starting print-server"
( cd "$INSTALL_DIR" && docker compose up -d )

blue "==> Waiting for healthz"
for i in {1..15}; do
  if curl -sf http://127.0.0.1:8088/healthz >/dev/null; then
    green "✓ print-server is up at http://$(hostname):8088"
    green "  UI: http://$(hostname).local:8088/ui/"
    green "  Info: curl http://localhost:8088/info | jq"
    exit 0
  fi
  sleep 1
done
red "✗ healthcheck did not respond after 15s — check: docker logs print-server"
exit 1
