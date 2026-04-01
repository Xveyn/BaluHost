"""Tests for setup wizard auth dependency."""
import pytest
from unittest.mock import MagicMock
from fastapi import HTTPException

from app.core.security import create_setup_token, create_access_token
from app.api.deps import get_setup_user
from app.services import users as user_service
from app.schemas.user import UserCreate


class TestGetSetupUser:
    """Tests for the get_setup_user dependency."""

    @pytest.mark.asyncio
    async def test_valid_setup_token_returns_user(self, db_session):
        """Valid setup token should return the admin user."""
        admin = user_service.create_user(
            UserCreate(username="setupadmin", email="s@example.com", password="Admin123!", role="admin"),
            db=db_session,
        )
        token = create_setup_token(user_id=admin.id, username=admin.username)

        request = MagicMock()
        request.client.host = "127.0.0.1"

        user = await get_setup_user(request=request, token=token, db=db_session)
        assert user.username == "setupadmin"

    @pytest.mark.asyncio
    async def test_access_token_rejected(self, db_session):
        """Regular access token must not work for setup endpoints."""
        admin = user_service.create_user(
            UserCreate(username="setupadmin2", email="s2@example.com", password="Admin123!", role="admin"),
            db=db_session,
        )
        token = create_access_token(admin)

        request = MagicMock()
        request.client.host = "127.0.0.1"

        with pytest.raises(HTTPException) as exc_info:
            await get_setup_user(request=request, token=token, db=db_session)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_no_token_rejected(self, db_session):
        """Missing token returns 401."""
        request = MagicMock()
        request.client.host = "127.0.0.1"

        with pytest.raises(HTTPException) as exc_info:
            await get_setup_user(request=request, token=None, db=db_session)
        assert exc_info.value.status_code == 401
