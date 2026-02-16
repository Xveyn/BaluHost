import { createElement } from 'react';
import { Lock, FileText, Terminal, Activity, Users } from 'lucide-react';
import type { ApiSection } from './types';

const icon = (Icon: React.ComponentType<{ className?: string }>) =>
  createElement(Icon, { className: 'w-5 h-5' });

export const coreSections: ApiSection[] = [
  {
    title: 'Authentication',
    icon: icon(Lock),
    endpoints: [
      {
        method: 'POST',
        path: '/api/auth/login',
        description: 'Login',
        body: [
          { field: 'username', type: 'string', required: true, description: 'Username' },
          { field: 'password', type: 'string', required: true, description: 'Password' },
        ],
        response: `{
  "access_token": "eyJhbGc...",
  "token_type": "bearer",
  "user": {
    "id": "uuid",
    "username": "admin",
    "email": "admin@baluhost.local",
    "role": "admin"
  }
}`,
      },
      {
        method: 'POST',
        path: '/api/auth/register',
        description: 'Register',
        body: [
          { field: 'username', type: 'string', required: true, description: 'Username' },
          { field: 'email', type: 'string', required: true, description: 'Email address' },
          { field: 'password', type: 'string', required: true, description: 'Password' },
        ],
        response: `{
  "access_token": "eyJhbGc...",
  "token_type": "bearer",
  "user": {
    "id": "uuid",
    "username": "newuser",
    "email": "user@example.com",
    "role": "user"
  }
}`,
      },
      {
        method: 'GET',
        path: '/api/auth/me',
        description: 'Read Current User',
        requiresAuth: true,
        response: `{
  "id": 1,
  "username": "admin",
  "email": "admin@baluhost.local",
  "role": "admin"
}`,
      },
      {
        method: 'POST',
        path: '/api/auth/change-password',
        description: 'Change Password',
        requiresAuth: true,
        body: [
          { field: 'current_password', type: 'string', required: true, description: 'Current password' },
          { field: 'new_password', type: 'string', required: true, description: 'New password' },
        ],
        response: '{ "message": "Password changed successfully" }',
      },
      {
        method: 'POST',
        path: '/api/auth/logout',
        description: 'Logout',
        requiresAuth: true,
        response: '{ "message": "Logged out successfully" }',
      },
      {
        method: 'POST',
        path: '/api/auth/refresh',
        description: 'Refresh Token',
        requiresAuth: true,
        response: `{
  "access_token": "eyJhbGc...",
  "token_type": "bearer"
}`,
      },
    ],
  },
  {
    title: 'Files',
    icon: icon(FileText),
    endpoints: [
      {
        method: 'GET',
        path: '/api/files/list',
        description: 'List Files',
        requiresAuth: true,
        params: [
          { name: 'path', type: 'string', required: false, description: 'Directory path (default: root)' },
        ],
        response: `{
  "files": [
    {
      "name": "document.pdf",
      "path": "/document.pdf",
      "size": 1048576,
      "is_directory": false,
      "modified": "2025-11-23T10:30:00",
      "owner": "admin",
      "permissions": "rw-r--r--"
    }
  ],
  "current_path": "/"
}`,
      },
      {
        method: 'POST',
        path: '/api/files/check-exists',
        description: 'Check If File Exists',
        requiresAuth: true,
        body: [
          { field: 'path', type: 'string', required: true, description: 'File path to check' },
        ],
        response: '{ "exists": true }',
      },
      {
        method: 'GET',
        path: '/api/files/permissions',
        description: 'Get File Permissions',
        requiresAuth: true,
        params: [
          { name: 'path', type: 'string', required: true, description: 'File path' },
        ],
        response: `{
  "path": "/document.pdf",
  "owner": "admin",
  "can_read": true,
  "can_write": true,
  "can_delete": true
}`,
      },
      {
        method: 'PUT',
        path: '/api/files/permissions',
        description: 'Update File Permissions',
        requiresAuth: true,
        body: [
          { field: 'path', type: 'string', required: true, description: 'File path' },
          { field: 'can_read', type: 'boolean', required: false, description: 'Read permission' },
          { field: 'can_write', type: 'boolean', required: false, description: 'Write permission' },
        ],
        response: '{ "path": "/document.pdf", "can_read": true, "can_write": true }',
      },
      {
        method: 'GET',
        path: '/api/files/mountpoints',
        description: 'Get Available Mountpoints',
        requiresAuth: true,
        response: `[
  { "name": "md0", "path": "/mnt/raid", "total": 10737418240, "used": 5368709120 }
]`,
      },
      {
        method: 'GET',
        path: '/api/files/download/{resource_path}',
        description: 'Download File by Path',
        requiresAuth: true,
        params: [
          { name: 'resource_path', type: 'string', required: true, description: 'File path' },
        ],
        response: 'Binary file content',
      },
      {
        method: 'GET',
        path: '/api/files/download/{file_id}',
        description: 'Download File by ID',
        requiresAuth: true,
        params: [
          { name: 'file_id', type: 'integer', required: true, description: 'File ID' },
        ],
        response: 'Binary file content',
      },
      {
        method: 'POST',
        path: '/api/files/upload',
        description: 'Upload File',
        requiresAuth: true,
        body: [
          { field: 'file', type: 'file', required: true, description: 'File to upload' },
          { field: 'path', type: 'string', required: false, description: 'Target directory path' },
        ],
        response: '{ "filename": "uploaded.txt", "path": "/uploaded.txt", "size": 2048 }',
      },
      {
        method: 'GET',
        path: '/api/files/storage/available',
        description: 'Get Available Storage',
        requiresAuth: true,
        response: '{ "total": 10737418240, "used": 5368709120, "available": 5368709120, "percent": 50.0 }',
      },
      {
        method: 'POST',
        path: '/api/files/folder',
        description: 'Create Folder',
        requiresAuth: true,
        body: [
          { field: 'path', type: 'string', required: true, description: 'Folder path' },
        ],
        response: '{ "path": "/new_folder", "message": "Folder created" }',
      },
      {
        method: 'POST',
        path: '/api/files/mkdir',
        description: 'Create Directory (Alias)',
        requiresAuth: true,
        body: [
          { field: 'path', type: 'string', required: true, description: 'Directory path' },
        ],
        response: '{ "path": "/new_dir", "message": "Directory created" }',
      },
      {
        method: 'POST',
        path: '/api/files/delete',
        description: 'Delete Path (POST)',
        requiresAuth: true,
        body: [
          { field: 'path', type: 'string', required: true, description: 'File or folder path' },
        ],
        response: '{ "message": "Path deleted successfully" }',
      },
      {
        method: 'DELETE',
        path: '/api/files/{resource_path}',
        description: 'Delete Path',
        requiresAuth: true,
        params: [
          { name: 'resource_path', type: 'string', required: true, description: 'File or folder path' },
        ],
        response: '{ "message": "Path deleted successfully" }',
      },
      {
        method: 'PUT',
        path: '/api/files/rename',
        description: 'Rename Path',
        requiresAuth: true,
        body: [
          { field: 'old_path', type: 'string', required: true, description: 'Current path' },
          { field: 'new_path', type: 'string', required: true, description: 'New path' },
        ],
        response: '{ "old_path": "/old.txt", "new_path": "/new.txt", "message": "Path renamed" }',
      },
      {
        method: 'PUT',
        path: '/api/files/move',
        description: 'Move Path',
        requiresAuth: true,
        body: [
          { field: 'source', type: 'string', required: true, description: 'Source path' },
          { field: 'destination', type: 'string', required: true, description: 'Destination path' },
        ],
        response: '{ "source": "/file.txt", "destination": "/folder/file.txt", "message": "Path moved" }',
      },
    ],
  },
  {
    title: 'Logging',
    icon: icon(Terminal),
    endpoints: [
      {
        method: 'GET',
        path: '/api/logging/disk-io',
        description: 'Get Disk-IO Logs',
        requiresAuth: true,
        params: [
          { name: 'limit', type: 'integer', required: false, description: 'Number of logs (default: 100)' },
        ],
        response: `{
  "logs": [
    {
      "timestamp": "2025-11-23T10:30:00",
      "operation": "read",
      "device": "/dev/sda1",
      "bytes": 4096,
      "duration_ms": 2.5
    }
  ]
}`,
      },
      {
        method: 'GET',
        path: '/api/logging/file-access',
        description: 'Get File Access Logs',
        requiresAuth: true,
        params: [
          { name: 'limit', type: 'integer', required: false, description: 'Number of logs (default: 100)' },
        ],
        response: `{
  "logs": [
    {
      "timestamp": "2025-11-23T10:30:00",
      "user": "admin",
      "action": "download",
      "path": "/document.pdf",
      "success": true
    }
  ]
}`,
      },
      {
        method: 'GET',
        path: '/api/logging/stats',
        description: 'Get Logging Stats',
        requiresAuth: true,
        response: '{ "total_logs": 15234, "disk_io_logs": 8500, "file_access_logs": 4234, "security_logs": 2500 }',
      },
      {
        method: 'GET',
        path: '/api/logging/audit',
        description: 'Get Audit Logs',
        requiresAuth: true,
        params: [
          { name: 'limit', type: 'integer', required: false, description: 'Number of logs (default: 100)' },
          { name: 'event_type', type: 'string', required: false, description: 'Filter by event type' },
        ],
        response: `{
  "logs": [
    {
      "timestamp": "2025-11-23T10:30:00",
      "event_type": "AUTH",
      "user": "admin",
      "action": "login",
      "success": true
    }
  ]
}`,
      },
    ],
  },
  {
    title: 'System',
    icon: icon(Activity),
    endpoints: [
      { method: 'GET', path: '/api/system/mode', description: 'Get System Mode', requiresAuth: true, response: '{ "mode": "dev" }' },
      {
        method: 'GET',
        path: '/api/system/info',
        description: 'Get System Info',
        requiresAuth: true,
        response: `{
  "hostname": "baluhost-nas",
  "os": "Linux",
  "os_version": "5.15.0",
  "architecture": "x86_64",
  "cpu_count": 8,
  "total_memory": 17179869184
}`,
      },
      { method: 'GET', path: '/api/system/info/local', description: 'Get Local System Info', requiresAuth: true, response: '{ "hostname": "baluhost-nas", "local_ip": "192.168.1.100" }' },
      { method: 'GET', path: '/api/system/storage', description: 'Get Storage Info', requiresAuth: true, response: '{ "total": 10737418240, "used": 5368709120, "available": 5368709120, "percent": 50.0 }' },
      { method: 'GET', path: '/api/system/storage/aggregated', description: 'Get Aggregated Storage', requiresAuth: true, response: '{ "total": 10737418240, "used": 5368709120, "raid_arrays": [...] }' },
      { method: 'GET', path: '/api/system/quota', description: 'Get Quota Status', requiresAuth: true, response: '{ "used": 1073741824, "limit": 5368709120, "percent": 20.0 }' },
      { method: 'GET', path: '/api/system/processes', description: 'Get BaluHost Processes', requiresAuth: true, response: '{ "processes": [...] }' },
      {
        method: 'GET',
        path: '/api/system/telemetry/history',
        description: 'Get Telemetry History',
        requiresAuth: true,
        params: [
          { name: 'samples', type: 'integer', required: false, description: 'Number of samples' },
        ],
        response: '{ "samples": [...] }',
      },
      {
        method: 'POST',
        path: '/api/system/shutdown',
        description: 'Schedule Application Shutdown (Admin)',
        requiresAuth: true,
        response: '{ "message": "Shutdown scheduled", "initiated_by": "admin", "eta_seconds": 3 }',
      },
      {
        method: 'GET',
        path: '/api/system/smart/status',
        description: 'Get SMART Data',
        requiresAuth: true,
        response: `{
  "devices": [
    {
      "device": "/dev/sda",
      "model": "Samsung SSD 970 EVO",
      "health": "PASSED",
      "temperature": 35
    }
  ]
}`,
      },
      { method: 'GET', path: '/api/system/smart/mode', description: 'Get SMART Mode', requiresAuth: true, response: '{ "mode": "simulated" }' },
      { method: 'POST', path: '/api/system/smart/toggle-mode', description: 'Toggle SMART Mode (Admin)', requiresAuth: true, response: '{ "mode": "real" }' },
      { method: 'POST', path: '/api/system/smart/test', description: 'Run SMART Test (Admin)', requiresAuth: true, body: [{ field: 'device', type: 'string', required: true, description: 'Device path' }], response: '{ "message": "SMART test started" }' },
      {
        method: 'GET',
        path: '/api/system/raid/status',
        description: 'Get RAID Status',
        requiresAuth: true,
        response: `{
  "arrays": [
    {
      "device": "/dev/md0",
      "level": "RAID1",
      "state": "active",
      "devices": ["/dev/sda1", "/dev/sdb1"],
      "health": "clean"
    }
  ]
}`,
      },
      { method: 'GET', path: '/api/system/raid/available-disks', description: 'Get Available Disks', requiresAuth: true, response: '{ "disks": [...] }' },
      { method: 'POST', path: '/api/system/raid/create-array', description: 'Create RAID Array (Admin)', requiresAuth: true, body: [{ field: 'level', type: 'string', required: true, description: 'RAID level' }, { field: 'disks', type: 'string[]', required: true, description: 'Disk device paths' }], response: '{ "success": true, "message": "Array created" }' },
      { method: 'POST', path: '/api/system/raid/delete-array', description: 'Delete RAID Array (Admin)', requiresAuth: true, body: [{ field: 'array', type: 'string', required: true, description: 'Array device path' }], response: '{ "success": true }' },
      { method: 'POST', path: '/api/system/raid/format-disk', description: 'Format Disk (Admin)', requiresAuth: true, body: [{ field: 'device', type: 'string', required: true, description: 'Device to format' }], response: '{ "success": true }' },
      { method: 'POST', path: '/api/system/raid/degrade', description: 'Degrade RAID Array (Admin)', requiresAuth: true, response: '{ "success": true }' },
      { method: 'POST', path: '/api/system/raid/rebuild', description: 'Rebuild RAID Array (Admin)', requiresAuth: true, response: '{ "success": true }' },
      { method: 'POST', path: '/api/system/raid/finalize', description: 'Finalize RAID Setup (Admin)', requiresAuth: true, response: '{ "success": true }' },
      { method: 'POST', path: '/api/system/raid/options', description: 'Set RAID Options (Admin)', requiresAuth: true, response: '{ "success": true }' },
      { method: 'POST', path: '/api/system/raid/scrub', description: 'Start RAID Scrub (Admin)', requiresAuth: true, response: '{ "success": true }' },
      { method: 'POST', path: '/api/system/raid/confirm/request', description: 'Request RAID Confirmation', requiresAuth: true, response: '{ "token": "abc123", "expires_at": "..." }' },
      { method: 'POST', path: '/api/system/raid/confirm/execute', description: 'Execute Confirmed RAID Action', requiresAuth: true, response: '{ "success": true }' },
      { method: 'GET', path: '/api/system/raid/cache/status', description: 'Get RAID Cache Status', requiresAuth: true, response: '[{ "array": "/dev/md0", "cache_device": "/dev/nvme0n1p1" }]' },
      { method: 'POST', path: '/api/system/raid/cache/attach', description: 'Attach RAID Cache (Admin)', requiresAuth: true, response: '{ "success": true }' },
      { method: 'POST', path: '/api/system/raid/cache/detach', description: 'Detach RAID Cache (Admin)', requiresAuth: true, response: '{ "success": true }' },
      { method: 'POST', path: '/api/system/raid/cache/configure', description: 'Configure RAID Cache (Admin)', requiresAuth: true, response: '{ "success": true }' },
      { method: 'POST', path: '/api/system/raid/cache/external-bitmap', description: 'Set External Bitmap (Admin)', requiresAuth: true, response: '{ "success": true }' },
      { method: 'GET', path: '/api/system/disk-io/history', description: 'Get Disk I/O History', requiresAuth: true, response: '{ "samples": [...] }' },
      { method: 'GET', path: '/api/system/health', description: 'Get System Health', requiresAuth: true, response: '{ "status": "healthy", "checks": [...] }' },
      { method: 'GET', path: '/api/system/audit-logging', description: 'Get Audit Logging Status', requiresAuth: true, response: '{ "enabled": true }' },
      { method: 'POST', path: '/api/system/audit-logging', description: 'Toggle Audit Logging (Admin)', requiresAuth: true, response: '{ "enabled": false }' },
    ],
  },
  {
    title: 'Users',
    icon: icon(Users),
    endpoints: [
      {
        method: 'GET',
        path: '/api/users/',
        description: 'List Users (Admin)',
        requiresAuth: true,
        params: [
          { name: 'search', type: 'string', required: false, description: 'Search by username or email' },
          { name: 'role', type: 'string', required: false, description: 'Filter by role' },
          { name: 'is_active', type: 'boolean', required: false, description: 'Filter by active status' },
          { name: 'sort_by', type: 'string', required: false, description: 'Sort field (default: created_at)' },
          { name: 'sort_order', type: 'string', required: false, description: 'Sort order: asc/desc' },
        ],
        response: `{
  "users": [
    { "id": 1, "username": "admin", "email": "admin@baluhost.local", "role": "admin", "is_active": true }
  ],
  "total": 5, "active": 4, "inactive": 1, "admins": 1
}`,
      },
      {
        method: 'POST',
        path: '/api/users/',
        description: 'Create User (Admin)',
        requiresAuth: true,
        body: [
          { field: 'username', type: 'string', required: true, description: 'Username' },
          { field: 'email', type: 'string', required: true, description: 'Email address' },
          { field: 'password', type: 'string', required: true, description: 'Password' },
          { field: 'role', type: 'string', required: false, description: 'Role: admin/user (default: user)' },
        ],
        response: '{ "id": 2, "username": "newuser", "email": "user@example.com", "role": "user", "is_active": true }',
      },
      {
        method: 'PUT',
        path: '/api/users/{user_id}',
        description: 'Update User (Admin)',
        requiresAuth: true,
        params: [{ name: 'user_id', type: 'integer', required: true, description: 'User ID' }],
        body: [
          { field: 'email', type: 'string', required: false, description: 'New email' },
          { field: 'role', type: 'string', required: false, description: 'New role' },
          { field: 'is_active', type: 'boolean', required: false, description: 'Active status' },
        ],
        response: '{ "id": 2, "username": "user", "email": "updated@example.com", "role": "user" }',
      },
      {
        method: 'DELETE',
        path: '/api/users/{user_id}',
        description: 'Delete User (Admin)',
        requiresAuth: true,
        params: [{ name: 'user_id', type: 'integer', required: true, description: 'User ID' }],
        response: '204 No Content',
      },
      {
        method: 'POST',
        path: '/api/users/bulk-delete',
        description: 'Bulk Delete Users (Admin)',
        requiresAuth: true,
        body: [{ field: 'user_ids', type: 'integer[]', required: true, description: 'Array of user IDs' }],
        response: '{ "deleted": 3 }',
      },
      {
        method: 'PATCH',
        path: '/api/users/{user_id}/toggle-active',
        description: 'Toggle User Active Status (Admin)',
        requiresAuth: true,
        params: [{ name: 'user_id', type: 'integer', required: true, description: 'User ID' }],
        response: '{ "id": 2, "username": "user", "is_active": false }',
      },
      {
        method: 'POST',
        path: '/api/users/{user_id}/avatar',
        description: 'Upload User Avatar',
        requiresAuth: true,
        params: [{ name: 'user_id', type: 'integer', required: true, description: 'User ID' }],
        body: [{ field: 'avatar', type: 'file', required: true, description: 'Image file (JPEG, PNG, GIF, WebP)' }],
        response: '{ "id": 1, "username": "admin", "avatar_url": "/avatars/abc123.png" }',
      },
    ],
  },
];
