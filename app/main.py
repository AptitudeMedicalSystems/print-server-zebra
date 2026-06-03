from __future__ import annotations

import logging
from pathlib import Path

import base64

from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config, preview, printer, table
from .templates import TemplateStore

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("print-server")

app = FastAPI(title="LAN Print Server", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

store = TemplateStore()


def _check_token(authorization: str | None) -> None:
    if not config.PRINT_API_TOKEN:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    if authorization.removeprefix("Bearer ").strip() != config.PRINT_API_TOKEN:
        raise HTTPException(status_code=403, detail="invalid token")


def gate(dry_run: bool, authorization: str | None) -> None:
    """Require token only when actually printing."""
    if not dry_run:
        _check_token(authorization)


_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
if _STATIC_DIR.is_dir():
    app.mount("/ui", StaticFiles(directory=str(_STATIC_DIR), html=True), name="ui")


@app.get("/", include_in_schema=False)
def root_redirect():
    return RedirectResponse(url="/ui/")


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/info")
def info():
    state = printer.get_state()
    w_dots, h_dots = config.label_dots()
    return {
        "service": "lan-print-server",
        "version": app.version,
        "printer": {
            "model": state.model,
            "dpi": state.dpi,
            "connected": state.connected,
            "device_path": state.device_path,
        },
        "label": {
            "width_mm": config.LABEL_WIDTH_MM,
            "height_mm": config.LABEL_HEIGHT_MM,
            "width_dots": w_dots,
            "height_dots": h_dots,
        },
        "charset": config.CHARSET,
        "preview_enabled": config.PREVIEW_ENABLED,
        "templates": [t.to_dict() for t in store.list()],
        "endpoints": {
            "GET /info": "this document",
            "GET /healthz": "health",
            "GET /status": "live printer status (sends ~HQES)",
            "GET /templates": "list templates",
            "GET /templates/{name}": "single template + schema",
            "PUT /templates/{name}": "upload/update (token)",
            "DELETE /templates/{name}": "delete (token)",
            "POST /print/template": "{template, data, copies, dry_run?} (token unless dry_run)",
            "POST /print/table": "{title?, columns, rows, options, dry_run?} (token unless dry_run)",
            "POST /print/raw": "{zpl, copies, dry_run?} (token unless dry_run)",
            "POST /print/text": "{text, barcode?, copies?, dry_run?} (token unless dry_run)",
            "POST /preview": "{zpl} -> image/png (preview via Labelary)",
        },
    }


@app.get("/status")
def get_printer_status():
    return printer.query_status()


@app.get("/templates")
def list_templates():
    return [t.to_dict() for t in store.list()]


@app.get("/templates/{name}")
def get_template(name: str):
    tpl = store.get(name)
    if not tpl:
        raise HTTPException(404, "template not found")
    return {**tpl.to_dict(), "body": tpl.body}


class TemplateBody(BaseModel):
    body: str


@app.put("/templates/{name}")
def put_template(
    name: str,
    body: TemplateBody,
    authorization: str | None = Header(default=None),
):
    _check_token(authorization)
    try:
        tpl = store.save(name, body.body)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return tpl.to_dict()


@app.delete("/templates/{name}")
def delete_template(
    name: str,
    authorization: str | None = Header(default=None),
):
    _check_token(authorization)
    try:
        ok = store.delete(name)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not ok:
        raise HTTPException(404, "template not found")
    return {"deleted": name}


def _emit(zpl: str, copies: int, dry_run: bool) -> dict:
    if dry_run:
        return {"dry_run": True, "zpl": zpl, "bytes": len(zpl.encode("utf-8"))}
    result = printer.send_zpl(zpl, copies=copies)
    if not result["success"]:
        raise HTTPException(500, result["message"])
    return result


class PrintTemplateReq(BaseModel):
    template: str
    data: dict = Field(default_factory=dict)
    copies: int = 1
    dry_run: bool = False


@app.post("/print/template")
def print_template(
    req: PrintTemplateReq,
    authorization: str | None = Header(default=None),
):
    gate(req.dry_run, authorization)
    try:
        zpl = store.render(req.template, req.data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if zpl is None:
        raise HTTPException(404, f"template '{req.template}' not found")
    return _emit(zpl, req.copies, req.dry_run)


class TableColumn(BaseModel):
    header: str
    key: str | None = None
    width: str | int | None = None
    align: str = "L"


class PrintTableReq(BaseModel):
    title: str = ""
    columns: list[TableColumn]
    rows: list[dict]
    copies: int = 1
    font_h: int = 22
    title_font_h: int = 28
    show_grid: bool = True
    dry_run: bool = False


@app.post("/print/table")
def print_table(
    req: PrintTableReq,
    authorization: str | None = Header(default=None),
):
    gate(req.dry_run, authorization)
    cols = [c.model_dump() for c in req.columns]
    opts = table.TableOptions(
        title=req.title,
        font_h=req.font_h,
        title_font_h=req.title_font_h,
        show_grid=req.show_grid,
        copies=req.copies,
    )
    zpl = table.render_table(cols, req.rows, opts)
    return _emit(zpl, req.copies, req.dry_run)


class PrintRawReq(BaseModel):
    zpl: str
    copies: int = 1
    dry_run: bool = False


@app.post("/print/raw")
def print_raw(
    req: PrintRawReq,
    authorization: str | None = Header(default=None),
):
    gate(req.dry_run, authorization)
    return _emit(req.zpl, req.copies, req.dry_run)


class PrintTextReq(BaseModel):
    text: str
    barcode: str | None = None
    copies: int = 1
    font_h: int = 30
    dry_run: bool = False


@app.post("/print/text")
def print_text(
    req: PrintTextReq,
    authorization: str | None = Header(default=None),
):
    gate(req.dry_run, authorization)
    w, h = config.label_dots()
    margin = 20
    parts = ["^XA", "^CI28", f"^PW{w}", f"^LL{h}", "^LH0,0"]
    parts.append(
        f"^FO{margin},{margin}^A0N,{req.font_h},{req.font_h}"
        f"^FB{w - 2 * margin},3,0,L,0^FD{req.text}^FS"
    )
    if req.barcode:
        parts.append(
            f"^FO{margin},{h - 90}^BCN,70,Y,N,N^FD{req.barcode}^FS"
        )
    parts.append("^XZ")
    return _emit("\n".join(parts), req.copies, req.dry_run)


class PreviewReq(BaseModel):
    zpl: str


@app.post("/preview")
def render_preview(req: PreviewReq):
    if not config.PREVIEW_ENABLED:
        raise HTTPException(404, "preview disabled")
    try:
        pngs = preview.render_all_pngs(req.zpl)
    except Exception as e:
        raise HTTPException(502, f"preview failed: {e}")
    return {
        "count": len(pngs),
        "images": [
            "data:image/png;base64," + base64.b64encode(p).decode("ascii")
            for p in pngs
        ],
    }
