"""Console output that never crashes, whatever the terminal encoding is.

Windows consoles default to a legacy code page (cp1252/cp437), and in CI stdout is a pipe
whose encoding comes from the locale. Printing a ✅ or a Δ then raises
``UnicodeEncodeError`` and takes the whole run down — which is exactly what happened on the
Windows CI matrix before this module existed.

Rules:

* ``install()`` switches stdout/stderr to UTF-8 with ``errors="replace"`` so encoding can
  never abort a run.
* ``sanitize()`` rewrites symbols to ASCII when the stream cannot represent them, so a
  cp437 console shows ``[ok]`` instead of mojibake.
* Call :func:`sym` instead of hard-coding a symbol: it picks the right form per stream.
"""

from __future__ import annotations

import sys

# symbol -> ASCII fallback
FALLBACKS = {
    "\u2705": "[ok]",       # ✅
    "\u274c": "[x]",        # ❌
    "\u26a0\ufe0f": "[!]",  # ⚠️
    "\u26a0": "[!]",        # ⚠
    "\u23f8": "[off]",      # ⏸
    "\u0394": "delta",      # Δ
    "\u2014": "-",          # —
    "\u2013": "-",          # –
    "\u2026": "...",        # …
    "\u00b7": "|",          # ·
    "\u2192": "->",         # →
    "\u2022": "*",          # •
    "\u00d7": "x",          # ×
    "\u2265": ">=",         # ≥
    "\u2264": "<=",         # <=
}

ASCII_ONLY = set(FALLBACKS)


def _encoding_of(stream) -> str:
    return (getattr(stream, "encoding", None) or "utf-8").lower()


def can_encode(stream, text: str) -> bool:
    encoding = _encoding_of(stream)
    try:
        text.encode(encoding)
        return True
    except (UnicodeEncodeError, LookupError):
        return False


def sanitize(text: str, stream=None) -> str:
    """Replace symbols the stream cannot encode with ASCII equivalents."""
    stream = stream or sys.stdout
    if can_encode(stream, text):
        return text
    out = text
    for symbol, fallback in FALLBACKS.items():
        out = out.replace(symbol, fallback)
    # anything still unencodable (e.g. emoji we forgot) becomes '?'
    try:
        out.encode(_encoding_of(stream))
    except UnicodeEncodeError:
        out = out.encode(_encoding_of(stream), "replace").decode(_encoding_of(stream), "replace")
    return out


def sym(unicode_char: str, fallback: str = "", stream=None) -> str:
    """Return `unicode_char` if the stream can show it, else `fallback`."""
    stream = stream or sys.stdout
    if can_encode(stream, unicode_char):
        return unicode_char
    return fallback or FALLBACKS.get(unicode_char, "")


def install(verbose: bool = False) -> None:
    """Make stdout/stderr UTF-8 tolerant. Safe to call more than once."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            # detached or closed stream — nothing to do
            pass
    if verbose:
        print(f"stdout encoding: {_encoding_of(sys.stdout)}")


def write(text: str, stream=None) -> None:
    """print(), but encoding-safe."""
    stream = stream or sys.stdout
    stream.write(sanitize(text, stream) + "\n")
