import sys
sys.path.insert(0, 'backend')

from app.core.database import SessionLocal
from app.models.user import User

db = SessionLocal()
users = db.query(User).all()
print(f'Total users: {len(users)}')
for u in users:
    print(f'  - {u.username} (role={u.role}, active={u.is_active})')
db.close()
