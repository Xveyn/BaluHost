# Debug script to reproduce login
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import os

os.environ.setdefault('NAS_MODE','dev')
os.environ.setdefault('SKIP_APP_INIT','1')

from app.main import app
from app.models.base import Base
from app.core.config import settings
from app.core.database import get_db
from app.services import users as user_service
from app.schemas.user import UserCreate

# Setup in-memory DB
engine = create_engine('sqlite:///:memory:', connect_args={'check_same_thread': False}, poolclass=StaticPool)
Base.metadata.create_all(bind=engine)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db_session = TestingSessionLocal()

# Create admin
if not user_service.get_user_by_username(settings.admin_username, db=db_session):
    user_service.create_user(UserCreate(username=settings.admin_username, email=settings.admin_email, password=settings.admin_password, role=settings.admin_role), db=db_session)

# Override dependency

def override_get_db():
    try:
        yield db_session
    finally:
        pass

app.dependency_overrides[get_db] = override_get_db

with TestClient(app) as client:
    resp = client.post(f"{settings.api_prefix}/auth/login", json={"username": settings.admin_username, "password": settings.admin_password})
    print('status', resp.status_code)
    try:
        print('json', resp.json())
    except Exception as e:
        print('no json', e)

# cleanup
app.dependency_overrides.clear()
