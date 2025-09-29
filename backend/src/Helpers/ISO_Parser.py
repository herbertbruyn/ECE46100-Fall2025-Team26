import re
from datetime import datetime
from typing import Optional


_ISO_DT_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?)?$"
)


def _parse_iso8601(ts: str) -> Optional[datetime]:
    """
    Parse an ISO 8601 formatted timestamp string into a datetime object.
    Args:
        ts: The timestamp string to parse
    Returns:
        A datetime object if parsing succeeds, None otherwise
    """
    try:
        if _ISO_DT_RE.match(ts):
            if 'T' not in ts:
                return datetime.fromisoformat(ts)
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None
    return None
