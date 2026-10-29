import json
import time
from datetime import datetime, timezone


def fmt_ts(ms, local: bool = False) -> str:
    if ms is None:
        return "-"
    tz = None if local else timezone.utc
    return datetime.fromtimestamp(ms / 1000, tz=tz).strftime("%Y-%m-%d %H:%M:%S")


def ts_header(label: str, local: bool) -> str:
    if not local:
        return f"{label} (UTC)"
    offset = datetime.fromtimestamp(time.time()).astimezone().strftime("%z")
    return f"{label} ({offset[:3]}:{offset[3:]})"


def fmt_value(value) -> str:
    """Render a dict or list as compact JSON instead of its Python repr."""
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"))
    return str(value)


def clip(text: str, width: int = 40) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"
