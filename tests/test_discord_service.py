import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from hibiki_logger.discord_service import (
    send_discord_notification,
    send_error_notification,
)


class TestSendDiscordNotification:
    @pytest.mark.asyncio
    async def test_returns_false_without_url(self):
        result = await send_discord_notification(message="test", webhook_url="")
        assert result is False

    @pytest.mark.asyncio
    async def test_successful_send(self):
        mock_response = MagicMock()
        mock_response.status = 204

        mock_post_cm = AsyncMock()
        mock_post_cm.__aenter__.return_value = mock_response

        mock_session = MagicMock()
        mock_session.post.return_value = mock_post_cm

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_session)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_client):
            result = await send_discord_notification(
                message="test", webhook_url="https://discord.com/api/webhooks/test"
            )
            assert result is True

    @pytest.mark.asyncio
    async def test_failed_send(self):
        mock_response = MagicMock()
        mock_response.status = 400

        mock_post_cm = AsyncMock()
        mock_post_cm.__aenter__.return_value = mock_response

        mock_session = MagicMock()
        mock_session.post.return_value = mock_post_cm

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_session)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_client):
            result = await send_discord_notification(
                message="test", webhook_url="https://discord.com/api/webhooks/test"
            )
            assert result is False


class TestSendErrorNotification:
    @pytest.mark.asyncio
    async def test_default_username(self):
        with patch(
            "hibiki_logger.discord_service.send_discord_notification",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_send:
            await send_error_notification(
                level="ERROR",
                message="test error",
                logger_name="app.test",
                webhook_url="https://example.com/webhook",
            )
            call_kwargs = mock_send.call_args[1]
            assert call_kwargs["username"] == "Hibiki Error Bot"

    @pytest.mark.asyncio
    async def test_custom_username(self):
        with patch(
            "hibiki_logger.discord_service.send_discord_notification",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_send:
            await send_error_notification(
                level="ERROR",
                message="test error",
                logger_name="app.test",
                webhook_url="https://example.com/webhook",
                username="Custom Bot",
            )
            call_kwargs = mock_send.call_args[1]
            assert call_kwargs["username"] == "Custom Bot"

    @pytest.mark.asyncio
    async def test_message_truncation(self):
        long_message = "x" * 600
        with patch(
            "hibiki_logger.discord_service.send_discord_notification",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_send:
            await send_error_notification(
                level="ERROR",
                message=long_message,
                logger_name="app.test",
                webhook_url="https://example.com/webhook",
            )
            sent_message = mock_send.call_args[1]["message"]
            assert len(sent_message) <= 1950
