import asyncio
import aiohttp
import logging
from typing import Optional

from .config import config as logging_config
from .embeds import build_error_embed, build_footer, truncate_end, truncate_middle

logger = logging.getLogger("hibiki_logger.discord")

# Discord caps `content` at 2000 characters.
CONTENT_LIMIT = 2000

# 429 and 5xx responses are retried. The ceiling keeps a wedged webhook
# from holding the calling task open indefinitely.
MAX_SEND_ATTEMPTS = 4
BASE_BACKOFF_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 30.0
REQUEST_TIMEOUT_SECONDS = 10


def _parse_retry_after(response, payload: Optional[dict]) -> Optional[float]:
    """Extract the retry delay Discord asks for, in seconds.

    Discord sends `Retry-After` as a header and also `retry_after` in the
    JSON body. Either may be absent; the body value is authoritative when
    both are present.
    """
    if payload:
        value = payload.get("retry_after")
        if value is not None:
            try:
                return max(0.0, float(value))
            except (TypeError, ValueError):
                pass

    header = response.headers.get("Retry-After")
    if header:
        try:
            return max(0.0, float(header))
        except (TypeError, ValueError):
            pass
    return None


def _backoff_delay(attempt: int, retry_after: Optional[float] = None) -> float:
    """Delay before the next attempt.

    Discord's own figure is honoured exactly when it gives one. It is not
    clamped to MAX_BACKOFF_SECONDS: retrying sooner than asked is what
    escalates a soft rate limit into a longer ban. Callers check the delay
    against the cap and give up rather than retry early.
    """
    if retry_after is not None:
        return max(retry_after, 0.0)
    return min(BASE_BACKOFF_SECONDS * (2 ** attempt), MAX_BACKOFF_SECONDS)


_OK = "ok"
_RETRY = "retry"
_FAIL = "fail"


