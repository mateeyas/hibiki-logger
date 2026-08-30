"""
Discord embed construction for error alerts.

Discord enforces hard limits on embed payloads and rejects the whole
message if any of them is exceeded:

* 4096 characters for the description
* 1024 characters per field value
* 6000 characters across the entire embed

Everything here is pure and synchronous so it can be unit tested without
touching the network. Construction never raises for oversized or unusual
input; callers still guard against unexpected failures and fall back to
plain text, because an alert that looks wrong beats no alert.
"""

from datetime import datetime, timezone
from typing import Optional

DESCRIPTION_LIMIT = 4096
FIELD_VALUE_LIMIT = 1024
FIELD_NAME_LIMIT = 256
TITLE_LIMIT = 256
FOOTER_LIMIT = 2048
TOTAL_LIMIT = 6000

WARNING_COLOR = 0xF59E0B
ERROR_COLOR = 0xDC2626
CRITICAL_COLOR = 0x7F1D1D
DEFAULT_COLOR = 0x6B7280

_LEVEL_COLORS = {
    "WARNING": WARNING_COLOR,
    "WARN": WARNING_COLOR,
    "ERROR": ERROR_COLOR,
    "CRITICAL": CRITICAL_COLOR,
    "FATAL": CRITICAL_COLOR,
}

_ELLIPSIS = "\n... {count} characters truncated ...\n"


def level_color(level: str) -> int:
    """Return the embed colour for a log level name."""
    return _LEVEL_COLORS.get((level or "").upper(), DEFAULT_COLOR)


def truncate_end(text: str, limit: int) -> str:
    """Truncate text to limit, marking that it was cut."""
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    suffix = "..."
    if limit <= len(suffix):
        return text[:limit]
    return text[: limit - len(suffix)] + suffix


def truncate_middle(text: str, limit: int) -> str:
    """Truncate text from the middle, keeping the head and the tail.

    Python formats tracebacks with the outermost frame first and the
    innermost frame plus the exception line last, so keeping both ends
    preserves the two parts that matter for diagnosis: where the request
    entered, and what actually blew up. The tail gets the larger share.
    """
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text

    dropped = len(text) - limit
    marker = _ELLIPSIS.format(count=dropped)

    # Re-derive the marker against the budget it actually consumes, so the
    # reported count stays truthful once the marker itself is accounted for.
    marker = _ELLIPSIS.format(count=dropped + len(marker))

    if len(marker) >= limit:
        return truncate_end(text, limit)

    budget = limit - len(marker)
    tail = int(budget * 0.7)
    head = budget - tail
    tail_start = len(text) - tail
    return text[:head] + marker + text[tail_start:]


def _field(name: str, value: Optional[str]) -> Optional[dict]:
    """Build an inline embed field, or None when the value is unset.

    Fields with no value are omitted entirely rather than rendered empty.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return {
        "name": truncate_end(name, FIELD_NAME_LIMIT),
        "value": truncate_end(text, FIELD_VALUE_LIMIT),
        "inline": True,
    }


def _embed_length(embed: dict) -> int:
    """Total character count Discord charges the 6000 limit against."""
    total = len(embed.get("title") or "")
    total += len(embed.get("description") or "")
    total += len((embed.get("footer") or {}).get("text") or "")
    total += len((embed.get("author") or {}).get("name") or "")
    for field in embed.get("fields") or []:
        total += len(field.get("name") or "") + len(field.get("value") or "")
    return total


def build_footer(
    suppressed_count: int = 0,
    dropped_count: int = 0,
) -> Optional[str]:
    """Render the footer note for suppressed and dropped alerts.

    Returns None when there is nothing to report, so the footer key can be
    omitted rather than rendered empty.
    """
    parts = []
    if suppressed_count > 0:
        noun = "occurrence" if suppressed_count == 1 else "occurrences"
        parts.append(f"{suppressed_count} further {noun} suppressed.")
    if dropped_count > 0:
        noun = "alert" if dropped_count == 1 else "alerts"
        parts.append(f"{dropped_count} older queued {noun} dropped.")
    if not parts:
        return None
    return " ".join(parts)


def build_error_embed(
    level: str,
    message: str,
    logger_name: str,
    trace: Optional[str] = None,
    user_id: Optional[str] = None,
    path: Optional[str] = None,
    method: Optional[str] = None,
    suppressed_count: int = 0,
    dropped_count: int = 0,
    timestamp: Optional[datetime] = None,
) -> dict:
    """Build a Discord embed for an error alert, within Discord's limits."""
    embed: dict = {
        "title": truncate_end(f"{(level or 'ERROR').upper()}", TITLE_LIMIT),
        "color": level_color(level),
        "timestamp": (timestamp or datetime.now(timezone.utc)).isoformat(),
    }

    fields = [
        _field("Logger", logger_name),
        _field("User ID", user_id),
        _field("Path", path),
        _field("Method", method),
    ]
    fields = [f for f in fields if f is not None]
    if fields:
        embed["fields"] = fields

    footer = build_footer(suppressed_count, dropped_count)
    if footer:
        embed["footer"] = {"text": truncate_end(footer, FOOTER_LIMIT)}

    # The description carries the message and, when present, the traceback.
    # It is the only unbounded part of the payload, so it absorbs whatever
    # budget the fixed parts leave behind.
    fixed_length = _embed_length({**embed, "description": ""})
    budget = min(DESCRIPTION_LIMIT, max(TOTAL_LIMIT - fixed_length, 0))

    head = str(message or "")
    if trace:
        fence_overhead = len("\n```\n\n```") if head else len("```\n\n```")
        trace_budget = max(budget - len(head) - fence_overhead, 0)
        if trace_budget <= 0:
            # No room for the traceback at all; keep as much message as fits.
            description = truncate_end(head, budget)
        else:
            description = (
                f"{head}\n```\n{truncate_middle(trace, trace_budget)}\n```"
                if head
                else f"```\n{truncate_middle(trace, trace_budget)}\n```"
            )
            if len(description) > budget:
                description = truncate_end(description, budget)
    else:
        description = truncate_end(head, budget)

    embed["description"] = description
    return embed
