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
    async def test_plain_text_message_truncation(self):
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
                use_embed=False,
            )
            sent_message = mock_send.call_args[1]["message"]
            assert len(sent_message) <= 1950

    @pytest.mark.asyncio
    async def test_sends_embed_by_default(self):
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
            assert "embed" in call_kwargs
            assert call_kwargs["embed"]["description"] == "test error"
            assert "message" not in call_kwargs

    @pytest.mark.asyncio
    async def test_plain_text_when_embed_disabled(self):
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
                use_embed=False,
            )
            call_kwargs = mock_send.call_args[1]
            assert "embed" not in call_kwargs
            assert "test error" in call_kwargs["message"]

    @pytest.mark.asyncio
    async def test_falls_back_to_plain_text_when_embed_fails(self):
        """An alert that looks wrong beats no alert."""
        with patch(
            "hibiki_logger.discord_service.build_error_embed",
            side_effect=ValueError("malformed embed"),
        ):
            with patch(
                "hibiki_logger.discord_service.send_discord_notification",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_send:
                result = await send_error_notification(
                    level="ERROR",
                    message="test error",
                    logger_name="app.test",
                    webhook_url="https://example.com/webhook",
                    use_embed=True,
                )
                assert result is True
                call_kwargs = mock_send.call_args[1]
                assert "embed" not in call_kwargs
                assert "test error" in call_kwargs["message"]

    @pytest.mark.asyncio
    async def test_suppression_count_lands_in_footer_not_body(self):
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
                suppressed_count=142,
            )
            embed = mock_send.call_args[1]["embed"]
            assert "142 further occurrences suppressed." in embed["footer"]["text"]
            assert "142" not in embed["description"]


class FakeResponse:
    def __init__(self, status, headers=None, body=None):
        self.status = status
        self.headers = headers or {}
        self._body = body

    async def json(self, content_type=None):
        if self._body is None:
            raise ValueError("no json body")
        return self._body


class FakePostContext:
    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self._response

    async def __aexit__(self, *exc_info):
        return False


class FakeSession:
    """Returns a scripted sequence of responses, repeating the last one."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.post_count = 0

    def post(self, *args, **kwargs):
        response = self._responses[min(self.post_count, len(self._responses) - 1)]
        self.post_count += 1
        return FakePostContext(response)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


class TestRateLimitHandling:
    @pytest.mark.asyncio
    async def test_429_is_retried_not_lost(self):
        session = FakeSession([FakeResponse(429, {"Retry-After": "2"}), FakeResponse(204)])
        slept = []

        async def fake_sleep(delay):
            slept.append(delay)

        with patch("aiohttp.ClientSession", return_value=session):
            with patch("hibiki_logger.discord_service.asyncio.sleep", fake_sleep):
                result = await send_discord_notification(
                    message="test", webhook_url="https://example.com/webhook"
                )

        assert result is True
        assert session.post_count == 2
        assert slept == [2.0]

    @pytest.mark.asyncio
    async def test_retry_after_from_json_body_is_honoured(self):
        session = FakeSession(
            [FakeResponse(429, {}, {"retry_after": 3.5}), FakeResponse(204)]
        )
        slept = []

        async def fake_sleep(delay):
            slept.append(delay)

        with patch("aiohttp.ClientSession", return_value=session):
            with patch("hibiki_logger.discord_service.asyncio.sleep", fake_sleep):
                result = await send_discord_notification(
                    message="test", webhook_url="https://example.com/webhook"
                )

        assert result is True
        assert slept == [3.5]

    @pytest.mark.asyncio
    async def test_persistent_429_gives_up_without_raising(self):
        session = FakeSession([FakeResponse(429, {"Retry-After": "1"})])

        async def fake_sleep(delay):
            return None

        with patch("aiohttp.ClientSession", return_value=session):
            with patch("hibiki_logger.discord_service.asyncio.sleep", fake_sleep):
                result = await send_discord_notification(
                    message="test", webhook_url="https://example.com/webhook"
                )

        assert result is False
        assert session.post_count == 4

    @pytest.mark.asyncio
    async def test_server_error_is_retried_with_backoff(self):
        session = FakeSession([FakeResponse(503), FakeResponse(204)])
        slept = []

        async def fake_sleep(delay):
            slept.append(delay)

        with patch("aiohttp.ClientSession", return_value=session):
            with patch("hibiki_logger.discord_service.asyncio.sleep", fake_sleep):
                result = await send_discord_notification(
                    message="test", webhook_url="https://example.com/webhook"
                )

        assert result is True
        assert slept == [1.0]

    @pytest.mark.asyncio
    async def test_client_error_is_not_retried(self):
        """A 400 will not succeed on retry; failing fast avoids pointless delay."""
        session = FakeSession([FakeResponse(400)])

        with patch("aiohttp.ClientSession", return_value=session):
            result = await send_discord_notification(
                message="test", webhook_url="https://example.com/webhook"
            )

        assert result is False
        assert session.post_count == 1

    @pytest.mark.asyncio
    async def test_backoff_is_capped(self):
        from hibiki_logger.discord_service import MAX_BACKOFF_SECONDS, _backoff_delay

        assert _backoff_delay(0, 9999.0) == MAX_BACKOFF_SECONDS
        assert _backoff_delay(20) == MAX_BACKOFF_SECONDS
