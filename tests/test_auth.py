"""Tests for auth module."""
import pytest
from unittest.mock import patch, MagicMock
import subprocess

from bsky_cli import auth


class TestLoadFromPass:
    """Tests for load_from_pass function."""

    def test_successful_load(self):
        """Should parse pass output correctly."""
        mock_output = "BSKY_HANDLE=test.bsky.social\nBSKY_APP_PASSWORD=secret123\n"
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=mock_output)
            result = auth.load_from_pass("api/test")
        
        assert result == {
            "BSKY_HANDLE": "test.bsky.social",
            "BSKY_APP_PASSWORD": "secret123"
        }

    def test_skips_comments_and_empty_lines(self):
        """Should skip comments and empty lines."""
        mock_output = "# Comment\n\nBSKY_HANDLE=test\n  \n"
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=mock_output)
            result = auth.load_from_pass("api/test")
        
        assert result == {"BSKY_HANDLE": "test"}

    def test_returns_none_on_failure(self):
        """Should return None when pass fails."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            result = auth.load_from_pass("api/nonexistent")
        
        assert result is None

    def test_returns_none_on_exception(self):
        """Should return None on subprocess exception."""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("pass", 5)
            result = auth.load_from_pass("api/test")
        
        assert result is None

    def test_returns_none_for_empty_output(self):
        """Should return None when output has no valid lines."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="# only comments\n")
            result = auth.load_from_pass("api/test")
        
        assert result is None


class TestCreateSession:
    """Tests for create_session function."""

    def test_successful_session_creation(self):
        """Should create session with correct API call."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "did": "did:plc:abc123",
            "accessJwt": "jwt-token",
            "handle": "test.bsky.social"
        }
        
        with patch('requests.post') as mock_post:
            mock_post.return_value = mock_response
            result = auth.create_session(
                "https://bsky.social",
                "test@example.com",
                "password123"
            )
        
        mock_post.assert_called_once_with(
            "https://bsky.social/xrpc/com.atproto.server.createSession",
            json={"identifier": "test@example.com", "password": "password123"},
            timeout=20
        )
        assert result["did"] == "did:plc:abc123"

    def test_strips_trailing_slash_from_pds(self):
        """Should handle PDS URL with trailing slash."""
        with patch('requests.post') as mock_post:
            mock_post.return_value = MagicMock(json=lambda: {"did": "x"})
            auth.create_session("https://bsky.social/", "id", "pw")
        
        call_url = mock_post.call_args[0][0]
        assert "//" not in call_url.replace("https://", "")


class TestGetSession:
    """Tests for get_session function."""

    def test_returns_session_tuple(self):
        """Should return (pds, did, jwt, handle) tuple."""
        mock_creds = {
            "BSKY_PDS": "https://bsky.social",
            "BSKY_HANDLE": "test.bsky.social",
            "BSKY_APP_PASSWORD": "secret"
        }
        mock_session = {
            "did": "did:plc:test",
            "accessJwt": "jwt123",
            "didDoc": {}
        }
        
        with patch.object(auth, 'load_credentials', return_value=mock_creds), \
             patch.object(auth, 'create_session', return_value=mock_session):
            pds, did, jwt, handle = auth.get_session()
        
        assert pds == "https://bsky.social"
        assert did == "did:plc:test"
        assert jwt == "jwt123"
        assert handle == "test.bsky.social"

    def test_extracts_pds_from_did_doc(self):
        """Should extract actual PDS from didDoc service endpoint."""
        mock_creds = {
            "BSKY_HANDLE": "test.bsky.social",
            "BSKY_APP_PASSWORD": "secret"
        }
        mock_session = {
            "did": "did:plc:test",
            "accessJwt": "jwt123",
            "didDoc": {
                "service": [
                    {
                        "id": "#atproto_pds",
                        "type": "AtprotoPersonalDataServer",
                        "serviceEndpoint": "https://pds.example.com"
                    }
                ]
            }
        }
        
        with patch.object(auth, 'load_credentials', return_value=mock_creds), \
             patch.object(auth, 'create_session', return_value=mock_session):
            pds, _, _, _ = auth.get_session()
        
        assert pds == "https://pds.example.com"

    def test_uses_email_when_no_handle(self):
        """Should use email as identifier when handle is missing."""
        mock_creds = {
            "BSKY_EMAIL": "test@example.com",
            "BSKY_APP_PASSWORD": "secret"
        }
        mock_session = {"did": "x", "accessJwt": "y", "didDoc": {}}
        
        with patch.object(auth, 'load_credentials', return_value=mock_creds), \
             patch.object(auth, 'create_session', return_value=mock_session) as mock_create:
            auth.get_session()
        
        call_args = mock_create.call_args[0]
        assert call_args[1] == "test@example.com"

    def test_exits_when_credentials_missing(self):
        """Should exit when required credentials are missing."""
        mock_creds = {"BSKY_HANDLE": "test"}  # Missing password
        
        with patch.object(auth, 'load_credentials', return_value=mock_creds):
            with pytest.raises(SystemExit):
                auth.get_session()


class TestUtcNowIso:
    """Tests for utc_now_iso function."""

    def test_returns_iso_format(self):
        """Should return ISO format with Z suffix."""
        result = auth.utc_now_iso()
        assert result.endswith("Z")
        assert "T" in result

    def test_no_microseconds(self):
        """Should not include microseconds."""
        result = auth.utc_now_iso()
        # Microseconds would add .123456 before Z
        assert "." not in result


class TestResolveHandle:
    """Tests for resolve_handle function."""

    def test_returns_did_unchanged(self):
        """Should return DID as-is without API call."""
        with patch('requests.get') as mock_get:
            result = auth.resolve_handle("https://bsky.social", "did:plc:abc123")
        
        mock_get.assert_not_called()
        assert result == "did:plc:abc123"

    def test_resolves_handle_via_api(self):
        """Should resolve handle to DID via API."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"did": "did:plc:resolved"}
        
        with patch('requests.get') as mock_get:
            mock_get.return_value = mock_response
            result = auth.resolve_handle("https://bsky.social", "test.bsky.social")
        
        mock_get.assert_called_once()
        assert result == "did:plc:resolved"
