import sys
sys.path.insert(0, 'backend')

from app.core.database import SessionLocal
from app.services.users import get_user_by_username, create_user
from app.schemas.user import UserCreate

db = SessionLocal()
existing = get_user_by_username('admin', db)
print(f'Existing admin: {existing}')

if not existing:
    payload = UserCreate(
        username='admin',
        email='admin@example.com',
        password='changeme',
        role='admin'
    )
    user = create_user(payload, db)
    print(f'Created admin user: {user.username}')
else:
    print('Admin user already exists')

db.close()
