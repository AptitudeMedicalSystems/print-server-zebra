"""ZPL template engine with frontmatter-declared field schemas.

Frontmatter format (lines starting with ';;' before any ZPL command):
    ;; @label width=50mm height=30mm
    ;; @field patient: str required "Patient name"
    ;; @field qty: int default=1
    ;; @field date: str
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import config

logger = logging.getLogger(__name__)


FIELD_RE = re.compile(
    r"^;;\s*@field\s+(?P<name>[A-Za-z_][\w]*)\s*:\s*"
    r"(?P<type>str|int|float|bool)"
    r"(?:\s+(?P<flags>[^\"]*?))?"
    r"(?:\s+\"(?P<desc>[^\"]*)\")?\s*$"
)
LABEL_RE = re.compile(
    r"^;;\s*@label(?:\s+width=(?P<w>[\d.]+)mm)?(?:\s+height=(?P<h>[\d.]+)mm)?\s*$"
)
VAR_RE = re.compile(r"\{\{\s*([A-Za-z_][\w]*)\s*\}\}")


@dataclass
class FieldSpec:
    name: str
    type: str
    required: bool = False
    default: object | None = None
    description: str = ""

    def to_dict(self) -> dict:
        d = {"name": self.name, "type": self.type, "required": self.required}
        if self.default is not None:
            d["default"] = self.default
        if self.description:
            d["description"] = self.description
        return d


@dataclass
class Template:
    name: str
    body: str
    fields: list[FieldSpec] = field(default_factory=list)
    label_width_mm: float | None = None
    label_height_mm: float | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "fields": [f.to_dict() for f in self.fields],
            "label_width_mm": self.label_width_mm,
            "label_height_mm": self.label_height_mm,
        }


def _coerce(value: object, type_name: str) -> object:
    if value is None:
        return None
    if type_name == "str":
        return str(value)
    if type_name == "int":
        return int(value)
    if type_name == "float":
        return float(value)
    if type_name == "bool":
        if isinstance(value, bool):
            return value
        return str(value).lower() in {"1", "true", "yes", "y"}
    return value


def _parse_flags(flags: str | None) -> tuple[bool, object | None]:
    if not flags:
        return False, None
    required = False
    default: object | None = None
    for token in flags.strip().split():
        if token == "required":
            required = True
        elif token.startswith("default="):
            default = token.split("=", 1)[1]
    return required, default


def parse_template(name: str, body: str) -> Template:
    fields: list[FieldSpec] = []
    label_w: float | None = None
    label_h: float | None = None

    for line in body.splitlines():
        stripped = line.strip()
        if not stripped.startswith(";;"):
            # frontmatter ends at first non-comment, non-blank line
            if stripped and not stripped.startswith(";;"):
                # still allow blank comment lines mid-frontmatter; stop on ZPL
                if stripped.startswith("^") or stripped.startswith("~"):
                    break
        if m := LABEL_RE.match(stripped):
            if m.group("w"):
                label_w = float(m.group("w"))
            if m.group("h"):
                label_h = float(m.group("h"))
            continue
        if m := FIELD_RE.match(stripped):
            required, default_raw = _parse_flags(m.group("flags"))
            type_name = m.group("type")
            default = _coerce(default_raw, type_name) if default_raw is not None else None
            fields.append(
                FieldSpec(
                    name=m.group("name"),
                    type=type_name,
                    required=required,
                    default=default,
                    description=(m.group("desc") or "").strip(),
                )
            )

    # If frontmatter declares no fields, auto-discover {{var}} placeholders.
    if not fields:
        seen: set[str] = set()
        for var in VAR_RE.findall(body):
            if var not in seen:
                seen.add(var)
                fields.append(FieldSpec(name=var, type="str", required=True))

    return Template(
        name=name,
        body=body,
        fields=fields,
        label_width_mm=label_w,
        label_height_mm=label_h,
    )


class TemplateStore:
    def __init__(self, directory: Path | None = None):
        self.dir = directory or config.TEMPLATES_DIR
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        if not re.match(r"^[A-Za-z0-9_-]+$", name):
            raise ValueError("template name: only [A-Za-z0-9_-] allowed")
        return self.dir / f"{name}.zpl"

    def list(self) -> list[Template]:
        out: list[Template] = []
        for path in sorted(self.dir.glob("*.zpl")):
            try:
                out.append(parse_template(path.stem, path.read_text(encoding="utf-8")))
            except Exception:
                logger.exception("failed to parse %s", path)
        return out

    def get(self, name: str) -> Template | None:
        path = self._path(name)
        if not path.is_file():
            return None
        return parse_template(name, path.read_text(encoding="utf-8"))

    def save(self, name: str, body: str) -> Template:
        path = self._path(name)
        path.write_text(body, encoding="utf-8")
        return parse_template(name, body)

    def delete(self, name: str) -> bool:
        path = self._path(name)
        if not path.is_file():
            return False
        path.unlink()
        return True

    def render(self, name: str, data: dict) -> str | None:
        tpl = self.get(name)
        if tpl is None:
            return None
        values: dict[str, object] = {}
        for f in tpl.fields:
            if f.name in data:
                values[f.name] = _coerce(data[f.name], f.type)
            elif f.default is not None:
                values[f.name] = f.default
            elif f.required:
                raise ValueError(f"missing required field: {f.name}")
            else:
                values[f.name] = ""

        def repl(m: re.Match[str]) -> str:
            key = m.group(1)
            return str(values.get(key, ""))

        return VAR_RE.sub(repl, tpl.body)
