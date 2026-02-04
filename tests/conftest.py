"""Pytest configuration and fixtures."""
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_session():
    """Mock BlueSky session."""
    with patch('bsky_cli.auth.get_session') as mock:
        mock.return_value = (
            "https://bsky.social",  # pds
            "did:plc:test123",       # did
            "fake-jwt-token",        # jwt
            "test.bsky.social"       # handle
        )
        yield mock


@pytest.fixture
def mock_requests():
    """Mock requests library."""
    with patch('requests.get') as mock_get, \
         patch('requests.post') as mock_post:
        yield {'get': mock_get, 'post': mock_post}
