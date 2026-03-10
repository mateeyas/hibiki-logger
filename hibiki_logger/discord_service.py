import aiohttp
import logging
from typing import Optional

logger = logging.getLogger("hibiki_logger.discord")


async def send_discord_notification(
    message: str,
    webhook_url: str,
    username: Optional[str] = None,
    avatar_url: Optional[str] = None,
) -> bool:
    """
    Send a notification to Discord using a webhook.

    Args:
        message: The message to send
        webhook_url: Discord webhook URL
        username: Optional username for the webhook
        avatar_url: Optional avatar URL for the webhook

    Returns:
        bool: True if successful, False otherwise
    """
    if not webhook_url:
        logger.warning("Discord webhook URL is not configured")
        return False

    payload = {"content": message}

    if username:
        payload["username"] = username

    if avatar_url:
        payload["avatar_url"] = avatar_url

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status == 204:
                    logger.info("Discord notification sent successfully")
                    return True
                else:
                    logger.error(
                        "Failed to send Discord notification. Status: %s",
                        response.status,
                    )
                    return False
    except Exception as e:
        logger.exception("Error sending Discord notification: %s", e)
        return False


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
) -> bool:
    """
    Send an error notification to Discord with formatted details.

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

    Returns:
        bool: True if successful, False otherwise
    """
    truncated_message = message[:500] if len(message) > 500 else message

    discord_message = f"**{level}** in `{logger_name}`\n"
    discord_message += f"```\n{truncated_message}\n```"

    if path:
        discord_message += f"\n**Path:** `{path}`"
    if method:
        discord_message += f" **Method:** `{method}`"
    if user_id:
        discord_message += f"\n**User ID:** `{user_id}`"

    if trace:
        truncated_trace = trace[:800] if len(trace) > 800 else trace
        discord_message += f"\n**Trace:**\n```\n{truncated_trace}\n```"

    if len(discord_message) > 1900:
        discord_message = discord_message[:1900] + "\n...(truncated)"

    return await send_discord_notification(
        message=discord_message,
        webhook_url=webhook_url,
        username=username or "Hibiki Error Bot"
    )
