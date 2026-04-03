"""Tests for OAuth redirect URI handling in cloud service."""

from unittest.mock import MagicMock, patch

from sqlalchemy.orm import Session

from app.services.cloud.service import CloudService


def test_get_oauth_url_uses_explicit_redirect_uri(db_session: Session):
    """An explicit redirect URI should be used in generated OAuth URLs."""
    service = CloudService(db_session)
    redirect_uri = "https://localhost/api/cloud/oauth/callback"

    with patch("app.services.cloud.oauth_config.CloudOAuthConfigService.get_credentials", return_value=("cid", "csecret")):
        oauth_url = service.get_oauth_url("google_drive", user_id=1, redirect_uri=redirect_uri)

    assert "redirect_uri=https%3A%2F%2Flocalhost%2Fapi%2Fcloud%2Foauth%2Fcallback" in oauth_url


def test_handle_oauth_callback_uses_explicit_redirect_uri(db_session: Session):
    """Token exchange must use the same explicit redirect URI to avoid mismatches."""
    service = CloudService(db_session)
    redirect_uri = "https://localhost/api/cloud/oauth/callback"

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "access_token": "test-access",
        "refresh_token": "test-refresh",
        "scope": "https://www.googleapis.com/auth/drive.readonly",
        "token_type": "Bearer",
    }

    with patch("app.services.cloud.oauth_config.CloudOAuthConfigService.get_credentials", return_value=("cid", "csecret")):
        with patch("httpx.post", return_value=fake_response) as post_mock:
            with patch(
                "app.services.cloud.adapters.rclone.RcloneAdapter.generate_config",
                return_value=("gdrive_test", "[gdrive_test]\ntype = drive\n"),
            ):
                conn = service.handle_oauth_callback(
                    "google_drive",
                    code="code-123",
                    user_id=1,
                    redirect_uri=redirect_uri,
                )

    assert conn.provider == "google_drive"
    assert conn.id is not None
    assert post_mock.call_args.kwargs["data"]["redirect_uri"] == redirect_uri
