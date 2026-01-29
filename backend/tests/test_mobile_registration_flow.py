"""Tests for mobile device registration flow."""
import os
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from fastapi import status


def test_mobile_registration_flow():
    """Test the complete mobile device registration flow using a token."""
    # Use an in-memory database for isolation and skip full app init
    os.environ['SKIP_APP_INIT'] = '1'
    os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

    # Import app modules after env override
    from app.main import create_app
    from app.core.database import init_db, SessionLocal
    from app.services.users import create_user
    from app.models.mobile import MobileRegistrationToken
    from app.schemas.user import UserCreate

    # Initialize DB schema for tests
    # Ensure a clean schema: drop existing and create tables to match models
    init_db()
    from app.models import Base
    from app.core.database import engine
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()

    # Create a test user
    user_payload = UserCreate(username='test_register', email='test@example.com', password='testpass')
    user = create_user(user_payload, db=db)

    # Create a one-time registration token (simulate /api/mobile/token/generate)
    token_value = 'reg_test_token_12345'
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    db_token = MobileRegistrationToken(token=token_value, user_id=str(user.id), expires_at=expires_at, used=False)
    db.add(db_token)
    db.commit()

    db.close()

    app = create_app()
    client = TestClient(app)

    # Perform mobile registration using the token
    payload = {
        "token": token_value,
        "device_info": {
            "device_name": "Test Phone",
            "device_type": "android",
            "device_model": "Pixel",
            "os_version": "13",
            "app_version": "1.0"
        }
    }

    resp = client.post('/api/mobile/register', json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert 'access_token' in data
    access_token = data['access_token']

    # Use returned access token to list devices for the user
    headers = {"Authorization": f"Bearer {access_token}"}
    resp2 = client.get('/api/mobile/devices', headers=headers)
    assert resp2.status_code == 200, resp2.text
    devices = resp2.json()

    assert any(d.get('device_name') == 'Test Phone' for d in devices), f"Devices: {devices}"


def test_token_generation_works_for_authenticated_user(client):
    """Test that any authenticated user can generate mobile tokens."""
    # Register a fresh user with a valid strong password
    username = "mobile_test_user"
    password = "StrongPassw0rd!"
    email = "mobile@example.com"

    r = client.post("/api/auth/register", json={
        "username": username,
        "email": email,
        "password": password
    })
    assert r.status_code == status.HTTP_201_CREATED

    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == status.HTTP_200_OK
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Token generation should work for any authenticated user
    resp = client.post('/api/mobile/token/generate', headers=headers)
    assert resp.status_code == 200, f"Authenticated user should be able to generate token: {resp.text}"
    data = resp.json()
    assert 'token' in data
    assert 'qr_code' in data


def test_token_generation_requires_authentication(client):
    """Test that unauthenticated requests are rejected."""
    # No auth header
    resp = client.post('/api/mobile/token/generate')
    assert resp.status_code == 401, "Unauthenticated request should be rejected"
