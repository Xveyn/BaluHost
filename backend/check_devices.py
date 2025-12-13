import sqlite3

conn = sqlite3.connect('baluhost.db')
cursor = conn.cursor()

print('=== Mobile Devices (neueste zuerst) ===')
cursor.execute('SELECT id, user_id, device_name, device_type, created_at FROM mobile_devices ORDER BY created_at DESC LIMIT 5')
for row in cursor.fetchall():
    print(f'ID: {row[0]}')
    print(f'User: {row[1]}')
    print(f'Name: {row[2]}')
    print(f'Type: {row[3]}')
    print(f'Created: {row[4]}')
    print('---')

conn.close()
