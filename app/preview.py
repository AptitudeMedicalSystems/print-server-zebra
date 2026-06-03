"""ZPL preview via Labelary public API.

Labelary indexes labels in the submitted ZPL by 0-based position. A submission
containing N ``^XA…^XZ`` blocks renders into N separate images. We probe with
index=0, read ``X-Total-Count``, then fetch the remaining indexes in parallel.
"""

from __future__ import annotations

import logging
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from . import config

logger = logging.getLogger(__name__)


_SUPPORTED_DPMM = (6, 8, 12, 24)
_MAX_LABELS = 16  # safety cap


def _dpmm_for(dpi: int) -> int:
    dpmm = dpi / 25.4
    return min(_SUPPORTED_DPMM, key=lambda v: abs(v - dpmm))


def _url(index: int) -> str:
    w_in = config.LABEL_WIDTH_MM / 25.4
    h_in = config.LABEL_HEIGHT_MM / 25.4
    dpmm = _dpmm_for(config.PRINTER_DPI)
    return (
        f"{config.LABELARY_URL.rstrip('/')}/v1/printers/{dpmm}dpmm/labels/"
        f"{w_in:.2f}x{h_in:.2f}/{index}/"
    )


def _fetch(index: int, zpl_bytes: bytes) -> tuple[bytes, int]:
    """Return (png_bytes, total_count_from_header_or_-1)."""
    req = urllib.request.Request(
        _url(index),
        data=zpl_bytes,
        headers={
            "Accept": "image/png",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=config.LABELARY_TIMEOUT) as r:
            png = r.read()
            total_hdr = r.headers.get("X-Total-Count")
            total = int(total_hdr) if total_hdr and total_hdr.isdigit() else -1
            return png, total
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"labelary {e.code} (index {index}): {body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"labelary unreachable: {e}") from e


def render_all_pngs(zpl: str) -> list[bytes]:
    """Render every ``^XA…^XZ`` block in ``zpl`` to a PNG.

    First request probes index 0 and reads ``X-Total-Count``; remaining indexes
    are fetched in parallel.
    """
    zpl_bytes = zpl.encode("utf-8")
    first, total = _fetch(0, zpl_bytes)
    if total <= 1:
        return [first]
    n = min(total, _MAX_LABELS)
    rest_indexes = list(range(1, n))
    results: dict[int, bytes] = {0: first}
    with ThreadPoolExecutor(max_workers=min(8, len(rest_indexes))) as pool:
        for idx, (png, _t) in zip(
            rest_indexes,
            pool.map(lambda i: _fetch(i, zpl_bytes), rest_indexes),
        ):
            results[idx] = png
    return [results[i] for i in range(n)]
