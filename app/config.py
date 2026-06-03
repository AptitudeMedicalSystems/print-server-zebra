import os
from pathlib import Path


def _int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default


HOST = os.getenv("HOST", "0.0.0.0")
PORT = _int("PORT", 8088)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

LABEL_WIDTH_MM = float(os.getenv("LABEL_WIDTH_MM", "50"))
LABEL_HEIGHT_MM = float(os.getenv("LABEL_HEIGHT_MM", "30"))
PRINTER_DPI = _int("PRINTER_DPI", 203)
PRINTER_MODEL = os.getenv("PRINTER_MODEL", "Zebra ZD411-203dpi")
CHARSET = os.getenv("CHARSET", "UTF-8")

TEMPLATES_DIR = Path(os.getenv("TEMPLATES_DIR", "/data/templates"))
DEVICE_PATH = os.getenv("DEVICE_PATH", "")  # empty = autodetect
LOCK_PATH = os.getenv("LOCK_PATH", "/var/lock/zd411.lock")

PRINT_API_TOKEN = os.getenv("PRINT_API_TOKEN", "")

PREVIEW_ENABLED = os.getenv("PREVIEW_ENABLED", "true").lower() in {"1", "true", "yes"}
LABELARY_URL = os.getenv("LABELARY_URL", "https://api.labelary.com")
LABELARY_TIMEOUT = float(os.getenv("LABELARY_TIMEOUT", "10"))


def dots_per_mm() -> float:
    return PRINTER_DPI / 25.4


def label_dots() -> tuple[int, int]:
    dpm = dots_per_mm()
    return int(round(LABEL_WIDTH_MM * dpm)), int(round(LABEL_HEIGHT_MM * dpm))
