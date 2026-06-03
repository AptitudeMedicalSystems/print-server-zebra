"""Generate ZPL for a simple table layout.

Auto-sizes column widths from headers + content. Falls back to even split
if total declared widths exceed label width.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import config


# Approximate character cell at ^A0N font, height = h, width ~ h*0.6
# We use width = font_h * 0.6 dots/char for spacing budgeting.
def char_width(font_h: int) -> float:
    return font_h * 0.6


@dataclass
class TableOptions:
    title: str = ""
    font_h: int = 22  # body font height in dots
    title_font_h: int = 28
    padding: int = 4
    show_grid: bool = True
    copies: int = 1


def render_table(
    columns: list[dict],
    rows: list[dict],
    opts: TableOptions,
) -> str:
    """columns: [{header, key, width?(mm or dots), align?(L/R/C)}]"""
    width_dots, height_dots = config.label_dots()
    margin_x = 8
    margin_y = 8
    usable_w = width_dots - 2 * margin_x

    # Resolve column widths
    declared = []
    for c in columns:
        w = c.get("width")
        if w is None:
            declared.append(None)
        elif isinstance(w, str) and w.endswith("mm"):
            declared.append(int(round(float(w[:-2]) * config.dots_per_mm())))
        else:
            declared.append(int(w))

    total_declared = sum(d for d in declared if d is not None)
    auto_count = sum(1 for d in declared if d is None)
    remaining = max(0, usable_w - total_declared)
    auto_w = (remaining // auto_count) if auto_count else 0
    col_widths = [d if d is not None else auto_w for d in declared]

    # If we overflowed, even-split
    if sum(col_widths) > usable_w or any(w <= 0 for w in col_widths):
        col_widths = [usable_w // len(columns)] * len(columns)

    cw = char_width(opts.font_h)
    line_h = opts.font_h + opts.padding * 2

    parts: list[str] = []
    parts.append("^XA")
    parts.append("^CI28")  # UTF-8
    parts.append(f"^PW{width_dots}")
    parts.append(f"^LL{height_dots}")
    parts.append("^LH0,0")

    y = margin_y

    if opts.title:
        parts.append(
            f"^FO{margin_x},{y}^A0N,{opts.title_font_h},{opts.title_font_h}"
            f"^FB{usable_w},1,0,L,0^FD{_esc(opts.title)}^FS"
        )
        y += opts.title_font_h + opts.padding

    # Header row
    x = margin_x
    header_y = y
    for i, col in enumerate(columns):
        w = col_widths[i]
        text = _truncate(str(col.get("header", "")), w, cw)
        parts.append(
            f"^FO{x + opts.padding},{y + opts.padding}"
            f"^A0N,{opts.font_h},{opts.font_h}^FD{_esc(text)}^FS"
        )
        x += w
    y += line_h
    # Underline under header
    if opts.show_grid:
        parts.append(f"^FO{margin_x},{y - 1}^GB{usable_w},1,1^FS")

    # Body rows
    for row in rows:
        if y + line_h > height_dots - margin_y:
            break
        x = margin_x
        for i, col in enumerate(columns):
            w = col_widths[i]
            key = col.get("key") or col.get("header", "")
            value = row.get(key, "")
            text = _truncate(str(value), w, cw)
            align = col.get("align", "L")
            if align == "R":
                # Right-align by FB
                parts.append(
                    f"^FO{x},{y + opts.padding}^A0N,{opts.font_h},{opts.font_h}"
                    f"^FB{w - opts.padding},1,0,R,0^FD{_esc(text)}^FS"
                )
            elif align == "C":
                parts.append(
                    f"^FO{x},{y + opts.padding}^A0N,{opts.font_h},{opts.font_h}"
                    f"^FB{w},1,0,C,0^FD{_esc(text)}^FS"
                )
            else:
                parts.append(
                    f"^FO{x + opts.padding},{y + opts.padding}"
                    f"^A0N,{opts.font_h},{opts.font_h}^FD{_esc(text)}^FS"
                )
            x += w
        y += line_h
        if opts.show_grid:
            parts.append(f"^FO{margin_x},{y - 1}^GB{usable_w},1,1^FS")

    # Optional vertical grid lines
    if opts.show_grid:
        x = margin_x
        grid_top = header_y
        grid_bottom = min(y, height_dots - margin_y)
        parts.append(f"^FO{x},{grid_top}^GB1,{grid_bottom - grid_top},1^FS")
        for w in col_widths:
            x += w
            parts.append(f"^FO{x},{grid_top}^GB1,{grid_bottom - grid_top},1^FS")

    parts.append("^XZ")
    return "\n".join(parts)


def _esc(s: str) -> str:
    # ZPL field data uses ^ ~ as command leads; escape via ^FH and \5E? Simpler: replace.
    return s.replace("^", " ").replace("~", " ").replace("\n", " ")


def _truncate(s: str, dot_width: int, char_w: float) -> str:
    if char_w <= 0:
        return s
    max_chars = max(1, int(dot_width // char_w))
    if len(s) <= max_chars:
        return s
    if max_chars <= 1:
        return s[:1]
    return s[: max_chars - 1] + "…"
