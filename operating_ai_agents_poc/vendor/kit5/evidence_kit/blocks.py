"""Blocks: what a case tab shows, as data.  An adapter describes each recorded row's tabs with these; the Lab Console
draws them.  The kit knows how to draw a card, a list of steps or a table, never what any experiment's steps mean.

    tabs = {"trace": [grid(card(kv("Request", case_request())), card(...))], "raw": [...]}

Text is escaped; ``md`` fields allow `code`, **bold** and *italic*.  Tones: ok, warn, bad, info, neutral (or '').
"""

from __future__ import annotations


def grid(*items, cls: str = "g2") -> dict:
    return {"t": "grid", "cls": cls, "items": list(items)}


def card(*items, title: str | None = None, sub: str | None = None) -> dict:
    """A card; `sub` is md."""
    return {"t": "card", "title": title, "sub": sub, "items": list(items)}


def kv(title: str, *items) -> dict:
    """A titled group inside a card."""
    return {"t": "kv", "title": title, "items": list(items)}


def h3(text: str, mt: int | None = None) -> dict:
    return {"t": "h3", "text": text, "mt": mt}


def quote(text: str, mt: int | None = None) -> dict:
    return {"t": "quote", "text": text, "mt": mt}


def line(label: str, value: str, bold: bool = False) -> dict:
    """`label: value` on one small line."""
    return {"t": "line", "label": label, "value": value, "bold": bold}


def small(text: str) -> dict:
    return {"t": "small", "text": text}


def muted(text: str) -> dict:
    return {"t": "muted", "text": text}


def chips(items: list, wrap: bool = False) -> dict:
    """Items are (text, tone) or (text, tone, title)."""
    return {"t": "chips", "items": [list(i) for i in items], "wrap": wrap}


def chip(text: str) -> dict:
    """One neutral chip on its own line (for 'nothing here' states)."""
    return {"t": "chip", "text": text}


def step(head: str, pill: tuple[str, str] | None = None, lines: list[str] | None = None, line_cls: str = "u",
         span: bool = True, mb: int | None = None) -> dict:
    """One step of a list: an md head, a pill, lines under it."""
    return {"head": head, "pill": list(pill) if pill else None, "lines": lines or [], "line_cls": line_cls, "span": span, "mb": mb}


def steps(items: list[dict], bare: bool = False) -> dict:
    """A list of steps; `bare` leaves out the list's frame (each step stands on its own, spaced by its `mb`)."""
    return {"t": "steps", "items": items, "bare": bare}


def status(ok: bool, text: str, after: str = "", link: tuple[str, str] | None = None) -> dict:
    """A ✓/✕ status, optional trailing text and a link to another tab: link=(text, tab id)."""
    return {"t": "status", "ok": ok, "text": text, "after": after, "link": list(link) if link else None}


def transcript(events: list[dict], title: str, sub: str) -> dict:
    """Events: {n, tone, text (md), msg, code, notes (md list)}."""
    return {"t": "transcript", "title": title, "sub": sub, "events": events}


def cell(*parts, cls: str = "") -> dict:
    """A table cell from parts: ('text', s) · ('md', s) · ('code', s) · ('sub', s) · ('alert', s) · ('pill', text, tone) · ('dash',)."""
    return {"cls": cls, "parts": [list(p) for p in parts]}


def table(head: list, rows: list[list], empty: str | None = None) -> dict:
    """Head items are labels, or (label, 'n') for a numeric column. Rows are lists of cells (or plain strings)."""
    return {"t": "table", "head": [list(h) if isinstance(h, (list, tuple)) else [h, ""] for h in head],
            "rows": [[c if isinstance(c, dict) else cell(("text", "" if c is None else str(c))) for c in r] for r in rows], "empty": empty}


def files(paths: list[str]) -> dict:
    return {"t": "files", "items": paths}


def callout(text: str, tone: str = "", icon: str = "alert", mt: int | None = None) -> dict:
    return {"t": "callout", "text": text, "tone": tone, "icon": icon, "mt": mt}


# ---- blocks the console fills from the row and its case (no copying of data that is already in evidence.json)

def case_request() -> dict:
    """The case's request as a quote, and who asked."""
    return {"t": "case_request"}


def case_facts(chip_title: str = "", chip_tone: str = "bad") -> dict:
    """The case's expected facts, and its chips (e.g. what is nearby that must not be used)."""
    return {"t": "case_facts", "chip_title": chip_title, "chip_tone": chip_tone}


def row_flags(note_label: str) -> dict:
    """The scorer's flags for the row, and its note (a failure class) under `note_label`."""
    return {"t": "row_flags", "note_label": note_label}


def row_measurements() -> dict:
    """The row's measurements and key-values as a two-column table."""
    return {"t": "row_measurements"}
