"""USB printer device handling: discovery, locked write, status query."""

from __future__ import annotations

import errno
import fcntl
import glob
import logging
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass

from . import config

logger = logging.getLogger(__name__)


@dataclass
class PrinterState:
    connected: bool
    device_path: str | None
    model: str
    dpi: int


def discover_device() -> str | None:
    if config.DEVICE_PATH:
        return config.DEVICE_PATH if os.path.exists(config.DEVICE_PATH) else None
    matches = sorted(glob.glob("/dev/usb/lp*"))
    return matches[0] if matches else None


def get_state() -> PrinterState:
    path = discover_device()
    return PrinterState(
        connected=path is not None,
        device_path=path,
        model=config.PRINTER_MODEL,
        dpi=config.PRINTER_DPI,
    )


@contextmanager
def _device_lock(timeout: float = 5.0):
    os.makedirs(os.path.dirname(config.LOCK_PATH), exist_ok=True)
    fd = os.open(config.LOCK_PATH, os.O_RDWR | os.O_CREAT, 0o666)
    deadline = time.monotonic() + timeout
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as e:
                if e.errno not in (errno.EAGAIN, errno.EACCES):
                    raise
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"Could not acquire printer lock {config.LOCK_PATH} within {timeout}s"
                    )
                time.sleep(0.05)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def send_zpl(zpl: str, copies: int = 1) -> dict:
    state = get_state()
    if not state.connected or not state.device_path:
        return {"success": False, "message": "Printer not connected"}

    payload = zpl.encode("utf-8")
    total = 0
    try:
        with _device_lock(timeout=5.0):
            with open(state.device_path, "wb", buffering=0) as f:
                for _ in range(max(1, copies)):
                    f.write(payload)
                    total += len(payload)
    except TimeoutError as e:
        logger.warning(str(e))
        return {"success": False, "message": str(e)}
    except PermissionError:
        return {"success": False, "message": f"Permission denied on {state.device_path}"}
    except FileNotFoundError:
        return {"success": False, "message": f"Device disappeared: {state.device_path}"}
    except Exception as e:
        logger.exception("print failed")
        return {"success": False, "message": str(e)}

    logger.info("sent %d bytes (%d copies) to %s", total, copies, state.device_path)
    return {
        "success": True,
        "device": state.device_path,
        "bytes": total,
        "copies": copies,
    }


def query_status() -> dict:
    """Send ~HQES and read printer error/status response."""
    state = get_state()
    if not state.connected or not state.device_path:
        return {"connected": False}

    try:
        with _device_lock(timeout=2.0):
            fd = os.open(state.device_path, os.O_RDWR | os.O_NONBLOCK)
            try:
                os.write(fd, b"~HQES\r\n")
                time.sleep(0.3)
                chunks: list[bytes] = []
                deadline = time.monotonic() + 1.0
                while time.monotonic() < deadline:
                    try:
                        data = os.read(fd, 4096)
                        if not data:
                            break
                        chunks.append(data)
                    except BlockingIOError:
                        time.sleep(0.1)
                        if chunks:
                            break
                raw = b"".join(chunks).decode("ascii", errors="replace")
            finally:
                os.close(fd)
    except Exception as e:
        return {"connected": True, "device": state.device_path, "status_error": str(e)}

    return {
        "connected": True,
        "device": state.device_path,
        "raw": raw,
        "parsed": _parse_hqes(raw),
    }


def _parse_hqes(raw: str) -> dict:
    """Best-effort parse of ~HQES response.

    The response includes flag bytes; we surface a few obvious keywords.
    """
    upper = raw.upper()
    flags = {
        "paper_out": "PAPER OUT" in upper,
        "ribbon_out": "RIBBON OUT" in upper,
        "head_open": "HEAD OPEN" in upper,
        "paused": "PAUSED" in upper,
        "head_over_temp": "HEAD OVER TEMP" in upper,
    }
    return flags
