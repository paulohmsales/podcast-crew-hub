"""Inline SVG icons for buttons, drawn in the style of Lucide (24px grid, 2px round strokes)."""

from markupsafe import Markup

PATHS = {
    "x": "M18 6 6 18M6 6l12 12",
    "plus": "M12 5v14M5 12h14",
    "trash": "M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6M10 11v6M14 11v6",
    "pencil": "M17 3l4 4L7 21H3v-4zM14 6l4 4",
    "archive": "M3 4h18v4H3zM5 8v12h14V8M10 12h4",
    "undo": "M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5",
    "history": "M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5M12 7v5l3 2",
    "eye": "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zM12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z",
    "key": "M10.7 12.3 21 2M17 6l3 3M15 8l2 2M7.5 11a4.5 4.5 0 1 0 0 9 4.5 4.5 0 0 0 0-9z",
    "table": "M3 3h18v18H3zM3 9h18M3 15h18M9 3v18",
    "calendar-x": "M3 5h18v16H3zM16 3v4M8 3v4M3 10h18M10 13l4 4M14 13l-4 4",
    "chevron-up": "M18 15l-6-6-6 6",
    "chevron-down": "M6 9l6 6 6-6",
}


def icon(name: str, size: int = 16) -> Markup:
    return Markup(
        f'<svg class="icon" viewBox="0 0 24 24" width="{size}" height="{size}" fill="none" stroke="currentColor" '
        f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="{PATHS[name]}"/></svg>'
    )
