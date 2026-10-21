import re

_UNITS = {"d": 86400, "h": 3600, "m": 60, "s": 1}
_PART = re.compile(r"(\d+)([dhms])")


def parse(text):
    """Parse a duration like '1h30m', '2d 4h', '45s' or '1H 5M' into seconds.

    Units are d, h, m and s, in any case, each used at most once and in that
    order (largest first). Spaces between parts are allowed. Anything else,
    including an empty string, raises ValueError.
    """
    text = text.strip()
    parts = _PART.findall(text)
    if not parts:
        raise ValueError(f"bad duration: {text!r}")
    return sum(int(n) * _UNITS[u] for n, u in parts)


def format_seconds(seconds):
    """Format seconds the way parse() reads them: 5400 -> '1h30m', 0 -> '0s'."""
    if seconds == 0:
        return "0s"
    out = []
    for unit, size in _UNITS.items():
        if seconds >= size:
            out.append(f"{seconds // size}{unit}")
            seconds %= size
    return "".join(out)
