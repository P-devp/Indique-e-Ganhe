import pytest

from app import app, reset_rate_limiter


@pytest.fixture(autouse=True)
def reset_limits():
    reset_rate_limiter()


@pytest.fixture
def client():
    with app.test_client() as client:
        yield client
