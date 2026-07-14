import pytest


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    """Retry logic in bot.client uses time.sleep for backoff; skip real delays in tests."""
    monkeypatch.setattr("bot.client.time.sleep", lambda seconds: None)
