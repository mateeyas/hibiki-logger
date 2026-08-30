import pytest

from hibiki_logger import logger as logger_module


@pytest.fixture(autouse=True)
def reset_discord_throttle():
    """Clear Discord dedup and rate-limit state between tests.

    The throttle is process-wide by design, so without this an identical
    alert sent by an earlier test suppresses the next test's alert.
    """
    logger_module.reset_discord_throttle()
    yield
    logger_module.reset_discord_throttle()
