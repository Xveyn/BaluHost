-- Fix PostgreSQL sequences after SQLite migration
-- This script resets all auto-increment sequences to match the current MAX(id) values

-- Fix audit_logs sequence
SELECT setval(pg_get_serial_sequence('audit_logs', 'id'), COALESCE((SELECT MAX(id) FROM audit_logs), 1), true);

-- Fix users sequence
SELECT setval(pg_get_serial_sequence('users', 'id'), COALESCE((SELECT MAX(id) FROM users), 1), true);

-- Fix file_metadata sequence
SELECT setval(pg_get_serial_sequence('file_metadata', 'id'), COALESCE((SELECT MAX(id) FROM file_metadata), 1), true);

-- Fix shares sequence
SELECT setval(pg_get_serial_sequence('shares', 'id'), COALESCE((SELECT MAX(id) FROM shares), 1), true);

-- Fix mobile_devices sequence
SELECT setval(pg_get_serial_sequence('mobile_devices', 'id'), COALESCE((SELECT MAX(id) FROM mobile_devices), 1), true);

-- Fix vpn_clients sequence
SELECT setval(pg_get_serial_sequence('vpn_clients', 'id'), COALESCE((SELECT MAX(id) FROM vpn_clients), 1), true);

-- Fix backups sequence
SELECT setval(pg_get_serial_sequence('backups', 'id'), COALESCE((SELECT MAX(id) FROM backups), 1), true);

-- Fix sync_folders sequence
SELECT setval(pg_get_serial_sequence('sync_folders', 'id'), COALESCE((SELECT MAX(id) FROM sync_folders), 1), true);

-- Display current sequence values
SELECT
    'audit_logs' as table_name,
    currval(pg_get_serial_sequence('audit_logs', 'id')) as current_sequence_value,
    (SELECT MAX(id) FROM audit_logs) as max_id
UNION ALL
SELECT
    'users',
    currval(pg_get_serial_sequence('users', 'id')),
    (SELECT MAX(id) FROM users)
UNION ALL
SELECT
    'file_metadata',
    currval(pg_get_serial_sequence('file_metadata', 'id')),
    (SELECT MAX(id) FROM file_metadata)
UNION ALL
SELECT
    'shares',
    currval(pg_get_serial_sequence('shares', 'id')),
    (SELECT MAX(id) FROM shares)
UNION ALL
SELECT
    'mobile_devices',
    currval(pg_get_serial_sequence('mobile_devices', 'id')),
    (SELECT MAX(id) FROM mobile_devices)
UNION ALL
SELECT
    'vpn_clients',
    currval(pg_get_serial_sequence('vpn_clients', 'id')),
    (SELECT MAX(id) FROM vpn_clients)
UNION ALL
SELECT
    'backups',
    currval(pg_get_serial_sequence('backups', 'id')),
    (SELECT MAX(id) FROM backups)
UNION ALL
SELECT
    'sync_folders',
    currval(pg_get_serial_sequence('sync_folders', 'id')),
    (SELECT MAX(id) FROM sync_folders);
