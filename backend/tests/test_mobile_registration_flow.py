import os
from datetime import datetime, timedelta, timezone


def test_mobile_registration_flow():
    # Use an in-memory database for isolation and skip full app init
    os.environ['SKIP_APP_INIT'] = '1'
    os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

    # Import app modules after env override
    from fastapi.testclient import TestClient
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
