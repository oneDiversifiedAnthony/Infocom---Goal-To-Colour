"""Lightweight SVG-to-PIL renderer for simple flag SVGs.

Handles the subset of SVG elements used in Flags.json:
rect, circle, ellipse, polygon, line. Groups with translate/scale transforms.
Skips path, text, and other complex elements gracefully.
"""

import re
import xml.etree.ElementTree as ET
from PIL import Image, ImageDraw


_NAMED_COLOURS = {
    "white": (255, 255, 255), "black": (0, 0, 0), "red": (255, 0, 0),
    "green": (0, 128, 0), "blue": (0, 0, 255), "yellow": (255, 255, 0),
    "orange": (255, 165, 0), "none": None,
}


def _parse_colour(s):
    if not s or s.lower() == "none":
        return None
    s = s.strip()
    if s in _NAMED_COLOURS:
        return _NAMED_COLOURS[s]
    if s.startswith("#"):
        h = s[1:]
        if len(h) == 3:
            h = h[0]*2 + h[1]*2 + h[2]*2
        if len(h) == 6:
            return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    return None


def _parse_transform(t):
    """Parse translate(x,y) and scale(s) from a transform string. Returns (tx, ty, sx, sy)."""
    tx, ty, sx, sy = 0.0, 0.0, 1.0, 1.0
    if not t:
        return tx, ty, sx, sy
    for m in re.finditer(r'(translate|scale|rotate)\(([^)]+)\)', t):
        fn, args = m.group(1), m.group(2)
        vals = [float(v) for v in re.split(r'[,\s]+', args.strip()) if v]
        if fn == "translate":
            tx = vals[0] if len(vals) > 0 else 0
            ty = vals[1] if len(vals) > 1 else 0
        elif fn == "scale":
            sx = vals[0]
            sy = vals[1] if len(vals) > 1 else vals[0]
    return tx, ty, sx, sy


def _parse_points(s):
    """Parse SVG points attribute into list of (x, y) tuples."""
    pairs = re.findall(r'(-?[\d.]+)[,\s]+(-?[\d.]+)', s)
    return [(float(x), float(y)) for x, y in pairs]


def _render_element(draw, el, gsx, gsy, gtx, gty):
    """Render a single SVG element onto the PIL ImageDraw."""
    tag = el.tag.split("}")[-1] if "}" in el.tag else el.tag

    if tag == "g":
        ttx, tty, tsx, tsy = _parse_transform(el.get("transform"))
        new_sx = gsx * tsx
        new_sy = gsy * tsy
        new_tx = gtx + ttx * gsx
        new_ty = gty + tty * gsy
        for child in el:
            _render_element(draw, child, new_sx, new_sy, new_tx, new_ty)
        return

    fill = _parse_colour(el.get("fill"))
    stroke = _parse_colour(el.get("stroke"))
    sw_str = el.get("stroke-width", "1")
    try:
        stroke_w = float(sw_str)
    except ValueError:
        stroke_w = 1.0
    line_w = max(1, int(stroke_w * min(gsx, gsy)))

    opacity = el.get("opacity")
    if opacity:
        try:
            if float(opacity) < 0.1:
                return
        except ValueError:
            pass

    def _x(v):
        return float(v) * gsx + gtx

    def _y(v):
        return float(v) * gsy + gty

    if tag == "rect":
        x = _x(el.get("x", "0"))
        y = _y(el.get("y", "0"))
        w = float(el.get("width", "0")) * gsx
        h = float(el.get("height", "0")) * gsy
        if fill:
            draw.rectangle([x, y, x + w, y + h], fill=fill)
        if stroke and not fill:
            draw.rectangle([x, y, x + w, y + h], outline=stroke, width=line_w)

    elif tag == "circle":
        cx = _x(el.get("cx", "0"))
        cy = _y(el.get("cy", "0"))
        r = float(el.get("r", "0")) * min(gsx, gsy)
        bbox = [cx - r, cy - r, cx + r, cy + r]
        if fill:
            draw.ellipse(bbox, fill=fill)
        if stroke:
            draw.ellipse(bbox, outline=stroke, width=line_w)

    elif tag == "ellipse":
        cx = _x(el.get("cx", "0"))
        cy = _y(el.get("cy", "0"))
        rx = float(el.get("rx", "0")) * gsx
        ry = float(el.get("ry", "0")) * gsy
        bbox = [cx - rx, cy - ry, cx + rx, cy + ry]
        if fill:
            draw.ellipse(bbox, fill=fill)
        if stroke:
            draw.ellipse(bbox, outline=stroke, width=line_w)

    elif tag == "polygon":
        pts = _parse_points(el.get("points", ""))
        if len(pts) >= 3:
            scaled = [(_x(str(x)), _y(str(y))) for x, y in pts]
            # Re-do without string conversion for speed
            scaled = [(x * gsx + gtx, y * gsy + gty) for x, y in pts]
            if fill:
                draw.polygon(scaled, fill=fill)
            if stroke:
                draw.polygon(scaled, outline=stroke)

    elif tag == "line":
        x1, y1 = _x(el.get("x1", "0")), _y(el.get("y1", "0"))
        x2, y2 = _x(el.get("x2", "0")), _y(el.get("y2", "0"))
        c = stroke or fill or (255, 255, 255)
        draw.line([x1, y1, x2, y2], fill=c, width=line_w)

    elif tag == "path":
        # Simplified path: try to extract fill colour and draw a rough polygon
        d = el.get("d", "")
        if fill and d:
            # Extract coordinate pairs from M/L commands (skip curves)
            coords = re.findall(r'(-?[\d.]+)[,\s]+(-?[\d.]+)', d)
            if len(coords) >= 3:
                scaled = [(float(x) * gsx + gtx, float(y) * gsy + gty) for x, y in coords]
                draw.polygon(scaled, fill=fill)

    # Recurse into child elements (for non-group containers like defs)
    if tag not in ("g",):
        for child in el:
            _render_element(draw, child, gsx, gsy, gtx, gty)


def svg_to_image(svg_string, width, height):
    """Convert an SVG string to a PIL RGBA Image at the given size."""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    root = ET.fromstring(svg_string)
    vb = root.get("viewBox", "0 0 900 600").split()
    vb_w = float(vb[2])
    vb_h = float(vb[3])
    sx = width / vb_w
    sy = height / vb_h

    for el in root:
        _render_element(draw, el, sx, sy, 0.0, 0.0)

    return img