async def _attempt_send(webhook_url: str, payload: dict):
    """Make one webhook request.

    Returns (outcome, retry_after). The caller owns the waiting, so the
    session and response are always closed before any backoff begins.
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS),
            ) as response:
                status = response.status

                if status in (200, 204):
                    return _OK, None

                if status == 429:
                    try:
                        body = await response.json(content_type=None)
                    except Exception:
                        body = None
                    logger.warning("Discord rate limited the webhook")
                    return _RETRY, _parse_retry_after(response, body)

                if 500 <= status < 600:
                    logger.warning("Discord returned %s", status)
                    return _RETRY, None

                # 4xx other than 429 will not succeed on retry.
                logger.error(
                    "Failed to send Discord notification. Status: %s", status
                )
                return _FAIL, None
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.warning("Error sending Discord notification: %s", e)
        return _RETRY, None


async def send_discord_notification(
    message: Optional[str] = None,
    webhook_url: str = "",
    username: Optional[str] = None,
    avatar_url: Optional[str] = None,
    embed: Optional[dict] = None,
) -> bool:
    """
    Send a notification to Discord using a webhook.

    Retries on 429 and 5xx responses, honouring Discord's `Retry-After`
    with exponential backoff between attempts. Returns False rather than
    raising, so a failing webhook never breaks the caller's logging path.

    Args:
        message: The message to send (optional when an embed is given)
        webhook_url: Discord webhook URL
        username: Optional username for the webhook
        avatar_url: Optional avatar URL for the webhook
        embed: Optional Discord embed object sent alongside the message

    Returns:
        bool: True if successful, False otherwise
    """
    if not webhook_url:
        logger.warning("Discord webhook URL is not configured")
        return False

    if not message and not embed:
        logger.warning("Discord notification has neither content nor embed")
        return False

    payload: dict = {}
    if message:
        payload["content"] = truncate_end(message, CONTENT_LIMIT)
    if embed:
        payload["embeds"] = [embed]
    if username:
        payload["username"] = username
    if avatar_url:
        payload["avatar_url"] = avatar_url

    for attempt in range(MAX_SEND_ATTEMPTS):
        outcome, retry_after = await _attempt_send(webhook_url, payload)

        if outcome == _OK:
            logger.info("Discord notification sent successfully")
            return True
        if outcome == _FAIL:
            return False

        if attempt + 1 >= MAX_SEND_ATTEMPTS:
            logger.error("Discord send failed and retries are exhausted")
            return False

        delay = _backoff_delay(attempt, retry_after)
        if delay > MAX_BACKOFF_SECONDS:
            # Retrying before Discord is ready would only deepen the limit.
            logger.error(
                "Discord asked to wait %.0fs, beyond the %.0fs cap; "
                "dropping notification",
                delay,
                MAX_BACKOFF_SECONDS,
            )
            return False

        logger.warning("Discord send failed; retrying in %.2fs", delay)
        # Outside the session context, so nothing is held open while waiting.
        await asyncio.sleep(delay)

    return False


def _plain_text_alert(
    level: str,
    message: str,
    logger_name: str,
    trace: Optional[str] = None,
    user_id: Optional[str] = None,
    path: Optional[str] = None,
    method: Optional[str] = None,
    suppressed_count: int = 0,
    dropped_count: int = 0,
) -> str:
    """Render an alert as plain text.

    This is both the pre-embed rendering, kept for LOG_DISCORD_EMBED=false,
    and the fallback when embed construction fails.
    """
    truncated_message = truncate_end(message or "", 500)

    text = f"**{level}** in `{logger_name}`\n"
    text += f"```\n{truncated_message}\n```"

    if path:
        text += f"\n**Path:** `{path}`"
    if method:
        text += f" **Method:** `{method}`"
    if user_id:
        text += f"\n**User ID:** `{user_id}`"

    if trace:
        text += f"\n**Trace:**\n```\n{truncate_middle(trace, 800)}\n```"

    footer = build_footer(suppressed_count, dropped_count)
    if footer:
        text += f"\n_{footer}_"

    return truncate_end(text, 1900)


async def send_error_notification(
    level: str,
    message: str,
    logger_name: str,
    webhook_url: str,
    username: Optional[str] = None,
    trace: Optional[str] = None,
    user_id: Optional[str] = None,
    path: Optional[str] = None,
    method: Optional[str] = None,
    suppressed_count: int = 0,
    dropped_count: int = 0,
    use_embed: Optional[bool] = None,
) -> bool:
    """
    Send an error notification to Discord with formatted details.

    Sends a Discord embed by default; set LOG_DISCORD_EMBED=false, or pass
    use_embed=False, for the plain text rendering. If embed construction
    fails for any reason the alert still goes out as plain text, because
    an alert that looks wrong beats no alert.

    Args:
        level: Log level (ERROR, CRITICAL)
        message: Error message
        logger_name: Name of the logger
        webhook_url: Discord webhook URL
        username: Custom username for the webhook (optional)
        trace: Optional stack trace
        user_id: Optional user ID
        path: Optional request path
        method: Optional HTTP method
        suppressed_count: Occurrences collapsed since this alert last sent
        dropped_count: Alerts shed by the send budget since the last send
        use_embed: Override the LOG_DISCORD_EMBED setting

    Returns:
        bool: True if successful, False otherwise
    """
    if use_embed is None:
        use_embed = logging_config.LOG_DISCORD_EMBED

    resolved_username = username or "Hibiki Error Bot"

    if use_embed:
        try:
            embed = build_error_embed(
                level=level,
                message=message,
                logger_name=logger_name,
                trace=trace,
                user_id=user_id,
                path=path,
                method=method,
                suppressed_count=suppressed_count,
                dropped_count=dropped_count,
            )
        except Exception:
            logger.exception(
                "Failed to build Discord embed; falling back to plain text"
            )
        else:
            return await send_discord_notification(
                webhook_url=webhook_url,
                username=resolved_username,
                embed=embed,
            )

    return await send_discord_notification(
        message=_plain_text_alert(
            level=level,
            message=message,
            logger_name=logger_name,
            trace=trace,
            user_id=user_id,
            path=path,
            method=method,
            suppressed_count=suppressed_count,
            dropped_count=dropped_count,
        ),
        webhook_url=webhook_url,
        username=resolved_username,
    )
